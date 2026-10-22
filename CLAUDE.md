# Projekt Glorfindel – Arbeitskontext für Claude

Lokales Web-Tool (Python/FastAPI + statische Weboberfläche), das aus Episode, Skript, Bildern, Karten und Sprachaufnahmen einen Premiere-Rohschnitt für die „Ringe der Macht“-Folgenbesprechungen erzeugt.

**Maßgebliche Spezifikation:** `Projektheft Folgenbesprechungs-Tool.md`. Eigene Umsetzungsentscheidungen: `docs/superpowers/specs/`, Plan: `docs/superpowers/plans/`. Offene Fragen an Danny: `FRAGEN.md` (nicht blockierend, regelmäßig auf Antworten prüfen). Stand/Offenes: `STATUS.md`.

## Arbeitsvereinbarungen
- Danny will **keine Rückfragen**, die blockieren; Fragen gehören in `FRAGEN.md` mit Standardwert.
- **Commits ohne Co-Authored-By oder andere Attributionszeilen.**
- UI muss professionell aussehen und einfach zu installieren/bedienen sein. Texte der Oberfläche auf Deutsch.
- `.env` (SCADS_API_KEY, SCADS_BASE_URL) ist lokal und nie im Repo. In einer Cloud-Sitzung als Umgebungsvariablen/Secrets setzen.
- Nutzertext nur per `textContent` ins DOM (kein innerHTML mit Nutzerdaten). Server bindet nur an 127.0.0.1, Middleware prüft Host/Origin.

## Befehle
- Einrichten: `uv venv .venv && uv pip install -e ".[dev]"` (optional `faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12` für lokales Whisper)
- Tests: `.venv/Scripts/python -m pytest -q` (Windows) bzw. `.venv/bin/python -m pytest -q`; benötigt `ffmpeg`/`ffprobe` im PATH.
- Start: `python -m glorfindel` (öffnet Browser auf http://localhost:8765)

## Architektur (server/glorfindel/)
`store` (atomare JSON, weiche Sperren, Konfliktkopien) · `timemap` (Anker, stückweise linear) · `media` (ffprobe/Proxy/Stills) · `conform` (HQ-Conform) · `scenes` (Längenampel, Stichpunkte) · `script_docx` + `legacy_import` (Word) · `align` / `align_bullets` / `stt` (Whisper lokal/ScaDS, Text- und Stichpunkt-Abgleich) · `rough_cut` + `fcpxml` (Schnittpaket, Fallback-XML) · `prfpset` (Effektrezepte) · `images` / `maps` / `llm` · `pipeline` (Orchestrierung) · `routes_*` + `api` (REST) · `web/` (ES-Module ohne Build).

## Testdaten (nur auf Dannys Rechner)
`F:\OneDrive\Mythen-Archiv\Videos\S2 E7\…` (Skript-docx, Aufnahmen), `F:\OneDrive\Videomaterial\Filme\Ringe der Macht\Staffel 2\…` (HQ deutsch, englische Bildschirmaufnahme), `…\Programm-Vorgaben\PremierePro\*.prfpset`. Tests, die diese Pfade brauchen, werden ohne sie übersprungen.
