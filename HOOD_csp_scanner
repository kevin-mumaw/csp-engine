# ============================================================
# HOOD CSP SCANNER — Google Colab Notebook
# File: HOOD_CSP_Scanner.py
# Purpose: Evaluate cash-secured put entry conditions for HOOD
#          each morning before market open
# Last Updated: 2026-05-28
# ============================================================
# PASTE EACH BLOCK INTO A SEPARATE COLAB CELL
# Each cell is labeled with: [CELL X — NAME]
# ============================================================


# ============================================================
# [CELL 1 — INSTALLS & IMPORTS]
# Purpose: Install required libraries and import dependencies
# Dependencies: None (run this first, every session)
# ============================================================

# Install yfinance if not already present
# In Colab, yfinance may need reinstalling each session
# !pip install yfinance --quiet   # <-- uncomment if needed

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

print("[CELL 1] Imports successful.")


# ============================================================
# [CELL 2 — CONFIGURATION]
# Purpose: All tunable parameters live here. Adjust this cell
#          to change behavior without touching scanner logic.
# Dependencies: Cell 1
# ============================================================

CONFIG = {
    # --- Ticker ---
    "ticker": "HOOD",

    # --- Trend Filter ---
    "ma_short": 20,          # Short-term MA period (days)
    "ma_long": 50,           # Long-term MA period (days)

    # --- Delta Range for Strike Selection ---
    # Target puts in this delta range (absolute value)
    # 0.20 = safer/further OTM, 0.30 = closer to ATM
    "delta_min": 0.15,
    "delta_max": 0.35,

    # --- Premium Filter ---
    "min_premium": 0.75,     # Minimum acceptable premium per contract ($)

    # --- IV Filter ---
    # IV approximation: flag if current IV > this % above recent HV
    # e.g. 1.10 = current IV at least 10% above 30-day HV
    "iv_hv_ratio_min": 1.10,

    # --- Roll Trigger ---
    # If stock moves up this % from entry price, evaluate rolling
    "roll_trigger_pct": 0.04,   # 4% move up

    # --- Expiration Preference ---
    # Target DTE range (days to expiration)
    "dte_min": 5,
    "dte_max": 14,
}

print("[CELL 2] Configuration loaded.")
print(f"         Ticker: {CONFIG['ticker']}")
print(f"         MA Filter: {CONFIG['ma_short']}d / {CONFIG['ma_long']}d")
print(f"         Target Delta Range: {CONFIG['delta_min']} – {CONFIG['delta_max']}")
print(f"         Min Premium: ${CONFIG['min_premium']}")
print(f"         DTE Window: {CONFIG['dte_min']}–{CONFIG['dte_max']} days")


# ============================================================
# [CELL 3 — PRICE & TREND DATA]
# Purpose: Pull current price and calculate moving averages.
#          Determines if the trend filter passes.
# Dependencies: Cell 1, Cell 2
# Output: price_data dict, trend_pass (bool)
# ============================================================

ticker = CONFIG["ticker"]

# Pull 90 days of daily price history
raw = yf.download(ticker, period="90d", interval="1d", progress=False)

if raw.empty:
    print(f"[CELL 3] ERROR: No price data returned for {ticker}. Check ticker symbol.")
else:
    close = raw["Close"].squeeze()

    current_price = float(close.iloc[-1])
    ma_short = float(close.rolling(CONFIG["ma_short"]).mean().iloc[-1])
    ma_long  = float(close.rolling(CONFIG["ma_long"]).mean().iloc[-1])

    # Trend pass: price above both MAs AND short MA above long MA
    trend_pass = (current_price > ma_short) and (current_price > ma_long) and (ma_short > ma_long)

    price_data = {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "ma_short": round(ma_short, 2),
        "ma_long": round(ma_long, 2),
        "trend_pass": trend_pass,
    }

    print(f"[CELL 3] Price & Trend Data — {ticker}")
    print(f"         Current Price : ${price_data['current_price']}")
    print(f"         {CONFIG['ma_short']}-Day MA      : ${price_data['ma_short']}")
    print(f"         {CONFIG['ma_long']}-Day MA      : ${price_data['ma_long']}")
    print(f"         Trend Filter  : {'✅ PASS' if trend_pass else '❌ FAIL (bearish structure — avoid selling puts)'}")


# ============================================================
# [CELL 4 — OPTIONS CHAIN PULL]
# Purpose: Fetch the put options chain for expirations within
#          the configured DTE window. Filters by strike range
#          near current price.
# Dependencies: Cell 1, Cell 2, Cell 3
# Output: filtered_puts DataFrame
# ============================================================

tk = yf.Ticker(ticker)
today = datetime.today().date()

# Get available expiration dates
all_expirations = tk.options
if not all_expirations:
    print(f"[CELL 4] ERROR: No options data available for {ticker}.")
else:
    # Filter to expirations within DTE window
    valid_expirations = []
    for exp in all_expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        if CONFIG["dte_min"] <= dte <= CONFIG["dte_max"]:
            valid_expirations.append((exp, dte))

    if not valid_expirations:
        print(f"[CELL 4] No expirations found in {CONFIG['dte_min']}–{CONFIG['dte_max']} DTE window.")
        print(f"         Available expirations: {all_expirations[:6]}")
    else:
        print(f"[CELL 4] Found {len(valid_expirations)} expiration(s) in target DTE window:")
        for exp, dte in valid_expirations:
            print(f"         {exp} ({dte} DTE)")

        # Pull puts for each valid expiration
        all_puts = []
        for exp, dte in valid_expirations:
            chain = tk.option_chain(exp)
            puts = chain.puts.copy()
            puts["expiration"] = exp
            puts["dte"] = dte
            all_puts.append(puts)

        puts_df = pd.concat(all_puts, ignore_index=True)

        # Filter: strikes within ±20% of current price (avoids deep ITM/OTM noise)
        price = price_data["current_price"]
        strike_min = price * 0.80
        strike_max = price * 1.05   # Slightly above for near-ATM consideration

        filtered_puts = puts_df[
            (puts_df["strike"] >= strike_min) &
            (puts_df["strike"] <= strike_max) &
            (puts_df["bid"] >= CONFIG["min_premium"])
        ].copy()

        # Mid-price as premium estimate
        filtered_puts["mid_premium"] = (filtered_puts["bid"] + filtered_puts["ask"]) / 2

        print(f"\n[CELL 4] Puts after strike/premium filter: {len(filtered_puts)} contracts")
        if not filtered_puts.empty:
            print(filtered_puts[["strike", "expiration", "dte", "bid", "ask", "mid_premium", "impliedVolatility", "openInterest", "volume"]].to_string(index=False))


# ============================================================
# [CELL 5 — IV APPROXIMATION & PREMIUM QUALITY]
# Purpose: Approximate IV Rank using current avg chain IV vs
#          30-day historical volatility. Flags if premium
#          environment is favorable for selling.
# Note: True IV Rank requires paid data. This is a proxy.
# Dependencies: Cell 1, Cell 2, Cell 3, Cell 4
# Output: iv_data dict, iv_pass (bool)
# ============================================================

# Historical Volatility (30-day annualized)
log_returns = np.log(close / close.shift(1)).dropna()
hv_30 = float(log_returns[-30:].std() * np.sqrt(252))

# Current IV: median of filtered puts' implied volatility
if filtered_puts.empty:
    print("[CELL 5] WARNING: No filtered puts available — cannot assess IV.")
    iv_pass = False
    iv_data = {}
else:
    current_iv = float(filtered_puts["impliedVolatility"].median())
    iv_hv_ratio = current_iv / hv_30 if hv_30 > 0 else 0
    iv_pass = iv_hv_ratio >= CONFIG["iv_hv_ratio_min"]

    iv_data = {
        "current_iv": round(current_iv, 4),
        "hv_30": round(hv_30, 4),
        "iv_hv_ratio": round(iv_hv_ratio, 2),
        "iv_pass": iv_pass,
    }

    print(f"[CELL 5] IV & Premium Quality — {ticker}")
    print(f"         Current Chain IV (median) : {round(current_iv * 100, 1)}%")
    print(f"         30-Day Historical Vol      : {round(hv_30 * 100, 1)}%")
    print(f"         IV / HV Ratio              : {iv_hv_ratio:.2f}x (min: {CONFIG['iv_hv_ratio_min']}x)")
    print(f"         IV Filter                  : {'✅ PASS — elevated premium environment' if iv_pass else '❌ FAIL — IV not elevated enough to sell'}")


# ============================================================
# [CELL 6 — STRIKE SELECTOR & GO/NO-GO SIGNAL]
# Purpose: Score each candidate strike using delta proxy
#          (moneyness), premium, and OI/volume. Output the
#          recommended strike and a final entry signal.
# Note: True delta requires Black-Scholes; we use moneyness
#       as a proxy since yfinance doesn't return Greeks.
# Dependencies: Cells 1–5
# Output: Final printed recommendation
# ============================================================

def moneyness_delta_proxy(strike, price, iv, dte_days):
    """
    Approximate put delta using log-moneyness.
    Not a substitute for Black-Scholes but directionally accurate
    for OTM puts when screening candidates.
    """
    if iv <= 0 or dte_days <= 0:
        return np.nan
    T = dte_days / 365
    d1 = (np.log(price / strike) + 0.5 * iv**2 * T) / (iv * np.sqrt(T))
    from scipy.stats import norm
    delta_put = norm.cdf(d1) - 1   # Put delta is negative
    return abs(delta_put)           # Return absolute value for easier filtering

if filtered_puts.empty or not iv_data:
    print("[CELL 6] Cannot generate signal — no valid puts found.")
else:
    price = price_data["current_price"]

    # Calculate delta proxy for each candidate
    filtered_puts["delta_proxy"] = filtered_puts.apply(
        lambda row: moneyness_delta_proxy(
            row["strike"], price,
            row["impliedVolatility"], row["dte"]
        ), axis=1
    )

    # Apply delta range filter
    delta_candidates = filtered_puts[
        (filtered_puts["delta_proxy"] >= CONFIG["delta_min"]) &
        (filtered_puts["delta_proxy"] <= CONFIG["delta_max"])
    ].copy()

    print(f"[CELL 6] Strike Candidates in Delta Range ({CONFIG['delta_min']}–{CONFIG['delta_max']}):")

    if delta_candidates.empty:
        print("         No strikes found in target delta range.")
        print("         Consider widening delta_min/delta_max in CONFIG.")
        best_strike = None
    else:
        # Score: weight premium (40%), OI (30%), volume (30%)
        dc = delta_candidates.copy()
        for col in ["mid_premium", "openInterest", "volume"]:
            col_min = dc[col].min()
            col_max = dc[col].max()
            if col_max > col_min:
                dc[f"{col}_score"] = (dc[col] - col_min) / (col_max - col_min)
            else:
                dc[f"{col}_score"] = 1.0

        dc["composite_score"] = (
            dc["mid_premium_score"] * 0.40 +
            dc["openInterest_score"] * 0.30 +
            dc["volume_score"] * 0.30
        )

        dc_sorted = dc.sort_values("composite_score", ascending=False)
        print(dc_sorted[["strike", "expiration", "dte", "mid_premium", "delta_proxy", "openInterest", "volume", "composite_score"]].to_string(index=False))

        best = dc_sorted.iloc[0]
        best_strike = best["strike"]
        best_premium = best["mid_premium"]
        best_exp = best["expiration"]
        best_dte = best["dte"]
        best_delta = best["delta_proxy"]

    # ── FINAL GO / NO-GO SIGNAL ──────────────────────────────
    print("\n" + "=" * 56)
    print("  FINAL SIGNAL SUMMARY")
    print("=" * 56)
    print(f"  Ticker        : {ticker}")
    print(f"  Current Price : ${price_data['current_price']}")
    print(f"  Trend Filter  : {'✅ PASS' if price_data['trend_pass'] else '❌ FAIL'}")
    print(f"  IV Filter     : {'✅ PASS' if iv_data.get('iv_pass') else '❌ FAIL'}")

    all_pass = price_data["trend_pass"] and iv_data.get("iv_pass") and best_strike is not None

    if all_pass:
        roll_trigger_price = round(price * (1 + CONFIG["roll_trigger_pct"]), 2)
        print(f"\n  ✅ SIGNAL: GO — Conditions met")
        print(f"  ─────────────────────────────────────────────────")
        print(f"  Recommended Strike : ${best_strike}")
        print(f"  Expiration         : {best_exp} ({best_dte} DTE)")
        print(f"  Est. Premium (mid) : ${round(best_premium, 2)} / contract")
        print(f"  Delta Proxy        : {round(best_delta, 3)}")
        print(f"  IV / HV Ratio      : {iv_data['iv_hv_ratio']}x")
        print(f"\n  Roll Trigger       : ${roll_trigger_price} (+{int(CONFIG['roll_trigger_pct']*100)}% from current)")
        print(f"  ─────────────────────────────────────────────────")
        print(f"  NOTE: Verify Greeks and liquidity on thinkorswim")
        print(f"        before placing any order.")
    else:
        reasons = []
        if not price_data["trend_pass"]:
            reasons.append("Bearish trend structure")
        if not iv_data.get("iv_pass"):
            reasons.append("IV not elevated (thin premium)")
        if best_strike is None:
            reasons.append("No strikes in target delta range")
        print(f"\n  ❌ SIGNAL: NO-GO")
        for r in reasons:
            print(f"     • {r}")
        print(f"\n  Wait for better conditions before selling puts.")

    print("=" * 56)
