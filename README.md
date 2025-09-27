# aster-trading
aster-trading: Aster DEX Pro Mode trading bot (maker)

Quick start

1) Python 3.10+
2) Create and fill .env

```
cp .env.example .env
```

3) Install

```
pip install -e .
```

4) Run

```
aster-trading --help
```

Commands (most used)

```
# Connectivity
aster-trading ping
aster-trading ws-ping btcusdt

# Maker
##SAFE - Farm-safe settings (still active, but controlled)
aster-trading maker BTCUSDT --no-dry-run --loops 100000 --width-ticks 3 --drift-ticks 2 --daily-loss-cap 1.4 --symbol-max-quote 12.5 --min-edge-bps 0.03

##SAFEST - Fee-positive (much fewer fills, aim to cover fees)
aster-trading maker BTCUSDT --no-dry-run --loops 100000 --width-ticks 100 --drift-ticks 2 --daily-loss-cap 1 --symbol-max-quote 12.5 --min-edge-bps 0.1

# Maximum volume approach
aster-trading maker BTCUSDT --no-dry-run --loops 100000 --width-ticks 2 --drift-ticks 2 --daily-loss-cap 4 --symbol-max-quote 150 --min-edge-bps 0.01

# Post-only helper
aster-trading postonly BTCUSDT BUY 109500 2

# Swing (breakout with ATR)
aster-trading run-swing BTCUSDT --interval 15m --dry-run

# Account and safety
aster-trading account
aster-trading cancel-all BTCUSDT
```

Environment (.env at project root)

```
ASTER_API_KEY=...
ASTER_API_SECRET=...
ASTER_API_BASE=https://fapi.asterdex.com
ASTER_WS_BASE=wss://fstream.asterdex.com
LOG_LEVEL=INFO
```
