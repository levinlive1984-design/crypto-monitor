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

# ==================== 2. 注入 CSS (視覺風格) ====================
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #1e293b; 
        color: #f1f5f9;
        font-family: 'Courier New', Courier, monospace;
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
    div[data-baseweb="select"] {
        background-color: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid #13f21a !important;
        border-radius: 4px;
    }
    .stButton>button {
        background-color: transparent !important;
        color: #13f21a !important;
        border: 1px solid #13f21a !important;
        font-weight: bold !important;
        border-radius: 4px !important;
        width: 100%;
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
        font-size: 20px;
        text-shadow: 0 0 10px #13f21a;
        margin-bottom: 15px;
        display: block;
    }
    .progress-bar-bg {
        width: 250px;
        height: 10px;
        border: 1px solid #13f21a;
        padding: 2px;
        margin: 0 auto;
    }
    .progress-bar-fill {
        height: 100%;
        background-color: #13f21a;
        box-shadow: 0 0 10px #13f21a;
    }
    [data-testid="stSpinner"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ==================== 3. 核心抓取邏輯 (加上緩存保護) ====================

@st.cache_data(ttl=600)  # 數據緩存 10 分鐘，避免重複請求
def get_crypto_data(symbol, interval):
    """
    從 Pionex 獲取數據，加上 timeout 避免掛起
    """
    url = "https://api.pionex.com/api/v1/market/klines"
    params = {"symbol": f"{symbol}_USDT", "interval": interval, "limit": 150}
    try:
        # 加上 timeout=5 秒，如果伺服器不回傳就跳過，不卡死
        resp = requests.get(url, params=params, timeout=5)
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
    except Exception:
        return None

def calculate_heikin_ashi(klines):
    if not klines: return []
    ha_klines = []
    prev_ha_open = None
    prev_ha_close = None
    for i, kline in enumerate(klines):
        open_p, high_p, low_p, close_p = kline['open'], kline['high'], kline['low'], kline['close']
        if i == 0:
            ha_close = (open_p + high_p + low_p + close_p) / 4
            ha_open = (open_p + close_p) / 2
        else:
            ha_close = (open_p + high_p + low_p + close_p) / 4
            ha_open = (prev_ha_open + prev_ha_close) / 2
        ha_high = max(high_p, ha_open, ha_close)
        ha_low = min(low_p, ha_open, ha_close)
        ha_klines.append({'time': kline['time'], 'open': ha_open, 'high': ha_high, 'low': ha_low, 'close': ha_close})
        prev_ha_open, prev_ha_close = ha_open, ha_close
    return ha_klines

def get_status_value(status_str):
    mapping = {"🔴": 0, "⚫": 1, "🟢": 2}
    return mapping.get(status_str, 3)

# ==================== 4. 幣種清單 ====================

SYMBOLS_CONFIG = {
    "考試幣": ["ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"],
    "DWF": ["ALGO","FET","BONK","CRV","FLOKI","JASMY","IOTA","GALA","A","EGLD","SNX","BEAMX","TURBO","ACH","KAVA","MASK","ID","COTI","CYBER","AUCTION","PHA","SPELL","YGG","BICO","C98","AGLD","METIS","DODO","ARPA","HIGH","HFT","BEL","MBOX","PORTAL"]
}

# ==================== 5. 介面佈局 ====================

col_title, col_select, col_btn = st.columns([0.65, 0.22, 0.13])

with col_title:
    st.markdown("<div class='cyber-title'>Heikin-Ashi Monitor Terminal</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='cyber-subtitle'>CORE PROTOCOL ACTIVE | UPDATED: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

with col_select:
    selection = st.selectbox("", list(SYMBOLS_CONFIG.keys()), label_visibility="collapsed")

with col_btn:
    if st.button("⚡ 重新分析"):
        st.cache_data.clear()  # 清除緩存，強制抓取最新數據
        st.rerun()

# --- 執行分析循環 ---
symbols = SYMBOLS_CONFIG[selection]
placeholder = st.empty()
results = []

for i, symbol in enumerate(symbols):
    percent = int(((i + 1) / len(symbols)) * 100)
    # 動態進度條
    placeholder.markdown(f"""
        <div id="loader-container">
            <span class="terminal-text">DEEP SCANNING: {symbol} {percent}%</span>
            <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: {percent}%;"></div></div>
        </div>
    """, unsafe_allow_html=True)
    
    # 分別抓取 1D 和 4H
    k1d_raw = get_crypto_data(symbol, "1D")
    k4h_raw = get_crypto_data(symbol, "4H")
    
    if k1d_raw and k4h_raw:
        ha1d = calculate_heikin_ashi(k1d_raw)
        ha4h = calculate_heikin_ashi(k4h_raw)
        
        # 判斷顏色邏輯
        p1d = "🟢" if ha1d[-2]['close'] > ha1d[-2]['open'] else ("🔴" if ha1d[-2]['close'] < ha1d[-2]['open'] else "⚫")
        c1d = "🟢" if ha1d[-1]['close'] > ha1d[-1]['open'] else ("🔴" if ha1d[-1]['close'] < ha1d[-1]['open'] else "⚫")
        p4h = "🟢" if ha4h[-2]['close'] > ha4h[-2]['open'] else ("🔴" if ha4h[-2]['close'] < ha4h[-2]['open'] else "⚫")
        c4h = "🟢" if ha4h[-1]['close'] > ha4h[-1]['open'] else ("🔴" if ha4h[-1]['close'] < ha4h[-1]['open'] else "⚫")
        
        results.append({
            "幣種": symbol, "1D前": p1d, "1D當": c1d, "4H前": p4h, "4H當": c4h,
            "val": (get_status_value(p1d), get_status_value(c1d), get_status_value(p4h), get_status_value(c4h))
        })

# 清除進度條並顯示表格
placeholder.empty()

if results:
    df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])
    
    # 樣式處理
    def color_logic(v):
        if v == '🟢': return 'color: #22c55e; font-weight: bold;'
        elif v == '🔴': return 'color: #ef4444; font-weight: bold;'
        return 'color: #64748b;'

    st.dataframe(
        df.style.map(color_logic, subset=["1D前", "1D當", "4H前", "4H當"]),
        use_container_width=True, 
        height=680,
        hide_index=True
    )

st.toast(f"✅ {selection} SYNC COMPLETE.", icon="⚡")
