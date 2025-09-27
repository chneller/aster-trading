from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Quote:
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float


class MicroMaker:
    def __init__(self, *, tick_size: float = 0.1, min_spread_ticks: int = 2, base_size: float = 0.001):
        self.tick_size = tick_size
        self.min_spread_ticks = min_spread_ticks
        self.base_size = base_size

    def compute_quotes(self, mid: float, volatility: float = 0.0) -> Quote:
        spread = max(self.min_spread_ticks * self.tick_size, volatility * 0.5)
        bid = mid - spread / 2
        ask = mid + spread / 2
        return Quote(bid_price=bid, ask_price=ask, bid_size=self.base_size, ask_size=self.base_size)

    @staticmethod
    def round_to_tick(value: float, tick: float) -> float:
        if tick <= 0:
            return value
        return (int(value / tick)) * tick

    @staticmethod
    def round_qty(value: float, step: float) -> float:
        if step <= 0:
            return value
        return (int(value / step)) * step

