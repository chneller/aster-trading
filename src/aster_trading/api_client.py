from __future__ import annotations

import time
import hmac
import hashlib
import json
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from .config import load_settings


class AsterClient:
    def __init__(self, *, api_key: Optional[str] = None, api_secret: Optional[str] = None, api_passphrase: Optional[str] = None, base_url: Optional[str] = None):
        self.settings = load_settings()
        self.base_url = base_url or self.settings.api_base
        self.api_key = api_key or self.settings.api_key
        self.api_secret = (api_secret or self.settings.api_secret or "").encode()
        self.api_passphrase = api_passphrase or self.settings.api_passphrase
        self._http = httpx.Client(base_url=self.base_url, timeout=10.0)

    def _headers_key_only(self) -> Dict[str, str]:
        # Aster connector uses X-MBX-APIKEY header for key-based endpoints
        headers = {}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    @retry(wait=wait_exponential_jitter(initial=0.2, max=2.0), stop=stop_after_attempt(3))
    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None, auth: bool = False, key_header: bool = False) -> httpx.Response:
        body_str = json.dumps(json_body) if json_body else ""
        headers: Dict[str, str] = {}
        if key_header:
            headers.update(self._headers_key_only())
        # For signed private endpoints (not implemented yet), append timestamp/signature to params
        return self._http.request(method, path, params=params, content=body_str if body_str else None, headers=headers)

    def _signed_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        assert self.api_key and self.api_secret, "API key/secret required for private endpoints"
        headers = self._headers_key_only()
        params = params.copy() if params else {}
        params.setdefault("recvWindow", 5000)
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        sig = hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()
        signed_params = dict(params)
        signed_params["signature"] = sig
        return self._http.request(method, path, params=signed_params, headers=headers)

    # Public endpoints per Aster connector
    def ping(self) -> Dict[str, Any]:
        resp = self._request("GET", "/fapi/v1/ping")
        return resp.json() if resp.text else {}

    def time(self) -> Dict[str, Any]:
        resp = self._request("GET", "/fapi/v1/time")
        return resp.json()

    def exchange_info(self) -> Dict[str, Any]:
        resp = self._request("GET", "/fapi/v1/exchangeInfo")
        return resp.json()

    def book_ticker(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        params = {"symbol": symbol} if symbol else None
        resp = self._request("GET", "/fapi/v1/ticker/bookTicker", params=params)
        return resp.json()

    def klines(self, *, symbol: str, interval: str, limit: int = 100) -> Any:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        resp = self._request("GET", "/fapi/v1/klines", params=params)
        return resp.json()

    def funding_rate(self, *, symbol: Optional[str] = None, limit: int = 1) -> Any:
        params: Dict[str, Any] = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        resp = self._request("GET", "/fapi/v1/fundingRate", params=params)
        return resp.json()

    # Private endpoints (signed)
    def account(self) -> Dict[str, Any]:
        resp = self._signed_request("GET", "/fapi/v2/account")
        return resp.json()

    def new_order(self, *, symbol: str, side: str, type: str, **kwargs: Any) -> Dict[str, Any]:
        params: Dict[str, Any] = {"symbol": symbol, "side": side, "type": type}
        params.update(kwargs)
        resp = self._signed_request("POST", "/fapi/v1/order", params=params)
        return resp.json()

    def cancel_open_orders(self, *, symbol: str) -> Dict[str, Any]:
        resp = self._signed_request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol})
        return resp.json()

    def open_orders(self, *, symbol: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        resp = self._signed_request("GET", "/fapi/v1/openOrders", params=params)
        return resp.json()

    def symbol_filters(self, *, symbol: str) -> Dict[str, Any]:
        info = self.exchange_info()
        for s in info.get("symbols", []):
            if s.get("symbol") == symbol:
                filters: Dict[str, Any] = {}
                for f in s.get("filters", []):
                    filters[f.get("filterType")] = f
                return {
                    "price_tick": float(filters.get("PRICE_FILTER", {}).get("tickSize", 0.0) or 0.0),
                    "lot_step": float(filters.get("LOT_SIZE", {}).get("stepSize", 0.0) or 0.0),
                    "min_qty": float(filters.get("LOT_SIZE", {}).get("minQty", 0.0) or 0.0),
                    "max_qty": float(filters.get("LOT_SIZE", {}).get("maxQty", 0.0) or 0.0),
                }
        raise ValueError(f"Symbol not found in exchangeInfo: {symbol}")

    def commission_rate(self, *, symbol: str) -> Dict[str, Any]:
        resp = self._signed_request("GET", "/fapi/v1/commissionRate", params={"symbol": symbol})
        return resp.json()

    def position_risk(self) -> Any:
        resp = self._signed_request("GET", "/fapi/v2/positionRisk")
        return resp.json()

    def income_history(self, *, startTime: Optional[int] = None, endTime: Optional[int] = None, limit: int = 1000) -> Any:
        params: Dict[str, Any] = {"limit": limit}
        if startTime is not None:
            params["startTime"] = startTime
        if endTime is not None:
            params["endTime"] = endTime
        resp = self._signed_request("GET", "/fapi/v1/income", params=params)
        return resp.json()

    def close(self) -> None:
        self._http.close()

