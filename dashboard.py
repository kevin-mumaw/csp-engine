# ============================================================
# CSP ENGINE — Streamlit Dashboard
# File: dashboard.py
# Purpose: Visual front-end for the HOOD CSP Scanner,
#          Roll Engine, and Trade Log
# Run with: py -m streamlit run dashboard.py
# Data: Price/HV via yfinance | Options via Tradier
# Last Updated: 2026-06-01
# ============================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
from scipy.stats import norm
from datetime import datetime, date
from dotenv import load_dotenv

# ── LOAD API KEY ─────────────────────────────────────────────
try:
    TRADIER_API_KEY = st.secrets["TRADIER_API_KEY"]
except:
    load_dotenv()
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY")

TRADIER_BASE = "https://api.tradier.com/v1"

# ── PAGE CONFIG ──────────────────────────────────────────────
st.set_page_config(
    page_title="CSP Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CONSTANTS ────────────────────────────────────────────────
LOG_FILE   = "csp_trade_log.csv"
MULTIPLIER = 100

LOG_COLUMNS = [
    "log_id", "timestamp", "event_type", "ticker", "contracts",
    "strike", "expiration", "dte_at_event", "stock_price",
    "premium_per_share", "premium_total", "buyback_per_share",
    "buyback_total", "net_credit_per_share", "net_credit_total",
    "cumulative_premium", "notes",
]

# ════════════════════════════════════════════════════════════
# TRADIER DATA LAYER
# ════════════════════════════════════════════════════════════

HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json",
}

def tradier_get_expirations(ticker):
    """
    Fetch available options expiration dates for a ticker.
    Returns a sorted list of date strings (YYYY-MM-DD).
    Works 24/7 with Tradier sandbox.
    """
    url    = f"{TRADIER_BASE}/markets/options/expirations"
    params = {"symbol": ticker.upper(), "includeAllRoots": "true"}
    try:
        r    = requests.get(url, headers=HEADERS, params=params, timeout=10)
        data = r.json()
        expirations = data.get("expirations", {})
        if not expirations or expirations == "null":
            return []
        dates = expirations.get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        return sorted(dates)
    except Exception as e:
        st.error(f"Tradier expiration fetch error: {e}")
        return []


def tradier_get_puts(ticker, expiration):
    """
    Fetch full put options chain for a specific expiration.
    Returns a DataFrame with strike, bid, ask, IV, OI, volume, greeks.
    One call returns everything — much simpler than Polygon.
    """
    url    = f"{TRADIER_BASE}/markets/options/chains"
    params = {
        "symbol":     ticker.upper(),
        "expiration": expiration,
        "greeks":     "true",
    }
    try:
        r    = requests.get(url, headers=HEADERS, params=params, timeout=10)
        data = r.json()
        options = data.get("options", {})
        if not options or options == "null":
            return pd.DataFrame()

        all_options = options.get("option", [])
        if isinstance(all_options, dict):
            all_options = [all_options]

        # Filter to puts only
        puts = [o for o in all_options if o.get("option_type") == "put"]
        if not puts:
            return pd.DataFrame()

        rows = []
        for o in puts:
            greeks = o.get("greeks") or {}
            rows.append({
                "strike":            float(o.get("strike", 0)),
                "expiration":        expiration,
                "bid":               float(o.get("bid", 0) or 0),
                "ask":               float(o.get("ask", 0) or 0),
                "impliedVolatility": float(o.get("implied_volatility", 0) or 0),
                "openInterest":      int(o.get("open_interest", 0) or 0),
                "volume":            int(o.get("volume", 0) or 0),
                "delta":             float(greeks.get("delta", 0) or 0),
                "theta":             float(greeks.get("theta", 0) or 0),
            })

        df = pd.DataFrame(rows)
        df["mid_premium"] = (df["bid"] + df["ask"]) / 2
        return df.sort_values("strike").reset_index(drop=True)

    except Exception as e:
        st.error(f"Tradier chain fetch error: {e}")
        return pd.DataFrame()


# ════════════════════════════════════════════════════════════
# SHARED HELPERS
# ════════════════════════════════════════════════════════════

def load_log():
    if os.path.exists(LOG_FILE):
        return pd.read_csv(LOG_FILE)
    return pd.DataFrame(columns=LOG_COLUMNS)


def save_log(df):
    df.to_csv(LOG_FILE, index=False)


def moneyness_delta_proxy(strike, price, iv, dte_days):
    """Approximate put delta using Black-Scholes d1 proxy."""
    if iv <= 0 or dte_days <= 0:
        return np.nan
    T  = dte_days / 365
    d1 = (np.log(price / strike) + 0.5 * iv**2 * T) / (iv * np.sqrt(T))
    return abs(norm.cdf(d1) - 1)


def append_log_event(df, event_type, ticker, contracts, strike, expiration,
                     dte_at_event, stock_price, premium_per_share=0.0,
                     buyback_per_share=0.0, notes=""):
    premium_total    = round(premium_per_share * contracts * MULTIPLIER, 2)
    buyback_total    = round(buyback_per_share * contracts * MULTIPLIER, 2)
    net_credit_per   = round(premium_per_share - buyback_per_share, 4)
    net_credit_total = round(net_credit_per * contracts * MULTIPLIER, 2)
    prior_cum        = float(df["net_credit_total"].sum()) if not df.empty else 0.0
    cumulative       = round(prior_cum + net_credit_total, 2)

    new_row = {
        "log_id":               len(df) + 1,
        "timestamp":            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event_type":           event_type,
        "ticker":               ticker,
        "contracts":            contracts,
        "strike":               strike,
        "expiration":           expiration,
        "dte_at_event":         dte_at_event,
        "stock_price":          stock_price,
        "premium_per_share":    premium_per_share,
        "premium_total":        premium_total,
        "buyback_per_share":    buyback_per_share,
        "buyback_total":        buyback_total,
        "net_credit_per_share": net_credit_per,
        "net_credit_total":     net_credit_total,
        "cumulative_premium":   cumulative,
        "notes":                notes,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_log(df)
    return df


# ── API KEY CHECK ────────────────────────────────────────────
if not TRADIER_API_KEY:
    st.error("⚠️ TRADIER_API_KEY not found. Add it to your Streamlit secrets.")
    st.stop()

# ── SIDEBAR CONFIG ───────────────────────────────────────────
st.sidebar.title("⚙️ Configuration")
ticker       = st.sidebar.text_input("Ticker", value="HOOD").upper()
ma_short     = st.sidebar.number_input("Short MA (days)", value=20, min_value=5)
ma_long      = st.sidebar.number_input("Long MA (days)", value=50, min_value=10)
delta_min    = st.sidebar.slider("Delta Min", 0.10, 0.40, 0.15)
delta_max    = st.sidebar.slider("Delta Max", 0.10, 0.50, 0.35)
min_premium  = st.sidebar.number_input("Min Premium ($)", value=0.75, step=0.25)
dte_min      = st.sidebar.number_input("DTE Min", value=5, min_value=1)
dte_max      = st.sidebar.number_input("DTE Max", value=14, min_value=2)
iv_hv_ratio  = st.sidebar.number_input("IV/HV Ratio Min", value=1.10, step=0.05)
roll_trigger = st.sidebar.number_input("Roll Trigger (%)", value=4.0, step=0.5) / 100

st.sidebar.markdown("---")
st.sidebar.caption("CSP Engine v1.3 — Tradier Data")

# ── TABS ─────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📡 Scanner", "🔄 Roll Engine", "📝 Trade Log", "📊 Performance"])


# ════════════════════════════════════════════════════════════
# TAB 1 — SCANNER
# ════════════════════════════════════════════════════════════
with tab1:
    st.header(f"📡 CSP Scanner — {ticker}")

    if st.button("▶ Run Scan", type="primary"):
        with st.spinner("Fetching price and options data..."):

            # ── Price & Trend (yfinance) ─────────────────────
            raw = yf.download(ticker, period="90d", interval="1d", progress=False)
            if raw.empty:
                st.error(f"No price data returned for {ticker}.")
                st.stop()

            close         = raw["Close"].squeeze()
            current_price = float(close.iloc[-1])
            ma_s          = float(close.rolling(ma_short).mean().iloc[-1])
            ma_l          = float(close.rolling(ma_long).mean().iloc[-1])
            trend_pass    = (current_price > ma_s) and (current_price > ma_l) and (ma_s > ma_l)

            log_returns = np.log(close / close.shift(1)).dropna()
            hv_30       = float(log_returns[-30:].std() * np.sqrt(252))

            # ── Expirations via Tradier ──────────────────────
            today      = date.today()
            all_exps   = tradier_get_expirations(ticker)
            valid_exps = [
                (e, (datetime.strptime(e, "%Y-%m-%d").date() - today).days)
                for e in all_exps
                if dte_min <= (datetime.strptime(e, "%Y-%m-%d").date() - today).days <= dte_max
            ]

            chain_available = False
            filtered = pd.DataFrame()
            dc       = pd.DataFrame()
            best_strike = None
            iv_pass  = False
            iv_hv_actual = 0
            current_iv   = 0
            iv_missing   = False

            if not valid_exps:
                st.warning(f"No expirations in {dte_min}–{dte_max} DTE window.")
                st.info(f"Nearest available: {all_exps[:6]}")
            else:
                all_puts = []
                for exp, dte in valid_exps:
                    puts = tradier_get_puts(ticker, exp)
                    if not puts.empty:
                        puts["dte"] = dte
                        all_puts.append(puts)

                if not all_puts:
                    st.warning("Options chain returned no data from Tradier.")
                else:
                    puts_df  = pd.concat(all_puts, ignore_index=True)
                    filtered = puts_df[
                        (puts_df["strike"] >= current_price * 0.80) &
                        (puts_df["strike"] <= current_price * 1.05) &
                        (puts_df["bid"]    >= min_premium)
                    ].copy()

                    current_iv   = float(filtered["impliedVolatility"].median()) if not filtered.empty else 0
                    # If Tradier returns zero IV, bypass IV filter and flag it
                    if current_iv == 0:
                        iv_hv_actual = 0
                        iv_pass      = True
                        iv_missing   = True
                    else:
                        iv_hv_actual = current_iv / hv_30 if hv_30 > 0 else 0
                        iv_pass      = iv_hv_actual >= iv_hv_ratio
                        iv_missing   = False
                    chain_available = not filtered.empty

                    if chain_available:
                        # Use real delta from Tradier if available, else proxy
                        if filtered["delta"].abs().sum() > 0:
                            filtered["delta_proxy"] = filtered["delta"].abs()
                        else:
                            filtered["delta_proxy"] = filtered.apply(
                                lambda r: moneyness_delta_proxy(
                                    r["strike"], current_price,
                                    r["impliedVolatility"], r["dte"]
                                ), axis=1
                            )

                        dc = filtered[
                            (filtered["delta_proxy"] >= delta_min) &
                            (filtered["delta_proxy"] <= delta_max)
                        ].copy()

                        if not dc.empty:
                            for col in ["mid_premium", "openInterest", "volume"]:
                                mn, mx = dc[col].min(), dc[col].max()
                                dc[f"{col}_score"] = (dc[col] - mn) / (mx - mn) if mx > mn else 1.0
                            dc["score"] = (
                                dc["mid_premium_score"] * 0.40 +
                                dc["openInterest_score"] * 0.30 +
                                dc["volume_score"]       * 0.30
                            )
                            dc          = dc.sort_values("score", ascending=False)
                            best        = dc.iloc[0]
                            best_strike = best["strike"]

            # ── Display Metrics ──────────────────────────────
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current Price", f"${current_price:.2f}")
            col2.metric(f"{ma_short}d MA", f"${ma_s:.2f}")
            col3.metric(f"{ma_long}d MA", f"${ma_l:.2f}")
            col4.metric("30d HV", f"{hv_30*100:.1f}%")

            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            c1.metric("Trend Filter", "✅ PASS" if trend_pass else "❌ FAIL")
            if chain_available:
                if iv_missing:
                    c2.metric("IV Filter", "⚠️ BYPASSED", "IV data unavailable from Tradier")
                    c3.metric("Chain IV (median)", "N/A")
                else:
                    c2.metric("IV Filter", "✅ PASS" if iv_pass else "❌ FAIL",
                              f"IV/HV: {iv_hv_actual:.2f}x")
                    c3.metric("Chain IV (median)", f"{current_iv*100:.1f}%")

            st.markdown("---")

            all_pass = trend_pass and chain_available and iv_pass and best_strike is not None

            if all_pass:
                st.success("✅ SIGNAL: GO — All conditions met")
                r1, r2, r3, r4, r5 = st.columns(5)
                r1.metric("Recommended Strike", f"${best['strike']}")
                r2.metric("Expiration",          best["expiration"])
                r3.metric("DTE",                 int(best["dte"]))
                r4.metric("Est. Premium (mid)",  f"${best['mid_premium']:.2f}")
                r5.metric("Delta",               f"{best['delta_proxy']:.3f}")
                roll_price = round(current_price * (1 + roll_trigger), 2)
                st.info(f"🔄 Roll trigger at ${roll_price} (+{int(roll_trigger*100)}% from current price)")
            else:
                st.error("❌ SIGNAL: NO-GO — Conditions not met")
                reasons = []
                if not trend_pass:      reasons.append("Bearish trend structure")
                if not chain_available: reasons.append("No options data returned from Tradier")
                elif not iv_pass:       reasons.append("IV not elevated enough vs historical vol")
                if chain_available and best_strike is None:
                    reasons.append("No strikes found in target delta range")
                for r in reasons:
                    st.warning(f"• {r}")

            if not dc.empty:
                st.markdown("#### Strike Candidates")
                st.dataframe(
                    dc[["strike", "expiration", "dte", "bid", "ask",
                        "mid_premium", "delta_proxy", "delta", "theta",
                        "openInterest", "volume", "score"]].round(3),
                    use_container_width=True,
                    hide_index=True,
                )


# ════════════════════════════════════════════════════════════
# TAB 2 — ROLL ENGINE
# ════════════════════════════════════════════════════════════
with tab2:
    st.header("🔄 Roll Engine")
    st.caption("Enter your open position to evaluate roll conditions.")

    re_ticker   = st.text_input("Ticker", value="HOOD", key="re_ticker").upper()
    re_exps     = tradier_get_expirations(re_ticker) if re_ticker else []
    today       = date.today()
    future_exps = [e for e in re_exps if datetime.strptime(e, "%Y-%m-%d").date() >= today]

    with st.form("roll_form"):
        col1, col2 = st.columns(2)
        r_contracts   = col1.number_input("Contracts", value=3, min_value=1)
        r_entry_prem  = col1.number_input("Entry Premium ($/share)", value=1.50, step=0.05)
        r_entry_price = col1.number_input("Entry Stock Price ($)", value=76.00, step=0.50)
        r_strike      = col2.number_input("Entry Strike ($)", value=71.00, step=0.50)
        r_expiration  = col2.selectbox("Expiration", future_exps) if future_exps else col2.text_input("Expiration (YYYY-MM-DD)", value="")
        submitted     = st.form_submit_button("▶ Evaluate Roll", type="primary")

    if submitted and r_expiration:
        with st.spinner("Evaluating roll conditions..."):
            try:
                exp_date      = datetime.strptime(r_expiration, "%Y-%m-%d").date()
                dte_remaining = (exp_date - date.today()).days

                raw2      = yf.download(re_ticker, period="5d", interval="1d", progress=False)
                cur_price = float(raw2["Close"].squeeze().iloc[-1])
                price_move_pct = (cur_price - r_entry_price) / r_entry_price

                puts2 = tradier_get_puts(re_ticker, r_expiration)

                if puts2.empty:
                    st.warning("No options data returned from Tradier.")
                    buyback_cost = None
                else:
                    row = puts2[puts2["strike"] == r_strike]
                    buyback_cost = float(row["ask"].iloc[0]) if not row.empty else None

                move_ok    = price_move_pct >= roll_trigger
                buyback_ok = (buyback_cost is not None) and (buyback_cost <= r_entry_prem * 0.25)
                dte_ok     = dte_remaining >= 2
                triggered  = move_ok and buyback_ok and dte_ok

                st.markdown("#### Roll Conditions")
                m1, m2, m3 = st.columns(3)
                m1.metric("Price Move", f"{price_move_pct*100:.1f}%",
                          f"Need +{int(roll_trigger*100)}%",
                          delta_color="normal" if move_ok else "inverse")
                m2.metric("Buyback Cost",
                          f"${buyback_cost:.2f}/sh" if buyback_cost is not None else "N/A",
                          f"Max ${r_entry_prem*0.25:.2f}",
                          delta_color="normal" if buyback_ok else "inverse")
                m3.metric("DTE Remaining", dte_remaining,
                          "OK" if dte_ok else "Too close",
                          delta_color="normal" if dte_ok else "inverse")

                st.markdown("---")

                if not triggered:
                    st.error("❌ Roll not triggered — hold your position.")
                    if not move_ok:    st.warning(f"• Stock hasn't moved +{int(roll_trigger*100)}% from entry")
                    if not buyback_ok: st.warning("• Buyback too expensive — wait for more decay")
                    if not dte_ok:     st.warning("• Too close to expiration to roll")
                else:
                    st.success("✅ Roll conditions met — finding best target...")

                    candidates = puts2[
                        (puts2["strike"] > r_strike) &
                        (puts2["strike"] <= cur_price * 1.02) &
                        (puts2["bid"] > 0)
                    ].copy()

                    candidates["net_credit_share"] = candidates["mid_premium"] - buyback_cost
                    candidates["net_credit_total"] = candidates["net_credit_share"] * r_contracts * MULTIPLIER
                    candidates["delta_proxy"]      = candidates["delta"].abs() if candidates["delta"].abs().sum() > 0 else candidates.apply(
                        lambda r: moneyness_delta_proxy(r["strike"], cur_price, r["impliedVolatility"], dte_remaining),
                        axis=1
                    )

                    credit_only = candidates[candidates["net_credit_share"] > 0].copy()

                    if credit_only.empty:
                        st.warning("No credit rolls available. Wait for more premium decay or a further move up.")
                    else:
                        credit_only["delta_score"] = (1 - abs(credit_only["delta_proxy"] - 0.25) / 0.25).clip(0, 1)
                        for col in ["net_credit_share", "openInterest"]:
                            mn, mx = credit_only[col].min(), credit_only[col].max()
                            credit_only[f"{col}_score"] = (credit_only[col] - mn) / (mx - mn) if mx > mn else 1.0
                        credit_only["score"] = (
                            credit_only["net_credit_share_score"] * 0.50 +
                            credit_only["delta_score"]             * 0.30 +
                            credit_only["openInterest_score"]      * 0.20
                        )
                        credit_only = credit_only.sort_values("score", ascending=False)
                        best_roll   = credit_only.iloc[0]

                        st.markdown("#### Roll Recommendation")
                        b1, b2, b3, b4 = st.columns(4)
                        b1.metric("New Strike",   f"${best_roll['strike']}")
                        b2.metric("New Premium",  f"${best_roll['mid_premium']:.2f}/sh")
                        b3.metric("Net Credit",   f"${best_roll['net_credit_share']:.2f}/sh")
                        b4.metric("Total Credit", f"${best_roll['net_credit_total']:.2f}")

                        st.dataframe(
                            credit_only[["strike", "mid_premium", "delta_proxy",
                                         "net_credit_share", "net_credit_total",
                                         "openInterest", "score"]].round(3),
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.info("⚠️ Verify fills on thinkorswim. Always use a limit order — never market order.")

            except Exception as e:
                st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 3 — TRADE LOG
# ════════════════════════════════════════════════════════════
with tab3:
    st.header("📝 Trade Log")

    if "trade_log" not in st.session_state:
        st.session_state.trade_log = load_log()

    log_df = st.session_state.trade_log

    with st.expander("➕ Log New Trade Event", expanded=False):
        with st.form("log_form"):
            lc1, lc2, lc3 = st.columns(3)
            l_event     = lc1.selectbox("Event Type", ["ENTRY", "ROLL", "EXIT", "EXPIRED"])
            l_ticker    = lc1.text_input("Ticker", value="HOOD")
            l_contracts = lc1.number_input("Contracts", value=3, min_value=1)
            l_strike    = lc2.number_input("Strike ($)", value=71.00, step=0.50)
            l_exp       = lc2.text_input("Expiration (YYYY-MM-DD)", value="2026-06-05")
            l_dte       = lc2.number_input("DTE at Event", value=7, min_value=0)
            l_price     = lc3.number_input("Stock Price ($)", value=76.00, step=0.50)
            l_prem      = lc3.number_input("Premium ($/share)", value=1.50, step=0.05)
            l_buyback   = lc3.number_input("Buyback ($/share)", value=0.0, step=0.05)
            l_notes     = st.text_input("Notes", value="")
            log_submitted = st.form_submit_button("Log Event", type="primary")

        if log_submitted:
            st.session_state.trade_log = append_log_event(
                st.session_state.trade_log,
                l_event, l_ticker.upper(), l_contracts, l_strike,
                l_exp, l_dte, l_price, l_prem, l_buyback, l_notes
            )
            st.success(f"✅ {l_event} logged successfully.")
            log_df = st.session_state.trade_log

    if log_df.empty:
        st.info("No trades logged yet. Use the form above to log your first entry.")
    else:
        st.dataframe(
            log_df[[
                "log_id", "timestamp", "event_type", "ticker", "contracts",
                "strike", "expiration", "stock_price", "net_credit_per_share",
                "net_credit_total", "cumulative_premium", "notes"
            ]],
            use_container_width=True,
            hide_index=True,
        )
        csv_data = log_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download Trade Log (CSV)",
            data=csv_data,
            file_name="csp_trade_log.csv",
            mime="text/csv",
        )


# ════════════════════════════════════════════════════════════
# TAB 4 — PERFORMANCE
# ════════════════════════════════════════════════════════════
with tab4:
    st.header("📊 Performance Summary")

    log_df = st.session_state.trade_log if "trade_log" in st.session_state else load_log()

    if log_df.empty:
        st.info("No trades logged yet. Performance stats will appear here once you start logging.")
    else:
        total_premium = round(float(log_df["net_credit_total"].sum()), 2)
        entries       = log_df[log_df["event_type"] == "ENTRY"]
        rolls         = log_df[log_df["event_type"] == "ROLL"]

        cycle_pnl      = log_df.groupby("expiration")["net_credit_total"].sum()
        winning_cycles = int((cycle_pnl > 0).sum())
        total_cycles   = len(cycle_pnl)
        win_rate       = round(winning_cycles / total_cycles * 100, 1) if total_cycles > 0 else 0
        avg_entry_prem = round(float(entries["premium_per_share"].mean()), 2) if not entries.empty else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Premium",     f"${total_premium}")
        m2.metric("Win Rate",          f"{win_rate}%")
        m3.metric("Completed Cycles",  total_cycles)
        m4.metric("Total Rolls",       len(rolls))
        m5.metric("Avg Entry Premium", f"${avg_entry_prem}/sh")

        st.markdown("---")

        if len(log_df) > 1:
            st.markdown("#### Cumulative Premium Collected")
            chart_data = log_df[["timestamp", "cumulative_premium"]].copy()
            chart_data["timestamp"] = pd.to_datetime(chart_data["timestamp"])
            chart_data = chart_data.set_index("timestamp")
            st.line_chart(chart_data)

        st.markdown("#### Premium by Expiration Cycle")
        cycle_summary = log_df.groupby("expiration").agg(
            events     =("log_id", "count"),
            rolls      =("event_type", lambda x: (x == "ROLL").sum()),
            net_premium=("net_credit_total", "sum"),
        ).reset_index()
        cycle_summary["net_premium"] = cycle_summary["net_premium"].round(2)
        cycle_summary["result"]      = cycle_summary["net_premium"].apply(
            lambda x: "✅ Win" if x > 0 else "❌ Loss"
        )
        st.dataframe(cycle_summary, use_container_width=True, hide_index=True)
