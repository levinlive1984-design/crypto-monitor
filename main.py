import requests
import pandas as pd
import streamlit as st
from datetime import datetime
import time

# ==================== 1. 網頁頁面設定 ====================
st.set_page_config(
    page_title="HA Crypto Analytics",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 2. 注入自定義 CSS (皮膚 + 終端機特效) ====================
st.markdown("""
<style>
    /* 全局背景：你喜歡的暗石藍色 */
    [data-testid="stAppViewContainer"] {
        background-color: #1e293b; 
        color: #f1f5f9;
    }
    
    /* 頂部導航欄玻璃感 */
    [data-testid="stHeader"] {
        background: rgba(30, 41, 59, 0.7) !important;
        backdrop-filter: blur(8px);
    }
    
    /* 標題與副標題樣式 */
    .cyber-title {
        font-size: 20px; 
        font-weight: 700;
        color: #fbbf24; /* 亮金 */
        letter-spacing: 1.5px;
        margin-bottom: 2px;
    }
    .cyber-subtitle {
        font-size: 11px;
        color: #94a3b8;
        margin-bottom: 15px;
    }

    /* --- 終端機加載畫面特效 --- */
    #terminal-loader {
        background-color: #000; 
        color: #13f21a;        /* 經典終端機綠 */
        font-family: 'Courier New', Courier, monospace;
        padding: 20px;
        border-radius: 8px;
        border: 2px solid #13f21a; 
        width: fit-content;
        margin: 40px auto; 
        box-shadow: 0 0 20px rgba(19, 242, 26, 0.4);
        text-align: center;
    }
    .terminal-text {
        font-size: 24px;
        font-weight: bold;
        text-shadow: 0 0 10px #13f21a;
        animation: flickering 0.15s infinite;
    }
    .terminal-cursor {
        display: inline-block;
        width: 12px;
        height: 24px;
        background-color: #13f21a;
        margin-left: 5px;
        animation: blink 0.8s infinite;
    }
    @keyframes flickering {
        0% { opacity: 1; } 50% { opacity: 0.8; } 100% { opacity: 1; }
    }
    @keyframes blink {
        0%, 100% { opacity: 0; } 50% { opacity: 1; }
    }
    /* 隱藏原本預設的轉圈圈 */
    [data-testid="stSpinner"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ==================== 3. 核心功能函式 (抓資料邏輯) ====================
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

# --- A. 建立一個「空白佔位符」，用來放加載畫面 ---
placeholder = st.empty()

# --- B. 在佔位符裡秀出你的「終端機綠色閃爍」加載畫面 ---
placeholder.markdown("""
    <div id="terminal-loader">
        <span class="terminal-text">SYSTEM LOADING...</span><span class="terminal-cursor"></span>
    </div>
""", unsafe_allow_html=True)

# --- C. 開始跑背景數據抓取 ---
symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

results = []
for symbol in symbols:
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

df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])

# --- D. 數據抓完了，把「加載畫面」清空 ---
placeholder.empty()

# --- E. 顯示最終的表格內容 ---
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
