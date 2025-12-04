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

# --- CONFIGURATION ---
st.set_page_config(page_title="Wall St. Pulse", page_icon="📈", layout="wide")

# --- SESSION STATE INITIALIZATION ---
if 'navigation' not in st.session_state:
    st.session_state['navigation'] = "Global Headlines"
if 'target_ticker' not in st.session_state:
    st.session_state['target_ticker'] = None

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stExpander { border: 1px solid #f0f2f6; border-radius: 8px; margin-bottom: 10px; background-color: #ffffff; }
    .signal-box { padding: 15px; border-radius: 10px; margin-bottom: 20px; text-align: center; font-weight: bold; font-size: 24px; }
    .buy { background-color: #e6fffa; color: #00bfa5; border: 1px solid #00bfa5; }
    .sell { background-color: #fff5f5; color: #ff5252; border: 1px solid #ff5252; }
    .hold { background-color: #f0f2f6; color: #555; border: 1px solid #ccc; }
    /* Compact buttons */
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
        response = requests.get(url, headers=headers)
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
    return df

def analyze_chart_with_gemini(ticker, df, api_key, model_name):
    if not api_key or df is None: return None
    latest = df.iloc[-1]
    weekly_df = df.resample('W').agg({'High': 'max', 'Low': 'min', 'Close': 'last'}).tail(15)
    price_sequence = ""
    for date, row in weekly_df.iterrows():
        price_sequence += f"Week {date.strftime('%Y-%m-%d')}: H {row['High']:.2f}, L {row['Low']:.2f}, C {row['Close']:.2f}\n"

    tech_data = f"""
    Ticker: {ticker} | Price: {latest['Close']:.2f} | RSI: {latest['RSI']:.2f} | MACD: {latest['MACD']:.4f}
    SMA50: {latest['SMA50']:.2f} | SMA200: {latest['SMA200']:.2f}
    Weekly Prices:
    {price_sequence}
    """

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        Act as a technical analyst for {ticker}.
        {tech_data}
        Check for: Staircases, Triangles, Flags, Wedges, Double Top/Bottom, Head & Shoulders, Cup & Handle.
        Output strictly: SIGNAL ||| Pattern Name: [Name] - [Reasoning]
        Replace SIGNAL with BUY, SELL, or HOLD.
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "|||" in text:
            parts = text.split("|||")
            sig = parts[0].strip().upper().replace("VERDICT","").replace("SIGNAL","").replace(":","").strip()
            if "BUY" in sig: s = "BUY"
            elif "SELL" in sig: s = "SELL"
            else: s = "HOLD"
            return {"signal": s, "reason": parts[1].strip()}
        else:
            return {"signal": "HOLD", "reason": text}
    except Exception as e:
        return {"signal": "ERROR", "reason": str(e)}

# --- NEWS FUNCTIONS ---

def fetch_rss_feed():
    items = []
    try:
        url = "https://finance.yahoo.com/news/rssindex"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
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
        model = genai.GenerativeModel(model_name)
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

# Check if the key exists in Streamlit Secrets
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ API Key loaded from Secrets")
else:
    # Fallback to manual input
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
    
st.sidebar.caption("[Get an API Key](https://aistudio.google.com/app/apikey)")
st.sidebar.markdown("---")

# --- UPDATED MODEL SELECTION LOGIC ---
default_model_name = "gemini-flash-lite-latest"
selected_model = default_model_name

if api_key:
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        opts = [m.name.replace("models/", "") for m in models if "generateContent" in m.supported_generation_methods]
        opts.sort()
        
        # Ensure our preferred default is in the list options (sometimes aliases aren't listed explicitly)
        if default_model_name not in opts:
            opts.insert(0, default_model_name)
            
        # Find the index of our default model to set the selectbox correctly
        default_index = 0
        if default_model_name in opts:
            default_index = opts.index(default_model_name)
            
        if opts: selected_model = st.sidebar.selectbox("Choose AI Model", opts, index=default_index)
    except: pass

# --- MAIN LAYOUT ---

# Linked to session state
page = st.sidebar.radio("Go to", ["Global Headlines", "Stock Analyst Pro"], key="navigation")

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
                        # --- FIX: USE CALLBACK FOR NAVIGATION ---
                        if tik not in ["MARKET", "NEWS"]:
                            st.button(f"🔍 {tik}", key=f"btn_{index}", on_click=go_to_ticker, args=(tik,))
                        else:
                            st.write(f"**{tik}**")
                    with c_sig:
                          st.markdown(f"<span style='color:{col}; font-weight:bold; font-size:1.1em;'>{sig}</span>", unsafe_allow_html=True)
                    st.write(item.get('summary', ''))
                    st.markdown(f"[Read More]({item['link']})")

elif page == "Stock Analyst Pro":
    st.title("🔎 Stock Technical Analyzer")
    
    incoming_ticker = st.session_state.get('target_ticker')
    default_val = incoming_ticker if incoming_ticker else ""
    query = st.text_input("Search Ticker:", value=default_val)
    
    if incoming_ticker: st.session_state['target_ticker'] = None

    if query:
        res = search_symbol(query)
        selected_ticker = None
        
        if len(res) > 0:
             exact_match = next((item for item in res if item['symbol'] == query.upper()), None)
             if exact_match:
                 selected_ticker = exact_match['symbol']
                 options = [f"{r['symbol']} - {r['name']}" for r in res]
                 idx = 0
                 for i, r in enumerate(res):
                     if r['symbol'] == selected_ticker: idx = i
                 choice = st.selectbox("Select:", options, index=idx)
                 selected_ticker = choice.split(" - ")[0]
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
                    
                    if api_key and df_tech is not None:
                        analysis = analyze_chart_with_gemini(selected_ticker, df_tech, api_key, selected_model)
                        if analysis:
                            sig = analysis['signal']
                            css = "buy" if "BUY" in sig else "sell" if "SELL" in sig else "hold"
                            st.markdown(f'<div class="signal-box {css}">VERDICT: {sig}</div>', unsafe_allow_html=True)
                            st.info(f"**AI Analysis:** {analysis['reason']}")
                    elif not api_key:
                        st.warning("Enter API Key in sidebar to unlock Pattern Recognition.")

                    with st.expander("📘 Reference: Chart Patterns, Signals & Success Rates"):
                            st.markdown("### 🏆 Highest Success Patterns")
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Inv. Head & Shoulders", "89% Success", "Bullish Reversal")
                            c2.metric("Double Bottom", "88% Success", "Bullish Reversal")
                            c3.metric("Desc. Triangle", "87% Success", "Bearish Breakout")
                            st.markdown("---")
                            st.markdown("### 📊 Comprehensive Pattern Guide")
                            t_tr, t_rev, t_con = st.tabs(["Trend", "Reversal", "Continuation"])
                            with t_tr: st.write("Staircases (Trend)")
                            with t_rev: st.write("Double Top/Bottom, Head & Shoulders, Wedges, Rounded Top/Bottom")
                            with t_con: st.write("Triangles, Flags, Cup & Handle")

                    st.markdown("---")

                    tabs = st.tabs(["Chart", "Fundamentals", "Financials", "News"])
                    with tabs[0]: 
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_width=[0.2, 0.7])
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Price'), row=1, col=1)
                        if df_tech is not None:
                            fig.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA50'], line=dict(color='orange', width=1), name='SMA 50'), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_tech.index, y=df_tech['SMA200'], line=dict(color='blue', width=1), name='SMA 200'), row=1, col=1)
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
