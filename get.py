"""
get.py

Streamlit-only snapshot builder.

保留用途：
- 把 main.py 當下 runtime 的表格與圖表資料組成 snapshot_pretty.txt 內容。
- 輸出 ladder_history / pattern_flags / gpt_analysis_records，讓 GPT 能讀懂黃線、紫線階梯。
- 型態判斷與分數規則已拆到 scoring_rules.py。

已移除：
- 不產生任何靜態檔
- 不寫入任何檔案
- 不呼叫任何遠端同步 API
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Iterable, Optional, Any

import numpy as np
import pandas as pd

from scoring_rules import build_pattern_flags, classify_pattern, score_hint

TW_TZ = timezone(timedelta(hours=8))


def _normalise_for_hash(value: Any) -> Any:
    """把 dataframe / numpy / pandas 物件轉為穩定 JSON，可用來判斷圖表資料是否真的改變。"""
    if isinstance(value, pd.DataFrame):
        return value.replace({np.nan: None}).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.to_dict()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, 10)
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
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
        pattern_flags = build_pattern_flags(r, ladder_history)
        item["ladder_history"] = ladder_history
        item["ladder_tail"] = ladder_history[-8:]
        item["pattern_flags"] = pattern_flags
        item["pattern_type_hint"] = classify_pattern(pattern_flags)
        item["machine_score_hint_0_100"] = score_hint(pattern_flags, item)
        item["gpt_notes"] = [
            "ladder_history 是 index.html 圖上黃/紫階梯的文字化版本。",
            "color=yellow/🟡 代表平均K收盤上梯；color=purple/🟣 代表平均K收盤下梯。",
            "判斷中軌突破回踩轉黃型，請優先看 pattern_flags.breakout_pullback_yellow_restart；4H 前/當只作為分數權重。",
            "判斷 PO3/AMD 不只看 yellow_over_previous_purple_count；強反轉需同時看 po3_amd_quality_label、clean_fast_reclaim_run、recent_color_transitions_6d、rapid_reclaim_magnitude。",
            "XLM 類屬 strong_fast_reclaim 但分數封頂 88；SUI/ONDO/BOME 類歸入 w_bottom_candidate/反轉候選；FIL 類單根小黃線屬 early_weak_rebound_wait_confirm。",
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
        "analysis_schema_version": "crypto-monitor-ladder-v5",
        "analysis_schema": {
            "midline_pct_axis": "0% = 日線 BB 中軌；pct_vs_midline = HA 收盤價相對當天日線中軌的百分比。",
            "ladder_history": "每個幣最近 20 根日線 HA 階梯；yellow/🟡 = 平均K收盤上梯，purple/🟣 = 平均K收盤下梯。",
            "main_patterns": [
                "中軌突破回踩轉黃型：先有黃線站上 0 軸，之後紫線回踩 0 軸附近，最新再轉黃線；4H 前紅→4H 當綠只作為最高分觸發權重。",
                "PO3/AMD 強反轉：仍在中軌下方時，最新黃線快速、大幅蓋過前面 2~3 層紫線，例如深紫區快速拉回近中軌。",
                "PO3/AMD 反轉候選：中軌下方黃紫交錯、W底盤整、緩慢墊高，例如底部盤來盤去後朝前紫線第 2~3 層推進。",
                "PO3/AMD 轉黃早期觀察：長紫線後只有 1 根小黃線，雖然略高於前紫線，但幅度太小，需等待下一日確認。",
            ],
            "four_h_trigger": "4H前=🔴 且 4H當=🟢 是最佳短線觸發；4H前=🟢 且 4H當=🟢 是偏多延續。",
            "important": "若 charts 裡有 ladder_history 與 pattern_flags，不可判定階梯資訊不足；table 只是簡表，完整圖形資料在 charts。",
        },
        "table": _records_from_df(df),
        "charts": charts,
        "gpt_analysis_records": charts,
        "mechanical_groups": _screen_candidates(charts),
    }


