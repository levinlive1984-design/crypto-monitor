import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ==================== 1. 網頁頁面設定 ====================
st.set_page_config(
    page_title="HA Crypto Analytics",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 2. 注入 Cyberpunk 玻璃皮膚 CSS ====================
st.markdown("""
<style>
    /* 全局背景：深邃黑 */
    [data-testid="stAppViewContainer"] {
        background-color: #0b0e14;
        color: #e0e6ed;
    }
    
    /* 玻璃頂部欄 */
    [data-testid="stHeader"] {
        background: rgba(15, 23, 42, 0.6) !important;
        backdrop-filter: blur(10px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* 標題樣式：縮小並改為琥珀金 */
    .cyber-title {
        font-size: 20px; /* 標題縮小 */
        font-weight: 700;
        color: #ffb000; /* 琥珀金 */
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 0px;
    }
    
    .cyber-subtitle {
        font-size: 11px;
        color: #64748b;
        margin-bottom: 20px;
    }

    /* 表格容器樣式 */
    .stDataFrame {
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        overflow: hidden;
        background: rgba(30, 41, 59, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# ==================== 3. 功能函式區 ====================
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

# ==================== 4. 網頁介面主體 ====================
st.markdown("<div class='cyber-title'>Analytics Hub v2.0</div>", unsafe_allow_html=True)
st.markdown(f"<div class='cyber-subtitle'>Heikin Ashi Monitor | Last Update: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

# 自動執行
with st.spinner('SYSTEM LOADING...'):
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

    # 排序
    df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])
    
    # --- 修正後的表格顏色邏輯 (解決報錯問題) ---
    def apply_style(df):
        def color_logic(v):
            if v == '🟢': return 'color: #00ffcc; font-weight: bold;' # 螢光青綠
            if v == '🔴': return 'color: #ff3366; font-weight: bold;' # 霓虹紅
            return 'color: #475569;'
        
        # 自動偵測 Pandas 版本使用 map 或 applymap
        styler = df.style
        func = getattr(styler, "map", getattr(styler, "applymap", None))
        return func(color_logic, subset=["1D前", "1D今", "4H前", "4H今"])

    st.dataframe(apply_style(df), use_container_width=True, height=750)
