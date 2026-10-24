# Glorfindel Bridge (Premiere-Panel)

Verbindet Premiere Pro mit der Glorfindel-App (lokal, `127.0.0.1`). Die App baut damit den Rohschnitt direkt im Premiere-Projekt
und tauscht später Proxy gegen HQ, ohne dass Effekte, Animationen oder Handarbeit verloren gehen.
Getestet gegen die Premiere-Typdeklarationen 26.5 (Version 26.5.2 vorhanden); die Logik hat Tests gegen eine strenge Nachbildung der API.
**Noch nicht in einem echten Premiere gelaufen** – dafür gibt es den Selbsttest (siehe unten).

## Installation (einmalig)
1. In der App: **Premiere → „Panel einrichten“**. Der Creative-Cloud-Installer fragt nach; bestätigen.
2. Premiere neu starten. **Fenster → Erweiterungen → „Glorfindel Bridge“** öffnen und offen lassen.
3. In der App erscheint „Mit Premiere verbunden“.

Klappt der Installer nicht: **Adobe UXP Developer Tool** → „Add Plugin“ → `premiere-panel/manifest.json` → „Load“ (danach „Debug“ nicht nötig).

## Benutzen
* **Rohschnitt bauen** (App → Premiere): legt in deinem geöffneten Projekt eine neue Sequenz „Rohschnitt … vN“ an. Vorhandenes bleibt unberührt.
* **Auf HQ umschalten / zurück**: tauscht nur die Datei der Episoden-Sequenz und ersetzt die Standbilder am gleichen Ort.
* **Selbsttest**: legt ein Test-Fach und eine Test-Sequenz an, prüft Effekte, Farbe, Keyframes und räumt alles auf. Vor dem ersten Bau einmal ausführen.
* **Aktive Sequenz auslesen**: zeigt Spuren, Clips und Effekte mit Parametern – nützlich, um den Rohschnitt mit dem Ursprungsschnitt zu vergleichen.

## Bekannte Grenzen der Premiere-API
Keine Spuren hinzufügen (daher eigene Sequenz-Vorgabe), keine Textgrafiken (Credits als PNG), keine Einstellungsebenen (Blur am Standbild),
keine Audio-„Konstante Leistung“-Blenden. Details: `docs/bridge/DESIGN.md`.

## Entwicklung
`node --test premiere-panel/test/panel.test.js` (läuft auch in `pytest`). Alle Premiere-Zugriffe laufen über das hineingereichte `ppro`-Objekt,
dadurch ist die Logik ohne Premiere testbar (`test/fake_ppro.js` erzwingt die Regeln der offiziellen Doku).
Der Plan, den das Panel ausführt, stammt aus `server/glorfindel/premiere_plan.py`; `test/fixtures/plan.json` ist ein echter Plan
(`python scripts/make_plan_fixture.py` erneuert ihn, ein Test prüft die Aktualität).
