"""Rule triggering: crossings, plateaus, cooldown, % change windows."""

import pytest

from alertbot.engine import RuleEngine
from alertbot.models import PricePoint, Rule, RuleType
from alertbot.store import Store

T0 = 1_700_000_000.0


@pytest.fixture()
def store():
    s = Store(":memory:")
    yield s
    s.close()


def engine_with(store, rule):
    engine = RuleEngine(store)
    engine.add_rule(rule)
    return engine


def tick(engine, price, dt, symbol="bitcoin"):
    return engine.process(PricePoint(symbol, float(price), T0 + dt))


def test_above_fires_once_on_crossing_not_on_plateau(store):
    engine = engine_with(store, Rule("bitcoin", RuleType.ABOVE, 100, cooldown_seconds=0))
    assert tick(engine, 90, 0) == []
    fired = tick(engine, 110, 10)
    assert len(fired) == 1
    assert "ABOVE" in fired[0].message
    # Price keeps rising / hovering above the level: no spam.
    assert tick(engine, 120, 20) == []
    assert tick(engine, 115, 30) == []
    assert store.count_alerts() == 1


def test_below_fires_on_crossing(store):
    engine = engine_with(store, Rule("bitcoin", RuleType.BELOW, 100, cooldown_seconds=0))
    assert tick(engine, 110, 0) == []
    fired = tick(engine, 95, 10)
    assert len(fired) == 1
    assert "BELOW" in fired[0].message
    assert tick(engine, 90, 20) == []


def test_refire_after_reset_once_cooldown_passed(store):
    engine = engine_with(store, Rule("bitcoin", RuleType.ABOVE, 100, cooldown_seconds=10))
    tick(engine, 90, 0)
    assert len(tick(engine, 110, 1)) == 1
    tick(engine, 90, 5)  # reset below the level
    assert len(tick(engine, 115, 20)) == 1  # 19s later: cooldown over
    assert store.count_alerts() == 2


def test_cooldown_consumes_a_crossing(store):
    engine = engine_with(store, Rule("bitcoin", RuleType.ABOVE, 100, cooldown_seconds=100))
    tick(engine, 90, 0)
    assert len(tick(engine, 110, 1)) == 1  # fires, last_fired = T0+1
    tick(engine, 90, 2)  # reset
    # Crossing at +50s is inside the 100s cooldown: consumed silently.
    assert tick(engine, 110, 50) == []
    # Still above afterwards: the consumed edge does not fire late.
    assert tick(engine, 120, 80) == []
    tick(engine, 90, 90)  # reset again
    # Fresh crossing after the cooldown: fires.
    assert len(tick(engine, 110, 150)) == 1
    assert store.count_alerts() == 2


def test_pct_change_up(store):
    rule = Rule("bitcoin", RuleType.PCT_CHANGE, 5, window_seconds=3600,
                cooldown_seconds=0)
    engine = engine_with(store, rule)
    tick(engine, 100, 0)
    tick(engine, 102, 1800)  # no full window of history yet at +1800 for ref<=t-3600
    fired = tick(engine, 106, 3600)  # +6% vs the price 1h ago
    assert len(fired) == 1
    assert fired[0].pct_change == pytest.approx(6.0)
    assert fired[0].reference_price == 100.0


def test_pct_change_down_with_negative_threshold(store):
    rule = Rule("bitcoin", RuleType.PCT_CHANGE, -5, window_seconds=3600,
                cooldown_seconds=0)
    engine = engine_with(store, rule)
    tick(engine, 100, 0)
    fired = tick(engine, 94, 3600)  # -6% in the window
    assert len(fired) == 1
    assert fired[0].pct_change == pytest.approx(-6.0)


def test_pct_change_small_move_does_not_fire(store):
    rule = Rule("bitcoin", RuleType.PCT_CHANGE, 5, window_seconds=3600,
                cooldown_seconds=0)
    engine = engine_with(store, rule)
    tick(engine, 100, 0)
    assert tick(engine, 103, 3600) == []  # only +3%


def test_pct_change_needs_history(store):
    rule = Rule("bitcoin", RuleType.PCT_CHANGE, 1, window_seconds=3600,
                cooldown_seconds=0)
    engine = engine_with(store, rule)
    # A single tick can never have a reference price a full window back.
    assert tick(engine, 100, 0) == []


def test_rules_are_evaluated_per_symbol(store):
    engine = engine_with(store, Rule("bitcoin", RuleType.ABOVE, 100, cooldown_seconds=0))
    assert tick(engine, 500, 0, symbol="ethereum") == []
    assert len(tick(engine, 500, 1, symbol="bitcoin")) == 1
