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
Offen: MOGRT-Credits, Audio-Blenden, optional verschachtelte Artwork-Sequenzen, Auto-Anker für HQ.


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
