# ============================================================
# HOOD CSP TRADE LOG — Google Colab Notebook Cells
# File: HOOD_Trade_Log.py
# Purpose: Log all entries, rolls, and exits. Track premium
#          collected, win rate, and cycle P&L over time.
# Depends on: HOOD_CSP_Scanner.py (Cell 1 imports)
#             HOOD_Roll_Engine.py (Cell 7 position structure)
# Last Updated: 2026-05-29
# ============================================================
# PASTE EACH BLOCK INTO A SEPARATE COLAB CELL
# Run AFTER scanner and roll engine cells
# ============================================================


# ============================================================
# [CELL 11 — TRADE LOG SETUP & STORAGE]
# Purpose: Initialize the trade log as a CSV file in Colab's
#          working directory. If the file already exists, it
#          loads the existing log. Run once per session.
# Dependencies: Cell 1 (imports)
# Output: trade_log_df DataFrame, log file path
# ============================================================

import os
import csv
from datetime import datetime

LOG_FILE = "/content/csp_trade_log.csv"

LOG_COLUMNS = [
    "log_id",           # Auto-incrementing ID
    "timestamp",        # When this entry was logged
    "event_type",       # ENTRY | ROLL | EXIT | EXPIRED
    "ticker",
    "contracts",
    "strike",           # Strike for this event
    "expiration",
    "dte_at_event",     # DTE when event occurred
    "stock_price",      # Stock price at time of event
    "premium_per_share",# Premium collected (positive) or paid (negative)
    "premium_total",    # premium_per_share * contracts * 100
    "buyback_per_share",# Cost to close (rolls/exits only)
    "buyback_total",
    "net_credit_per_share",  # Net for rolls: new premium - buyback
    "net_credit_total",
    "cumulative_premium",    # Running total premium collected this cycle
    "notes",
]

# Load existing log or create new one
if os.path.exists(LOG_FILE):
    trade_log_df = pd.read_csv(LOG_FILE)
    print(f"[CELL 11] Existing trade log loaded: {len(trade_log_df)} records")
else:
    trade_log_df = pd.DataFrame(columns=LOG_COLUMNS)
    trade_log_df.to_csv(LOG_FILE, index=False)
    print(f"[CELL 11] New trade log created at {LOG_FILE}")

print(f"          Columns: {list(trade_log_df.columns)}")


# ============================================================
# [CELL 12 — LOG ENTRY FUNCTION]
# Purpose: Define the function used to add any event to the
#          trade log. Called by Cells 13, 14, and 15.
# Dependencies: Cell 11
# Output: Function definition (no output until called)
# ============================================================

def log_trade_event(
    event_type,
    ticker,
    contracts,
    strike,
    expiration,
    dte_at_event,
    stock_price,
    premium_per_share=0.0,
    buyback_per_share=0.0,
    notes=""
):
    """
    Append a trade event to the log CSV and update the DataFrame.

    event_type options:
        ENTRY   — Opening a new CSP position
        ROLL    — Rolling to a new strike (same expiration)
        EXIT    — Buying back to close before expiration
        EXPIRED — Position expired worthless (full premium kept)

    Returns the updated trade_log_df.
    """
    global trade_log_df

    multiplier = 100
    premium_total    = round(premium_per_share * contracts * multiplier, 2)
    buyback_total    = round(buyback_per_share * contracts * multiplier, 2)
    net_credit_per   = round(premium_per_share - buyback_per_share, 4)
    net_credit_total = round(net_credit_per * contracts * multiplier, 2)

    # Cumulative premium: sum of all net credits in the log + this event
    prior_cumulative = float(trade_log_df["net_credit_total"].sum()) if not trade_log_df.empty else 0.0
    cumulative = round(prior_cumulative + net_credit_total, 2)

    log_id = len(trade_log_df) + 1
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = {
        "log_id": log_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "ticker": ticker,
        "contracts": contracts,
        "strike": strike,
        "expiration": expiration,
        "dte_at_event": dte_at_event,
        "stock_price": stock_price,
        "premium_per_share": premium_per_share,
        "premium_total": premium_total,
        "buyback_per_share": buyback_per_share,
        "buyback_total": buyback_total,
        "net_credit_per_share": net_credit_per,
        "net_credit_total": net_credit_total,
        "cumulative_premium": cumulative,
        "notes": notes,
    }

    trade_log_df = pd.concat(
        [trade_log_df, pd.DataFrame([new_row])],
        ignore_index=True
    )
    trade_log_df.to_csv(LOG_FILE, index=False)

    print(f"[LOG] {event_type} logged — {ticker} ${strike} | "
          f"Net: ${net_credit_total} | Cumulative: ${cumulative}")

    return trade_log_df

print("[CELL 12] log_trade_event() function ready.")


# ============================================================
# [CELL 13 — LOG A NEW ENTRY]
# Purpose: Call this cell when you open a new CSP position.
#          Update the values below to match your actual trade.
# Dependencies: Cells 11, 12
# ============================================================

# ── UPDATE THESE VALUES BEFORE RUNNING ───────────────────
entry_event = {
    "event_type"        : "ENTRY",
    "ticker"            : "HOOD",
    "contracts"         : 3,
    "strike"            : 71.00,       # Strike you sold
    "expiration"        : "2026-06-05",
    "dte_at_event"      : 7,           # DTE when you entered
    "stock_price"       : 76.00,       # Stock price at entry
    "premium_per_share" : 1.50,        # Premium collected per share
    "buyback_per_share" : 0.0,         # 0 for new entries
    "notes"             : "Initial CSP entry. IV elevated post-earnings.",
}
# ─────────────────────────────────────────────────────────

# Uncomment the line below to log the entry
# log_trade_event(**entry_event)

print("[CELL 13] Entry event defined.")
print("          Edit values above, then uncomment log_trade_event() and run.")


# ============================================================
# [CELL 14 — LOG A ROLL]
# Purpose: Call this cell after executing a roll on thinkorswim.
#          Captures both the buyback and new premium in one event.
# Dependencies: Cells 11, 12
# ============================================================

# ── UPDATE THESE VALUES AFTER YOUR ROLL FILLS ────────────
roll_event = {
    "event_type"        : "ROLL",
    "ticker"            : "HOOD",
    "contracts"         : 3,
    "strike"            : 72.00,       # NEW strike after rolling
    "expiration"        : "2026-06-05",
    "dte_at_event"      : 4,           # DTE when you rolled
    "stock_price"       : 80.00,       # Stock price at roll
    "premium_per_share" : 1.38,        # New premium collected per share
    "buyback_per_share" : 0.10,        # Cost to close old strike per share
    "notes"             : "Rolled $71 -> $72. Stock ran to $80. Net credit roll.",
}
# ─────────────────────────────────────────────────────────

# Uncomment the line below to log the roll
# log_trade_event(**roll_event)

print("[CELL 14] Roll event defined.")
print("          Edit values above, then uncomment log_trade_event() and run.")


# ============================================================
# [CELL 15 — LOG AN EXIT OR EXPIRATION]
# Purpose: Log closing a position early (EXIT) or letting it
#          expire worthless (EXPIRED). For EXPIRED, set
#          buyback_per_share to 0 — you keep all premium.
# Dependencies: Cells 11, 12
# ============================================================

# ── UPDATE THESE VALUES BEFORE RUNNING ───────────────────
exit_event = {
    "event_type"        : "EXPIRED",   # Change to EXIT if closing early
    "ticker"            : "HOOD",
    "contracts"         : 3,
    "strike"            : 72.00,
    "expiration"        : "2026-06-05",
    "dte_at_event"      : 0,
    "stock_price"       : 82.00,       # Stock price at expiration
    "premium_per_share" : 0.0,         # No new premium at exit
    "buyback_per_share" : 0.0,         # 0 if expired worthless
    "notes"             : "Expired worthless. Full premium kept.",
}
# ─────────────────────────────────────────────────────────

# Uncomment the line below to log the exit/expiration
# log_trade_event(**exit_event)

print("[CELL 15] Exit/expiration event defined.")
print("          Edit values above, then uncomment log_trade_event() and run.")


# ============================================================
# [CELL 16 — TRADE LOG SUMMARY & STATS]
# Purpose: Print a full summary of all logged trades with
#          cycle-level P&L, win rate, and premium stats.
#          Run any time to review performance.
# Dependencies: Cell 11
# ============================================================

if trade_log_df.empty:
    print("[CELL 16] Trade log is empty. Log some trades first (Cells 13–15).")
else:
    print("[CELL 16] ── TRADE LOG ──────────────────────────────────────")
    print(trade_log_df[[
        "log_id", "timestamp", "event_type", "ticker",
        "strike", "expiration", "stock_price",
        "net_credit_per_share", "net_credit_total", "cumulative_premium", "notes"
    ]].to_string(index=False))

    print("\n[CELL 16] ── PERFORMANCE SUMMARY ──────────────────────────")

    total_premium     = round(float(trade_log_df["net_credit_total"].sum()), 2)
    total_events      = len(trade_log_df)
    entries           = trade_log_df[trade_log_df["event_type"] == "ENTRY"]
    rolls             = trade_log_df[trade_log_df["event_type"] == "ROLL"]
    exits             = trade_log_df[trade_log_df["event_type"].isin(["EXIT", "EXPIRED"])]

    # Win rate: cycles where total net credit > 0
    # Group by expiration, sum net credits
    if not exits.empty:
        cycle_pnl = trade_log_df.groupby("expiration")["net_credit_total"].sum()
        winning_cycles = int((cycle_pnl > 0).sum())
        total_cycles   = len(cycle_pnl)
        win_rate       = round(winning_cycles / total_cycles * 100, 1) if total_cycles > 0 else 0
    else:
        win_rate = None
        total_cycles = 0
        winning_cycles = 0

    avg_entry_premium = round(float(entries["premium_per_share"].mean()), 2) if not entries.empty else 0
    total_rolls       = len(rolls)

    print(f"          Total Premium Collected : ${total_premium}")
    print(f"          Total Events Logged     : {total_events}")
    print(f"          Entries                 : {len(entries)}")
    print(f"          Rolls                   : {total_rolls}")
    print(f"          Exits / Expirations     : {len(exits)}")
    print(f"          Avg Entry Premium       : ${avg_entry_premium} / share")
    if win_rate is not None:
        print(f"          Win Rate (by cycle)     : {win_rate}% ({winning_cycles}/{total_cycles} cycles)")
    else:
        print(f"          Win Rate                : N/A (no completed cycles yet)")

    print("\n          Premium by Expiration Cycle:")
    if not trade_log_df.empty:
        cycle_summary = trade_log_df.groupby("expiration").agg(
            events=("log_id", "count"),
            rolls=("event_type", lambda x: (x == "ROLL").sum()),
            net_premium=("net_credit_total", "sum"),
        ).reset_index()
        cycle_summary["net_premium"] = cycle_summary["net_premium"].round(2)
        print(cycle_summary.to_string(index=False))

    print("─" * 56)
