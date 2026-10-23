"""SQLite state store.

Persists alert rules plus the per-rule runtime state the engine needs to
avoid duplicate alerts:

- ``is_triggered``  : edge detection (fire on the crossing, not the plateau)
- ``last_fired_at`` : cooldown enforcement across restarts

Every fired alert is also written to ``alert_log`` so there is an audit
trail of what was sent, when, and at what price.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .models import Alert, Rule, RuleType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id          INTEGER NOT NULL,
    symbol           TEXT    NOT NULL,
    rule_type        TEXT    NOT NULL,
    threshold        REAL    NOT NULL,
    window_seconds   INTEGER NOT NULL DEFAULT 3600,
    cooldown_seconds INTEGER NOT NULL DEFAULT 3600,
    active           INTEGER NOT NULL DEFAULT 1,
    created_at       REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rule_state (
    rule_id       INTEGER PRIMARY KEY REFERENCES rules(id),
    is_triggered  INTEGER NOT NULL DEFAULT 0,
    last_fired_at REAL,
    last_price    REAL
);
CREATE TABLE IF NOT EXISTS alert_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id  INTEGER NOT NULL,
    chat_id  INTEGER NOT NULL,
    fired_at REAL    NOT NULL,
    price    REAL    NOT NULL,
    message  TEXT    NOT NULL
);
"""


@dataclass
class RuleState:
    is_triggered: bool = False
    last_fired_at: float | None = None
    last_price: float | None = None


class Store:
    """Thin SQLite wrapper. ``path`` may be a file path or ``":memory:"``."""

    def __init__(self, path: str = "alertbot.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------------------------------------------------------------- rules
    def add_rule(self, rule: Rule) -> Rule:
        cur = self.conn.execute(
            "INSERT INTO rules (chat_id, symbol, rule_type, threshold,"
            " window_seconds, cooldown_seconds, active)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                rule.chat_id,
                rule.symbol,
                rule.rule_type.value,
                rule.threshold,
                rule.window_seconds,
                rule.cooldown_seconds,
                1 if rule.active else 0,
            ),
        )
        self.conn.commit()
        rule.id = cur.lastrowid
        return rule

    def list_rules(self, chat_id: int | None = None, symbol: str | None = None,
                   active_only: bool = True) -> list[Rule]:
        sql = "SELECT * FROM rules WHERE 1=1"
        params: list = []
        if active_only:
            sql += " AND active = 1"
        if chat_id is not None:
            sql += " AND chat_id = ?"
            params.append(chat_id)
        if symbol is not None:
            sql += " AND symbol = ?"
            params.append(symbol)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def delete_rule(self, rule_id: int, chat_id: int | None = None) -> bool:
        sql = "DELETE FROM rules WHERE id = ?"
        params: list = [rule_id]
        if chat_id is not None:
            sql += " AND chat_id = ?"
            params.append(chat_id)
        cur = self.conn.execute(sql, params)
        self.conn.execute("DELETE FROM rule_state WHERE rule_id = ?", (rule_id,))
        self.conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> Rule:
        return Rule(
            id=row["id"],
            chat_id=row["chat_id"],
            symbol=row["symbol"],
            rule_type=RuleType(row["rule_type"]),
            threshold=row["threshold"],
            window_seconds=row["window_seconds"],
            cooldown_seconds=row["cooldown_seconds"],
            active=bool(row["active"]),
        )

    # ---------------------------------------------------------------- state
    def get_state(self, rule_id: int) -> RuleState:
        row = self.conn.execute(
            "SELECT * FROM rule_state WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        if row is None:
            return RuleState()
        return RuleState(
            is_triggered=bool(row["is_triggered"]),
            last_fired_at=row["last_fired_at"],
            last_price=row["last_price"],
        )

    def set_state(self, rule_id: int, state: RuleState) -> None:
        self.conn.execute(
            "INSERT INTO rule_state (rule_id, is_triggered, last_fired_at, last_price)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(rule_id) DO UPDATE SET"
            " is_triggered = excluded.is_triggered,"
            " last_fired_at = excluded.last_fired_at,"
            " last_price = excluded.last_price",
            (
                rule_id,
                1 if state.is_triggered else 0,
                state.last_fired_at,
                state.last_price,
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ log
    def log_alert(self, alert: Alert) -> None:
        self.conn.execute(
            "INSERT INTO alert_log (rule_id, chat_id, fired_at, price, message)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                alert.rule.id,
                alert.rule.chat_id,
                alert.point.ts,
                alert.point.price,
                alert.message,
            ),
        )
        self.conn.commit()

    def count_alerts(self, rule_id: int | None = None) -> int:
        if rule_id is None:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM alert_log").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM alert_log WHERE rule_id = ?", (rule_id,)
            ).fetchone()
        return int(row["n"])
