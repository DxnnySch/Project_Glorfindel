# Stand (wird laufend aktualisiert)

## Fertig und getestet (pytest)
Store/Sperren/Konflikte, Zeitmodell, Medien (Probe/Proxy/Stills/Wellenform), HQ-Conform + Kontrollansicht,
Szenen/Längenampel, Word-Export/-Import (inkl. Stichpunkte, freie Blöcke), Altformat-Import (echtes S2-E7-Skript),
Aufnahme-Abgleich Text + Stichpunkte (lokal Whisper getestet an echter Aufnahme; ScaDS-Whisper als Option),
Rohschnitt-Paket + FCP-XML, Effektrezepte aus .prfpset, Bildindex/XMP/Credits/Konturfarbe, SSRF-sicherer Web-Import,
Kartenproxy, LLM (ScaDS live geprüft), REST-API.

## Weboberfläche (neu, im Browser mit synthetischen Daten geprüft)
web/js: Übersicht, Quellen (Import/Proxy/Anker/Zuschnitt), Strang-Board, Szenen-Editor (Player mit I/O, Segmente, Stichpunkte, Autosave, Sperren, Drag-Sortierung), Word-Skript, Bilder, Karten, Aufnahme (Wellenform, Zeiten korrigieren, „Als Skript“), Rohschnitt, Einstellungen. Installer/Startskripte/README vorhanden.

## Teil 2 (Zeitgewinn & Bedienung) – umgesetzt
Siehe `Projektheft Teil 2 - Zeitgewinn und Bedienung.md`, Reviews in `docs/review/`. Welle 1–3 fertig: Aufgabenleiste, Auto-Proxy, Papierkorb/Rückgängig, Status „veraltet“, Versionsschutz (409), Cockpit, Editor-Tempo (Suche/Filter/Kürzel), Zwei-Player-Anker, Textauswahl-Anker, KI-Hilfen, Aufnahme-Prüfansicht (Takes), Rahmenteile mit Dauer, Word-Marker mit Namen, Künstler-Datenbank, Karten-Editor, Board mit Drag&Drop, Rohschnitt-Vorschau, Update-Check, Selbsttest. Fixes aus beiden Reviews eingearbeitet (111 Tests grün).

## Teil 3 (Segment-Workflow) – umgesetzt
Siehe `Projektheft Teil 3 - Segment-Workflow.md`. Kommentare gehören zu Segmenten (Segment-Notiz + Dialog der Episode), Dialog-Transkription der Episode, Szenen-Editor neu (Dialog zum Markieren, Zeitleiste mit Kommentarmarken, Bild-/Karten-Picker mit Vorschaubildern, farbige Wortbereiche), Board mit Mehrfachauswahl und Player, Ablauf-Ansicht (Stränge/Szenen frei sortieren), Sprecherskript, Kartenfarben und Animationsvorschau, gemerkter Ansichtszustand, Premiere-XML überarbeitet (Ursachen aus dem echten Export behoben).

## Offen
- Review 2, noch nicht umgesetzt: Rohschnitt warnt nicht bei „veraltet“; Papierkorb ohne Übersicht in der UI; Aufnahme-Grenzen nur tippbar (Wellenform-Ziehen); `@`-Autovervollständigung für Bilder im Text; ffmpeg-Jobs nicht abbrechbar; Zeitfelder ohne Bereichsprüfung; ScaDS-Netzfehler beim Abgleich noch technisch formuliert.
- Premiere-UXP-Panel und AE-Skript sind nur Skelette (nicht testbar ohne Premiere), End-to-End mit echter S2-E7-Konformierung.


## Premiere-Bridge (Stand 2026-10-24)
Fertig und getestet (Python + Node, strenge API-Nachbildung): Hub/WebSocket mit Token- und Origin-Schutz, Plan-Builder (Rezepte aus dem echten S2-E7-Schnitt),
konforme Referenz, Standbilder aus derselben Datei auf dem Episodenraster, Credit-PNGs, Sequenz-Vorgabe mit 14 V/16 A, Panel (Bau, Effekte, Marker, Tausch,
Auslesen, Selbsttest), Premiere-Ansicht in der Oberfläche, HQ-Tausch mit Rückweg, Projektleser für .prproj.
**Nicht in echtem Premiere gelaufen** (siehe FRAGEN F10): Parameternamen/Farbformat/Keyframe-Zeitbezug sind per Selbsttest zu bestätigen.
Offen: Auto-Anker für HQ.


## Premiere-Parität (Stand 2026-11-03, Panel 0.5.1)
Gemessen am echten Schnitt (`scripts/parity_report.py`), Spec `docs/superpowers/specs/2026-11-03-premiere-paritaet-design.md`, Vorgehen: Skill `premiere-paritaet`.
Umgesetzt und gegen die Premiere-Nachbildung getestet (237 pytest, 24 Node-Tests):
- **Cross Dissolve 0,42 s** am Anfang/Ende von Artwork, Credits und Karten; Serienclips an den Szenenkanten (Regeln in `premiere_rezepte.json → uebergaenge`, gemessen: 562 im Ursprungsschnitt).
- **Serienton**: Gleichleistungs-Blenden (1 s an Szenenkanten, 0,2 s an harten Schnitten) als Pegel-Keyframes – die Premiere-API kennt keine Audioübergänge (Ersatz, weiter frei editierbar).
- **Credits als editierbarer Text** über Vorlagen in `vorlagen/mogrt/` (siehe README dort), sonst PNG.

**Abnahme in Premiere (bitte einmal ausführen, Claude kann Premiere nicht starten):**
1. Panel neu laden (0.5.1), **Selbsttest** laufen lassen. Zu prüfen: Schritt „Übergänge (Cross Dissolve)“ ok (`findings.crossDissolve`, `audioTransitions` zeigt, ob die API doch Audioübergänge anbietet);
   Schritt „Text-Vorlage (MOGRT)“ ok (`mogrtTextIsJson`: Textformat des Parameters).
2. `Credit Amazon/Artwork.mogrt` nach `vorlagen/mogrt/` exportieren (README dort), neu bauen: Credits müssen Textclips sein, Text änderbar.
3. Am Serienton A4: Pegel-Keyframes sichtbar; Pegel-Werte plausibel (Panel erkennt linear/dB selbst). Falls hörbar falsch: `findings` aus dem Selbsttest an Claude geben.
4. Der Bau-Bericht listet Warnungen („Übergang … nicht gesetzt“, „Credit-Vorlage … nicht verwendet“) – dann greift der Rückfall (Deckkraft-Blende bzw. PNG).

**Noch offen (aus dem Paritätsbericht):** Zwischenüberschriften (V11, Vorlage `Zwischenüberschriften Serienvideo.mogrt` existiert), Bauchbinde/Instagram-Popups (V12), Mitglieder-Grafiken V5–V7,
Musik (A10/A11, nicht im Plan), Einstellungsebenen für alle Blur-Stellen (V2: 46), 1:1-Vergleich mit einem echt von der Bridge gebauten Projekt (`--built`).


## Abgleich Premiere → App (Stand 2026-11-04)
- Button „Aus Premiere einlesen“ (Bereich „Änderungen aus Premiere“): liest die gebaute Sequenz (`sequence.dump`), ordnet Serienclips über den Namen „sz_xx Segment n“ den Segmenten zu und übernimmt geänderte/geteilte Ein-/Aus-Punkte. Gelöschte Clips werden nur gemeldet. Module: `premiere_sync`, `premiere_ops.read_from_premiere/sync_state/refresh_stills`.
- Anzeige „Tausch nötig“: Vergleich der Standbild-Zeiten des Modells mit denen beim Bau; „Standbilder in Premiere tauschen“ erzeugt neue Dateien (`1_r1.png`) und tauscht sie über `media.swap`.
- Offen/ungeprüft in echtem Premiere: ob `getInPoint/getOutPoint` der Clips die Quellzeit liefern (Annahme: ja). Bauten vor dieser Version haben Clipnamen ohne Nummer (Zuordnung dann nach Reihenfolge).
- Verschobene Clips (nur Start geändert) und Änderungen an Bildern/Credits werden nicht eingelesen.

## Editierbare Credits: Recherche (2026-11-04)
- Premiere 26.5.2 liefert für eingesetzte Vorlagen nur Deckkraft/Bewegung/Vektorbewegung; der Textparameter ist per UXP nicht erreichbar (auch Adobes „Basic Title“ nicht). Forum: `MOGRT Parameters in UXP availabilty`, `Setting MOGRT text parameters in Premiere UXP?`.
- Adobe hat die Schnittstelle für Premiere **27.0 (Beta)** angekündigt: `AE.ADBE Capsule`-Komponente, Wert `MogrtText` (`getText`/`setText`), zurück per `createKeyframe` + `createSetValueAction` (Typen `adobe/premierepro-types` v27.0.0-beta.22, Beispiel `uxp-premiere-pro-samples` PR #100).
- Die Bridge unterstützt diesen Weg (Panel 0.5.7); mit 26.x fallen Credits auf PNG zurück. Ungeprüft in echtem Premiere 27.0.
- Verworfen: Umweg über Änderung der .mogrt-Datei (internes Binärformat, keine Quellen, nicht prüfbar); ExtendScript aus UXP (nicht aufrufbar).
- **Gemessen in Premiere 27.1.0 Beta (Selbsttest und UXP-Konsole, 2026-11-04):** Die Klassen `MogrtText` und `MogrtComment` gibt es, aber bei eingesetzten Grafiken (eigene Vorlagen „Credit Amazon v2“/„Credit Artwork v2“ und Adobes „Basic Title“) liefert der Textparameter `Text [AE.ADBE Text]/Quelltext` den Wert `null`, `getKeyframePtr` wirft „Illegal Parameter type“, `createKeyframe` verlangt „ArbData“ (diese Klasse gibt es nicht). Keine `AE.ADBE Capsule`-Komponente, kein Zugriff auf Vorlagenfelder am Clip: der Text ist per Skript weder lesbar noch setzbar.
- **Umgesetzt statt Skript: der Text steht in der Datei** (`server/glorfindel/mogrt_text.py`, von Danny in Premiere bestätigt: „funktioniert perfekt“). Eine .mogrt ist ein ZIP mit `definition.json` (freigegebenes Textfeld, Typ 6) und `project.prgraphic` (ZIP mit gzip-komprimiertem Projekt; darin der Parameter „Quelltext“ als FlatBuffer-Block). Der Server schreibt je Credit eine Kopie mit dem richtigen Text (neuer String ans Blockende, ein Verweis umgebogen, Kopf angepasst, `capsuleID` erneuert; die Quell-ID in `sourceInfoLocalized` bleibt, sie steht auch im Projekt; siehe „Credits ohne Text“ unten). Das Panel setzt die fertige Datei nur ein (`c.mogrt.baked`). Funktioniert mit jeder Premiere-Version, die die Vorlage importiert (kein Beta nötig). Cache: `…/premiere/mogrt/`.


## Credits ohne Text – Ursache und Abhilfe (Panel 0.6.2, 2026-11-05)
Auswertung von `Test8/9/10.prproj` (je 13 Credits, 1–2 mit Text):
- Ein Credit **mit** Text hat in der Komponentenkette des Clips `Bewegung` + `Text` [AE.ADBE Text] mit „Quelltext“ und den Quellbereich der Vorlage (3099,2–3142,45 s); ein Credit **ohne** Text hat eine leere Kette und einen frischen Quellbereich ab 3600 s. Beide verweisen auf je einen eigenen Masterclip „Grafik“ (Medium `1196574294`), Name und Mogrt-Kennung stimmen.
- Ein Rest des Credits @25,07 (Test10) zeigt, dass er beim nächsten Einsetzen noch **leer** war und die Grafik erst danach bekam: Premiere lädt die Grafik nach `insertMogrtFromPath` nachträglich; meist kam sie nie an. Dieselbe Datei (`Credit Amazon v2 490e484fe5c8.mogrt`) ergab Credits mit und ohne Text – an den Kennungen lag es nicht.
- Der Cache-Schlüssel der Text-Vorlagen enthielt die Formatkennung nicht: Test8–Test10 liefen alle mit den Dateien von 09:30 (nur `capsuleID` neu), die Kennungs-Umschreibung erreichte Premiere nie. Jetzt im Schlüssel; die Umschreibung ist aus (`FRESH_SOURCE_ID`).
- `insertMogrtFromPath` **fügt ein** (spätere Clips der Spur rücken um die Vorlagenlänge, 43,2 s), ein Clip an der Einfügestelle wird geteilt. Auf 4 Stellen gerundete Credit-Zeiten ließen hauchdünne Reste stehen; der Plan behält jetzt die genauen Bildzeiten.
- **Abhilfe:** Das Panel wartet nach jedem Einsetzen auf die Text-Komponente (bis 12 s, `calibration.mogrt_wait_ms`), ändert den Clip vorher nicht, setzt bei Misserfolg einmal neu ein, sonst PNG mit Hinweis (nach drei Fehlschlägen in Folge alle weiteren als PNG); Schlussprüfung aller Credits am Ende. Das Werkzeug „Credit setzen“ räumt nach dem Einfügen wie beim Überschreiben auf (Clips im Bereich ersetzt/gekürzt, spätere zurückgeschoben) – `createMoveAction` mit negativer Zeit und `createSetStartAction` sind in Premiere **ungeprüft**.
- Robustheit: Wiederholung bei „no longer valid“ und leeren Listeneinträgen („reading 'guid'“) für Länge, Name, Bewegung, Deckkraft, Übergänge, Ton-Blende, Effekte; eine Artwork-Sequenz, deren Bewegung/Spurmaske scheitert, kommt trotzdem in den Schnitt (Hinweis). „Artwork bauen“ aktiviert die Hauptsequenz wieder, überschreibt das Bild mit der Sequenz und prüft das Ergebnis.

## Panel-Werkzeuge (Kurzbefehle, Panel 0.6.0, Stand 2026-11-04)
Entwurf: `docs/superpowers/specs/2026-11-04-premiere-werkzeuge-design.md`. Das Panel hat eine Werkzeugleiste, die auf die **Auswahl in der Zeitleiste** wirkt; fachliche Entscheidungen trifft der Server (`premiere_tools.py`, Anfragen per `rpc` über die Bridge), das Panel führt Premiere-Grundoperationen aus (`lib/tools.js`).
- **Artwork bauen:** Bild → verschachtelte Sequenz (Bild V3, Maske V5, Spurmaske-Key) an Stelle des Bildes, Standardeffekte der Einstellungen.
- **Credit setzen:** Name aus Bilddatei bzw. Künstlerdatenbank (oder dem Clip unter einem gewählten Text-Clip), Vorlage mit festem Text, Länge wie der Clip, Cross Dissolve; oder eigener Text am Abspielkopf. Arten Amazon/Künstler/Musik (Spuren V9/V10/V11).
- **Effekte:** Karte, Gauß, Zoom schnell/langsam, Pop, Kreis, Fancy-Kante, Transformieren, Von rechts, Schlagschatten – ein/aus/beide, Zeiten relativ zum Clip (Rezepte aus den .prfpset-Vorgaben).
- **Überblendung 0,42 s** (Anfang/Ende/beide), **Ton-Blende** (Gleichleistung), **Länge setzen** (feste Länge oder bis zum Abspielkopf), **Szene am Abspielkopf**, **Auswahl untersuchen** (Fehlersuche).
- In der App (Ansicht Premiere): „Szene in Premiere zeigen“ setzt den Abspielkopf an den Anfang der Szene.
- Die Werkzeuge nutzen die Einstellungen der zuletzt gebauten Folge (`bridge_context.json`); davor ist ein Bau nötig. Entscheidungen und Standardwerte: `FRAGEN.md` F12.
- **Ungeprüft in echtem Premiere** (nur gegen die strenge Nachbildung getestet, 46 Node- und die Python-Tests): `Sequence.getSelection()`, `getPlayerPosition/setPlayerPosition`, das Ersetzen eines Bildes durch die Artwork-Sequenz (Clip entfernen ohne Lücke, Sequenz setzen) und die Erkennung Video/Ton am Clip. Erster Test: ein Standbild wählen → „Artwork bauen“; „Auswahl untersuchen“ zeigt bei Problemen die Komponenten des Clips.

## Ton der Referenz (2026-11-04)
Premiere 27.1 zeigt E-AC-3 in MP4 ohne Wellenform und spielt keinen Ton (auch nicht das unveränderte Dolby-Original). Die Referenz bekommt den Ton der HQ-Datei jetzt als **AAC-Stereo** (`…_Referenz_CFR_TonAAC.mp4`).
**Folge und Lösung:** Premiere tauscht Medien nur gegen Dateien mit gleichem Tonformat. Beim ersten „Auf HQ umschalten“ legt die App deshalb eine Kopie der HQ-Datei mit unverändertem Bild und AAC-Ton an (`…_AAC.mp4` im Cache der Folge, `premiere_ops.hq_for_premiere`, nur Umpacken, einmal je HQ-Datei) und tauscht gegen diese; „Zurück auf Proxy“ nimmt dieselbe Datei als Ausgangspunkt (`hq_pr` im Zustand). Das Original bleibt unberührt.
