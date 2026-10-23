# Fragen & Antworten (nicht blockierend)

Ich arbeite währenddessen weiter und lese diese Datei regelmäßig. Antworte einfach direkt unter **Antwort:** (Freitext reicht).
Jede Frage hat einen **Standard**, den ich bis zu deiner Antwort verwende.

Status-Legende: 🟡 offen · 🟢 beantwortet · ⚙️ von mir mit Standard entschieden

---

## F1 – Oberfläche ohne Build-Schritt?  🟢
Das Projektheft nennt "Svelte oder React". Ich baue die Oberfläche zunächst als **Vanilla-TypeScript-freie JS-Module ohne Build-Schritt** (statische Dateien, vom Python-Server ausgeliefert). Vorteil: keine Node-Installation für Philipp/Maurice, einfacheres Release.
**Standard:** Vanilla-JS ohne Build.
**Antwort:** es soll sehr nutzerfreundlich sowohl in installation als auch in Bedienung sein, achte darauf und stelle sicher, dass es professionell aussieht und nutzbar ist!

## F2 – Wo sollen die Testdaten aus S2 E7 liegen?  🟢
Ich nutze die echten Dateien direkt aus `F:\OneDrive\...` (nur lesend) und erzeuge kleine Test-Ausschnitte (≈60 s) im lokalen Cache, nicht im Repo.
**Standard:** Nur lesend aus OneDrive, Ausschnitte lokal in `.testdata/` (gitignored).
**Antwort:** passt

## F3 – Premiere-Panel nicht testbar  🟢
Ich kann Premiere hier nicht starten. Das UXP-Panel schreibe ich nach bestem Wissen der UXP-API und mit Schnittpaket-Format, aber **ungetestet**; zusätzlich liefere ich den FCP-XML-Fallback, den ich per Parser validiere.
**Standard:** Panel als Best-Effort-Skelett, Fallback-XML als geprüfter Weg.
**Antwort:** ist okay

## F4 – Whisper-Modell  🟢
RTX 4070 Ti (12 GB) vorhanden. Standard: `large-v3` auf CUDA, sonst `small` auf CPU.
**Standard:** large-v3 (GPU) / small (CPU).
**Antwort:** scads hat auch ein whisper

## F5 – ScaDS-Modelle  ⚙️
Ich frage `/v1/models` ab und wähle automatisch ein passendes Modell (bevorzugt DeepSeek/GLM). Auswahl pro Funktion in den Einstellungen änderbar.

## F6 – Git  🟢
Der Ordner ist (noch) kein Git-Repository. Ich lege lokal eins an (`git init`), committe ohne Remote. `.env` kommt in `.gitignore`.
**Antwort:** achte bei commits darauf, dass kein co-authored-by oder ähnliches enthalten ist

## F7 – Stichpunkt-Skripte (frei ausformulieren)  ⚙️
Umgesetzt (deine Nachricht): Ein Kommentarblock hat einen Modus „text“ oder „stichpunkte“ (Zeilen mit `-`/`•` im Textfeld werden automatisch erkannt). Word-Export schreibt Stichpunkte als Aufzählung, Rückimport liest sie zurück. Der Abgleich ordnet das Transkript per Schlüsselwörtern den Stichpunkten zu (reihenfolgetreu, Retakes = letzter Take), Bilder/Karten hängen an Stichpunkten. Danach kann der gesprochene Text mit einem Klick als Skript übernommen werden (Anker wandern auf Wörter).
Offene Feinjustierung: Zeitschätzung ohne Aufnahme = **12 s pro Stichpunkt** (einstellbar `bullet_seconds`). Passt das etwa zu euch?
**Antwort:** es wird erst das "Skript" erstellt, dann eingesprochen und dann zugeordnet, wenn das geht, dann kann danach der Rawcut gemacht werden easy

## F8 – Credit-Spuren bei Doppelbild  🟡
Heft nennt „zwei Credit-Spuren“, V11 (Musik-Credit) und V12 (Bauchbinden) sind belegt. Standard: V10 (links/einzeln) und **V13** (rechts).
**Antwort:** top

---
## Log (von mir)
- 2026-10-22: Datei angelegt.
- Antworten erhalten (15:20): F1 → Fokus auf Profi-Optik + einfache Installation/Bedienung (wird umgesetzt). F4 → ScaDS-Whisper wird als wählbares Transkriptions-Backend ergänzt (Heft: „nie Audio senden“ → nur auf deine Anweisung, in den Einstellungen gekennzeichnet). F6 → keine Co-Author-Zeilen in Commits.
- 2026-10-22 15:10: Kern (Store, Zeitmodell, Conform, Word, Rohschnitt, Abgleich inkl. Stichpunkte) fertig, 54 Tests grün.
- 2026-10-22: Weboberfläche, Installer und README ergänzt. Der ScaDS-Schlüssel liegt nur in der lokalen `.env` (gitignored). Da er im Chat stand, rotiere ihn bitte bei Gelegenheit.
- 2026-10-22 (abends): Teil 2 des Projekthefts umgesetzt (Aufgabenleiste, Cockpit, Karten-Editor, Anker setzen u. v. m.), zwei unabhängige Review-Durchgänge eingearbeitet.

## F9 – Reihenfolge im Word: Strang oder Szenen-Editor?  🟡
Aktuell sortiert Word/Rohschnitt nach Strang-Reihenfolge, der Editor zeigt die Szenen-Reihenfolge (die Liste zeigt jetzt die Ausgabenummer). Beim Word-Export gibt es einen Schalter.
**Standard:** Nach Strängen (wie im Heft).
**Antwort:**

## F10 – Soll „Papierkorb“ eine eigene Ansicht bekommen?  🟡
Gelöschte Szenen liegen im Ordner `glorfindel/papierkorb/` und lassen sich 12 s per „Rückgängig“ zurückholen; eine Übersicht fehlt noch.
**Standard:** Später, nur bei Bedarf.
**Antwort:**

## F11 – Premiere-XML: „Dateiimport fehlgeschlagen“ ohne Meldung  🟢→🟡
Danke für die `schnitt_v1.xml` – damit konnte ich die Ursachen im echten Export finden:
- 4 Kommentar-Clips **ohne Datei** (Blöcke ohne Aufnahme, als 1-Bild-Clips geschrieben) – Premiere bricht bei Clips ohne Medien ab,
- **kein `<rate>`** an irgendeinem Clip und **kein `<sourcetrack>`** an Audio-Clips,
- Pfade **nicht URL-kodiert** (Leerzeichen, `[ENGLISCH]`), Stand-bilder im falschen Ordner (`F:/OneDrive/Videoelemente` statt Folgenordner),
- Aufnahme-Clips mit Zeitbasis 48000 (Samples) statt Bildern.
Alles behoben (Clips ohne Medien werden weggelassen und im Rohschnitt als Warnung gemeldet, Struktur wie Premiere sie exportiert, automatische Prüfung vor dem Schreiben, Regressionstest mit genau diesem Fall).
**Bitte:** Rohschnitt neu erzeugen und die neue XML importieren. Wenn Premiere wieder ablehnt: bitte die neue Datei schicken (oder das Premiere-Log), dann prüfe ich weiter.
**Antwort:**
