# ... (Previous code remains exactly the same) ...

elif page == "Stock Analyst Pro":
    st.title("🔎 Stock Technical Analyzer")
    
    # --- FIX: ROBUST STATE MANAGEMENT ---
    # 1. Initialize the query state if it doesn't exist
    if 'stock_query' not in st.session_state:
        st.session_state.stock_query = ""

    # 2. If we are coming from the Market Scanner (target_ticker is set), 
    #    FORCE update the search bar state.
    if st.session_state.get('target_ticker'):
        st.session_state.stock_query = st.session_state['target_ticker']
        st.session_state['target_ticker'] = None # Clear the trigger so it doesn't stick

    # 3. Bind the text_input directly to the session state key
    #    This ensures the box shows "AAPL" immediately when redirected.
    query = st.text_input("Search Ticker:", key="stock_query")
    
    # ------------------------------------

    if query:
        res = search_symbol(query)
        selected_ticker = None
        
        if len(res) > 0:
             exact_match = next((item for item in res if item['symbol'] == query.upper()), None)
             if exact_match:
                 selected_ticker = exact_match['symbol']
                 # We simply show the found ticker, no complex selectbox needed if exact match
                 st.success(f"Selected: {selected_ticker} - {exact_match['name']}")
             else:
                 # Fallback to selectbox if ambiguous
                 options = [f"{r['symbol']} - {r['name']}" for r in res]
                 choice = st.selectbox("Did you mean:", options)
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
