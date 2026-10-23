"""Bot command layer, exercised offline with a stub price provider.

No telegram library, no network, no token: BotCore takes plain args and
returns reply text.
"""

import pytest

from alertbot.bot import BotCore, parse_window, resolve_symbol
from alertbot.engine import RuleEngine
from alertbot.models import RuleType
from alertbot.store import Store

PRICES = {"bitcoin": 67123.0, "ethereum": 3123.0}


@pytest.fixture()
def core():
    store = Store(":memory:")
    engine = RuleEngine(store)
    core = BotCore(store, engine, price_provider=PRICES.get)
    yield core
    store.close()


def test_resolve_symbol_and_window_parsing():
    assert resolve_symbol("BTC") == "bitcoin"
    assert resolve_symbol("bitcoin") == "bitcoin"
    assert parse_window("15m") == 900
    assert parse_window("1h") == 3600
    assert parse_window("24h") == 86400
    assert parse_window("300") == 300


def test_price_command(core):
    assert core.cmd_price(1, ["BTC"]) == "💰 BTC = $67,123.00"
    assert "couldn't fetch" in core.cmd_price(1, ["XRP"])  # stub returns None
    assert "Usage" in core.cmd_price(1, [])


def test_watch_above_then_rules_then_unwatch(core):
    reply = core.cmd_watch(42, ["BTC", "above", "70000"])
    assert "Watching" in reply and "BTC above $70,000.00" in reply

    rules = core.store.list_rules(chat_id=42)
    assert len(rules) == 1
    assert rules[0].rule_type is RuleType.ABOVE
    assert rules[0].symbol == "bitcoin"

    listing = core.cmd_rules(42)
    assert f"#{rules[0].id}" in listing

    assert "removed" in core.cmd_unwatch(42, [str(rules[0].id)])
    assert core.store.list_rules(chat_id=42) == []
    assert "no active alert rules" in core.cmd_rules(42)


def test_watch_pct_rule_parses_window(core):
    reply = core.cmd_watch(7, ["ETH", "pct", "-5", "15m"])
    assert "Watching" in reply
    rule = core.store.list_rules(chat_id=7)[0]
    assert rule.rule_type is RuleType.PCT_CHANGE
    assert rule.threshold == -5.0
    assert rule.window_seconds == 900


def test_watch_rejects_garbage(core):
    assert "Usage" in core.cmd_watch(1, ["BTC"])
    assert "couldn't parse" in core.cmd_watch(1, ["BTC", "above", "banana"])
    assert core.store.list_rules() == []


def test_rules_are_private_per_chat(core):
    core.cmd_watch(1, ["BTC", "above", "70000"])
    assert "no active alert rules" in core.cmd_rules(2)
    # Chat 2 cannot remove chat 1's rule.
    rule_id = core.store.list_rules(chat_id=1)[0].id
    assert "No rule" in core.cmd_unwatch(2, [str(rule_id)])
    assert len(core.store.list_rules(chat_id=1)) == 1
