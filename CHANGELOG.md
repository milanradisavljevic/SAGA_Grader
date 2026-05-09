# Changelog

## 2026-04-13 – v0.6.0 (LLM-Analyse-Pipeline mit Retry-Logik)

### LLM-Pipeline (Neu)
- **`run_llm_analysis()`** in `saga_core.py`: Vollstaendige Analyse-Pipeline
  - Prompt-Building → API-Aufruf → JSON-Extraktion → Schema-Validierung
  - **Automatische Retry-Logik** (bis zu 3 Versuche) bei:
    - Ungueltigem JSON aus der LLM-Antwort
    - Schema-Verletzungen im JSON-Response
  - Retry-Prompt enthaelt Fehlerdetails + Original-Aufgabe als Kontext
  - Exponentieller Backoff (2s, 4s, 6s) zwischen Retries
  - `cancel_event`-Support fuer sofortigen Abbruch
  - Return-Typ: `tuple[data | None, list[errors]]` – explizite Fehlerkommunikation

### Dashboard
- **`_run_analysis()`** refactored: Nutzt jetzt `nc.run_llm_analysis()` statt manueller Einzelschritte
  - Deutlich weniger Code, bessere Fehlerbehandlung
  - Alle Fehler (JSON, Schema, API) werden ins Fehlerlog geschrieben
  - Status-Text "Analyse laeuft..." statt nur "Sende an API..."

### Tests
- **`tests/test_llm_pipeline.py`**: Neue Testsuite fuer die LLM-Pipeline
  - `extract_json_from_llm`: Plain JSON, Markdown-fenced, Surrounding Text, Error Cases
  - `validate_against_schema`: Valid-Fixture, Missing Fields, Invalid Note Range, No Schema
  - `_build_retry_prompt`: Error Message, Attempt Number, Truncation
  - `run_llm_analysis`: Success on first try, Retry on invalid JSON, Fail after max retries, API error (no retry), Cancel event, Schema violation then success

### Bugfix
- VERSION auf 0.6.0 aktualisiert

## 2026-04-13 – v0.5.0 (UX-Verbesserungen + DOCX-Redesign)

### TUI / Dashboard
- **EditAssignment**: Text-Inputs durch `Select`-Dropdowns ersetzt (Fach, Schulstufe, Textsorte, Rubrik)
  - Textsorte-Optionen wechseln automatisch je nach Fach (Deutsch / Englisch)
  - Rubrik wird auf Basis von Fach+Schulstufe vorausgewählt (inkl. B1/B2 für Englisch Oberstufe)
- **File-Watcher**: Neuer Background-Worker pollt `input/` alle 10s; neue `.docx`-Dateien werden ohne Neustart erkannt
- **Cancel**: `threading.Event` auf App-Ebene ersetzt fragilen Screen-Flag-Ansatz
- **Einstellungen**: Default-Fach, Schulstufe und Modell jetzt direkt im Dashboard bearbeitbar (kein Editor, kein Neustart)
- **Logo**: Acronym aktualisiert → "Normbasierte Analyse von Texten / Automatisierte Schularbeits-Correction mit Hilfe-Agents"

### DOCX-Generator
- **Zusammenfassungstabelle**: Kriterien-Übersicht mit blauem Header und farbiger Notenzeile am Dokumentanfang
- **Farbschema**: Stärken grün, Schwächen rot, Verbesserungsvorschläge blau (benannte Konstanten `C_STRENGTH`, `C_WEAKNESS`, `C_SUGGESTION`)
- **Notenfarbe**: Note ≥ 5 rot, alle anderen in der Primärfarbe (vorher: immer orange)
- **Header-Block**: Metadaten-Tabelle (Datei, Schüler/in, Fach, Datum) mit optionalem Logo und Lehrerkennzeichnung
- **Seitenformat**: A4 explizit gesetzt (21×29.7cm), Ränder 2.5cm, Fußzeile mit Datum
- `build_feedback_document()` nimmt jetzt optionales `config`-Dict für Lehrername, Schule, Logo-Pfad

### Bugfix
- `tests/test_tui.py`: Import von `natascha_tui` auf `saga_core` korrigiert (Modul wurde in v0.4.0 umbenannt)

## 2026-04-11 – v0.4.0 (Textual Dashboard)

- `saga.py` Neu: Textual-basiertes 3-Spalten-Dashboard (Dateien / Zuordnung / Vorschau)
- `saga_core.py` Logik-Funktionen aus dem Wizard extrahiert (gemeinsamer Unterbau)
- `saga_wizard.py` Bisheriger rich+InquirerPy-Wizard als Fallback umbenannt
- `saga.tcss` Eigenstaendige CSS-Datei fuer das Dashboard
- Asynchrone API-Analyse mit `@work(thread=True)` und Fortschrittsdialog
- Modale Dialoge: Review, Einstellungen, Hilfe, Zuordnung bearbeiten
- Tastatursteuerung: Navigation, Batch-Markierung, Suche, Sortierung
- Existierende Analysen werden beim Start automatisch erkannt
- CLI: `python saga.py` (Dashboard), `python saga_wizard.py` (Wizard)

## 2026-04-10

- neue SRDP-orientierte Rubrics fuer Deutsch Oberstufe, Deutsch Unterstufe und Englisch A2/B1/B2 angelegt
- bisherige Rubrics aus `rubrics/` nach `rubrics/legacy/` verschoben
- `MASTER_PROMPT.md` auf das neue Rubric-System vorbereitet
- `generate_feedback.py` von hartcodierten Einzelfaellen auf einen JSON-basierten Batch-Generator umgestellt
- `feedback_schema.json` sowie pytest-Fixtures und Tests fuer den DOCX-Generator ergaenzt
