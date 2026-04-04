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

# ==================== 2. 注入進度條與終端機 CSS ====================
st.markdown("""
<style>
    /* 全局背景：你喜歡的暗石藍色 */
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
        margin-bottom: 2px;
    }
    .cyber-subtitle {
        font-size: 11px;
        color: #94a3b8;
        margin-bottom: 15px;
    }

    /* --- 終端機進度條外框 --- */
    #loader-container {
        background-color: #000; 
        padding: 30px;
        border-radius: 12px;
        border: 1px solid rgba(19, 242, 26, 0.3);
        width: 500px;
        margin: 40px auto; 
        text-align: center;
        box-shadow: 0 0 30px rgba(0, 0, 0, 0.5);
    }

    .terminal-text {
        color: #13f21a;
        font-family: 'Courier New', Courier, monospace;
        font-size: 22px;
        font-weight: bold;
        text-shadow: 0 0 10px #13f21a;
        margin-bottom: 20px;
        display: block;
    }

    /* 進度條長框 [ ======= ] */
    .progress-frame {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #13f21a;
        font-family: 'Courier New', Courier, monospace;
        font-size: 24px;
        gap: 10px;
    }

    .progress-bar-bg {
        width: 300px;
        height: 14px;
        border: 1px solid #13f21a;
        padding: 2px;
        position: relative;
    }

    .progress-bar-fill {
        height: 100%;
        background-color: #13f21a;
        box-shadow: 0 0 15px #13f21a;
        transition: width 0.2s ease-out;
    }

    /* 隱藏預設的 Spinner */
    [data-testid="stSpinner"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ==================== 3. 核心功能函式 ====================
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
                "open": float(k["open"]), "close": float(k["close"])
            })
        data.sort(key=lambda x: x["time"])
        return data
    except: return []

def calculate_heikin_ashi(klines):
    ha_klines = []
    prev_ha_open, prev_ha_close = None, None
    for i, kline in enumerate(klines):
        o, c = kline['open'], kline['close']
        if i == 0:
            ha_close = (o + o + o + c) / 4 
            ha_open = (o + c) / 2
        else:
            ha_close = (o + o + o + c) / 4 
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

# ==================== 4. 網頁介面啟動 ====================
st.markdown("<div class='cyber-title'>LD-NY BOUNDARY TERMINAL</div>", unsafe_allow_html=True)
st.markdown(f"<div class='cyber-subtitle'>SYSTEM STATUS: ACTIVE | UPDATED: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

placeholder = st.empty()

# --- 資料抓取與即時更新進度條 ---
symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

results = []
total = len(symbols)

for i, symbol in enumerate(symbols):
    # 更新進度條 UI
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
    
    # 執行抓取
    ha1d = calculate_heikin_ashi(fetch_klines(symbol, "1D"))
    p1d, c1d = get_status_emoji(ha1d)
    ha4h = calculate_heikin_ashi(fetch_klines(symbol, "4H"))
    p4h, c4h = get_status_emoji(ha4h)

    results.append({
        "幣種": symbol,
        "1D前": p1d, "1D今": c1d,
        "4H前": p4h, "4H今": c4h,
        "val": (get_status_value(p1d), get_status_value(c1d), get_status_value(p4h), get_status_value(c4h))
    })

# 資料處理
df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])

# 清除進度條
placeholder.empty()

# 顯示表格
def apply_style(df):
    def color_logic(v):
        if v == '🟢': return 'color: #22c55e; font-weight: bold;'
        if v == '🔴': return 'color: #ef4444; font-weight: bold;'
        return 'color: #64748b;'
    styler = df.style
    func = getattr(styler, "map", getattr(styler, "applymap", None))
    return func(color_logic, subset=["1D前", "1D今", "4H前", "4H今"])

st.dataframe(apply_style(df), use_container_width=True, height=750)
st.success("SYNC COMPLETE.")
