"""型態判斷與機械分數規則。

這個檔案是最常修改的地方：
- PO3/AMD 強反轉 / 反轉候選 / 早期觀察
- 中軌突破回踩轉黃
- 4H 前/當權重
- 中軌上下與高乖離封頂
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

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




def _ha_step_emoji(color: str) -> str:
    return {"yellow": "🟡", "purple": "🟣", "flat": "⚫"}.get(color, "—")




def _current_color_run(history: list[dict]) -> dict:
    if not history:
        return {"color": "unknown", "start_index": None, "length": 0}
    color = history[-1].get("color", "unknown")
    start = len(history) - 1
    while start > 0 and history[start - 1].get("color") == color:
        start -= 1
    return {"color": color, "start_index": start, "length": len(history) - start}




def _color_transitions(items: list[dict]) -> int:
    """計算最近階梯的顏色切換次數；用來區分 W 底盤整 vs 單日小反彈。"""
    colors = [h.get("color") for h in items if h.get("color") in ["yellow", "purple"]]
    if len(colors) < 2:
        return 0
    return sum(1 for a, b in zip(colors, colors[1:]) if a != b)




def _avg(values: list[float]) -> Optional[float]:
    nums = [_safe_float(v) for v in values]
    nums = [v for v in nums if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)




def build_pattern_flags(r: dict, history: list[dict]) -> dict:
    """
    把使用者討論的核心型態做成明確布林欄位，避免 GPT 只因「靠近中軌」或
    「最新黃線略高於前紫線」就把弱反彈誤判成強反轉。

    這版新增三個人眼判斷：
    1. 強反轉：最新黃線必須快速、大幅蓋過前 2~3 層紫線。
    2. W 底候選：中軌下方黃紫交錯、緩慢墊高，歸類為反轉候選而非強反轉。
    3. 早期弱反彈：長紫線後只出現 1 根小黃線，雖然略高於前紫線，也要降權等待確認。
    """
    latest = history[-1] if history else {}
    run = _current_color_run(history)
    run_start = run.get("start_index")
    run_length = int(run.get("length") or 0)
    latest_pct = latest.get("pct_vs_midline")
    latest_color = latest.get("color", "unknown")

    previous_items = history[:run_start] if isinstance(run_start, int) else history[:-1]
    previous_purples_reversed = [h for h in reversed(previous_items) if h.get("color") == "purple"]
    previous_purple_pcts = [h.get("pct_vs_midline") for h in previous_purples_reversed if h.get("pct_vs_midline") is not None]
    yellow_ref = history[run_start] if isinstance(run_start, int) and 0 <= run_start < len(history) else latest
    yellow_ref_pct = yellow_ref.get("pct_vs_midline")

    prev_before_run = history[run_start - 1] if isinstance(run_start, int) and run_start > 0 else None
    prev_before_run_pct = prev_before_run.get("pct_vs_midline") if prev_before_run else None
    recent_tail = history[-8:]
    recent_color_transitions = _color_transitions(recent_tail)
    recent_yellow_count = sum(1 for h in recent_tail if h.get("color") == "yellow")
    recent_purple_count = sum(1 for h in recent_tail if h.get("color") == "purple")

    def _count_yellow_over_prev_purples(ref_pct: Any, n: int = 3) -> int:
        ref = _safe_float(ref_pct)
        if ref is None:
            return 0
        return sum(1 for p in previous_purple_pcts[:n] if p is not None and ref > p)

    yellow_over_count_from_run_start = _count_yellow_over_prev_purples(yellow_ref_pct, 3)
    yellow_over_count_latest = _count_yellow_over_prev_purples(latest_pct, 3)
    yellow_over_count = max(yellow_over_count_from_run_start, yellow_over_count_latest)

    prev3 = [_safe_float(p) for p in previous_purple_pcts[:3]]
    prev3 = [p for p in prev3 if p is not None]
    latest_num = _safe_float(latest_pct)
    yellow_ref_num = _safe_float(yellow_ref_pct)
    prev_before_num = _safe_float(prev_before_run_pct)

    latest_reclaim_margins = []
    if latest_num is not None:
        latest_reclaim_margins = [latest_num - p for p in prev3]
    avg_reclaim_margin_vs_prev3 = _avg(latest_reclaim_margins)
    max_reclaim_margin_vs_prev3 = max(latest_reclaim_margins) if latest_reclaim_margins else None
    min_reclaim_margin_vs_prev3 = min(latest_reclaim_margins) if latest_reclaim_margins else None
    rebound_from_recent_purple_low_pct = None
    if latest_num is not None and prev3:
        rebound_from_recent_purple_low_pct = latest_num - min(prev3)
    lift_from_previous_step_pct = None
    if latest_num is not None and prev_before_num is not None:
        lift_from_previous_step_pct = latest_num - prev_before_num
    current_yellow_run_lift_pct = None
    if latest_num is not None and yellow_ref_num is not None:
        current_yellow_run_lift_pct = latest_num - yellow_ref_num

    breakout_indices = [
        i for i, h in enumerate(history)
        if h.get("color") == "yellow" and h.get("pct_vs_midline") is not None and h["pct_vs_midline"] >= 0
    ]
    breakout_before_current_run = [i for i in breakout_indices if not isinstance(run_start, int) or i < run_start]
    last_breakout_idx = breakout_before_current_run[-1] if breakout_before_current_run else None

    # 「曾經站上中軌」是結構強弱分水嶺：
    # BOME 類：前面曾黃線站上/穿越中軌，後面摔回中軌下方，再重新蓋過紫線，偏杯柄反攻候選。
    # ARB 類：最近 20 根從頭到尾沒摸過中軌，代表一直被中軌壓制，反轉分數需要降權。
    any_above_indices = [
        i for i, h in enumerate(history)
        if h.get("pct_vs_midline") is not None and h["pct_vs_midline"] >= 0
    ]
    above_before_current_run = [i for i in any_above_indices if not isinstance(run_start, int) or i < run_start]
    had_any_above_midline_before_current_run = bool(above_before_current_run)
    last_above_idx = above_before_current_run[-1] if above_before_current_run else None
    bars_since_last_above_midline = (len(history) - 1 - last_above_idx) if isinstance(last_above_idx, int) else None
    recent_above_midline_before_current_run = bool(
        bars_since_last_above_midline is not None and bars_since_last_above_midline <= 12
    )

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
        and latest_num is not None
        and latest_num < 0
        and yellow_over_count >= 2
    )

    prior_breakout_then_pullback_reclaim = bool(
        below_midline_po3_amd
        and bool(breakout_before_current_run)
        and recent_above_midline_before_current_run
        and latest_num is not None
        and latest_num >= -6.5
        and yellow_over_count >= 2
        # 排除 FIL 類單根小黃：曾經上過中軌不代表現在就穩，還要有連續黃線或足夠 reclaim 幅度。
        and run_length >= 2
        and (avg_reclaim_margin_vs_prev3 is not None and avg_reclaim_margin_vs_prev3 >= 1.5)
        and (rebound_from_recent_purple_low_pct is not None and rebound_from_recent_purple_low_pct >= 2.0)
    )
    structurally_suppressed_never_touched_midline = bool(
        below_midline_po3_amd
        and not had_any_above_midline_before_current_run
    )

    # 人眼版「強反轉 v3」：不是只算有沒有蓋過 3 層，而是看「速度 + 乾淨度 + 幅度」。
    # XLM 類：最新黃線在 1~2 根內乾淨拉升，中途沒有黃紫黃反覆，直接蓋過前 3 層紫線。
    # SUI 類：雖然最後也蓋到第 3 層，但途中有黃紫黃/紫黃紫混合，屬於盤整式反轉候選。
    recent_tail_6 = history[-6:]
    recent_color_transitions_6d = _color_transitions(recent_tail_6)
    recent_tail_5 = history[-5:]
    recent_color_transitions_5d = _color_transitions(recent_tail_5)

    clean_fast_reclaim_run = bool(
        latest_color == "yellow"
        and 1 <= run_length <= 2
        and recent_color_transitions_6d <= 1
    )

    interrupted_reclaim_by_color_mix = bool(
        latest_color == "yellow"
        and yellow_over_count >= 3
        and recent_color_transitions_6d >= 2
    )

    rapid_reclaim_magnitude = bool(
        (lift_from_previous_step_pct is not None and lift_from_previous_step_pct >= 4.0)
        or (rebound_from_recent_purple_low_pct is not None and rebound_from_recent_purple_low_pct >= 6.0)
        or (avg_reclaim_margin_vs_prev3 is not None and avg_reclaim_margin_vs_prev3 >= 4.5)
    )

    po3_amd_strong_reversal = bool(
        below_midline_po3_amd
        and yellow_over_count >= 3
        and clean_fast_reclaim_run
        and rapid_reclaim_magnitude
        and (latest_num is not None and latest_num >= -4.0)
    )

    # ONDO / SUI 類：黃紫交錯、底部盤整、緩慢墊高。可以進候選，但不應該貼「強反轉」。
    po3_amd_w_bottom_candidate = bool(
        below_midline_po3_amd
        and not po3_amd_strong_reversal
        and (
            interrupted_reclaim_by_color_mix
            or recent_color_transitions >= 3
            or recent_color_transitions_6d >= 2
            or (avg_reclaim_margin_vs_prev3 is not None and avg_reclaim_margin_vs_prev3 >= 1.5)
            or four_h_red_to_green
        )
    )

    # FIL 類：長紫線後只出 1 根小黃，雖然機械上超過前紫線，但幅度太小，先降為早期觀察。
    po3_amd_early_weak_rebound = bool(
        below_midline_po3_amd
        and not po3_amd_strong_reversal
        and not po3_amd_w_bottom_candidate
        and run_length <= 1
        and recent_color_transitions <= 1
        and (avg_reclaim_margin_vs_prev3 is None or avg_reclaim_margin_vs_prev3 < 1.5)
        and (rebound_from_recent_purple_low_pct is None or rebound_from_recent_purple_low_pct < 2.0)
    )

    po3_amd_quality_label = "none"
    if po3_amd_strong_reversal:
        po3_amd_quality_label = "strong_fast_reclaim"
    elif po3_amd_w_bottom_candidate:
        po3_amd_quality_label = "w_bottom_candidate"
    elif po3_amd_early_weak_rebound:
        po3_amd_quality_label = "early_weak_rebound_wait_confirm"
    elif below_midline_po3_amd:
        po3_amd_quality_label = "normal_candidate"

    return {
        "analysis_ready": bool(len(history) >= 10 and latest_color in ["yellow", "purple", "flat"]),
        "latest_color": latest_color,
        "latest_color_emoji": _ha_step_emoji(latest_color),
        "latest_pct_vs_midline": latest_pct,
        "latest_above_midline": bool(latest_num is not None and latest_num >= 0),
        "latest_near_midline": bool(latest_num is not None and abs(latest_num) <= 3.0),
        "current_color_run": run,
        "had_yellow_above_midline_before_current_run": bool(breakout_before_current_run),
        "had_any_above_midline_before_current_run": bool(had_any_above_midline_before_current_run),
        "recent_above_midline_before_current_run": bool(recent_above_midline_before_current_run),
        "bars_since_last_above_midline": int(bars_since_last_above_midline) if bars_since_last_above_midline is not None else None,
        "prior_breakout_then_pullback_reclaim": bool(prior_breakout_then_pullback_reclaim),
        "structurally_suppressed_never_touched_midline": bool(structurally_suppressed_never_touched_midline),
        "purple_pullback_near_midline_after_breakout": bool(purple_pullback_near_midline),
        "purple_pullback_not_deep_broken": bool(purple_pullback_not_deep_broken),
        "breakout_pullback_yellow_restart": breakout_pullback_restart,
        "previous_purple_pcts_for_po3": previous_purple_pcts[:3],
        "yellow_ref_pct_for_po3": yellow_ref_pct,
        "yellow_over_previous_purple_count": int(yellow_over_count),
        "yellow_over_2_previous_purple_steps": po3_amd_yellow_over_2,
        "yellow_over_3_previous_purple_steps": po3_amd_yellow_over_3,
        "below_midline_po3_amd_candidate": below_midline_po3_amd,
        "po3_amd_quality_label": po3_amd_quality_label,
        "po3_amd_strong_reversal": po3_amd_strong_reversal,
        "po3_amd_w_bottom_candidate": po3_amd_w_bottom_candidate,
        "po3_amd_early_weak_rebound": po3_amd_early_weak_rebound,
        "recent_color_transitions_8d": int(recent_color_transitions),
        "recent_color_transitions_6d": int(recent_color_transitions_6d),
        "recent_color_transitions_5d": int(recent_color_transitions_5d),
        "clean_fast_reclaim_run": bool(clean_fast_reclaim_run),
        "interrupted_reclaim_by_color_mix": bool(interrupted_reclaim_by_color_mix),
        "rapid_reclaim_magnitude": bool(rapid_reclaim_magnitude),
        "strong_reclaim_run_length_days": int(run_length),
        "recent_yellow_count_8d": int(recent_yellow_count),
        "recent_purple_count_8d": int(recent_purple_count),
        "lift_from_previous_step_pct": round(lift_from_previous_step_pct, 6) if lift_from_previous_step_pct is not None else None,
        "current_yellow_run_lift_pct": round(current_yellow_run_lift_pct, 6) if current_yellow_run_lift_pct is not None else None,
        "avg_reclaim_margin_vs_prev3_purple_pct": round(avg_reclaim_margin_vs_prev3, 6) if avg_reclaim_margin_vs_prev3 is not None else None,
        "max_reclaim_margin_vs_prev3_purple_pct": round(max_reclaim_margin_vs_prev3, 6) if max_reclaim_margin_vs_prev3 is not None else None,
        "min_reclaim_margin_vs_prev3_purple_pct": round(min_reclaim_margin_vs_prev3, 6) if min_reclaim_margin_vs_prev3 is not None else None,
        "rebound_from_recent_purple_low_pct": round(rebound_from_recent_purple_low_pct, 6) if rebound_from_recent_purple_low_pct is not None else None,
        "four_h_red_to_green": four_h_red_to_green,
        "four_h_green_green": four_h_green_green,
        "four_h_trigger_label": "4H前紅→4H當綠：最佳啟動" if four_h_red_to_green else ("4H綠→綠：偏多延續" if four_h_green_green else ("4H綠→紅：短線轉弱" if (r.get("4H前") == "🟢" and r.get("4H當") == "🔴") else "4H未啟動或偏弱")),
    }



def classify_pattern(flags: dict) -> str:
    # v5：🚀與🛩合併。只要符合「曾突破中軌 → 紫線回踩 → 最新轉黃」，
    # 統一歸類為「中軌突破回踩轉黃型」；4H 紅轉綠只作為分數權重，不再拆成獨立型態。
    if flags.get("breakout_pullback_yellow_restart"):
        return "中軌突破回踩轉黃型"

    if flags.get("below_midline_po3_amd_candidate"):
        if flags.get("po3_amd_strong_reversal"):
            return "中軌下方 PO3/AMD 強反轉型"
        if flags.get("po3_amd_early_weak_rebound"):
            return "中軌下方 PO3/AMD 轉黃早期觀察型"
        # v5：🏆杯柄候選不再獨立成型態；保留 prior_breakout_then_pullback_reclaim 作為內部分數加權。
        return "中軌下方 PO3/AMD 反轉候選型"

    if flags.get("latest_color") == "yellow" and flags.get("latest_near_midline"):
        return "中軌附近磨合轉黃型"
    if flags.get("latest_color") == "purple":
        return "紫線未轉黃觀察型"
    return "一般觀察型"



def score_hint(flags: dict, item: dict) -> int:
    """
    給 GPT 的機械分數提示，不是最終交易建議。

    v5 分層：
    1. 最高分保留給「曾突破中軌 → 回踩中軌附近 → 最新轉黃」的 SOL 類確認型。
       其中 4H 前紅→4H 當綠給最高權重，但不再拆成獨立型態。
    2. 中軌下方的 XLM 類強反轉再強，也仍是「未確認過中軌壓力」；分數封頂，不給 100。
    3. BOME 類曾經站上中軌、後續回落再反攻，歸入 PO3/AMD 反轉候選型，但內部分數高於 ARB 類從頭到尾沒碰中軌。
    4. 站上中軌但乖離過大視為追高，分數要被封頂。
    """
    score = 0

    latest_color = flags.get("latest_color")
    latest_pct = _safe_float(flags.get("latest_pct_vs_midline"))
    near_midline_zone = bool(latest_pct is not None and -2.5 <= latest_pct <= 3.5)

    # 1) 結構底分：中軌突破回踩再啟動 > 曾經突破後回落 > 一般黃線 > 紫線觀察
    if flags.get("breakout_pullback_yellow_restart"):
        score += 60
    elif flags.get("had_yellow_above_midline_before_current_run") and latest_color == "yellow":
        score += 34
    elif latest_color == "yellow":
        score += 18
    elif latest_color == "purple":
        score += 6

    over_count = int(flags.get("yellow_over_previous_purple_count") or 0)

    # 2) PO3/AMD 分數：中軌下方仍需降階；但曾經站上中軌的杯柄候選要高於一路被壓制的幣。
    if flags.get("below_midline_po3_amd_candidate"):
        if flags.get("po3_amd_strong_reversal"):
            score += 30 + min(over_count, 3) * 4
        elif flags.get("prior_breakout_then_pullback_reclaim"):
            score += 31 + min(over_count, 3) * 3
        elif flags.get("po3_amd_w_bottom_candidate"):
            score += 24 + min(over_count, 3) * 3
        elif flags.get("po3_amd_early_weak_rebound"):
            score += 14 + min(over_count, 3) * 2
        else:
            score += 20 + min(over_count, 3) * 3

        if flags.get("structurally_suppressed_never_touched_midline"):
            score -= 8
    elif over_count >= 2 and latest_color == "yellow":
        score += 14 + min(over_count, 3) * 3

    # 3) 4H 觸發：紅轉綠最高；綠綠是延續，不等於最佳買點。
    if flags.get("four_h_red_to_green"):
        score += 22
    elif flags.get("four_h_green_green"):
        score += 12
    elif item.get("4H前") == "🟢" and item.get("4H當") == "🔴":
        score -= 8
    elif item.get("4H當") == "🔴":
        score += 2

    # 4) 中軌距離：靠近中軌加分；站上太遠或跌太深都降分。
    if latest_pct is not None:
        if -1.5 <= latest_pct <= 2.5:
            score += 14
        elif -3.5 <= latest_pct < -1.5:
            score += 8
        elif 2.5 < latest_pct <= 5.0:
            score += 6
        elif -6.0 <= latest_pct < -3.5:
            score += 3
        elif 5.0 < latest_pct <= 8.0:
            score -= 2
        elif 8.0 < latest_pct <= 12.0:
            score -= 12
        elif latest_pct > 12.0:
            score -= 22
        elif latest_pct < -12.0:
            score -= 10

    avg_margin = _safe_float(flags.get("avg_reclaim_margin_vs_prev3_purple_pct"))
    rebound = _safe_float(flags.get("rebound_from_recent_purple_low_pct"))
    transitions = int(flags.get("recent_color_transitions_8d") or 0)
    transitions_6d = int(flags.get("recent_color_transitions_6d") or 0)

    if flags.get("po3_amd_strong_reversal"):
        if rebound is not None and rebound >= 8.0:
            score += 5
        if latest_pct is not None and latest_pct >= -1.5:
            score += 3
    elif flags.get("prior_breakout_then_pullback_reclaim"):
        # 曾經站上中軌再回落，代表上方空方區塊已有被稀釋，杯柄反攻權重較高。
        score += 8
        if avg_margin is not None and avg_margin >= 2.0:
            score += 3
    elif flags.get("po3_amd_w_bottom_candidate"):
        if transitions >= 3:
            score += 3
        if transitions_6d >= 2:
            score -= 2
        if avg_margin is not None and avg_margin >= 2.0:
            score += 2
    elif flags.get("po3_amd_early_weak_rebound"):
        score -= 8
        if avg_margin is not None and avg_margin < 1.0:
            score -= 4

    final_score = max(0, min(100, int(round(score))))

    # 5) 最高分只給 SOL 類：中軌突破回踩轉黃；4H 紅轉綠 + 接近中軌才允許滿分。
    if flags.get("breakout_pullback_yellow_restart"):
        if flags.get("four_h_red_to_green") and near_midline_zone:
            final_score = 100
        elif flags.get("four_h_green_green") and near_midline_zone:
            final_score = max(final_score, 92)
            final_score = min(final_score, 96)
        else:
            final_score = min(final_score, 90)

    # 6) 中軌下方一律封頂：XLM 再強也不能與 SOL 類確認型同分。
    if flags.get("below_midline_po3_amd_candidate"):
        if flags.get("po3_amd_strong_reversal"):
            # 強反轉但未真正站上中軌：高分，但不給 100。
            final_score = min(final_score, 88)
            final_score = max(final_score, 82)
        elif flags.get("prior_breakout_then_pullback_reclaim"):
            # BOME 類：曾經稀釋過中軌上方空方區塊，仍歸入反轉候選，但分數高於 ARB 類。
            final_score = min(final_score, 86)
            final_score = max(final_score, 76)
        elif flags.get("po3_amd_w_bottom_candidate"):
            final_score = min(final_score, 80)
        elif flags.get("po3_amd_early_weak_rebound"):
            final_score = min(final_score, 55)
        else:
            final_score = min(final_score, 76)

        if flags.get("structurally_suppressed_never_touched_midline"):
            final_score = min(final_score, 74)

    # v5 防呆二次封頂：只要 pattern 仍屬中軌下方 PO3/AMD，就絕不可顯示 100。
    pattern_guard = _classify_pattern(flags)
    if pattern_guard == "中軌下方 PO3/AMD 強反轉型":
        final_score = min(final_score, 88)
        final_score = max(final_score, 82)
    elif pattern_guard == "中軌下方 PO3/AMD 反轉候選型":
        if flags.get("prior_breakout_then_pullback_reclaim"):
            final_score = min(final_score, 86)
            final_score = max(final_score, 76)
        else:
            final_score = min(final_score, 80)
    elif pattern_guard == "中軌下方 PO3/AMD 轉黃早期觀察型":
        final_score = min(final_score, 55)

    # 7) 站上中軌但乖離太大，視為追高，不應比回踩中軌型高。
    if latest_pct is not None and latest_pct > 0:
        if latest_pct > 15.0:
            final_score = min(final_score, 55)
        elif latest_pct > 10.0:
            final_score = min(final_score, 65)
        elif latest_pct > 7.0:
            final_score = min(final_score, 76)

    return max(0, min(100, int(final_score)))


