# Fragen & Antworten (nicht blockierend)

Ich arbeite währenddessen weiter und lese diese Datei regelmäßig. Antworte einfach direkt unter **Antwort:** (Freitext reicht).
Jede Frage hat einen **Standard**, den ich bis zu deiner Antwort verwende.

Status-Legende: 🟡 offen · 🟢 beantwortet · ⚙️ von mir mit Standard entschieden

---

## F1 – Oberfläche ohne Build-Schritt?  🟡
Das Projektheft nennt "Svelte oder React". Ich baue die Oberfläche zunächst als **Vanilla-TypeScript-freie JS-Module ohne Build-Schritt** (statische Dateien, vom Python-Server ausgeliefert). Vorteil: keine Node-Installation für Philipp/Maurice, einfacheres Release.
**Standard:** Vanilla-JS ohne Build.
**Antwort:**

## F2 – Wo sollen die Testdaten aus S2 E7 liegen?  🟡
Ich nutze die echten Dateien direkt aus `F:\OneDrive\...` (nur lesend) und erzeuge kleine Test-Ausschnitte (≈60 s) im lokalen Cache, nicht im Repo.
**Standard:** Nur lesend aus OneDrive, Ausschnitte lokal in `.testdata/` (gitignored).
**Antwort:**

## F3 – Premiere-Panel nicht testbar  🟡
Ich kann Premiere hier nicht starten. Das UXP-Panel schreibe ich nach bestem Wissen der UXP-API und mit Schnittpaket-Format, aber **ungetestet**; zusätzlich liefere ich den FCP-XML-Fallback, den ich per Parser validiere.
**Standard:** Panel als Best-Effort-Skelett, Fallback-XML als geprüfter Weg.
**Antwort:**

## F4 – Whisper-Modell  🟡
RTX 4070 Ti (12 GB) vorhanden. Standard: `large-v3` auf CUDA, sonst `small` auf CPU.
**Standard:** large-v3 (GPU) / small (CPU).
**Antwort:**

## F5 – ScaDS-Modelle  ⚙️
Ich frage `/v1/models` ab und wähle automatisch ein passendes Modell (bevorzugt DeepSeek/GLM). Auswahl pro Funktion in den Einstellungen änderbar.

## F6 – Git  🟡
Der Ordner ist (noch) kein Git-Repository. Ich lege lokal eins an (`git init`), committe ohne Remote. `.env` kommt in `.gitignore`.
**Antwort:**

---
## Log (von mir)
- 2026-10-22: Datei angelegt.
