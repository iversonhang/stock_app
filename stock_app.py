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

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Wall St. Pulse",
    page_icon="📈",
    layout="wide"
)

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stExpander {
        border: 1px solid #f0f2f6;
        border-radius: 8px;
        margin-bottom: 10px;
        background-color: #ffffff;
    }
    .streamlit-expanderHeader {
        font-size: 15px;
        font-weight: 600;
        color: #0e1117;
    }
    .metric-container {
        padding: 10px;
    }
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
                    results.append({
                        'symbol': quote['symbol'],
                        'name': quote['shortname'],
                        'exch': quote.get('exchange', 'N/A'),
                        'type': quote.get('quoteType', 'N/A')
                    })
        return results
    except Exception:
        return []

@st.cache_data(ttl=300) 
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if 'symbol' not in info: return None
        return info
    except Exception: return None

@st.cache_data(ttl=300)
def get_stock_history(ticker, period):
    stock = yf.Ticker(ticker)
    return stock.history(period=period)

@st.cache_data(ttl=300)
def get_financials_data(ticker):
    stock = yf.Ticker(ticker)
    return stock.financials, stock.balance_sheet, stock.cashflow

@st.cache_data(ttl=900) 
def get_general_headlines():
    """
    Fetches Yahoo Finance RSS with robust fallback for summaries.
    Handles 'media' namespaces where the actual text often hides.
    """
    news_items = []
    try:
        url = "https://finance.yahoo.com/news/rssindex"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        root = ET.fromstring(response.content)
        
        # Yahoo uses the Media RSS namespace
        ns = {'media': 'http://search.yahoo.com/mrss/'}
        
        for item in root.findall('./channel/item'):
            title = item.find('title').text if item.find('title') is not None else 'No Title'
            link = item.find('link').text if item.find('link') is not None else '#'
            pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ''
            
            # --- ROBUST SUMMARY EXTRACTION ---
            summary_text = ""
            
            # Strategy 1: Standard Description
            desc_tag = item.find('description')
            if desc_tag is not None and desc_tag.text:
                summary_text = desc_tag.text
            
            # Strategy 2: Media Description (Namespaced) - often contains the real text
            # If standard description is empty or too short (likely just an image link)
            if len(summary_text) < 20:
                media_desc = item.find('media:description', ns)
                if media_desc is not None and media_desc.text:
                    summary_text = media_desc.text
                else:
                    # Strategy 3: Media Text
                    media_text = item.find('media:text', ns)
                    if media_text is not None and media_text.text:
                        summary_text = media_text.text

            # Clean HTML tags using BeautifulSoup
            if summary_text:
                soup = BeautifulSoup(summary_text, 'html.parser')
                summary_text = soup.get_text().strip()
            
            # Final Fallback
            if not summary_text or len(summary_text) < 10:
                summary_text = "No summary provided by source. Click the link to read the full article."

            # Date Parsing
            try:
                pub_date_obj = parsedate_to_datetime(pub_date_str)
            except:
                pub_date_obj = datetime.min

            news_items.append({
                'title': title,
                'link': link,
                'pubDateStr': pub_date_str,
                'pubDateObj': pub_date_obj,
                'summary': summary_text
            })
            
        news_items.sort(key=lambda x: x['pubDateObj'], reverse=True)
            
    except Exception as e:
        print(f"RSS Error: {e}")
        return []
        
    return news_items[:20]

@st.cache_data(ttl=300)
def get_ticker_news(ticker):
    try:
        stock = yf.Ticker(ticker)
        return stock.news
    except:
        return []

def format_number(num):
    if num:
        if num > 1e12: return f"{num/1e12:.2f}T"
        if num > 1e9: return f"{num/1e9:.2f}B"
        if num > 1e6: return f"{num/1e6:.2f}M"
        return f"{num:.2f}"
    return "N/A"

# --- MAIN LAYOUT ---

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Global Headlines", "Stock Analyst Pro"])
st.sidebar.markdown("---")

# --- PAGE 1: GLOBAL HEADLINES ---
if page == "Global Headlines":
    st.title("🌍 Global Financial Headlines")
    
    # 1. Market Snapshot
    st.subheader("Market Snapshot")
    indices = [
        {"name": "S&P 500", "ticker": "^GSPC", "fallback": "SPY"},
        {"name": "Dow Jones", "ticker": "^DJI", "fallback": "DIA"},
        {"name": "Nasdaq", "ticker": "^IXIC", "fallback": "QQQ"},
        {"name": "Gold", "ticker": "GC=F", "fallback": "GLD"},
        {"name": "Oil", "ticker": "CL=F", "fallback": "USO"}
    ]
    
    cols = st.columns(len(indices))
    
    for i, item in enumerate(indices):
        name = item["name"]
        ticker = item["ticker"]
        
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        
        if hist.empty:
            t = yf.Ticker(item["fallback"])
            hist = t.history(period="5d")
            if not hist.empty: name = f"{name} (ETF)"
        
        with cols[i]:
            if len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                delta = curr - prev
                pct = (delta / prev) * 100
                st.metric(label=name, value=f"{curr:,.2f}", delta=f"{delta:,.2f} ({pct:.2f}%)")
            else:
                st.metric(label=name, value="N/A", delta="No Data")

    st.markdown("---")

    # 2. News Feed
    st.subheader("Latest News Briefs")
    st.caption("Click on a headline to reveal the summary.")
    
    with st.spinner("Fetching latest news summaries..."):
        general_news = get_general_headlines()
    
    if not general_news:
        st.error("Could not fetch news feed.")
    else:
        for article in general_news:
            title = article['title']
            summary = article['summary']
            date_display = article['pubDateObj'].strftime("%H:%M") if article['pubDateObj'] != datetime.min else ""
            
            with st.expander(f"🕒 {date_display} | {title}"):
                st.write(summary)
                st.markdown(f"👉 [Read full article on Yahoo Finance]({article['link']})")

# --- PAGE 2: STOCK ANALYST PRO ---
elif page == "Stock Analyst Pro":
    st.title("🔎 US Stock Analyzer")
    
    search_query = st.text_input("Search (e.g. 'Nvidia'):")
    selected_ticker = None

    if search_query:
        results = search_symbol(search_query)
        if results:
            options = [f"{r['symbol']} - {r['name']}" for r in results]
            choice = st.selectbox("Select:", options)
            selected_ticker = choice.split(" - ")[0]
        else: st.warning("No results.")

    if selected_ticker:
        st.markdown("---")
        with st.spinner('Loading data...'):
            info = get_stock_info(selected_ticker)
            
            if info:
                # HEADER
                c1, c2, c3 = st.columns([1, 2, 1])
                with c1: 
                    if info.get('logo_url'): st.image(info['logo_url'], width=80)
                with c2:
                    st.header(f"{info.get('shortName')} ({selected_ticker})")
                    st.write(info.get('industry', ''))
                with c3:
                    p = info.get('currentPrice', info.get('regularMarketPrice'))
                    prev = info.get('previousClose')
                    if p and prev: st.metric("Price", f"${p:,.2f}", f"{p-prev:.2f}")

                # TABS
                t1, t2, t3, t4 = st.tabs(["Chart", "Stats", "Financials", "News"])
                
                # CHART
                with t1:
                    h = get_stock_history(selected_ticker, '1y')
                    if not h.empty:
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_width=[0.2, 0.7])
                        fig.add_trace(go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close'], name='Price'), row=1, col=1)
                        h['SMA50'] = h['Close'].rolling(50).mean()
                        fig.add_trace(go.Scatter(x=h.index, y=h['SMA50'], line=dict(color='#2962FF'), name='SMA 50'), row=1, col=1)
                        fig.add_trace(go.Bar(x=h.index, y=h['Volume'], name='Vol', marker_color='#B0BEC5'), row=2, col=1)
                        fig.update_layout(height=600, xaxis_rangeslider_visible=False, showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

                # STATS
                with t2:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**Mkt Cap:** {format_number(info.get('marketCap'))}")
                        st.write(f"**P/E:** {info.get('trailingPE', '-')}")
                    with col_b:
                        st.write(f"**52W High:** {info.get('fiftyTwoWeekHigh', '-')}")
                        st.write(f"**Div Yield:** {info.get('dividendYield', 0)*100:.2f}%")

                # FINANCIALS
                with t3:
                    f, b, c = get_financials_data(selected_ticker)
                    st.dataframe(f)

                # NEWS
                with t4:
                    news = get_ticker_news(selected_ticker)
                    if news:
                        for n in news[:10]:
                            with st.expander(f"{n.get('title')}"):
                                st.write(f"Publisher: {n.get('publisher')}")
                                st.markdown(f"[Read full story]({n.get('link')})")
                    else: st.info("No news.")
