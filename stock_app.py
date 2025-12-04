import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import xml.etree.ElementTree as ET # Standard library for parsing RSS

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Wall St. Pulse",
    page_icon="📈",
    layout="wide"
)

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .metric-container {
        border: 1px solid #e6e6e6;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

@st.cache_data(ttl=3600)
def search_symbol(query):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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

@st.cache_data(ttl=900) # Cache for 15 mins
def get_general_headlines():
    """
    Fetches the Yahoo Finance Top Stories via RSS Feed.
    This is more reliable for 'General News' than the API.
    """
    news_items = []
    try:
        # Yahoo Finance Top Stories RSS
        url = "https://finance.yahoo.com/news/rssindex"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        # Iterate through items in the RSS feed
        # Channel -> Item
        count = 0
        for item in root.findall('./channel/item'):
            if count >= 15: break
            
            news_item = {
                'title': item.find('title').text if item.find('title') is not None else 'No Title',
                'link': item.find('link').text if item.find('link') is not None else '#',
                'pubDate': item.find('pubDate').text if item.find('pubDate') is not None else '',
                # RSS often puts the image in media:content or description, skipping for simplicity in RSS view
                # or extracting simplified text
            }
            news_items.append(news_item)
            count += 1
            
    except Exception as e:
        print(f"RSS Error: {e}")
        return []
        
    return news_items

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
    
    # Indices with a Fallback mechanism (Futures -> ETFs)
    indices = [
        {"name": "S&P 500", "ticker": "^GSPC", "fallback": "SPY"},
        {"name": "Dow Jones", "ticker": "^DJI", "fallback": "DIA"},
        {"name": "Nasdaq", "ticker": "^IXIC", "fallback": "QQQ"},
        {"name": "Gold", "ticker": "GC=F", "fallback": "GLD"}, # Futures usually GC=F, fallback to GLD ETF
        {"name": "Oil", "ticker": "CL=F", "fallback": "USO"}   # Futures usually CL=F, fallback to USO ETF
    ]
    
    cols = st.columns(len(indices))
    
    for i, item in enumerate(indices):
        name = item["name"]
        ticker = item["ticker"]
        fallback = item["fallback"]
        
        # Try fetching primary ticker (Futures/Index)
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        
        # If primary fails or is empty, try fallback (ETF)
        if hist.empty:
            t = yf.Ticker(fallback)
            hist = t.history(period="5d")
            # Append a small note to the label if using fallback
            if not hist.empty:
                name = f"{name} (ETF)"
        
        with cols[i]:
            if len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                delta = current - prev
                pct_change = (delta / prev) * 100
                
                st.metric(
                    label=name, 
                    value=f"{current:,.2f}", 
                    delta=f"{delta:,.2f} ({pct_change:.2f}%)"
                )
            else:
                st.metric(label=name, value="N/A", delta="No Data")

    st.markdown("---")

    # 2. News Feed (RSS BASED)
    st.subheader("Top Financial Stories (Yahoo Finance)")
    
    with st.spinner("Fetching latest headlines..."):
        general_news = get_general_headlines()
    
    if not general_news:
        st.error("Could not fetch news feed. Please check your internet connection.")
    else:
        for article in general_news:
            title = article.get('title')
            link = article.get('link')
            pub_date = article.get('pubDate')

            with st.container():
                col1, col2 = st.columns([0.5, 4])
                
                with col1:
                    st.write("📰") 
                
                with col2:
                    st.markdown(f"### [{title}]({link})")
                    if pub_date:
                        st.caption(f"Published: {pub_date}")
                st.divider()

# --- PAGE 2: STOCK ANALYST PRO ---
elif page == "Stock Analyst Pro":
    st.title("🔎 US Stock Analyzer")
    
    search_query = st.text_input("Search by Company Name or Ticker (e.g., 'Apple' or 'AAPL'):")
    selected_ticker = None

    if search_query:
        results = search_symbol(search_query)
        if results:
            options = [f"{r['symbol']} - {r['name']} ({r['exch']})" for r in results]
            if len(options) > 0:
                choice = st.selectbox("Select Company:", options)
                selected_ticker = choice.split(" - ")[0]
        else:
            st.warning("No results found.")

    if selected_ticker:
        st.markdown("---")
        with st.spinner(f'Analyzing {selected_ticker}...'):
            info = get_stock_info(selected_ticker)
            
            if info:
                # HEADER
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if info.get('logo_url'): st.image(info['logo_url'], width=100)
                with col2:
                    st.header(f"{info.get('shortName', 'N/A')} ({selected_ticker})")
                    st.write(f"{info.get('sector', 'N/A')} | {info.get('industry', 'N/A')}")
                with col3:
                    price = info.get('currentPrice', info.get('regularMarketPrice'))
                    prev = info.get('previousClose')
                    if price and prev:
                        st.metric("Price", f"${price:,.2f}", f"{price-prev:.2f}")

                # TABS
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["Chart", "Fundamentals", "Financials", "Company Profile", "News"])
                
                # CHART
                with tab1:
                    hist = get_stock_history(selected_ticker, '1y')
                    if not hist.empty:
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.2, 0.7])
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Price'), row=1, col=1)
                        hist['SMA50'] = hist['Close'].rolling(50).mean()
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], line=dict(color='blue', width=1), name='SMA 50'), row=1, col=1)
                        fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='Volume'), row=2, col=1)
                        fig.update_layout(xaxis_rangeslider_visible=False, height=600)
                        st.plotly_chart(fig, use_container_width=True)
                    else: st.warning("No chart data.")

                # FUNDAMENTALS
                with tab2:
                    c1, c2, c3 = st.columns(3)
                    with c1: 
                        st.metric("Market Cap", format_number(info.get('marketCap')))
                        st.metric("Beta", info.get('beta', 'N/A'))
                    with c2: 
                        st.metric("PE Ratio", info.get('trailingPE', 'N/A'))
                        st.metric("EPS", info.get('trailingEps', 'N/A'))
                    with c3:
                        st.metric("Dividend Yield", f"{info.get('dividendYield', 0)*100:.2f}%")
                        st.metric("52W High", info.get('fiftyTwoWeekHigh', 'N/A'))

                # FINANCIALS
                with tab3:
                    fin_type = st.selectbox("Statement", ["Income", "Balance Sheet", "Cash Flow"])
                    f, b, c = get_financials_data(selected_ticker)
                    if fin_type=="Income": st.dataframe(f)
                    elif fin_type=="Balance Sheet": st.dataframe(b)
                    else: st.dataframe(c)

                # PROFILE
                with tab4:
                    st.write(info.get('longBusinessSummary', ''))
                    st.write(f"**Website:** {info.get('website', 'N/A')}")

                # NEWS
                with tab5:
                    news = get_ticker_news(selected_ticker)
                    if news:
                        for n in news[:10]:
                            st.markdown(f"[{n.get('title')}]({n.get('link')})")
                            st.caption(f"Source: {n.get('publisher')}")
                            st.divider()
                    else: st.info("No specific news found.")
            else:
                st.error("Error loading data.")
