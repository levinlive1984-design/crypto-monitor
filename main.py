import requests
import pandas as pd
import streamlit as st
from datetime import datetime
import time

# ==================== 1. 網頁頁面設定 ====================
st.set_page_config(
    page_title="HA Crypto Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 2. 注入 CSS (含賽博按鈕樣式) ====================
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] {
        overflow: hidden; 
        height: 100vh;
    }
    [data-testid="stAppViewContainer"] {
        background-color: #1e293b; 
        color: #f1f5f9;
    }
    [data-testid="stHeader"] {
        background: rgba(30, 41, 59, 0.7) !important;
        backdrop-filter: blur(8px);
    }
    .cyber-title {
        font-size: 22px; 
        font-weight: 700;
        color: #fbbf24;
        letter-spacing: 1.5px;
        margin-top: -15px;
    }
    .cyber-subtitle {
        font-size: 11px;
        color: #94a3b8;
    }

    /* 重新分析按鈕樣式 */
    .stButton>button {
        background-color: transparent !important;
        color: #13f21a !important;
        border: 1px solid #13f21a !important;
        font-family: 'Courier New', Courier, monospace !important;
        font-weight: bold !important;
        box-shadow: 0 0 10px rgba(19, 242, 26, 0.2);
        transition: all 0.3s;
        border-radius: 4px !important;
    }
    .stButton>button:hover {
        background-color: rgba(19, 242, 26, 0.1) !important;
        box-shadow: 0 0 20px rgba(19, 242, 26, 0.5);
    }

    /* 終端機進度條 */
    #loader-container {
        background-color: #000; 
        padding: 30px;
        border-radius: 12px;
        border: 1px solid rgba(19, 242, 26, 0.3);
        width: 450px;
        margin: 100px auto; 
        text-align: center;
    }
    .terminal-text {
        color: #13f21a;
        font-family: 'Courier New', Courier, monospace;
        font-size: 20px;
        text-shadow: 0 0 10px #13f21a;
        margin-bottom: 15px;
        display: block;
    }
    .progress-frame {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #13f21a;
        font-family: 'Courier New', Courier, monospace;
        gap: 10px;
    }
    .progress-bar-bg {
        width: 250px;
        height: 10px;
        border: 1px solid #13f21a;
        padding: 2px;
    }
    .progress-bar-fill {
        height: 100%;
        background-color: #13f21a;
        box-shadow: 0 0 10px #13f21a;
    }
    [data-testid="stSpinner"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ==================== 3.（（不能動的邏輯））====================
def fetch_klines(symbol, limit=150): # 預設 1D
    url = "https://api.pionex.com/api/v1/market/klines"
    params = {"symbol": f"{symbol}_USDT", "interval": "1D", "limit": limit}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    klines = resp.json()["data"]["klines"]
    data = []
    for k in klines:
        data.append({
            "time": int(k["time"]) + 8*3600*1000,
            "open": float(k["open"]), "high": float(k["high"]),
            "low": float(k["low"]), "close": float(k["close"]), "volume": float(k["volume"])
        })
    data.sort(key=lambda x: x["time"])
    return data

def fetch_klines_4h(symbol, limit=150):
    url = "https://api.pionex.com/api/v1/market/klines"
    params = {"symbol": f"{symbol}_USDT", "interval": "4H", "limit": limit}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    klines = resp.json()["data"]["klines"]
    data = []
    for k in klines:
        data.append({
            "time": int(k["time"]) + 8*3600*1000,
            "open": float(k["open"]), "high": float(k["high"]),
            "low": float(k["low"]), "close": float(k["close"]), "volume": float(k["volume"])
        })
    data.sort(key=lambda x: x["time"])
    return data

def calculate_heikin_ashi(klines):
    ha_klines = []
    prev_ha_open = None
    prev_ha_close = None
    for i, kline in enumerate(klines):
        o, h, l, c = kline['open'], kline['high'], kline['low'], kline['close']
        if i == 0:
            ha_close = (o + h + l + c) / 4
            ha_open = (o + c) / 2
        else:
            ha_close = (o + h + l + c) / 4
            ha_open = (prev_ha_open + prev_ha_close) / 2
        
        ha_high = max(h, ha_open, ha_close)
        ha_low = min(l, ha_open, ha_close)
        
        ha_klines.append({'time': kline['time'], 'open': ha_open, 'high': ha
