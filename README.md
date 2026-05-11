# SAGA — Schularbeits-Analyse mit Generativer AI

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

SAGA ist ein **terminalbasierter KI-Korrektur-Assistent** für österreichische Schularbeiten (Gymnasium, SRDP-Standards). Das Tool analysiert Schülertexte (`.docx`) mithilfe von Large Language Models (Claude, GPT, GLM, Kimi oder lokalem Ollama) und erstellt professionell formatierte Feedback-Dokumente mit Notenempfehlungen.

Entwickelt, um Lehrkräften stundenlange Korrekturarbeit zu ersparen — bei gleichbleibend **objektiver, rubrikbasierter Bewertung**.

---

## Funktionen

- **KI-gestützte Textanalyse** — Automatische Auswertung von Schülertexten anhand offizieller SRDP-Bewertungsraster (Deutsch & Englisch, Unterstufe & Oberstufe)
- **Multi-LLM-Unterstützung** — Flexibles Provider-System: Anthropic Claude, OpenAI GPT, GLM, Kimi oder lokales Ollama
- **Professionelle DOCX-Ausgabe** — Formatierte Word-Dokumente mit farbiger Notenübersicht, Stärken-/Schwächen-Analyse und konkreten Verbesserungsvorschlägen
- **Rich TUI-Dashboard** — Dreispaltiges Terminal-Interface (Textual-Framework) mit Tastaturnavigation, Datei-Browser, Rubrik-Viewer und Stapelverarbeitung
- **SRDP-konforme Bewertungsraster** — Integrierte Rubriken für österreichische Standardisierte Reifeprüfung: Deutsch Oberstufe/Unterstufe, Englisch A2/B1/B2
- **Stapelverarbeitung** — Mehrere Schülerarbeiten in einem Durchlauf korrigieren
- **Klassenverwaltung** — Eingaben nach Klasse und Aufgabe organisieren, Fortschritt nachverfolgen
- **Statistiken & Auswertungen** — Notenverteilung pro Klasse, Kriteriendurchschnitte, Identifikation der stärksten/schwächsten Kriterien
- **Robuste LLM-Pipeline** — Automatische Wiederholungsversuche mit exponentiellem Backoff, JSON-Schema-Validierung, strukturierter Output via Anthropic Tool Use
- **Watch-Modus** — Automatische Erkennung neuer Dateien im Eingabeverzeichnis
- **Dualer Betrieb** — Vollständiges Textual-Dashboard (Standard) oder schlanker InquirerPy-Assistent

---

## Architektur

```
saga.py (TUI Dashboard)   +   saga_wizard.py (Legacy CLI)
           |                            |
           +--------+-------------------+
                    |
            saga_core.py (Gemeinsame Logik)
                    |
        +-----------+-----------+
        |                       |
generate_feedback.py      LLM-Provider
(DOCX-Generierung)        (anthropic, openai, glm, kimi, ollama)
```

### Datenfluss

```
Schüler-.docx  →  Fach/Rubrik-Auswahl  →  LLM-Analyse
                                               ↓
                                    JSON-Validierung (Schema)
                                               ↓
                                    Review & Bearbeiten im TUI
                                               ↓
                                    Formatiertes DOCX-Feedback
```

---

## Screenshots

<img width="1682" height="1087" alt="image" src="https://github.com/user-attachments/assets/2a67ab3a-29ef-43bc-aa2a-a1dc0963bfe9" />

<br>

<img width="1524" height="673" alt="image" src="https://github.com/user-attachments/assets/b19316be-bb8e-463a-b0fb-de1cb66997a7" />

---

## Installation

### Voraussetzungen

- Python 3.11+
- (Optional) Ein API-Key für den gewünschten LLM-Provider

### Einrichtung

```bash
# Repository klonen
git clone https://github.com/milanradisavljevic/SAGA_Grader.git
cd SAGA_Grader

# Virtuelle Umgebung erstellen
python3 -m venv .venv
source .venv/bin/activate

# SAGA installieren
pip install -e .

# Für Entwicklung (Tests + Linting)
pip install -e ".[dev]"

# API-Key konfigurieren
cp .env.example .env
# .env mit gewünschtem LLM-Provider und API-Key befüllen
```

### Schnellstart

```bash
# Textual TUI-Dashboard starten
saga

# Oder Legacy-Wizard-Modus
saga-wizard
```

Schüler-`.docx`-Dateien im Verzeichnis `input/` ablegen und im Dashboard auswählen.

---

## Bedienung

### Tastenkürzel (Dashboard)

| Taste | Aktion |
|---|---|
| `↑`/`↓` | Dateiliste navigieren |
| `Tab` | Panel-Fokus wechseln |
| `a` | Aktuelle Datei analysieren |
| `Shift+A` | Alle markierten Dateien stapelweise analysieren |
| `r` | Analyse-Review-Dialog öffnen |
| `d` | DOCX-Feedback generieren |
| `e` | Zuordnung bearbeiten (Fach, Schulstufe, Textsorte, Rubrik) |
| `s` | Einstellungen öffnen |
| `?` | Hilfe anzeigen |
| `/` | Dateisuche |
| `Space` | Datei für Stapeloperationen markieren/entmarkieren |
| `q` | Beenden |

### API- vs. CLI-Modus

SAGA unterstützt zwei Analysemodi:

- **API-Modus** (empfohlen): Direkte LLM-API-Aufrufe — schnell, strukturierter JSON-Output, Schema-Validierung
- **CLI/Agent-Modus**: Lokale CLI-Agenten (Claude Code, Codex, Qwen) — geeignet für datenschutzsensible Inhalte

Umschalten in den Einstellungen (`s` → API aktiviert).

---

## Konfiguration

### `saga_config.toml`

| Abschnitt | Beschreibung |
|---|---|
| `[agent]` | CLI-Agenten-Befehle und Timeout |
| `[api]` | LLM-Provider, Modellauswahl |
| `[paths]` | Eingabe-/Ausgabe-/Rubrik-Verzeichnisse |
| `[classes]` | Klassen- und Aufgabendefinitionen |
| `[rubric_mapping]` | Zuordnung Fach+Stufe → Rubrik-Datei |

### `saga.tcss`

Vollständiges Textual-CSS-Theme für das Dashboard — Farben, Layout, Abstände.

---

## Projektstruktur

```
SAGA_Grader/
├── saga.py                  # Textual TUI-Dashboard
├── saga_core.py             # Gemeinsame Logik (Konfiguration, LLM, Pfade)
├── saga_wizard.py           # Legacy InquirerPy-Assistent
├── generate_feedback.py     # DOCX-Feedback-Generator
├── saga_config.toml         # Projektkonfiguration
├── saga.tcss                # Textual-CSS-Theme
├── feedback_schema.json     # JSON-Schema für LLM-Output
├── rubrics/                 # SRDP-konforme Bewertungsraster
│   ├── srdp_deutsch_oberstufe.md
│   ├── deutsch_unterstufe.md
│   ├── srdp_englisch_b1.md
│   ├── srdp_englisch_b2.md
│   └── englisch_a2.md
├── input/                   # Schüler-.docx-Eingaben
├── output/                  # Generierte Feedback-Dokumente
├── tests/                   # Pytest-Testsuite
│   ├── test_feedback.py
│   ├── test_llm_pipeline.py
│   ├── test_tui.py
│   └── fixtures/
└── docs/                    # Dokumentation & Screenshots
```

---

## Entwicklung

### Tests ausführen

```bash
pytest
```

### Linting

```bash
ruff check .
```

---

## Lizenz

MIT

---

## Warum SAGA?

SAGA ersetzt manuelle Korrektur durch einen KI-gestützten Workflow, der:
1. **Zeit spart** — konsistente, rubrikbasierte Analyse in Sekunden
2. **Bias reduziert** — objektive Bewertung anhand standardisierter Kriterien
3. **Feedback-Qualität verbessert** — detaillierte Stärken, Schwächen und konkrete Verbesserungsvorschläge
4. **Datenschutz wahrt** — unterstützt lokale Modelle (Ollama) und CLI-Agent-Modus für sensible Schülerdaten
