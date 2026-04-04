import requests
import math
from datetime import datetime
import pandas as pd
import streamlit as st  # 引入網頁套件

# ==================== 網頁頁面基本設定 ====================
st.set_page_config(page_title="加密幣監控系統", layout="wide")

# ==================== 幣種設定 ====================
symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

# ==================== 功能函式區 (保持原始邏輯) ====================
def fetch_klines(symbol, limit=150):
    try:
        url = "https://api.pionex.com/api/v1/market/klines"
        params = {"symbol": f"{symbol}_USDT", "interval": "1D", "limit": limit}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        klines = resp.json()["data"]["klines"]
        data = []
        for k in klines:
            data.append({
                "time": int(k["time"]) + 8*3600*1000,
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"])
            })
        data.sort(key=lambda x: x["time"])
        return data
    except:
        return []

def fetch_klines_4h(symbol, limit=150):
    try:
        url = "https://api.pionex.com/api/v1/market/klines"
        params = {"symbol": f"{symbol}_USDT", "interval": "4H", "limit": limit}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        klines = resp.json()["data"]["klines"]
        data = []
        for k in klines:
            data.append({
                "time": int(k["time"]) + 8*3600*1000,
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"])
            })
        data.sort(key=lambda x: x["time"])
        return data
    except:
        return []

def calculate_heikin_ashi(klines):
    ha_klines = []
    prev_ha_open = None
    prev_ha_close = None

    for i, kline in enumerate(klines):
        open_price = kline['open']
        high_price = kline['high']
        low_price = kline['low']
        close_price = kline['close']

        if i == 0:
            ha_close = (open_price + high_price + low_price + close_price) / 4
            ha_open = (open_price + close_price) / 2
        else:
            ha_close = (open_price + high_price + low_price + close_price) / 4
            ha_open = (prev_ha_open + prev_ha_close) / 2

        ha_high = max(high_price, ha_open, ha_close)
        ha_low = min(low_price, ha_open, ha_close)

        ha_klines.append({
            'time': kline['time'], 'open': ha_open, 'high': ha_high, 'low': ha_low, 'close': ha_close
        })
        prev_ha_open = ha_open
        prev_ha_close = ha_close
    return ha_klines

def get_status_value(status_str):
    mapping = {"🔴": 0, "⚫": 1, "🟢": 2}
    return mapping.get(status_str, 3)

def custom_sort_key(item):
    return (
        get_status_value(item["prev_1d"]),
        get_status_value(item["curr_1d"]),
        get_status_value(item["prev_4h"]),
        get_status_value(item["curr_4h"])
    )

# ==================== Streamlit 網頁主體 ====================
st.title("📊 Heikin Ashi 多時區監控戰情室")
st.markdown("當前分析數據來源：**Pionex 交易所**")

if st.button("🚀 點擊開始掃描全幣種行情"):
    with st.spinner('正在分析數據中，請稍候...'):
        results = []
        for symbol in symbols:
            prev_status_1d_str = "⚫"
            status_1d_str = "⚫"
            prev_status_4h_str = "⚫"
            status_4h_str = "⚫"

            # 1D 分析
            k1d = fetch_klines(symbol)
            ha1d = calculate_heikin_ashi(k1d)
            if len(ha1d) >= 2:
                p = ha1d[-2]
                c = ha1d[-1]
                prev_status_1d_str = "🟢" if p['close'] > p['open'] else ("🔴" if p['close'] < p['open'] else "⚫")
                status_1d_str = "🟢" if c['close'] > c['open'] else ("🔴" if c['close'] < c['open'] else "⚫")

            # 4H 分析
            k4h = fetch_klines_4h(symbol)
            ha4h = calculate_heikin_ashi(k4h)
            if len(ha4h) >= 2:
                p = ha4h[-2]
                c = ha4h[-1]
                prev_status_4h_str = "🟢" if p['close'] > p['open'] else ("🔴" if p['close'] < p['open'] else "⚫")
                status_4h_str = "🟢" if c['close'] > c['open'] else ("🔴" if c['close'] < c['open'] else "⚫")

            results.append({
                "symbol": symbol,
                "prev_1d": prev_status_1d_str,
                "curr_1d": status_1d_str,
                "prev_4h": prev_status_4h_str,
                "curr_4h": status_4h_str
            })

        # 排序
        results.sort(key=custom_sort_key)

        # 轉成 DataFrame 並顯示
        df_results = pd.DataFrame(results)
        df_results.rename(columns={
            'symbol': '幣種',
            'prev_1d': '1D 前一根',
            'curr_1d': '1D 當下',
            'prev_4h': '4H 前一根',
            'curr_4h': '4H 當下'
        }, inplace=True)

        st.success(f"更新完成！資料時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.dataframe(df_results, use_container_width=True, height=800)
else:
    st.write("請點擊上方按鈕開始獲取最新分析結果。")