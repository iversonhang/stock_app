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
        return stock.info if 'symbol' in stock.info else None
    except: return None

@st.cache_data(ttl=300)
def get_stock_history(ticker, period):
    return yf.Ticker(ticker).history(period=period)

@st.cache_data(ttl=300)
def get_financials_data(ticker):
    stock = yf.Ticker(ticker)
    return stock.financials, stock.balance_sheet, stock.cashflow

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
        
        prompt = "Here are financial news headlines. Summarize each one into exactly 2 professional sentences for an investor. Return them separated by '|||'.\n\n"
        for item in news_items:
            prompt += f"Headline: {item['title']}\nContext: {item['raw_desc']}\n\n"

        response = model.generate_content(prompt)
        summaries = response.text.split('|||')
        
        for i, item in enumerate(news_items):
            if i < len(summaries):
                cleaned = summaries[i].strip().replace('**', '').replace('Headline:', '').strip()
                item['summary'] = cleaned
            else:
                item['summary'] = item['raw_desc']
                
    except Exception as e:
        for item in news_items:
            item['summary'] = f"AI Error: {item['raw_desc']}"
            
    return news_items

# --- SIDEBAR CONFIG (DYNAMIC MODEL LIST) ---
st.sidebar.title("Configuration")

# 1. API Key Input
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
st.sidebar.caption("[Get an API Key](https://aistudio.google.com/app/apikey)")

st.sidebar.markdown("---")

# 2. Dynamic Model Selection
selected_model = "gemini-1.5-flash" # Default fallback

if api_key:
    try:
        genai.configure(api_key=api_key)
        # Fetch list of models
        models = genai.list_models()
        
        # Filter for models that support content generation
        model_options = [m.name.replace("models/", "") for m in models if "generateContent" in m.supported_generation_methods]
        
        # Sort so newer/popular models might appear (optional)
        model_options.sort()
        
        if model_options:
            selected_model = st.sidebar.selectbox(
                "Choose AI Model", 
                model_options, 
                index=model_options.index("gemini-1.5-flash") if "gemini-1.5-flash" in model_options else 0
            )
        else:
            st.sidebar.warning("No generative models found for this key.")
            
    except Exception as e:
        st.sidebar.error("Invalid API Key or Connection Error")
else:
    st.sidebar.info("Enter API Key to load available models.")

# --- MAIN PAGE LAYOUT ---

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
    st.subheader(f"AI-Powered News Briefs ({selected_model})")
    
    if not api_key:
        st.warning("⚠️ Please enter your Gemini API Key in the sidebar to enable AI summaries.")
        with st.spinner("Fetching news..."):
            raw_news = fetch_rss_feed()
            for item in raw_news:
                with st.expander(f"{item['title']}"):
                    st.write(item['raw_desc'])
                    st.markdown(f"[Read Source]({item['link']})")
    else:
        with st.spinner(f"🤖 Gemini ({selected_model}) is analyzing the market..."):
            raw_items = fetch_rss_feed()
            ai_news = summarize_with_gemini(raw_items, api_key, selected_model)
            
            for item in ai_news:
                summary = item.get('summary', item['raw_desc'])
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
