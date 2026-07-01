"""
get.py

專門負責：
1. 把 main.py 當下分析出的表格與圖表輸出成 docs/index.html。
2. 可選擇把 docs/index.html 透過 GitHub Contents API 回寫到 GitHub repo，讓 GitHub Pages 顯示同一份靜態圖表。

設計重點：
- main.py 仍是主檔。
- get.py 不重新抓 Pionex API，只接收 main.py 已經算好的 df / plot_results。
- Streamlit Cloud 產出的 docs/index.html 是臨時檔；若要讓 GitHub Pages 更新，必須呼叫 sync_index_to_github()。
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Iterable, Optional, Any

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd
import requests


TW_TZ = timezone(timedelta(hours=8))
OUTPUT_DIR = Path("docs")
OUTPUT_FILE = "index.html"
GITHUB_API_BASE = "https://api.github.com"


# ==================== 中文字型設定 ====================
def setup_cjk_font() -> None:
    """盡量避免靜態圖表中文變成方塊。"""
    candidates = [
        "Noto Sans CJK TC", "Noto Sans CJK SC", "Noto Sans TC", "Noto Sans SC",
        "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "PingFang SC",
        "Heiti TC", "SimHei", "WenQuanYi Zen Hei", "Arial Unicode MS",
    ]
    installed = {f.name for f in fm.fontManager.ttflist}
    chosen = next((name for name in candidates if name in installed), None)
    if chosen:
        plt.rcParams["font.sans-serif"] = [chosen]
    plt.rcParams["axes.unicode_minus"] = False


setup_cjk_font()


# ==================== 工具函式 ====================
def _escape(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _visible_table_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "幣種", "現價", "差%", "BB日中軌", "BB中軌",
        "1D前", "1D當", "4H前", "4H當", "距離中軌%",
    ]
    return [c for c in preferred if c in df.columns]


def _cell_class(column: str, row: pd.Series) -> str:
    if column == "現價":
        price = row.get("_price", None)
        bb = row.get("_bb1d", None)
        try:
            if bb and float(bb) > 0 and float(price) > float(bb):
                return "pos"
            if bb and float(bb) > 0 and float(price) < float(bb):
                return "neg"
        except Exception:
            return ""

    if column == "差%":
        text = str(row.get("差%", ""))
        if "🟢" in text or "+" in text:
            return "pos"
        if "🔴" in text or "-" in text:
            return "neg"

    text = str(row.get(column, ""))
    if text in ["🟢", "✅"]:
        return "pos"
    if text in ["🔴", "❌"]:
        return "neg"
    if text in ["⚫", "—"]:
        return "muted"
    return ""


def _render_table_html(df: pd.DataFrame) -> str:
    cols = _visible_table_columns(df)
    thead = "".join(f"<th>{_escape(c)}</th>" for c in cols)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in cols:
            css = _cell_class(col, row)
            cls = f" class=\"{css}\"" if css else ""
            cells.append(f"<td{cls}>{_escape(row.get(col, '—'))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    if not rows:
        rows.append(f"<tr><td colspan=\"{len(cols)}\">目前沒有資料</td></tr>")

    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr>{thead}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def _date_labels_from_times(ha_times: list, n: int) -> list[str]:
    if ha_times:
        try:
            # 保持與 main.py 原圖相同邏輯：用最後一根時間回推 n 天。
            last_ts = float(ha_times[-1]) / 1000.0
            last_date = datetime.fromtimestamp(last_ts, tz=TW_TZ).date()
            return [(last_date - timedelta(days=n - 1 - i)).strftime("%m/%d") for i in range(n)]
        except Exception:
            pass
    return [str(i) for i in range(n)]


def _chart_to_base64(r: dict) -> str:
    ha_series = r.get("_ha_pct_series", [0.0]) or [0.0]
    curr_pct = float(r.get("_ha_curr_pct", 0.0) or 0.0)
    ha_opens = r.get("_ha_opens_last20", []) or []
    ha_closes = r.get("_ha_closes_last20", []) or []
    ha_times = r.get("_ha_times_last20", []) or []

    fig, ax = plt.subplots(figsize=(6.4, 3.2), facecolor="#1e293b")
    ax.set_facecolor("#1e293b")

    n = len(ha_series)
    x = list(range(n))
    y = [float(v) for v in ha_series]
    date_labels = _date_labels_from_times(ha_times, n)

    for i in range(max(n - 1, 0)):
        if i < len(ha_opens) and i < len(ha_closes):
            is_bull = float(ha_closes[i]) > float(ha_opens[i])
            seg_color = "#FFEB3B" if is_bull else "#B39DDB"
        else:
            seg_color = "#22c55e" if curr_pct >= 0 else "#ef4444"
        ax.step([x[i], x[i + 1]], [y[i], y[i + 1]], where="post", color=seg_color, linewidth=2.3)

    if n > 0:
        ax.plot(x[-1], y[-1], "o", color="white", markersize=8, zorder=7)
        final_color = "#FFEB3B" if (ha_closes and ha_opens and float(ha_closes[-1]) > float(ha_opens[-1])) else "#B39DDB"
        ax.plot(x[-1], y[-1], "o", color=final_color, markersize=4.5, zorder=8)
    else:
        final_color = "#B39DDB"

    ax.axhline(0, color="#64748b", linestyle="--", linewidth=1.5)
    ax.fill_between(x, y, 0, where=(np.array(y) >= 0), alpha=0.12, color="#22c55e", step="post", zorder=1)
    ax.fill_between(x, y, 0, where=(np.array(y) < 0), alpha=0.12, color="#ef4444", step="post", zorder=1)

    if y:
        ax.set_ylim(min(y) - 4, max(y) + 4)
    ax.set_xlim(-0.5, max(n - 0.5, 0.5))
    ax.set_xticks(x[::2])
    ax.set_xticklabels(date_labels[::2], rotation=45, ha="right", fontsize=7, color="#94a3b8")
    ax.set_ylabel("乖離中軌%", fontsize=9, color="#94a3b8")
    ax.set_title(f"日線中軌 = {r.get('BB日中軌', '—')}", fontsize=9, color="#cbd5e1", pad=4)
    ax.tick_params(colors="#94a3b8", labelsize=7)
    ax.grid(True, linestyle=":", alpha=0.35, color="#475569")
    for spine in ax.spines.values():
        spine.set_color("#475569")
        spine.set_alpha(0.6)

    offset_y = 10 if curr_pct >= 0 else -14
    va_align = "bottom" if curr_pct >= 0 else "top"
    if n > 0:
        ax.annotate(
            f"{curr_pct:+.2f}%",
            xy=(x[-1], y[-1]),
            xytext=(0, offset_y),
            textcoords="offset points",
            ha="center",
            va=va_align,
            fontsize=8,
            color=final_color,
            fontweight="bold",
        )

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=145, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _render_chart_cards(plot_results: Iterable[dict], max_charts: Optional[int] = None) -> str:
    cards = []
    for idx, r in enumerate(plot_results):
        if max_charts is not None and idx >= max_charts:
            break
        img64 = _chart_to_base64(r)
        symbol = _escape(r.get("幣種", "—"))
        price = _escape(r.get("現價", "—"))
        diff = _escape(r.get("差%", "—"))
        h4_prev = _escape(r.get("4H前", "—"))
        h4_now = _escape(r.get("4H當", "—"))
        cards.append(f"""
        <article class="chart-card">
          <div class="chart-title">
            <strong>{symbol}</strong>
            <span>現價 {price}</span>
            <span>目前偏離 {diff}</span>
            <span>4H前 {h4_prev} / 4H當 {h4_now}</span>
          </div>
          <img src="data:image/png;base64,{img64}" alt="{symbol} HA vs BB chart">
        </article>
        """)
    if not cards:
        return "<p class='muted'>目前沒有可輸出的圖表。</p>"
    return "\n".join(cards)


def _normalise_for_hash(value: Any) -> Any:
    """把 dataframe / numpy / pandas 物件轉為穩定 JSON，可用來判斷圖表資料是否真的改變。"""
    if isinstance(value, pd.DataFrame):
        cols = [c for c in _visible_table_columns(value) if c in value.columns]
        extra_cols = [c for c in ["_price", "_bb1d", "_bb_pct", "_abs_dev"] if c in value.columns]
        return value[cols + extra_cols].fillna("—").to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.to_dict()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), 10)
    if isinstance(value, float):
        return round(value, 10)
    if isinstance(value, dict):
        keep = [
            "幣種", "現價", "差%", "BB日中軌", "BB中軌", "1D前", "1D當", "4H前", "4H當",
            "距離中軌%", "_price", "_bb1d", "_bb_pct", "_abs_dev", "_ha_pct_series",
            "_ha_curr_pct", "_ha_opens_last20", "_ha_closes_last20", "_ha_times_last20",
        ]
        return {k: _normalise_for_hash(value.get(k)) for k in keep if k in value}
    if isinstance(value, (list, tuple)):
        return [_normalise_for_hash(v) for v in value]
    if value is None:
        return None
    return value


def snapshot_hash(df: pd.DataFrame, plot_results: Iterable[dict], selection: str = "—", sort_option: str = "—") -> str:
    payload = {
        "selection": selection,
        "sort_option": sort_option,
        "table": _normalise_for_hash(df),
        "charts": _normalise_for_hash(list(plot_results)),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_index_html(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    title: str = "HA Crypto Terminal",
    max_charts: Optional[int] = None,
    generated_at: Optional[str] = None,
    data_hash: Optional[str] = None,
) -> str:
    plot_results = list(plot_results)
    generated_at = generated_at or datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    data_hash = data_hash or snapshot_hash(df, plot_results, selection=selection, sort_option=sort_option)
    short_hash = data_hash[:10]
    table_html = _render_table_html(df)
    chart_html = _render_chart_cards(plot_results, max_charts=max_charts)
    count = len(df) if isinstance(df, pd.DataFrame) else 0

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="snapshot-hash" content="{_escape(data_hash)}">
  <title>{_escape(title)}</title>
  <style>
    :root {{
      --bg: #1e293b;
      --panel: #172033;
      --panel2: #0f172a;
      --line: #334155;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --green: #22c55e;
      --red: #ef4444;
      --yellow: #FFEB3B;
      --neon: #13f21a;
      --purple: #B39DDB;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", "Microsoft JhengHei", monospace;
      line-height: 1.5;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(30, 41, 59, .92);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--line);
      padding: 16px 24px;
    }}
    main {{ padding: 20px 24px 36px; max-width: 1500px; margin: 0 auto; }}
    h1 {{ margin: 0; color: var(--yellow); font-size: 24px; letter-spacing: .5px; }}
    h2 {{ margin-top: 28px; font-size: 20px; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .badge {{ border: 1px solid rgba(19,242,26,.45); color: var(--neon); padding: 4px 8px; border-radius: 999px; background: rgba(15,23,42,.55); font-size: 12px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }}
    table {{ border-collapse: collapse; width: 100%; min-width: 820px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{ background: var(--panel2); color: #cbd5e1; font-size: 13px; }}
    td {{ font-size: 13px; }}
    tr:hover td {{ background: rgba(255,255,255,.025); }}
    .pos {{ color: var(--green); font-weight: 700; }}
    .neg {{ color: var(--red); font-weight: 700; }}
    .muted {{ color: var(--muted); }}
    .charts {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .chart-card {{ border: 1px solid var(--line); border-radius: 12px; background: var(--panel); padding: 12px; }}
    .chart-title {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; color: #cbd5e1; font-size: 13px; margin-bottom: 6px; }}
    .chart-title strong {{ color: white; font-size: 15px; }}
    .chart-card img {{ width: 100%; height: auto; display: block; }}
    footer {{ color: var(--muted); font-size: 12px; padding: 24px; text-align: center; }}
    @media (max-width: 900px) {{
      header, main {{ padding-left: 12px; padding-right: 12px; }}
      .charts {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>📈 {_escape(title)}</h1>
    <div class="meta">更新時間：{_escape(generated_at)} 台灣時間</div>
    <div class="badge-row">
      <span class="badge">選單：{_escape(selection)}</span>
      <span class="badge">表格筆數：{count}</span>
      <span class="badge">圖表排序：{_escape(sort_option)}</span>
      <span class="badge">輸出：docs/index.html</span>
      <span class="badge">snapshot：{_escape(short_hash)}</span>
    </div>
  </header>

  <main>
    <h2>表格快照</h2>
    {table_html}

    <h2>最近 20 根 HA 收盤價 vs BB中軌 % 偏差走勢圖</h2>
    <section class="charts">
      {chart_html}
    </section>
  </main>

  <footer>
    Static snapshot generated from Streamlit runtime. Data source follows main.py runtime calculation.
  </footer>
</body>
</html>
"""


def write_index_html(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
    max_charts: Optional[int] = None,
) -> Path:
    """寫出 docs/index.html，回傳實際路徑。"""
    plot_results = list(plot_results)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_hash = snapshot_hash(df, plot_results, selection=selection, sort_option=sort_option)
    html_text = build_index_html(
        df=df,
        plot_results=plot_results,
        selection=selection,
        sort_option=sort_option,
        title=title,
        max_charts=max_charts,
        data_hash=data_hash,
    )
    index_path = out_dir / OUTPUT_FILE
    index_path.write_text(html_text, encoding="utf-8")
    return index_path


# ==================== GitHub Pages 回寫 ====================
def _github_headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "crypto-monitor-go-streamlit-sync",
    }


def _extract_snapshot_hash(html_text: str) -> Optional[str]:
    m = re.search(r'<meta\s+name=["\']snapshot-hash["\']\s+content=["\']([^"\']+)["\']', html_text)
    if m:
        return m.group(1)
    return None


def _get_remote_file(repo: str, path: str, branch: str, token: str) -> dict:
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=_github_headers(token), params={"ref": branch}, timeout=30)
    if resp.status_code == 404:
        return {"exists": False, "sha": None, "content_text": None, "html_url": None}
    if resp.status_code >= 400:
        raise RuntimeError(f"GitHub 讀取遠端檔案失敗：HTTP {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    raw = data.get("content", "")
    encoding = data.get("encoding")
    content_text = None
    if raw and encoding == "base64":
        try:
            content_text = base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception:
            content_text = None
    return {
        "exists": True,
        "sha": data.get("sha"),
        "content_text": content_text,
        "html_url": data.get("html_url"),
    }


def push_file_to_github(
    local_file: str | Path,
    repo: str,
    token: str,
    branch: str = "main",
    repo_path: str = "docs/index.html",
    commit_message: Optional[str] = None,
    skip_if_same_snapshot: bool = True,
) -> dict:
    """
    透過 GitHub Contents API 建立或更新 repo 內的檔案。

    repo 格式："owner/repository"，例如 "levinlive1984-design/crypto-monitor-go"。
    token：Fine-grained token 或 classic PAT，需具備該 repo 的 Contents write 權限。
    """
    if not token:
        raise ValueError("缺少 GitHub token。請在 Streamlit Secrets 設定 GITHUB_TOKEN。")
    if not repo or "/" not in repo:
        raise ValueError("GITHUB_REPO 格式錯誤，應為 owner/repo，例如 levinlive1984-design/crypto-monitor-go。")

    local_path = Path(local_file)
    html_text = local_path.read_text(encoding="utf-8")
    local_hash = _extract_snapshot_hash(html_text)

    remote = _get_remote_file(repo=repo, path=repo_path, branch=branch, token=token)
    remote_hash = _extract_snapshot_hash(remote.get("content_text") or "") if remote.get("content_text") else None

    if skip_if_same_snapshot and local_hash and remote_hash and local_hash == remote_hash:
        return {
            "status": "skipped",
            "reason": "remote snapshot hash is identical",
            "snapshot_hash": local_hash,
            "repo_path": repo_path,
            "branch": branch,
            "html_url": remote.get("html_url"),
        }

    encoded = base64.b64encode(local_path.read_bytes()).decode("ascii")
    now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    commit_message = commit_message or f"update crypto static index {now_tw} TW"

    payload = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }
    if remote.get("sha"):
        payload["sha"] = remote["sha"]

    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{repo_path}"
    resp = requests.put(url, headers=_github_headers(token), json=payload, timeout=45)
    if resp.status_code >= 400:
        raise RuntimeError(f"GitHub 寫入遠端檔案失敗：HTTP {resp.status_code} {resp.text[:500]}")

    data = resp.json()
    return {
        "status": "updated" if remote.get("exists") else "created",
        "snapshot_hash": local_hash,
        "repo_path": repo_path,
        "branch": branch,
        "commit_sha": (data.get("commit") or {}).get("sha"),
        "content_url": ((data.get("content") or {}).get("html_url")),
    }


def sync_index_to_github(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str,
    sort_option: str,
    repo: str,
    token: str,
    branch: str = "main",
    repo_path: str = "docs/index.html",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
    max_charts: Optional[int] = None,
) -> dict:
    """
    main.py 呼叫用的一站式函式：
    1. 產生本次 Streamlit runtime 的 docs/index.html。
    2. 比對遠端 docs/index.html 的 snapshot-hash。
    3. 若資料已相同則略過；若資料不同則 commit 回 GitHub。
    """
    plot_results = list(plot_results)
    index_path = write_index_html(
        df=df,
        plot_results=plot_results,
        selection=selection,
        sort_option=sort_option,
        output_dir=output_dir,
        title=title,
        max_charts=max_charts,
    )
    data_hash = snapshot_hash(df, plot_results, selection=selection, sort_option=sort_option)
    result = push_file_to_github(
        local_file=index_path,
        repo=repo,
        token=token,
        branch=branch,
        repo_path=repo_path,
        commit_message=f"update crypto index {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} TW {data_hash[:8]}",
        skip_if_same_snapshot=True,
    )
    result["local_path"] = str(index_path)
    return result


# ==================== AI 分析用資料輸出：snapshot.json / latest_signals.txt ====================
# 這一段放在檔案最後，會覆蓋前面同名函式。
# 目的：index.html 給人看；snapshot.json 給 ChatGPT / API 讀取；latest_signals.txt 當備援文字版。
DATA_FILE = "snapshot.json"
SUMMARY_FILE = "latest_signals.txt"
AI_JSON_TEXT_FILE = "snapshot_pretty.txt"  # 給 ChatGPT / 瀏覽器穩定讀取的 text/plain 版 pretty JSON


def _to_plain(value: Any) -> Any:
    """轉成 JSON 可安全序列化的 Python 原生型別。"""
    if isinstance(value, pd.DataFrame):
        return [_to_plain(row) for row in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return _to_plain(value.to_dict())
    if isinstance(value, np.ndarray):
        return [_to_plain(v) for v in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return round(value, 10)
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if value is pd.NA:
        return None
    return value


def _records_from_df(df: pd.DataFrame) -> list[dict]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    keep = [
        "幣種", "現價", "差%", "BB日中軌", "BB中軌",
        "1D前", "1D當", "4H前", "4H當", "距離中軌%",
        "_price", "_bb1d", "_bb_pct", "_abs_dev",
    ]
    cols = [c for c in keep if c in df.columns]
    return _to_plain(df[cols].replace({np.nan: None}).to_dict(orient="records"))


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """把值安全轉為 float；無法轉換或 NaN/Inf 則回傳 default。"""
    try:
        if value is None or value is pd.NA:
            return default
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except Exception:
        return default


def _ha_step_color(open_value: Any, close_value: Any) -> str:
    """回傳使用者圖表中的階梯顏色語意：yellow=上梯，purple=下梯。"""
    o = _safe_float(open_value)
    c = _safe_float(close_value)
    if o is None or c is None:
        return "unknown"
    if c > o:
        return "yellow"
    if c < o:
        return "purple"
    return "flat"


def _ha_step_emoji(color: str) -> str:
    return {"yellow": "🟡", "purple": "🟣", "flat": "⚫"}.get(color, "—")


def _format_ladder_date(ts: Any, fallback_index: int) -> str:
    try:
        return datetime.fromtimestamp(float(ts) / 1000.0, tz=TW_TZ).strftime("%m/%d")
    except Exception:
        return str(fallback_index)


def _build_ladder_history(r: dict) -> list[dict]:
    """
    把 index.html 圖上那條黃/紫階梯，轉成 GPT 可直接讀的機器資料。
    pct = HA 收盤價相對「當天日線 BB 中軌」的百分比。
    color = yellow 代表 HA 收盤 > HA 開盤；purple 代表 HA 收盤 < HA 開盤。
    """
    pct_series = r.get("_ha_pct_series", []) or []
    opens = r.get("_ha_opens_last20", []) or []
    closes = r.get("_ha_closes_last20", []) or []
    times = r.get("_ha_times_last20", []) or []
    n = len(pct_series)
    history = []

    for i in range(n):
        pct = _safe_float(pct_series[i], 0.0)
        color = _ha_step_color(opens[i] if i < len(opens) else None, closes[i] if i < len(closes) else None)
        prev_pct = _safe_float(pct_series[i - 1], None) if i > 0 else None
        history.append({
            "index": i,
            "date": _format_ladder_date(times[i], i) if i < len(times) else str(i),
            "pct_vs_midline": round(float(pct), 6) if pct is not None else None,
            "color": color,
            "color_emoji": _ha_step_emoji(color),
            "meaning": "平均K收盤上梯/多方連續性" if color == "yellow" else ("平均K收盤下梯/空方連續性" if color == "purple" else "平盤/資料不足"),
            "above_midline": bool(pct is not None and pct >= 0),
            "near_midline": bool(pct is not None and abs(pct) <= 3.0),
            "crossed_above_midline": bool(prev_pct is not None and prev_pct < 0 and pct is not None and pct >= 0),
            "crossed_below_midline": bool(prev_pct is not None and prev_pct >= 0 and pct is not None and pct < 0),
            "is_latest": i == n - 1,
        })
    return history


def _current_color_run(history: list[dict]) -> dict:
    if not history:
        return {"color": "unknown", "start_index": None, "length": 0}
    color = history[-1].get("color", "unknown")
    start = len(history) - 1
    while start > 0 and history[start - 1].get("color") == color:
        start -= 1
    return {"color": color, "start_index": start, "length": len(history) - start}


def _build_pattern_flags(r: dict, history: list[dict]) -> dict:
    """把使用者討論的兩個核心型態做成明確布林欄位，避免 GPT 誤判資料不足。"""
    latest = history[-1] if history else {}
    run = _current_color_run(history)
    run_start = run.get("start_index")
    latest_pct = latest.get("pct_vs_midline")
    latest_color = latest.get("color", "unknown")

    previous_items = history[:run_start] if isinstance(run_start, int) else history[:-1]
    previous_purples_reversed = [h for h in reversed(previous_items) if h.get("color") == "purple"]
    previous_purple_pcts = [h.get("pct_vs_midline") for h in previous_purples_reversed if h.get("pct_vs_midline") is not None]
    yellow_ref = history[run_start] if isinstance(run_start, int) and 0 <= run_start < len(history) else latest
    yellow_ref_pct = yellow_ref.get("pct_vs_midline")

    def _count_yellow_over_prev_purples(ref_pct: Any, n: int = 3) -> int:
        ref = _safe_float(ref_pct)
        if ref is None:
            return 0
        return sum(1 for p in previous_purple_pcts[:n] if p is not None and ref > p)

    yellow_over_count_from_run_start = _count_yellow_over_prev_purples(yellow_ref_pct, 3)
    yellow_over_count_latest = _count_yellow_over_prev_purples(latest_pct, 3)
    yellow_over_count = max(yellow_over_count_from_run_start, yellow_over_count_latest)

    breakout_indices = [
        i for i, h in enumerate(history)
        if h.get("color") == "yellow" and h.get("pct_vs_midline") is not None and h["pct_vs_midline"] >= 0
    ]
    breakout_before_current_run = [i for i in breakout_indices if not isinstance(run_start, int) or i < run_start]
    last_breakout_idx = breakout_before_current_run[-1] if breakout_before_current_run else None

    pullback_items = []
    if isinstance(last_breakout_idx, int) and isinstance(run_start, int):
        pullback_items = history[last_breakout_idx + 1:run_start]

    purple_pullback_near_midline = any(
        h.get("color") == "purple"
        and h.get("pct_vs_midline") is not None
        and -4.0 <= h["pct_vs_midline"] <= 3.0
        for h in pullback_items
    )
    purple_pullback_not_deep_broken = True
    if pullback_items:
        pcts = [h["pct_vs_midline"] for h in pullback_items if h.get("pct_vs_midline") is not None]
        purple_pullback_not_deep_broken = bool(pcts and min(pcts) >= -6.0)

    four_h_red_to_green = (r.get("4H前") == "🔴" and r.get("4H當") == "🟢")
    four_h_green_green = (r.get("4H前") == "🟢" and r.get("4H當") == "🟢")

    breakout_pullback_restart = bool(
        latest_color == "yellow"
        and bool(breakout_before_current_run)
        and purple_pullback_near_midline
        and purple_pullback_not_deep_broken
    )

    po3_amd_yellow_over_2 = bool(latest_color == "yellow" and yellow_over_count >= 2)
    po3_amd_yellow_over_3 = bool(latest_color == "yellow" and yellow_over_count >= 3)
    below_midline_po3_amd = bool(
        latest_color == "yellow"
        and latest_pct is not None
        and latest_pct < 0
        and yellow_over_count >= 2
    )

    return {
        "analysis_ready": bool(len(history) >= 10 and latest_color in ["yellow", "purple", "flat"]),
        "latest_color": latest_color,
        "latest_color_emoji": _ha_step_emoji(latest_color),
        "latest_pct_vs_midline": latest_pct,
        "latest_above_midline": bool(latest_pct is not None and latest_pct >= 0),
        "latest_near_midline": bool(latest_pct is not None and abs(latest_pct) <= 3.0),
        "current_color_run": run,
        "had_yellow_above_midline_before_current_run": bool(breakout_before_current_run),
        "purple_pullback_near_midline_after_breakout": bool(purple_pullback_near_midline),
        "purple_pullback_not_deep_broken": bool(purple_pullback_not_deep_broken),
        "breakout_pullback_yellow_restart": breakout_pullback_restart,
        "previous_purple_pcts_for_po3": previous_purple_pcts[:3],
        "yellow_ref_pct_for_po3": yellow_ref_pct,
        "yellow_over_previous_purple_count": int(yellow_over_count),
        "yellow_over_2_previous_purple_steps": po3_amd_yellow_over_2,
        "yellow_over_3_previous_purple_steps": po3_amd_yellow_over_3,
        "below_midline_po3_amd_candidate": below_midline_po3_amd,
        "four_h_red_to_green": four_h_red_to_green,
        "four_h_green_green": four_h_green_green,
        "four_h_trigger_label": "4H前紅→4H當綠：最佳啟動" if four_h_red_to_green else ("4H綠→綠：偏多延續" if four_h_green_green else ("4H綠→紅：短線轉弱" if (r.get("4H前") == "🟢" and r.get("4H當") == "🔴") else "4H未啟動或偏弱")),
    }


def _classify_pattern(flags: dict) -> str:
    if flags.get("breakout_pullback_yellow_restart") and flags.get("four_h_red_to_green"):
        return "中軌突破回踩再啟動型"
    if flags.get("below_midline_po3_amd_candidate") and flags.get("yellow_over_3_previous_purple_steps"):
        return "中軌下方 PO3/AMD 強反轉型"
    if flags.get("below_midline_po3_amd_candidate"):
        return "中軌下方 PO3/AMD 反轉候選型"
    if flags.get("breakout_pullback_yellow_restart"):
        return "中軌突破回踩轉黃型"
    if flags.get("latest_color") == "yellow" and flags.get("latest_near_midline"):
        return "中軌附近磨合轉黃型"
    if flags.get("latest_color") == "purple":
        return "紫線未轉黃觀察型"
    return "一般觀察型"


def _score_hint(flags: dict, item: dict) -> int:
    """
    給 GPT 的機械分數提示，不是最終交易建議。
    正式分析仍可依使用者指令重新用 0~100 分排序。
    """
    score = 0

    if flags.get("breakout_pullback_yellow_restart"):
        score += 45
    elif flags.get("had_yellow_above_midline_before_current_run") and flags.get("latest_color") == "yellow":
        score += 30
    elif flags.get("latest_color") == "yellow":
        score += 22
    elif flags.get("latest_color") == "purple":
        score += 6

    over_count = int(flags.get("yellow_over_previous_purple_count") or 0)
    if flags.get("below_midline_po3_amd_candidate"):
        score += 28 + min(over_count, 3) * 4
    elif over_count >= 2 and flags.get("latest_color") == "yellow":
        score += 18 + min(over_count, 3) * 3

    if flags.get("four_h_red_to_green"):
        score += 20
    elif flags.get("four_h_green_green"):
        score += 14
    elif item.get("4H前") == "🟢" and item.get("4H當") == "🔴":
        score -= 8
    elif item.get("4H當") == "🔴":
        score += 2

    latest_pct = _safe_float(flags.get("latest_pct_vs_midline"))
    if latest_pct is not None:
        if -2.5 <= latest_pct <= 5.0:
            score += 10
        elif 5.0 < latest_pct <= 8.0:
            score += 2
        elif latest_pct > 8.0:
            score -= 12
        elif latest_pct < -12.0:
            score -= 10

    return max(0, min(100, int(round(score))))


def _records_from_plot_results(plot_results: Iterable[dict]) -> list[dict]:
    keep = [
        "幣種", "現價", "差%", "BB日中軌", "BB中軌", "1D前", "1D當", "4H前", "4H當",
        "距離中軌%", "_price", "_bb1d", "_bb_pct", "_abs_dev",
        "_ha_pct_series", "_ha_curr_pct", "_ha_opens_last20", "_ha_closes_last20", "_ha_times_last20",
    ]
    out = []
    for r in list(plot_results):
        item = {k: r.get(k) for k in keep if k in r}
        item["symbol"] = r.get("幣種")
        item["price"] = _safe_float(r.get("_price"))
        item["bb_basis_1d"] = _safe_float(r.get("_bb1d"))
        item["bb_pct"] = _safe_float(r.get("_bb_pct"))
        item["abs_dev"] = _safe_float(r.get("_abs_dev"))
        item["ha_curr_pct"] = _safe_float(r.get("_ha_curr_pct"))

        ladder_history = _build_ladder_history(r)
        pattern_flags = _build_pattern_flags(r, ladder_history)
        item["ladder_history"] = ladder_history
        item["ladder_tail"] = ladder_history[-8:]
        item["pattern_flags"] = pattern_flags
        item["pattern_type_hint"] = _classify_pattern(pattern_flags)
        item["machine_score_hint_0_100"] = _score_hint(pattern_flags, item)
        item["gpt_notes"] = [
            "ladder_history 是 index.html 圖上黃/紫階梯的文字化版本。",
            "color=yellow/🟡 代表平均K收盤上梯；color=purple/🟣 代表平均K收盤下梯。",
            "判斷中軌突破回踩再啟動，請優先看 pattern_flags.breakout_pullback_yellow_restart 與 4H 前/當。",
            "判斷 PO3/AMD，請看 yellow_over_previous_purple_count、below_midline_po3_amd_candidate。",
        ]
        out.append(_to_plain(item))
    return out


def _screen_candidates(charts: list[dict]) -> dict:
    """機械式分組，非直接買賣建議；主要讓 GPT 不必從表格猜圖形。"""
    def ok_num(x):
        return isinstance(x, (int, float)) and not np.isnan(x)

    rows = []
    for r in charts:
        flags = r.get("pattern_flags") or {}
        row = {
            "symbol": r.get("symbol") or r.get("幣種"),
            "price": r.get("price"),
            "bb_pct": r.get("bb_pct"),
            "abs_dev": r.get("abs_dev"),
            "1D前": r.get("1D前"),
            "1D當": r.get("1D當"),
            "4H前": r.get("4H前"),
            "4H當": r.get("4H當"),
            "latest_color": flags.get("latest_color"),
            "latest_pct_vs_midline": flags.get("latest_pct_vs_midline"),
            "pattern_type_hint": r.get("pattern_type_hint"),
            "machine_score_hint_0_100": r.get("machine_score_hint_0_100"),
            "yellow_over_previous_purple_count": flags.get("yellow_over_previous_purple_count"),
            "four_h_trigger_label": flags.get("four_h_trigger_label"),
        }
        if row["symbol"]:
            rows.append(row)

    def score_key(x):
        return -(x.get("machine_score_hint_0_100") or 0)

    breakout_pullback_restart = sorted(
        [r for r in rows if "中軌突破回踩" in str(r.get("pattern_type_hint"))],
        key=score_key,
    )[:20]
    po3_amd = sorted(
        [r for r in rows if "PO3" in str(r.get("pattern_type_hint"))],
        key=score_key,
    )[:20]
    red_to_green = sorted(
        [r for r in rows if r.get("4H前") == "🔴" and r.get("4H當") == "🟢"],
        key=score_key,
    )[:20]
    near_midline = sorted([r for r in rows if ok_num(r.get("abs_dev"))], key=lambda x: x["abs_dev"])[:20]
    bullish_above_midline = sorted(
        [r for r in rows if ok_num(r.get("bb_pct")) and r["bb_pct"] >= 0 and r.get("1D當") == "🟢" and r.get("4H當") == "🟢"],
        key=lambda x: abs(x.get("bb_pct", 999)),
    )[:20]
    rebound_watch = sorted(
        [r for r in rows if ok_num(r.get("abs_dev")) and r["abs_dev"] <= 3 and r.get("4H當") == "🟢"],
        key=lambda x: x["abs_dev"],
    )[:20]
    high_score_hint = sorted(
        [r for r in rows if (r.get("machine_score_hint_0_100") or 0) >= 60],
        key=score_key,
    )[:30]

    return {
        "breakout_pullback_restart": breakout_pullback_restart,
        "po3_amd_yellow_over_purple_steps": po3_amd,
        "four_h_red_to_green": red_to_green,
        "high_score_hint_over_60": high_score_hint,
        "near_midline": near_midline,
        "bullish_above_midline": bullish_above_midline,
        "rebound_watch": rebound_watch,
    }

def build_snapshot_payload(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    title: str = "HA Crypto Terminal",
    generated_at: Optional[str] = None,
) -> dict:
    plot_results = list(plot_results)
    generated_at = generated_at or datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    data_hash = snapshot_hash(df, plot_results, selection=selection, sort_option=sort_option)
    charts = _records_from_plot_results(plot_results)
    return {
        "title": title,
        "generated_at_taiwan": generated_at,
        "selection": selection,
        "sort_option": sort_option,
        "snapshot_hash": data_hash,
        "count": len(df) if isinstance(df, pd.DataFrame) else 0,
        "note": "index.html is visual; snapshot.json and snapshot_pretty.txt are the machine-readable data sources for ChatGPT analysis.",
        "analysis_schema_version": "crypto-monitor-ladder-v3",
        "analysis_schema": {
            "midline_pct_axis": "0% = 日線 BB 中軌；pct_vs_midline = HA 收盤價相對當天日線中軌的百分比。",
            "ladder_history": "每個幣最近 20 根日線 HA 階梯；yellow/🟡 = 平均K收盤上梯，purple/🟣 = 平均K收盤下梯。",
            "main_patterns": [
                "中軌突破回踩再啟動：先有黃線站上 0 軸，之後紫線回踩 0 軸附近，最新再轉黃線。",
                "PO3/AMD：仍在中軌下方時，最新黃線一次蓋過前面 2~3 層紫線。",
            ],
            "four_h_trigger": "4H前=🔴 且 4H當=🟢 是最佳短線觸發；4H前=🟢 且 4H當=🟢 是偏多延續。",
            "important": "若 charts 裡有 ladder_history 與 pattern_flags，不可判定階梯資訊不足；table 只是簡表，完整圖形資料在 charts。",
        },
        "table": _records_from_df(df),
        "charts": charts,
        "gpt_analysis_records": charts,
        "mechanical_groups": _screen_candidates(charts),
    }


def write_snapshot_json(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot_payload(
        df=df,
        plot_results=list(plot_results),
        selection=selection,
        sort_option=sort_option,
        title=title,
    )
    path = out_dir / DATA_FILE
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(json_text + "\n", encoding="utf-8")
    return path


def write_ai_snapshot_txt(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
) -> Path:
    """
    寫出 text/plain 版的 pretty JSON。
    用途：有些讀取工具會把 application/json 壓成單行或只顯示 metadata，
    但 .txt 通常可以穩定逐行讀取。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot_payload(
        df=df,
        plot_results=list(plot_results),
        selection=selection,
        sort_option=sort_option,
        title=title,
    )
    path = out_dir / AI_JSON_TEXT_FILE
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(json_text + "\n", encoding="utf-8")
    return path


def write_summary_txt(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
) -> Path:
    payload = build_snapshot_payload(df, list(plot_results), selection, sort_option, title)
    lines = []
    lines.append(f"{payload['title']}")
    lines.append(f"更新時間：{payload['generated_at_taiwan']} 台灣時間")
    lines.append(f"選單：{payload['selection']}")
    lines.append(f"排序：{payload['sort_option']}")
    lines.append(f"snapshot_hash：{payload['snapshot_hash']}")
    lines.append("")
    lines.append("=== 機械式候選分組，非直接買賣建議 ===")
    for group_name, rows in payload["mechanical_groups"].items():
        lines.append(f"\n[{group_name}]")
        if not rows:
            lines.append("無")
            continue
        for r in rows[:20]:
            lines.append(
                f"{r.get('symbol')} | price={r.get('price')} | bb_pct={r.get('bb_pct')} | "
                f"abs_dev={r.get('abs_dev')} | 1D當={r.get('1D當')} | 4H前={r.get('4H前')} | 4H當={r.get('4H當')}"
            )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SUMMARY_FILE
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_static_outputs(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
    max_charts: Optional[int] = None,
) -> dict:
    plot_results = list(plot_results)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_hash = snapshot_hash(df, plot_results, selection=selection, sort_option=sort_option)
    html_text = build_index_html(
        df=df,
        plot_results=plot_results,
        selection=selection,
        sort_option=sort_option,
        title=title,
        max_charts=max_charts,
        data_hash=data_hash,
    )
    data_links = (
        '<span class="badge"><a style="color:inherit;text-decoration:none" href="snapshot.json">AI資料：snapshot.json</a></span>'
        '<span class="badge"><a style="color:inherit;text-decoration:none" href="snapshot_pretty.txt">AI快讀：snapshot_pretty.txt</a></span>'
        '<span class="badge"><a style="color:inherit;text-decoration:none" href="latest_signals.txt">文字版：latest_signals.txt</a></span>'
    )
    target = '<span class="badge">snapshot：' + _escape(data_hash[:10]) + '</span>'
    html_text = html_text.replace(target, target + data_links)
    index_path = out_dir / OUTPUT_FILE
    index_path.write_text(html_text, encoding="utf-8")
    snapshot_path = write_snapshot_json(df, plot_results, selection, sort_option, output_dir, title)
    ai_snapshot_path = write_ai_snapshot_txt(df, plot_results, selection, sort_option, output_dir, title)
    summary_path = write_summary_txt(df, plot_results, selection, sort_option, output_dir, title)
    return {"index": index_path, "snapshot": snapshot_path, "ai_snapshot": ai_snapshot_path, "summary": summary_path, "snapshot_hash": data_hash}


# 覆蓋舊版 write_index_html：仍回傳 index.html 路徑，但會順手輸出 snapshot.json / latest_signals.txt。
def write_index_html(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str = "—",
    sort_option: str = "—",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
    max_charts: Optional[int] = None,
) -> Path:
    paths = write_static_outputs(
        df=df,
        plot_results=list(plot_results),
        selection=selection,
        sort_option=sort_option,
        output_dir=output_dir,
        title=title,
        max_charts=max_charts,
    )
    return paths["index"]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def push_text_file_to_github(
    local_file: str | Path,
    repo: str,
    token: str,
    branch: str = "main",
    repo_path: str = "docs/snapshot.json",
    commit_message: Optional[str] = None,
) -> dict:
    if not token:
        raise ValueError("缺少 GitHub token。請在 Streamlit Secrets 設定 GITHUB_TOKEN。")
    local_path = Path(local_file)
    local_text = local_path.read_text(encoding="utf-8")
    local_hash = _sha256_text(local_text)
    remote = _get_remote_file(repo=repo, path=repo_path, branch=branch, token=token)
    remote_text = remote.get("content_text") or ""
    remote_hash = _sha256_text(remote_text) if remote.get("exists") else None
    if remote.get("exists") and remote_hash == local_hash:
        return {"status": "skipped", "reason": "remote file content is identical", "repo_path": repo_path, "hash": local_hash}

    encoded = base64.b64encode(local_path.read_bytes()).decode("ascii")
    now_tw = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "message": commit_message or f"update {repo_path} {now_tw} TW",
        "content": encoded,
        "branch": branch,
    }
    if remote.get("sha"):
        payload["sha"] = remote["sha"]
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{repo_path}"
    resp = requests.put(url, headers=_github_headers(token), json=payload, timeout=45)
    if resp.status_code >= 400:
        raise RuntimeError(f"GitHub 寫入 {repo_path} 失敗：HTTP {resp.status_code} {resp.text[:500]}")
    data = resp.json()
    return {
        "status": "updated" if remote.get("exists") else "created",
        "repo_path": repo_path,
        "hash": local_hash,
        "commit_sha": (data.get("commit") or {}).get("sha"),
    }


# 覆蓋舊版 sync_index_to_github：除了 index.html，也同步 snapshot.json 與 latest_signals.txt。
def sync_index_to_github(
    df: pd.DataFrame,
    plot_results: Iterable[dict],
    selection: str,
    sort_option: str,
    repo: str,
    token: str,
    branch: str = "main",
    repo_path: str = "docs/index.html",
    output_dir: str | Path = OUTPUT_DIR,
    title: str = "HA Crypto Terminal",
    max_charts: Optional[int] = None,
) -> dict:
    plot_results = list(plot_results)
    paths = write_static_outputs(
        df=df,
        plot_results=plot_results,
        selection=selection,
        sort_option=sort_option,
        output_dir=output_dir,
        title=title,
        max_charts=max_charts,
    )
    data_hash = paths["snapshot_hash"]
    index_result = push_file_to_github(
        local_file=paths["index"],
        repo=repo,
        token=token,
        branch=branch,
        repo_path=repo_path,
        commit_message=f"update crypto index {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} TW {data_hash[:8]}",
        skip_if_same_snapshot=True,
    )
    snapshot_repo_path = str(Path(repo_path).with_name(DATA_FILE)).replace("\\", "/")
    ai_snapshot_repo_path = str(Path(repo_path).with_name(AI_JSON_TEXT_FILE)).replace("\\", "/")
    summary_repo_path = str(Path(repo_path).with_name(SUMMARY_FILE)).replace("\\", "/")
    snapshot_result = push_text_file_to_github(
        local_file=paths["snapshot"],
        repo=repo,
        token=token,
        branch=branch,
        repo_path=snapshot_repo_path,
        commit_message=f"update crypto snapshot {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} TW {data_hash[:8]}",
    )
    ai_snapshot_result = push_text_file_to_github(
        local_file=paths["ai_snapshot"],
        repo=repo,
        token=token,
        branch=branch,
        repo_path=ai_snapshot_repo_path,
        commit_message=f"update crypto readable snapshot {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} TW {data_hash[:8]}",
    )
    summary_result = push_text_file_to_github(
        local_file=paths["summary"],
        repo=repo,
        token=token,
        branch=branch,
        repo_path=summary_repo_path,
        commit_message=f"update crypto latest signals {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} TW {data_hash[:8]}",
    )
    all_results = [index_result, snapshot_result, ai_snapshot_result, summary_result]
    return {
        "status": "updated" if any(r.get("status") != "skipped" for r in all_results) else "skipped",
        "snapshot_hash": data_hash,
        "local_path": str(paths["index"]),
        "files": {
            "index": index_result,
            "snapshot": snapshot_result,
            "ai_snapshot": ai_snapshot_result,
            "summary": summary_result,
        },
        "repo_path": repo_path,
        "branch": branch,
        "commit_sha": index_result.get("commit_sha") or snapshot_result.get("commit_sha") or ai_snapshot_result.get("commit_sha") or summary_result.get("commit_sha"),
    }


# ==================== 評分系統 v3.1 微調覆蓋 ====================
# 目的：
# 1) 中軌下方即使最近 20 天未突破中軌，只要紫黃交替、低點墊高、接近中軌，應高於「紫紫紫持續下梯」。
# 2) 中軌上方若已突破過、回踩轉紫但未跌破中軌，且 4H 紅→綠，應視為「強勢整理等待再轉黃」，分數上修但仍低於最新黃線確認。


def _recent_color_stats(history: list[dict], lookback: int = 8) -> dict:
    tail = history[-lookback:] if history else []
    colors = [h.get("color") for h in tail if h.get("color") in ["yellow", "purple"]]
    pcts = [_safe_float(h.get("pct_vs_midline")) for h in tail]
    pcts = [p for p in pcts if p is not None]
    switches = sum(1 for a, b in zip(colors, colors[1:]) if a != b)
    yellow_count = sum(1 for c in colors if c == "yellow")
    purple_count = sum(1 for c in colors if c == "purple")
    latest_pct = _safe_float(history[-1].get("pct_vs_midline")) if history else None
    recent_low = min(pcts) if pcts else None
    recent_high = max(pcts) if pcts else None
    repair_from_low = None
    if latest_pct is not None and recent_low is not None:
        repair_from_low = latest_pct - recent_low
    return {
        "lookback": lookback,
        "color_switch_count": switches,
        "yellow_count": yellow_count,
        "purple_count": purple_count,
        "recent_low_pct": recent_low,
        "recent_high_pct": recent_high,
        "repair_from_recent_low_pct": repair_from_low,
    }


def _build_pattern_flags(r: dict, history: list[dict]) -> dict:
    """v3.1：加入「中軌下方紫黃修復」與「中軌上方紫線強勢整理」辨識。"""
    latest = history[-1] if history else {}
    run = _current_color_run(history)
    run_start = run.get("start_index")
    latest_pct = latest.get("pct_vs_midline")
    latest_color = latest.get("color", "unknown")

    previous_items = history[:run_start] if isinstance(run_start, int) else history[:-1]
    previous_purples_reversed = [h for h in reversed(previous_items) if h.get("color") == "purple"]
    previous_purple_pcts = [h.get("pct_vs_midline") for h in previous_purples_reversed if h.get("pct_vs_midline") is not None]
    yellow_ref = history[run_start] if isinstance(run_start, int) and 0 <= run_start < len(history) else latest
    yellow_ref_pct = yellow_ref.get("pct_vs_midline")

    def _count_yellow_over_prev_purples(ref_pct: Any, n: int = 3) -> int:
        ref = _safe_float(ref_pct)
        if ref is None:
            return 0
        return sum(1 for p in previous_purple_pcts[:n] if p is not None and ref > p)

    yellow_over_count_from_run_start = _count_yellow_over_prev_purples(yellow_ref_pct, 3)
    yellow_over_count_latest = _count_yellow_over_prev_purples(latest_pct, 3)
    yellow_over_count = max(yellow_over_count_from_run_start, yellow_over_count_latest)

    breakout_indices = [
        i for i, h in enumerate(history)
        if h.get("color") == "yellow" and h.get("pct_vs_midline") is not None and h["pct_vs_midline"] >= 0
    ]
    breakout_before_current_run = [i for i in breakout_indices if not isinstance(run_start, int) or i < run_start]
    last_breakout_idx = breakout_before_current_run[-1] if breakout_before_current_run else None

    pullback_items = []
    if isinstance(last_breakout_idx, int) and isinstance(run_start, int):
        pullback_items = history[last_breakout_idx + 1:run_start]

    purple_pullback_near_midline = any(
        h.get("color") == "purple"
        and h.get("pct_vs_midline") is not None
        and -4.0 <= h["pct_vs_midline"] <= 3.0
        for h in pullback_items
    )
    purple_pullback_not_deep_broken = True
    if pullback_items:
        pcts = [h["pct_vs_midline"] for h in pullback_items if h.get("pct_vs_midline") is not None]
        purple_pullback_not_deep_broken = bool(pcts and min(pcts) >= -6.0)

    four_h_red_to_green = (r.get("4H前") == "🔴" and r.get("4H當") == "🟢")
    four_h_green_green = (r.get("4H前") == "🟢" and r.get("4H當") == "🟢")
    four_h_green_to_red = (r.get("4H前") == "🟢" and r.get("4H當") == "🔴")

    breakout_pullback_restart = bool(
        latest_color == "yellow"
        and bool(breakout_before_current_run)
        and purple_pullback_near_midline
        and purple_pullback_not_deep_broken
    )

    po3_amd_yellow_over_2 = bool(latest_color == "yellow" and yellow_over_count >= 2)
    po3_amd_yellow_over_3 = bool(latest_color == "yellow" and yellow_over_count >= 3)
    below_midline_po3_amd = bool(
        latest_color == "yellow"
        and latest_pct is not None
        and latest_pct < 0
        and yellow_over_count >= 2
    )

    stats = _recent_color_stats(history, lookback=8)
    had_any_midline_breakout = any(
        h.get("pct_vs_midline") is not None and h["pct_vs_midline"] >= 0
        for h in history
    )
    current_run_pcts = []
    if isinstance(run_start, int):
        current_run_pcts = [h.get("pct_vs_midline") for h in history[run_start:] if h.get("pct_vs_midline") is not None]

    # 中軌下方：未突破過中軌，但紫黃交替、低點墊高、正在靠近中軌。
    below_midline_yellow_purple_repair = bool(
        latest_pct is not None
        and latest_pct < 0
        and latest_pct >= -5.5
        and not had_any_midline_breakout
        and stats.get("color_switch_count", 0) >= 2
        and stats.get("yellow_count", 0) >= 2
        and (stats.get("repair_from_recent_low_pct") is not None and stats["repair_from_recent_low_pct"] >= 2.0)
    )
    below_midline_repair_near_breakout = bool(
        below_midline_yellow_purple_repair
        and latest_pct is not None
        and latest_pct >= -3.0
    )

    # 中軌上方：突破後回踩轉紫，但紫線仍守在 0 軸上方或接近 0 軸，屬強勢整理。
    above_midline_purple_pullback_hold = bool(
        latest_color == "purple"
        and bool(breakout_before_current_run or had_any_midline_breakout)
        and latest_pct is not None
        and -1.0 <= latest_pct <= 5.5
        and (not current_run_pcts or min(current_run_pcts) >= -1.5)
    )
    above_midline_purple_pullback_with_4h_trigger = bool(
        above_midline_purple_pullback_hold and four_h_red_to_green
    )

    purple_continuation_weak = bool(
        latest_color == "purple"
        and run.get("length", 0) >= 3
        and stats.get("repair_from_recent_low_pct") is not None
        and stats["repair_from_recent_low_pct"] < 1.0
    )

    return {
        "analysis_ready": bool(len(history) >= 10 and latest_color in ["yellow", "purple", "flat"]),
        "latest_color": latest_color,
        "latest_color_emoji": _ha_step_emoji(latest_color),
        "latest_pct_vs_midline": latest_pct,
        "latest_above_midline": bool(latest_pct is not None and latest_pct >= 0),
        "latest_near_midline": bool(latest_pct is not None and abs(latest_pct) <= 3.0),
        "current_color_run": run,
        "recent_color_stats": stats,
        "had_any_midline_breakout_in_lookback": bool(had_any_midline_breakout),
        "had_yellow_above_midline_before_current_run": bool(breakout_before_current_run),
        "purple_pullback_near_midline_after_breakout": bool(purple_pullback_near_midline),
        "purple_pullback_not_deep_broken": bool(purple_pullback_not_deep_broken),
        "breakout_pullback_yellow_restart": breakout_pullback_restart,
        "below_midline_yellow_purple_repair": below_midline_yellow_purple_repair,
        "below_midline_repair_near_breakout": below_midline_repair_near_breakout,
        "above_midline_purple_pullback_hold": above_midline_purple_pullback_hold,
        "above_midline_purple_pullback_with_4h_trigger": above_midline_purple_pullback_with_4h_trigger,
        "purple_continuation_weak": purple_continuation_weak,
        "previous_purple_pcts_for_po3": previous_purple_pcts[:3],
        "yellow_ref_pct_for_po3": yellow_ref_pct,
        "yellow_over_previous_purple_count": int(yellow_over_count),
        "yellow_over_2_previous_purple_steps": po3_amd_yellow_over_2,
        "yellow_over_3_previous_purple_steps": po3_amd_yellow_over_3,
        "below_midline_po3_amd_candidate": below_midline_po3_amd,
        "four_h_red_to_green": four_h_red_to_green,
        "four_h_green_green": four_h_green_green,
        "four_h_green_to_red": four_h_green_to_red,
        "four_h_trigger_label": "4H前紅→4H當綠：最佳啟動" if four_h_red_to_green else ("4H綠→綠：偏多延續" if four_h_green_green else ("4H綠→紅：短線轉弱" if four_h_green_to_red else "4H未啟動或偏弱")),
    }


def _classify_pattern(flags: dict) -> str:
    if flags.get("breakout_pullback_yellow_restart") and flags.get("four_h_red_to_green"):
        return "中軌突破回踩再啟動型"
    if flags.get("breakout_pullback_yellow_restart"):
        return "中軌突破回踩轉黃型"
    if flags.get("above_midline_purple_pullback_with_4h_trigger"):
        return "中軌上方紫線強勢整理型（等待轉黃）"
    if flags.get("above_midline_purple_pullback_hold"):
        return "中軌上方紫線整理型"
    if flags.get("below_midline_po3_amd_candidate") and flags.get("yellow_over_3_previous_purple_steps"):
        return "中軌下方 PO3/AMD 強反轉型"
    if flags.get("below_midline_po3_amd_candidate"):
        return "中軌下方 PO3/AMD 反轉候選型"
    if flags.get("below_midline_repair_near_breakout"):
        return "中軌下方紫黃修復近中軌型"
    if flags.get("below_midline_yellow_purple_repair"):
        return "中軌下方紫黃修復觀察型"
    if flags.get("latest_color") == "yellow" and flags.get("latest_near_midline"):
        return "中軌附近磨合轉黃型"
    if flags.get("latest_color") == "purple":
        return "紫線未轉黃觀察型"
    return "一般觀察型"


def _score_hint(flags: dict, item: dict) -> int:
    """
    v3.1 機械分數提示：
    - 最新黃線仍是正式確認。
    - 但中軌下方紫黃修復、以及中軌上方紫線守 0 軸 + 4H 紅轉綠，會給更合理的預備分。
    - 紫線型可上修，但除非重新轉黃，原則上不給 90+。
    """
    score = 0
    latest_color = flags.get("latest_color")
    four_h_red_to_green = flags.get("four_h_red_to_green")
    four_h_green_green = flags.get("four_h_green_green")
    four_h_green_to_red = flags.get("four_h_green_to_red") or (item.get("4H前") == "🟢" and item.get("4H當") == "🔴")

    # 1) 日線結構基礎分
    if flags.get("breakout_pullback_yellow_restart"):
        score += 45
    elif flags.get("above_midline_purple_pullback_hold"):
        score += 42
    elif flags.get("below_midline_repair_near_breakout") and latest_color == "yellow":
        score += 34
    elif flags.get("below_midline_yellow_purple_repair") and latest_color == "yellow":
        score += 29
    elif flags.get("below_midline_yellow_purple_repair"):
        score += 22
    elif flags.get("had_yellow_above_midline_before_current_run") and latest_color == "yellow":
        score += 30
    elif latest_color == "yellow":
        score += 22
    elif latest_color == "purple":
        score += 6

    # 2) PO3 / AMD 黃線蓋過紫線
    over_count = int(flags.get("yellow_over_previous_purple_count") or 0)
    if flags.get("below_midline_po3_amd_candidate"):
        score += 28 + min(over_count, 3) * 4
    elif over_count >= 2 and latest_color == "yellow":
        score += 18 + min(over_count, 3) * 3

    # 3) 4H 觸發
    if four_h_red_to_green:
        score += 20
    elif four_h_green_green:
        score += 14
    elif four_h_green_to_red:
        score -= 8
    elif item.get("4H當") == "🔴":
        score += 2

    # 4) 位置修正
    latest_pct = _safe_float(flags.get("latest_pct_vs_midline"))
    if latest_pct is not None:
        if -2.5 <= latest_pct <= 5.0:
            score += 10
        elif -5.5 <= latest_pct < -2.5:
            score += 5
        elif 5.0 < latest_pct <= 8.0:
            score += 2
        elif latest_pct > 8.0:
            score -= 12
        elif latest_pct < -12.0:
            score -= 10

    # 5) 型態封頂：避免「尚未轉黃」或「未站上中軌」被誤拉到核心候選。
    if latest_color == "purple":
        if flags.get("above_midline_purple_pullback_with_4h_trigger"):
            score = min(score, 82)
        elif flags.get("above_midline_purple_pullback_hold"):
            score = min(score, 74)
        else:
            score = min(score, 59)

    if flags.get("below_midline_yellow_purple_repair") and not flags.get("had_any_midline_breakout_in_lookback"):
        if latest_color == "yellow" and four_h_red_to_green and flags.get("below_midline_repair_near_breakout"):
            score = min(score, 84)
        elif latest_color == "yellow" and flags.get("below_midline_repair_near_breakout"):
            score = min(score, 78)
        elif latest_color == "yellow":
            score = min(score, 74)
        else:
            score = min(score, 66)

    if flags.get("purple_continuation_weak"):
        score = min(score, 55)

    return max(0, min(100, int(round(score))))
