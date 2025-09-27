from __future__ import annotations

import asyncio
import json
from typing import Callable

import websockets

from .config import load_settings


async def subscribe_book_ticker(symbol: str, on_msg: Callable[[dict], None]) -> None:
    settings = load_settings()
    base = settings.ws_base.rstrip("/")
    if base.endswith("/ws") or base.endswith("/stream"):
        url = base
    else:
        url = f"{base}/ws"
    async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
        sub = {"method": "SUBSCRIBE", "params": [f"{symbol.lower()}@bookTicker"], "id": 1}
        await ws.send(json.dumps(sub))
        while True:
            raw = await ws.recv()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            on_msg(msg)


def run_ws_book_ticker(symbol: str, on_msg: Callable[[dict], None]) -> None:
    asyncio.run(subscribe_book_ticker(symbol, on_msg))

