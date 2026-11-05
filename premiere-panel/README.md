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

## Werkzeuge (Kurzbefehle)
Unter der Statusanzeige liegen Schaltflächen, die auf die **Auswahl in der Zeitleiste** wirken (Version 0.6.2). Sie benutzen die Einstellungen der zuletzt gebauten Folge, vorher also einmal „Rohschnitt bauen“.
* **Artwork bauen:** gewähltes Bild → verschachtelte Sequenz mit Maske und Spurmaske-Key, dazu die Standardeffekte.
* **Credit setzen:** Vorlage mit Namen aus dem Bild (oder eigenem Text; ohne Auswahl am Abspielkopf). Ist ein Text-Clip gewählt, liefert das Bild darunter den Namen.
* **Effekte:** Karte, Gauß, Zoom, Pop, Kreis, Fancy-Kante … ein/aus/beide.
* **Überblendung / Ton-Blende / Länge:** Cross Dissolve 0,42 s, Gleichleistungs-Blende, Länge setzen oder bis zum Abspielkopf.
* **Szene am Abspielkopf**, **Auswahl untersuchen** (Komponenten und Wertetypen des Clips ins Protokoll).

## Bekannte Grenzen der Premiere-API
Keine Spuren hinzufügen (daher eigene Sequenz-Vorgabe), Text von Grafiken nicht per Skript setzbar (Credits: Text steht in der Vorlagendatei, siehe `vorlagen/mogrt/README.md`), keine Einstellungsebenen (Blur am Standbild),
keine Audio-„Konstante Leistung“-Blenden. Details: `docs/bridge/DESIGN.md`.

## Entwicklung
`node --test premiere-panel/test/panel.test.js` (läuft auch in `pytest`). Alle Premiere-Zugriffe laufen über das hineingereichte `ppro`-Objekt,
dadurch ist die Logik ohne Premiere testbar (`test/fake_ppro.js` erzwingt die Regeln der offiziellen Doku).
Der Plan, den das Panel ausführt, stammt aus `server/glorfindel/premiere_plan.py`; `test/fixtures/plan.json` ist ein echter Plan
(`python scripts/make_plan_fixture.py` erneuert ihn, ein Test prüft die Aktualität).
