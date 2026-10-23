#!/usr/bin/env python3
"""Offline CLI simulator.

Feeds a fixture price series through the real rule engine and prints the
alert messages that *would* be sent to Telegram — no token, no network.

Fixture format (JSON)::

    {
      "start_ts": 1700000000,
      "rules": [
        {"chat_id": 1, "symbol": "bitcoin", "type": "above",
         "threshold": 70000, "cooldown_seconds": 3600},
        {"chat_id": 1, "symbol": "bitcoin", "type": "pct_change",
         "threshold": 3, "window_seconds": 3600, "cooldown_seconds": 3600}
      ],
      "ticks": [
        {"t": 0,    "prices": {"bitcoin": 66000}},
        {"t": 3600, "prices": {"bitcoin": 70600}}
      ]
    }

``t`` is seconds after ``start_ts``. Run:
    python simulator.py fixtures/prices.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from alertbot.engine import RuleEngine
from alertbot.models import PricePoint, Rule, RuleType
from alertbot.store import Store


def load_fixture(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run_simulation(fixture: dict, db_path: str = ":memory:") -> list[str]:
    """Run a fixture dict through the engine; return printed alert lines."""
    store = Store(db_path)
    engine = RuleEngine(store)
    for raw in fixture.get("rules", []):
        engine.add_rule(
            Rule(
                chat_id=raw.get("chat_id", 1),
                symbol=raw["symbol"],
                rule_type=RuleType(raw["type"]),
                threshold=float(raw["threshold"]),
                window_seconds=int(raw.get("window_seconds", 3600)),
                cooldown_seconds=int(raw.get("cooldown_seconds", 3600)),
            )
        )

    start_ts = float(fixture.get("start_ts", 1_700_000_000))
    lines: list[str] = []
    for tick in fixture.get("ticks", []):
        ts = start_ts + float(tick["t"])
        for symbol, price in tick["prices"].items():
            for alert in engine.process(PricePoint(symbol, float(price), ts)):
                stamp = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )
                lines.append(f"[{stamp}] chat {alert.rule.chat_id}: {alert.message}")
    store.close()
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate price alerts offline.")
    parser.add_argument("fixture", help="Path to a fixture JSON file")
    parser.add_argument("--db", default=":memory:", help="SQLite path (default: in-memory)")
    args = parser.parse_args(argv)

    lines = run_simulation(load_fixture(args.fixture), db_path=args.db)
    for line in lines:
        print(line)
    print(f"\n{len(lines)} alert(s) would fire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
