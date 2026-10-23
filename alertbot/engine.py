"""Rule engine.

Feed it :class:`PricePoint` observations; it returns the alerts that fire.

Duplicate protection is two-layered:

1. **Edge triggering** — an ABOVE rule fires on the tick where the price
   crosses the threshold, not on every tick while it stays above it.
   The "currently triggered" flag lives in SQLite, so restarts are safe.
2. **Cooldown** — even after a fresh crossing, a rule stays silent until
   ``cooldown_seconds`` have passed since its last fired alert. A crossing
   that happens inside the cooldown window is consumed (marked triggered)
   but does not produce an alert.
"""

from __future__ import annotations

from collections import defaultdict

from . import formatter
from .models import Alert, PricePoint, Rule, RuleType
from .store import RuleState, Store


class RuleEngine:
    def __init__(self, store: Store):
        self.store = store
        # symbol -> [(ts, price), ...] kept for PCT_CHANGE windows
        self._history: dict[str, list[tuple[float, float]]] = defaultdict(list)

    def add_rule(self, rule: Rule) -> Rule:
        return self.store.add_rule(rule)

    # -------------------------------------------------------------- public
    def process(self, point: PricePoint) -> list[Alert]:
        """Evaluate all active rules for ``point.symbol`` against one tick."""
        hist = self._history[point.symbol]
        hist.append((point.ts, point.price))
        self._prune(point)

        alerts: list[Alert] = []
        for rule in self.store.list_rules(symbol=point.symbol):
            alert = self._evaluate(rule, point)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def process_many(self, points: list[PricePoint]) -> list[Alert]:
        out: list[Alert] = []
        for point in points:
            out.extend(self.process(point))
        return out

    # ------------------------------------------------------------ internal
    def _evaluate(self, rule: Rule, point: PricePoint) -> Alert | None:
        state = self.store.get_state(rule.id)  # type: ignore[arg-type]
        triggered, pct, ref = self._condition(rule, point)

        if not triggered:
            if state.is_triggered or state.last_price != point.price:
                state.is_triggered = False
                state.last_price = point.price
                self.store.set_state(rule.id, state)  # type: ignore[arg-type]
            return None

        # Condition is true. Only the rising edge can fire.
        if state.is_triggered:
            return None

        state.is_triggered = True
        state.last_price = point.price

        in_cooldown = (
            state.last_fired_at is not None
            and point.ts - state.last_fired_at < rule.cooldown_seconds
        )
        if in_cooldown:
            # Consume the crossing silently; the plateau will not re-fire.
            self.store.set_state(rule.id, state)  # type: ignore[arg-type]
            return None

        state.last_fired_at = point.ts
        self.store.set_state(rule.id, state)  # type: ignore[arg-type]

        alert = Alert(rule=rule, point=point, pct_change=pct, reference_price=ref)
        alert.message = formatter.format_alert(alert)
        self.store.log_alert(alert)
        return alert

    def _condition(self, rule: Rule, point: PricePoint):
        """Return (triggered, pct_change, reference_price)."""
        if rule.rule_type is RuleType.ABOVE:
            return point.price > rule.threshold, None, None
        if rule.rule_type is RuleType.BELOW:
            return point.price < rule.threshold, None, None

        # PCT_CHANGE: compare against the newest observation at or before
        # (now - window). Without one there is not enough history yet.
        cutoff = point.ts - rule.window_seconds
        ref: float | None = None
        for ts, price in self._history[point.symbol]:
            if ts <= cutoff:
                ref = price
            else:
                break
        if ref is None or ref == 0:
            return False, None, None
        pct = (point.price - ref) / ref * 100.0
        if rule.threshold >= 0:
            return pct >= rule.threshold, pct, ref
        return pct <= rule.threshold, pct, ref

    def _prune(self, point: PricePoint) -> None:
        """Drop history older than the largest window for this symbol.

        Always keeps the newest point at-or-before the cut-off as well:
        PCT_CHANGE needs it as its reference price even when ticks are sparse.
        """
        windows = [
            r.window_seconds
            for r in self.store.list_rules(symbol=point.symbol)
            if r.rule_type is RuleType.PCT_CHANGE
        ]
        hist = self._history[point.symbol]
        if not windows:
            self._history[point.symbol] = hist[-1:]
            return
        keep_from = point.ts - max(windows)
        old = [hp for hp in hist if hp[0] < keep_from]
        new = [hp for hp in hist if hp[0] >= keep_from]
        self._history[point.symbol] = (old[-1:] if old else []) + new
