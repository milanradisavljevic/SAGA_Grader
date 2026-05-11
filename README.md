# SAGA — Schularbeits-Analyse mit Generativer AI

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

SAGA is a **terminal-based AI grading assistant** for Austrian secondary school exams (Gymnasium, SRDP standards). It analyzes student essays (`.docx`) using Large Language Models (Claude, GPT, GLM, Kimi, or local Ollama) and generates professionally formatted feedback documents with grade recommendations.

Designed to save teachers hours of grading time while maintaining **objective, rubric-aligned assessments**.

---

## Features

- **AI-Powered Essay Analysis** — Automatically evaluates student texts against official SRDP rubrics (Deutsch & Englisch, Unterstufe & Oberstufe)
- **Multi-LLM Support** — Pluggable provider system: Anthropic Claude, OpenAI GPT, GLM, Kimi, or local Ollama
- **Professional DOCX Feedback** — Generates formatted Word documents with colored grade tables, strengths/weaknesses analysis, and improvement suggestions
- **Rich TUI Dashboard** — Three-column terminal UI (Textual framework) with keyboard navigation, file browser, rubric viewer, and batch processing
- **SRDP-Compliant Rubrics** — Built-in rubrics for Austrian standardised exams: Deutsch Oberstufe/Unterstufe, Englisch A2/B1/B2
- **Batch Processing** — Grade multiple student submissions in one run
- **Class Management** — Organise submissions by class and assignment, track progress over time
- **Statistics & Analytics** — Per-class grade distributions, criteria averages, weakest/strongest criteria identification
- **Robust LLM Pipeline** — Automatic retry with exponential backoff, JSON schema validation, structured output via Anthropic Tool Use
- **Watch Mode** — Automatic file detection in input directories
- **Dual UI** — Full Textual dashboard (default) or lightweight InquirerPy wizard

---

## Architecture

```
saga.py (TUI Dashboard)   +   saga_wizard.py (Legacy CLI)
           |                            |
           +--------+-------------------+
                    |
            saga_core.py (Shared Logic)
                    |
        +-----------+-----------+
        |                       |
generate_feedback.py      LLM Providers
(DOCX generation)         (anthropic, openai, glm, kimi, ollama)
```

### Data Flow

```
Student .docx  →  Subject/Rubric Selection  →  LLM Analysis
                                                   ↓
                                        JSON Validation (Schema)
                                                   ↓
                                        Review & Edit in TUI
                                                   ↓
                                        Formatted DOCX Feedback
```

---

## Screenshots

<img width="1682" height="1087" alt="image" src="https://github.com/user-attachments/assets/2a67ab3a-29ef-43bc-aa2a-a1dc0963bfe9" />
<img width="1524" height="673" alt="image" src="https://github.com/user-attachments/assets/b19316be-bb8e-463a-b0fb-de1cb66997a7" />


---

## Installation

### Prerequisites

- Python 3.11+
- (Optional) An API key for your chosen LLM provider

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/saga.git
cd saga

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install SAGA
pip install -e .

# For development (tests + linting)
pip install -e ".[dev]"

# Configure your API key
cp .env.example .env
# Edit .env with your LLM provider and API key
```

### Quick Start

```bash
# Start the Textual TUI dashboard
saga

# Or use the legacy wizard mode
saga-wizard
```

Place student `.docx` files in the `input/` directory and select them from the dashboard.

---

## Usage

### Keyboard Shortcuts (Dashboard)

| Key | Action |
|---|---|
| `↑`/`↓` | Navigate file list |
| `Tab` | Cycle panels |
| `a` | Analyse current file |
| `Shift+A` | Batch-analyse all marked files |
| `r` | Open analysis review dialog |
| `d` | Generate DOCX feedback |
| `e` | Edit assignment (subject, grade level, text type, rubric) |
| `s` | Open settings |
| `?` | Show help |
| `/` | Search files |
| `Space` | Mark/unmark file for batch operations |
| `q` | Quit |

### API vs. CLI Mode

SAGA supports two analysis modes:

- **API mode** (recommended): Direct LLM API calls — fast, structured JSON output, schema validation
- **CLI/Agent mode**: Uses local CLI agents (Claude Code, Codex, Qwen) — useful for private data

Toggle between modes in Settings (`s` → API enabled).

---

## Configuration

### `saga_config.toml`

| Section | Description |
|---|---|
| `[agent]` | CLI agent commands and timeout |
| `[api]` | LLM provider, model selection |
| `[paths]` | Input/output/rubric directories |
| `[classes]` | Class and assignment definitions |
| `[rubric_mapping]` | Subject+level to rubric file mapping |

### `saga.tcss`

Full Textual CSS theme for the dashboard — colours, layout, spacing.

---

## Project Structure

```
saga/
├── saga.py                  # Textual TUI Dashboard
├── saga_core.py             # Shared logic (config, LLM, paths)
├── saga_wizard.py           # Legacy InquirerPy wizard
├── generate_feedback.py     # DOCX feedback generator
├── saga_config.toml         # Project configuration
├── saga.tcss                # Textual CSS theme
├── feedback_schema.json     # JSON schema for LLM output
├── rubrics/                 # SRDP-compliant grading rubrics
│   ├── srdp_deutsch_oberstufe.md
│   ├── deutsch_unterstufe.md
│   ├── srdp_englisch_b1.md
│   ├── srdp_englisch_b2.md
│   └── englisch_a2.md
├── input/                   # Student .docx submissions
├── output/                  # Generated feedback documents
├── tests/                   # Pytest test suite
│   ├── test_feedback.py
│   ├── test_llm_pipeline.py
│   ├── test_tui.py
│   └── fixtures/
└── docs/                    # Development documentation & screenshots
```

---

## Development

### Running Tests

```bash
pytest
```

### Linting

```bash
ruff check .
```

---

## License

MIT

---

## Why SAGA?

SAGA replaces manual correction with an AI-assisted workflow that:
1. **Saves time** — consistent, rubric-based analysis in seconds
2. **Reduces bias** — objective evaluation against standardised criteria
3. **Improves feedback quality** — detailed strengths, weaknesses, and actionable suggestions
4. **Maintains privacy** — supports local models (Ollama) and CLI agent mode for sensitive data
