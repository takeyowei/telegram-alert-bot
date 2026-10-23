# Telegram Price Alert Bot (Python)

A Telegram bot that watches crypto prices and messages you the moment
*your* rules trigger — a level cross, or a sharp % move inside a time
window. Built on a small, fully offline-testable core: the rule engine,
SQLite state store and command layer use only the Python standard
library; python-telegram-bot is just the live transport.

## Features

- **Three rule types**
  - `above` — price crosses above a level (e.g. BTC > $70,000)
  - `below` — price drops below a level
  - `pct_change` — price moves ±X% within a window (15m / 1h / 24h / …)
- **No alert spam, ever.** A rule fires on the *crossing*, not on every
  tick while the price stays beyond the level, and a per-rule cooldown
  keeps it silent for a configurable period after each alert.
- **State survives restarts.** Rules, the triggered-edge flag and the
  last-fired timestamp live in SQLite (`alertbot.db`), plus an audit log
  of every alert ever sent.
- **Real market data shape.** Prices come from CoinGecko's public
  `/simple/price` API; the parser is pure, so fixtures can be fed in
  tests with zero network.
- **Per-chat rules.** Every Telegram chat manages its own watchlist.

## Commands

| Command | Example | Meaning |
|---|---|---|
| `/price` | `/price BTC` | Current price |
| `/watch` | `/watch BTC above 70000` | Alert on crossing above a level |
| `/watch` | `/watch ETH below 3000` | Alert on dropping below a level |
| `/watch` | `/watch BTC pct 5 1h` | Alert on a ±5% move within 1 hour |
| `/rules` | `/rules` | List your rules |
| `/unwatch` | `/unwatch 3` | Remove rule #3 |

Tickers BTC, ETH, SOL, DOGE, ADA, XRP are recognised, as are raw
CoinGecko ids (`bitcoin`, `ethereum`, …).

## Project layout

```
alertbot/
    models.py      Rule / PricePoint / Alert dataclasses
    engine.py      Rule engine: edge triggering + cooldown + % windows
    store.py       SQLite: rules, per-rule state, alert audit log
    formatter.py   Telegram message formatting
    sources.py     CoinGecko /simple/price source (parse is pure)
    bot.py         BotCore command layer + python-telegram-bot wiring
simulator.py       Offline CLI: replay a fixture series, print alerts
fixtures/          Sample price series used by the simulator and tests
tests/             pytest suite (engine, store, formatter, bot, simulator)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Create the bot (BotFather)

1. Open Telegram, talk to **@BotFather**, send `/newbot` and follow the
   prompts to get a token.
2. Export it (never commit it):

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
```

## Run the live bot

```bash
python -m alertbot.bot
```

The bot long-polls Telegram, answers commands, and every 60 seconds
checks the prices of all symbols that have rules, pushing fired alerts
to the chat that created each rule. State is stored in `alertbot.db`
(override with the `ALERTBOT_DB` environment variable).

## Try it offline — simulator

No token, no network: replay the bundled fixture series through the
real engine and see exactly which messages would be sent.

```bash
python simulator.py fixtures/prices.json
```

The fixture narrates a rise through $70,000 (a level alert and a +6.97%
window alert fire together), a re-crossing inside the cooldown that
correctly stays silent, a second crossing after the cooldown, and a
final drop below $64,000 — 4 alerts in total.

## Tests

```bash
pytest
```

Covered: rule triggering (crossings vs. plateaus, % change up/down,
insufficient history), dedupe/cooldown including persistence across a
store reopen, message formatting, the `/watch`–`/rules`–`/price`–
`/unwatch` command layer with a stub price provider, and an end-to-end
simulator run on the fixture.

## How duplicate prevention works

Two mechanisms compose:

1. **Edge triggering** — `rule_state.is_triggered` in SQLite records
   whether the rule's condition is currently true. An alert can only
   fire on a False→True transition.
2. **Cooldown** — `rule_state.last_fired_at` records the last alert.
   A fresh crossing inside `cooldown_seconds` is consumed (marked
   triggered) without sending, so a jittery price around a level can't
   spam the chat when the cooldown expires mid-plateau.
