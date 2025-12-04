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

# --- SIDEBAR CONFIG ---
st.sidebar.title("Configuration")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
st.sidebar.caption("[Get an API Key](https://aistudio.google.com/app/apikey)")

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

# --- CORE LOGIC: RSS + GEMINI ---

def fetch_rss_feed():
    """Fetches raw RSS items without AI processing."""
    items = []
    try:
        url = "https://finance.yahoo.com/news/rssindex"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        root = ET.fromstring(response.content)
        
        for item in root.findall('./channel/item')[:10]: # Limit to top 10 for AI speed
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            description = item.find('description').text if item.find('description') is not None else ""
            
            # Basic cleanup of description for the prompt
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

def summarize_with_gemini(news_items, api_key):
    """
    Sends a batch request to Gemini to summarize all headlines at once.
    This is much faster than sending 1 request per headline.
    """
    if not api_key:
        return news_items # Return raw items if no key

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # specific prompt to ensure structured output
        prompt = "Here are financial news headlines. Summarize each one into exactly 2 professional sentences for an investor. Return them separated by '|||'.\n\n"
        
        for item in news_items:
            prompt += f"Headline: {item['title']}\nContext: {item['raw_desc']}\n\n"

        response = model.generate_content(prompt)
        
        # Split response back into list
        summaries = response.text.split('|||')
        
        # Attach summaries to items
        for i, item in enumerate(news_items):
            if i < len(summaries):
                cleaned_summary = summaries[i].strip()
                # Remove any markdown junk if Gemini adds it
                cleaned_summary = cleaned_summary.replace('**', '').replace('Headline:', '').strip()
                item['summary'] = cleaned_summary
            else:
                item['summary'] = item['raw_desc'] # Fallback
                
    except Exception as e:
        # Fallback if AI fails
        for item in news_items:
            item['summary'] = f"AI Error: Using raw text. {item['raw_desc']}"
            
    return news_items

# --- MAIN PAGE LAYOUT ---

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Global Headlines", "Stock Analyst Pro"])

if page == "Global Headlines":
    st.title("🌍 Global Financial Headlines")
    
    # Snapshot Section
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

    # News Section
    st.subheader("AI-Powered News Briefs")
    
    if not api_key:
        st.warning("⚠️ Please enter your Gemini API Key in the sidebar to enable AI summaries.")
        # Fallback to standard fetch without AI
        with st.spinner("Fetching news..."):
            raw_news = fetch_rss_feed()
            for item in raw_news:
                with st.expander(f"{item['title']}"):
                    st.write(item['raw_desc'])
                    st.markdown(f"[Read Source]({item['link']})")
    else:
        with st.spinner("🤖 Gemini is reading the news for you..."):
            # 1. Fetch Raw
            raw_items = fetch_rss_feed()
            # 2. Process with AI
            ai_news = summarize_with_gemini(raw_items, api_key)
            
            for item in ai_news:
                summary = item.get('summary', item['raw_desc'])
                # Parsing date for display
                try: 
                    dt = parsedate_to_datetime(item['pub_date']).strftime("%H:%M")
                except: dt = ""
                
                with st.expander(f"🕒 {dt} | {item['title']}"):
                    st.markdown(f"**AI Summary:** {summary}")
                    st.markdown(f"👉 [Read full article]({item['link']})")

elif page == "Stock Analyst Pro":
    st.title("🔎 Stock Analyzer")
    query = st.text_input("Search Ticker:")
    if query:
        res = search_symbol(query)
        if res:
            sel = st.selectbox("Select:", [f"{r['symbol']}" for r in res])
            if sel:
                with st.spinner("Loading..."):
                    info = get_stock_info(sel)
                    if info:
                        st.header(f"{info.get('shortName')} ({sel})")
                        st.metric("Price", f"${info.get('currentPrice', 0)}")
                        
                        tab1, tab2 = st.tabs(["Chart", "Financials"])
                        with tab1:
                            h = get_stock_history(sel, '1y')
                            if not h.empty:
                                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_width=[0.2, 0.7])
                                fig.add_trace(go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close']), row=1, col=1)
                                fig.add_trace(go.Bar(x=h.index, y=h['Volume']), row=2, col=1)
                                fig.update_layout(xaxis_rangeslider_visible=False, showlegend=False)
                                st.plotly_chart(fig)
                        with tab2:
                            f, _, _ = get_financials_data(sel)
                            st.dataframe(f)
