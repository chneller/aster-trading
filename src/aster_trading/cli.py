from __future__ import annotations

import sys
import time
import typer
from rich.console import Console
import threading

from .config import load_settings
from .api_client import AsterClient
from .strategy import MicroMaker
from .ws_client import run_ws_book_ticker
from .risk import RiskManager, RiskCaps, CostModel
from .pairs import run_pairs_meanrev
# swing module disabled by request


app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def ping():
    """Quick connectivity check."""
    settings = load_settings()
    client = AsterClient(base_url=settings.api_base)
    try:
        console.print({"ping": client.ping(), "time": client.time()})
        info = client.exchange_info()
        # print a couple of symbols
        symbols = [s.get("symbol") for s in info.get("symbols", [])][:5]
        console.print({"exchange_info_symbols": symbols})
    except Exception as e:
        console.print(f"Ping failed: {e}")
        raise typer.Exit(code=1)
    finally:
        client.close()


@app.command()
def dryrun(symbol: str = typer.Argument("BTCUSDT")):
    """Simulate quote decisions without sending orders."""
    mm = MicroMaker()
    mid = 100.0
    for _ in range(3):
        q = mm.compute_quotes(mid)
        console.print({"symbol": symbol, "mid": mid, "quote": q.__dict__})
        mid += 0.1
        time.sleep(0.2)


@app.command()
def ws_ping(symbol: str = typer.Argument("btcusdt")):
    """Subscribe to bookTicker WS and print a few messages."""
    from collections import deque

    messages = deque(maxlen=5)

    def on_msg(msg):
        if msg.get("e") == "bookTicker" or "b" in msg and "a" in msg:
            messages.append({"best_bid": msg.get("b"), "best_ask": msg.get("a")})
            console.print(messages[-1])
            if len(messages) >= 5:
                raise typer.Exit(code=0)

    try:
        run_ws_book_ticker(symbol, on_msg)
    except SystemExit:
        pass


@app.command()
def account():
    """Show basic account info (requires API key/secret in .env)."""
    settings = load_settings()
    client = AsterClient()
    try:
        info = client.account()
        console.print({"account": {"totalWalletBalance": info.get("totalWalletBalance"), "totalUnrealizedProfit": info.get("totalUnrealizedProfit")}})
    except Exception as e:
        console.print(f"Account failed: {e}")
        raise typer.Exit(code=1)
    finally:
        client.close()


@app.command()
def place_limit(symbol: str = typer.Argument("BTCUSDT"), side: str = typer.Argument("BUY"), price: float = typer.Argument(...), qty: float = typer.Argument(...)):
    """Place a LIMIT order with timeInForce=GTC (use small qty!)."""
    client = AsterClient()
    try:
        res = client.new_order(symbol=symbol, side=side.upper(), type="LIMIT", timeInForce="GTC", price=price, quantity=qty)
        console.print({"order": res})
    except Exception as e:
        console.print(f"Place order failed: {e}")
        raise typer.Exit(code=1)
    finally:
        client.close()


@app.command()
def cancel_all(symbol: str = typer.Argument("BTCUSDT")):
    """Cancel all open orders for a symbol."""
    client = AsterClient()
    try:
        res = client.cancel_open_orders(symbol=symbol)
        console.print({"cancel_all": res})
    except Exception as e:
        console.print(f"Cancel failed: {e}")
        raise typer.Exit(code=1)
    finally:
        client.close()


@app.command()
def postonly(symbol: str = typer.Argument("BTCUSDT"), side: str = typer.Argument("BUY"), mid: float = typer.Argument(...), width_ticks: int = typer.Argument(2)):
    """Place a post-only style limit by offsetting price from mid so it doesn't take."""
    client = AsterClient()
    try:
        filters = client.symbol_filters(symbol=symbol)
        mm = MicroMaker(tick_size=filters["price_tick"], min_spread_ticks=width_ticks)
        q = mm.compute_quotes(mid)
        price = q.bid_price if side.upper() == "BUY" else q.ask_price
        price = MicroMaker.round_to_tick(price, filters["price_tick"]) 
        qty = MicroMaker.round_qty(mm.base_size, filters["lot_step"]) 
        res = client.new_order(symbol=symbol, side=side.upper(), type="LIMIT", timeInForce="GTC", price=price, quantity=qty)
        console.print({"postonly": res})
    except Exception as e:
        console.print(f"Post-only failed: {e}")
        raise typer.Exit(code=1)
    finally:
        client.close()


@app.command()
def maker(
    symbol: str = typer.Argument("BTCUSDT"),
    dry_run: bool = typer.Option(True, help="Don't send orders"),
    loops: int = typer.Option(10),
    width_ticks: int = typer.Option(2),
    drift_ticks: int = typer.Option(1, help="reprice if mid moves by this many ticks"),
    daily_loss_cap: float = typer.Option(1.0, help="USDT daily loss cap"),
    symbol_max_quote: float = typer.Option(25.0, help="Max notional exposure per symbol (USDT)"),
    min_edge_bps: float = typer.Option(6.0, help="Only quote when natural spread >= this many bps"),
):
    """Minimal maker loop using REST bookTicker (safe for testing)."""
    client = AsterClient()
    try:
        filters = client.symbol_filters(symbol=symbol)
        rm = RiskManager(RiskCaps(daily_loss_limit=daily_loss_cap, symbol_max_quote=symbol_max_quote))
        mm = MicroMaker(tick_size=filters["price_tick"], min_spread_ticks=width_ticks)
        last_mid = None
        for _ in range(loops):
            # Daily PnL update from income (funding/trading)
            # We keep it simple: fetch latest income and sum today entries
            # Users can increase loops/delay to reduce API calls
            try:
                incomes = client.income_history(limit=100)
                # Sum today's income
                import time as _t
                day_str = _t.strftime("%Y-%m-%d")
                day_ms = int(_t.time())
                pnl_today = 0.0
                for inc in incomes:
                    if "time" in inc and "income" in inc:
                        pnl_today += float(inc.get("income", 0.0))
                rm._daily_pnl = pnl_today
            except Exception:
                pass

            if not rm.check_daily_loss():
                console.print({"halt": "daily_loss_cap_reached"})
                if not dry_run:
                    client.cancel_open_orders(symbol=symbol)
                break

            bt = client.book_ticker(symbol)
            bid = float(bt.get("bidPrice"))
            ask = float(bt.get("askPrice"))
            mid = (bid + ask) / 2

            # natural spread in bps
            natural_spread = max(ask - bid, 0.0)
            spread_bps = (natural_spread / mid) * 1e4 if mid > 0 else 0.0
            # gate by min edge
            if spread_bps < min_edge_bps:
                console.print({"skip": "edge_too_small", "spread_bps": round(spread_bps, 3)})
                time.sleep(0.6)
                last_mid = mid
                continue

            q = mm.compute_quotes(mid)
            bid_px = MicroMaker.round_to_tick(q.bid_price, filters["price_tick"]) 
            ask_px = MicroMaker.round_to_tick(q.ask_price, filters["price_tick"]) 
            qty = MicroMaker.round_qty(mm.base_size, filters["lot_step"]) 
            console.print({"mid": mid, "bid_px": bid_px, "ask_px": ask_px, "qty": qty, "spread_bps": round(spread_bps, 3), "daily_pnl": rm._daily_pnl})
            if not dry_run:
                # Drift-based reprice: only cancel/replace if mid moved beyond drift_ticks
                need_reprice = False
                if last_mid is None:
                    need_reprice = True
                else:
                    tick = filters["price_tick"]
                    moved = abs(mid - last_mid) >= (drift_ticks * tick)
                    need_reprice = moved
                if need_reprice:
                    client.cancel_open_orders(symbol=symbol)
                    client.new_order(symbol=symbol, side="BUY", type="LIMIT", timeInForce="GTC", price=bid_px, quantity=qty)
                    client.new_order(symbol=symbol, side="SELL", type="LIMIT", timeInForce="GTC", price=ask_px, quantity=qty)
                last_mid = mid
            time.sleep(0.6)
    except Exception as e:
        console.print(f"Maker loop failed: {e}")
        raise typer.Exit(code=1)
    finally:
        client.close()


@app.command()
def pairs_meanrev(
    symbol_a: str = typer.Argument("BTCUSDT"),
    symbol_b: str = typer.Argument("ETHUSDT"),
    cap_usdt: float = typer.Option(200.0, help="Total notional cap for the pair (both legs)"),
    z_enter: float = typer.Option(2.0),
    z_exit: float = typer.Option(0.5),
    z_stop: float = typer.Option(3.5),
    loops: int = typer.Option(100000),
):
    """Run a simple beta-hedged mean reversion on two symbols."""
    try:
        run_pairs_meanrev(symbol_a=symbol_a, symbol_b=symbol_b, cap_usdt=cap_usdt, z_enter=z_enter, z_exit=z_exit, z_stop=z_stop, loops=loops)
    except Exception as e:
        console.print(f"Pairs loop failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def multi(
    maker_symbol: str = typer.Option("BTCUSDT"),
    maker_cap: float = typer.Option(150.0, help="Maker cap in USDT"),
    pairs: str = typer.Option("BTCUSDT,ETHUSDT"),
    pairs_cap: float = typer.Option(200.0, help="Pairs total cap in USDT"),
    z_enter: float = typer.Option(2.0),
    z_exit: float = typer.Option(0.5),
    z_stop: float = typer.Option(3.5),
    shared_daily_loss_cap: float = typer.Option(3.5),
    width_ticks: int = typer.Option(2),
    drift_ticks: int = typer.Option(2),
    min_edge_bps: float = typer.Option(0.01),
):
    """Run maker and pairs concurrently with separate caps and one shared daily loss cap."""
    settings = load_settings()
    pair_a, pair_b = [s.strip() for s in pairs.split(",")]
    # Background threads
    stop_event = False
    maker_thread = threading.Thread(
        target=maker,
        kwargs=dict(symbol=maker_symbol, dry_run=False, loops=100000, width_ticks=width_ticks, drift_ticks=drift_ticks, daily_loss_cap=shared_daily_loss_cap, symbol_max_quote=maker_cap, min_edge_bps=min_edge_bps),
        daemon=True,
    )
    pairs_thread = threading.Thread(
        target=pairs_meanrev,
        kwargs=dict(symbol_a=pair_a, symbol_b=pair_b, cap_usdt=pairs_cap, z_enter=z_enter, z_exit=z_exit, z_stop=z_stop, loops=100000),
        daemon=True,
    )
    maker_thread.start()
    pairs_thread.start()
    maker_thread.join()
    pairs_thread.join()


@app.command(hidden=True)
def run_swing():
    console.print({"disabled": "swing module has been disabled"})

if __name__ == "__main__":
    app()

