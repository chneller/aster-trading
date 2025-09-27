# Aster DEX Pro - Algo v1.0
MicroMaker airdrop farm + Statistical Arbitrage bot

Strategies

- Maker (MicroMaker): Airdrop farming strategy for volume generation only - not profitable - posts symmetric bid/ask around the mid, reprices when the mid drifts, and gates by a minimum natural spread. Best for steady volume with low risk. Key knobs: `--width-ticks`, `--drift-ticks`, `--min-edge-bps`, `--symbol-max-quote`.
- Statistical arbitrage (pairs-meanrev): Aims to be profitable - trades BTCUSDT vs ETHUSDT via a beta‑hedged z‑score spread. Enters when |z| >= z_enter, exits near z_exit or on timeout with reduceOnly market closes. Ensure `--pairs-cap` is high enough to satisfy min order sizes (BTC leg ≈ ≥ 0.001 BTC notional).
- Multi: runs both concurrently with separate caps and a shared daily loss cap. Recommended: one‑way mode, cross margin, and sufficient leverage on the exchange for small balances.
------

Quick start

1) Python 3.10+
2) Create and fill .env

```
cp .env.example .env
```

3) Create a Python virtual environment

```
python3 -m venv .venv
```

4) Activate the virtual environment

```
source .venv/bin/activate
# On Windows (PowerShell): .venv\\Scripts\\Activate.ps1
```

5) Install

```
pip install -e .
```

6) Run

```
aster-trading --help
```

Environment (.env at project root)

```
ASTER_API_KEY=...
ASTER_API_SECRET=...
ASTER_API_BASE=https://fapi.asterdex.com
ASTER_WS_BASE=wss://fstream.asterdex.com

# Logging
LOG_LEVEL=INFO

# Optional defaults
DEFAULT_SYMBOL=BTCUSDT
MARGIN_MODE=cross      # isolated|cross
HEDGE_MODE=off         # off|on
```

Commands (most used)

```
# Connectivity
aster-trading ping
aster-trading ws-ping btcusdt

---

# Maker
# SAFE - Farm-safe settings (still active, but controlled)
aster-trading maker BTCUSDT --no-dry-run --loops 100000 --width-ticks 3 --drift-ticks 2 --daily-loss-cap 1.4 --symbol-max-quote 12.5 --min-edge-bps 0.03

# SAFEST - Fee-positive (much fewer fills, aim to cover fees)
aster-trading maker BTCUSDT --no-dry-run --loops 100000 --width-ticks 100 --drift-ticks 2 --daily-loss-cap 1 --symbol-max-quote 12.5 --min-edge-bps 0.1

# MAX VOL
aster-trading maker BTCUSDT --no-dry-run --loops 100000 --width-ticks 2 --drift-ticks 2 --daily-loss-cap 4 --symbol-max-quote 150 --min-edge-bps 0.01

---

# Maker + Pairs Strategies (Statistical Arb)
aster-trading multi --maker-symbol BTCUSDT --maker-cap 150 --pairs BTCUSDT,ETHUSDT --pairs-cap 260 --z-enter 2.0 --z-exit 0.5 --shared-daily-loss-cap 3.5

# Pairs Only (Statistical Arb)
aster-trading pairs-meanrev BTCUSDT ETHUSDT --cap-usdt 260 --z-enter 2.0 --z-exit 0.5 --z-stop 3.5

---

# Post-only helper
aster-trading postonly BTCUSDT BUY 109500 2

---

# Account and safety
aster-trading account
aster-trading cancel-all BTCUSDT
```
