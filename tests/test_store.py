"""SQLite store: rule CRUD, chat scoping, dedupe state persistence."""

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


def test_add_and_list_rules(store):
    store.add_rule(Rule("bitcoin", RuleType.ABOVE, 70000, chat_id=1))
    store.add_rule(Rule("ethereum", RuleType.BELOW, 3000, chat_id=1))
    store.add_rule(Rule("bitcoin", RuleType.BELOW, 60000, chat_id=2))

    assert len(store.list_rules()) == 3
    assert len(store.list_rules(chat_id=1)) == 2
    assert len(store.list_rules(chat_id=2)) == 1
    btc = store.list_rules(symbol="bitcoin")
    assert {r.threshold for r in btc} == {70000, 60000}
    assert all(r.id is not None for r in btc)


def test_delete_rule_is_scoped_to_owner_chat(store):
    mine = store.add_rule(Rule("bitcoin", RuleType.ABOVE, 70000, chat_id=1))
    # Another chat cannot delete my rule.
    assert store.delete_rule(mine.id, chat_id=2) is False
    assert len(store.list_rules()) == 1
    assert store.delete_rule(mine.id, chat_id=1) is True
    assert store.list_rules() == []


def test_trigger_state_survives_restart(tmp_path):
    """The anti-spam edge flag lives in SQLite: after a restart the bot
    must not re-fire for a plateau it already alerted on."""
    db = str(tmp_path / "alerts.db")

    store1 = Store(db)
    engine1 = RuleEngine(store1)
    engine1.add_rule(Rule("bitcoin", RuleType.ABOVE, 100, chat_id=1, cooldown_seconds=0))
    engine1.process(PricePoint("bitcoin", 90.0, T0))
    assert len(engine1.process(PricePoint("bitcoin", 110.0, T0 + 10))) == 1
    store1.close()

    store2 = Store(db)
    engine2 = RuleEngine(store2)  # fresh in-memory history, same DB state
    assert engine2.process(PricePoint("bitcoin", 120.0, T0 + 20)) == []
    assert store2.count_alerts() == 1
    store2.close()


def test_cooldown_survives_restart(tmp_path):
    db = str(tmp_path / "alerts.db")

    store1 = Store(db)
    engine1 = RuleEngine(store1)
    engine1.add_rule(Rule("bitcoin", RuleType.ABOVE, 100, chat_id=1,
                          cooldown_seconds=1000))
    engine1.process(PricePoint("bitcoin", 90.0, T0))
    assert len(engine1.process(PricePoint("bitcoin", 110.0, T0 + 10))) == 1
    store1.close()

    store2 = Store(db)
    engine2 = RuleEngine(store2)
    engine2.process(PricePoint("bitcoin", 90.0, T0 + 20))   # reset
    # New crossing only 490s after the last alert: still in cooldown.
    assert engine2.process(PricePoint("bitcoin", 110.0, T0 + 500)) == []
    assert store2.count_alerts() == 1
    store2.close()
