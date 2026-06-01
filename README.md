# CSP Engine

A rules-based cash-secured put scanner, roll engine, and trade log built for retail options traders.

## What it does
- **Scanner** — evaluates entry conditions for cash-secured puts using price trend, implied volatility, and delta filters
- **Roll Engine** — given an open position, determines whether roll criteria are met and recommends the best credit roll target
- **Trade Log** — logs entries, rolls, and exits with running premium totals
- **Performance** — tracks win rate, cumulative premium collected, and cycle-by-cycle P&L

## Data
- Price and historical volatility via yfinance
- Options chain data via Polygon.io

## Stack
Python · Streamlit · yfinance · Polygon.io

## Status
Active development — paper trading phase
