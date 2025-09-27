from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class CostModel:
    maker_fee: float  # e.g., 0.0001 for 1 bps
    taker_fee: float  # e.g., 0.00035 for 3.5 bps
    funding_rate: float = 0.0  # per 8h; applied proportionally to horizon

    def expected_trade_cost(self, *, mid: float, spread: float, is_maker: bool, qty_quote: float) -> float:
        fee = self.maker_fee if is_maker else self.taker_fee
        return -fee * qty_quote


@dataclass
class RiskCaps:
    daily_loss_limit: float  # in USDT
    symbol_max_quote: float  # per symbol max notional exposure


class RiskManager:
    def __init__(self, caps: RiskCaps):
        self.caps = caps
        self._day_start = self._day_key()
        self._daily_pnl = 0.0

    def _day_key(self) -> str:
        return time.strftime("%Y-%m-%d")

    def add_realized_pnl(self, pnl: float) -> None:
        if self._day_key() != self._day_start:
            self._day_start = self._day_key()
            self._daily_pnl = 0.0
        self._daily_pnl += pnl

    def check_daily_loss(self) -> bool:
        return self._daily_pnl >= -abs(self.caps.daily_loss_limit)

    def can_increase_exposure(self, current_symbol_quote: float) -> bool:
        return current_symbol_quote <= self.caps.symbol_max_quote

