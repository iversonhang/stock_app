import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Wall St. Pulse",
    page_icon="📈",
    layout="wide"
)

# --- HELPER FUNCTIONS ---
@st.cache_data(ttl=300) # Cache data for 5 minutes to prevent rate limiting
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    # Check if stock exists by trying to fetch info
    try:
        info = stock.info
        if 'symbol' not in info:
            return None
    except:
        return None
    return stock

@st.cache_data(ttl=300)
def get_market_indices():
    # S&P 500, Dow Jones, Nasdaq, Gold, Crude Oil
    tickers = ['^GSPC', '^DJI', '^IXIC', 'GC=F', 'CL=F']
    data = yf.download(tickers, period="1d", progress=False)['Close']
    return data

def format_number(num):
    if num:
        if num > 1e12: return f"{num/1e12:.2f}T"
        if num > 1e9: return f"{num/1e9:.2f}B"
        if num > 1e6: return f"{num/1e6:.2f}M"
        return f"{num:.2f}"
    return "N/A"

# --- MAIN LAYOUT ---

# Sidebar for Navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Global Headlines", "Stock Analyst Pro"])
st.sidebar.markdown("---")
st.sidebar.caption("Data provided by Yahoo Finance")

if page == "Global Headlines":
    st.title("🌍 Global Financial Headlines")
    
    # 1. Market Overview Ticker
    st.subheader("Market Snapshot")
    try:
        indices = {
            "S&P 500": "^GSPC",
            "Dow Jones": "^DJI",
            "Nasdaq": "^IXIC",
            "Gold": "GC=F",
            "Oil": "CL=F"
        }
        
        cols = st.columns(len(indices))
        for i, (name, ticker) in enumerate(indices.items()):
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                delta = current - prev
                cols[i].metric(label=name, value=f"{current:,.2f}", delta=f"{delta:,.2f}")
    except Exception as e:
        st.error("Could not load market indices at this moment.")

    st.markdown("---")

    # 2. News Feed
    st.subheader("Top Financial Stories")
    try:
        market_news = yf.Ticker("SPY").news
        
        if not market_news:
            st.info("No news available at the moment.")
        
        for article in market_news:
            # FIX: Use .get() to safely retrieve data. If missing, skip the article.
            title = article.get('title')
            link = article.get('link')
            publisher = article.get('publisher', 'Unknown Source')
            publish_time_raw = article.get('providerPublishTime')

            # If essential info is missing, skip this news item
            if not title or not link:
                continue

            with st.container():
                col1, col2 = st.columns([1, 3])
                
                # Image handling
                with col1:
                    has_image = False
                    if 'thumbnail' in article and 'resolutions' in article['thumbnail']:
                        try:
                            # Try to get the first resolution url
                            resolutions = article['thumbnail']['resolutions']
                            if resolutions:
                                st.image(resolutions[0]['url'], use_column_width=True)
                                has_image = True
                        except:
                            pass # Fail silently on image errors
                    
                    if not has_image:
                        st.write("📰") # Placeholder icon
                
                with col2:
                    st.markdown(f"### [{title}]({link})")
                    st.write(f"**Publisher:** {publisher}")
                    
                    # Safe timestamp conversion
                    if publish_time_raw:
                        try:
                            pub_time = datetime.fromtimestamp(publish_time_raw)
                            st.caption(f"Published: {pub_time.strftime('%Y-%m-%d %H:%M')}")
                        except:
                            st.caption("Published: Recently")
                st.divider()

    except Exception as e:
        st.warning("News feed is temporarily unavailable.")

elif page == "Stock Analyst Pro":
    st.title("🔎 US Stock Analyzer")
    
    ticker_input = st.text_input("Enter Stock Ticker (e.g., AAPL, NVDA, TSLA):", "AAPL").upper()
    
    if ticker_input:
        with st.spinner(f'Analyzing {ticker_input}...'):
            stock = get_stock_data(ticker_input)
            
            if stock:
                info = stock.info
                
                # --- HEADER SECTION ---
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    logo = info.get('logo_url', '')
                    if logo:
                        st.image(logo, width=100)
                with col2:
                    st.header(f"{info.get('shortName', 'N/A')} ({ticker_input})")
                    st.write(f"{info.get('sector', 'N/A')} | {info.get('industry', 'N/A')}")
                with col3:
                    current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                    prev_close = info.get('previousClose', 0)
                    if current_price and prev_close:
                        st.metric("Current Price", f"${current_price}", f"{current_price - prev_close:.2f}")
                    else:
                        st.write("Price data unavailable")

                # --- TABS FOR ANALYSIS ---
                tab1, tab2, tab3, tab4 = st.tabs(["Chart", "Fundamentals", "Financials", "Company Profile"])
                
                # TAB 1: CHARTING
                with tab1:
                    st.subheader("Technical Analysis")
                    time_period = st.select_slider("Select Time Range", options=['1mo', '3mo', '6mo', '1y', '2y', '5y'], value='1y')
                    
                    hist = stock.history(period=time_period)
                    
                    if not hist.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index,
                                        open=hist['Open'], high=hist['High'],
                                        low=hist['Low'], close=hist['Close'], name='Price'))
                        
                        hist['SMA20'] = hist['Close'].rolling(window=20).mean()
                        hist['SMA50'] = hist['Close'].rolling(window=50).mean()
                        
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA20'], line=dict(color='orange', width=1), name='SMA 20'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        
                        fig.update_layout(title=f'{ticker_input} Price History', xaxis_rangeslider_visible=False, height=600)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("No chart data available.")

                # TAB 2: FUNDAMENTALS
                with tab2:
                    st.subheader("Key Ratios")
                    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
                    
                    with f_col1:
                        st.write("**Valuation**")
                        st.write(f"Market Cap: {format_number(info.get('marketCap'))}")
                        st.write(f"Trailing P/E: {info.get('trailingPE', 'N/A')}")
                        st.write(f"Forward P/E: {info.get('forwardPE', 'N/A')}")
                        
                    with f_col2:
                        st.write("**Profitability**")
                        st.write(f"Profit Margins: {info.get('profitMargins', 0)*100:.2f}%")
                        st.write(f"ROA: {info.get('returnOnAssets', 0)*100:.2f}%")
                        st.write(f"ROE: {info.get('returnOnEquity', 0)*100:.2f}%")
                        
                    with f_col3:
                        st.write("**Risk/Volatility**")
                        st.write(f"Beta: {info.get('beta', 'N/A')}")
                        st.write(f"52 Week High: {info.get('fiftyTwoWeekHigh', 'N/A')}")
                        st.write(f"52 Week Low: {info.get('fiftyTwoWeekLow', 'N/A')}")

                    with f_col4:
                        st.write("**Dividends**")
                        st.write(f"Dividend Rate: {info.get('dividendRate', 'N/A')}")
                        st.write(f"Dividend Yield: {info.get('dividendYield', 0)*100:.2f}%")

                # TAB 3: FINANCIAL STATEMENTS
                with tab3:
                    st.subheader("Financial Statements")
                    fin_type = st.selectbox("Select Statement", ["Income Statement", "Balance Sheet", "Cash Flow"])
                    
                    try:
                        if fin_type == "Income Statement":
                            st.dataframe(stock.financials)
                        elif fin_type == "Balance Sheet":
                            st.dataframe(stock.balance_sheet)
                        elif fin_type == "Cash Flow":
                            st.dataframe(stock.cashflow)
                    except:
                        st.write("Financial statement data unavailable.")

                # TAB 4: PROFILE & NEWS
                with tab4:
                    st.subheader("Business Summary")
                    st.write(info.get('longBusinessSummary', 'No summary available.'))
                    
                    st.subheader("Company Data")
                    st.write(f"**Employees:** {info.get('fullTimeEmployees', 'N/A')}")
                    st.write(f"**Website:** {info.get('website', 'N/A')}")
                    st.write(f"**Headquarters:** {info.get('city', '')}, {info.get('state', '')}")

            else:
                st.error("Stock ticker not found. Please check the symbol and try again.")
