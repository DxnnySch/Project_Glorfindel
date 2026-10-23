# Projekt Glorfindel

Lokales Werkzeug, das aus Episode, Skript, Bildern, Karten und Sprachaufnahmen einen Premiere-Rohschnitt für die „Ringe der Macht“-Folgenbesprechungen erzeugt.

## Installation
- **Windows:** `install.ps1` per Rechtsklick „Mit PowerShell ausführen“, danach `start.bat`.
- **macOS/Linux:** `./install.sh`, danach `./start.sh`.

Beim ersten Start öffnet sich der Browser (http://localhost:8765). In den **Einstellungen** den OneDrive-Stammordner wählen – fertig.
Der ScaDS-Schlüssel (optional, für KI-Hilfen) steht in `.env` (Vorlage: `.env.example`).

Eine ausführliche Schritt-für-Schritt-Anleitung steht in der Anwendung unter **Hilfe** (Quelle: `web/help/anleitung.md`).

## Ablauf
1. **Folge anlegen**, Referenz-Episode unter *Quellen* importieren (Proxy erzeugen), weitere Fassungen per Ankerpunkten abbilden.
2. **Szenen** schreiben (Text oder Stichpunkte), Segmente mit `I`/`O` im Player setzen; Längenampel zeigt zu lange Segmente.
3. Optional Skript als **Word** exportieren/zurückspielen, **Bilder** und **Karten** zuordnen.
4. **Aufnahme** importieren und automatisch zuordnen (lokal Whisper, optional ScaDS).
5. **Rohschnitt** erzeugen: Schnittpaket (.json) für das Premiere-Panel plus FCP-XML als Fallback.

## Entwicklung
`uv venv .venv && uv pip install -e ".[dev]"`, Tests: `.venv/bin/python -m pytest -q` (benötigt ffmpeg). Maßgebliche Spezifikation: `Projektheft Folgenbesprechungs-Tool.md`; Arbeitsstand: `STATUS.md`.
