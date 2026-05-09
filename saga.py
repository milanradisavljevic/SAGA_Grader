#!/usr/bin/env python3
"""
SAGA Dashboard – Textual-basiertes Korrektur-Dashboard.

Drei-Spalten-Layout mit Dateiliste, Zuordnung und Vorschau.
Tastatur-Navigation, modale Dialoge, asynchrone Analyse.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

if sys.version_info < (3, 11):
    print("Python 3.11+ wird benoetigt.")
    raise SystemExit(1)

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical, VerticalScroll
    from textual.reactive import reactive
    from textual.screen import ModalScreen
    from textual.widget import Widget
    from textual.widgets import (
        Button,
        Footer,
        Input,
        Label,
        ListItem,
        ListView,
        Markdown,
        Select,
        Static,
        TextArea,
    )
except ImportError:
    print("textual fehlt: pip install textual")
    raise SystemExit(1)

from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import saga_core as nc
import generate_feedback as gf

# Notenfarben (passend zum DOCX-Farbschema)
_NOTE_COLORS: dict[int, str] = {
    1: "#70C070",  # Hellgrün
    2: "#008000",  # Dunkelgrün
    3: "#C0A000",  # Gelb
    4: "#E06000",  # Orange
    5: "#C00000",  # Rot
}


def _note_rich_text(note: int | str, label: str) -> Text:
    """Gibt ein farbig formatiertes Rich-Text-Objekt für die Notenzeile zurück."""
    color = _NOTE_COLORS.get(int(note) if str(note).isdigit() else 0, "#C00000")
    t = Text()
    t.append(label, style=f"bold {color}")
    return t


class FileStatus(Enum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    DONE = "done"
    PROGRESS = "progress"
    ERROR = "error"


STATUS_SYMBOLS = {
    FileStatus.DONE: ("●", "status-done"),
    FileStatus.ANALYZED: ("●", "status-analyzed"),
    FileStatus.PROGRESS: ("◐", "status-progress"),
    FileStatus.PENDING: ("○", "status-pending"),
    FileStatus.ERROR: ("✗", "status-error"),
}


@dataclass
class FileInfo:
    path: Path
    word_count: int = 0
    status: FileStatus = FileStatus.PENDING
    fach: str = ""
    schulstufe: str = ""
    textsorte: str = ""
    rubric: str = ""
    schueler: str = ""
    analysis: dict[str, Any] | None = None
    marked: bool = False


def safe_id(prefix: str, raw: str) -> str:
    digest = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{prefix}-{digest}"


# =============================================================================
# Logo constants for SAGA TUI v8
# =============================================================================

LOGO_FULL = r"""
██████╗  █████╗  ██████╗  █████╗ 
██╔══██╗██╔══██╗██╔════╝ ██╔══██╗
███████║███████║██║  ███╗███████║
██╔══██║██╔══██║██║   ██║██╔══██║
██║  ██║██║  ██║╚██████╔╝██║  ██║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
"""

LOGO_COMPACT = r"""
▒█░▒█ ░█▀▀█ ▒█▀▀▀█ ░█▀▀█
▒█▀▀█ ▒█▄▄█ ░▀▀▀▄▄ ▒█▄▄█
▒█░▒█ ▒█░▒█ ▒█▄▄▄█ ▒█░▒█
"""


def render_logo_gradient(width: int = 120) -> Text:
    """Render SAGA logo with vertical gradient coloring."""
    logo = LOGO_FULL if width >= 100 else LOGO_COMPACT
    lines = logo.strip("\n").split("\n")
    colors = ["#ff00ff", "#cc44ff", "#8888ff", "#00aaff", "#00ddff", "#00ffaa"]

    result = Text()
    for line, color in zip(lines, colors):
        result.append(line + "\n", style=f"bold {color}")
    return result


def render_acronym() -> Text:
    """Render SAGA acronym with highlighted initial letters."""
    parts = [
        ("S", "chularbeits-"),
        ("A", "nalyse mit"),
        ("G", "enerativer"),
        ("A", "I"),
    ]
    result = Text()
    for i, (letter, rest) in enumerate(parts):
        result.append(letter, style="bold #00ddff")
        result.append(rest, style="dim white")
        if i < len(parts) - 1:
            result.append("  ", style="dim white")
    return result


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    def compose(self) -> ComposeResult:
        with Container(classes="help-container"):
            yield Label("HILFE – SAGA Dashboard", classes="panel-title")
            yield Static(
                "Navigation:\n"
                "  ↑/↓        Dateiliste navigieren\n"
                "  Tab         Panel-Fokus wechseln\n"
                "  /           Suche in Dateiliste\n"
                "  Esc         Suche beenden / Dialog schliessen\n\n"
                "Aktionen:\n"
                "  a           Analyse starten (API)\n"
                "  Shift+A     Analyse fuer alle markierten Dateien\n"
                "  r           Review-Dialog oeffnen\n"
                "  d           DOCX generieren\n"
                "  Shift+D     DOCX fuer alle markierten Dateien\n"
                "  e           Zuordnung bearbeiten (Fach/Stufe/Textsorte/Rubrik)\n"
                "  Space       Datei markieren (Batch)\n"
                "  Enter       Vorschau-Tab wechseln (Text→Bewertung→Rubrik)\n"
                "  1/2/3       Vorschau direkt auf Text/Bewertung/Rubrik\n"
                "  Del         Datei entfernen\n\n"
                "Allgemein:\n"
                "  s           Einstellungen\n"
                "  ? / F1      Diese Hilfe\n"
                "  o           Sortierung aendern\n"
                "  q           Beenden"
            )


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(classes="confirm-container"):
            yield Label(self.message)
            with Horizontal():
                yield Button("Ja", variant="success", id="confirm-yes")
                yield Button("Nein", variant="error", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class SettingsScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    _PROVIDERS = [
        ("GLM / ZhipuAI (kostenlos)", "glm"),
        ("Kimi / Moonshot", "kimi"),
        ("OpenAI", "openai"),
        ("Anthropic / Claude", "anthropic"),
        ("Ollama (lokal)", "ollama"),
    ]
    _MODELS_BY_PROVIDER: dict[str, list[tuple[str, str]]] = {
        "glm": [("glm-4-flash (gratis)", "glm-4-flash"), ("glm-4", "glm-4")],
        "kimi": [
            ("moonshot-v1-8k", "moonshot-v1-8k"),
            ("moonshot-v1-32k", "moonshot-v1-32k"),
        ],
        "openai": [("gpt-4o-mini", "gpt-4o-mini"), ("gpt-4o", "gpt-4o")],
        "anthropic": [
            ("claude-sonnet-4-6", "claude-sonnet-4-6"),
            ("claude-opus-4-6", "claude-opus-4-6"),
            ("claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001"),
        ],
        "ollama": [
            ("qwen3.5:27b (27B, empfohlen)", "qwen3.5:27b"),
            ("qwen3.5:35b (35B, langsam)", "qwen3.5:35b"),
            ("qwen3-vl:8b (8B, schnell)", "qwen3-vl:8b"),
            ("qwen2.5-coder:32b", "qwen2.5-coder:32b"),
        ],
    }

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        defaults = self.config.get("defaults", {})
        api_cfg = self.config.get("api", {})
        current_provider = api_cfg.get("provider", "glm")
        current_model = api_cfg.get("model", "glm-4-flash")
        current_fach = defaults.get("fach", "Deutsch")
        current_schulstufe = defaults.get("schulstufe", "Oberstufe")

        provider_values = [v for _, v in self._PROVIDERS]
        if current_provider not in provider_values:
            current_provider = provider_values[0]

        model_opts = self._MODELS_BY_PROVIDER.get(current_provider, [("", "")])
        model_values = [v for _, v in model_opts]
        if current_model not in model_values:
            current_model = model_values[0] if model_values else ""

        # Key-Status für aktuellen Provider ermitteln
        key_env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "glm": "GLM_API_KEY",
            "kimi": "KIMI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "ollama": None,
        }
        env_key_name = key_env_map.get(current_provider)
        api_key_val = os.environ.get(env_key_name, "") if env_key_name else "n/a (lokal)"
        if env_key_name is None:
            key_display = "kein Key nötig"
            has_key = "✓"
        elif len(api_key_val) > 12:
            key_display = f"{api_key_val[:6]}...{api_key_val[-3:]}"
            has_key = "✓"
        else:
            key_display = "(nicht gesetzt)"
            has_key = "✗"

        with VerticalScroll(classes="settings-container"):
            yield Label("EINSTELLUNGEN", classes="panel-title")

            with Container(classes="settings-section"):
                yield Label("Pfade", classes="settings-section-title")
                yield Static(f"  Input:   {nc.resolve_path(self.config, 'input')}")
                yield Static(f"  Output:  {nc.resolve_path(self.config, 'output')}")
                yield Static(f"  Rubrics: {nc.resolve_path(self.config, 'rubrics')}")

            with Container(classes="settings-section"):
                yield Label("API-Provider", classes="settings-section-title")
                yield Static(f"  Key:  {has_key} {key_display}")
                yield Label("  Provider:")
                yield Select(
                    options=self._PROVIDERS,
                    value=current_provider,
                    id="settings-provider",
                )
                yield Label("  Modell:")
                yield Select(
                    options=model_opts,
                    value=current_model,
                    id="settings-model",
                )

            with Container(classes="settings-section"):
                yield Label("CLI-Agents", classes="settings-section-title")
                availability = nc.check_agent_availability(self.config)
                for name, avail in availability.items():
                    sym = "✓" if avail else "✗"
                    yield Static(f"  {sym}  {name}")

            with Container(classes="settings-section"):
                yield Label("Standardwerte (aenderbar)", classes="settings-section-title")
                yield Label("  Standard-Fach:")
                yield Select(
                    options=[("Deutsch", "Deutsch"), ("Englisch", "Englisch")],
                    value=current_fach,
                    id="settings-fach",
                )
                yield Label("  Standard-Schulstufe:")
                yield Select(
                    options=[("Oberstufe", "Oberstufe"), ("Unterstufe", "Unterstufe")],
                    value=current_schulstufe,
                    id="settings-schulstufe",
                )

            with Horizontal():
                yield Button("Speichern", variant="success", id="save-settings-btn")
                yield Button("Abbrechen", variant="error", id="close-settings-btn")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Wenn Provider geändert wird, Model-Optionen aktualisieren."""
        if event.select.id == "settings-provider" and event.value is not Select.BLANK:
            new_provider = str(event.value)
            model_opts = self._MODELS_BY_PROVIDER.get(new_provider, [("", "")])
            model_sel = self.query_one("#settings-model", Select)
            model_sel.set_options(model_opts)
            # Gespeichertes Modell wiederherstellen falls es zu diesem Provider passt
            saved_model = self.config.get("api", {}).get("model", "")
            model_values = [v for _, v in model_opts]
            if saved_model in model_values:
                model_sel.value = saved_model

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings-btn":
            self._save_settings()
        elif event.button.id == "close-settings-btn":
            self.dismiss(None)

    @staticmethod
    def _sel_value(sel: Select, fallback: str) -> str:
        """Liest den String-Wert eines Select — gibt fallback zurück wenn BLANK oder None."""
        v = sel.value
        if v is Select.BLANK or v is None:
            return fallback
        s = str(v)
        # Textual-interne Sentinel-Strings abfangen
        if s.startswith("_") or "NoSelection" in s or "NULL" in s or "BLANK" in s:
            return fallback
        return s

    def _save_settings(self) -> None:
        provider_sel = self.query_one("#settings-provider", Select)
        model_sel = self.query_one("#settings-model", Select)
        fach_sel = self.query_one("#settings-fach", Select)
        stufe_sel = self.query_one("#settings-schulstufe", Select)

        current_api = self.config.get("api", {})
        new_provider = self._sel_value(provider_sel, current_api.get("provider", "ollama"))
        # Modell-Fallback: erstes Modell des gewählten Providers
        default_model = self._MODELS_BY_PROVIDER.get(new_provider, [("", "gpt-4o-mini")])[0][1]
        new_model = self._sel_value(model_sel, current_api.get("model", default_model))
        new_fach = self._sel_value(fach_sel, "Deutsch")
        new_stufe = self._sel_value(stufe_sel, "Oberstufe")

        try:
            nc.save_settings(new_fach, new_stufe, new_provider, new_model)
            # Update in-memory config so changes take effect immediately
            self.config.setdefault("defaults", {})["fach"] = new_fach
            self.config.setdefault("defaults", {})["schulstufe"] = new_stufe
            self.config.setdefault("api", {})["provider"] = new_provider
            self.config.setdefault("api", {})["model"] = new_model
            self.app.notify("Einstellungen gespeichert – ab sofort aktiv.")
            self.dismiss(None)
        except Exception as e:
            self.app.notify(f"Fehler beim Speichern: {e}", severity="error")


class ReviewScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "dismiss", "Abbrechen"),
        ("e", "edit_json", "JSON editieren"),
        ("d", "generate_docx", "DOCX"),
        ("p", "generate_pdf", "PDF"),
    ]

    def __init__(self, file_info: FileInfo, config: dict[str, Any]) -> None:
        super().__init__()
        self.file_info = file_info
        self.config = config

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="review-container"):
            fname = self.file_info.path.name
            yield Label(f"Review: {fname}", classes="panel-title")

            if not self.file_info.analysis:
                yield Static("Keine Analysedaten vorhanden.")
                return

            data = self.file_info.analysis
            note_data = data.get("notenempfehlung", {})
            note = note_data.get("note", "?")
            bez = note_data.get("bezeichnung", "?")
            schnitt = note_data.get("durchschnitt", "?")

            yield Static(
                _note_rich_text(note, f"Note: {note} – {bez}    Durchschnitt: {schnitt}"),
                classes="review-note",
            )

            bewertung = data.get("bewertung", {})
            for key, crit in bewertung.items():
                if not isinstance(crit, dict):
                    continue
                punkte = crit.get("punkte", 0)
                max_pts = 5
                filled = int(punkte) if isinstance(punkte, (int, float)) else 0
                bar = "●" * filled + "○" * (max_pts - filled)

                with Container(classes="criterion-box"):
                    yield Label(
                        f"{key.replace('_', ' ').title()} – {punkte} Punkte ({bar})",
                        classes="criterion-header",
                    )
                    with Vertical(classes="criterion-body"):
                        yield Static(f"Stufe: {crit.get('stufe', '?')}")

                        staerken = crit.get("staerken", [])
                        if staerken:
                            lines = "\n".join(f"  + {s}" for s in staerken)
                            yield Static(f"Staerken:\n{lines}", classes="strength")

                        schwaechen = crit.get("schwaechen", [])
                        if schwaechen:
                            lines = "\n".join(f"  - {s}" for s in schwaechen)
                            yield Static(f"Schwaechen:\n{lines}", classes="weakness")

                        vorschlaege = crit.get("vorschlaege", [])
                        if vorschlaege:
                            lines = "\n".join(f"  > {s}" for s in vorschlaege)
                            yield Static(f"Vorschlaege:\n{lines}", classes="suggestion")

            with Horizontal(classes="stats-buttons"):
                yield Button("📄 DOCX erstellen", id="review-docx", variant="primary")
                yield Button("📄 Als PDF", id="review-pdf", variant="default")
                yield Button("Abbrechen", id="review-close", variant="error")

    def action_edit_json(self) -> None:
        if not self.file_info.analysis:
            return
        paths = nc.build_project_paths(self.config)
        paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = paths.feedback_data_dir / (self.file_info.path.stem + "_edit.json")
        tmp_path.write_text(
            json.dumps(self.file_info.analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        editor = os.environ.get("EDITOR", "nano")
        self.app.suspend()
        subprocess.run([editor, str(tmp_path)])
        try:
            edited = json.loads(tmp_path.read_text(encoding="utf-8"))
            self.file_info.analysis = edited
            self._save_analysis()
        except json.JSONDecodeError:
            pass

    def action_generate_docx(self) -> None:
        if not self.file_info.analysis:
            return
        self._generate_single_docx()

    def action_generate_pdf(self) -> None:
        if not self.file_info.analysis:
            return
        self._generate_single_pdf()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "review-docx":
            self.action_generate_docx()
        elif event.button.id == "review-pdf":
            self.action_generate_pdf()
        elif event.button.id == "review-close":
            self.dismiss(None)

    def _save_analysis(self) -> None:
        if not self.file_info.analysis:
            return
        paths = nc.build_project_paths(self.config)
        paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
        out_name = self.file_info.path.stem + "_analysis.json"
        (paths.feedback_data_dir / out_name).write_text(
            json.dumps(self.file_info.analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _generate_single_docx(self) -> None:
        if not self.file_info.analysis:
            return
        paths = nc.build_project_paths(self.config)
        paths.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            feedback = gf.parse_feedback_data(self.file_info.analysis)
            out_name = gf.output_filename(feedback.datei)
            out_path = paths.output_dir / out_name
            doc = gf.build_feedback_document(feedback, config=self.config)
            doc.save(str(out_path))
            self.file_info.status = FileStatus.DONE
            self.app.notify(f"DOCX gespeichert: {out_path.name}", severity="information")
            nc.open_file(out_path)
        except Exception as e:
            nc.log_tui_error(paths, f"{self.file_info.path.name}: {e}")
            self.file_info.status = FileStatus.ERROR
            self.app.notify(f"Fehler beim DOCX-Erstellen: {e}", severity="error")

    def _generate_single_pdf(self) -> None:
        if not self.file_info.analysis:
            return
        paths = nc.build_project_paths(self.config)
        paths.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            feedback = gf.parse_feedback_data(self.file_info.analysis)
            out_name = gf.output_filename(feedback.datei)
            docx_path = paths.output_dir / out_name
            doc = gf.build_feedback_document(feedback, config=self.config)
            doc.save(str(docx_path))
            self.file_info.status = FileStatus.DONE

            pdf_path = nc.docx_to_pdf(docx_path)
            if pdf_path and pdf_path.exists():
                self.app.notify(f"PDF gespeichert: {pdf_path.name}", severity="information")
                nc.open_file(pdf_path)
            else:
                self.app.notify(
                    "PDF-Konvertierung nicht verfuegbar — LibreOffice installieren.",
                    severity="warning",
                )
                nc.open_file(docx_path)
        except Exception as e:
            nc.log_tui_error(paths, f"{self.file_info.path.name}: {e}")
            self.app.notify(f"Fehler beim PDF-Erstellen: {e}", severity="error")


class ProgressScreen(ModalScreen[None]):
    BINDINGS = [("escape", "cancel_analysis", "Abbrechen")]

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    def compose(self) -> ComposeResult:
        with Container(classes="progress-container"):
            yield Label("Analyse laeuft...", classes="panel-title")
            yield Static("", id="progress-current")
            yield Static("", id="progress-queue")
            yield Static("", id="progress-bar")

    def update_progress(
        self,
        current_file: str,
        status_text: str,
        queue: list[str],
        done: int,
        total: int,
    ) -> None:
        self.query_one("#progress-current", Static).update(f"  {current_file}\n    {status_text}")
        if queue:
            q_text = "\n".join(f"  ⏳ {f} (in Warteschlange)" for f in queue)
            self.query_one("#progress-queue", Static).update(q_text)
        else:
            self.query_one("#progress-queue", Static).update("")

        pct = int((done / total) * 100) if total > 0 else 0
        filled = int(pct / 5)
        bar = "█" * filled + "░" * (20 - filled)
        self.query_one("#progress-bar", Static).update(
            f"\n  Fortschritt: {done}/{total}\n  {bar}  {pct}%\n\n  [Esc] Abbrechen"
        )

    def action_cancel_analysis(self) -> None:
        self._cancelled = True
        # Signal the worker thread via the app-level event
        try:
            self.app._cancel_event.set()
        except AttributeError:
            pass
        self.dismiss(None)


class EditAssignmentScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    _TEXTSORTEN_DEUTSCH = [
        "Erörterung",
        "Kommentar",
        "Leserbrief",
        "Textanalyse",
        "Textinterpretation",
        "Zusammenfassung",
        "Offener Brief",
        "Meinungsrede",
        "Empfehlung/Rezension",
    ]
    _TEXTSORTEN_ENGLISCH = [
        "Article",
        "Report",
        "Essay",
        "Email/Letter",
        "Review",
        "Blog Post",
        "Story",
    ]

    def __init__(self, file_info: FileInfo, config: dict[str, Any]) -> None:
        super().__init__()
        self.file_info = file_info
        self.config = config
        self._current_fach = file_info.fach or "Deutsch"
        self._current_schulstufe = file_info.schulstufe or "Oberstufe"

    def _textsorte_options(self, fach: str) -> list[tuple[str, str]]:
        lst = self._TEXTSORTEN_ENGLISCH if fach == "Englisch" else self._TEXTSORTEN_DEUTSCH
        return [(t, t) for t in lst]

    def _rubric_options(self) -> list[tuple[str, str]]:
        opts = nc.rubric_options_for(self._current_fach, self._current_schulstufe, self.config)
        return [(o, o) for o in opts] if opts else [("(keine Rubrik gefunden)", "")]

    def compose(self) -> ComposeResult:
        ts_opts = self._textsorte_options(self._current_fach)
        ts_values = [v for _, v in ts_opts]
        current_ts = (
            self.file_info.textsorte
            if self.file_info.textsorte in ts_values
            else (ts_values[0] if ts_values else "")
        )

        rubric_opts = self._rubric_options()
        rubric_values = [v for _, v in rubric_opts]
        current_rubric = (
            self.file_info.rubric
            if self.file_info.rubric in rubric_values
            else (rubric_values[0] if rubric_values else "")
        )

        with Container(classes="settings-container"):
            yield Label(f"Zuordnung: {self.file_info.path.name}", classes="panel-title")
            yield Label("Fach:")
            yield Select(
                options=[("Deutsch", "Deutsch"), ("Englisch", "Englisch")],
                value=self._current_fach,
                id="edit-fach",
            )
            yield Label("Schulstufe:")
            yield Select(
                options=[("Oberstufe", "Oberstufe"), ("Unterstufe", "Unterstufe")],
                value=self._current_schulstufe,
                id="edit-schulstufe",
            )
            yield Label("Textsorte:")
            yield Select(
                options=ts_opts,
                value=current_ts,
                id="edit-textsorte",
            )
            yield Label("Rubrik:")
            yield Select(
                options=rubric_opts,
                value=current_rubric,
                id="edit-rubric",
            )
            yield Label("Schüler/in (optional):")
            yield Input(
                value=self.file_info.schueler,
                placeholder="Name, optional",
                id="edit-schueler",
            )
            with Horizontal():
                yield Button("Speichern", variant="success", id="edit-save")
                yield Button("Abbrechen", variant="error", id="edit-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Kaskadiert Textsorte- und Rubrik-Optionen wenn Fach oder Schulstufe geaendert wird."""
        if event.select.id == "edit-fach" and event.value is not Select.BLANK:
            self._current_fach = str(event.value)
            # Textsorte-Optionen aktualisieren
            new_ts_opts = self._textsorte_options(self._current_fach)
            ts_select = self.query_one("#edit-textsorte", Select)
            ts_select.set_options(new_ts_opts)
            # Rubrik aktualisieren
            self._update_rubric_select()

        elif event.select.id == "edit-schulstufe" and event.value is not Select.BLANK:
            self._current_schulstufe = str(event.value)
            self._update_rubric_select()

    def _update_rubric_select(self) -> None:
        new_rubric_opts = self._rubric_options()
        rubric_select = self.query_one("#edit-rubric", Select)
        rubric_select.set_options(new_rubric_opts)
        # Standard-Rubrik automatisch vorauswählen
        default = nc.default_rubric_for(self._current_fach, self._current_schulstufe, self.config)
        rubric_values = [v for _, v in new_rubric_opts]
        if default in rubric_values:
            rubric_select.value = default
        elif rubric_values:
            rubric_select.value = rubric_values[0]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edit-save":
            fach_sel = self.query_one("#edit-fach", Select)
            stufe_sel = self.query_one("#edit-schulstufe", Select)
            ts_sel = self.query_one("#edit-textsorte", Select)
            rubric_sel = self.query_one("#edit-rubric", Select)
            schueler_input = self.query_one("#edit-schueler", Input)

            if fach_sel.value is not Select.BLANK:
                self.file_info.fach = str(fach_sel.value)
            if stufe_sel.value is not Select.BLANK:
                self.file_info.schulstufe = str(stufe_sel.value)
            if ts_sel.value is not Select.BLANK:
                self.file_info.textsorte = str(ts_sel.value)
            if rubric_sel.value is not Select.BLANK:
                self.file_info.rubric = str(rubric_sel.value)
            self.file_info.schueler = schueler_input.value.strip()
            self.dismiss(True)
        else:
            self.dismiss(False)


class SagaHeader(Widget):
    """Enhanced header with gradient logo, acronym tagline, and animated status."""

    DEFAULT_CSS = """
    SagaHeader {
        dock: top;
        height: 10;
        background: #050810;
        padding: 1 2 0 2;
    }
    SagaHeader #logo-container {
        width: 70%;
        align: left top;
    }
    SagaHeader #status-container {
        width: 30%;
        align: right top;
        padding: 1 2;
    }
    SagaHeader #acronym {
        margin-top: 0;
    }
    """

    _pulse_state = reactive(0)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._terminal_width = 120
        self._api_status = "?"
        self._n_files = 0
        self._version = "0.7.0"

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="logo-container"):
                yield Static(render_logo_gradient(self._terminal_width), id="logo")
                yield Static(render_acronym(), id="acronym")
            with Vertical(id="status-container"):
                yield Static(self._render_status(), id="status")

    def on_mount(self) -> None:
        """Start pulse animation for offline API indicator."""
        self.set_interval(0.8, self._pulse)

    def _pulse(self) -> None:
        """Toggle pulse state for animated status indicator."""
        self._pulse_state = (self._pulse_state + 1) % 2
        try:
            self.query_one("#status", Static).update(self._render_status())
        except Exception:
            pass

    def on_resize(self) -> None:
        """Handle terminal resize for responsive logo."""
        if self.app.size:
            old_width = self._terminal_width
            self._terminal_width = self.app.size.width
            # Only re-render if logo type would change
            if (old_width >= 100) != (self._terminal_width >= 100):
                try:
                    self.query_one("#logo", Static).update(
                        render_logo_gradient(self._terminal_width)
                    )
                except Exception:
                    pass

    def update_status(self, api_status: str, n_files: int, version: str) -> None:
        """Update header status information."""
        self._api_status = api_status
        self._n_files = n_files
        self._version = version
        try:
            self.query_one("#status", Static).update(self._render_status())
        except Exception:
            pass

    def _render_status(self) -> Text:
        """Render status text with animated offline indicator."""
        text = Text(justify="right")

        api_available = getattr(self.app, "api_available", False)
        api_status_str = getattr(self, "_api_status", "?")
        n_files = getattr(self, "_n_files", 0)
        version = getattr(self, "_version", "0.4.0")

        if api_status_str == "✓":
            text.append("● API verbunden\n", style="bold #00ffaa")
        else:
            color = "#ff4466" if self._pulse_state else "#882233"
            text.append("● API offline\n", style=f"bold {color}")

        text.append(f"{n_files} Dateien\n", style="dim")
        text.append(f"v{version}", style="dim italic")
        return text


# Note-Beschriftungen für Statistiken
_NOTE_LABELS = {1: "Sehr gut", 2: "Gut", 3: "Befriedigend", 4: "Genügend", 5: "Nicht gen."}
_BAR_WIDTH = 20  # Breite des ASCII-Balkens


class StatisticsScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    def __init__(self, files: list, config: dict[str, Any] | None = None) -> None:
        super().__init__()
        analyses = [fi.analysis for fi in files if fi.analysis is not None]
        self._stats = nc.compute_statistics(analyses)
        self._total_files = len(files)
        self._config = config or {}
        self._view_mode = "stats"

        klasse = nc.active_klasse(self._config)
        if klasse:
            try:
                self._progress = nc.compute_class_progress(self._config, klasse)
            except Exception:
                self._progress = []
        else:
            self._progress = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="stats-container"):
            yield Label("Klassen-Statistiken", classes="panel-title")
            yield Static(self._build_content(), id="stats-body")
            with Horizontal(classes="stats-buttons"):
                yield Button("📊 Als DOCX", variant="default", id="stats-docx")
                yield Button("📈 Fortschritt", variant="default", id="stats-progress")
                yield Button("Abbrechen", variant="error", id="stats-close")

    def _build_content(self) -> Text:
        s = self._stats
        total = s["total"]
        text = Text()

        # ── Übersicht ──────────────────────────────────────────────────
        text.append(f"Ausgewertet: {total} von {self._total_files} Dateien\n", style="bold")
        if total == 0:
            text.append("\nNoch keine Analysen vorhanden.", style="dim")
            return text
        text.append(f"Gesamtdurchschnitt: ", style="bold")
        avg = s["grade_average"]
        avg_note = round(avg)
        avg_color = _NOTE_COLORS.get(avg_note, "#ffffff")
        text.append(f"{avg:.2f}\n\n", style=f"bold {avg_color}")

        # ── Notenverteilung ───────────────────────────────────────────
        text.append("Notenverteilung\n", style="bold underline")
        dist = s["grade_distribution"]
        max_count = max(dist.values()) if dist else 1
        for note in range(1, 6):
            count = dist.get(note, 0)
            pct = (count / total * 100) if total > 0 else 0
            filled = round(count / max_count * _BAR_WIDTH) if max_count > 0 else 0
            bar = "█" * filled + "░" * (_BAR_WIDTH - filled)
            color = _NOTE_COLORS.get(note, "#ffffff")
            label = _NOTE_LABELS[note]
            text.append(f"  {note} {label:<12s} ", style="default")
            text.append(bar, style=color)
            text.append(f"  {count:2d}  ({pct:4.1f}%)\n", style="default")

        # ── Kriterien-Durchschnitte ────────────────────────────────────
        crit_avgs = s["criteria_averages"]
        if crit_avgs:
            text.append("\nKriterien\n", style="bold underline")
            weakest = s["weakest_criterion"]
            strongest = s["strongest_criterion"]
            for key, vals in sorted(crit_avgs.items(), key=lambda x: x[1]["avg"]):
                label = key.replace("_", " ").title()
                avg_c = vals["avg"]
                bar_filled = round(avg_c / 5 * _BAR_WIDTH)
                bar_c = "█" * bar_filled + "░" * (_BAR_WIDTH - bar_filled)
                if key == weakest:
                    style = f"bold {_NOTE_COLORS[5]}"
                    marker = " ◀ schwächstes"
                elif key == strongest:
                    style = f"bold {_NOTE_COLORS[1]}"
                    marker = " ◀ stärkstes"
                else:
                    style = "default"
                    marker = ""
                text.append(f"  {label:<22s} ", style=style)
                text.append(bar_c, style=style)
                text.append(f"  Ø {avg_c:.2f}  (n={vals['count']}){marker}\n", style=style)

        return text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stats-close":
            self.dismiss(None)
        elif event.button.id == "stats-docx":
            self._save_stats_docx()
        elif event.button.id == "stats-progress":
            self._toggle_progress_view()

    def _toggle_progress_view(self) -> None:
        if self._view_mode == "stats":
            self._view_mode = "progress"
        else:
            self._view_mode = "stats"
        body = self.query_one("#stats-body", Static)
        if self._view_mode == "progress":
            body.update(self._build_progress_content())
        else:
            body.update(self._build_content())

    def _build_progress_content(self) -> Text:
        text = Text()
        progress = self._progress

        if not progress or len(progress) < 1:
            text.append("Lernfortschritt\n\n", style="bold underline")
            text.append(
                "Keine Aufgaben mit Analysen vorhanden.\n"
                "Es werden mindestens 1 Aufgabe mit abgeschlossenen Analysen benoetigt.",
                style="dim",
            )
            return text

        text.append("Lernfortschritt\n\n", style="bold underline")

        labels = [p["label"] for p in progress]
        short_labels = []
        for lbl in labels:
            parts = lbl.split("–")
            short = parts[-1].strip() if len(parts) > 1 else lbl
            short_labels.append(short[:10])

        notes = [p["avg_note"] for p in progress]

        chart_width = max(len(short_labels), 1)
        note_range = list(range(5, 0, -1))

        for note_val in note_range:
            text.append(f"  {note_val} │", style="default")
            for avg in notes:
                rounded = round(avg)
                if rounded == note_val:
                    text.append("  ●", style=f"bold {_NOTE_COLORS.get(rounded, '#ffffff')}")
                else:
                    text.append("   ", style="default")
            text.append("\n", style="default")

        text.append("    └", style="default")
        for _ in short_labels:
            text.append("───", style="default")
        text.append("─\n", style="default")

        text.append("     ", style="default")
        for sl in short_labels:
            text.append(f"{sl:^10s}", style="dim")
        text.append("\n\n", style="default")

        for i, p in enumerate(progress):
            n_color = _NOTE_COLORS.get(round(p["avg_note"]), "#ffffff")
            text.append(f"  {p['label']:<30s}", style="default")
            text.append(f"Ø {p['avg_note']:.2f}", style=f"bold {n_color}")
            text.append(f"  (n={p['n']})\n", style="dim")

        if len(progress) >= 2:
            text.append("\nKriterien-Vergleich\n", style="bold underline")
            all_keys: set[str] = set()
            for p in progress:
                all_keys.update(p["avg_criteria"].keys())

            for key in sorted(all_keys):
                label = key.replace("_", " ").title()
                text.append(f"  {label:<22s}", style="default")
                for i, p in enumerate(progress):
                    val = p["avg_criteria"].get(key, 0.0)
                    trend = ""
                    if i > 0:
                        prev = progress[i - 1]["avg_criteria"].get(key)
                        if prev is not None:
                            if val > prev:
                                trend = "↑"
                            elif val < prev:
                                trend = "↓"
                            else:
                                trend = "="
                    text.append(f" {val:.1f}{trend}", style="default")
                text.append("\n", style="default")

        return text

    def _save_stats_docx(self) -> None:
        try:
            paths = nc.build_project_paths(self._config)
            paths.output_dir.mkdir(parents=True, exist_ok=True)
            klasse_name = nc.active_klasse(self._config) or ""
            doc = gf.build_statistics_document(
                self._stats, config=self._config, klasse_name=klasse_name
            )
            today = time.strftime("%Y-%m-%d")
            out_name = f"klassenreport_{today}.docx"
            if klasse_name:
                out_name = f"klassenreport_{klasse_name}_{today}.docx"
            out_path = paths.output_dir / out_name
            doc.save(str(out_path))
            self.app.notify(f"Klassenreport gespeichert: {out_name}", severity="information")
            nc.open_file(out_path)
        except Exception as e:
            self.app.notify(f"Fehler: {e}", severity="error")


class RubrikEditorScreen(ModalScreen[bool]):
    """Modal zum Bearbeiten einer Rubrik-Datei (.md) aus rubrics/."""

    BINDINGS = [
        ("escape", "request_close", "Abbrechen"),
        ("ctrl+s", "save", "Speichern"),
    ]

    def __init__(self, rubric_filename: str, config: dict[str, Any]) -> None:
        super().__init__()
        self._rubric_filename = rubric_filename
        self._config = config
        self._original_text = ""
        self._dirty = False
        self._mode = "edit"

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="settings-container"):
            yield Label(f"Rubrik-Editor: {self._rubric_filename}", classes="panel-title")
            with Horizontal(classes="stats-buttons"):
                yield Button("Schreiben", id="re-tab-edit", variant="primary")
                yield Button("Vorschau", id="re-tab-preview", variant="default")
                yield Button("Speichern", id="re-save", variant="success")
                yield Button("📂 Extern öffnen", id="re-external", variant="default")
            yield TextArea(id="re-textarea")
            yield Markdown(id="re-preview", classes="review-container")
            with Horizontal(classes="stats-buttons"):
                yield Button("Abbrechen", id="re-close", variant="error")

    def on_mount(self) -> None:
        try:
            self._original_text = nc.load_rubric(self._rubric_filename, self._config)
        except FileNotFoundError:
            self._original_text = ""
        textarea = self.query_one("#re-textarea", TextArea)
        textarea.load_text(self._original_text)
        self._show_edit_tab()

    def _show_edit_tab(self) -> None:
        self._mode = "edit"
        self.query_one("#re-textarea", TextArea).display = True
        self.query_one("#re-preview", Markdown).display = False
        self.query_one("#re-tab-edit", Button).variant = "primary"
        self.query_one("#re-tab-preview", Button).variant = "default"

    def _show_preview_tab(self) -> None:
        self._mode = "preview"
        textarea = self.query_one("#re-textarea", TextArea)
        preview = self.query_one("#re-preview", Markdown)
        preview.update(textarea.text)
        textarea.display = False
        preview.display = True
        self.query_one("#re-tab-edit", Button).variant = "default"
        self.query_one("#re-tab-preview", Button).variant = "primary"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "re-tab-edit":
            self._show_edit_tab()
        elif btn_id == "re-tab-preview":
            self._show_preview_tab()
        elif btn_id == "re-save":
            self.action_save()
        elif btn_id == "re-close":
            self.action_request_close()
        elif btn_id == "re-external":
            self.action_open_external()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "re-textarea":
            self._dirty = event.text_area.text != self._original_text

    def action_save(self) -> None:
        textarea = self.query_one("#re-textarea", TextArea)
        rubric_dir = nc.resolve_path(self._config, "rubrics")
        target = rubric_dir / self._rubric_filename
        try:
            target.write_text(textarea.text, encoding="utf-8")
            self._original_text = textarea.text
            self._dirty = False
            self.app.notify(
                f"Rubrik gespeichert: {self._rubric_filename}",
                severity="information",
            )
        except Exception as e:
            self.app.notify(f"Fehler beim Speichern: {e}", severity="error")

    def action_open_external(self) -> None:
        rubric_dir = nc.resolve_path(self._config, "rubrics")
        target = rubric_dir / self._rubric_filename
        if not target.exists():
            self.app.notify(f"Datei nicht gefunden: {target}", severity="error")
            return
        nc.open_file(target)
        self.app.notify(f"Geöffnet: {self._rubric_filename}", severity="information")

    def action_request_close(self) -> None:
        if self._dirty:

            def _handle(result: bool) -> None:
                if result:
                    self.dismiss(False)

            self.app.push_screen(
                ConfirmScreen("Ungespeicherte Aenderungen verwerfen?"),
                _handle,
            )
        else:
            self.dismiss(False)


class AddAufgabeScreen(ModalScreen[bool]):
    """Modal zum Anlegen einer neuen Aufgabe (Schularbeit) für eine Klasse."""

    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    _TEXTSORTEN_DEUTSCH = [
        "Erörterung",
        "Kommentar",
        "Leserbrief",
        "Textanalyse",
        "Textinterpretation",
        "Zusammenfassung",
        "Offener Brief",
        "Meinungsrede",
        "Empfehlung/Rezension",
    ]
    _TEXTSORTEN_ENGLISCH = [
        "Article",
        "Report",
        "Essay",
        "Email/Letter",
        "Review",
        "Blog Post",
    ]

    def __init__(self, klasse: str, existing_slugs: list[str], config: dict[str, Any]) -> None:
        super().__init__()
        self._klasse = klasse
        self._existing = existing_slugs
        self._config = config
        self._current_fach = "Deutsch"
        self._current_schulstufe = "Oberstufe"

    def _textsorte_options(self, fach: str) -> list[tuple[str, str]]:
        lst = self._TEXTSORTEN_ENGLISCH if fach == "Englisch" else self._TEXTSORTEN_DEUTSCH
        return [(t, t) for t in lst]

    def _rubric_options(self) -> list[tuple[str, str]]:
        opts = nc.rubric_options_for(self._current_fach, self._current_schulstufe, self._config)
        return [(o, o) for o in opts] if opts else [("(keine Rubrik gefunden)", "")]

    def compose(self) -> ComposeResult:
        ts_opts = self._textsorte_options(self._current_fach)
        rubric_opts = self._rubric_options()
        with Container(classes="settings-container"):
            yield Label(f"Neue Aufgabe für Klasse {self._klasse}", classes="panel-title")
            yield Label("Bezeichnung (z.B. SA1 – Kommentar):")
            yield Input(placeholder="Label", id="auf-label")
            yield Label("Fach:")
            yield Select(
                options=[("Deutsch", "Deutsch"), ("Englisch", "Englisch")],
                value="Deutsch",
                id="auf-fach",
            )
            yield Label("Schulstufe:")
            yield Select(
                options=[("Oberstufe", "Oberstufe"), ("Unterstufe", "Unterstufe")],
                value="Oberstufe",
                id="auf-schulstufe",
            )
            yield Label("Textsorte:")
            yield Select(options=ts_opts, value=ts_opts[0][1], id="auf-textsorte")
            yield Label("Rubrik:")
            yield Select(options=rubric_opts, value=rubric_opts[0][1], id="auf-rubric")
            with Horizontal():
                yield Button("Anlegen", variant="success", id="auf-ok")
                yield Button("Abbrechen", variant="error", id="auf-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "auf-fach" and event.value is not Select.BLANK:
            self._current_fach = str(event.value)
            ts_opts = self._textsorte_options(self._current_fach)
            self.query_one("#auf-textsorte", Select).set_options(ts_opts)
            self._refresh_rubric()
        elif event.select.id == "auf-schulstufe" and event.value is not Select.BLANK:
            self._current_schulstufe = str(event.value)
            self._refresh_rubric()

    def _refresh_rubric(self) -> None:
        opts = self._rubric_options()
        rubric_sel = self.query_one("#auf-rubric", Select)
        rubric_sel.set_options(opts)
        default = nc.default_rubric_for(self._current_fach, self._current_schulstufe, self._config)
        values = [v for _, v in opts]
        rubric_sel.value = default if default in values else (values[0] if values else "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "auf-cancel":
            self.dismiss(False)
        elif event.button.id == "auf-ok":
            self._do_save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_save()

    def _do_save(self) -> None:
        label = self.query_one("#auf-label", Input).value.strip()
        if not label:
            self.app.notify("Bitte eine Bezeichnung eingeben.", severity="warning")
            return
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", label)
        if slug in self._existing:
            self.app.notify(f"Aufgabe '{slug}' existiert bereits.", severity="warning")
            return
        fach_sel = self.query_one("#auf-fach", Select)
        stufe_sel = self.query_one("#auf-schulstufe", Select)
        ts_sel = self.query_one("#auf-textsorte", Select)
        rubric_sel = self.query_one("#auf-rubric", Select)
        fach = str(fach_sel.value) if fach_sel.value is not Select.BLANK else "Deutsch"
        schulstufe = str(stufe_sel.value) if stufe_sel.value is not Select.BLANK else "Oberstufe"
        textsorte = str(ts_sel.value) if ts_sel.value is not Select.BLANK else ""
        rubric = str(rubric_sel.value) if rubric_sel.value is not Select.BLANK else ""
        try:
            nc.add_aufgabe_to_config(self._klasse, slug, label, fach, schulstufe, textsorte, rubric)
            self.dismiss(True)
        except Exception as e:
            self.app.notify(f"Fehler: {e}", severity="error")


class AddClassScreen(ModalScreen[bool]):
    """Modal zum Anlegen einer neuen Klasse."""

    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    def __init__(self, existing_names: list[str]) -> None:
        super().__init__()
        self._existing = existing_names

    def compose(self) -> ComposeResult:
        with Container(classes="confirm-container"):
            yield Label("Neue Klasse anlegen", classes="panel-title")
            yield Label("Name der Klasse (z.B. 7A, 8B):")
            yield Input(placeholder="Klassenname", id="new-class-name")
            with Horizontal():
                yield Button("Anlegen", variant="success", id="add-class-ok")
                yield Button("Abbrechen", variant="error", id="add-class-cancel")
        yield Static("", id="add-class-error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-class-cancel":
            self.dismiss(False)
            return
        if event.button.id == "add-class-ok":
            self._do_save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_save()

    def _do_save(self) -> None:
        name_input = self.query_one("#new-class-name", Input)
        name = name_input.value.strip()
        if not name:
            self.app.notify("Bitte einen Klassennamen eingeben.", severity="warning")
            return
        if name in self._existing:
            self.app.notify(f"Klasse '{name}' existiert bereits.", severity="warning")
            return
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", name).lower()
        input_rel = f"input/{slug}"
        output_rel = f"output/{slug}"
        try:
            nc.add_class_to_config(name, input_rel, output_rel)
            (nc.PROJECT_ROOT / input_rel).mkdir(parents=True, exist_ok=True)
            (nc.PROJECT_ROOT / output_rel).mkdir(parents=True, exist_ok=True)
            self.dismiss(True)
        except Exception as e:
            self.app.notify(f"Fehler: {e}", severity="error")


class AttachRubricScreen(ModalScreen[bool]):
    """Modal zum Anhängen einer Rubrik-Datei (.md) an eine Aufgabe."""

    BINDINGS = [("escape", "dismiss", "Abbrechen")]

    def __init__(
        self,
        klasse: str,
        aufgabe: str,
        aufgabe_label: str,
        config: dict[str, Any],
    ) -> None:
        super().__init__()
        self._klasse = klasse
        self._aufgabe = aufgabe
        self._aufgabe_label = aufgabe_label
        self._config = config

    def compose(self) -> ComposeResult:
        all_rubrics = nc.list_all_rubrics(self._config)
        rubric_opts: list[tuple[str, str]] = [(r, r) for r in all_rubrics]
        if not rubric_opts:
            rubric_opts = [("(keine Rubrik vorhanden)", "")]
        with Container(classes="settings-container"):
            yield Label(f"Rubrik für: {self._aufgabe_label}", classes="panel-title")
            yield Label("Pfad zur Rubrik-Datei (.md) – tippen oder einfügen:")
            yield Input(
                placeholder="/home/user/meine_rubrik.md",
                id="rubric-path-input",
            )
            yield Label("Oder vorhandene Rubrik aus rubrics/ wählen:")
            yield Select(
                options=rubric_opts,
                id="rubric-existing-select",
                prompt="Rubrik wählen…",
            )
            with Horizontal():
                yield Button("Speichern", variant="success", id="rubric-save")
                yield Button("Abbrechen", variant="error", id="rubric-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rubric-cancel":
            self.dismiss(False)
        elif event.button.id == "rubric-save":
            self._do_save()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._do_save()

    def _do_save(self) -> None:
        path_str = self.query_one("#rubric-path-input", Input).value.strip()
        existing_sel = self.query_one("#rubric-existing-select", Select)

        if path_str:
            source = Path(path_str)
            if not source.exists():
                self.app.notify(f"Datei nicht gefunden: {path_str}", severity="error")
                return
            if source.suffix.lower() != ".md":
                self.app.notify("Nur .md-Dateien erlaubt.", severity="warning")
                return
            try:
                dest_name = nc.attach_rubric_to_aufgabe(self._klasse, self._aufgabe, source)
                self.app.notify(f"Rubrik gespeichert: {dest_name}", severity="information")
                self.dismiss(True)
            except Exception as e:
                self.app.notify(f"Fehler: {e}", severity="error")
        elif existing_sel.value is not Select.BLANK and str(existing_sel.value):
            rubric_name = str(existing_sel.value)
            try:
                nc.set_rubric_for_aufgabe(self._klasse, self._aufgabe, rubric_name)
                self.app.notify(f"Rubrik gesetzt: {rubric_name}", severity="information")
                self.dismiss(True)
            except Exception as e:
                self.app.notify(f"Fehler: {e}", severity="error")
        else:
            self.app.notify("Bitte Pfad eingeben oder Rubrik wählen.", severity="warning")


class SagaApp(App):
    TITLE = "SAGA"
    CSS_PATH = "saga.tcss"

    BINDINGS = [
        Binding("q", "quit", "Beenden"),
        Binding("question_mark", "show_help", "Hilfe", key_display="?"),
        Binding("f1", "show_help", "Hilfe"),
        Binding("s", "show_settings", "Einstellungen"),
        Binding("slash", "toggle_search", "Suche", key_display="/"),
        Binding("tab", "next_panel", "Naechstes Panel"),
        Binding("a", "analyze_file", "Analyse"),
        Binding("shift+a", "analyze_marked", "Batch-Analyse"),
        Binding("r", "review_file", "Review"),
        Binding("d", "generate_docx", "DOCX"),
        Binding("shift+d", "generate_docx_marked", "Batch-DOCX"),
        Binding("e", "edit_assignment", "Zuordnung"),
        Binding("o", "toggle_sort", "Sortierung"),
        Binding("t", "show_statistics", "Statistik"),
        Binding("1", "preview_tab('text')", "Text", show=False),
        Binding("2", "preview_tab('rating')", "Bewertung", show=False),
        Binding("3", "preview_tab('rubrik')", "Rubrik", show=False),
        Binding("4", "preview_tab('output')", "Output", show=False),
    ]

    selected_index: reactive[int] = reactive(0)
    preview_mode: reactive[str] = reactive("text")
    sort_mode: reactive[str] = reactive("name")
    search_active: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.config = nc.load_config()
        self.files: list[FileInfo] = []
        self._id_to_index: dict[str, int] = {}
        self._search_filter: str = ""
        self._filtered_indices: list[int] = []
        self._focus_panel: int = 0
        self._analysis_cancelled = False
        self._rebuilding_list: bool = False
        self._cancel_event = threading.Event()
        self._known_files: set[Path] = set()
        self._last_click_id: str = ""
        self._last_click_time: float = 0.0
        self._output_paths: dict[str, Path] = {}  # output-list item id → Path

    def compose(self) -> ComposeResult:
        yield SagaHeader(id="app-header")
        with Horizontal(id="main-container"):
            with Vertical(id="files-panel"):
                yield Label("DATEIEN", classes="panel-title")
                yield Select([], id="class-select", prompt="Klasse wählen…")
                yield Button("＋ Klasse", id="add-class-btn", classes="add-class-btn")
                yield Select([], id="aufgabe-select", prompt="Aufgabe wählen…")
                with Horizontal(id="action-row-aufgabe"):
                    yield Button("＋ Aufgabe", id="add-aufgabe-btn", classes="action-row-btn")
                    yield Button("📎 Rubrik", id="attach-rubric-btn", classes="action-row-btn")
                    yield Button("📂 Ordner", id="btn-open-folder", classes="action-row-btn")
                yield Input(placeholder="Suche...", id="search-input")
                yield ListView(id="file-list")
                yield Static("", id="file-counter")
            with Vertical(id="middle-panel"):
                yield Label("ZUORDNUNG", classes="panel-title")
                yield VerticalScroll(Static("", id="middle-content"), id="middle-scroll")
                with Vertical(id="action-bar"):
                    yield Button(
                        "▶  Analysieren", id="btn-analyze", variant="success", classes="action-btn"
                    )
                    yield Button(
                        "👁  Review öffnen", id="btn-review", variant="primary", classes="action-btn"
                    )
                    yield Button(
                        "📄  DOCX erstellen", id="btn-docx", variant="primary", classes="action-btn"
                    )
                    yield Button(
                        "✏  Zuordnung bearbeiten",
                        id="btn-edit",
                        variant="default",
                        classes="action-btn",
                    )
                    yield Button(
                        "🔄  Neu analysieren",
                        id="btn-reanalyze",
                        variant="warning",
                        classes="action-btn",
                    )
            with VerticalScroll(id="preview-panel"):
                yield Label("VORSCHAU", classes="panel-title")
                with Horizontal(id="preview-tabs"):
                    yield Button("1 Text", id="tab-text", classes="tab-btn tab-active")
                    yield Button("2 Bewertung", id="tab-rating", classes="tab-btn")
                    yield Button("3 Rubrik", id="tab-rubrik", classes="tab-btn")
                    yield Button("4 Output", id="tab-output", classes="tab-btn")
                yield Static("", id="preview-content")
                yield Button(
                    "✏️  Rubrik bearbeiten",
                    id="btn-edit-rubric",
                    variant="default",
                    classes="action-btn",
                )
                yield ListView(id="output-list")
        yield Footer()

    def on_mount(self) -> None:
        self._populate_class_select()
        self._populate_aufgabe_select()
        self._load_files()
        self._update_header()
        self._apply_defaults()
        self._update_all_panels()

        search_input = self.query_one("#search-input", Input)
        search_input.display = False

        output_list = self.query_one("#output-list", ListView)
        output_list.display = False

        if not nc.api_key_available(self.config):
            self._check_first_run()

        self._watch_input_dir()

    def _populate_class_select(self) -> None:
        """Befüllt das Klassen-Select-Widget aus der Config."""
        class_sel = self.query_one("#class-select", Select)
        names = nc.list_classes(self.config)
        if not names:
            class_sel.display = False
            self.query_one("#add-class-btn", Button).display = False
            return
        options = [(n, n) for n in names]
        class_sel.set_options(options)
        active = nc.active_klasse(self.config)
        if active and active in names:
            class_sel.value = active

    def _populate_aufgabe_select(self) -> None:
        """Befüllt das Aufgaben-Select-Widget für die aktive Klasse."""
        aufgabe_sel = self.query_one("#aufgabe-select", Select)
        action_row = self.query_one("#action-row-aufgabe")
        rubric_btn = self.query_one("#attach-rubric-btn", Button)
        klasse = nc.active_klasse(self.config)
        if not klasse:
            aufgabe_sel.display = False
            action_row.display = False
            return
        slugs = nc.list_aufgaben(self.config, klasse)
        aufgabe_sel.display = True
        action_row.display = True
        rubric_btn.display = bool(slugs)
        if not slugs:
            aufgabe_sel.set_options([])
            return
        cls_cfg = self.config.get("classes", {}).get(klasse, {})
        options = [(cls_cfg.get("aufgaben", {}).get(s, {}).get("label", s), s) for s in slugs]
        aufgabe_sel.set_options(options)
        active = nc.active_aufgabe(self.config, klasse)
        if active and active in slugs:
            aufgabe_sel.value = active

    def _load_files(self) -> None:
        input_dir = nc.build_project_paths(self.config).input_dir
        if not input_dir.exists():
            return

        docx_files = sorted(input_dir.glob("*.docx"))
        self.files = []
        for p in docx_files:
            wc = nc.count_words(p)
            fi = FileInfo(path=p, word_count=wc)
            self._load_existing_analysis(fi)
            self.files.append(fi)

        self._known_files = {fi.path for fi in self.files}
        self._rebuild_id_map()
        self._apply_filter()

    def _load_existing_analysis(self, fi: FileInfo) -> None:
        paths = nc.build_project_paths(self.config)
        analysis_name = fi.path.stem + "_analysis.json"
        analysis_path = paths.feedback_data_dir / analysis_name
        if analysis_path.exists():
            try:
                data = json.loads(analysis_path.read_text(encoding="utf-8"))
                fi.analysis = data
                fi.fach = data.get("fach", fi.fach)
                fi.schulstufe = data.get("schulstufe", fi.schulstufe)
                fi.textsorte = data.get("textsorte", fi.textsorte)
                fi.rubrik = data.get("rubrik", fi.rubric)
                fi.schueler = data.get("schueler", fi.schueler)
                docx_name = gf.output_filename(data.get("datei", fi.path.name))
                if (paths.output_dir / docx_name).exists():
                    fi.status = FileStatus.DONE
                else:
                    fi.status = FileStatus.ANALYZED
            except (json.JSONDecodeError, Exception):
                fi.status = FileStatus.ERROR

    def _apply_defaults(self) -> None:
        klasse = nc.active_klasse(self.config)
        aufgabe = nc.active_aufgabe(self.config, klasse) if klasse else None
        auf_defs = nc.aufgabe_defaults(self.config, klasse, aufgabe)
        global_defs = self.config.get("defaults", {})
        for fi in self.files:
            if not fi.fach:
                fi.fach = auf_defs.get("fach") or global_defs.get("fach", "Deutsch")
            if not fi.schulstufe:
                fi.schulstufe = auf_defs.get("schulstufe") or global_defs.get(
                    "schulstufe", "Oberstufe"
                )
            if not fi.textsorte:
                fi.textsorte = auf_defs.get("textsorte") or "Kommentar"
            if not fi.rubric:
                fi.rubric = auf_defs.get("rubric") or nc.default_rubric_for(
                    fi.fach, fi.schulstufe, self.config
                )

    @work(thread=True)
    def _watch_input_dir(self) -> None:
        """Pollt alle 10 Sekunden den input/-Ordner auf neue .docx-Dateien."""
        while True:
            time.sleep(10)
            input_dir = nc.build_project_paths(self.config).input_dir
            if not input_dir.exists():
                continue
            try:
                current_paths = set(input_dir.glob("*.docx"))
                known_paths = {fi.path for fi in self.files}
                new_paths = sorted(current_paths - known_paths)
                if new_paths:
                    self.call_from_thread(self._on_new_files_detected, new_paths)
            except Exception:
                pass

    def _on_new_files_detected(self, new_paths: list[Path]) -> None:
        """Fügt neu erkannte Dateien zur Dateiliste hinzu (läuft im Main-Thread)."""
        klasse = nc.active_klasse(self.config)
        aufgabe = nc.active_aufgabe(self.config, klasse) if klasse else None
        auf_defs = nc.aufgabe_defaults(self.config, klasse, aufgabe)
        global_defs = self.config.get("defaults", {})
        added = 0
        for p in new_paths:
            if any(fi.path == p for fi in self.files):
                continue
            wc = nc.count_words(p)
            fi = FileInfo(path=p, word_count=wc)
            self._load_existing_analysis(fi)
            if not fi.fach:
                fi.fach = auf_defs.get("fach") or global_defs.get("fach", "Deutsch")
            if not fi.schulstufe:
                fi.schulstufe = auf_defs.get("schulstufe") or global_defs.get(
                    "schulstufe", "Oberstufe"
                )
            if not fi.textsorte:
                fi.textsorte = auf_defs.get("textsorte") or "Kommentar"
            if not fi.rubric:
                fi.rubric = auf_defs.get("rubric") or nc.default_rubric_for(
                    fi.fach, fi.schulstufe, self.config
                )
            self.files.append(fi)
            added += 1

        if added > 0:
            self._known_files = {fi.path for fi in self.files}
            self._rebuild_id_map()
            self._apply_filter()
            self._update_all_panels()
            self._update_header()
            self.notify(
                f"{added} neue Datei{'en' if added > 1 else ''} erkannt",
                severity="information",
            )

    def _rebuild_id_map(self) -> None:
        self._id_to_index = {}
        for i, fi in enumerate(self.files):
            sid = safe_id("fi", fi.path.name)
            self._id_to_index[sid] = i

    def _apply_filter(self) -> None:
        if self._search_filter:
            self._filtered_indices = [
                i
                for i, fi in enumerate(self.files)
                if self._search_filter.lower() in fi.path.name.lower()
            ]
        else:
            self._filtered_indices = list(range(len(self.files)))

        if self.sort_mode == "status":
            self._filtered_indices.sort(
                key=lambda i: (
                    0
                    if self.files[i].status == FileStatus.ERROR
                    else 1
                    if self.files[i].status == FileStatus.PENDING
                    else 2
                    if self.files[i].status == FileStatus.ANALYZED
                    else 3
                    if self.files[i].status == FileStatus.PROGRESS
                    else 4
                )
            )
        elif self.sort_mode == "words":
            self._filtered_indices.sort(key=lambda i: self.files[i].word_count)
        else:
            self._filtered_indices.sort(key=lambda i: self.files[i].path.name.lower())

        if self.selected_index >= len(self._filtered_indices):
            self.selected_index = max(0, len(self._filtered_indices) - 1)

    def _update_header(self) -> None:
        api_status = "✓" if nc.api_key_available(self.config) else "✗"
        self.query_one("#app-header", SagaHeader).update_status(
            api_status, len(self.files), nc.VERSION
        )

    def _update_all_panels(self) -> None:
        self._update_file_list()
        self._update_middle_panel()
        self._update_preview_panel()
        self._update_counter()

    def _update_file_list(self) -> None:
        list_view = self.query_one("#file-list", ListView)
        self._rebuilding_list = True

        wanted_ids = [safe_id("fi", self.files[i].path.name) for i in self._filtered_indices]

        # Vorhandene IDs ermitteln
        existing_ids = {item.id for item in list_view.query(ListItem)}

        # Überflüssige Items entfernen
        for item in list(list_view.query(ListItem)):
            if item.id not in wanted_ids:
                item.remove()

        # Items erstellen oder Label aktualisieren
        for pos, real_idx in enumerate(self._filtered_indices):
            fi = self.files[real_idx]
            sym, cls = STATUS_SYMBOLS[fi.status]
            mark = " ◉" if fi.marked else ""
            label_text = f" {sym} {fi.path.name}{mark}  ({fi.word_count} W)"
            item_id = safe_id("fi", fi.path.name)
            if item_id in existing_ids:
                # Nur Label aktualisieren — kein neues Widget mounten
                try:
                    existing = list_view.query_one(f"#{item_id}", ListItem)
                    existing.query_one(Static).update(Text(label_text))
                except Exception:
                    pass
            else:
                item = ListItem(Static(Text(label_text)), id=item_id)
                list_view.append(item)

        if self._filtered_indices:
            list_view.index = min(self.selected_index, len(self._filtered_indices) - 1)
        self._rebuilding_list = False

    def _update_counter(self) -> None:
        counter = self.query_one("#file-counter", Static)
        total = len(self.files)
        analyzed = sum(
            1 for fi in self.files if fi.status in (FileStatus.ANALYZED, FileStatus.DONE)
        )
        pending = total - analyzed
        text = f"{total} Dateien\n● {analyzed} analysiert\n○ {pending} offen"
        if self._search_filter:
            text += f"\n{len(self._filtered_indices)} / {total} angezeigt"
        counter.update(text)

    def _update_middle_panel(self) -> None:
        content = self.query_one("#middle-content", Static)
        if not self._filtered_indices:
            content.update("Keine Dateien gefunden.")
            return

        idx = (
            self._filtered_indices[self.selected_index]
            if self.selected_index < len(self._filtered_indices)
            else None
        )
        if idx is None:
            content.update("")
            return

        fi = self.files[idx]
        lines = [
            f"Datei:     {fi.path.name}",
            f"Woerter:   {fi.word_count}",
            f"Fach:      {fi.fach}",
            f"Schulstufe:{fi.schulstufe}",
            f"Textsorte: {fi.textsorte}",
            f"Rubrik:    {fi.rubric}",
        ]
        if fi.schueler:
            lines.append(f"Schüler/in:{fi.schueler}")

        text = Text("\n".join(lines))

        if fi.analysis:
            note_data = fi.analysis.get("notenempfehlung", {})
            note = note_data.get("note", "?")
            bez = note_data.get("bezeichnung", "?")
            schnitt = note_data.get("durchschnitt", "?")
            text.append("\n")
            text.append(
                f"\nNote: {note} – {bez}",
                style=f"bold {_NOTE_COLORS.get(int(note) if str(note).isdigit() else 0, '#ffffff')}",
            )
            text.append(f"\nDurchschnitt: {schnitt}")
            text.append("\n\nKriterien:")

            bewertung = fi.analysis.get("bewertung", {})
            for key, crit in bewertung.items():
                if isinstance(crit, dict):
                    punkte = crit.get("punkte", 0)
                    filled = int(punkte) if isinstance(punkte, (int, float)) else 0
                    bar = "●" * filled + "○" * (5 - filled)
                    text.append(f"\n  {key.replace('_', ' ').title():20s} {punkte}  {bar}")

        content.update(text)
        self._update_action_bar(fi)

    def _update_action_bar(self, fi: FileInfo) -> None:
        """Blendet Buttons je nach Dateistatus ein oder aus."""
        status = fi.status
        analyzed = status in (FileStatus.ANALYZED, FileStatus.DONE)
        pending = status == FileStatus.PENDING
        in_progress = status == FileStatus.PROGRESS
        error = status == FileStatus.ERROR

        self.query_one("#btn-analyze", Button).display = pending or error
        self.query_one("#btn-review", Button).display = analyzed
        self.query_one("#btn-docx", Button).display = analyzed
        self.query_one("#btn-edit", Button).display = True
        self.query_one("#btn-reanalyze", Button).display = analyzed
        # Während Analyse läuft: alle deaktivieren
        for btn_id in ("#btn-analyze", "#btn-review", "#btn-docx", "#btn-edit", "#btn-reanalyze"):
            self.query_one(btn_id, Button).disabled = in_progress

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Aktionsbuttons im Middle Panel → gleiche Aktionen wie Tastenkürzel."""
        btn_id = event.button.id
        if btn_id == "btn-analyze":
            self.action_analyze_file()
        elif btn_id == "btn-review":
            self.action_review_file()
        elif btn_id == "btn-docx":
            self.action_generate_docx()
        elif btn_id == "btn-edit":
            self.action_edit_assignment()
        elif btn_id == "btn-reanalyze":
            fi = self._get_selected_file()
            if fi:
                fi.status = FileStatus.PENDING
                fi.analysis = None
                self._update_all_panels()
        elif btn_id == "add-class-btn":
            self._action_add_class()
        elif btn_id == "add-aufgabe-btn":
            self._action_add_aufgabe()
        elif btn_id == "attach-rubric-btn":
            self._action_attach_rubric()
        elif btn_id == "btn-open-folder":
            paths = nc.build_project_paths(self.config)
            paths.input_dir.mkdir(parents=True, exist_ok=True)
            nc.open_file(paths.input_dir)
            self.notify(f"Ordner: {paths.input_dir.name}")
        elif btn_id in ("tab-text", "tab-rating", "tab-rubrik", "tab-output"):
            mode = btn_id.removeprefix("tab-")
            self.action_preview_tab(mode)
        elif btn_id == "btn-edit-rubric":
            self._action_edit_rubric()

    def _action_add_class(self) -> None:
        existing = nc.list_classes(self.config)

        def _after_add(result: bool) -> None:
            if result:
                self.config = nc.load_config()
                self._populate_class_select()
                self._populate_aufgabe_select()
                self._load_files()
                self._update_all_panels()
                new_active = nc.active_klasse(self.config)
                if new_active:
                    self.notify(f"Klasse '{new_active}' angelegt.", severity="information")

        self.push_screen(AddClassScreen(existing), _after_add)

    def _action_add_aufgabe(self) -> None:
        klasse = nc.active_klasse(self.config)
        if not klasse:
            self.notify("Erst eine Klasse wählen.", severity="warning")
            return
        existing_slugs = nc.list_aufgaben(self.config, klasse)

        def _after_add(result: bool) -> None:
            if result:
                self.config = nc.load_config()
                self._populate_aufgabe_select()
                self.files = []
                self._load_files()
                self._apply_defaults()
                self._update_all_panels()
                new_auf = nc.active_aufgabe(self.config, klasse)
                auf_cfg = nc.get_aufgabe_cfg(self.config, klasse, new_auf or "")
                label = auf_cfg.get("label", new_auf or "")
                if label:
                    self.notify(f"Aufgabe '{label}' angelegt.", severity="information")

        self.push_screen(AddAufgabeScreen(klasse, existing_slugs, self.config), _after_add)

    def _action_attach_rubric(self) -> None:
        klasse = nc.active_klasse(self.config)
        if not klasse:
            self.notify("Erst eine Klasse wählen.", severity="warning")
            return
        aufgabe = nc.active_aufgabe(self.config, klasse)
        if not aufgabe:
            self.notify("Erst eine Aufgabe wählen.", severity="warning")
            return
        auf_cfg = nc.get_aufgabe_cfg(self.config, klasse, aufgabe)
        label = auf_cfg.get("label", aufgabe)

        def _after(result: bool) -> None:
            if result:
                self.config = nc.load_config()
                self._update_preview_panel()

        self.push_screen(AttachRubricScreen(klasse, aufgabe, label, self.config), _after)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Klassen- oder Aufgaben-Wechsel: Dateiliste neu laden."""
        if event.select.id == "class-select" and event.value is not Select.BLANK:
            new_klasse = str(event.value)
            self.config.setdefault("classes", {})["active"] = new_klasse
            try:
                nc.save_active_klasse(new_klasse)
            except Exception:
                pass
            self._populate_aufgabe_select()
            self.files = []
            self._load_files()
            self._apply_defaults()
            self._update_all_panels()
            self.notify(f"Klasse: {new_klasse}")

        elif event.select.id == "aufgabe-select" and event.value is not Select.BLANK:
            new_aufgabe = str(event.value)
            klasse = nc.active_klasse(self.config)
            if klasse:
                self.config.setdefault("classes", {}).setdefault(klasse, {})["active_aufgabe"] = (
                    new_aufgabe
                )
                try:
                    nc.save_active_aufgabe(klasse, new_aufgabe)
                except Exception:
                    pass
            self.files = []
            self._load_files()
            self._apply_defaults()
            self._update_all_panels()
            auf_cfg = nc.get_aufgabe_cfg(self.config, klasse or "", new_aufgabe)
            label = auf_cfg.get("label", new_aufgabe)
            self.notify(f"Aufgabe: {label}")

    def _update_preview_panel(self) -> None:
        content = self.query_one("#preview-content", Static)
        output_list = self.query_one("#output-list", ListView)

        # Toggle content vs output-list visibility
        is_output_tab = self.preview_mode == "output"
        is_rubrik_tab = self.preview_mode == "rubrik"
        content.display = not is_output_tab
        output_list.display = is_output_tab

        edit_rubric_btn = self.query_one("#btn-edit-rubric", Button)
        edit_rubric_btn.display = is_rubrik_tab

        # Aktiven Tab-Button hervorheben
        tab_btn_ids = {
            "text": "tab-text",
            "rating": "tab-rating",
            "rubrik": "tab-rubrik",
            "output": "tab-output",
        }
        for mode, btn_id in tab_btn_ids.items():
            btn = self.query_one(f"#{btn_id}", Button)
            if mode == self.preview_mode:
                btn.add_class("tab-active")
            else:
                btn.remove_class("tab-active")

        if is_output_tab:
            self._populate_output_list(output_list)
            return

        if not self._filtered_indices:
            content.update("")
            return

        idx = (
            self._filtered_indices[self.selected_index]
            if self.selected_index < len(self._filtered_indices)
            else None
        )
        if idx is None:
            content.update("")
            return

        fi = self.files[idx]

        if self.preview_mode == "text":
            try:
                content.update(nc.read_docx_rich(fi.path))
            except Exception:
                content.update("(Datei konnte nicht gelesen werden)")
        elif self.preview_mode == "rubrik":
            try:
                klasse = nc.active_klasse(self.config)
                aufgabe = nc.active_aufgabe(self.config, klasse) if klasse else None
                rubric_content = nc.load_rubric_for_aufgabe(self.config, klasse, aufgabe)
                content.update(
                    rubric_content[:1200] + ("..." if len(rubric_content) > 1200 else "")
                )
            except Exception:
                content.update("(Rubrik konnte nicht geladen werden)")
        else:
            if fi.analysis:
                lines = []
                bewertung = fi.analysis.get("bewertung", {})
                for key, crit in bewertung.items():
                    if not isinstance(crit, dict):
                        continue
                    lines.append(f"── {key.replace('_', ' ').title()} ──")
                    for s in crit.get("staerken", []):
                        lines.append(f"  + {s}")
                    for s in crit.get("schwaechen", []):
                        lines.append(f"  - {s}")
                    lines.append("")
                content.update("\n".join(lines))
            else:
                content.update("(Keine Analyse vorhanden)")

    def _get_selected_file(self) -> FileInfo | None:
        if not self._filtered_indices or self.selected_index >= len(self._filtered_indices):
            return None
        return self.files[self._filtered_indices[self.selected_index]]

    def _populate_output_list(self, output_list: ListView) -> None:
        """Befüllt die Output-ListView mit DOCX-Dateien aus dem output/-Ordner.

        Verwendet In-Place-Update (kein clear()) um DuplicateIds zu vermeiden —
        dasselbe Muster wie _update_file_list. IDs sind Hash-basiert damit
        dieselbe Datei immer dieselbe ID bekommt und nie doppelt eingefügt wird.
        """
        output_dir = nc.build_project_paths(self.config).output_dir

        # Neue Items aufbauen: id → (path, anzeigetext)
        new_items: dict[str, tuple[Path, str]] = {}
        if output_dir.exists():
            for p in sorted(
                output_dir.glob("*.docx"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            ):
                try:
                    st = p.stat()
                    mtime = time.strftime("%d.%m.%y %H:%M", time.localtime(st.st_mtime))
                    size_kb = st.st_size // 1024
                    label_text = f"{mtime}  {p.name}  ({size_kb} KB)"
                    item_id = "out-" + hashlib.md5(p.name.encode()).hexdigest()[:8]
                    new_items[item_id] = (p, label_text)
                except OSError:
                    continue

        # _output_paths aktualisieren
        self._output_paths = {k: v[0] for k, v in new_items.items()}

        # Existierende IDs im ListView ermitteln
        existing_ids = {item.id for item in output_list.query(ListItem) if item.id}

        # Stale Items entfernen (ohne clear())
        for item in list(output_list.query(ListItem)):
            if item.id and item.id not in new_items and item.id != "out-empty":
                item.remove()

        if not new_items:
            if "out-empty" not in existing_ids:
                output_list.append(ListItem(Label("Noch keine DOCX erstellt."), id="out-empty"))
            return

        # Platzhalter entfernen falls vorhanden
        if "out-empty" in existing_ids:
            try:
                output_list.query_one("#out-empty", ListItem).remove()
            except Exception:
                pass

        # Nur wirklich neue Items anhängen (keine DuplicateIds möglich)
        for item_id, (_path, label_text) in new_items.items():
            if item_id not in existing_ids:
                output_list.append(ListItem(Label(label_text), id=item_id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        # Handle output-list selections
        if item.id and item.id in self._output_paths:
            p = self._output_paths[item.id]
            if p.exists():
                nc.open_file(p)
                self.notify(f"Öffne: {p.name}")
            return
        if not (item.id and item.id in self._id_to_index):
            return
        real_idx = self._id_to_index[item.id]
        if real_idx not in self._filtered_indices:
            return

        now = time.time()
        is_double_click = item.id == self._last_click_id and now - self._last_click_time < 0.5
        self._last_click_id = item.id
        self._last_click_time = now

        self.selected_index = self._filtered_indices.index(real_idx)
        self._update_middle_panel()
        self._update_preview_panel()

        if is_double_click:
            fi = self.files[real_idx]
            if fi.status in (FileStatus.ANALYZED, FileStatus.DONE):
                self.action_review_file()
            elif fi.status == FileStatus.PENDING:
                self.action_analyze_file()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if self._rebuilding_list or event.item is None:
            return
        if event.item.id and event.item.id in self._id_to_index:
            real_idx = self._id_to_index[event.item.id]
            if real_idx in self._filtered_indices:
                self.selected_index = self._filtered_indices.index(real_idx)
                self._update_middle_panel()
                self._update_preview_panel()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._search_filter = event.value
            self._apply_filter()
            self.selected_index = 0
            self._update_file_list()
            self._update_counter()

    def action_toggle_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        self.search_active = not self.search_active
        search_input.display = self.search_active
        if self.search_active:
            search_input.focus()
        else:
            self._search_filter = ""
            search_input.value = ""
            self._apply_filter()
            self._update_file_list()
            self._update_counter()

    def action_next_panel(self) -> None:
        panels = ["#files-panel", "#middle-panel", "#preview-panel"]
        for p in panels:
            try:
                self.query_one(p).remove_class("panel-focused")
            except Exception:
                pass
        self._focus_panel = (self._focus_panel + 1) % 3
        try:
            panel = self.query_one(panels[self._focus_panel])
            panel.add_class("panel-focused")
            panel.focus()
        except Exception:
            pass

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_show_settings(self) -> None:
        self.push_screen(SettingsScreen(self.config))

    def action_show_statistics(self) -> None:
        self.push_screen(StatisticsScreen(self.files, self.config))

    def action_toggle_sort(self) -> None:
        modes = ["name", "status", "words"]
        current = modes.index(self.sort_mode) if self.sort_mode in modes else 0
        self.sort_mode = modes[(current + 1) % len(modes)]
        self._apply_filter()
        self._update_file_list()
        self._update_counter()
        self.notify(f"Sortierung: {self.sort_mode}")

    def action_edit_assignment(self) -> None:
        fi = self._get_selected_file()
        if not fi:
            return

        def _on_assignment_saved(result: bool) -> None:
            if result:
                self._update_all_panels()
                saved_fi = self._get_selected_file()
                if saved_fi:
                    self.notify(f"Zuordnung gespeichert: {saved_fi.path.name}")

        self.push_screen(EditAssignmentScreen(fi, self.config), _on_assignment_saved)

    def action_review_file(self) -> None:
        fi = self._get_selected_file()
        if not fi or not fi.analysis:
            self.notify("Keine Analyse vorhanden.", severity="warning")
            return
        self.push_screen(ReviewScreen(fi, self.config))
        self._update_all_panels()

    def action_analyze_file(self) -> None:
        fi = self._get_selected_file()
        if not fi:
            return
        self._run_analysis([fi])

    def action_analyze_marked(self) -> None:
        marked = [fi for fi in self.files if fi.marked]
        if not marked:
            fi = self._get_selected_file()
            if fi:
                marked = [fi]
        if marked:
            self._run_analysis(marked)

    @work(thread=True)
    def _run_analysis(self, targets: list[FileInfo]) -> None:
        """Fuehrt die LLM-Analyse mit robuster Retry-Logik aus."""
        if not nc.api_key_available(self.config):
            provider = self.config.get("api", {}).get("provider", "anthropic")
            self.call_from_thread(
                self.notify,
                f"API-Key fuer Provider '{provider}' nicht gesetzt. .env pruefen.",
                severity="error",
            )
            return

        self._cancel_event.clear()
        progress_screen = ProgressScreen()
        self.call_from_thread(self.push_screen, progress_screen)

        total = len(targets)
        for i, fi in enumerate(targets):
            if self._cancel_event.is_set():
                break

            fi.status = FileStatus.PROGRESS
            self.call_from_thread(self._update_file_list)

            queue = [t.path.name for t in targets[i + 1 :]]
            self.call_from_thread(
                progress_screen.update_progress,
                fi.path.name,
                "Analyse laeuft...",
                queue,
                i,
                total,
            )

            try:
                docx_text = nc.read_docx_text(fi.path)
                rubric_content = nc.load_rubric(fi.rubric, self.config)
                data, errors = nc.run_llm_analysis(
                    docx_text,
                    rubric_content,
                    fi.fach,
                    fi.schulstufe,
                    fi.textsorte,
                    self.config,
                    schueler=fi.schueler,
                    cancel_event=self._cancel_event,
                )

                if errors:
                    # Fehler oder Abbruch
                    last_error = errors[-1]
                    if "abgebrochen" in last_error.lower():
                        fi.status = FileStatus.PENDING
                    else:
                        fi.status = FileStatus.ERROR
                        paths = nc.build_project_paths(self.config)
                        for err in errors:
                            nc.log_tui_error(paths, f"{fi.path.name}: {err}")
                elif data is not None:
                    fi.analysis = data
                    fi.status = FileStatus.ANALYZED
                    self._save_analysis(fi)
                else:
                    fi.status = FileStatus.ERROR

            except Exception as e:
                if self._cancel_event.is_set():
                    fi.status = FileStatus.PENDING
                else:
                    fi.status = FileStatus.ERROR
                    paths = nc.build_project_paths(self.config)
                    nc.log_tui_error(paths, f"{fi.path.name}: {e}")

            status_text = (
                "✓ Fertig"
                if fi.status == FileStatus.ANALYZED
                else "⏹ Abgebrochen"
                if fi.status == FileStatus.PENDING
                else "✗ Fehler"
            )
            self.call_from_thread(
                progress_screen.update_progress,
                fi.path.name,
                status_text,
                [],
                i + 1,
                total,
            )

        if progress_screen in self.screen_stack:
            self.call_from_thread(progress_screen.dismiss)

        self.call_from_thread(self._update_all_panels)
        done_count = sum(1 for f in targets if f.status == FileStatus.ANALYZED)
        self.call_from_thread(
            self.notify,
            f"Analyse abgeschlossen: {done_count}/{total} erfolgreich",
        )

    def _save_analysis(self, fi: FileInfo) -> None:
        if not fi.analysis:
            return
        paths = nc.build_project_paths(self.config)
        paths.feedback_data_dir.mkdir(parents=True, exist_ok=True)
        if fi.schueler:
            fi.analysis["schueler"] = fi.schueler
        out_name = fi.path.stem + "_analysis.json"
        (paths.feedback_data_dir / out_name).write_text(
            json.dumps(fi.analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def action_generate_docx(self) -> None:
        fi = self._get_selected_file()
        if not fi or not fi.analysis:
            self.notify("Keine Analyse vorhanden.", severity="warning")
            return
        self._generate_docx_files([fi])

    def action_generate_docx_marked(self) -> None:
        marked = [fi for fi in self.files if fi.marked]
        if not marked:
            fi = self._get_selected_file()
            if fi:
                marked = [fi]
        if marked:
            self._generate_docx_files(marked)

    def _generate_docx_files(self, targets: list[FileInfo]) -> None:
        paths = nc.build_project_paths(self.config)
        paths.output_dir.mkdir(parents=True, exist_ok=True)
        success = 0
        last_out_path = None
        for fi in targets:
            if not fi.analysis:
                continue
            try:
                feedback = gf.parse_feedback_data(fi.analysis)
                out_name = gf.output_filename(feedback.datei)
                out_path = paths.output_dir / out_name
                doc = gf.build_feedback_document(feedback, config=self.config)
                doc.save(str(out_path))
                fi.status = FileStatus.DONE
                success += 1
                last_out_path = out_path
            except Exception as e:
                fi.status = FileStatus.ERROR
                nc.log_tui_error(paths, f"{fi.path.name}: {e}")

        self._update_all_panels()
        self.notify(f"DOCX: {success}/{len(targets)} generiert")
        if success == 1 and last_out_path:
            nc.open_file(last_out_path)

    def action_quit(self) -> None:
        def _handle_confirm(result: bool) -> None:
            if result:
                self.exit()

        self.push_screen(ConfirmScreen("SAGA beenden?"), _handle_confirm)

    def _check_first_run(self) -> None:
        marker = nc.PROJECT_ROOT / ".saga_first_run_done"
        if marker.exists():
            return
        provider = self.config.get("api", {}).get("provider", "anthropic")
        self.notify(
            f"API-Key für Provider '{provider}' nicht gefunden. .env prüfen.",
            severity="warning",
        )
        try:
            marker.touch()
        except OSError:
            pass

    def key_space(self) -> None:
        if self.search_active:
            return
        fi = self._get_selected_file()
        if fi:
            fi.marked = not fi.marked
            self._update_file_list()
            self._update_counter()

    def key_enter(self) -> None:
        modes = ["text", "rating", "rubrik", "output"]
        cur = self.preview_mode if self.preview_mode in modes else "text"
        self.preview_mode = modes[(modes.index(cur) + 1) % len(modes)]
        self._update_preview_panel()

    def action_preview_tab(self, mode: str) -> None:
        self.preview_mode = mode
        self._update_preview_panel()
        names = {"text": "Text", "rating": "Bewertung", "rubrik": "Rubrik", "output": "Output"}
        self.notify(f"Vorschau: {names.get(mode, mode)}")

    def _action_edit_rubric(self) -> None:
        fi = self._get_selected_file()
        rubric_name = ""
        if fi and fi.rubric:
            rubric_name = fi.rubric
        else:
            klasse = nc.active_klasse(self.config)
            aufgabe = nc.active_aufgabe(self.config, klasse) if klasse else None
            auf_cfg = nc.get_aufgabe_cfg(self.config, klasse or "", aufgabe or "")
            rubric_name = auf_cfg.get("rubric", "")
        if not rubric_name:
            self.notify("Keine Rubrik zugeordnet.", severity="warning")
            return

        def _after_edit(result: bool) -> None:
            self._update_preview_panel()

        self.push_screen(RubrikEditorScreen(rubric_name, self.config), _after_edit)

    def key_delete(self) -> None:
        fi = self._get_selected_file()
        if not fi:
            return

        def _handle(result: bool) -> None:
            if result:
                self.files.remove(fi)
                self._rebuild_id_map()
                self._apply_filter()
                self._update_all_panels()

        self.push_screen(ConfirmScreen(f"{fi.path.name} entfernen?"), _handle)


def main() -> None:
    app = SagaApp()
    app.run()


if __name__ == "__main__":
    main()
