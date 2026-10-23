"""Price data sources.

Ships with a CoinGecko source speaking the public ``/simple/price`` API
shape::

    GET https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd
    -> {"bitcoin": {"usd": 67123.45}, "ethereum": {"usd": 3123.45}}

``parse`` is pure (dict in, PricePoints out) so tests and the simulator can
feed fixture payloads without any network access.
"""

from __future__ import annotations

import json
import time
import urllib.request

from .models import PricePoint


class CoinGeckoSource:
    BASE_URL = "https://api.coingecko.com/api/v3/simple/price"

    def __init__(self, vs_currency: str = "usd", timeout: float = 15.0):
        self.vs_currency = vs_currency
        self.timeout = timeout

    def build_url(self, ids: list[str]) -> str:
        joined = ",".join(ids)
        return f"{self.BASE_URL}?ids={joined}&vs_currencies={self.vs_currency}"

    def parse(self, payload: dict, ts: float | None = None) -> list[PricePoint]:
        """Convert a CoinGecko-shaped payload into price points."""
        ts = time.time() if ts is None else ts
        points = []
        for symbol, currencies in payload.items():
            if self.vs_currency in currencies:
                points.append(
                    PricePoint(symbol=symbol, price=float(currencies[self.vs_currency]), ts=ts)
                )
        return points

    def fetch(self, ids: list[str]) -> list[PricePoint]:
        """Live fetch (network). Not used by tests or the simulator."""
        req = urllib.request.Request(
            self.build_url(ids), headers={"accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return self.parse(payload)
