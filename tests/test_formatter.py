"""Message formatting."""

from alertbot.formatter import (
    describe_rule,
    format_alert,
    format_price,
    format_rules,
    human_window,
)
from alertbot.models import Alert, PricePoint, Rule, RuleType

T0 = 1_700_000_000.0


def make_alert(rule, price, **kw):
    return Alert(rule=rule, point=PricePoint(rule.symbol, price, T0), **kw)


def test_format_above_alert():
    rule = Rule("bitcoin", RuleType.ABOVE, 70000)
    msg = format_alert(make_alert(rule, 70150.0))
    assert "BTC" in msg
    assert "ABOVE" in msg
    assert "$70,000.00" in msg
    assert "$70,150.00" in msg


def test_format_below_alert():
    rule = Rule("ethereum", RuleType.BELOW, 3000)
    msg = format_alert(make_alert(rule, 2950.5))
    assert "ETH" in msg and "BELOW" in msg
    assert "$3,000.00" in msg and "$2,950.50" in msg


def test_format_pct_change_alert():
    rule = Rule("bitcoin", RuleType.PCT_CHANGE, 3, window_seconds=3600)
    msg = format_alert(make_alert(rule, 70600.0, pct_change=6.9697,
                                  reference_price=66000.0))
    assert "+6.97%" in msg
    assert "1h" in msg
    assert "$66,000.00" in msg and "$70,600.00" in msg


def test_format_price_and_windows():
    assert format_price("bitcoin", 67123.4) == "💰 BTC = $67,123.40"
    assert human_window(900) == "15m"
    assert human_window(3600) == "1h"
    assert human_window(86400) == "1d"


def test_describe_rule():
    assert describe_rule(Rule("bitcoin", RuleType.ABOVE, 70000)) == \
        "BTC above $70,000.00"
    text = describe_rule(Rule("solana", RuleType.PCT_CHANGE, -5,
                              window_seconds=900))
    assert "SOL" in text and "-5.0%" in text and "15m" in text


def test_format_rules_empty_and_nonempty():
    assert "no active alert rules" in format_rules([])
    rules = [Rule("bitcoin", RuleType.ABOVE, 70000, id=7, cooldown_seconds=600)]
    text = format_rules(rules)
    assert "#7" in text and "BTC above" in text and "10m" in text
