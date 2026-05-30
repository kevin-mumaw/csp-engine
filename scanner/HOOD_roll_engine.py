# ============================================================
# HOOD CSP ROLL ENGINE — Google Colab Notebook Cells
# File: HOOD_Roll_Engine.py
# Purpose: Given an open CSP position, evaluate whether roll
#          criteria are met and calculate the best roll target
# Depends on: HOOD_CSP_Scanner.py (Cells 1–6 must be run first)
# Last Updated: 2026-05-29
# ============================================================
# PASTE EACH BLOCK INTO A SEPARATE COLAB CELL
# Run AFTER all scanner cells (1–6) have been executed
# ============================================================


# ============================================================
# [CELL 7 — OPEN POSITION INPUT]
# Purpose: Define your current open CSP position manually.
#          Update these values each time you run the roll engine.
# Dependencies: Cell 1 (imports)
# Output: position dict
# ============================================================

position = {
    "ticker": "HOOD",
    "contracts": 3,                  # Number of contracts
    "entry_strike": 71.00,           # Strike you originally sold
    "entry_premium": 1.50,           # Premium collected per share at entry (estimate — update this)
    "total_premium_collected": 3.84, # Running total premium collected including any prior rolls ($)
    "entry_price": 76.00,            # Stock price when you entered
    "expiration": "2026-06-05",      # Current expiration date (YYYY-MM-DD)
    "contracts_multiplier": 100,     # Standard options multiplier
}

# Derived values
position["max_loss"] = position["entry_strike"] * position["contracts"] * position["contracts_multiplier"]
position["total_entry_premium_dollars"] = position["entry_premium"] * position["contracts"] * position["contracts_multiplier"]

print("[CELL 7] Open Position Loaded")
print(f"         Ticker        : {position['ticker']}")
print(f"         Contracts     : {position['contracts']}")
print(f"         Entry Strike  : ${position['entry_strike']}")
print(f"         Entry Premium : ${position['entry_premium']} / share  (${position['total_entry_premium_dollars']} total)")
print(f"         Total Premium Collected (incl. rolls): ${position['total_premium_collected'] * 100:.2f}")
print(f"         Entry Stock Price : ${position['entry_price']}")
print(f"         Expiration    : {position['expiration']}")
print(f"         Max Loss      : ${position['max_loss']:,.2f} (if assigned at strike)")


# ============================================================
# [CELL 8 — ROLL TRIGGER EVALUATION]
# Purpose: Check whether current market conditions meet the
#          criteria to roll the position. Three conditions must
#          all pass: stock move, buyback cost, and DTE check.
# Dependencies: Cell 2 (CONFIG), Cell 3 (price_data), Cell 7 (position)
# Output: roll_eval dict, roll_triggered (bool)
# ============================================================

from datetime import datetime

today = datetime.today().date()
exp_date = datetime.strptime(position["expiration"], "%Y-%m-%d").date()
dte_remaining = (exp_date - today).days

current_price = price_data["current_price"]
entry_price = position["entry_price"]

# --- Condition 1: Stock has moved up enough from entry ---
price_move_pct = (current_price - entry_price) / entry_price
move_condition = price_move_pct >= CONFIG["roll_trigger_pct"]

# --- Condition 2: Buyback cost is low enough ---
# Pull current bid on the open strike to estimate buyback cost
tk = yf.Ticker(position["ticker"])
try:
    chain = tk.option_chain(position["expiration"])
    current_puts = chain.puts
    open_strike_row = current_puts[current_puts["strike"] == position["entry_strike"]]

    if open_strike_row.empty:
        print(f"[CELL 8] WARNING: Strike ${position['entry_strike']} not found in chain for {position['expiration']}.")
        print(f"         It may have been delisted or expiration passed.")
        buyback_cost_per_share = None
        buyback_condition = False
    else:
        # Use ask price as buyback cost (you pay the ask to close)
        buyback_cost_per_share = float(open_strike_row["ask"].iloc[0])
        buyback_total = buyback_cost_per_share * position["contracts"] * position["contracts_multiplier"]

        # Condition: buyback costs less than 25% of original premium collected
        # i.e. you're keeping at least 75% of the original premium
        max_buyback_per_share = position["entry_premium"] * 0.25
        buyback_condition = buyback_cost_per_share <= max_buyback_per_share

except Exception as e:
    print(f"[CELL 8] ERROR fetching current chain: {e}")
    buyback_cost_per_share = None
    buyback_total = None
    buyback_condition = False

# --- Condition 3: Enough DTE remaining to find a roll ---
# Need at least 2 DTE to find a liquid roll target
dte_condition = dte_remaining >= 2

roll_triggered = move_condition and buyback_condition and dte_condition

roll_eval = {
    "current_price": current_price,
    "price_move_pct": round(price_move_pct * 100, 2),
    "move_condition": move_condition,
    "buyback_cost_per_share": buyback_cost_per_share,
    "buyback_total": buyback_total if buyback_cost_per_share else None,
    "buyback_condition": buyback_condition,
    "dte_remaining": dte_remaining,
    "dte_condition": dte_condition,
    "roll_triggered": roll_triggered,
}

print(f"[CELL 8] Roll Trigger Evaluation — {position['ticker']}")
print(f"         Current Price     : ${current_price}")
print(f"         Price Move        : {roll_eval['price_move_pct']}% (trigger: +{int(CONFIG['roll_trigger_pct']*100)}%)")
print(f"         Move Condition    : {'✅ PASS' if move_condition else '❌ FAIL'}")
if buyback_cost_per_share is not None:
    print(f"         Buyback Cost      : ${buyback_cost_per_share} / share  (${buyback_total:.2f} total)")
    print(f"         Buyback Condition : {'✅ PASS' if buyback_condition else '❌ FAIL (too expensive to close)'}")
else:
    print(f"         Buyback Cost      : N/A")
    print(f"         Buyback Condition : ❌ FAIL")
print(f"         DTE Remaining     : {dte_remaining} days")
print(f"         DTE Condition     : {'✅ PASS' if dte_condition else '❌ FAIL (too close to expiration)'}")
print(f"\n         Roll Triggered    : {'✅ YES — proceed to Cell 9' if roll_triggered else '❌ NO — hold position'}")


# ============================================================
# [CELL 9 — ROLL TARGET SELECTION]
# Purpose: If roll is triggered, find the best new strike to
#          roll into on the same expiration. Scores candidates
#          by net credit, delta proxy, and open interest.
# Dependencies: Cells 1–8
# Output: roll_recommendation dict
# ============================================================

from scipy.stats import norm

def moneyness_delta_proxy(strike, price, iv, dte_days):
    """Approximate put delta using log-moneyness (Black-Scholes d1 proxy)."""
    if iv <= 0 or dte_days <= 0:
        return np.nan
    T = dte_days / 365
    d1 = (np.log(price / strike) + 0.5 * iv**2 * T) / (iv * np.sqrt(T))
    return abs(norm.cdf(d1) - 1)

if not roll_triggered:
    print("[CELL 9] Roll not triggered — no action needed.")
    print("         Re-run after conditions change.")
else:
    print(f"[CELL 9] Searching for roll targets on {position['expiration']}...")

    try:
        chain = tk.option_chain(position["expiration"])
        all_puts = chain.puts.copy()
        all_puts["dte"] = dte_remaining

        # Only consider strikes ABOVE the current strike (rolling up)
        roll_candidates = all_puts[
            (all_puts["strike"] > position["entry_strike"]) &
            (all_puts["strike"] <= current_price * 1.02) &  # Don't go ITM
            (all_puts["bid"] > 0)                            # Must have a bid
        ].copy()

        if roll_candidates.empty:
            print("[CELL 9] No valid roll targets found above current strike.")
            print("         The stock may not have moved enough to find a higher strike with premium.")
        else:
            roll_candidates["mid_premium"] = (roll_candidates["bid"] + roll_candidates["ask"]) / 2
            roll_candidates["delta_proxy"] = roll_candidates.apply(
                lambda row: moneyness_delta_proxy(
                    row["strike"], current_price,
                    row["impliedVolatility"], dte_remaining
                ), axis=1
            )

            # Net credit = new premium collected - buyback cost
            roll_candidates["net_credit_per_share"] = roll_candidates["mid_premium"] - buyback_cost_per_share
            roll_candidates["net_credit_total"] = (
                roll_candidates["net_credit_per_share"] *
                position["contracts"] *
                position["contracts_multiplier"]
            )

            # Filter: must result in a net credit (not a debit roll)
            credit_rolls = roll_candidates[roll_candidates["net_credit_per_share"] > 0].copy()

            if credit_rolls.empty:
                print("[CELL 9] ⚠️  No credit rolls available — all roll targets result in a debit.")
                print("         Consider waiting for more premium decay or a further move up.")
            else:
                # Score: weight net credit (50%), delta proximity to 0.25 (30%), OI (20%)
                credit_rolls["delta_score"] = 1 - abs(credit_rolls["delta_proxy"] - 0.25) / 0.25
                credit_rolls["delta_score"] = credit_rolls["delta_score"].clip(0, 1)

                for col in ["net_credit_per_share", "openInterest"]:
                    col_min = credit_rolls[col].min()
                    col_max = credit_rolls[col].max()
                    if col_max > col_min:
                        credit_rolls[f"{col}_score"] = (credit_rolls[col] - col_min) / (col_max - col_min)
                    else:
                        credit_rolls[f"{col}_score"] = 1.0

                credit_rolls["composite_score"] = (
                    credit_rolls["net_credit_per_share_score"] * 0.50 +
                    credit_rolls["delta_score"] * 0.30 +
                    credit_rolls["openInterest_score"] * 0.20
                )

                credit_rolls_sorted = credit_rolls.sort_values("composite_score", ascending=False)

                print("\n         Roll Candidates (credit rolls only, ranked):")
                print(credit_rolls_sorted[[
                    "strike", "mid_premium", "delta_proxy",
                    "net_credit_per_share", "net_credit_total",
                    "openInterest", "composite_score"
                ]].to_string(index=False))

                best_roll = credit_rolls_sorted.iloc[0]
                new_premium_total = position["total_premium_collected"] * 100 + best_roll["net_credit_total"]

                roll_recommendation = {
                    "action": "ROLL",
                    "close_strike": position["entry_strike"],
                    "new_strike": best_roll["strike"],
                    "expiration": position["expiration"],
                    "buyback_cost_total": buyback_total,
                    "new_premium_per_share": round(best_roll["mid_premium"], 2),
                    "net_credit_per_share": round(best_roll["net_credit_per_share"], 2),
                    "net_credit_total": round(best_roll["net_credit_total"], 2),
                    "new_total_premium": round(new_premium_total, 2),
                    "new_delta": round(best_roll["delta_proxy"], 3),
                }

                print(f"\n{'='*56}")
                print(f"  ROLL RECOMMENDATION")
                print(f"{'='*56}")
                print(f"  Action        : Buy back ${roll_recommendation['close_strike']} puts")
                print(f"                  Sell new  ${roll_recommendation['new_strike']} puts")
                print(f"  Expiration    : {roll_recommendation['expiration']}")
                print(f"  Buyback Cost  : ${roll_recommendation['buyback_cost_total']:.2f} total")
                print(f"  New Premium   : ${roll_recommendation['new_premium_per_share']} / share")
                print(f"  Net Credit    : ${roll_recommendation['net_credit_per_share']} / share  (${roll_recommendation['net_credit_total']:.2f} total)")
                print(f"  New Delta     : {roll_recommendation['new_delta']}")
                print(f"\n  Total Premium Collected (all-in): ${roll_recommendation['new_total_premium']:.2f}")
                print(f"{'='*56}")
                print(f"  ⚠️  Verify fills on thinkorswim before executing.")
                print(f"      Use a limit order on the roll — never market order.")
                print(f"{'='*56}")

    except Exception as e:
        print(f"[CELL 9] ERROR: {e}")


# ============================================================
# [CELL 10 — POST-ROLL POSITION UPDATE]
# Purpose: After executing a roll on thinkorswim, update the
#          position dict to reflect the new state. Run this
#          manually after confirming the roll fill.
# Dependencies: Cell 7 (position), Cell 9 (roll_recommendation)
# Output: Updated position dict printed for confirmation
# ============================================================

# ── INSTRUCTIONS ─────────────────────────────────────────
# 1. Execute the roll on thinkorswim first
# 2. Confirm your actual fill prices
# 3. Update actual_buyback and actual_new_premium below
# 4. Run this cell to update your position
# ─────────────────────────────────────────────────────────

actual_buyback_per_share   = 0.10   # ← Update with your actual buyback fill
actual_new_premium_per_share = 1.38  # ← Update with your actual new premium fill

actual_net_credit_per_share = actual_new_premium_per_share - actual_buyback_per_share
actual_net_credit_total = actual_net_credit_per_share * position["contracts"] * position["contracts_multiplier"]

# Update position
if roll_triggered and "roll_recommendation" in dir():
    updated_position = position.copy()
    updated_position["entry_strike"]    = roll_recommendation["new_strike"]
    updated_position["entry_premium"]   = actual_new_premium_per_share
    updated_position["entry_price"]     = current_price
    updated_position["total_premium_collected"] = round(
        position["total_premium_collected"] + actual_net_credit_per_share, 4
    )

    print("[CELL 10] Position Updated After Roll")
    print(f"          Old Strike    : ${position['entry_strike']}  →  New Strike: ${updated_position['entry_strike']}")
    print(f"          Buyback Fill  : ${actual_buyback_per_share} / share")
    print(f"          New Premium   : ${actual_new_premium_per_share} / share")
    print(f"          Net Credit    : ${actual_net_credit_per_share} / share  (${actual_net_credit_total:.2f} total)")
    print(f"          Total Premium Collected: ${updated_position['total_premium_collected'] * position['contracts'] * position['contracts_multiplier']:.2f}")
    print(f"\n          Copy 'updated_position' into Cell 7 for the next session.")
    print(f"          updated_position = {updated_position}")
else:
    print("[CELL 10] No roll was executed — position unchanged.")
    print("          Update actual fill prices above and re-run after executing on thinkorswim.")
