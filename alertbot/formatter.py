"""Telegram-style alert message formatting."""

from __future__ import annotations

from .models import Alert, Rule, RuleType

TICKERS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "ripple": "XRP",
}


def display_symbol(symbol: str) -> str:
    return TICKERS.get(symbol.lower(), symbol.upper())


def fmt_price(price: float) -> str:
    return f"${price:,.2f}"


def human_window(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def describe_rule(rule: Rule) -> str:
    sym = display_symbol(rule.symbol)
    if rule.rule_type is RuleType.ABOVE:
        return f"{sym} above {fmt_price(rule.threshold)}"
    if rule.rule_type is RuleType.BELOW:
        return f"{sym} below {fmt_price(rule.threshold)}"
    return (
        f"{sym} moves {rule.threshold:+.1f}% within "
        f"{human_window(rule.window_seconds)}"
    )


def format_alert(alert: Alert) -> str:
    rule, point = alert.rule, alert.point
    sym = display_symbol(rule.symbol)
    if rule.rule_type is RuleType.ABOVE:
        return (
            f"🚨 Price Alert: {sym} crossed ABOVE {fmt_price(rule.threshold)}\n"
            f"Current price: {fmt_price(point.price)}"
        )
    if rule.rule_type is RuleType.BELOW:
        return (
            f"📉 Price Alert: {sym} dropped BELOW {fmt_price(rule.threshold)}\n"
            f"Current price: {fmt_price(point.price)}"
        )
    # PCT_CHANGE
    pct = alert.pct_change or 0.0
    arrow = "📈" if pct >= 0 else "📉"
    return (
        f"{arrow} {sym} moved {pct:+.2f}% in the last "
        f"{human_window(rule.window_seconds)}\n"
        f"{fmt_price(alert.reference_price or 0)} → {fmt_price(point.price)}"
    )


def format_price(symbol: str, price: float) -> str:
    return f"💰 {display_symbol(symbol)} = {fmt_price(price)}"


def format_rules(rules: list[Rule]) -> str:
    if not rules:
        return "You have no active alert rules.\nAdd one with /watch — e.g. /watch BTC above 70000"
    lines = ["📋 Your alert rules:"]
    for rule in rules:
        lines.append(
            f"#{rule.id}  {describe_rule(rule)}"
            f"  (cooldown {human_window(rule.cooldown_seconds)})"
        )
    return "\n".join(lines)
