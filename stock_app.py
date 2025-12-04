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

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stExpander { border: 1px solid #f0f2f6; border-radius: 8px; margin-bottom: 10px; background-color: #ffffff; }
    .streamlit-expanderHeader { font-size: 15px; font-weight: 600; color: #0e1117; }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

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
        # Force a fetch to check validity
        info = stock.info
        return info if 'symbol' in info else None
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

# --- CORE LOGIC: RSS + GEMINI ---

def fetch_rss_feed():
    """Fetches raw RSS items without AI processing."""
    items = []
    try:
        url = "https://finance.yahoo.com/news/rssindex"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        root = ET.fromstring(response.content)
        
        # Limit to top 10 for AI speed
        for item in root.findall('./channel/item')[:10]: 
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            description = item.find('description').text if item.find('description') is not None else ""
            
            if description:
                soup = BeautifulSoup(description, 'html.parser')
                description = soup.get_text().strip()

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'raw_desc': description
            })
    except Exception as e:
        st.error(f"RSS Error: {e}")
        return []
    return items

def summarize_with_gemini(news_items, api_key, model_name):
    if not api_key: return news_items 

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        
        # --- PROMPT FOR SIGNALS ---
        prompt = """
        Analyze the following financial news headlines. For each one:
        1. Write a 2-sentence summary.
        2. Assign a one-word signal: "BUY", "SELL", or "HOLD".
        
        Return format: Summary text... %% SIGNAL
        Separate items with '|||'.
        """
        
        for item in news_items:
            prompt += f"\nHeadline: {item['title']}\nContext: {item['raw_desc']}\n"

        response = model.generate_content(prompt)
        raw_responses = response.text.split('|||')
        
        for i, item in enumerate(news_items):
            if i < len(raw_responses):
                full_text = raw_responses[i].strip()
                if "%%" in full_text:
                    parts = full_text.split("%%")
                    item['summary'] = parts[0].strip()
                    item['signal'] = parts[1].strip().upper()
                else:
                    item['summary'] = full_text
                    item['signal'] = "HOLD"
            else:
                item['summary'] = item['raw_desc']
                item['signal'] = "HOLD"
                
    except Exception as e:
        for item in news_items:
            item['summary'] = f"AI Error: {item['raw_desc']}"
            item['signal'] = "HOLD"
            
    return news_items

# --- SIDEBAR CONFIG ---
st.sidebar.title("Configuration")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
st.sidebar.caption("[Get an API Key](https://aistudio.google.com/app/apikey)")
st.sidebar.markdown("---")

# Dynamic Model Selection
selected_model = "gemini-1.5-flash" 
if api_key:
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        model_options = [m.name.replace("models/", "") for m in models if "generateContent" in m.supported_generation_methods]
        model_options.sort()
        if model_options:
            selected_model = st.sidebar.selectbox("Choose AI Model", model_options, index=0)
    except: pass

# --- MAIN PAGE LAYOUT ---

page = st.sidebar.radio("Go to", ["Global Headlines", "Stock Analyst Pro"])

# --- PAGE 1: GLOBAL HEADLINES ---
if page == "Global Headlines":
    st.title("🌍 Global Financial Headlines")
    
    st.subheader("Market Snapshot")
    indices = [
        {"name": "S&P 500", "ticker": "^GSPC", "fallback": "SPY"},
        {"name": "Nasdaq", "ticker": "^IXIC", "fallback": "QQQ"},
        {"name": "Gold", "ticker": "GC=F", "fallback": "GLD"},
        {"name": "Oil", "ticker": "CL=F", "fallback": "USO"}
    ]
    cols = st.columns(len(indices))
    for i, idx in enumerate(indices):
        t = yf.Ticker(idx["ticker"])
        hist = t.history(period="5d")
        if hist.empty:
            t = yf.Ticker(idx["fallback"])
            hist = t.history(period="5d")
        
        with cols[i]:
            if len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                st.metric(idx["name"], f"{curr:,.2f}", f"{curr-prev:,.2f}")
            else:
                st.metric(idx["name"], "N/A")

    st.markdown("---")
    st.subheader(f"AI Market Signals ({selected_model})")
    
    if not api_key:
        st.warning("⚠️ Enter Gemini API Key to see Buy/Sell/Hold signals.")
        with st.spinner("Fetching news..."):
            raw_news = fetch_rss_feed()
            for item in raw_news:
                with st.expander(f"{item['title']}"):
                    st.write(item['raw_desc'])
                    st.markdown(f"[Read Source]({item['link']})")
    else:
        st.caption("Disclaimer: Signals are AI-generated based on news sentiment and are NOT financial advice.")
        with st.spinner(f"🤖 Analyzing market sentiment..."):
            raw_items = fetch_rss_feed()
            ai_news = summarize_with_gemini(raw_items, api_key, selected_model)
            
            for item in ai_news:
                summary = item.get('summary', item['raw_desc'])
                signal = item.get('signal', 'HOLD').replace("**", "").strip()
                color = "grey"
                if "BUY" in signal: color = "green"
                elif "SELL" in signal: color = "red"
                
                try: dt = parsedate_to_datetime(item['pub_date']).strftime("%H:%M")
                except: dt = ""
                
                with st.expander(f"🕒 {dt} | {item['title']}"):
                    st.markdown(f"**AI Sentiment:** :{color}[**{signal}**]")
                    st.write(summary)
                    st.markdown(f"👉 [Read full article]({item['link']})")

# --- PAGE 2: STOCK ANALYST PRO ---
elif page == "Stock Analyst Pro":
    st.title("🔎 Stock Analyzer")
    query = st.text_input("Search Ticker:")
    
    if query:
        res = search_symbol(query)
        if res:
            options = [f"{r['symbol']} - {r['name']}" for r in res]
            choice = st.selectbox("Select:", options)
            selected_ticker = choice.split(" - ")[0]
            
            if selected_ticker:
                st.markdown("---")
                with st.spinner(f"Analyzing {selected_ticker}..."):
                    info = get_stock_info(selected_ticker)
                    
                    if info:
                        # Header
                        c1, c2, c3 = st.columns([1, 2, 1])
                        with c1: 
                            if info.get('logo_url'): st.image(info['logo_url'], width=80)
                        with c2:
                            st.header(f"{info.get('shortName')} ({selected_ticker})")
                            st.write(f"{info.get('sector', '')} | {info.get('industry', '')}")
                        with c3:
                            p = info.get('currentPrice', info.get('regularMarketPrice'))
                            prev = info.get('previousClose')
                            if p and prev: st.metric("Price", f"${p:,.2f}", f"{p-prev:.2f}")

                        # --- RESTORED 5 TABS ---
                        t1, t2, t3, t4, t5 = st.tabs(["Chart", "Fundamentals", "Financials", "Profile", "News"])
                        
                        # Tab 1: Chart
                        with t1:
                            h = get_stock_history(selected_ticker, '1y')
                            if not h.empty:
                                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_width=[0.2, 0.7])
                                fig.add_trace(go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close'], name='Price'), row=1, col=1)
                                h['SMA50'] = h['Close'].rolling(50).mean()
                                fig.add_trace(go.Scatter(x=h.index, y=h['SMA50'], line=dict(color='blue', width=1), name='SMA 50'), row=1, col=1)
                                fig.add_trace(go.Bar(x=h.index, y=h['Volume'], name='Vol'), row=2, col=1)
                                fig.update_layout(height=600, xaxis_rangeslider_visible=False)
                                st.plotly_chart(fig, use_container_width=True)

                        # Tab 2: Fundamentals (Restored)
                        with t2:
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.write(f"**Mkt Cap:** {format_number(info.get('marketCap'))}")
                                st.write(f"**P/E:** {info.get('trailingPE', '-')}")
                                st.write(f"**Beta:** {info.get('beta', '-')}")
                            with col_b:
                                st.write(f"**52W High:** {info.get('fiftyTwoWeekHigh', '-')}")
                                st.write(f"**Div Yield:** {info.get('dividendYield', 0)*100:.2f}%")
                                st.write(f"**Profit Margin:** {info.get('profitMargins', 0)*100:.2f}%")

                        # Tab 3: Financials
                        with t3:
                            st.caption("Annual Income Statement")
                            f, _, _ = get_financials_data(selected_ticker)
                            st.dataframe(f)

                        # Tab 4: Profile (Restored)
                        with t4:
                            st.subheader("Business Summary")
                            st.write(info.get('longBusinessSummary', 'No summary available.'))
                            st.markdown("---")
                            st.write(f"**Website:** {info.get('website', 'N/A')}")
                            st.write(f"**Employees:** {info.get('fullTimeEmployees', 'N/A')}")

                        # Tab 5: News (Restored)
                        with t5:
                            st.subheader(f"Recent News for {selected_ticker}")
                            news = get_ticker_news(selected_ticker)
                            if news:
                                for n in news[:10]:
                                    with st.expander(f"{n.get('title')}"):
                                        st.write(f"Publisher: {n.get('publisher')}")
                                        st.markdown(f"[Read full story]({n.get('link')})")
                            else: st.info("No specific news found.")
                    else:
                        st.error("Could not load data.")
        else:
            st.warning("No results found.")
