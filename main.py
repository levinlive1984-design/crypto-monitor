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

# ==================== 2. 注入 CSS (視覺風格與下拉選單樣式) ====================
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

    /* 下拉選單與按鈕樣式優化 */
    div[data-baseweb="select"] {
        background-color: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid #13f21a !important;
        border-radius: 4px;
    }
    
    .stButton>button {
        background-color: transparent !important;
        color: #13f21a !important;
        border: 1px solid #13f21a !important;
        font-family: 'Courier New', Courier, monospace !important;
        font-weight: bold !important;
        border-radius: 4px !important;
        width: 100%;
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

# ==================== 3. 原始主程式 (核心邏輯：絕對不動) ====================

def fetch_klines(symbol, limit=150):
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
            "open": float(k["open"]),
            "high": float(k["high"]),
            "low": float(k["low"]),
            "close": float(k["close"]),
            "volume": float(k["volume"])
        })
    data.sort(key=lambda x: x["time"])
    return data

def calculate_heikin_ashi(klines):
    ha_klines = []
    prev_ha_open = None
    prev_ha_close = None
    for i, kline in enumerate(klines):
        open_price, high_price, low_price, close_price = kline['open'], kline['high'], kline['low'], kline['close']
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
        prev_ha_open, prev_ha_close = ha_open, ha_close
    return ha_klines

def get_status_value(status_str):
    if status_str == "🔴": return 0
    elif status_str == "⚫": return 1
    elif status_str == "🟢": return 2
    return 3

# ==================== 4. 幣種清單定義 ====================

symbols_exam = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

symbols_dwf = [
    "ALGO","FET","BONK","CRV","FLOKI","JASMY","IOTA","GALA","A","EGLD","SNX","BEAMX","TURBO","ACH","KAVA","MASK","ID","COTI","CYBER","AUCTION","PHA","SPELL","YGG","BICO","C98","AGLD","METIS","DODO","ARPA","HIGH","HFT","BEL","MBOX","PORTAL"
]

# ==================== 5. 介面佈局與邏輯 ====================

# 頂部欄：左邊標題，中間下拉選單，右邊按鈕
col_title, col_select, col_btn = st.columns([0.65, 0.22, 0.13])

with col_title:
    st.markdown("<div class='cyber-title'>Heikin-Ashi Monitor Terminal</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='cyber-subtitle'>CORE PROTOCOL ACTIVE | UPDATED: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

with col_select:
    # 下拉式選項
    selection = st.selectbox("", ["考試幣", "DWF"], label_visibility="collapsed")

with col_btn:
    # 重新分析按鈕
    btn_container = st.empty()

# 決定要分析的清單
symbols = symbols_exam if selection == "考試幣" else symbols_dwf

# 進度條空位
placeholder = st.empty()

results = []
total = len(symbols)

# --- 執行分析循環 ---
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
    
    try:
        # 1D 分析
        k1d = fetch_klines(symbol)
        ha1d = calculate_heikin_ashi(k1d)
        p1d = "🟢" if ha1d[-2]['close'] > ha1d[-2]['open'] else ("🔴" if ha1d[-2]['close'] < ha1d[-2]['open'] else "⚫") if len(ha1d)>=2 else "⚫"
        c1d = "🟢" if ha1d[-1]['close'] > ha1d[-1]['open'] else ("🔴" if ha1d[-1]['close'] < ha1d[-1]['open'] else "⚫") if ha1d else "⚫"

        # 4H 分析
        k4h = fetch_klines_4h(symbol)
        ha4h = calculate_heikin_ashi(k4h)
        p4h = "🟢" if ha4h[-2]['close'] > ha4h[-2]['open'] else ("🔴" if ha4h[-2]['close'] < ha4h[-2]['open'] else "⚫") if len(ha4h)>=2 else "⚫"
        c4h = "🟢" if ha4h[-1]['close'] > ha4h[-1]['open'] else ("🔴" if ha4h[-1]['close'] < ha4h[-1]['open'] else "⚫") if ha4h else "⚫"

        results.append({
            "幣種": symbol, "1D前": p1d, "1D當": c1d, "4H前": p4h, "4H當": c4h,
            "val": (get_status_value(p1d), get_status_value(c1d), get_status_value(p4h), get_status_value(c4h))
        })
    except:
        pass

# 排序
df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])

# 清除進度條
placeholder.empty()

# --- 6. 顯示結果 ---

def apply_style(df):
    def color_logic(v):
        if v == '🟢': return 'color: #22c55e; font-weight: bold;'
        elif v == '🔴': return 'color: #ef4444; font-weight: bold;'
        return 'color: #64748b;'
    styler = df.style
    func = getattr(styler, "map", getattr(styler, "applymap", None))
    return func(color_logic, subset=["1D前", "1D當", "4H前", "4H當"])

# 顯示表格
st.dataframe(apply_style(df), use_container_width=True, height=680)

# 在右上角塞入按鈕
if btn_container.button("⚡ 重新分析"):
    st.rerun()

st.toast(f"✅ {selection} SYNC COMPLETE.", icon="⚡")
