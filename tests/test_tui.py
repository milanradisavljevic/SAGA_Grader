from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga_core import (
    check_agent_availability,
    default_rubric_for,
    humanize_agent_error,
    load_config,
    rubric_options_for,
    run_agent_sync,
)


def test_default_rubric_for_uses_configured_mapping() -> None:
    config = load_config()

    assert (
        default_rubric_for("Deutsch", "Oberstufe", config)
        == "srdp_deutsch_oberstufe.md"
    )
    assert default_rubric_for("Englisch", "Unterstufe", config) == "englisch_a2.md"
    assert default_rubric_for("Englisch", "Oberstufe", config) == "srdp_englisch_b2.md"


def test_rubric_options_for_english_upper_stage_offers_b2_and_b1() -> None:
    config = load_config()

    assert rubric_options_for("Englisch", "Oberstufe", config) == [
        "srdp_englisch_b2.md",
        "srdp_englisch_b1.md",
    ]


def test_run_agent_sync_transports_prompt_via_stdin() -> None:
    prompt = "erste zeile\nquote ' bleibt erhalten"

    output = run_agent_sync("cat", prompt, timeout=5)

    assert output.strip() == prompt


def test_humanize_agent_error_nicht_gefunden() -> None:
    msg = humanize_agent_error("FEHLER: Befehl nicht gefunden: claude", "claude")
    assert "nicht installiert" in msg


def test_humanize_agent_error_timeout() -> None:
    msg = humanize_agent_error("FEHLER: Timeout nach 120s", "claude")
    assert "zu lange gebraucht" in msg


def test_humanize_agent_error_api_key() -> None:
    msg = humanize_agent_error("FEHLER: API key nicht gesetzt", "api")
    assert "API-Schluessel" in msg


def test_check_agent_availability_returns_dict() -> None:
    config = load_config()
    availability = check_agent_availability(config)
    assert isinstance(availability, dict)
    for name in config.get("agent", {}).get("commands", {}):
        assert name in availability
