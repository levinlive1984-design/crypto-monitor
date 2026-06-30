import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone, timedelta
import time
import html
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import streamlit.components.v1 as components
from get import write_index_html, sync_index_to_github

# ==================== 0. matplotlib 中文字型設定 ====================
# 自動從系統已安裝字型中找一個支援中文的字型，避免圖表中文顯示成方塊 □□□
_CJK_FONT_CANDIDATES = [
    "Noto Sans CJK TC", "Noto Sans CJK SC", "Noto Sans TC", "Noto Sans SC",
    "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "PingFang SC",
    "Heiti TC", "SimHei", "WenQuanYi Zen Hei", "Arial Unicode MS",
]
_installed_fonts = {f.name for f in fm.fontManager.ttflist}
_chosen_font = next((f for f in _CJK_FONT_CANDIDATES if f in _installed_fonts), None)

if _chosen_font:
    plt.rcParams["font.sans-serif"] = [_chosen_font]
else:
    # 系統完全沒有中文字型時，嘗試載入隨包附帶/下載的 Noto Sans TC
    import os
    _font_path = "/tmp/NotoSansTC-Regular.ttf"
    try:
        if not os.path.exists(_font_path):
            import urllib.request
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf",
                _font_path,
            )
        fm.fontManager.addfont(_font_path)
        _chosen_font = fm.FontProperties(fname=_font_path).get_name()
        plt.rcParams["font.sans-serif"] = [_chosen_font]
    except Exception:
        # 下載失敗則維持預設字型（中文仍可能顯示為方塊，但不影響程式執行）
        pass

plt.rcParams["axes.unicode_minus"] = False

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
        color: #FFEB3B;
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

    /* 隱藏 data_editor / dataframe 標題列的排序箭頭與過濾圖示 */
    [data-testid="stDataEditor"] .ag-header-cell-label .ag-header-cell-text::after,
    [data-testid="stDataFrame"] .ag-header-cell-label .ag-header-cell-text::after {
        content: none !important;
    }
    .ag-header-cell-menu-button,
    .ag-sort-indicator {
        display: none !important;
    }

    /* 浮動操作抽屜：選幣 + 恢復預設 + 清除勾選，預設收在畫面右側外，
       點擊 FAB 後滑出，無時無刻都浮動在畫面上 */
    .st-key-floating_action_bar {
        position: fixed;
        top: 175px;
        right: 0px;
        z-index: 99999;
        width: 150px;
        padding: 14px 10px 10px 10px;
        background: rgba(15, 23, 42, 0.96);
        border: 1px solid rgba(19, 242, 26, 0.45);
        border-radius: 10px 0 0 10px;
        box-shadow: -4px 4px 20px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(6px);
        transform: translateX(150px);
        transition: transform 0.3s cubic-bezier(0.4,0,0.2,1);
    }
    .st-key-floating_action_bar.drawer-open {
        transform: translateX(0);
    }
    .st-key-floating_action_bar [data-testid="stButton"] {
        margin-bottom: 5px;
    }
    .st-key-floating_action_bar [data-testid="stButton"]:last-child {
        margin-bottom: 0;
    }
    .st-key-floating_action_bar .stButton>button {
        font-size: 10px !important;
        padding: 3px 6px !important;
        line-height: 1.4 !important;
    }
    /* 浮動 FAB 按鈕（永遠顯示，用於開關抽屜） */
    #panel-fab {
        position: fixed;
        top: 175px;
        right: 18px;
        z-index: 999999;
        width: 42px;
        height: 42px;
        border-radius: 10px;
        background: rgba(15, 23, 42, 0.96);
        border: 1px solid rgba(19, 242, 26, 0.6);
        box-shadow: 0 0 10px rgba(19, 242, 26, 0.25), 3px 3px 0px rgba(0,0,0,0.4);
        color: #13f21a;
        font-size: 19px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease;
        font-family: 'Courier New', Courier, monospace;
    }
    #panel-fab:hover {
        background: rgba(19, 242, 26, 0.15);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# ==================== 2.1 浮動 FAB：開關「選幣／恢復預設／清除勾選」抽屜 ====================
def inject_panel_fab():
    components.html(
        """
        <script>
        (function() {
            function inject() {
                try {
                    var p = window.parent.document;

                    // 清除舊版 FAB，避免重複 rerun 後疊加
                    var old = p.getElementById('panel-fab');
                    if (old) old.remove();

                    var fab = p.createElement('div');
                    fab.id = 'panel-fab';
                    fab.innerHTML = '🎛️';
                    fab.title = '選幣 / 恢復預設 / 清除勾選';

                    // 還原上次的開關狀態（避免按鈕觸發 rerun 後抽屜被重置成關閉）
                    var drawerNow = p.querySelector('.st-key-floating_action_bar');
                    if (drawerNow && window.parent.sessionStorage.getItem('panelDrawerOpen') === '1') {
                        drawerNow.classList.add('drawer-open');
                    }

                    fab.addEventListener('click', function() {
                        var drawer = p.querySelector('.st-key-floating_action_bar');
                        if (drawer) {
                            drawer.classList.toggle('drawer-open');
                            var isOpen = drawer.classList.contains('drawer-open');
                            window.parent.sessionStorage.setItem('panelDrawerOpen', isOpen ? '1' : '0');
                        }
                    });

                    p.body.appendChild(fab);
                } catch (e) {
                    console.error('[panel-fab] inject failed:', e);
                }
            }

            if (window.parent.document.body) {
                inject();
            } else {
                window.parent.addEventListener('load', inject);
            }
            setTimeout(inject, 300);
        })();
        </script>
        """,
        height=0,
        width=0,
    )

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

# --- 圖表篩選狀態（不再使用搜尋框，改由「🎯 選幣」與「📊 恢復預設」按鈕直接控制） ---
if "applied_search" not in st.session_state:
    st.session_state.applied_search = ""

if "editor_version" not in st.session_state:
    st.session_state.editor_version = 0

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

        # ── HA 日線收盤價 (用於新表格欄位與圖表) ──
        ha_close_curr = ha1d[-1]['close']
        ha_close_prev = ha1d[-2]['close'] if len(ha1d) >= 2 else ha_close_curr

        bb_signal = get_bb_signal(ha_close_curr, bb_basis_1d)
        
        # 原有 HA 顏色判斷（1D前、1D當、4H前、4H當）
        p1d = "🟢" if ha1d[-2]['close'] > ha1d[-2]['open'] else ("🔴" if ha1d[-2]['close'] < ha1d[-2]['open'] else "⚫")
        c1d = "🟢" if ha1d[-1]['close'] > ha1d[-1]['open'] else ("🔴" if ha1d[-1]['close'] < ha1d[-1]['open'] else "⚫")
        p4h = "🟢" if ha4h[-2]['close'] > ha4h[-2]['open'] else ("🔴" if ha4h[-2]['close'] < ha4h[-2]['open'] else "⚫")
        c4h = "🟢" if ha4h[-1]['close'] > ha4h[-1]['open'] else ("🔴" if ha4h[-1]['close'] < ha4h[-1]['open'] else "⚫")
        
        # 計算現價 vs BB中軌的百分比 (維持原有「差%」)
        if bb_basis_1d and bb_basis_1d > 0:
            bb_pct = ((current_price - bb_basis_1d) / bb_basis_1d) * 100
            # st.data_editor 不支援 Styler 顏色樣式，改用 🟢/🔴 圓點前綴來呈現正負色彩
            pct_dot = "🟢" if bb_pct > 0 else ("🔴" if bb_pct < 0 else "⚫")
            bb_pct_str = f"{pct_dot} {bb_pct:+.2f}%"
            abs_dev = abs(bb_pct)
            abs_dev_str = f"{abs_dev:.2f}%"
        else:
            bb_pct = 0
            bb_pct_str = "—"
            abs_dev = 999.0
            abs_dev_str = "—"
        
        # 計算最近 20 根 HA 收盤價（每根用「當天」的 BB中軌 計算 % 偏差）
        ha_last20 = ha1d[-20:]
        ha_closes_last20 = [k['close'] for k in ha_last20]
        ha_opens_last20 = [k['open'] for k in ha_last20]
        ha_times_last20 = [k['time'] for k in ha_last20]

        # 取得原始日線收盤價序列（用來計算每一天的 SMA20）
        raw_closes = [k['close'] for k in k1d_raw]

        ha_pct_series = []
        for i in range(len(ha_last20)):
            # 對應到 raw_closes 的結束位置（由舊到新）
            end_idx = len(raw_closes) - (len(ha_last20) - 1 - i)
            if end_idx >= 20:
                sma20 = sum(raw_closes[end_idx-20 : end_idx]) / 20
                ha_c = ha_closes_last20[i]
                pct = (ha_c - sma20) / sma20 * 100 if sma20 > 0 else 0.0
                ha_pct_series.append(pct)
            else:
                ha_pct_series.append(0.0)

        ha_curr_pct = ha_pct_series[-1] if ha_pct_series else 0.0
        
        results.append({
            "幣種": symbol,
            "現價": format_price(current_price),
            "差%": bb_pct_str,
            "BB日中軌": format_price(bb_basis_1d),
            "BB中軌": bb_signal,
            "1D前": p1d,
            "1D當": c1d,
            "4H前": p4h,
            "4H當": c4h,
            "距離中軌%": abs_dev_str,   # 保留新欄位，方便排序找接近中軌的幣種
            "_price": current_price,
            "_bb1d": bb_basis_1d if bb_basis_1d else 0,
            "_bb_pct": bb_pct,
            "_abs_dev": abs_dev,
            "val": (get_status_value(p1d), get_status_value(c1d), get_status_value(p4h), get_status_value(c4h)),
            "_ha_pct_series": ha_pct_series,
            "_ha_curr_pct": ha_curr_pct,
            "_ha_opens_last20": ha_opens_last20,
            "_ha_closes_last20": ha_closes_last20,
            "_ha_times_last20": ha_times_last20,
        })

# 清除進度條並顯示表格
placeholder.empty()

if results:
    # 表格使用原本的排序方式（依 1D前/1D當/4H前/4H當 的狀態排序）
    df = pd.DataFrame(results).sort_values(by="val").drop(columns=["val"])

    # 圖表區專用的過濾結果（支援多幣種，用「、」或「,」分隔）
    # 注意：這裡讀取的是「按下恢復預設按鈕後」套用的 applied_search，
    # 而不是輸入框即時的文字，避免每打一個字就重新畫圖表。
    active_search = st.session_state.get("applied_search", "")
    if active_search:
        search_terms = [t.strip().upper() for t in active_search.replace("、", ",").split(",") if t.strip()]
        if search_terms:
            chart_results = [r for r in results if any(term in r["幣種"].upper() for term in search_terms)]
        else:
            chart_results = results
    else:
        chart_results = results

    # ── 現價顏色：現價 > 日線BB中軌 → 綠；< → 紅 ──
    price_styles = []
    pct_styles = []
    for _, row in df.iterrows():
        p, b, pct = row["_price"], row["_bb1d"], row["_bb_pct"]
        
        # 現價樣式
        if b > 0 and p > b:
            price_styles.append('color: #22c55e; font-weight: bold;')
        elif b > 0 and p < b:
            price_styles.append('color: #ef4444; font-weight: bold;')
        else:
            price_styles.append('')
        
        # 差%顏色：正數→綠；負數→紅
        if pct > 0:
            pct_styles.append('color: #22c55e; font-weight: bold;')
        elif pct < 0:
            pct_styles.append('color: #ef4444; font-weight: bold;')
        else:
            pct_styles.append('')

    # 準備帶勾選框的表格（移除「距離中軌%」）
    display_df = df.drop(columns=["_price", "_bb1d", "_bb_pct", "_abs_dev", "_ha_pct_series", "_ha_curr_pct", "_ha_opens_last20", "_ha_closes_last20", "_ha_times_last20", "距離中軌%"]).copy()
    display_df.insert(0, "選取", False)  # 最前面加入勾選欄位

    def color_logic(v):
        if v in ['🟢', '✅']: return 'color: #22c55e; font-weight: bold;'
        elif v in ['🔴', '❌']: return 'color: #ef4444; font-weight: bold;'
        return 'color: #64748b;'

    def color_price(col):
        return pd.Series(price_styles, index=col.index)
    
    def color_pct(col):
        return pd.Series(pct_styles, index=col.index)

    col_cfg = {
        "選取":    st.column_config.CheckboxColumn("選取", width=50),
        "幣種":    st.column_config.TextColumn("幣種",    width=75),
        "現價":    st.column_config.TextColumn("現價",    width=95),
        "差%":     st.column_config.TextColumn("差%",     width=85),
        "BB日中軌": st.column_config.TextColumn("BB日中軌", width=95),
        "BB中軌":  st.column_config.TextColumn("BB中軌",  width=65),
        "1D前":    st.column_config.TextColumn("1D前",    width=55),
        "1D當":    st.column_config.TextColumn("1D當",    width=55),
        "4H前":    st.column_config.TextColumn("4H前",    width=55),
        "4H當":    st.column_config.TextColumn("4H當",    width=55),
    }

    styled = (
        display_df.style
        .map(color_logic, subset=["BB中軌"])
        .apply(color_price, subset=["現價"], axis=0)
        .apply(color_pct, subset=["差%"], axis=0)
    )

    # 表格全寬顯示 + 浮動操作面板（捲動表格時仍固定在畫面右側）
    edited_df = st.data_editor(
        styled,
        use_container_width=True,
        column_config=col_cfg,
        height=(len(display_df) + 1) * 34 + 5,
        hide_index=True,
        key=f"coin_selector_{st.session_state.editor_version}"
    )

    with st.container(key="floating_action_bar"):
        st.markdown("<div style='color:#13f21a;font-size:11px;font-weight:bold;margin-bottom:6px;'>🎛️ 操作面板</div>", unsafe_allow_html=True)
        pick_clicked = st.button("🎯 選幣", type="primary", use_container_width=True)
        show_all_clicked = st.button("📊 恢復預設", use_container_width=True)
        clear_clicked = st.button("🗑️ 清除勾選", use_container_width=True)

    # 注入永遠浮動的 FAB 按鈕，點擊即可滑開/收起上方抽屜
    inject_panel_fab()

    # 「🎯 選幣」：把目前勾選的幣種直接套用，圖表立刻只顯示這些幣種
    if pick_clicked:
        selected = edited_df[edited_df.get("選取", False) == True]["幣種"].tolist() if isinstance(edited_df, pd.DataFrame) else []
        if selected:
            st.session_state.applied_search = "、".join(selected)
            st.toast(f"🎯 已選擇 {len(selected)} 個幣種", icon="✅")
            st.rerun()
        else:
            st.toast("請先勾選幣種", icon="⚠️")

    # 「📊 恢復預設」：恢復原廠設定，顯示全部幣種的圖表
    if show_all_clicked:
        st.session_state.applied_search = ""
        st.toast("📊 已恢復顯示全部幣種圖表", icon="🔄")
        st.rerun()

    # 「🗑️ 清除勾選」：重置所有勾選（透過更換 data_editor key 強制清空）
    if clear_clicked:
        st.session_state.editor_version += 1
        st.toast("🗑️ 已清除所有勾選", icon="✅")
        st.rerun()

    # ==================== 各幣種 最近20根 HA 收盤價 vs BB中軌 % 偏差圖 ====================
    st.markdown("---")
    st.markdown("### 📈 最近 20 根 HA 收盤價 vs BB中軌 % 偏差走勢圖")

    # --- 圖表排序選單 ---
    sort_option = st.selectbox(
        "圖表排序方式",
        options=[
            "依「距離中軌%」距離近的排序（預設）",
            "依目前的日K收盤價 > 開盤價排序（多頭優先）",
            "依目前的日K收盤價 < 開盤價排序（空頭優先）",
            "依幣種英文字母順序排序"
        ],
        index=0
    )

    # 根據選擇的排序方式處理圖表列表
    if sort_option == "依「距離中軌%」距離近的排序（預設）":
        sorted_chart_results = sorted(chart_results, key=lambda x: x["_abs_dev"])
    elif sort_option == "依目前的日K收盤價 > 開盤價排序（多頭優先）":
        sorted_chart_results = sorted(chart_results, key=lambda x: 0 if (x.get("_ha_closes_last20") and x.get("_ha_opens_last20") and x["_ha_closes_last20"][-1] > x["_ha_opens_last20"][-1]) else 1)
    elif sort_option == "依目前的日K收盤價 < 開盤價排序（空頭優先）":
        sorted_chart_results = sorted(chart_results, key=lambda x: 0 if (x.get("_ha_closes_last20") and x.get("_ha_opens_last20") and x["_ha_closes_last20"][-1] < x["_ha_opens_last20"][-1]) else 1)
    else:  # 依幣種英文字母順序排序
        sorted_chart_results = sorted(chart_results, key=lambda x: x["幣種"])

    # 直接顯示所有圖表（已移除 checkbox）
    plot_results = sorted_chart_results

    # ==================== 輸出靜態 GitHub Pages index.html + 回寫 GitHub ====================
    # main.py 只負責呼叫；實際 HTML / 圖表輸出與 GitHub 同步邏輯集中在 get.py，方便後續維護。
    def _secret(name, default=""):
        try:
            return st.secrets.get(name, default)
        except Exception:
            return default

    github_repo = _secret("GITHUB_REPO", "levinlive1984-design/crypto-monitor")
    github_branch = _secret("GITHUB_BRANCH", "main")
    github_pages_path = _secret("GITHUB_PAGES_PATH", "docs/index.html")
    github_token = _secret("GITHUB_TOKEN", "")
    auto_sync_github_pages = str(_secret("AUTO_SYNC_GITHUB_PAGES", "true")).lower() in ["1", "true", "yes", "y", "on"]

    def _github_pages_base_url(repo: str) -> str:
        """依 GitHub repo 推出 GitHub Pages base URL。"""
        try:
            owner, repo_name = str(repo).strip().split("/", 1)
            if repo_name.lower() == f"{owner.lower()}.github.io":
                return f"https://{owner}.github.io/"
            return f"https://{owner}.github.io/{repo_name}/"
        except Exception:
            return ""

    def _render_sync_status(messages: list[tuple[str, str]], default_open: bool = False) -> None:
        """使用 Streamlit 原生 expander 顯示同步狀態，避免 raw HTML 被 Markdown 誤判成程式碼區塊。"""
        if not messages:
            return
        with st.expander("靜態頁 / GitHub Pages 同步狀態　點開查看", expanded=default_open):
            for icon, text in messages:
                st.markdown(
                    f"""
                    <div style="display:flex;gap:8px;align-items:flex-start;padding:4px 0;border-bottom:1px solid rgba(148,163,184,.10);font-size:11px;line-height:1.45;">
                        <span style="min-width:18px;">{html.escape(icon)}</span>
                        <span style="color:#cbd5e1;">{html.escape(text)}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    def _render_pages_links(repo: str) -> None:
        """在 Streamlit 畫面顯示可直接點擊的 GitHub Pages 檔案連結。"""
        base_url = _github_pages_base_url(repo)
        if not base_url:
            return
        links = {
            "index.html｜圖表頁": base_url + "index.html",
            "snapshot.json｜正式 JSON": base_url + "snapshot.json",
            "snapshot_pretty.txt｜AI 快讀 JSON": base_url + "snapshot_pretty.txt",
            "latest_signals.txt｜候選摘要": base_url + "latest_signals.txt",
        }
        link_html = "".join(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'style="display:inline-block;margin:2px 5px 2px 0;padding:3px 6px;border:1px solid rgba(19,242,26,.50);border-radius:999px;color:#13f21a;text-decoration:none;background:rgba(15,23,42,.50);font-size:10px;line-height:1.15;">{label}</a>'
            for label, url in links.items()
        )
        st.markdown(
            f"""
            <div style="margin:6px 0 10px 0;padding:7px 9px;border:1px solid rgba(19,242,26,.32);border-radius:9px;background:rgba(15,23,42,.70);">
                <div style="color:#cbd5e1;font-weight:700;margin-bottom:4px;font-size:11px;">🔗 GitHub Pages 快速連結</div>
                <div style="line-height:1.55;">{link_html}</div>
                <div style="color:#94a3b8;font-size:10px;margin-top:4px;">剛回寫 GitHub 時，GitHub Pages 可能需要 30–120 秒刷新。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    sync_messages = []
    try:
        # 先在 Streamlit runtime 產生本機暫存版 docs/index.html。
        index_path = write_index_html(
            df=df,
            plot_results=plot_results,
            selection=selection,
            sort_option=sort_option,
            output_dir="docs",
            title="HA Crypto Terminal",
        )
        sync_messages.append(("📄", f"已產生暫存靜態頁：{index_path}"))

        # Streamlit Cloud 的 docs/index.html 不會自己回寫 GitHub；這段會透過 GitHub API commit 回 repo。
        if auto_sync_github_pages and github_token:
            sync_result = sync_index_to_github(
                df=df,
                plot_results=plot_results,
                selection=selection,
                sort_option=sort_option,
                repo=github_repo,
                token=github_token,
                branch=github_branch,
                repo_path=github_pages_path,
                output_dir="docs",
                title="HA Crypto Terminal",
            )
            if sync_result.get("status") == "skipped":
                sync_messages.append(("✅", "GitHub Pages 已是同一份圖表快照，略過重複 commit。"))
            else:
                sync_messages.append(("🚀", f"已回寫 GitHub Pages：{github_pages_path}｜commit {str(sync_result.get('commit_sha', ''))[:8]}"))
        elif not github_token:
            sync_messages.append(("⚠️", "尚未設定 GITHUB_TOKEN，所以只產生 Streamlit 暫存 index.html，尚未回寫 GitHub Pages。"))

        # 狀態收進可展開小頁籤；連結維持直接顯示，但縮小。
        _render_sync_status(sync_messages, default_open=False)
        _render_pages_links(github_repo)

    except Exception as exc:
        st.warning(f"⚠️ 靜態頁 / GitHub Pages 同步失敗：{exc}")

    n_cols = 2 if len(plot_results) > 4 else 3
    chart_cols = st.columns(n_cols)

    for idx, r in enumerate(plot_results):
        with chart_cols[idx % n_cols]:
            with st.container(border=True):
                ha_series = r.get("_ha_pct_series", [0.0])
                curr_pct = r.get("_ha_curr_pct", 0.0)
                ha_opens = r.get("_ha_opens_last20", [])
                ha_closes = r.get("_ha_closes_last20", [])
                ha_times = r.get("_ha_times_last20", [])

                # 標題
                st.markdown(
                    f"**{r['幣種']}**　現價 {r['現價']}　|　目前偏離 {r['差%']}　|　4H前 {r.get('4H前','—')} 4H當 {r.get('4H當','—')}"
                )

                # 建立 20期走勢圖
                fig, ax = plt.subplots(figsize=(5.8, 2.9), facecolor='#1e293b')
                ax.set_facecolor('#1e293b')

                n = len(ha_series)
                x = list(range(n))
                y = ha_series

                # === 產生日期標籤 (台灣時間) ===
                if ha_times:
                    last_ts = ha_times[-1] / 1000.0
                    last_date = datetime.fromtimestamp(last_ts, tz=TW_TZ).date()
                    date_labels = [(last_date - timedelta(days=n-1-i)).strftime('%m/%d') for i in range(n)]
                else:
                    date_labels = [str(i) for i in range(n)]

                # === 依每根 K 的方向著色階梯線 ===
                # 黃色 (#FFEB3B) = 當日 HA 收盤 > 開盤 (多頭)
                # 紫色 (#B39DDB) = 當日 HA 收盤 < 開盤 (空頭)
                for i in range(n-1):
                    if i < len(ha_opens) and i < len(ha_closes):
                        is_bull = ha_closes[i] > ha_opens[i]
                        seg_color = '#FFEB3B' if is_bull else '#B39DDB'
                    else:
                        seg_color = '#22c55e' if curr_pct >= 0 else '#ef4444'

                    # 畫這一段 step
                    ax.step([x[i], x[i+1]], [y[i], y[i+1]], where='post', color=seg_color, linewidth=2.3)

                # 目前最新點特別標註 (白色外框)
                if n > 0:
                    ax.plot(x[-1], y[-1], 'o', color='white', markersize=8, zorder=7)
                    final_color = '#FFEB3B' if (ha_closes and ha_opens and ha_closes[-1] > ha_opens[-1]) else '#B39DDB'
                    ax.plot(x[-1], y[-1], 'o', color=final_color, markersize=4.5, zorder=8)

                # 中軌基準線 (改為淡灰色)
                ax.axhline(0, color='#64748b', linestyle='--', linewidth=1.5, label='BB中軌 (0%)')

                # 區域填色 (保持原本邏輯)
                ax.fill_between(x, y, 0, where=(np.array(y) >= 0), alpha=0.12, color='#22c55e', step='post', zorder=1)
                ax.fill_between(x, y, 0, where=(np.array(y) < 0), alpha=0.12, color='#ef4444', step='post', zorder=1)

                # 給 Y 軸留一些空間，避免最新 % 數字被切掉
                if y:
                    y_min = min(y) - 4
                    y_max = max(y) + 4
                    ax.set_ylim(y_min, y_max)

                # 設定
                ax.set_xlim(-0.5, n - 0.5)
                ax.set_xticks(x[::2])  # 每隔一天顯示日期，避免太密
                ax.set_xticklabels(date_labels[::2], rotation=45, ha='right', fontsize=7, color='#94a3b8')
                ax.set_ylabel('乖離中軌%', fontsize=9, color='#94a3b8')
                ax.set_title(f"日線中軌 = {r['BB日中軌']}", fontsize=9, color='#cbd5e1', pad=4)

                ax.tick_params(colors='#94a3b8', labelsize=7)
                ax.grid(True, linestyle=':', alpha=0.35, color='#475569')
                for spine in ax.spines.values():
                    spine.set_color('#475569')
                    spine.set_alpha(0.6)

                # 根據正負號動態放置 % 標註
                # 正數放在上方，負數放在下方
                offset_y = 10 if curr_pct >= 0 else -14
                va_align = 'bottom' if curr_pct >= 0 else 'top'

                ax.annotate(f'{curr_pct:+.2f}%', 
                            xy=(x[-1], y[-1]), 
                            xytext=(0, offset_y),
                            textcoords='offset points', 
                            ha='center', 
                            va=va_align,
                            fontsize=8, 
                            color=final_color, 
                            fontweight='bold')

                st.pyplot(fig, clear_figure=True, use_container_width=True)

st.toast(f"✅ {selection} SYNC COMPLETE.", icon="⚡")
