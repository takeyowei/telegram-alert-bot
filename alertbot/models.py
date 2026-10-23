"""Core data models for the alert bot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuleType(str, Enum):
    ABOVE = "above"          # fire when price crosses above threshold
    BELOW = "below"          # fire when price crosses below threshold
    PCT_CHANGE = "pct_change"  # fire when % change over a window passes threshold


@dataclass
class PricePoint:
    """One observed price for a symbol at a point in time."""

    symbol: str      # CoinGecko id, e.g. "bitcoin"
    price: float     # price in USD
    ts: float        # epoch seconds


@dataclass
class Rule:
    """A user alert rule.

    threshold:      price level for ABOVE/BELOW, percent for PCT_CHANGE
                    (positive = upward move, negative = downward move).
    window_seconds: look-back window, only used by PCT_CHANGE.
    cooldown_seconds: minimum seconds between two alerts for this rule.
    """

    symbol: str
    rule_type: RuleType
    threshold: float
    chat_id: int = 0
    window_seconds: int = 3600
    cooldown_seconds: int = 3600
    id: int | None = None
    active: bool = True


@dataclass
class Alert:
    """An alert that fired, ready to be formatted / sent."""

    rule: Rule
    point: PricePoint
    pct_change: float | None = None       # set for PCT_CHANGE alerts
    reference_price: float | None = None  # price at start of the window
    message: str = ""
