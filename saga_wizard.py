#!/usr/bin/env python3
"""
SAGA TUI – Wizard-Pattern mit rich + InquirerPy.

Sequentieller Korrektur-Workflow: Dateiauswahl -> Zuordnung -> Analyse -> Review -> DOCX.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if sys.version_info < (3, 11):
    print("Python 3.11+ wird benoetigt.")
    raise SystemExit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    print("rich fehlt: pip install rich")
    raise SystemExit(1)

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
except ImportError:
    print("InquirerPy fehlt: pip install InquirerPy")
    raise SystemExit(1)

try:
    import pyfiglet as _pyfiglet
except ImportError:
    _pyfiglet = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_feedback as gf
import saga_core as nc

PROJECT_ROOT = Path(__file__).resolve().parent

FIRST_RUN_MARKER = Path.home() / ".saga_first_run_done"

STYLE_BRAND = "bold cyan"
STYLE_HEADING = "bold white"
STYLE_SUCCESS = "green"
STYLE_WARNING = "yellow"
STYLE_ERROR = "bold red"
STYLE_DIM = "dim"
STYLE_ACCENT = "cyan"
STYLE_INPUT_LABEL = "bold"
STYLE_TABLE_HEADER = "bold cyan"

TOTAL_STEPS = 5

_ASCII_LOGO = (
    " \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557\n"
    " \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u255a\u2550\u2550\u2550\u2588\u2588\u2554\u255d\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\n"
    " \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551   \u2588\u2588\u2551  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\n"
    " \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551   \u2588\u2588\u2551  \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\n"
    " \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551 \u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551  \u2588\u2588\u2551\n"
    " \u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d"
)


def show_banner(console: Console) -> None:
    console.print()
    if _pyfiglet is not None:
        logo = _pyfiglet.figlet_format("SAGA", font="slant")
    else:
        logo = _ASCII_LOGO
    console.print(Text(logo, style=STYLE_BRAND), highlight=False)
    console.print(
        "  Schularbeits-Analyse mit Generativer AI\n"
        "  Automatisierte Korrektur-Unterstützung für Lehrkräfte\n",
        style=STYLE_DIM,
    )


def show_first_run_help(console: Console) -> None:
    console.print(
        Panel(
            f"[{STYLE_BRAND}]Willkommen bei SAGA![/{STYLE_BRAND}]\n\n"
            "Diese Anwendung hilft dir beim Korrigieren von Schularbeiten.\n\n"
            f"[{STYLE_INPUT_LABEL}]So funktioniert's:[/{STYLE_INPUT_LABEL}]\n"
            f"  1. Lege deine .docx-Dateien in den [{STYLE_ACCENT}]input/[/{STYLE_ACCENT}]-Ordner\n"
            "  2. Starte Neue Korrektur im Hauptmenue\n"
            "  3. Waehle Fach, Schulstufe und Textsorte\n"
            "  4. Lass den LLM die Arbeit analysieren (per API oder CLI)\n"
            "  5. Die Notenempfehlung wird als Word-Dokument im output/-Ordner gespeichert\n\n"
            f"[{STYLE_DIM}]Tipp: Im Hauptmenue unter Einstellungen findest du alle Konfigurationsoptionen.[/{STYLE_DIM}]",
            border_style=STYLE_ACCENT,
            padding=(1, 2),
        )
    )
    console.print()
    inquirer.confirm(message="Verstanden, los geht's?", default=True).execute()


def show_step(console: Console, current: int, total: int, title: str) -> None:
    dots = ""
    for i in range(1, total + 1):
        if i < current:
            dots += "\u25cf "
        elif i == current:
            dots += "\u25c9 "
        else:
            dots += "\u25cb "
    bar = "\u2500" * 50
    console.print()
    console.print(f"  {dots}  [{STYLE_DIM}]Schritt {current}/{total}[/{STYLE_DIM}]")
    console.print(f"  [{STYLE_HEADING}]{title}[/{STYLE_HEADING}]")
    console.print(f"  [{STYLE_DIM}]{bar}[/{STYLE_DIM}]")
    console.print()


def show_assignment_summary(console: Console, assignment: dict[str, Any]) -> None:
    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=False,
        padding=(0, 2),
        border_style=STYLE_DIM,
    )
    table.add_column("Key", style=STYLE_INPUT_LABEL, width=14)
    table.add_column("Value")
    table.add_row("Datei", assignment["filename"])
    table.add_row("Fach", assignment["fach"])
    table.add_row("Schulstufe", assignment["schulstufe"])
    table.add_row("Textsorte", assignment["textsorte"])
    table.add_row("Rubrik", f"[{STYLE_ACCENT}]{assignment['rubric']}[/{STYLE_ACCENT}]")
    console.print(table)
    console.print()


def show_review_table(console: Console, data: dict[str, Any], fname: str) -> None:
    bewertung = data.get("bewertung", {})
    note_data = data.get("notenempfehlung", {})

    table = Table(
        title=f"[{STYLE_HEADING}]{fname}[/{STYLE_HEADING}]",
        box=box.ROUNDED,
        show_lines=True,
        border_style=STYLE_DIM,
        title_style=STYLE_BRAND,
    )
    table.add_column("Kriterium", style=STYLE_INPUT_LABEL, min_width=20)
    table.add_column("Stufe", min_width=30)
    table.add_column("Punkte", justify="center", width=8)

    for key, crit in bewertung.items():
        if not isinstance(crit, dict):
            continue
        punkte = crit.get("punkte", 0)
        if isinstance(punkte, (int, float)):
            if punkte >= 4:
                punkte_str = f"[{STYLE_SUCCESS}]{punkte}[/{STYLE_SUCCESS}]"
            elif punkte >= 2.5:
                punkte_str = f"[{STYLE_WARNING}]{punkte}[/{STYLE_WARNING}]"
            else:
                punkte_str = f"[{STYLE_ERROR}]{punkte}[/{STYLE_ERROR}]"
        else:
            punkte_str = str(punkte)

        label = key.replace("_", " ").title()
        table.add_row(label, str(crit.get("stufe", "?")), punkte_str)

    table.add_section()

    schnitt = note_data.get("durchschnitt", "?")
    note = note_data.get("note", "?")
    bez = note_data.get("bezeichnung", "?")

    if isinstance(note, int):
        if note <= 2:
            note_style = STYLE_SUCCESS
        elif note <= 3:
            note_style = STYLE_WARNING
        else:
            note_style = STYLE_ERROR
    else:
        note_style = ""

    table.add_row("[bold]Durchschnitt[/bold]", "", str(schnitt))
    table.add_row(
        "[bold]Note[/bold]",
        f"[{note_style}]{note} \u2013 {bez}[/{note_style}]",
        "",
    )

    console.print(table)
    console.print()


def main_menu() -> str:
    return inquirer.select(
        message="Hauptmenue",
        choices=[
            Choice(value="neue_korrektur", name="Neue Korrektur starten"),
            Choice(value="analyse_laden", name="Bestehende Analyse laden"),
            Choice(value="einstellungen", name="Einstellungen"),
            Choice(value="beenden", name="Beenden"),
        ],
        default="neue_korrektur",
    ).execute()


def step_file_selection(config: dict[str, Any], console: Console) -> list[Path]:
    input_dir = nc.resolve_path(config,"input")
    docx_files = sorted(input_dir.glob("*.docx")) if input_dir.exists() else []

    if not docx_files:
        console.print(
            f"\n[{STYLE_ERROR}]Keine .docx-Dateien in {input_dir} gefunden.[/{STYLE_ERROR}]"
        )
        console.print(
            f"[{STYLE_DIM}]Bitte Schuelerarbeiten in den input/-Ordner kopieren.[/{STYLE_DIM}]\n"
        )
        return []

    choices = []
    for docx in docx_files:
        wc = nc.count_words(docx)
        warn = " [! < 50 Woerter]" if wc < 50 else ""
        label = f"{docx.name}  ({wc} Woerter){warn}"
        choices.append(Choice(value=docx, name=label, enabled=True))

    selected = inquirer.checkbox(
        message="Welche Arbeiten sollen korrigiert werden? (Leertaste = auswaehlen, Enter = weiter)",
        choices=choices,
        validate=lambda result: len(result) > 0,
        invalid_message="Bitte mindestens eine Datei auswaehlen.",
    ).execute()

    return selected


def step_assignment(
    files: list[Path], config: dict[str, Any], console: Console
) -> list[dict[str, Any]]:
    assignments = []
    defaults = config.get("defaults", {})

    for docx_path in files:
        wc = nc.count_words(docx_path)

        console.print()
        console.print(
            f"  [{STYLE_BRAND}]\u25cf[/{STYLE_BRAND}] [{STYLE_INPUT_LABEL}]{docx_path.name}[/{STYLE_INPUT_LABEL}]  [{STYLE_DIM}]({wc} Woerter)[/{STYLE_DIM}]"
        )
        console.print()

        fach = inquirer.select(
            message="Fach",
            choices=["Deutsch", "Englisch"],
            default=defaults.get("fach", "Deutsch"),
        ).execute()

        schulstufe = inquirer.select(
            message="Schulstufe",
            choices=["Oberstufe", "Unterstufe"],
            default=defaults.get("schulstufe", "Oberstufe"),
        ).execute()

        textsorte = inquirer.text(
            message="Textsorte (frei eingeben)",
            validate=lambda val: len(val.strip()) > 0,
            invalid_message="Textsorte darf nicht leer sein.",
        ).execute()

        auto_rubric = nc.default_rubric_for(fach, schulstufe, config)
        console.print(
            f"  Rubrik: [{STYLE_ACCENT}]{auto_rubric}[/{STYLE_ACCENT}] (automatisch gewaehlt)"
        )

        rubric = auto_rubric
        aendern = inquirer.confirm(
            message="Rubrik aendern?",
            default=False,
        ).execute()

        if aendern:
            all_rubric_files = sorted(
                p.name for p in (nc.resolve_path(config,"rubrics")).glob("*.md")
            )
            rubric_choices = [Choice(value=r, name=r) for r in all_rubric_files]
            rubric = inquirer.select(
                message="Rubrik auswaehlen",
                choices=rubric_choices,
                default=auto_rubric,
            ).execute()

        assignment = {
            "path": docx_path,
            "filename": docx_path.name,
            "fach": fach,
            "schulstufe": schulstufe,
            "textsorte": textsorte,
            "rubric": rubric,
        }
        assignments.append(assignment)
        show_assignment_summary(console, assignment)

    return assignments


def step_analysis(
    assignments: list[dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    schema: dict[str, Any],
) -> dict[str, dict[str, Any]]:

    results: dict[str, dict[str, Any]] = {}
    api_enabled = config.get("api", {}).get("enabled", False)

    while True:
        choices = [
            Choice(value="clipboard", name="Prompt in Zwischenablage kopieren"),
            Choice(value="anzeigen", name="Prompt anzeigen (zum manuellen Kopieren)"),
        ]

        if api_enabled:
            choices.append(Choice(value="api", name="Ueber Anthropic API analysieren"))

        availability = nc.check_agent_availability(config)
        if any(availability.values()):
            choices.append(Choice(value="agent", name="CLI-Agent starten"))

        choices.extend(
            [
                Choice(value="json_laden", name="JSON-Datei manuell laden"),
                Choice(value="weiter", name="Weiter zum Review (ohne neue Analyse)"),
            ]
        )

        mode = inquirer.select(
            message="Wie soll die Analyse durchgefuehrt werden?",
            choices=choices,
        ).execute()

        if mode == "clipboard":
            _prompt_to_clipboard(assignments, config, console, results)
        elif mode == "anzeigen":
            _prompt_anzeigen(assignments, config, console, results)
        elif mode == "api":
            _run_api(assignments, config, console, schema, results)
        elif mode == "agent":
            _run_agent(assignments, config, console, schema, results)
        elif mode == "json_laden":
            _load_json_file(config, console, schema, results)
        elif mode == "weiter":
            break

        if results:
            nochmal = inquirer.confirm(
                message="Weitere Analysen durchfuehren?",
                default=False,
            ).execute()
            if not nochmal:
                break

    return results


def _prompt_to_clipboard(
    assignments: list[dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    results: dict[str, dict[str, Any]],
) -> None:
    for a in assignments:
        if a["filename"] in results:
            continue
        docx_text = nc.read_docx_text(a["path"])
        rubric_content = nc.load_rubric(a["rubric"], config)
        prompt = nc.build_analysis_prompt(
            docx_text,
            rubric_content,
            a["fach"],
            a["schulstufe"],
            a["textsorte"],
            config,
        )
        if nc.copy_to_clipboard(prompt):
            console.print(
                f"  [{STYLE_SUCCESS}]Prompt fuer {a['filename']} in Zwischenablage kopiert.[/{STYLE_SUCCESS}]"
            )
        else:
            console.print(
                f"  [{STYLE_WARNING}]Zwischenablage nicht verfuegbar. Prompt wird angezeigt:[/{STYLE_WARNING}]"
            )
            console.print(
                Panel(
                    prompt[:2000] + ("..." if len(prompt) > 2000 else ""),
                    title=f"Prompt: {a['filename']}",
                    border_style=STYLE_WARNING,
                )
            )
        console.print(
            f"[{STYLE_DIM}]Speichere das JSON-Ergebnis nach output/feedback_data/ und waehle 'JSON-Datei manuell laden'.[/{STYLE_DIM}]"
        )
        console.print()


def _prompt_anzeigen(
    assignments: list[dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    results: dict[str, dict[str, Any]],
) -> None:
    for a in assignments:
        if a["filename"] in results:
            continue

        docx_text = nc.read_docx_text(a["path"])
        rubric_content = nc.load_rubric(a["rubric"], config)

        console.print()
        console.rule(f"[{STYLE_HEADING}]Prompt fuer {a['filename']}[/{STYLE_HEADING}]")

        meta_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        meta_table.add_column("Key", style=STYLE_INPUT_LABEL)
        meta_table.add_column("Value")
        meta_table.add_row("Fach", a["fach"])
        meta_table.add_row("Schulstufe", a["schulstufe"])
        meta_table.add_row("Textsorte", a["textsorte"])
        meta_table.add_row("Rubrik", f"[{STYLE_ACCENT}]{a['rubric']}[/{STYLE_ACCENT}]")
        console.print(meta_table)
        console.print()

        preview = docx_text[:500] + ("..." if len(docx_text) > 500 else "")
        console.print(
            Panel(
                preview,
                title="Schuelertext (Vorschau)",
                border_style=STYLE_SUCCESS,
                padding=(1, 1),
            )
        )
        console.print()

        rubric_preview = "\n".join(rubric_content.splitlines()[:8])
        console.print(
            Panel(
                rubric_preview + f"\n[{STYLE_DIM}]...[/{STYLE_DIM}]",
                title="Bewertungsraster (Auszug)",
                border_style=STYLE_ACCENT,
                padding=(1, 1),
            )
        )
        console.print()

        console.print(
            f"[{STYLE_DIM}]  JSON-Schema und Beispiel-JSON werden im Prompt mitgesendet.[/{STYLE_DIM}]"
        )
        console.print()

        prompt = nc.build_analysis_prompt(
            docx_text,
            rubric_content,
            a["fach"],
            a["schulstufe"],
            a["textsorte"],
            config,
        )

        action = inquirer.select(
            message="Was tun?",
            choices=[
                Choice(value="clipboard", name="Prompt in Zwischenablage kopieren"),
                Choice(value="full", name="Vollstaendigen Prompt anzeigen"),
                Choice(value="skip", name="Ueberspringen"),
            ],
        ).execute()

        if action == "clipboard":
            if nc.copy_to_clipboard(prompt):
                console.print(
                    f"  [{STYLE_SUCCESS}]In Zwischenablage kopiert.[/{STYLE_SUCCESS}]"
                )
            else:
                console.print(
                    f"  [{STYLE_WARNING}]Zwischenablage nicht verfuegbar.[/{STYLE_WARNING}]"
                )
                console.print(
                    Panel(
                        prompt,
                        title="Vollstaendiger Prompt",
                        border_style=STYLE_WARNING,
                    )
                )
        elif action == "full":
            console.print(
                Panel(
                    prompt,
                    title="Vollstaendiger Prompt",
                    border_style=STYLE_BRAND,
                    padding=(1, 1),
                )
            )
            inquirer.confirm(message="Weiter?", default=True).execute()


def _run_api(
    assignments: list[dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    schema: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> None:
    model = config.get("api", {}).get("model", "claude-sonnet-4-6")
    timeout = config.get("agent", {}).get("timeout_seconds", 120)

    for a in assignments:
        if a["filename"] in results:
            continue

        console.print(
            f"  [{STYLE_HEADING}]Analysiere {a['filename']}...[/{STYLE_HEADING}]"
        )
        docx_text = nc.read_docx_text(a["path"])
        rubric_content = nc.load_rubric(a["rubric"], config)
        prompt = nc.build_analysis_prompt(
            docx_text,
            rubric_content,
            a["fach"],
            a["schulstufe"],
            a["textsorte"],
            config,
        )

        console.print(
            f"  [{STYLE_DIM}]Sende an Anthropic API ({model})...[/{STYLE_DIM}]"
        )
        output = nc.run_anthropic_api(prompt, model, timeout)

        if output.startswith("FEHLER"):
            msg = nc.humanize_agent_error(output, "Anthropic API")
            console.print(f"  [{STYLE_ERROR}]{msg}[/{STYLE_ERROR}]")
            paths = nc.build_project_paths(config)
            nc.log_tui_error(paths, f"{a['filename']}: {output}")
            retry = inquirer.confirm(
                message="Erneut versuchen?", default=False
            ).execute()
            if retry:
                output = nc.run_anthropic_api(prompt, model, timeout)
                if output.startswith("FEHLER"):
                    console.print(
                        f"  [{STYLE_ERROR}]Erneut fehlgeschlagen: {nc.humanize_agent_error(output, 'Anthropic API')}[/{STYLE_ERROR}]"
                    )
                    continue
            else:
                continue

        try:
            data = nc.extract_json_from_llm(output)
        except json.JSONDecodeError as e:
            console.print(f"  [{STYLE_ERROR}]JSON-Parse-Fehler: {e}[/{STYLE_ERROR}]")
            paths = nc.build_project_paths(config)
            nc.log_tui_error(paths, f"{a['filename']}: JSON-Parse-Fehler: {e}")
            continue

        errors = nc.validate_against_schema(data, schema)
        if errors:
            console.print(
                f"  [{STYLE_WARNING}]Schema-Warnungen ({len(errors)}):[/{STYLE_WARNING}]"
            )
            for e in errors[:3]:
                console.print(f"    [{STYLE_WARNING}]- {e}[/{STYLE_WARNING}]")
        else:
            console.print(f"  [{STYLE_SUCCESS}]Analyse OK.[/{STYLE_SUCCESS}]")

        results[a["filename"]] = data
        _save_analysis_json(a["filename"], data, config)
        console.print()


def _run_agent(
    assignments: list[dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    schema: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> None:
    availability = nc.check_agent_availability(config)
    available_agents = [name for name, ok in availability.items() if ok]

    if not available_agents:
        console.print(f"[{STYLE_ERROR}]Keine CLI-Agents verfuegbar.[/{STYLE_ERROR}]")
        console.print(
            f"[{STYLE_DIM}]Tipp: Nutze 'Prompt in Zwischenablage kopieren' oder aktiviere den API-Modus.[/{STYLE_DIM}]"
        )
        return

    agent_choices = [Choice(value=name, name=name) for name in available_agents]
    default_agent = config.get("agent", {}).get("default", "claude")
    if default_agent not in available_agents:
        default_agent = available_agents[0]

    agent_name = inquirer.select(
        message="Welchen Agent verwenden?",
        choices=agent_choices,
        default=default_agent,
    ).execute()

    commands = config.get("agent", {}).get("commands", {})
    cmd_template = commands.get(agent_name, agent_name)
    timeout = config.get("agent", {}).get("timeout_seconds", 120)

    for a in assignments:
        if a["filename"] in results:
            continue

        console.print(
            f"  [{STYLE_HEADING}]Analysiere {a['filename']}...[/{STYLE_HEADING}]"
        )
        docx_text = nc.read_docx_text(a["path"])
        rubric_content = nc.load_rubric(a["rubric"], config)
        prompt = nc.build_analysis_prompt(
            docx_text,
            rubric_content,
            a["fach"],
            a["schulstufe"],
            a["textsorte"],
            config,
        )

        console.print(
            f"  [{STYLE_DIM}]Sende an {agent_name} (Timeout: {timeout}s)...[/{STYLE_DIM}]"
        )
        output = nc.run_agent_sync(cmd_template, prompt, timeout)

        if output.startswith("FEHLER"):
            msg = nc.humanize_agent_error(output, agent_name)
            console.print(f"  [{STYLE_ERROR}]{msg}[/{STYLE_ERROR}]")
            paths = nc.build_project_paths(config)
            nc.log_tui_error(paths, f"{a['filename']}: {output}")
            retry = inquirer.confirm(
                message="Erneut versuchen?", default=False
            ).execute()
            if retry:
                output = nc.run_agent_sync(cmd_template, prompt, timeout)
                if output.startswith("FEHLER"):
                    console.print(
                        f"  [{STYLE_ERROR}]Erneut fehlgeschlagen: {nc.humanize_agent_error(output, agent_name)}[/{STYLE_ERROR}]"
                    )
                    continue
            else:
                continue

        try:
            data = nc.extract_json_from_llm(output)
        except json.JSONDecodeError as e:
            console.print(f"  [{STYLE_ERROR}]JSON-Parse-Fehler: {e}[/{STYLE_ERROR}]")
            paths = nc.build_project_paths(config)
            nc.log_tui_error(paths, f"{a['filename']}: JSON-Parse-Fehler: {e}")
            continue

        errors = nc.validate_against_schema(data, schema)
        if errors:
            console.print(
                f"  [{STYLE_WARNING}]Schema-Warnungen ({len(errors)}):[/{STYLE_WARNING}]"
            )
            for e in errors[:3]:
                console.print(f"    [{STYLE_WARNING}]- {e}[/{STYLE_WARNING}]")
        else:
            console.print(f"  [{STYLE_SUCCESS}]Analyse OK.[/{STYLE_SUCCESS}]")

        results[a["filename"]] = data
        _save_analysis_json(a["filename"], data, config)
        console.print()


def _load_json_file(
    config: dict[str, Any],
    console: Console,
    schema: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> None:
    paths = nc.build_project_paths(config)
    paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
    json_files = sorted(paths.feedback_data_dir.glob("*.json"))

    if not json_files:
        console.print(
            f"[{STYLE_WARNING}]Keine JSON-Dateien in output/feedback_data/ gefunden.[/{STYLE_WARNING}]"
        )
        return

    choices = [Choice(value=jf, name=jf.name) for jf in json_files]
    selected = inquirer.select(
        message="Welche Datei laden?",
        choices=choices,
    ).execute()

    if not selected:
        return

    try:
        data = json.loads(selected.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[{STYLE_ERROR}]Fehler beim Laden: {e}[/{STYLE_ERROR}]")
        return

    errors = nc.validate_against_schema(data, schema)
    if errors:
        console.print(
            f"[{STYLE_WARNING}]Schema-Warnungen ({len(errors)}):[/{STYLE_WARNING}]"
        )
        for e in errors[:3]:
            console.print(f"  - {e}")
    else:
        console.print(f"[{STYLE_SUCCESS}]Schema-Validierung OK.[/{STYLE_SUCCESS}]")

    original_name = data.get("datei", selected.stem)
    results[original_name] = data
    console.print(f"[{STYLE_SUCCESS}]{selected.name} geladen.[/{STYLE_SUCCESS}]")
    console.print()


def _save_analysis_json(
    filename: str, data: dict[str, Any], config: dict[str, Any]
) -> None:
    paths = nc.build_project_paths(config)
    paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
    out_name = Path(filename).stem + "_analysis.json"
    (paths.feedback_data_dir / out_name).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def step_review(
    results: dict[str, dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    schema: dict[str, Any],
) -> None:
    if not results:
        console.print(
            f"[{STYLE_WARNING}]Keine Ergebnisse zum Review.[/{STYLE_WARNING}]"
        )
        return

    filenames = list(results.keys())
    current_idx = 0

    while True:
        fname = filenames[current_idx]
        data = results[fname]

        console.print()
        console.rule(
            f"[{STYLE_HEADING}]Schritt 4: Review  ({current_idx + 1}/{len(filenames)})[/{STYLE_HEADING}]"
        )
        console.print()

        show_review_table(console, data, fname)

        errors = nc.validate_against_schema(data, schema)
        if errors:
            console.print(
                f"[{STYLE_ERROR}]Schema-Validierung: {len(errors)} Fehler[/{STYLE_ERROR}]"
            )
            for e in errors[:3]:
                console.print(f"  [{STYLE_ERROR}]- {e}[/{STYLE_ERROR}]")
            console.print()
        else:
            console.print(f"[{STYLE_SUCCESS}]Schema-Validierung: OK[/{STYLE_SUCCESS}]")
            console.print()

        choices = [
            Choice(value="details", name="Details zu einem Kriterium anzeigen"),
            Choice(value="json_editor", name="JSON im Editor oeffnen"),
            Choice(value="docx", name="DOCX generieren"),
        ]
        if len(filenames) > 1 and current_idx > 0:
            choices.append(Choice(value="prev", name="Vorherige Datei"))
        if len(filenames) > 1 and current_idx < len(filenames) - 1:
            choices.append(Choice(value="next", name="Naechste Datei"))
        choices.append(Choice(value="zurueck", name="Zurueck"))

        action = inquirer.select(
            message="Was moechtest du tun?",
            choices=choices,
        ).execute()

        if action == "details":
            _show_criterion_details(data, console)
        elif action == "json_editor":
            _edit_json_external(fname, data, results, config, console, schema)
        elif action == "docx":
            _generate_docx({fname: data}, config, console)
        elif action == "prev":
            current_idx -= 1
        elif action == "next":
            current_idx += 1
        elif action == "zurueck":
            break


def _show_criterion_details(data: dict[str, Any], console: Console) -> None:
    bewertung = data.get("bewertung", {})
    choices = [
        Choice(value=key, name=key.replace("_", " ").title())
        for key, val in bewertung.items()
        if isinstance(val, dict)
    ]
    if not choices:
        console.print(f"[{STYLE_WARNING}]Keine Kriterien vorhanden.[/{STYLE_WARNING}]")
        return

    selected_key = inquirer.select(
        message="Welches Kriterium?",
        choices=choices,
    ).execute()

    crit = bewertung[selected_key]
    sections = []
    sections.append(
        f"[{STYLE_HEADING}]{selected_key.replace('_', ' ').title()}[/{STYLE_HEADING}]"
    )
    sections.append(
        f"Stufe: {crit.get('stufe', '?')}  |  Punkte: {crit.get('punkte', '?')}"
    )
    sections.append("")

    if crit.get("staerken"):
        sections.append(f"[{STYLE_SUCCESS}]Staerken:[/{STYLE_SUCCESS}]")
        for s in crit["staerken"]:
            sections.append(f"  [{STYLE_SUCCESS}]+ {s}[/{STYLE_SUCCESS}]")

    if crit.get("schwaechen"):
        sections.append(f"[{STYLE_ERROR}]Schwaechen:[/{STYLE_ERROR}]")
        for s in crit["schwaechen"]:
            sections.append(f"  [{STYLE_ERROR}]- {s}[/{STYLE_ERROR}]")

    if crit.get("vorschlaege"):
        sections.append(f"[{STYLE_ACCENT}]Verbesserungsvorschlaege:[/{STYLE_ACCENT}]")
        for s in crit["vorschlaege"]:
            sections.append(f"  > {s}")

    if crit.get("fehler_detail"):
        sections.append(f"[{STYLE_ERROR}]Fehler im Detail:[/{STYLE_ERROR}]")
        for s in crit["fehler_detail"]:
            sections.append(f"  [{STYLE_ERROR}]! {s}[/{STYLE_ERROR}]")

    if crit.get("fehlerschwerpunkte"):
        sections.append("Fehlerschwerpunkte:")
        for s in crit["fehlerschwerpunkte"]:
            sections.append(f"  * {s}")

    if crit.get("rhetorische_figuren"):
        sections.append("Rhetorische Figuren:")
        for s in crit["rhetorische_figuren"]:
            sections.append(f"  ~ {s}")

    console.print(Panel("\n".join(sections), border_style=STYLE_ACCENT, padding=(1, 1)))
    console.print()


def _edit_json_external(
    fname: str,
    data: dict[str, Any],
    results: dict[str, dict[str, Any]],
    config: dict[str, Any],
    console: Console,
    schema: dict[str, Any],
) -> None:
    paths = nc.build_project_paths(config)
    paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = paths.feedback_data_dir / (Path(fname).stem + "_edit.json")
    tmp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    editor = os.environ.get("EDITOR", "nano")
    console.print(f"[{STYLE_DIM}]Oeffne {tmp_path} in {editor}...[/{STYLE_DIM}]")
    try:
        subprocess.run([editor, str(tmp_path)])
    except FileNotFoundError:
        console.print(
            f"[{STYLE_ERROR}]Editor '{editor}' nicht gefunden. Versuche nano...[/{STYLE_ERROR}]"
        )
        try:
            subprocess.run(["nano", str(tmp_path)])
        except FileNotFoundError:
            console.print(
                f"[{STYLE_ERROR}]Auch nano nicht gefunden. Ueberspringe.[/{STYLE_ERROR}]"
            )
            return

    try:
        edited = json.loads(tmp_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        console.print(f"[{STYLE_ERROR}]JSON-Fehler nach Editieren: {e}[/{STYLE_ERROR}]")
        retry = inquirer.confirm(message="Erneut editieren?", default=True).execute()
        if retry:
            _edit_json_external(fname, data, results, config, console, schema)
        return

    errors = nc.validate_against_schema(edited, schema)
    if errors:
        console.print(
            f"[{STYLE_WARNING}]Schema-Warnungen ({len(errors)}):[/{STYLE_WARNING}]"
        )
        for e in errors[:3]:
            console.print(f"  - {e}")
        retry = inquirer.confirm(
            message="Trotzdem uebernehmen?", default=True
        ).execute()
        if not retry:
            return

    results[fname] = edited
    _save_analysis_json(fname, edited, config)
    console.print(f"[{STYLE_SUCCESS}]JSON gespeichert.[/{STYLE_SUCCESS}]")
    console.print()


def _generate_docx(
    results: dict[str, dict[str, Any]],
    config: dict[str, Any],
    console: Console,
) -> None:
    paths = nc.build_project_paths(config)
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    gen_results: list[tuple[str, Path, bool]] = []

    for fname, data in results.items():
        try:
            feedback = gf.parse_feedback_data(data)
            out_name = gf.output_filename(feedback.datei)
            out_path = paths.output_dir / out_name

            if out_path.exists():
                overwrite = inquirer.confirm(
                    message=f"{out_name} existiert bereits. Ueberschreiben?",
                    default=False,
                ).execute()
                if not overwrite:
                    console.print(
                        f"  [{STYLE_DIM}]Uebersprungen: {out_name}[/{STYLE_DIM}]"
                    )
                    continue

            doc = gf.build_feedback_document(feedback)
            doc.save(str(out_path))
            gen_results.append((out_name, out_path, True))
        except Exception as e:
            gen_results.append((fname, Path(""), False))
            nc.log_tui_error(paths, f"{fname}: {e}")

    console.print()
    for name, path, success in gen_results:
        if success:
            console.print(
                f"  [{STYLE_SUCCESS}]\u2713[/{STYLE_SUCCESS}]  [bold]{name}[/bold]"
            )
            console.print(f"     [{STYLE_DIM}]{path}[/{STYLE_DIM}]")
        else:
            console.print(
                f"  [{STYLE_ERROR}]\u2717[/{STYLE_ERROR}]  [bold]{name}[/bold]"
            )
    console.print()


def run_korrektur_wizard(config: dict[str, Any], console: Console) -> None:
    schema = nc.load_schema(config)

    show_step(console, 1, TOTAL_STEPS, "Dateiauswahl")
    files = step_file_selection(config, console)
    if not files:
        return

    show_step(console, 2, TOTAL_STEPS, "Zuordnung")
    assignments = step_assignment(files, config, console)

    show_step(console, 3, TOTAL_STEPS, "Analyse")
    results = step_analysis(assignments, config, console, schema)

    if not results:
        console.print(
            f"\n[{STYLE_WARNING}]Keine Analyseergebnisse. Zurueck zum Hauptmenue.[/{STYLE_WARNING}]"
        )
        return

    show_step(console, 4, TOTAL_STEPS, "Review")
    step_review(results, config, console, schema)

    generate = inquirer.confirm(
        message="DOCX-Dateien generieren?",
        default=True,
    ).execute()
    if generate:
        show_step(console, 5, TOTAL_STEPS, "DOCX-Generierung")
        _generate_docx(results, config, console)

    action = inquirer.select(
        message="Was nun?",
        choices=[
            Choice(value="ordner", name="Ordner oeffnen"),
            Choice(value="neu", name="Neue Korrektur starten"),
            Choice(value="menue", name="Zurueck zum Hauptmenue"),
            Choice(value="beenden", name="Beenden"),
        ],
        default="ordner",
    ).execute()

    if action == "ordner":
        nc.open_file(nc.build_project_paths(config).output_dir)
    elif action == "neu":
        run_korrektur_wizard(config, console)
    elif action == "menue":
        pass
    elif action == "beenden":
        raise SystemExit(0)


def run_load_existing(config: dict[str, Any], console: Console) -> None:
    schema = nc.load_schema(config)
    paths = nc.build_project_paths(config)
    paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
    json_files = sorted(paths.feedback_data_dir.glob("*.json"))

    if not json_files:
        console.print(
            f"[{STYLE_WARNING}]Keine JSON-Dateien in output/feedback_data/ gefunden.[/{STYLE_WARNING}]"
        )
        return

    choices = [Choice(value=jf, name=jf.name) for jf in json_files]
    selected = inquirer.select(
        message="Welche Datei laden?",
        choices=choices,
    ).execute()

    if not selected:
        return

    try:
        data = json.loads(selected.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[{STYLE_ERROR}]Fehler: {e}[/{STYLE_ERROR}]")
        return

    original_name = data.get("datei", selected.stem)
    results = {original_name: data}

    errors = nc.validate_against_schema(data, schema)
    if errors:
        console.print(
            f"[{STYLE_WARNING}]Schema-Warnungen: {len(errors)}[/{STYLE_WARNING}]"
        )
    else:
        console.print(f"[{STYLE_SUCCESS}]Schema-Validierung OK.[/{STYLE_SUCCESS}]")

    show_step(console, 4, TOTAL_STEPS, "Review")
    step_review(results, config, console, schema)

    generate = inquirer.confirm(message="DOCX generieren?", default=True).execute()
    if generate:
        show_step(console, 5, TOTAL_STEPS, "DOCX-Generierung")
        _generate_docx(results, config, console)


def show_settings(config: dict[str, Any], console: Console) -> None:
    while True:
        console.print()
        console.rule(f"[{STYLE_HEADING}]Einstellungen[/{STYLE_HEADING}]")
        console.print()

        table = Table(box=box.SIMPLE)
        table.add_column("Einstellung", style=STYLE_INPUT_LABEL)
        table.add_column("Wert")

        table.add_row(
            "Default-Agent",
            f"[{STYLE_ACCENT}]{config.get('agent', {}).get('default', '?')}[/{STYLE_ACCENT}]",
        )
        table.add_row(
            "Timeout", f"{config.get('agent', {}).get('timeout_seconds', '?')}s"
        )
        table.add_row("Input-Ordner", str(nc.resolve_path(config,"input")))
        table.add_row("Output-Ordner", str(nc.resolve_path(config,"output")))
        table.add_row("Rubric-Ordner", str(nc.resolve_path(config,"rubrics")))
        table.add_row("Default-Fach", config.get("defaults", {}).get("fach", "?"))
        table.add_row(
            "Default-Schulstufe", config.get("defaults", {}).get("schulstufe", "?")
        )

        api_cfg = config.get("api", {})
        api_status = "aktiv" if api_cfg.get("enabled") else "deaktiviert"
        table.add_row("API-Modus", f"[{STYLE_ACCENT}]{api_status}[/{STYLE_ACCENT}]")
        if api_cfg.get("enabled"):
            table.add_row("API-Model", api_cfg.get("model", "?"))

        console.print(table)
        console.print()

        commands = config.get("agent", {}).get("commands", {})
        if commands:
            console.print(f"[{STYLE_HEADING}]CLI-Agents:[/{STYLE_HEADING}]")
            availability = nc.check_agent_availability(config)
            for name, cmd in commands.items():
                avail = availability.get(name, False)
                if avail:
                    console.print(
                        f"  [{STYLE_SUCCESS}]\u2713[/{STYLE_SUCCESS}]  [{STYLE_ACCENT}]{name}[/{STYLE_ACCENT}]  [{STYLE_DIM}]{cmd}[/{STYLE_DIM}]"
                    )
                else:
                    console.print(
                        f"  [{STYLE_ERROR}]\u2717[/{STYLE_ERROR}]  [{STYLE_ACCENT}]{name}[/{STYLE_ACCENT}]  [{STYLE_DIM}]nicht installiert[/{STYLE_DIM}]"
                    )
            console.print()

        action = inquirer.select(
            message="Was moechtest du tun?",
            choices=[
                Choice(value="check_agents", name="Agent-Verfuegbarkeit pruefen"),
                Choice(value="test_api", name="API-Verbindung testen"),
                Choice(
                    value="open_config", name="Konfigurationsdatei im Editor oeffnen"
                ),
                Choice(value="zurueck", name="Zurueck"),
            ],
        ).execute()

        if action == "check_agents":
            console.print()
            availability = nc.check_agent_availability(config)
            for name, avail in availability.items():
                cmd = config["agent"]["commands"][name]
                if avail:
                    console.print(
                        f"  [{STYLE_SUCCESS}]\u2713[/{STYLE_SUCCESS}]  [{STYLE_ACCENT}]{name}[/{STYLE_ACCENT}]  [{STYLE_DIM}]{cmd}[/{STYLE_DIM}]"
                    )
                else:
                    console.print(
                        f"  [{STYLE_ERROR}]\u2717[/{STYLE_ERROR}]  [{STYLE_ACCENT}]{name}[/{STYLE_ACCENT}]  [{STYLE_DIM}]nicht installiert[/{STYLE_DIM}]"
                    )
            console.print()
        elif action == "test_api":
            _test_api_connection(config, console)
        elif action == "open_config":
            _open_config_in_editor(console)
        elif action == "zurueck":
            break


def _test_api_connection(config: dict[str, Any], console: Console) -> None:
    api_cfg = config.get("api", {})
    if not api_cfg.get("enabled"):
        console.print(
            f"[{STYLE_WARNING}]API-Modus ist nicht aktiviert.[/{STYLE_WARNING}]"
        )
        console.print(
            f"[{STYLE_DIM}]Setze [api] enabled = true in saga_config.toml.[/{STYLE_DIM}]"
        )
        console.print()
        return

    model = api_cfg.get("model", "claude-sonnet-4-6")
    console.print(
        f"[{STYLE_DIM}]Teste Verbindung zu Anthropic API ({model})...[/{STYLE_DIM}]"
    )
    output = nc.run_anthropic_api("Antworte nur mit dem Wort: OK", model, timeout=15)
    if output.strip() in ("OK", "Ok", "ok", "OK."):
        console.print(f"[{STYLE_SUCCESS}]Verbindung OK.[/{STYLE_SUCCESS}]")
    elif output.startswith("FEHLER"):
        console.print(
            f"[{STYLE_ERROR}]{nc.humanize_agent_error(output, 'Anthropic API')}[/{STYLE_ERROR}]"
        )
    else:
        console.print(
            f"[{STYLE_WARNING}]Unerwartete Antwort: {output[:100]}[/{STYLE_WARNING}]"
        )
    console.print()


def _open_config_in_editor(console: Console) -> None:
    config_path = PROJECT_ROOT / "saga_config.toml"
    editor = os.environ.get("EDITOR", "nano")
    console.print(f"[{STYLE_DIM}]Oeffne {config_path} in {editor}...[/{STYLE_DIM}]")
    try:
        subprocess.run([editor, str(config_path)])
    except FileNotFoundError:
        console.print(
            f"[{STYLE_ERROR}]Editor '{editor}' nicht gefunden.[/{STYLE_ERROR}]"
        )


def main() -> None:
    try:
        config = nc.load_config()
    except FileNotFoundError as e:
        print(f"Fehler: {e}")
        raise SystemExit(1)

    console = Console()
    show_banner(console)

    if not FIRST_RUN_MARKER.exists():
        show_first_run_help(console)
        try:
            FIRST_RUN_MARKER.touch()
        except OSError:
            pass

    while True:
        try:
            choice = main_menu()
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[{STYLE_DIM}]Beendet.[/{STYLE_DIM}]")
            break

        if choice == "neue_korrektur":
            try:
                run_korrektur_wizard(config, console)
            except (KeyboardInterrupt, EOFError):
                console.print(
                    f"\n[{STYLE_DIM}]Abgebrochen. Zurueck zum Hauptmenue.[/{STYLE_DIM}]"
                )
        elif choice == "analyse_laden":
            try:
                run_load_existing(config, console)
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n[{STYLE_DIM}]Abgebrochen.[/{STYLE_DIM}]")
        elif choice == "einstellungen":
            show_settings(config, console)
        elif choice == "beenden":
            console.print(f"[{STYLE_DIM}]Beendet.[/{STYLE_DIM}]")
            break


if __name__ == "__main__":
    main()
