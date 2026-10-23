"""End-to-end simulator runs on fixture price series."""

from pathlib import Path

from simulator import load_fixture, main, run_simulation

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "prices.json"


def test_sustained_crossing_fires_exactly_once():
    """Dedupe end-to-end: price crosses a level and stays there for many
    ticks — exactly one alert may come out."""
    fixture = {
        "start_ts": 1_700_000_000,
        "rules": [
            {"chat_id": 1, "symbol": "bitcoin", "type": "above",
             "threshold": 100, "cooldown_seconds": 3600},
        ],
        "ticks": [
            {"t": t, "prices": {"bitcoin": p}}
            for t, p in [(0, 90), (60, 110), (120, 120), (180, 130), (240, 125)]
        ],
    }
    lines = run_simulation(fixture)
    assert len(lines) == 1
    assert "ABOVE" in lines[0]


def test_shipped_fixture_scenario():
    """fixtures/prices.json narrates: a rise through $70k (level + % alerts
    together), a mid-cooldown re-crossing that must stay silent, a second
    crossing after the cooldown, and a final drop below $64k."""
    lines = run_simulation(load_fixture(FIXTURE))
    text = "\n".join(lines)
    assert len(lines) == 4
    assert text.count("crossed ABOVE") == 2
    assert text.count("moved +6.97%") == 1
    assert text.count("dropped BELOW") == 1


def test_cli_main_prints_alerts(capsys):
    rc = main([str(FIXTURE)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "4 alert(s) would fire." in out
