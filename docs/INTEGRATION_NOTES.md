# INTEGRATION_NOTES.md – Was mir beim Bauen aufgefallen ist

> Erstellt: 2026-04-10
> Autor: GLM 5.1 (TUI-Bau)
> Aktualisiert: 2026-04-11 – v0.4.0 (Textual Dashboard)

---

## v2-Umstellung: textual -> rich + InquirerPy

Der erste TUI-Entwurf basierte auf textual (5-Screen-Dashboard). Im Praxistest crashte er bei Dateinamen mit Sonderzeichen (`BadIdentifier` – Widget-IDs duerfen keine `!`, `-`, `.` etc. enthalten). Zudem war das Dashboard-Pattern fuer die Zielgruppe (Lehrkraft, 3x/Semester) zu komplex.

**Loesung:** Komplett auf rich + InquirerPy umgestellt. Wizard-Pattern (eine Frage nach der anderen), keine Widget-IDs, kein CSS, keine Screen-Klassen. Dateinamen sind jetzt nur noch Anzeige-Labels in `Choice.name`, nicht mehr Teil irgendwelcher Identifikatoren.

**Beibehalten:** Alle Logik-Funktionen (load_config, build_analysis_prompt, run_agent_sync etc.) wurden 1:1 uebernommen. Die beiden aktiven Fixes (Finding 3 + 4) sind weiterhin wirksam.

## Aktiv geloeste Probleme

### Finding 3: `main()` loescht fehlerlog.txt bei jedem Aufruf

**Ort:** `generate_feedback.py:458`

```python
if not args.dry_run:
    paths.fehlerlog.write_text("", encoding="utf-8")
```

**Problem:** `main()` loescht das Fehlerlog bei jedem Aufruf. Wenn die TUI `main()` nutzen wuerde, wuerden Fehler vorheriger Laeufe verloren gehen.

**Loesung in der TUI:** Die TUI ruft NICHT `main()` auf. Stattdessen:
- Screen 5 (`GenerationScreen`) ruft direkt `gf.parse_feedback_data()` und `gf.build_feedback_document()` auf.
- Fehler werden ueber eine eigene `log_tui_error()` Funktion ins Fehlerlog geschrieben (append-Modus, mit `[TUI]`-Praefix).
- Dadurch bleibt das Fehlerlog ueber mehrere TUI-Sessions hinweg erhalten.

### Finding 4: `project_paths()` ist skript-relativ

**Ort:** `generate_feedback.py:95`

```python
root = Path(__file__).resolve().parent
```

**Problem:** `project_paths()` verwendet `__file__` als Basis. Wenn die TUI `generate_feedback.py` importiert (was sie tut), verweist `__file__` auf den Speicherort von `generate_feedback.py` – das funktioniert. Aber wenn die TUI aus einem anderen Arbeitsverzeichnis gestartet wird (z.B. `cd /tmp && python /home/milan/dev/Natascha3/natascha_tui.py`), wuerden relative Pfadangaben in der Konfiguration nicht mehr stimmen.

**Loesung in der TUI:** Die TUI verwendet `PROJECT_ROOT = Path(__file__).resolve().parent` (aus `natascha_tui.py`) als feste Basis und baut eigene Pfade ueber `resolve_path(config, key)` auf. Fuer den Aufruf von `generate_feedback`-Funktionen wird `build_project_paths()` verwendet, das ebenfalls `PROJECT_ROOT` nutzt. Dadurch ist die TUI unabhaengig vom Startverzeichnis.

---

## Dokumentierte Beobachtungen (keine Code-Aenderung)

### Finding 1: A2-Rubrik deutsche Keys vs. Code englische Keys

`rubrics/englisch_a2.md` beschreibt die Kriterien auf Deutsch ("Erfuellung der Aufgabenstellung", "Aufbau und Layout", "Wortschatz", "Grammatik"), aber `generate_feedback.py` erwartet englische Keys (`task_achievement`, `organisation_layout`, `lexical_range_accuracy`, `grammatical_range_accuracy`), wenn `fach == "Englisch"`.

Die `ALIASES`-Map in `generate_feedback.py:29` bietet Ersetzungen an (`erfuellung_aufgabenstellung` -> `task_achievement`, `wortschatz` -> `lexical_range_accuracy`), deckt aber nicht exakt die Formulierungen in der A2-Rubrik ab. Der LLM-Prompt muss klarstellen, dass die JSON-Keys die englischen Varianten sein muessen, egal welche Sprache die Rubrik hat.

**Empfehlung:** Den LLM-Prompt explizit die erwarteten JSON-Key-Namen auflisten lassen. Die TUI tut das ueber das eingebettete Schema und Beispiel-JSON.

### Finding 2: CEFR-Level (A2/B1/B2) fehlt als explizites Feld im Schema

`feedback_schema.json` hat `schulstufe` (Unterstufe/Oberstufe) aber keinen Eintrag fuer das CEFR-Niveau (A2, B1, B2). Das Niveau ist nur implizit ueber den Rubrik-Dateinamen codiert (z.B. `srdp_englisch_b2.md`). Das funktioniert, solange man den Rubrik-Namen parst, ist aber fragil.

**Auswirkung auf die TUI:** Die TUI leitet das Niveau aus der Rubrik-Auswahl ab. Das Mapping steht in `natascha_config.toml` unter `[rubric_mapping]`. Kein Breaking-Change, aber ein potenzielles Problem fuer zukuenftige Erweiterungen.

### Finding 5: `additionalProperties: false` im Schema

`feedback_schema.json:122` und `:148` setzen `additionalProperties: false`. Das bedeutet: jedes zusaetzliche Feld im JSON fuehrt zu einem Validierungsfehler. Das ist einerseits gut (strikte Konformitaet), andererseits koennen LLMs kreative Felder hinzufuegen, die dann abgelehnt werden.

**Auswirkung auf die TUI:** Die Schema-Validierung in Screen 4 wird diese Fehler anzeigen. Der User kann das JSON dann manuell bereinigen. Das ist akzeptabel, aber der LLM-Prompt muss sehr klar sein: "Keine zusaetzlichen Felder erfinden."

### Finding 6: Englisch Oberstufe hat zwei Rubrics (B1/B2)

Der Workflow "Englisch + Oberstufe -> srdp_englisch_b2.md" ist sinnvoll als Default, aber die Unterscheidung zwischen B1 und B2 ist nur ueber den Rubrik-Dateinamen sichtbar. Das Feld `schulstufe` im JSON sagt nur "Oberstufe", nicht "B2".

**Auswirkung auf die TUI:** Die TUI zeigt beide Optionen im Rubrik-Dropdown an (B2 als Default, B1 waehlbar). Die Zuordnung ist transparent, aber das JSON selbst speichert nur den Rubrik-Namen. Bei der Notenberechnung muesste man den Rubrik-Namen parsen, um das Niveau zu ermitteln. Aktuell ist das kein Problem, da die Notenberechnung vom LLM gemacht wird, nicht von der TUI.

---

## Zusammenfassung

| # | Finding | Typ | Geloesst? |
|---|---------|-----|-----------|
| 1 | A2 deutsche Keys vs. Code englische Keys | Prompt-Thema | Dokumentiert |
| 2 | CEFR-Level fehlt im Schema | Schema-Erw. vorgeschlagen | Dokumentiert |
| 3 | fehlerlog.txt wird geleert | **Aktiv geloest** | Ja (TUI umgeht `main()`) |
| 4 | project_paths skript-relativ | **Aktiv geloest** | Ja (TUI eigenes PROJECT_ROOT) |
| 5 | additionalProperties: false sehr strikt | Prompt-Thema | Dokumentiert |
| 6 | B1/B2 nur im Rubrik-Namen | Architektur-Hinweis | Dokumentiert |

---

## v0.4.0: Textual Dashboard (2026-04-11)

### Architektur

Drei-Spalten-Dashboard mit Textual statt Wizard-Pattern. Datei-Struktur:

- `natascha.py` – Hauptapp (Textual `App`-Subklasse)
- `natascha_core.py` – Geteilte Logik (wird von Dashboard und Wizard genutzt)
- `natascha_wizard.py` – Bisheriger Wizard (Fallback)
- `natascha.tcss` – Externe CSS-Datei

### Lessons Learned aus dem ersten Textual-Versuch (v2)

1. **Widget-IDs**: Niemals Dateinamen direkt als IDs verwenden. `safe_id()` hasht den Dateinamen mit MD5 (8 Zeichen). Mapping in `_id_to_index`.
2. **Ein Dashboard statt 5 Screens**: Reactive State (`selected_index`, `preview_mode`, `sort_mode`) statt Screen-Hopping.
3. **Async Workers**: `@work(thread=True)` fuer API-Calls, `call_from_thread()` fuer UI-Updates.
4. **CSS in `.tcss`**: Externe Datei statt inline.
5. **ModalScreen**: Fuer Review, Settings, Help, Progress, Confirm.

### Bekannte Einschraenkungen

- **EditAssignmentScreen**: Verwendet einfache `Input`-Widgets statt Dropdowns. User muss exakte Werte eingeben (Deutsch/Englisch, Oberstufe/Unterstufe). Bei Fehleingabe greift der Default.
- **Kein File-Watcher**: Neue Dateien im input/-Ordner werden nicht automatisch erkannt. Neustart noetig.
- **ProgressScreen cancel**: Der Abbrechen-Button bricht nach der aktuell laufenden Datei ab, nicht sofort.
- **Settings bearbeiten**: "Konfigurationsdatei oeffnen" beendet die App. Neu starten nach dem Editieren.
