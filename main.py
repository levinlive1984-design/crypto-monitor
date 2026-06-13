import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone, timedelta
import time

# 台灣時區 UTC+8
TW_TZ = timezone(timedelta(hours=8))

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

    /* 移除頁面上下 padding */
    .block-container {
        padding-top: 3.5rem !important;
        padding-bottom: 0rem !important;
    }

    /* 強制放大 dataframe 內所有文字格的字體，讓 ▲▼ 跟 emoji 等大 */
    [data-testid="stDataFrame"] iframe {
        font-size: 20px !important;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 3. 核心抓取邏輯 (加上緩存保護) ====================

@st.cache_data(ttl=600)
def get_crypto_data(symbol, interval):
    """
    從 Pionex 獲取數據，加上 timeout 避免掛起
    """
    url = "https://api.pionex.com/api/v1/market/klines"
    params = {"symbol": f"{symbol}_USDT", "interval": interval, "limit": 150}
    try:
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

def calculate_bollinger_basis(klines, period=20):
    """
    計算布林帶中軌 (SMA20)，使用原始日線收盤價
    對應 Pine Script: basis = ta.sma(close, 20)
    回傳最新一根完整日線的中軌值
    """
    if not klines or len(klines) < period:
        return None
    # 取最後 period 根 K 棒的收盤價（用 index -1 是當根，對應 Pine 的 basis 當下值）
    closes = [k['close'] for k in klines[-period:]]
    return sum(closes) / period

def get_status_value(status_str):
    mapping = {"🔴": 0, "⚫": 1, "🟢": 2}
    return mapping.get(status_str, 3)

def get_bb_signal(ha_close, bb_basis):
    """
    比較 HA 收盤價 vs 布林帶中軌
    HA close > BB basis → 綠色 ▲
    HA close < BB basis → 紅色 ▼
    相等 → 灰色 —
    """
    if bb_basis is None:
        return "—"
    if ha_close > bb_basis:
        return "✅"
    elif ha_close < bb_basis:
        return "❌"
    else:
        return "—"

def format_price(price):
    if price is None:
        return "—"
    if price >= 10000:
        return f"{price:,.1f}"
    elif price >= 1000:
        return f"{price:,.2f}"
    elif price >= 100:
        return f"{price:.2f}"
    elif price >= 10:
        return f"{price:.3f}"
    elif price >= 1:
        return f"{price:.4f}"
    elif price >= 0.01:
        return f"{price:.5f}"
    elif price >= 0.0001:
        return f"{price:.6f}"
    else:
        return f"{price:.8f}"

# ==================== 4. 幣種清單 ====================

SYMBOLS_CONFIG = {
    "考試幣": ["ADA", "BTC", "DOGE", "ETH", "LINK", "LTC", "XLM", "XRP", "BCH", "ETC", "DOT", "FIL", "SOL", "BNB", "AVAX", "UNI", "ATOM", "AAVE", "ARB", "OP", "SUI", "PEPE", "SHIB", "WLD", "ORDI", "FLOKI", "BOME","1INCH", "AIXBT", "ALGO", "APT", "ASTER", "AXS", "BONK", "BRETT", "CAKE", "CHZ", "COMP", "CRV", "DEGEN", "DOG", "DYDX", "EGLD", "ENA", "ENJ", "FART", "FLR", "GALA", "GLM", "GMX", "GRASS", "GRT", "HBAR", "HYPE", "ICP", "IMX", "INJ", "IP", "JTO", "JUP", "KAITO", "KAS", "KAVA", "LDO", "LPT", "LRC", "MANA", "MANTA", "MEME", "MOODENG", "NEAR", "OKB", "ONDO", "PAXG", "PENDLE", "PENGU", "PNUT", "POL", "POPCAT", "PUMP", "PYTH", "RAY", "RENDER", "ROSE", "RPL", "RSR", "RUNE", "S", "SAND", "SEI", "SNX", "STRK", "STX", "SUSHI", "TAO", "TIA", "TON", "TRUMP", "TRX", "VET", "VIRTUAL", "W", "WIF", "XPL", "YFI", "ZEC"],
    "全部": ["A","A2Z","AAVE","ACE","ACH","ACT","ACU","ADA","AERGO","AERO","AEVO","AGIX","AGLD","AGT","AI","AI16Z","AIA","AIGENSYN","AIN","AIO","AIOT","AIXBT","AKE","AKT","ALCH","ALGO","ALICE","ALL","ALLO","ALPHA","ALPINE","ALT","ANIME","ANKR","ANT","ANTHROPIC","APE","API3","APR","APT","AR","ARB","ARC","ARIA","ARK","ARKM","ARPA","ASR","ASTER","ASTR","AT","ATA","ATH","ATOM","AUCTION","AUDIO","AVAX","AVNT","AWE","AXL","AXS","AZTEC","B","B3","BABY","BABYDOGE","BADGER","BAKE","BAL","BAN","BANANA","BANANAS31","BAND","BANK","BARD","BAS","BASED","BAT","BB","BCH","BDXN","BEAMX","BEAT","BEL","BERA","BICO","BIGTIME","BILL","BIO","BIRB","BLEND","BLESS","BLUAI","BLUR","BLZ","BNB","BNT","BNX","BOB","BOME","BOND","BONK","BR","BRENTOIL","BRETT","BREV","BROCCOLI","BSB","BSV","BTC","BTR","BTW","BULLA","C98","CAKE","CAR","CARV","CATI","CBRS","CC","CELO","CELR","CETUS","CFG","CFX","CHEEMS","CHIP","CHR","CHZ","CKB","CL","CLANKER","CLO","CNBARS","CNLX","CNWTMLL","COAI","COLLECT","COMBO","COMMON","COMP","COOKIE","COPPER","COTI","COW","CRO","CROSS","CRV","CTR","CUDIS","CVC","CVX","CYBER","CYS","DAM","DAR","DASH","DEAGENTAI","DEGEN","DIA","DODO","DOGE","DOGS","DOLO","DOT","DRIFT","DUSK","DYDX","DYM","EDGE","EDU","EGLD","EIGEN","ELSA","ENA","ENJ","ENS","ENSO","EOS","EPT","ESP","ESPORTS","ETC","ETH","ETHFI","ETHW","EUL","EVAA","F","FARTCOIN","FET","FF","FHE","FIGHT","FIL","FIO","FLM","FLOCK","FLOKI","FLOW","FLUID","FOGO","FOLKS","FORTH","FOUR","FOURTWO","FRAX","FRONT","FTM","FTT","FUN","FXS","GAL","GALA","GAS","GENIUS","GIGGLE","GLMR","GMT","GMX","GOAT","GPS","GRASS","GRIFFAIN","GRT","GTC","GUA","GUN","GWEI","H","HAEDAL","HANA","HBAR","HEMI","HFT","HIFI","HIGH","HIPPO","HMSTR","HNT","HOLO","HOME","HOOK","HUMA","HYPE","HYUNDAI","ICNT","ICP","ICX","ID","IDEX","IDOL","ILV","IMX","IN","INCH","INFQX","INIT","INJ","INX","IO","IOST","IOTA","IOTX","IP","IR","IRYS","JASMY","JCT","JELLYJELLY","JOE","JTO","JUP","KAIA","KAITO","KAS","KAT","KAVA","KERNEL","KGEN","KITE","KLAY","KMNO","KNC","LA","LAB","LAUNCHCOIN","LAYER","LDO","LEVER","LIGHT","LIGHTER","LINA","LINEA","LINK","LISTA","LIT","LOKA","LOOM","LPT","LQTY","LRC","LSK","LTC","LUNA2","LUNC","LYN","MAGIC","MAGMA","MANA","MANTA","MANTRA","MASK","MATIC","MAV","MAVIA","MBL","MBOX","MDT","ME","MEGA","MELANIA","MEME","MERL","MET","METIS","MEW","MINA","MITO","MKR","MLN","MMT","MNT","MON","MOODENG","MOVE","MOVR","MTL","MUBARAK","MYRO","MYX","NAORIS","NATGAS","NEAR","NEIROCTO","NEIROETH","NEO","NFP","NIGHT","NIL","NKN","NMR","NOM","NOT","NOWX","NTRN","NXPC","OCEAN","OFC","OG","OGN","OKB","OL","OM","OMG","OMNI","ON","ONDO","ONE","ONG","ONT","OP","OPEN","OPENAI","OPENEDEN","OPG","OPN","ORBS","ORCA","ORDER","ORDI","OXT","PARTI","PAXG","PENDLE","PENGU","PEOPLE","PEPE","PERP","PHA","PHB","PI","PIEVERSE","PIGGY","PIPPIN","PIXEL","PLAY","PLUME","PNUT","POL","POLYX","PONKE","POPCAT","PORT3","PORTAL","POWER","POWR","PRL","PROMPT","PROS","PROVE","PTB","PUFFER","PUMP","PUMPFUN","PYTH","Q","QNT","QNTX","QTUM","RAD","RARE","RATS","RAVE","RAY","RDNT","RECALL","REEF","RENDER","RESOLV","REZ","RHEA","RIF","RIVER","RLC","RLS","RNDR","ROBO","RON","ROSE","RPL","RSR","RSS3","RUNE","RVN","RVV","S","SAGA","SAHARA","SAND","SAPIEN","SATS","SCR","SCRT","SEI","SENT","SFP","SHELL","SHIB","SIREN","SKATE","SKHX","SKL","SKR","SKY","SKYAI","SLERF","SLP","SLX","SMSN","SNT","SNX","SOL","SOLV","SOMI","SOON","SOPH","SPACE","SPELL","SPK","SPORTFUN","SPX","SQD","SRM","SSV","STABLE","STAR","STARL","STBL","STEEM","STG","STMX","STO","STORJ","STPT","STRAX","STRK","STX","SUI","SUN","SUPER","SUSHI","SWARMS","SXP","SXT","SYRUP","SYS","T","TA","TAC","TAIKO","TAKE","TANSSI","TAO","THE","THETA","TIA","TLM","TNSR","TOKEN","TOMO","TON","TOSHI","TOWNS","TRADOOR","TRB","TREE","TRIA","TRU","TRUMP","TRUST","TRUTH","TRX","TST","TURBO","TURTLE","TUT","TWOZ","TWT","UAI","UB","UMA","UNFI","UNI","UP","US","USD","USDC","USDE","USELESS","USTC","USUAL","UXLINK","VANRY","VELODROME","VELVET","VET","VIDT","VINE","VIRTUAL","VOXEL","VRA","VVV","W","WAL","WAVES","WAXP","WCT","WET","WIF","WLD","WLFI","WOO","XAG","XAI","XAN","XAU","XAUT","XEC","XEM","XLM","XMR","XNO","XNY","XPD","XPIN","XPL","XPT","XRP","XTZ","XVG","XVS","YALA","YB","YFI","YGG","YZY","ZAMA","ZBT","ZEC","ZEN","ZEREBRO","ZEROG","ZEST","ZETA","ZIL","ZKC","ZKF","ZKP","ZKSYNC","ZORA","ZRC","ZRO","ZRX"]
}

# ==================== 5. 介面佈局 ====================

col_title, col_select, col_btn = st.columns([0.65, 0.22, 0.13])

with col_title:
    st.markdown("<div class='cyber-title'>Heikin-Ashi Monitor Terminal</div>", unsafe_allow_html=True)
    tw_now = datetime.now(TW_TZ).strftime('%H:%M:%S')
    st.markdown(f"<div class='cyber-subtitle'>CORE PROTOCOL ACTIVE | UPDATED: {tw_now} (TWN)</div>", unsafe_allow_html=True)

with col_select:
    selection = st.selectbox("", list(SYMBOLS_CONFIG.keys()), label_visibility="collapsed")

with col_btn:
    if st.button("⚡ 重新分析"):
        st.cache_data.clear()
        st.rerun()

# --- 執行分析循環 ---
symbols = SYMBOLS_CONFIG[selection]
placeholder = st.empty()
results = []

for i, symbol in enumerate(symbols):
    percent = int(((i + 1) / len(symbols)) * 100)
    placeholder.markdown(f"""
        <div id="loader-container">
            <span class="terminal-text">DEEP SCANNING: {symbol} {percent}%</span>
            <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: {percent}%;"></div></div>
        </div>
    """, unsafe_allow_html=True)
    
    k1d_raw = get_crypto_data(symbol, "1D")
    k4h_raw = get_crypto_data(symbol, "4H")
    
    if k1d_raw and k4h_raw:
        ha1d = calculate_heikin_ashi(k1d_raw)
        ha4h = calculate_heikin_ashi(k4h_raw)

        # ── 布林帶中軌 (SMA20)，使用原始日線收盤價計算 ──
        bb_basis_1d = calculate_bollinger_basis(k1d_raw, period=20)

        # ── 現價 (最新 4H 收盤) ──
        current_price = k4h_raw[-1]['close']

        # ── HA 當前日線收盤價 vs 布林帶中軌 ──
        # 對應 Pine: daybasis = request.security('','D', basis, lookahead_on)
        # 這裡直接用日線資料，ha1d[-1] 即當根平均K的收盤價
        ha_close_1d = ha1d[-1]['close']
        bb_signal = get_bb_signal(ha_close_1d, bb_basis_1d)
        
        # 原有 HA 顏色判斷
        p1d = "🟢" if ha1d[-2]['close'] > ha1d[-2]['open'] else ("🔴" if ha1d[-2]['close'] < ha1d[-2]['open'] else "⚫")
        c1d = "🟢" if ha1d[-1]['close'] > ha1d[-1]['open'] else ("🔴" if ha1d[-1]['close'] < ha1d[-1]['open'] else "⚫")
        p4h = "🟢" if ha4h[-2]['close'] > ha4h[-2]['open'] else ("🔴" if ha4h[-2]['close'] < ha4h[-2]['open'] else "⚫")
        c4h = "🟢" if ha4h[-1]['close'] > ha4h[-1]['open'] else ("🔴" if ha4h[-1]['close'] < ha4h[-1]['open'] else "⚫")
        
        results.append({
            "幣種": symbol,
            "現價": format_price(current_price),
            "BB日中軌": format_price(bb_basis_1d),
            "BB中軌": bb_signal,
            "1D前": p1d,
            "1D當": c1d,
            "4H前": p4h,
            "4H當": c4h,
            "val": (get_status_value(p1d), get_status_value(c1d), get_status_value(p4h), get_status_value(c4h)),
            "_price": current_price,
            "_bb1d": bb_basis_1d if bb_basis_1d else 0,
        })

# 清除進度條並顯示表格
placeholder.empty()

if results:
    df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])

    # ── 現價顏色：現價 > 日線BB中軌 → 綠；< → 紅 ──
    price_styles = []
    for _, row in df.iterrows():
        p, b = row["_price"], row["_bb1d"]
        if b > 0 and p > b:
            price_styles.append('color: #22c55e; font-weight: bold;')
        elif b > 0 and p < b:
            price_styles.append('color: #ef4444; font-weight: bold;')
        else:
            price_styles.append('')

    display_df = df.drop(columns=["_price", "_bb1d"])

    def color_logic(v):
        if v == '🟢': return 'color: #22c55e; font-weight: bold;'
        elif v == '🔴': return 'color: #ef4444; font-weight: bold;'
        elif v == '✅': return ''
        elif v == '❌': return ''
        return 'color: #64748b;'

    def color_price(col):
        return pd.Series(price_styles, index=col.index)

    col_cfg = {
        "幣種":    st.column_config.TextColumn("幣種",    width=80),
        "現價":    st.column_config.TextColumn("現價",    width=100),
        "BB中軌": st.column_config.TextColumn("BB中軌", width=100),
        "BB中軌":  st.column_config.TextColumn("BB中軌",  width=70),
        "1D前":    st.column_config.TextColumn("1D前",    width=60),
        "1D當":    st.column_config.TextColumn("1D當",    width=60),
        "4H前":    st.column_config.TextColumn("4H前",    width=60),
        "4H當":    st.column_config.TextColumn("4H當",    width=60),
    }

    styled = (
        display_df.style
        .map(color_logic, subset=["1D前", "1D當", "4H前", "4H當", "BB中軌"])
        .apply(color_price, subset=["現價"], axis=0)
    )

    st.dataframe(
        styled,
        use_container_width=False,
        column_config=col_cfg,
        height=(len(display_df) + 1) * 35 + 3,
        hide_index=True
    )

st.toast(f"✅ {selection} SYNC COMPLETE.", icon="⚡")
