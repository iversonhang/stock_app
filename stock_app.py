import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import io # Added for robust table parsing

# --- CONFIGURATION ---
st.set_page_config(page_title="Wall St. Pulse", page_icon="📈", layout="wide")

# --- SESSION STATE INITIALIZATION ---
if 'navigation' not in st.session_state:
    st.session_state['navigation'] = "Global Headlines"
if 'target_ticker' not in st.session_state:
    st.session_state['target_ticker'] = None
if 'stock_query' not in st.session_state:
    st.session_state.stock_query = ""

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stExpander { border: 1px solid #f0f2f6; border-radius: 8px; margin-bottom: 10px; background-color: #ffffff; }
    .signal-box { padding: 15px; border-radius: 10px; margin-bottom: 20px; text-align: center; font-weight: bold; font-size: 24px; }
    .buy { background-color: #e6fffa; color: #00bfa5; border: 1px solid #00bfa5; }
    .sell { background-color: #fff5f5; color: #ff5252; border: 1px solid #ff5252; }
    .hold { background-color: #f0f2f6; color: #555; border: 1px solid #ccc; }
    div[data-testid="stButton"] button {
        padding: 0.25rem 0.75rem;
        font-size: 0.8rem;
    }
    .ticker-tag { 
        background-color: #f0f2f6; color: #31333F; padding: 2px 8px; border-radius: 4px; 
        font-size: 12px; font-weight: bold; border: 1px solid #d6d6d6; margin-right: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def go_to_ticker(ticker):
    """Callback to switch page and set ticker"""
    st.session_state['target_ticker'] = ticker
    st.session_state['navigation'] = "Stock Analyst Pro"

@st.cache_data(ttl=3600)
def search_symbol(query):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        results = []
        if 'quotes' in data:
            for quote in data['quotes']:
                if 'symbol' in quote and 'shortname' in quote:
                    results.append({'symbol': quote['symbol'], 'name': quote['shortname'], 'exch': quote.get('exchange', 'N/A')})
        return results
    except: return []

@st.cache_data(ttl=300) 
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.info if 'symbol' in stock.info else None
    except: return None

@st.cache_data(ttl=300)
def get_stock_history(ticker, period):
    return yf.Ticker(ticker).history(period=period)

@st.cache_data(ttl=300)
def get_financials_data(ticker):
    stock = yf.Ticker(ticker)
    return stock.financials, stock.balance_sheet, stock.cashflow

@st.cache_data(ttl=300)
def get_ticker_news(ticker):
    try:
        return yf.Ticker(ticker).news
    except: return []

def format_number(num):
    if num:
        if num > 1e12: return f"{num/1e12:.2f}T"
        if num > 1e9: return f"{num/1e9:.2f}B"
        if num > 1e6: return f"{num/1e6:.2f}M"
        return f"{num:.2f}"
    return "N/A"

# --- MARKET SCANNER FUNCTIONS ---

@st.cache_data(ttl=3600)
def get_sp500_tickers():
    try:
        # Use requests with headers to bypass Wikipedia block
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        response = requests.get(url, headers=headers)
        # Use io.StringIO to avoid parser warnings
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        
        # Replace dot with hyphen for Yahoo Finance compatibility (e.g. BRK.B -> BRK-B)
        tickers = df['Symbol'].apply(lambda x: x.replace('.', '-')).tolist()
        return tickers
    except Exception as e:
        # Fallback list if scrape completely fails
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK-B', 'V', 'JNJ', 'JPM', 'XOM']

@st.cache_data(ttl=3600)
def get_market_scanner_data():
    tickers = get_sp500_tickers()
    
    # 1. BATCH DOWNLOAD (Fast)
    data = yf.download(tickers, period="6mo", interval="1d", group_by='ticker', threads=True)
    
    rsi_candidates = []
    
    # 2. CALCULATE RSI
    for ticker in tickers:
        try:
            # Handle MultiIndex DataFrame from yfinance
            if isinstance(data.columns, pd.MultiIndex):
                if ticker in data.columns.get_level_values(0):
                    df = data[ticker].copy()
                else: continue
            else:
                df = data
            
            if len(df) < 15: continue
            
            # RSI Calculation
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            latest_rsi = df['RSI'].iloc[-1]
            latest_price = df['Close'].iloc[-1]
            
            if not pd.isna(latest_rsi):
                rsi_candidates.append({
                    "Ticker": ticker,
                    "Price": latest_price,
                    "RSI": latest_rsi
                })
        except: continue
            
    # 3. FILTER LOGIC
    def get_verified_list(candidates, is_oversold):
        # Sort by RSI
        sorted_list = sorted(candidates, key=lambda x: x['RSI'], reverse=not is_oversold)
        
        verified = []
        for item in sorted_list:
            if len(verified) >= 10: break 
            
            # Strict RSI Filters
            if is_oversold and item['RSI'] >= 30: continue
            if not is_oversold and item['RSI'] <= 70: continue
            
            try:
                # Fetch Market Cap (Lazy Loading)
                info = yf.Ticker(item['Ticker']).info
                mkt_cap = info.get('marketCap', 0) or 0
                
                # Filter > 10 Million
                if mkt_cap > 10_000_000:
                    item['MarketCap'] = mkt_cap
                    verified.append(item)
            except:
                continue
        return pd.DataFrame(verified)

    oversold_df = get_verified_list(rsi_candidates, is_oversold=True)
    overbought_df = get_verified_list(rsi_candidates, is_oversold=False)
    
    return oversold_df, overbought_df, len(tickers)

# --- TECHNICAL ANALYSIS FUNCTIONS ---

def calculate_technicals(df):
    if len(df) < 50: return None 
    
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    rsv = (df['Close'] - low_min) / (high_max - low_min) * 100
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_chart_with_gemini_cached(ticker, _df_monthly_summary, _latest_indicators, api_key, model_name):
    if not api_key: return None

    price_sequence = _df_monthly_summary
    
    tech_data = f"""
    Ticker: {ticker} 
    {_latest_indicators}
    
    Monthly Price Data (Use these dates for coordinates):
    {price_sequence}
    """

    try:
        genai.configure(api_key=api_key)
        generation_config = genai.GenerationConfig(temperature=0.0, response_mime_type="application/json")
        model = genai.GenerativeModel(model_name, generation_config=generation_config)
        
        prompt = f"""
        Act as a technical analyst for {ticker}.
        {tech_data}
        
        TASK:
        1. Analyze the MONTHLY data for patterns (Staircases, Triangles, Flags, Wedges, Double Top/Bottom, Head & Shoulders, Cup & Handle).
        2. If MULTIPLE patterns exist, use RSI/KDJ to pick the BEST one.
        3. If NO pattern, use RSI/KDJ for the signal (Overbought=SELL, Oversold=BUY).
        
        IMPORTANT: DRAW THE PATTERN.
        Identify up to 2 key trendlines (e.g. Support and Resistance) that define the pattern found.
        Return the Start and End points (Date and Price) for each line. Ensure the dates strictly match the "Date" field in the data provided.

        Output strictly valid JSON:
        {{
            "signal": "BUY",
            "pattern_name": "Bull Flag",
            "reasoning": "...",
            "lines": [
                {{"label": "Upper Trendline", "x1": "YYYY-MM-DD", "y1": 150.0, "x2": "YYYY-MM-DD", "y2": 160.0}},
                {{"label": "Lower Trendline", "x1": "YYYY-MM-DD", "y1": 140.0, "x2": "YYYY-MM-DD", "y2": 145.0}}
            ]
        }}
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        try:
            data = json.loads(text)
            data['reason'] = data.get('reasoning', '')
            return data
        except json.JSONDecodeError:
            return {"signal": "HOLD", "reason": text, "lines": []}
            
    except Exception as e:
        return {"signal": "ERROR", "reason": str(e), "lines": []}

# --- NEWS FUNCTIONS ---

def fetch_rss_feed():
    items = []
    try:
        url = "https://finance.yahoo.com/news/rssindex"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        root = ET.fromstring(response.content)
        for item in root.findall('./channel/item')[:10]: 
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            description = item.find('description').text if item.find('description') is not None else ""
            if description:
                soup = BeautifulSoup(description, 'html.parser')
                description = soup.get_text().strip()
            items.append({'title': title, 'link': link, 'pub_date': pub_date, 'raw_desc': description})
    except: return []
    return items

def summarize_news_with_gemini(news_items, api_key, model_name):
    if not api_key: return news_items 
    try:
        genai.configure(api_key=api_key)
        generation_config = genai.GenerationConfig(temperature=0.0)
        model = genai.GenerativeModel(model_name, generation_config=generation_config)
        prompt = """
        Analyze headlines. 
        1. Summarize in 2 sentences. 
        2. Assign signal (BUY, SELL, HOLD). 
        3. Identify the primary Ticker (e.g. AAPL). If general/market-wide, use "MARKET".
        Format: Summary %% SIGNAL %% TICKER
        Separator: |||
        """
        input_text = ""
        for item in news_items: input_text += f"Head: {item['title']}\nCtx: {item['raw_desc']}\n"
        response = model.generate_content(prompt + "\n\n" + input_text)
        res_list = response.text.split('|||')
        for i, item in enumerate(news_items):
            if i < len(res_list):
                txt = res_list[i].strip()
                if "%%" in txt:
                    parts = txt.split("%%")
                    item['summary'] = parts[0].strip()
                    item['signal'] = parts[1].strip().upper()
                    if len(parts) > 2: item['ticker'] = parts[2].strip().upper()
                    else: item['ticker'] = "MARKET"
                else:
                    item['summary'] = txt
                    item['signal'] = "HOLD"
                    item['ticker'] = "NEWS"
    except: pass
    return news_items

# --- SIDEBAR ---
st.sidebar.title("Configuration")

if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ API Key loaded from Secrets")
else:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
    
st.sidebar.caption("[Get an API Key](https://aistudio.google.com/app/apikey)")
st.sidebar.markdown("---")

default_model_name = "gemini-flash-lite-latest"
selected_model = default_model_name

if api_key:
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        opts = [m.name.replace("models/", "") for m in models if "generateContent" in m.supported_generation_methods]
        opts.sort()
        if default_model_name not in opts: opts.insert(0, default_model_name)
        default_index = opts.index(default_model_name) if default_model_name in opts else 0
        if opts: selected_model = st.sidebar.selectbox("Choose AI Model", opts, index=default_index)
    except: pass

# --- MAIN LAYOUT ---

# Navigation Menu
page = st.sidebar.radio("Go to", ["Global Headlines", "Market Scanner", "Stock Analyst Pro"], key="navigation")

if page == "Global Headlines":
    st.title("🌍 Global Financial Headlines")
    st.subheader("Market Snapshot")
    indices = [{"n": "S&P 500", "t": "^GSPC", "f": "SPY"}, {"n": "Nasdaq", "t": "^IXIC", "f": "QQQ"}, {"n": "Gold", "t": "GC=F", "f": "GLD"}, {"n": "Oil", "t": "CL=F", "f": "USO"}]
    cols = st.columns(len(indices))
    for i, x in enumerate(indices):
        t = yf.Ticker(x["t"])
        h = t.history(period="5d")
        if h.empty: h = yf.Ticker(x["f"]).history(period="5d")
        with cols[i]:
            if len(h)>=2:
                cur = h['Close'].iloc[-1]
                delta = cur - h['Close'].iloc[-2]
                st.metric(x["n"], f"{cur:,.2f}", f"{delta:,.2f}")
            else: st.metric(x["n"], "N/A")
    
    st.markdown("---")
    st.subheader(f"AI Market Signals ({selected_model})")
    
    if not api_key:
        st.warning("⚠️ Enter Gemini API Key.")
        raw = fetch_rss_feed()
        for i in raw: st.write(f"- [{i['title']}]({i['link']})")
    else:
        with st.spinner("Analyzing news sentiment..."):
            items = fetch_rss_feed()
            ai_items = summarize_news_with_gemini(items, api_key, selected_model)
            
            for index, item in enumerate(ai_items):
                sig = item.get('signal', 'HOLD').replace("**","").strip()
                tik = item.get('ticker', 'MARKET').replace("**","").strip()
                col = "green" if "BUY" in sig else "red" if "SELL" in sig else "grey"
                
                try: dt = parsedate_to_datetime(item['pub_date']).strftime("%H:%M")
                except: dt = ""
                
                with st.expander(f"🕒 {dt} | {item['title']}"):
                    c_btn, c_sig, c_empty = st.columns([0.15, 0.2, 0.65])
                    with c_btn:
                        if tik not in ["MARKET", "NEWS"]:
                            st.button(f"🔍 {tik}", key=f"btn_{index}", on_click=go_to_ticker, args=(tik,))
                        else:
                            st.write(f"**{tik}**")
                    with c_sig:
                          st.markdown(f"<span style='color:{col}; font-weight:bold; font-size:1.1em;'>{sig}</span>", unsafe_allow_html=True)
                    st.write(item.get('summary', ''))
                    st.markdown(f"[Read More]({item['link']})")

elif page == "Market Scanner":
    st.title("⚡ S&P 500 Market Scanner")
    st.markdown("Scanning stocks for extreme RSI conditions (Filtered by Market Cap > $10M)...")
    
    # --- REFRESH BUTTON ---
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    # ----------------------

    with st.spinner("Batch processing S&P 500 data... (this runs once per hour)"):
        oversold_df, overbought_df, scanned_count = get_market_scanner_data()
        st.caption(f"✅ Successfully scanned {scanned_count} stocks.")
        
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🟢 Top 10 Oversold (Buy Candidates)")
        st.caption("RSI < 30 indicates the stock may be undervalued.")
        if not oversold_df.empty:
            for i, row in oversold_df.iterrows():
                with st.expander(f"**{row['Ticker']}** | RSI: {row['RSI']:.1f}"):
                    st.write(f"Price: ${row['Price']:.2f}")
                    st.write(f"Market Cap: {format_number(row.get('MarketCap', 0))}")
                    st.button(f"Analyze {row['Ticker']}", key=f"os_{i}", on_click=go_to_ticker, args=(row['Ticker'],))
        else:
            st.info("No stocks found with RSI < 30 (Market is strong).")

    with c2:
        st.subheader("🔴 Top 10 Overbought (Sell Candidates)")
        st.caption("RSI > 70 indicates the stock may be overvalued.")
        if not overbought_df.empty:
            for i, row in overbought_df.iterrows():
                with st.expander(f"**{row['Ticker']}** | RSI: {row['RSI']:.1f}"):
                    st.write(f"Price: ${row['Price']:.2f}")
                    st.write(f"Market Cap: {format_number(row.get('MarketCap', 0))}")
                    st.button(f"Analyze {row['Ticker']}", key=f"ob_{i}", on_click=go_to_ticker, args=(row['Ticker'],))
        else:
            st.info("No stocks found with RSI > 70 (Market is weak).")

elif page == "Stock Analyst Pro":
    st.title("🔎 Stock Technical Analyzer")
    
    # --- SEARCH BAR FIX ---
    if 'stock_query' not in st.session_state:
        st.session_state.stock_query = ""

    if st.session_state.get('target_ticker'):
        st.session_state.stock_query = st.session_state['target_ticker']
        st.session_state['target_ticker'] = None

    query = st.text_input("Search Ticker:", key="stock_query")
    # ----------------------

    if query:
        res = search_symbol(query)
        selected_ticker = None
        
        if len(res) > 0:
             exact_match = next((item for item in res if item['symbol'] == query.upper()), None)
             if exact_match:
                 selected_ticker = exact_match['symbol']
                 st.success(f"Selected: {selected_ticker} - {exact_match['name']}")
             else:
                 options = [f"{r['symbol']} - {r['name']}" for r in res]
                 choice = st.selectbox("Select:", options)
                 selected_ticker = choice.split(" - ")[0]
        
        if selected_ticker:
            st.markdown("---")
            with st.spinner(f"Analyzing {selected_ticker}..."):
                info = get_stock_info(selected_ticker)
                
                if info:
                    c1, c2, c3 = st.columns([1, 2, 1])
                    with c1: 
                        if info.get('logo_url'): st.image(info['logo_url'], width=80)
                    with c2:
                        st.header(f"{info.get('shortName')} ({selected_ticker})")
                        st.write(f"{info.get('sector', '')}")
                    with c3:
                        p = info.get('currentPrice', info.get('regularMarketPrice'))
                        if p: st.metric("Price", f"${p:,.2f}")

                    st.subheader("🤖 Pattern Recognition (AI)")
                    hist = get_stock_history(selected_ticker, '2y')
                    df_tech = calculate_technicals(hist.copy())
                    
                    analysis = None

                    if api_key and df_tech is not None:
                        # --- PREPARE DATA FOR CACHED FUNCTION ---
                        latest = df_tech.iloc[-1]
                        monthly_df = df_tech.resample('M').agg({'High': 'max', 'Low': 'min', 'Close': 'last'}).tail(24)
                        
                        monthly_str = ""
                        for date, row in monthly_df.iterrows():
                            monthly_str += f"Date {date.strftime('%Y-%m-%d')}: H {row['High']:.2f}, L {row['Low']:.2f}, C {row['Close']:.2f}\n"
                        
                        indicators_str = f"Latest Price: {latest['Close']:.2f}\nRSI: {latest['RSI']:.2f} | MACD: {latest['MACD']:.4f}\nKDJ -> K: {latest['K']:.2f} | D: {latest['D']:.2f} | J: {latest['J']:.2f}"
                        
                        # CALL CACHED FUNCTION
                        analysis = analyze_chart_with_gemini_cached(selected_ticker, monthly_str, indicators_str, api_key, selected_model)
                        
                        if analysis:
                            sig = analysis.get('signal', 'HOLD')
                            reason = analysis.get('reason', 'No analysis returned.')
                            css = "buy" if "BUY" in sig else "sell" if "SELL" in sig else "hold"
                            st.markdown(f'<div class="signal-box {css}">VERDICT: {sig}</div>', unsafe_allow_html=True)
                            st.info(f"**AI Analysis:** {reason}")
                    elif not api_key:
                        st.warning("Enter API Key in sidebar to unlock Pattern Recognition.")

                    with st.expander("📘 Reference: Chart Patterns, Signals & Success Rates"):
                            
                            def check(pat):
                                if analysis and 'reason' in analysis:
                                    reason_text = analysis['reason'].lower()
                                    pat_lower = pat.lower()
                                    if "inv" in pat_lower:
                                        if "inv" in reason_text and ("head" in reason_text or "cup" in reason_text): return " ✅ **MATCH**"
                                    elif "head & shoulders" in pat_lower:
                                        if "head & shoulders" in reason_text and "inv" not in reason_text: return " ✅ **MATCH**"
                                    elif "cup" in pat_lower:
                                         if "cup" in reason_text and "inv" not in reason_text: return " ✅ **MATCH**"
                                    elif "staircase" in pat_lower:
                                        if "staircase" in reason_text:
                                            if "ascending" in pat_lower and "ascending" in reason_text: return " ✅ **MATCH**"
                                            if "descending" in pat_lower and "descending" in reason_text: return " ✅ **MATCH**"
                                    elif pat_lower in reason_text: return " ✅ **MATCH**"
                                return ""

                            st.markdown("### 🏆 Highest Success Patterns")
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Inv. Head & Shoulders", "89% Success", "Bullish Reversal")
                            c2.metric("Double Bottom", "88% Success", "Bullish Reversal")
                            c3.metric("Desc. Triangle", "87% Success", "Bearish Breakout")
                            
                            st.markdown("---")
                            st.markdown("### 📊 Comprehensive Pattern Guide")
                            
                            t_rev, t_con, t_tr = st.tabs(["🔄 Reversal", "➡️ Continuation", "📈 Trend"])
                            
                            with t_rev:
                                st.markdown("#### Reversal Patterns")
                                

[Image of head and shoulders stock pattern diagram]

                                rev_cols = st.columns(2)
                                with rev_cols[0]:
                                    st.markdown("##### 🟢 Bullish (Buy)")
                                    st.markdown(f"""
                                    | Pattern | Signal |
                                    | :--- | :--- |
                                    | **Inv. Head & Shoulders**{check("Inv")} | **BUY** |
                                    | **Double Bottom**{check("Double Bottom")} | **BUY** |
                                    | **Rounded Bottom**{check("Rounded Bottom")} | **BUY** |
                                    | **Falling Wedge**{check("Falling Wedge")} | **BUY** |
                                    """)
                                with rev_cols[1]:
                                    st.markdown("##### 🔴 Bearish (Sell)")
                                    st.markdown(f"""
                                    | Pattern | Signal |
                                    | :--- | :--- |
                                    | **Head & Shoulders**{check("Head & Shoulders")} | **SELL** |
                                    | **Double Top**{check("Double Top")} | **SELL** |
                                    | **Rounded Top**{check("Rounded Top")} | **SELL** |
                                    | **Rising Wedge**{check("Rising Wedge")} | **SELL** |
                                    """)

                            with t_con:
                                st.markdown("#### Continuation Patterns")
                                

[Image of bullish flag chart pattern]

                                con_cols = st.columns(2)
                                with con_cols[0]:
                                    st.markdown("##### 🟢 Bullish")
                                    st.markdown(f"""
                                    | Pattern | Signal |
                                    | :--- | :--- |
                                    | **Bull Flag**{check("Bull Flag")} | **BUY** |
                                    | **Cup & Handle**{check("Cup")} | **BUY** |
                                    | **Asc. Triangle**{check("Ascending Triangle")} | **BUY** |
                                    | **Sym. Triangle (Bull)**{check("Symmetrical Triangle")} | **BUY** |
                                    """)
                                with con_cols[1]:
                                    st.markdown("##### 🔴 Bearish")
                                    st.markdown(f"""
                                    | Pattern | Signal |
                                    | :--- | :--- |
                                    | **Bear Flag**{check("Bear Flag")} | **SELL** |
                                    | **Inv. Cup & Handle**{check("Inv. Cup")} | **SELL** |
                                    | **Desc. Triangle**{check("Descending Triangle")} | **SELL** |
                                    | **Sym. Triangle (Bear)**{check("Symmetrical Triangle")} | **SELL** |
                                    """)

                            with t_tr:
                                st.markdown("#### Trend Trading")
                                st.markdown(f"""
                                - **Ascending Staircase**{check("Ascending Staircase")}: Higher Highs & Higher Lows -> **BUY** dips.
                                - **Descending Staircase**{check("Descending Staircase")}: Lower Highs & Lower Lows -> **SELL** rallies.
                                """)

                    st.markdown("---")

                    tabs = st.tabs(["Chart", "Fundamentals", "Financials", "News"])
                    with tabs[0]: 
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_width=[0.2, 0.7])
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Price'), row=1, col=1)
                        if df_tech is not None:
                            fig.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA50'], line=dict(color='orange', width=1), name='SMA 50'), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA200'], line=dict(color='blue', width=1), name='SMA 200'), row=1, col=1)
                        
                        # --- DRAW PATTERN LINES ---
                        if analysis and "lines" in analysis:
                            for line in analysis["lines"]:
                                try:
                                    fig.add_shape(
                                        type="line",
                                        x0=line['x1'], y0=line['y1'],
                                        x1=line['x2'], y1=line['y2'],
                                        line=dict(color="purple", width=3, dash="dot"),
                                        name=line.get('label', 'Pattern Line')
                                    )
                                except: pass
                        # ---------------------------
                        
                        fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='Vol'), row=2, col=1)
                        fig.update_layout(height=600, xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)

                    with tabs[1]:
                        c_a, c_b = st.columns(2)
                        with c_a:
                            st.write(f"**Mkt Cap:** {format_number(info.get('marketCap'))}")
                            st.write(f"**P/E:** {info.get('trailingPE', '-')}")
                        with c_b:
                            st.write(f"**52W High:** {info.get('fiftyTwoWeekHigh', '-')}")
                            st.write(f"**Div Yield:** {info.get('dividendYield', 0)*100:.2f}%")

                    with tabs[2]:
                        f, _, _ = get_financials_data(selected_ticker)
                        st.dataframe(f)

                    with tabs[3]:
                        news = get_ticker_news(selected_ticker)
                        for n in news[:5]: st.write(f"- [{n.get('title')}]({n.get('link')})")
