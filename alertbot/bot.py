"""Telegram bot layer.

Two pieces:

- :class:`BotCore` — all command logic (/watch, /rules, /price, /unwatch)
  with zero dependency on the telegram library. It takes plain arguments
  and returns the reply text, so the whole command surface is unit-testable
  offline with a stub price provider.

- :func:`build_application` / :func:`main` — the live wiring on top of
  python-telegram-bot, imported lazily so the core never requires it.
  A repeating job polls prices for every symbol that has rules and pushes
  fired alerts to the owning chat.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from . import formatter
from .engine import RuleEngine
from .models import Rule, RuleType
from .sources import CoinGeckoSource
from .store import Store

TICKER_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "XRP": "ripple",
}

PriceProvider = Callable[[str], float | None]

HELP_TEXT = (
    "🤖 Crypto Price Alert Bot\n\n"
    "Commands:\n"
    "/watch BTC above 70000 — alert when BTC crosses above $70,000\n"
    "/watch ETH below 3000 — alert when ETH drops below $3,000\n"
    "/watch BTC pct 5 1h — alert when BTC moves ±5% within 1 hour\n"
    "/rules — list your alert rules\n"
    "/unwatch 3 — remove rule #3\n"
    "/price BTC — current price"
)


def resolve_symbol(token: str) -> str:
    """Accept a ticker (BTC) or a CoinGecko id (bitcoin)."""
    return TICKER_TO_ID.get(token.upper(), token.lower())


def parse_window(token: str) -> int:
    """Parse '15m', '1h', '24h' or a plain number of seconds."""
    token = token.strip().lower()
    if token.endswith("h"):
        return int(float(token[:-1]) * 3600)
    if token.endswith("m"):
        return int(float(token[:-1]) * 60)
    if token.endswith("d"):
        return int(float(token[:-1]) * 86400)
    return int(token)


class BotCore:
    def __init__(self, store: Store, engine: RuleEngine, price_provider: PriceProvider):
        self.store = store
        self.engine = engine
        self.price_provider = price_provider

    # ------------------------------------------------------------- commands
    def cmd_start(self, chat_id: int) -> str:
        return HELP_TEXT

    def cmd_price(self, chat_id: int, args: list[str]) -> str:
        if len(args) != 1:
            return "Usage: /price BTC"
        symbol = resolve_symbol(args[0])
        price = self.price_provider(symbol)
        if price is None:
            return f"Sorry, I couldn't fetch a price for {args[0].upper()} right now."
        return formatter.format_price(symbol, price)

    def cmd_watch(self, chat_id: int, args: list[str]) -> str:
        """Grammar:
            /watch BTC above 70000
            /watch ETH below 3000
            /watch BTC pct 5 1h      (upward +5% within 1h)
            /watch BTC pct -5 1h     (downward -5% within 1h)
        """
        try:
            if len(args) == 3 and args[1].lower() in ("above", "below"):
                rule = Rule(
                    chat_id=chat_id,
                    symbol=resolve_symbol(args[0]),
                    rule_type=RuleType(args[1].lower()),
                    threshold=float(args[2].replace(",", "").replace("$", "")),
                )
            elif len(args) == 4 and args[1].lower() in ("pct", "change", "%"):
                rule = Rule(
                    chat_id=chat_id,
                    symbol=resolve_symbol(args[0]),
                    rule_type=RuleType.PCT_CHANGE,
                    threshold=float(args[2].replace("%", "")),
                    window_seconds=parse_window(args[3]),
                )
            else:
                return (
                    "Usage:\n/watch BTC above 70000\n/watch ETH below 3000\n"
                    "/watch BTC pct 5 1h"
                )
        except ValueError:
            return "I couldn't parse that. Example: /watch BTC above 70000"

        self.engine.add_rule(rule)
        return f"✅ Watching: {formatter.describe_rule(rule)} (rule #{rule.id})"

    def cmd_rules(self, chat_id: int) -> str:
        return formatter.format_rules(self.store.list_rules(chat_id=chat_id))

    def cmd_unwatch(self, chat_id: int, args: list[str]) -> str:
        if len(args) != 1 or not args[0].lstrip("#").isdigit():
            return "Usage: /unwatch <rule number from /rules>"
        rule_id = int(args[0].lstrip("#"))
        if self.store.delete_rule(rule_id, chat_id=chat_id):
            return f"🗑 Rule #{rule_id} removed."
        return f"No rule #{rule_id} found among your rules."


# ------------------------------------------------------------ live wiring
def build_application(token: str, core: BotCore, source: CoinGeckoSource):
    """Create a python-telegram-bot Application bound to ``core``.

    Imported lazily: the offline core and tests never need the library.
    """
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
    )

    async def _reply(update: "Update", text: str) -> None:
        if update.message:
            await update.message.reply_text(text)

    async def start(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        await _reply(update, core.cmd_start(update.effective_chat.id))  # type: ignore[union-attr]

    async def price(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        await _reply(update, core.cmd_price(update.effective_chat.id, list(ctx.args or [])))  # type: ignore[union-attr]

    async def watch(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        await _reply(update, core.cmd_watch(update.effective_chat.id, list(ctx.args or [])))  # type: ignore[union-attr]

    async def rules(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        await _reply(update, core.cmd_rules(update.effective_chat.id))  # type: ignore[union-attr]

    async def unwatch(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        await _reply(update, core.cmd_unwatch(update.effective_chat.id, list(ctx.args or [])))  # type: ignore[union-attr]

    async def check_prices(ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        symbols = sorted({r.symbol for r in core.store.list_rules()})
        if not symbols:
            return
        for point in source.fetch(symbols):
            for alert in core.engine.process(point):
                await ctx.bot.send_message(chat_id=alert.rule.chat_id, text=alert.message)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("unwatch", unwatch))
    if app.job_queue is not None:
        app.job_queue.run_repeating(check_prices, interval=60, first=10)
    return app


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "Set TELEGRAM_BOT_TOKEN first (create a bot with @BotFather)."
        )
    source = CoinGeckoSource()
    store = Store(os.environ.get("ALERTBOT_DB", "alertbot.db"))

    def provider(symbol: str) -> float | None:
        points = source.fetch([symbol])
        return points[0].price if points else None

    core = BotCore(store, RuleEngine(store), provider)
    build_application(token, core, source).run_polling()


if __name__ == "__main__":
    main()
