import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ==================== 基礎設定 ====================
st.set_page_config(page_title="加密幣監控系統", layout="wide")

symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

# ==================== 功能函式 (不變) ====================
def fetch_klines(symbol, interval, limit=150):
    try:
        url = "https://api.pionex.com/api/v1/market/klines"
        params = {"symbol": f"{symbol}_USDT", "interval": interval, "limit": limit}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        klines = resp.json()["data"]["klines"]
        data = []
        for k in klines:
            data.append({
                "time": int(k["time"]) + 8*3600*1000,
                "open": float(k["open"]), "high": float(k["high"]),
                "low": float(k["low"]), "close": float(k["close"])
            })
        data.sort(key=lambda x: x["time"])
        return data
    except: return []

def calculate_heikin_ashi(klines):
    ha_klines = []
    prev_ha_open, prev_ha_close = None, None
    for i, kline in enumerate(klines):
        o, h, l, c = kline['open'], kline['high'], kline['low'], kline['close']
        if i == 0:
            ha_close = (o + h + l + c) / 4
            ha_open = (o + c) / 2
        else:
            ha_close = (o + h + l + c) / 4
            ha_open = (prev_ha_open + prev_ha_close) / 2
        ha_klines.append({'open': ha_open, 'close': ha_close})
        prev_ha_open, prev_ha_close = ha_open, ha_close
    return ha_klines

def get_status_emoji(ha_list):
    if len(ha_list) < 2: return "⚫", "⚫"
    def check(bar): return "🟢" if bar['close'] > bar['open'] else ("🔴" if bar['close'] < bar['open'] else "⚫")
    return check(ha_list[-2]), check(ha_list[-1])

def get_status_value(status_str):
    return {"🔴": 0, "⚫": 1, "🟢": 2}.get(status_str, 3)

# ==================== 網頁介面 (移除按鈕閘門) ====================
st.title("💹 加密幣 Heikin Ashi 戰情室")
st.write(f"數據來源：Pionex | 當前系統時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# --- 這裡直接開始跑，不設 if button ---
with st.spinner('🚀 偵測到進入網頁，正在自動更新全幣種行情...'):
    results = []
    for symbol in symbols:
        ha1d = calculate_heikin_ashi(fetch_klines(symbol, "1D"))
        prev1d, curr1d = get_status_emoji(ha1d)
        
        ha4h = calculate_heikin_ashi(fetch_klines(symbol, "4H"))
        prev4h, curr4h = get_status_emoji(ha4h)

        results.append({
            "幣種": symbol,
            "1D前一根": prev1d, "1D當下": curr1d,
            "4H前一根": prev4h, "4H當下": curr4h,
            "sort_key": (get_status_value(prev1d), get_status_value(curr1d), get_status_value(prev4h), get_status_value(curr4h))
        })

    # 排序並顯示
    df = pd.DataFrame(results).sort_values(by="sort_key").drop(columns=["sort_key"])
    st.success("✅ 數據已自動更新完畢！")
    st.dataframe(df, use_container_width=True, height=800)

# 如果想手動重新整理，網頁右上角選單也有 Rerun 功能，或者直接重新整理瀏覽器
