import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ==================== 1. 網頁頁面設定 ====================
st.set_page_config(
    page_title="HA Crypto Watch", # 改個專業的名字
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 2. 注入自定義 CSS 網頁皮膚 ====================
# 這裡使用了深色背景、螢光色標籤，並在上方加入玻璃反射效果
st.markdown("""
<style>
    /* 1. 全局深色底色與玻璃質感背景 */
    [data-testid="stAppViewContainer"] {
        background-color: #0d1117; /* 深色底 */
        color: #c9d1d9; /* 淺灰色文字 */
    }
    
    /* 2. 在網頁最上方加入微弱的玻璃反射圖層 */
    [data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.03); /* 半透明白 */
        backdrop-filter: blur(5px); /* 模糊背景，產生玻璃感 */
        -webkit-backdrop-filter: blur(5px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* 3. 調整中間內容區域的樣式 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 1rem;
    }

    /* 4. 將原本大標題改小，並加上琥珀金（金色）樣式 */
    .styled-title {
        font-size: 24px; /* 字體改小 */
        font-weight: 700;
        color: #e3b341; /* 金色 */
        margin-bottom: 5px;
        letter-spacing: 1px;
    }
    
    /* 5. 小號文字樣式 */
    .styled-subtitle {
        font-size: 14px;
        color: #8b949e;
        margin-bottom: 20px;
    }

    /* 6. 表格樣式優化 (深色系) */
    [data-testid="stDataFrame"] {
        background-color: #161b22;
        border-radius: 8px;
        border: 1px solid #30363d;
        padding: 10px;
    }
    
    /* 將 Streamlit 的 Spinner (轉圈圈) 和提示框也改成深色系 */
    .stSpinner > div {
        color: #e3b341 !important;
    }
    .stAlert {
        background-color: #21262d !important;
        border: 1px solid #30363d !important;
        color: #c9d1d9 !important;
    }

</style>
""", unsafe_allow_html=True)

# ==================== 3. 基礎設定 ====================
symbols = [
    "ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", 
    "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", 
    "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME"
]

# ==================== 4. 功能函式 ====================
# ... 功能函式區內容與上一版完全一致，保持穩定不變 ...
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

# ==================== 5. 網頁介面主體 ====================
# 改用 HTML/CSS 寫小號標題
st.markdown("<div class='styled-title'>💹 加密幣 Heikin Ashi 戰情室</div>", unsafe_allow_html=True)
st.markdown(f"<div class='styled-subtitle'>數據來源：Pionex | 當前系統時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)

# --- 直接開始跑，不設 if button ---
with st.spinner('🚀 偵測到進入網頁，正在自動更新全幣種行情...'):
    results = []
    for symbol in symbols:
        # 抓取並計算 1D 與 4H
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

    # 排序
    df_results = pd.DataFrame(results).sort_values(by="sort_key").drop(columns=["sort_key"])
    st.success("✅ 數據已自動更新完畢！")

    # ==================== 6. 表格細胞顏色優化 ====================
    # 讓表格內出現的綠色🔴和紅色🔴看起來更像螢光標籤
    def style_dataframe(df):
        def color_status(val):
            color = ''
            if val == '🟢': color = '#00ff00; font-weight: bold; background-color: rgba(0, 255, 0, 0.05);' # 螢光綠
            elif val == '🔴': color = '#ff4b4b; font-weight: bold; background-color: rgba(255, 75, 75, 0.05);' # 亮紅
            elif val == '⚫': color = '#8b949e;' # 淺灰
            return f'color: {color}'
        
        styled_df = df.style.applymap(color_status, subset=['1D前一根', '1D當下', '4H前一根', '4H當下'])
        # 幣種一欄改為亮白色
        styled_df = styled_df.applymap(lambda v: 'color: white; font-weight: bold;', subset=['幣種'])
        return styled_df

    # 顯示優化過後的表格
    st.dataframe(style_dataframe(df_results), use_container_width=True, height=800)

# =========================================================
