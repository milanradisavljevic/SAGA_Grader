# API-Modus aktivieren

Der API-Modus erlaubt direkte Aufrufe an die Anthropic API ohne CLI-Subprocess.

## Voraussetzungen

1. Anthropic API-Key besorgen: https://console.anthropic.com/
2. Paket installieren:
   ```bash
   pip install anthropic
   ```
3. API-Key als Umgebungsvariable setzen:
   ```bash
   # Einmalig in der aktuellen Session:
   export ANTHROPIC_API_KEY="sk-ant-..."

   # Dauerhaft (in ~/.bashrc oder ~/.zshrc):
   echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
   source ~/.bashrc
   ```
4. In `natascha_config.toml`:
   ```toml
   [api]
   enabled = true
   provider = "anthropic"
   model = "claude-sonnet-4-6"
   ```

## Kosten

Pro Schularbeit ca. 0,02 - 0,05 USD bei Sonnet, je nach Textlaenge und Rubrik.
Bei Opus entsprechend hoeher (ca. 5x).
