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

# ==================== 2. 注入 CSS (消除雙捲軸 + 終端機皮膚) ====================
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
        font-size: 20px; 
        font-weight: 700;
        color: #fbbf24;
        letter-spacing: 1.5px;
        margin-top: -20px;
    }
    .cyber-subtitle {
        font-size: 11px;
        color: #94a3b8;
        margin-bottom: 10px;
    }
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

# ==================== 3. 核心功能函式 (還原你的原始邏輯) ====================
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
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"])
            })
        data.sort(key=lambda x: x["time"])
        return data
    except: return []

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

        ha_klines.append({
            'open': ha_open,
            'close': ha_close
        })
        prev_ha_open = ha_open
        prev_ha_close = ha_close
    return ha_klines

def get_status_emoji(ha_list):
    if len(ha_list) < 2: return "⚫", "⚫"
    def check(bar): 
        return "🟢" if bar['close'] > bar['open'] else ("🔴" if bar['close'] < bar['open'] else "⚫")
    return check(ha_list[-2]), check(ha_list[-1])

def get_status_value(status_str):
    return {"🔴": 0, "⚫": 1, "🟢": 2}.get(status_str, 3)

# ==================== 4. 介面啟動 ====================
st.markdown("<div class='cyber-title'>📊Heikin  Ashi Monitor Terminal</div>", unsafe_allow_html=True)
st.markdown(f"<div class='cyber-subtitle'>CORE PROTOCOL ACTIVE | UPDATED: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

placeholder = st.empty()

symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

results = []
total = len(symbols)

for i, symbol in enumerate(symbols):
    percent = int(((i + 1) / total) * 100)
    placeholder.markdown(f"""
        <div id="loader-container">
            <span class="terminal-text">SYSTEM LOADING... {percent}%</span>
            <div class="progress-frame">
                <span>[</span>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width: {percent}%;"></div>
                </div>
                <span>]</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # 抓取 1D 與 4H 並帶入原始公式計算
    ha1d = calculate_heikin_ashi(fetch_klines(symbol, "1D"))
    p1d, c1d = get_status_emoji(ha1d)
    
    ha4h = calculate_heikin_ashi(fetch_klines(symbol, "4H"))
    p4h, c4h = get_status_emoji(ha4h)

    results.append({
        "幣種": symbol, "1D前一根": p1d, "1D當下": c1d, "4H前一根": p4h, "4H當下": c4h,
        "val": (get_status_value(p1d), get_status_value(c1d), get_status_value(p4h), get_status_value(c4h))
    })

df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])
placeholder.empty()

# --- 5. 顯示數據表格 ---
def apply_style(df):
    def color_logic(v):
        if v == '🟢': return 'color: #22c55e; font-weight: bold;'
        if v == '🔴': return 'color: #ef4444; font-weight: bold;'
        return 'color: #64748b;'
    styler = df.style
    func = getattr(styler, "map", getattr(styler, "applymap", None))
    return func(color_logic, subset=["1D前一根", "1D當下", "4H前一根", "4H當下"])

st.dataframe(apply_style(df), use_container_width=True, height=680)
st.toast("✅ DATA SYNC COMPLETE.", icon="⚡")
