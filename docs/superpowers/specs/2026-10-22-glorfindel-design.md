# Glorfindel – Design-Spec (Umsetzungsentscheidungen)

Fachliche Anforderungen: `Projektheft Folgenbesprechungs-Tool.md` (maßgeblich). Dieses Dokument legt nur fest, **wie** gebaut wird.
Vorgabe des Nutzers: autonom arbeiten, Rückfragen nicht blockierend über `FRAGEN.md`.

## Architektur
- `server/glorfindel/` Python-Paket (FastAPI). Module, je eine Aufgabe:
  - `config.py` Einstellungen (lokal, nie in OneDrive), `.env` für ScaDS.
  - `paths.py` OneDrive-Stamm, relative Pfade, Cache-Ordner.
  - `store.py` JSON-Dateien pro Entität (atomar schreiben), weiche Sperren, Änderungsprotokoll, Konfliktkopien.
  - `models.py` Pydantic-Modelle mit `schema_version`.
  - `media.py` ffprobe/ffmpeg: Probe, Proxy (540p, All-Intra H.264), Stills, Thumbnails.
  - `timemap.py` Episodenzeit ↔ Quellzeit (Ankerpunkte, stückweise linear).
  - `scenes.py` Szenen/Segmente, Längenampel, PySceneDetect-Vorschläge, Stränge.
  - `script_docx.py` Word-Export/-Rückimport mit Szenenmarken.
  - `align.py` Whisper (faster-whisper, optional), Wort-Alignment, Retakes.
  - `rough_cut.py` `schnitt.json`, Stills, FCP-XML-Fallback.
  - `conform.py` HQ-Conform (ffmpeg-Filtergraph aus Ankern).
  - `images.py` Bildindex (SQLite, XMP), Credit-Vorbelegung, Konturfarbe.
  - `maps.py` Kartenproxy (JSON, PNG/Platzhalterclip).
  - `llm.py` OpenAI-kompatibler Client (ScaDS), abschaltbar.
  - `api.py` REST + statische Auslieferung von `web/`; `__main__.py` Starter.
- `web/` statische Oberfläche, ES-Module, kein Build (Frage F1).
- `premiere-panel/` UXP-Skelett, `ae-scripts/` JSX, `vorlagen/` Rezepte (`grafiken.json`, `effekt_rezepte.json`).
- Tests: `pytest`, Medientests mit kurzen synthetischen ffmpeg-Clips (lavfi), zusätzlich optionale Tests gegen echte S2-E7-Ausschnitte (`.testdata/`).

## Datenmodell
Wie Heft §7: pro Folge `glorfindel/projekt.json`, `quellen.json`, `szenen/sz_XX.json`, `straenge.json`, `assets/`, `karten/`, `aufnahme/abgleich.json`, `log.jsonl`. Zeiten in Sekunden Episodenzeit. Pfade relativ zum OneDrive-Stamm (POSIX-Schrägstriche).

## Zeitabbildung
`t_quelle = a·t_ref + b` pro Anker-Intervall; ≥2 Anker ⇒ stückweise linear, außerhalb extrapoliert mit erstem/letztem Segment. Invertierbar. Quelle ohne Anker = Identität.

## Wichtige Entscheidungen
1. Schnittpaket-JSON ist die Schnittstelle zu Premiere; FCP-XML als Fallback.
2. Conform: je Zeitabbildungs-Intervall `trim`+`setpts` (Tempo) + `tpad`/`color` für Lücken, Ausgabe ProRes 422 HQ/DNxHR; Test mit libx264 für Geschwindigkeit.
3. Retakes: Skript-Satzfenster gegen Transkript-Wortfolge (difflib/Levenshtein auf normalisierten Wörtern), mehrere Treffer ⇒ letzter Take.
4. LLM nur optional, jede Funktion einzeln abschaltbar; Fehler/Timeouts ⇒ stiller Fallback.
5. Längenampel: Segment >9,5 s rot, >80 % gelb; Serienanteil Ziel 34 % (einstellbar).

## Nicht umgesetzt / nur Skelett
Premiere-Ausführung (nicht testbar), echte Auto-Update-Installer (Skelett über GitHub-Release-Check), AE-Skript ungetestet.
