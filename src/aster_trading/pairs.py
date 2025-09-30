from __future__ import annotations

import math
import time
from collections import deque
from typing import Deque, Tuple

from .api_client import AsterClient
from .strategy import MicroMaker


def _rolling_beta_and_z(
    lna: Deque[float], lnb: Deque[float]
) -> Tuple[float, float, float, float]:
    n = len(lna)
    if n < 10:
        return 1.0, 0.0, 0.0, 0.0
    ma = sum(lna) / n
    mb = sum(lnb) / n
    cov = sum((a - ma) * (b - mb) for a, b in zip(lna, lnb)) / max(n - 1, 1)
    var_b = sum((b - mb) ** 2 for b in lnb) / max(n - 1, 1)
    beta = cov / var_b if var_b > 0 else 1.0
    spread = [a - beta * b for a, b in zip(lna, lnb)]
    ms = sum(spread) / n
    stds = math.sqrt(max(sum((s - ms) ** 2 for s in spread) / max(n - 1, 1), 1e-12))
    z = (spread[-1] - ms) / stds if stds > 0 else 0.0
    return beta, z, ms, stds


def run_pairs_meanrev(
    *,
    symbol_a: str,
    symbol_b: str,
    cap_usdt: float,
    z_enter: float = 2.0,
    z_exit: float = 0.5,
    z_stop: float = 3.5,
    loops: int = 100000,
    delay_s: float = 0.6,
) -> None:
    client = AsterClient()
    try:
        filt_a = client.symbol_filters(symbol=symbol_a)
        filt_b = client.symbol_filters(symbol=symbol_b)

        lna: Deque[float] = deque(maxlen=120)
        lnb: Deque[float] = deque(maxlen=120)

        side_state: str | None = None  # "A_long" or "B_long" or None
        entry_ts = 0.0

        for _ in range(loops):
            # prices
            ta = client.book_ticker(symbol_a)
            tb = client.book_ticker(symbol_b)
            pa = (float(ta.get("bidPrice")) + float(ta.get("askPrice"))) / 2.0
            pb = (float(tb.get("bidPrice")) + float(tb.get("askPrice"))) / 2.0
            lna.append(math.log(max(pa, 1e-12)))
            lnb.append(math.log(max(pb, 1e-12)))

            beta, z, ms, stds = _rolling_beta_and_z(lna, lnb)

            # check shared daily loss by reading income (lightweight, no shared state)
            # intentionally omitted here to keep the loop focused; callers can gate externally

            # sizing - equal notionals per leg within cap
            per_leg_quote = cap_usdt / 2.0
            qty_a = MicroMaker.round_qty(per_leg_quote / pa, filt_a["lot_step"])
            qty_b = MicroMaker.round_qty(per_leg_quote / pb, filt_b["lot_step"])
            if qty_a < filt_a["min_qty"] or qty_b < filt_b["min_qty"]:
                time.sleep(delay_s)
                continue

            # entry
            now = time.time()
            if side_state is None and abs(z) >= z_enter and len(lna) >= 30:
                # if z>0, A rich vs B: short A, long B; if z<0, long A, short B
                if z > 0:
                    # short A @ ask, long B @ bid
                    pa_ask = MicroMaker.round_to_tick(pa + filt_a["price_tick"], filt_a["price_tick"])  # be maker-ish
                    pb_bid = MicroMaker.round_to_tick(pb - filt_b["price_tick"], filt_b["price_tick"])  # be maker-ish
                    client.cancel_open_orders(symbol=symbol_a)
                    client.cancel_open_orders(symbol=symbol_b)
                    client.new_order(symbol=symbol_a, side="SELL", type="LIMIT", timeInForce="GTC", price=str(pa_ask), quantity=str(qty_a))
                    client.new_order(symbol=symbol_b, side="BUY", type="LIMIT", timeInForce="GTC", price=str(pb_bid), quantity=str(qty_b))
                    side_state = "B_long"
                    entry_ts = now
                else:
                    # long A, short B
                    pa_bid = MicroMaker.round_to_tick(pa - filt_a["price_tick"], filt_a["price_tick"]) 
                    pb_ask = MicroMaker.round_to_tick(pb + filt_b["price_tick"], filt_b["price_tick"]) 
                    client.cancel_open_orders(symbol=symbol_a)
                    client.cancel_open_orders(symbol=symbol_b)
                    client.new_order(symbol=symbol_a, side="BUY", type="LIMIT", timeInForce="GTC", price=str(pa_bid), quantity=str(qty_a))
                    client.new_order(symbol=symbol_b, side="SELL", type="LIMIT", timeInForce="GTC", price=str(pb_ask), quantity=str(qty_b))
                    side_state = "A_long"
                    entry_ts = now

            # exit rules: z back to 0 band or stop, or timeout
            timeout = 90.0
            if side_state is not None:
                should_exit = (abs(z) <= z_exit) or (abs(z) >= z_stop) or ((now - entry_ts) > timeout)
                if should_exit:
                    # Use reduceOnly MARKET to close both legs
                    try:
                        # BTCUSDT
                        client.new_order(symbol=symbol_a, side="SELL" if side_state == "A_long" else "BUY", type="MARKET", reduceOnly=True, quantity=str(qty_a))
                    except Exception:
                        pass
                    try:
                        # ETHUSDT
                        client.new_order(symbol=symbol_b, side="BUY" if side_state == "B_long" else "SELL", type="MARKET", reduceOnly=True, quantity=str(qty_b))
                    except Exception:
                        pass
                    client.cancel_open_orders(symbol=symbol_a)
                    client.cancel_open_orders(symbol=symbol_b)
                    side_state = None
                    entry_ts = 0.0

            time.sleep(delay_s)
    finally:
        client.close()



