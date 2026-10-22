# Test- und Produktreview, zweiter Durchgang (Stand 22.10.2026)

Unabhängiger zweiter Durchgang nach den Wellen 1 bis 3 (Commits bis `21d6862`). Am Repo wurde nichts geändert, nur diese Datei ist neu. `pytest` läuft grün (110 bestanden, 2 übersprungen), das sagt aber nichts über die unten gefundenen Lücken.

**Vorgehen:** Server auf Port 8799, neue Folgen S5 E1 (Referenz 40 s, zweite Quelle 38 s, 7 bis 8 Szenen, 2 Bilder, 1 Karte, 2 Aufnahmen), S5 E2 (XSS-Test) und S6 E1 (49 Szenen, Referenz, Aufnahme). Bedienung per Chromium (Playwright) in 1500, 1100, 900, 600 und 390 px, dunkel und hell, dazu REST-Aufrufe zur Gegenprüfung und Lesen von `web/js` und `server/glorfindel` zur Ursachensuche.

**Kennzeichnung:** „Belegt“ heißt: am laufenden Tool per Browser oder API nachgestellt. „Code-belegt“ heißt: aus dem Quelltext eindeutig, aber nicht am laufenden Tool ausgelöst. „Vermutung“ heißt: plausibel, nicht geprüft.

**Nicht prüfbar im Sandkasten:** Videowiedergabe im Browser (kein H.264, daher I/O-Tasten, Zeitleiste, Bildschritt, Segment-Abspielen und die beiden Player der Kontrolle nur über die gespeicherte Startposition `currentTime` gestreift), echte Spracherkennung (lokal wie ScaDS), ScaDS-LLM (Netz gesperrt), Premiere und Panel, HQ-Conform mit echten Daten, Windows und macOS (Installer, Tasten, Dateinamen), zwei echte OneDrive-Rechner, XMP-Tags (Testbilder haben keine).

Schwere: **K** kritisch (Datenverlust oder Kernfunktion unbrauchbar), **H** hoch, **M** mittel, **N** niedrig.

---

## 1. Status der Fehler aus Review 1

| Nr. | Thema | Status | Beleg |
| --- | --- | --- | --- |
| F1 (K) | Autosave verliert Eingaben | **behoben** | Kommentar in drei Stufen getippt (ALPHA, BETA, GAMMA, je 2 s Pause), danach Titel, Segmentzeit, zweiter Block, schneller Szenenwechsel, Strg+S: Alles stand jeweils im Serverstand (`GET /scenes`). Der Speichern-Handler überschreibt nur noch `report`, `problems`, `status`, `geaendert_*`. Ein Restproblem steht unter N10 (Kopfpille). |
| F2 (K) | Rohschnitt bricht bei „nicht gefunden“ ab | **behoben** | Abgleich mit 4 fehlenden Blöcken, danach Rohschnitt: läuft durch, Blöcke erscheinen als Platzhalter mit Warnung „noch keine Aufnahme zugeordnet (Schätzung)“. |
| F3 (H) | Segment hinter Episodenende | **behoben, mit Vorbehalt** | Editor-Banner „liegt hinter dem Ende der Episode (40 s)“ erscheint nach dem Speichern. Rohschnitt nennt Szene und Segment im Klartext. Er bricht aber weiterhin komplett ab, statt zu warnen. Neu: Ein Segment mit Out vor In erzeugt dagegen still einen 1-Bild-Clip (siehe N12). |
| F4 (H) | Drag-Sortieren nicht ans Ende | **behoben** | Erste Szene auf die letzte gezogen: landet am Ende. Zusätzlich funktionieren Hoch/Runter-Knöpfe und Alt+Umschalt+↑/↓. |
| F5 (H) | Reihenfolge Editor gegen Word/Rohschnitt | **teilweise behoben** | Die Liste zeigt jetzt die Ausgabenummer (Word/Rohschnitt) mit Tooltip. Die Liste ist aber nach `reihenfolge` sortiert, die Nummern laufen dann 01, 03, 02, 05, 04, 06. Das ist für Gespräche über „Szene 12“ weiterhin verwirrend (N24). Strang-Reihenfolge ist im Board per Pfeilen änderbar, wird aber nur mit „Speichern“ übernommen (N20). |
| F6 (H) | Automatisch sendet Audio an ScaDS | **behoben** | `choose_backend("auto")` liefert nur `lokal` oder `keins`. Einstellungen zeigen „Aktives Verfahren: keins“. Abgleich ohne Whisper bricht mit deutscher Anleitung ab. ScaDS nur bei ausdrücklicher Wahl. |
| F7 (M) | Abgleich mit rohem Technikfehler | **teilweise behoben** | Fehlendes Whisper: gut verständlich. ScaDS gewählt und nicht erreichbar: weiterhin `APIConnectionError: Connection error.` (N16). |
| F8 (M) | Word-Import | **überwiegend behoben** | Kaputte .docx: HTTP 400 mit deutschem Text. Unveränderter Rundlauf: keine falschen Änderungen. Vorschau nennt Titel. Hinweis zu „Überschrift 1“ steht auf der Seite. Offen: Altformat-Import mit kaputter Datei gibt noch HTTP 500; der Erfolgs-Toast zeigt `JSON.stringify` (N23). Neuer schwerer Fehler im Rückimport: N5. |
| F9 (M) | Falscher Marker-Hinweis | **behoben** | Seite nennt `⟦sz:sz_01⟧` und `⟦+bild:…⟧`. |
| F10 (M) | HTTP 500 bei Fehlerfällen | **überwiegend behoben** | Unbekannter Sprecher 400, fehlende Aufnahme und Quelle 404 mit Text, kein Referenz-Rohschnitt mit Text. Rest: Szenenerkennung ohne Referenz `KeyError: ''`, Nicht-Videodatei meldet englischen ffprobe-Text, 400 bei Sprecher enthält pydantic-Text mit URL (N23). |
| F11 (M) | Folge anlegen ungeprüft | **behoben** | Staffel 0/99999 abgelehnt („Staffel 1–99 und Folge 1–999 angeben“), Duplikat 409 „S5 E1 gibt es schon.“, Dialog schlägt nächste Folge vor, Autofokus, Enter legt an. |
| F12 (M) | Re-Import überschreibt Referenz-Rolle | **behoben** | Gleiche Datei als Screener importiert: Rolle bleibt `referenz`. Aber siehe N21 (Rolle per Auswahlfeld frei änderbar). |
| F13 (M) | Szene ohne Segment grün | **behoben** | Ampel grau, Rohschnitt-Warnung „noch kein Serienmaterial (Segment) gesetzt“. |
| F14 (M) | Zeitformat | **teilweise behoben** | `00:10.5` ergibt 10,50 s, Anzeige in Hundertstelsekunden, Aufnahme-Ansicht ebenfalls. **Offen:** `PUT /recording/block` akzeptiert In nach Out, negative Zeiten, Zeiten hinter Aufnahmeende (500 s bei 20 s) und unbekannte Szenen; Aufnahme-Ansicht und Rohschnitt nehmen das ohne Meldung an (N11). Zeitanker ohne Prüfung (N11). |
| F15 (M) | Schmale Fenster | **überwiegend behoben** | Editor ab 1100 px einspaltig, bei 900 und 600 px bedienbar, kein horizontales Scrollen. Rest: bei 390 px schrumpft das Titelfeld auf zwei Zeichen und der Inhalt wird rechts abgeschnitten; die Szenenliste zeigt unter 1100 px nur etwa eine Szene (N26). |
| F16 (N) | Kleinkram | **überwiegend behoben** | Deep-Link `…/editor?id=sz_04` geht, Dialog fokussiert, Enter bestätigt, doppeltes Bild meldet „Schon in dieser Folge“, Unterstrich im Dateinamen wird als Trenner erkannt (`ted nasmith`), Kartenid-Kollision behoben. **Offen:** Ordnername in der Bildsuche (N14), Auswahl zeigt nach Abbrechen „Folge wählen …“ statt der aktuellen Folge (N26), Credit wird klein geschrieben (`alan lee`, N), Standbildnummern überspringen nicht mehr geprüft. |

---

## 2. Neue Funktionen aus Teil 2

Zeile für Zeile gegen die Anforderungen A1 bis C6 des Hefts Teil 2.

| Anforderung | Ergebnis | Anmerkung |
| --- | --- | --- |
| A1 Aufgabenleiste | **funktioniert mit Lücken** | Liste auch nach Seitenwechsel, Fehler mit „Kopieren“. **Abbrechen wirkt bei ffmpeg-Jobs nicht** (N13). Fehlerzähler „N Fehler“ kommt nach jedem Neuladen wieder (N). |
| A2 Auto-Proxy | **funktioniert** | Nach dem Import entsteht der Proxy als Folgeauftrag. Lücke: Zuschnitt oder Rollenwechsel löschen den Proxy ohne Neubau (N15). |
| A3 Reihenfolge | **funktioniert** | Knöpfe, Tasten, Drag bis ans Ende, Ausgabenummer. Strang löschen warnt (nutzt aber natives `confirm`). |
| A4 Suche und Filter | **funktioniert** | Suche in Titel und Text, Filter „Ohne Segment“, „Zu langes Segment“, Strang, Status, Zähler „10 von 49“. |
| A4 Tastenkürzel | **teilweise** | Strg+S, Strg+Enter (fokussiert den neuen Block), Alt+1/2 (Block mit Fokus), Alt+↑/↓ (auch aus dem Textfeld), Alt+Umschalt+↑/↓ funktionieren. **Nach Alt+↓ steht der Fokus auf `body`, die Liste scrollt nicht mit** (N4). Heft nennt Strg+Alt, umgesetzt ist Alt. Auf dem Mac vermutlich problematisch (N19). J/K/L sind Sprung ±2 s und Pause. Kein Kürzel für „Neue Szene“. |
| A4 Kopfzeile, Zeitstempel, `beforeunload` | **teilweise** | „Gespeichert 14:32:10“ und Warnung beim Schließen vorhanden. Kopfzeile ist weiter dreizeilig (Titel, Auswahlfelder, Pillen). |
| A5 Dialoge | **funktioniert** | siehe F11. |
| A6 Status „veraltet“ | **teilweise** | Text, Sprecher und Segmente einer abgeglichenen Szene setzen `veraltet` (belegt, API und Browser), Übersicht und Cockpit zeigen es, Aufnahme-Ansicht markiert es. **Der Rohschnitt warnt nicht** und nutzt die alten Zeiten weiter (N9). Neuabgleich nur betroffener Szenen fehlt (der Abgleich läuft über alle, das Transkript ist aber zwischengespeichert). |
| A7 Cockpit „Als Nächstes“ | **funktioniert** | Zahlen und Sprungziele stimmen mit den Daten überein. Phasenkarten zeigen nur Häkchen, keine Zahlen („3 von 6“). |
| A8 Papierkorb/Rückgängig | **teilweise** | Toast „Rückgängig“ (12 s) funktioniert. **Szenen-ID-Wiederverwendung überschreibt den Papierkorb** (N3). Kein 30-Tage-Aufräumen, keine Oberfläche für den Papierkorb (nach 12 s nur noch per API wiederherstellbar). Ungespeicherte Eingaben der letzten 0,7 s fehlen in der wiederhergestellten Szene. |
| B1 Anker setzen (zwei Player) | **teilweise prüfbar** | Seite, Knöpfe und Speichern funktionieren, Anker landen in `quellen.json`, Protokoll schreibt jeden Anker einzeln. Videos nicht abspielbar. **Fehler in `mapTime` (N8).** Seite liegt unterhalb von Szenenprüfung am Ende der Kontrolle. |
| B2 Bildanker per Textauswahl | **funktioniert, halb** | Markierte Wörter werden als Vorgabe übernommen („ab ‚Geschichte‘“), Anker gespeichert und im Word als `⟦+bild:art_0002~Alan_Lee_-_Celebrimbor⟧` sichtbar. Weiterhin ein Dialog mit Auswahlfeld und Wortnummern, ohne Vorschaubilder; kein Popup direkt am Text. |
| B3 Aufnahme-Prüfansicht | **teilweise** | „Nur unsichere“ (5), „Nächste unsichere“, Take-Auswahl, Spontanergänzungen als Text, Zeiten in Sekunden. Es fehlen: Grenzen per Klick/Taste aus der Wellenform setzen (Klick spielt nur ab), Beschriftung der Wellenformbereiche, Übernahme von Ergänzungen in Textblöcke. Manuell gesetzte Blöcke zeigen „0 %“. |
| B4 Word | **überwiegend** | Markernamen, Schalter „Marker zeigen“, „Nach Strängen sortieren“, Schrift 14/18 pt, Importvorschau mit Titeln. Sprecher nicht farbig; die Vorschau zeigt kein Vorher/Nachher. |
| B5 Rahmenteile mit Dauer | **funktioniert** | Intro 12 s und Werbung 81 s erscheinen in `GAP` des Pakets mit exakter Länge. **Aber:** N5 (Rückimport löscht sie) und N6 (verschwinden bei gelöschter Bezugsszene). |
| B6 Bilder-Komfort/Künstler-DB | **teilweise** | „Schon in Folge“, Entfernen, Künstler-Dialog, Datenbank wächst beim Speichern des Credits (`ted nasmith` → `Ted Nasmith`). **Ordnernamen fehlen in der Suche** (`haystack` enthält nur Dateiname und Metadaten, belegt per DB-Inhalt). Tag-Chips nicht prüfbar (keine XMP-Tags im Testbestand). |
| B7 KI-Hilfen | **vorhanden, irreführend offline** | Knöpfe im Block (Namen, Bild-Ideen, Karte, Titel). Offline liefern die Endpunkte leere Ergebnisse, die Oberfläche sagt dann „Keine auffälligen Namen gefunden“ (N17). |
| C1 Karten-Editor | **funktioniert** | Marker, Pfeil (Doppelklick/Enter), Region, Kamerarahmen, Hinweise, Speichern, Blatt und Platzhalter-Clip werden gerendert (Blatt zeigt Pfeil, Region, Marker, Kamera). Mängel: Elemente nicht verschiebbar, kein Hinweis pro Element, Zeitfelder abgeschnitten, Text-Werkzeug per `prompt()`, Esc schließt den ganzen Dialog beim Zeichnen, nach dem Speichern muss der Platzhalter von Hand neu gerendert werden (kein Hinweis „veraltet“). |
| C2 Board | **teilweise** | Teilen, Verbinden, Drag auf Stränge, Anlegen funktionieren. Geteilte Karten haben kein Vorschaubild. „Neu erkennen“ verwirft alle Zuordnungen ohne Rückfrage (N18). Angelegte Szenen bekommen nur die ersten 9,5 s und den Titel „Szene ab 00:12.30“. |
| C3 Versionsschutz/Live | **teilweise, mit zwei schweren Fehlern** | 409 und Dialog funktionieren, aber N1 und N2. Live-Hinweis kommt als Toast nach 8 bis 16 s („Daten wurden extern geändert“), ohne Szene und Namen. Sperre wird nicht verlängert (N7). |
| C4 Rohschnitt-Vorschau | **funktioniert** | Zeitleiste mit 7 Spuren, Zoom, Legende, Warnungen mit „Zur Szene“, Versionsliste mit Pfad. |
| C5 Update, Selbsttest | **funktioniert** | Update-Prüfung schlägt offline still fehl, Selbsttest zeigt ffmpeg, Ordner, Name, Whisper, Schlüssel; „Verbindung testen“ vorhanden. Kein echter Erststart-Assistent. |
| C6 Panel/AE-Skelett | **vorhanden** | `premiere-panel/` und `ae-scripts/` existieren, nicht prüfbar. |

---

## 3. Neue Fehler

Reihenfolge nach Schwere.

### Hoch

**N1 (H, belegt) Versionskonflikt: Dialog erscheint in Endlosschleife**
Reproduktion: Szene im Editor öffnen, dieselbe Szene von einem anderen Nutzer ändern (hier: Szenendatei mit `geaendert_von: philipp` und neuerer Zeit), dann im Editor weitertippen. Nach 1,5 s liegen 2 Dialoge „Szene wurde inzwischen geändert“ übereinander, nach 6,5 s sind es 9, danach geht es weiter (etwa 1,3 pro Sekunde, jeweils mit einer 409-Anfrage).
Ursache (Code-belegt): Im 409-Fall bleibt `dirty = true`, das `finally` ruft `save()` erneut, der nächste Versuch scheitert wieder und öffnet einen weiteren Dialog.
Folge: Eine gutwillige Schutzfunktion wird zur Falle; der Nutzer muss neun Dialoge wegklicken, jeder trägt dieselbe Aktion.
Vorschlag: Beim 409 Autosave anhalten (`dirty` merken, aber `saving`-Schleife beenden), genau einen Dialog zeigen, danach „Aktuelle laden“ oder „Meine speichern“.

**N2 (H, belegt) Szenenwechsel und Verlassen der Ansicht umgehen den Versionsschutz**
Reproduktion: Szene A öffnen, Philipp ändert A (anderer Nutzer, spätere Zeit), im Editor in A tippen und innerhalb von 0,7 s Alt+↓ drücken (oder die Szene wechseln, bevor das Autosave läuft). Der Wechsel speichert A über `select()` ohne `?base=…`. Ergebnis im Test: Philipps Umbenennung ging verloren, der Serverstand hatte wieder den alten Titel von Danny, kein Dialog, kein Hinweis.
Ursache: Der Flush in `select()` und beim Verlassen der Ansicht ruft `PUT` ohne `base`, nur das Autosave sendet `base`. Außerdem übernimmt dieser Pfad die Serverantwort nicht (`geaendert_am` bleibt alt), und ein 409 würde dort nur als Toast gezeigt und die Eingabe stillschweigend verworfen (Code-belegt).
Vorschlag: Eine gemeinsame Speicherfunktion für alle Pfade, die immer `base` sendet und bei 409 die Szene nicht verlässt.

**N3 (H, belegt) Szenen-ID wird nach Löschen der letzten Szene wiederverwendet: Papierkorb überschrieben, falsche Szene wiederhergestellt**
Reproduktion (API): `sz_06` löschen, neue Szene anlegen (bekommt wieder `sz_06`), diese löschen, `POST /scenes/sz_06/restore`. Zurück kommt „Neu nach Löschen“, die ursprüngliche Szene „Sechs Stichpunkt“ ist weg (Datei im Papierkorb überschrieben).
Ursache (Code-belegt): `next_scene_id` nimmt max. vorhandene Nummer plus 1, der Papierkorb zählt nicht mit; `delete_scene` verschiebt auf `papierkorb/<id>.json` ohne Kollisionsprüfung.
Folge (Schlussfolgerung, nicht einzeln geprüft): Auch `abgleich.json` und Rahmenteile sind nach Szenen-ID geführt; eine neue Szene mit alter ID erbt alte Abgleichdaten.
Vorschlag: IDs nie wiederverwenden (Zähler in `projekt.json` oder Papierkorb in die Zählung), Papierkorbdateien mit Zeitstempel ablegen.

**N5 (H, belegt) Word-Rückimport löscht alle Rahmenteile samt Dauer, wenn das Dokument keine enthält**
Reproduktion: Skript exportieren, danach in der App Rahmenteile „Werbung 81 s“ und „Outro 68 s“ anlegen, die alte Datei importieren: Vorschau zeigt „0 Szenen geändert“ und keinen Hinweis; nach „Übernehmen“ ist `free-blocks` leer.
Ursache: `import_apply` ersetzt die Liste immer durch `res.free_blocks`.
Folge: Bekannte Längen gehen still verloren, die Rohschnitt-Lücken schrumpfen auf Sprechschätzung.
Vorschlag: Importierte Rahmenteile mit vorhandenen zusammenführen (nach Titel), Entfernungen nur nach Rückfrage in der Vorschau anzeigen.

**N6 (H, Code-belegt für Regex, Vermutung für Windows-Namen) Konfliktkopien mit Bindestrich im Rechnernamen werden nicht erkannt**
Test: `sz_07-LAPTOP.json` wird erkannt, `sz_08-DESKTOP-ABC123.json` und `sz_09-Dannys-PC.json` nicht (Regex erlaubt im Rechnernamen nur Buchstaben, Ziffern und Unterstrich). Windows vergibt standardmäßig Namen der Form `DESKTOP-XXXXXXX`; ob OneDrive bei Konflikten exakt `<Name>-<Rechnername>.json` bildet, ist eine Annahme aus dem Heft, nicht in der Sandbox geprüft.
Folge: Genau die Fälle, für die der Konfliktdialog gebaut wurde, bleiben unsichtbar.

### Mittel

**N4 (M, belegt) Tastaturfluss bricht nach Alt+↑/↓ ab**
Bei 49 Szenen (S6 E1): 25 × Alt+↓ stellt Szene 28 ein, die Szenenliste scrollt nicht mit (`scrollTop` bleibt 0, aktive Zeile bei y = 1607 px im 900-px-Fenster). Der Fokus steht nach dem Wechsel auf `body`, getippter Text geht ins Leere. Wer „überwiegend per Tastatur“ arbeiten will (Ziel Z1), muss nach jeder Szene mit der Maus ins Textfeld klicken. Vorschlag: `scrollIntoView` für die aktive Zeile, Fokus auf das erste leere Textfeld, Kürzel für „Neue Szene“.

**N7 (M, Code-belegt, Rechenprobe) Sperre läuft nach 120 s ab und wird nicht erneuert**
`LOCK_TTL_S = 120`, im Editor gibt es keinen Heartbeat. Nach 2 min Schreiben gilt die Szene für andere als frei (Test mit abgelaufener Datei: `acquire_lock` für Danny liefert `held: true`). Das Heft verlangt weiche Sperren „wer bearbeitet gerade“; so zeigt die Sperre nur die ersten zwei Minuten.

**N8 (M, belegt) Kontrolle: „Quelle auf Referenzzeit springen“ rechnet hinter dem letzten Anker falsch**
In `compare.js` ergibt `findIndex` bei Zeiten hinter dem letzten Anker `-1`, und `i <= 0 ? 1 : …` fängt das ab, bevor der Zweig für `-1` greift. Dann wird mit dem ersten statt dem letzten Ankerintervall extrapoliert. Test mit Ankern (2→3), (10→11), (30→28), Referenzzeit 31 s: UI springt auf 32 s, der Server (`TimeMap`) würde 28,85 s liefern. Der Knopf „Hier verknüpfen“ legt danach das falsche Paar als neuen Anker ab.

**N9 (M, Code-belegt und im Paket belegt) Rohschnitt warnt nicht bei „veraltet“**
Szenen `sz_01` und `sz_02` waren veraltet, die Paketwarnungen nennen nur fehlende Aufnahmen und Segmente. Teil 2 A6 verlangt den Hinweis auch im Rohschnitt.

**N10 (M, belegt) Kopfpille und Segmentampel aktualisieren sich nach dem Speichern nicht**
Segment auf 11 s gesetzt: Server meldet `rot`, im Editor bleibt „Serie 0:07 min“ in Grün und der Punkt neben dem Segment grün, bis man die Szene verlässt und wieder öffnet. Ursache (Code-belegt): `drawRepOnly` wird nirgends zugewiesen; `drawRepOnly?.()` läuft ins Leere. Die Liste links aktualisiert sich dagegen.

**N11 (M, belegt) Fehlende Prüfungen bei Aufnahmegrenzen und Ankern**
`PUT /recording/block` nimmt In 15 / Out 3, In −3, Out 500 (bei 20 s Aufnahme) und eine nicht existierende Szene mit Block 7 an; der Rohschnitt erzeugt daraus einen Clip mit `src_in −3` ohne Warnung. `PUT /sources/{id}/anchors` nimmt nicht monotone Paare (5→6, 20→3), doppelte Referenzzeiten und negative Zeiten an. Das UI lässt In > Out in der Aufnahme-Ansicht ebenfalls zu.

**N12 (M, belegt) Segment mit Out vor In: Rohschnitt erzeugt 1-Bild-Clip und Standbild ohne Warnung**
`src_in 30, src_out 5` ergibt einen Clip von 0,017 s plus Standbild. Der Editor-Banner „Out liegt nicht nach In“ erscheint, die Ampel bleibt aber grün, der Rohschnitt läuft ohne Hinweis durch.

**N13 (M, belegt) „Abbrechen“ in der Aufgabenleiste wirkt bei ffmpeg-Aufträgen nicht**
`POST /jobs/{id}/cancel` setzt nur ein Flag, das nur `progress()` prüft. Proxy, Import und Szenenerkennung rufen es zeitweise oder nie auf. Test: Proxy gestartet, sofort „Abbrechen“: Antwort `laeuft`, Ende nach 3,9 s mit `fertig`. Außerdem laufen nur 2 Worker, wartende Aufträge heißen ebenfalls „läuft“ (Code-belegt, mit drei Quellen plus Erkennung vermutlich spürbar).

**N14 (M, belegt) Bildsuche findet keine Ordnernamen**
Suche „eregion“ ergibt „Keine Treffer“, obwohl die Datei im Ordner `Bilder/Eregion/` liegt (Index-Feld `haystack` enthält nur Dateiname, Titel, Beschreibung, Ersteller, Tags). Teil 2 B6 nennt Ordnernamen ausdrücklich.

**N15 (M, belegt) Proxy wird nach Zuschnitt oder Rollenänderung gelöscht und nicht neu gebaut**
`PATCH /sources/{id}` entfernt den Proxy immer (auch bei gleicher Rolle). Danach meldet der Editor wieder „Für die Vorschau fehlt der Proxy“. Das widerspricht dem Ziel „Warten im Hintergrund“.

**N16 (M, belegt) Netzfehler bei ScaDS-Whisper weiter roh**
Fehlermeldung „APIConnectionError: Connection error.“ ohne Hinweis auf Netz, Schlüssel oder Umschalten auf lokal.

**N17 (M, belegt und Code-belegt) KI-Hilfen melden offline falsche „Entwarnung“**
`check-names` liefert bei fehlender Verbindung `[]`, die Oberfläche sagt „Keine auffälligen Namen gefunden“. Zusätzlich speichert `Llm.models()` eine leere Liste dauerhaft (`if self._models is None` wird nie wieder wahr), sodass „Verbindung testen“ nach wiederhergestelltem Netz erst nach Neustart oder Speichern der Einstellungen wieder funktioniert (Code-belegt, Wiederherstellung nicht getestet).

**N18 (M, belegt) Board: „Neu erkennen“ verwirft Zuordnungen und Teilungen ohne Rückfrage; Strangänderungen gehen ohne „Speichern“ verloren**
Test: Karten geteilt und zugeordnet, danach „Neu erkennen“: `board.json` enthält wieder nur den Rohvorschlag. Strang-Reihenfolge per Pfeil geändert, Seite gewechselt: Reihenfolge unverändert, keine Warnung. Geteilte Karten haben kein Vorschaubild (`thumb: ''`).

**N19 (M, Vermutung) Alt-Tastenkürzel auf dem Mac**
Option+1/2 liefert auf dem Mac Sonderzeichen in `e.key` (nicht „1“ oder „2“), Option+Pfeil verschiebt im Textfeld den Cursor wortweise und wird per `preventDefault` unterbunden. Es ist nicht getestet, Philipp nutzt laut Review 1 vermutlich einen Mac. Vorschlag: `e.code` auswerten und Tastenbelegung in der Oberfläche zeigen.

**N20 (M, belegt) Veralteter Editor überschreibt Status des Abgleichs (derselbe Nutzer)**
Szene im Editor offen (Status „neu“), Abgleich läuft (zweiter Tab, Aufnahme-Seite): Server setzt „abgeglichen“. Danach speichert der Editor den Titel: Status springt zurück auf „neu“, kein Konflikt, weil `geaendert_von` derselbe Nutzer ist. Im Zwei-Nutzer-Fall greift der 409. Vorschlag: Status und `gesprochen` nicht vom Client schreiben lassen (nur Server-Felder), oder Basis auch bei gleichem Nutzer prüfen.

**N21 (M, belegt) Rollenwechsel frei möglich: zweite Referenz oder Referenz wird zu Screener**
`PATCH` setzt `q2` auf `referenz` (zwei Referenzen), oder `q1` auf `screener`, `reference_source` bleibt `q1`. Danach widersprechen sich Rolle und Projektfeld; `compare` und `frame` behandeln Quellen nach Rolle als Identität.

**N22 (M, belegt) Rahmenteile verschwinden still, wenn ihre Bezugsszene gelöscht wird**
Rahmenteil „Werbung nach sz_05“, `sz_05` gelöscht: Word-Export und Rohschnitt enthalten die Werbung nicht mehr, keine Warnung. Nach „Wiederherstellen“ ist sie wieder da (die Daten bleiben, nur die Ausgabe verliert sie).

**N27 (M, belegt) `PUT` nach `DELETE` erweckt die Szene wieder**
`put_scene` legt unbekannte IDs neu an. Wer löscht, während ein Autosave unterwegs ist (oder ein zweiter Client noch speichert), bringt die Szene zurück. Im Browser ist das Zeitfenster eng (nicht ausgelöst), per API sofort reproduzierbar. Vorschlag: `PUT` auf nicht vorhandene ID mit 404 beantworten.

### Niedrig

- **N23 (N)** Verbliebene technische Fehlertexte: Altformat-Import mit kaputter Datei HTTP 500, Szenenerkennung ohne Referenz `KeyError: ''`, Nicht-Videodatei meldet ffprobe auf Englisch, unbekannter Sprecher liefert pydantic-Text mit Link, Erfolgs-Toast des Altformat-Imports zeigt `JSON.stringify`.
- **N24 (N)** Szenenliste mit „Ausgabenummer“ (z. B. 01, 03, 02, 05, 04) in anderer Reihenfolge ist missverständlich; es fehlt ein Schalter „Liste in Wordreihenfolge zeigen“.
- **N25 (N)** Zeitfelder der Karten-Elemente zeigen `00:00.0(`; Hinweis „Ausschnitt 20/20/40/40 %“ bricht um.
- **N26 (N)** Schmale Fenster: Bei 390 px ist das Titelfeld nur zwei Zeichen breit und der Inhalt rechts abgeschnitten, unter 1100 px zeigt die Liste knapp eine Szene (Suchfeld und Filter verbrauchen den Platz), Folgenauswahl zeigt nach Abbrechen „Folge wählen …“ statt der aktuellen Folge, Episodenauswahl wird auf „S5“ abgeschnitten.
- **N28 (N, belegt)** Barrierefreiheit: Szenenzeilen haben weder `tabindex` noch `role` (per Tastatur nicht erreichbar), Dialoge ohne `aria-modal` und Fokusfalle, Toasts ohne `aria-live`, deaktivierte Navigationseinträge bleiben per Tab erreichbar (`pointer-events: none` ersetzt kein `disabled`), Drag-Sortieren nur mit Maus (Alt+Umschalt+Pfeile ersetzen das aber). Im Hellmodus ist die Warnleiste (orange auf beige) knapp lesbar.
- **N29 (N, Code-belegt)** Jeder Dialog hängt einen Escape-Listener an `document`, der erst bei Escape entfernt wird; Escape schließt alle offenen Dialoge gleichzeitig; `onClose` kann nach dem Schließen erneut feuern.
- **N30 (N, belegt)** Native `confirm()`/`prompt()` an vier Stellen (Strang löschen, Teilen, Alle Szenen ersetzen, Karten-Text) passen nicht zur Oberfläche und sind in manchen Einbettungen blockiert.
- **N31 (N, Code-belegt)** `thumbs/` bekommt bei jedem Start neue Dateinamen, weil `hash(path)` je Prozess zufällig ist (bestätigt: Python gibt bei zwei Läufen verschiedene Werte). Der Thumbnail-Cache wird nie wiederverwendet und wächst.
- **N32 (N)** Pfad- und Id-Prüfung: Datei-Endpunkte sind sicher (siehe Abschnitt 4), aber `PUT /assets/{id}` akzeptiert die ID `..\..\evil` (auf Linux entstand eine Datei mit diesem Namen im Assets-Ordner; unter Windows würde der Backslash vermutlich Verzeichnisse verlassen, nicht geprüft), `PUT /scenes/x..y` legt Szenen mit beliebiger ID an. Der Origin-Schutz prüft den Host, nicht den Port (`Origin: http://localhost:3000` wird akzeptiert).
- **N33 (N)** Manuell gesetzte Blöcke zeigen „0 %“ in der Aufnahme-Ansicht; Wellenformbereiche ohne Beschriftung; Sprecher im Word nicht farbig; Marker im Word mit Unterstrichen statt Leerzeichen.
- **N34 (N)** Repo-Hygiene: `STATUS.md` ist veraltet (nennt Doppelansicht, Update-Check und Konfliktdialog als „in Arbeit/offen“); im Repo liegt eine versionierte Datei `MEMORY_PLACEHOLDER_NOOP`.

---

## 4. Sicherheit (belegt)

- **XSS:** In allen Feldern HTML mit `onerror` abgelegt (Folgentitel, Strangname, Szenentitel und -text, Rahmenteil, Kartentitel/-hinweis/-label, Asset-Titel/-Credit/-Link, Künstler-DB). 11 Ansichten und beide Dialoge (Künstler, Zuordnung) geöffnet: kein eingefügtes Element, `window.__x` bleibt unbelegt. Im Code kein `innerHTML`; Links zeigen nur auf die Update-URL aus der GitHub-Antwort (ohne Schemaprüfung, sehr geringes Risiko).
- **Pfad-Traversal:** `asset-file`, `images/thumb`, `maps/thumb` lehnen `../`, absolute Pfade, kodierte Schrägstriche und einen Symlink aus dem OneDrive-Ordner heraus ab (400). `thumb/{name}` und `compare-img/{name}` mit `..%2f` ergeben 404. Szenen-, Karten- und Asset-IDs mit `%2f` ergeben 404 (Router), Backslash siehe N32.
- **Host/Origin:** Fremder Host, Host mit Port, `localhost.evil.com` ergeben 403; Schreibzugriff mit fremdem oder `null`-Origin 403. Zugriff ohne Origin (curl) erlaubt (gewollt). Port wird nicht geprüft (N32). `GET /api/fs` listet beliebige lokale Ordner, bleibt aber hinter dem Host-Schutz (nur lokal).

---

## 5. Lücken gegenüber den Heften

**Teil 1**
- Premiere-Panel und AE-Credit-Skript sind nur Skelette (nicht prüfbar). Die FCP-XML ist der einzige in der Sandbox prüfbare Weg; die Vorlagenwerte stimmen ohne Premiere nicht verifizierbar mit dem echten Schnitt überein.
- 5.2: Filmstreifen ohne Thumbnails nach Teilung, kein Mehrfachauswählen, keine Tonpausen/Schnittdichte als Entscheidungshilfe. Szenen aus dem Board bekommen nur 9,5 s Segment und Titel „Szene ab …“.
- 5.3: Kein formatierter Kommentar-Editor („einfache Formatierung“), keine Gesamtlaufzeit und kein Serienanteil im Editor (nur Übersicht), J/K/L nur als Sprung.
- 5.4: Konturfarbe ohne Vorschau der Rahmenanimation und ohne Pipette, Bildausschnitt und Position fehlen.
- 5.5: Kein Hinweis pro Kartenelement, Elemente nicht verschiebbar, Platzhalter-Neurendern von Hand.
- 5.7: Retake-Umschaltung nur über Auswahlfeld je Block, kein globaler Schalter; Spontanergänzungen nicht übernehmbar; Sprecherfilter für den Rohschnitt hat keinen Schalter (API `speakers`).
- 7: Live-Sync nur als Toast; Sperre ohne Verlängerung (N7); Konflikterkennung unvollständig (N6); Versionsschutz mit Lücken (N1, N2, N20).
- 8: Kein Erststart-Assistent (nur Selbsttest in den Einstellungen).
- Audio-Fingerabdruck zum Wiederfinden verschobener Quellen: Feld vorhanden, keine Oberfläche (nicht geprüft).

**Teil 2**
- A1: Abbrechen wirkungslos bei ffmpeg-Jobs (N13). A4: Kopfzeile nicht einzeilig; Alt statt Strg+Alt; Fokus nach Szenenwechsel (N4). A6: Rohschnitt-Hinweis und Teilabgleich fehlen (N9). A7: Phasenkarten ohne Zahlen. A8: Papierkorb-Oberfläche und 30-Tage-Aufräumen fehlen, ID-Kollision (N3).
- B2: weiterhin Dialog mit Wortnummern; B3: Grenzen per Klick/Taste aus der Wellenform fehlen (Z3 für Aufnahme nicht erreicht); B4: Sprecherfarbe; B6: Ordnernamen (N14); B7: Ehrlichkeit bei fehlendem Netz (N17).
- C2: Thumbnails nach Teilung, Rückfrage bei „Neu erkennen“ (N18). C3: Live-Hinweis ohne Namen/Szene. C5: Erststart-Assistent.

---

## 6. Zeitgewinn: der Ablauf einer Folge mit 49 Szenen

Gedanklicher und praktischer Durchlauf (S6 E1 mit 49 Szenen, Abruf unter 0,1 s je Liste; Tippen 50 Zeichen in 0,66 s, keine Verzögerung spürbar). Die Technik trägt, die Reibung liegt in der Bedienung.

1. **Vorbereiten (Maurice/Philipp):** Import plus Auto-Proxy sind gut. Die Wartezeit der Proxys und der Szenenerkennung (Minuten) ist die einzige Phase, in der das Team wirklich wartet; mit 2 Workern und wirkungslosem Abbrechen (N13) bleibt die Aufgabenleiste ehrlich, aber nicht steuerbar.
2. **Board:** 49 Vorschläge ziehen, teilen, anlegen. Reibung: geteilte Karten ohne Bild, kein Mehrfachziehen, angelegte Szenen mit Titel „Szene ab …“ und nur 9,5 s Segment, danach muss jede Montage im Editor von Hand neu gesetzt werden.
3. **Skript schreiben (der häufigste Weg):** Suche und Filter sind gut. Es bleiben die größten Brüche des Alltags:
   - Nach jedem Szenenwechsel per Tastatur steht kein Fokus im Textfeld, die Liste scrollt nicht (N4). Bei 49 Szenen sind das 49 Mausklicks und Scrollbewegungen mehr.
   - Bilder und Karten zuordnen: für jede Einblendung ein Dialog mit Auswahlfeld ohne Vorschaubild. Bei rund 3 bis 5 Einblendungen je Szene ist das der größte verbleibende Zeitfresser.
   - Zeitcodes tippen bleibt im Editor (Segmente) und in der Aufnahme-Prüfung (Grenzen).
   - Ein Autosave-Konflikt bei zwei Nutzern ist riskant (N1, N2, N20), solange Philipp und Maurice zeitgleich in derselben Folge arbeiten.
4. **Word-Runde:** Export und Vorschau sind brauchbar, aber ein Import älterer Dateien löscht Rahmenteile (N5), und die Vorschau zeigt nur Titel, nicht was sich geändert hat.
5. **Einsprechen und Abgleich:** Abgleich und Prüfansicht („nur unsichere“) sparen viel. Bei jedem Neuabgleich laufen alle Szenen, ein Teilabgleich nur der „veraltet“-Szenen fehlt. Grenzen müssen getippt werden.
6. **Rohschnitt:** Vorschau und Warnungen mit „Zur Szene“ helfen. Es fehlt der Hinweis auf veraltete Szenen (N9), und ein einzelnes Segment hinter dem Ende stoppt den Lauf (bei 49 Szenen ärgerlich, wenn die Meldung nur die erste Szene nennt).

---

## 7. Verbesserungsvorschläge nach Nutzen und Aufwand

### A. Sofort (hoher Nutzen, kleiner Aufwand)
1. **Autosave-Schleife und Flush korrigieren (N1, N2, N20, N27):** Eine Speicherfunktion für alle Pfade mit `base`, bei 409 Autosave anhalten und genau einen Dialog zeigen, `PUT` auf unbekannte ID mit 404 beantworten, Status und `gesprochen` serverseitig behalten.
2. **IDs nie wiederverwenden (N3)** und Papierkorbdateien mit Zeitstempel ablegen.
3. **Import-Schutz für Rahmenteile (N5):** zusammenführen, nicht ersetzen, Entfernungen in der Vorschau nennen.
4. **Konfliktdatei-Muster erweitern (N6)** (mehrere Bindestriche, Leerzeichen, Klammern-Zähler wie „sz_07-DESKTOP-ABC (1).json“), mit Test.
5. **Tastaturfluss (N4):** aktive Zeile sichtbar halten, Fokus ins erste leere Textfeld, Kürzel für „Neue Szene“, `e.code` statt `e.key` (N19).
6. **Kopfpille/Ampel sofort aktualisieren (N10):** `drawRepOnly` zuweisen.
7. **Validierung nachziehen (N11, N12, N21):** Aufnahmegrenzen und Anker prüfen, Segmente mit Out vor In im Rohschnitt als Warnung, Rolle nur ändern, wenn eindeutig.
8. **Rohschnitt-Hinweis „veraltet“ (N9)** und Warnung bei Rahmenteilen ohne Bezugsszene (N22).

### B. Hoher Nutzen, mittlerer Aufwand
9. **Bild-/Kartenzuordnung im Fließtext:** Im Kommentarfeld `@` oder `[[` tippen, Autovervollständigung aus den Folgen-Bildern (mit Vorschaubild), setzt den Anker an die Stelle. Entspricht den Wordmarkern, ersetzt den Wortnummern-Dialog und spart pro Einblendung mehrere Klicks.
10. **Aufnahme-Prüfansicht bedienbar machen:** Taste „I/O“ für Beginn/Ende an der Abspielposition, Ziehen der Ränder in der Wellenform, Beschriftung der Bereiche, „Weiter zur nächsten Unsicheren“ per Taste (Z3).
11. **Sperre mit Heartbeat (N7)** und Live-Hinweis mit Namen und Szene („Philipp hat Szene 12 geändert – neu laden?“), `LOCK_TTL` gegen Pausen abwägen.
12. **Abbrechen wirklich abbrechen (N13):** ffmpeg-Prozess beenden (Subprozess-Handle im Job), Warteschlange sichtbar als „wartet“.
13. **Proxy automatisch neu bauen (N15)** nach Zuschnitt/Rollenwechsel.
14. **KI ehrlich (N17):** Fehlerzustand statt leerer Ergebnisse, „Alle Namen prüfen“ für die ganze Folge mit einem Klick, Modellliste nicht dauerhaft leer cachen.
15. **Board:** Rückfrage bei „Neu erkennen“, Strang-Änderungen autospeichern, Thumbnails für geteilte Karten über `/frame`, Mehrfachauswahl, Titel aus der Zeit nach erstem Kommentar statt „Szene ab …“.
16. **Papierkorb-Ansicht** im Protokoll (Wiederherstellen, 30-Tage-Aufräumen).

### C. Nutzen mittel
17. Ordnernamen und Pfade in die Bildsuche (N14), Tag-Chips testen, Credit in „Vorname Nachname“ umwandeln.
18. Importvorschau mit Vorher/Nachher je Szene, Wordreihenfolge-Schalter für die Liste (N24), Sprecherfarben im Word.
19. Phasenkarten mit Zahlen („31 von 49 Szenen mit Segment“), Gesamtlaufzeit und Serienanteil im Editor.
20. Kartenelemente verschiebbar, Hinweis je Element, automatisches Neurendern oder Hinweis „Platzhalter veraltet“.
21. Barrierefreiheit (N28): fokussierbare Szenenzeilen, `aria-live` für Toasts, Fokusfalle in Dialogen, `disabled` für Navigation.
22. Kleinkram: natives `confirm`/`prompt` ersetzen (N30), `thumbs`-Namen stabilisieren (N31), ID-Muster prüfen (N32), Fehlertexte (N23), STATUS.md und Placeholder-Datei (N34).

---

## Anhang: Testprotokoll in Kürze

| Bereich | Ergebnis |
| --- | --- |
| Regression F1 bis F16 | siehe Abschnitt 1; 9 voll behoben (F1, F2, F3 mit Vorbehalt, F4, F6, F9, F11, F12, F13), 7 überwiegend oder teilweise (F5, F7, F8, F10, F14, F15, F16) |
| Autosave, Szenenwechsel, Strg+S, Löschen/Rückgängig | funktioniert; N2 (Flush ohne `base`), N27 (PUT nach DELETE), N3 (ID) |
| Tastenkürzel Alt+↑/↓, Strg+Enter, Alt+1/2, Strg+S, Alt+Umschalt+↑/↓ | funktionieren; N4 (Fokus, Scrollen), N19 (Mac, Vermutung) |
| Suche/Filter (49 Szenen) | funktioniert |
| Versionsschutz 409 | Dialog erscheint, aber Endlosschleife (N1) |
| Cockpit, Status veraltet | funktioniert; Rohschnitt ignoriert veraltet (N9) |
| Aufgabenleiste, Auto-Proxy | funktioniert; Abbrechen wirkungslos (N13) |
| Kontrolle, Anker | Seite funktioniert, Berechnungsfehler (N8), keine Validierung (N11) |
| Aufnahme-Prüfansicht | funktioniert; Grenzen nur tippbar, keine Validierung |
| Word, Rahmenteile | funktioniert; N5, N22 |
| Bilder, Künstler-DB | funktioniert; N14 |
| Karten-Editor | funktioniert, Blatt und Clip gerendert |
| Board | Drag, Teilen, Verbinden, Anlegen funktionieren; N18 |
| Rohschnitt-Vorschau, Update, Selbsttest | funktioniert |
| XSS, Traversal, Origin/Host | sicher (Abschnitt 4), Kleinigkeiten N32 |
| Hell-Design, 1100 bis 600 px | in Ordnung; 390 px und Barrierefreiheit siehe N26, N28 |
| `pytest` | 110 bestanden, 2 übersprungen |
