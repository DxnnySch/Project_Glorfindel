# Test- und Produktreview Projekt Glorfindel (Stand 22.10.2026)

Unabhängiger Durchgang als Nutzer: Server auf Port 8799 mit Testdaten, Bedienung per Browser (Chromium, Playwright) und per REST-API, dazu Lesen von `web/js` und `server/glorfindel` zur Ursachensuche. Gegenprüfung gegen `Projektheft Folgenbesprechungs-Tool.md`. Am Repo wurde nichts geändert, nur diese Datei ist neu.

**Testumfang:** neue Folge S3 E1 (640x360-Referenz, 40 s), 6 Szenen (Text und Stichpunkte, 2 Sprecher, Montage mit 2 Segmenten), 3 Bilder, 1 Karte, Word-Export und -Import (inkl. freiem Block), Aufnahme (Sinuston-WAV, Transkript von Hand in den Cache geschrieben, weil kein Whisper und kein ScaDS im Sandkasten erreichbar), Alignment, Rohschnitt (JSON + FCP-XML, wohlgeformt), Hell-Design, Fensterbreiten 1500/900/600/390, Tastatur, Fehlerfälle.

**Nicht testbar hier:** Videowiedergabe im Browser (kein H.264), echte Spracherkennung (lokal wie ScaDS), Premiere, HQ-Conform mit echten Daten, Windows/macOS-Installer, OneDrive-Synchronisierung mit zwei Rechnern. Aussagen dazu sind unten als „nicht geprüft“ markiert.

Schwere: **K** = kritisch (Datenverlust / Kernfunktion unbrauchbar), **H** = hoch, **M** = mittel, **N** = niedrig.

---

## 1. Gefundene Fehler

### F1 (K) Szenen-Editor verliert Eingaben nach dem ersten Autosave, obwohl „Gespeichert“ angezeigt wird
Das ist der wichtigste Fund: Das Kernstück (Skript schreiben) speichert nur die erste Änderung einer Szene zuverlässig.

Reproduktion (reproduziert in drei Varianten, jeweils per Browser und Gegenprüfung über die API):
1. Szenen öffnen, eine Szene wählen, in das Kommentarfeld tippen, 2 s warten (Anzeige „Gespeichert“), weitertippen, 2 s warten.
2. API-Stand prüfen (`GET /api/ep/3/1/scenes`): Es steht nur der Text der ersten Speicherung drin, alles danach fehlt. Anzeige bleibt „Gespeichert“.
3. Beim Wechseln der Szene und zurück zeigt das Feld ebenfalls nur den alten Stand.

Weitere Varianten mit gleicher Ursache:
- Neue Szene anlegen, Titel tippen, warten, dann Kommentartext tippen: Kommentar wird nie gespeichert (leer nach Neuladen).
- Titel ändern (löst Speichern aus), danach Segment-Zeit ändern: Segmentänderung geht verloren.
- Titel ändern, danach „Bilder & Karten …“ zuordnen und „Übernehmen“: Zuordnung geht verloren.

Vermutete Ursache (aus dem Code, nicht am Debugger bestätigt): `save()` in `web/js/views/editor.js` (Zeile ~27) macht `Object.assign(sel, scene, { report })` mit der Serverantwort. Dadurch werden `sel.kommentar` und `sel.segmente` durch neue Objekte ersetzt. Die Eingabefelder halten aber weiter Verweise auf die alten Objekte (`b`, `g`), ändern also etwas, das nicht mehr in `sel` hängt. Neu gezeichnet wird erst beim Umschalten von Sprecher/Modus oder beim Wechsel der Szene. Betroffen sind auch `select()` und das Aufräumen beim Verlassen der Ansicht (flushen `clean(sel)` mit dem alten Stand).
Der Befund (Daten gehen verloren) ist belegt, der Mechanismus ist eine begründete Vermutung.
Lösungsrichtung: Antwort des Servers nur in Felder wie `report`/`geaendert_*` übernehmen und nicht `kommentar`/`segmente` überschreiben, oder nach dem Speichern die Handler neu an `sel` binden.

### F2 (K) Rohschnitt bricht ab, sobald ein Kommentarblock im Abgleich „nicht gefunden“ ist
Reproduktion: Aufnahme für Philipp abgleichen, in der mindestens ein Philipp-Block nicht im Transkript steht (hier: zwei Szenen mit Text „Test“ bzw. leerem Text). Danach „Rohschnitt erzeugen“.
Ergebnis: Auftrag endet mit `KeyError: 'in'`, in der Oberfläche eine unverständliche Fehlermeldung.
Ursache: `rough_cut.py` Zeile ~143 nimmt den Abgleich-Eintrag auch dann, wenn er `missing: true` trägt (ohne `in`/`out`), Zeile ~169 greift auf `al["in"]` zu. `align.flatten_for_rough_cut` filtert solche Einträge, wird aber in `pipeline.build_rough_cut` nicht aufgerufen. Das ist der Normalfall nach jedem Abgleich (eine verpasste Passage reicht). Abhilfe im Test: Zeiten für den Block von Hand eintragen.

### F3 (H) Ein einzelnes Segment hinter dem Ende der Quelle lässt den ganzen Rohschnitt scheitern, Meldung ohne Hinweis
Reproduktion: Segment mit Out 90 s bei 40 s Quelle (die Ampel zeigt nur „rot / 55 s zu lang“, kein Hinweis auf „liegt hinter dem Ende“). Rohschnitt erzeugen: Fehler „Frame-Export fehlgeschlagen: “ (leerer Zusatz, keine Szene genannt).
Der Editor prüft nur „Out nach In“ und „nicht negativ“ (`validate_segments`), nicht „innerhalb der Quelldauer“. Die Prüfung `problems` kommt außerdem nur beim Laden der Liste, nicht aus der Speicherantwort, das Banner aktualisiert sich nach dem Tippen also nicht.

### F4 (H) Drag-Sortieren kann eine Szene nicht ans Ende setzen
Reproduktion: Szenenliste, erste Szene auf die letzte ziehen. Die Szene landet vor der letzten (`ids.splice(indexOf(to), 0, from)`). Eine Szene an das Ende zu bringen ist nur über Umwege möglich (letzte Szene nach oben ziehen). Keine Alternative per Tastatur oder Knopf.

### F5 (H) Reihenfolge im Editor stimmt nicht mit Word und Rohschnitt überein
Szenenliste, Aufnahme-Ansicht und Rohschnitt-Warnungen zählen nach `reihenfolge`; Word-Export und Rohschnitt sortieren standardmäßig nach Strang-Reihenfolge (`by_strand=True`), „dramaturgisch fixiert“ ausgenommen.
Reproduktion: Szene aus Strang Númenor an Position 1 ziehen, Word exportieren: Dort steht „Szene 01“ eine Eregion-Szene. Nummern im Word, im Editor und in den Rohschnitt-Markern widersprechen sich, die Sprecher nennen im Gespräch also andere Nummern als das Tool anzeigt. Die Strang-Reihenfolge selbst lässt sich in der Oberfläche nicht ändern (siehe Abschnitt 2).

### F6 (H) „Automatisch“ bei der Transkription sendet Aufnahmen ohne Rückfrage an ScaDS
Einstellungen zeigen bei „Automatisch“ den Satz „Aufnahmen verlassen den Rechner nur, wenn ausdrücklich ScaDS.AI Whisper gewählt ist“ und gleichzeitig „Aktives Verfahren: scads“. Bei fehlender CUDA-GPU (z. B. Philipps Mac) wählt `stt.choose_backend("auto")` ScaDS. Der Text widerspricht dem Verhalten, und es gibt keine Bestätigung vor dem ersten Upload. Laut FRAGEN.md F4 war ScaDS-Whisper gewünscht, aber „nur auf deine Anweisung“.

### F7 (M) Abgleich scheitert mit rohem Technik-Fehler
Ist ScaDS nicht erreichbar, lautet die Meldung `APIConnectionError: Connection error.` Kein Hinweis auf Netz, Schlüssel oder Umschalten auf lokal. Das Gleiche bei nicht vorhandener Aufnahmedatei (HTTP 500 ohne Text, siehe F10).

### F8 (M) Word-Import: kaputte Datei ergibt HTTP 500; unveränderte Szenen werden als „geändert“ gemeldet
- Keine gültige .docx (Textdatei mit Endung .docx) hochladen: „Internal Server Error“ statt „Datei ist kein Word-Dokument“.
- Unmittelbar nach dem Export wieder importiert, meldet die Vorschau Szenen als geändert, deren Text leer ist (leerer Block „PHILIPP: “ → `changed`). Das erzeugt Verunsicherung („was wurde geändert?“).
- Die Vorschau nennt nur Szenen-IDs (`sz_02, sz_03`), keine Titel, kein Vorher/Nachher; freie Blöcke werden weder in der Vorschau noch nach dem Import gezeigt (die Antwort enthält `free_blocks`, die Oberfläche ignoriert sie).
- Neue Absätze ohne „Überschrift 1“ im Word werden still an die letzte Szene angehängt (Test: „WERBUNG … 80 Sekunden“ landete im Text der letzten Szene). Freie Blöcke funktionieren nur mit Überschrift 1; das steht nirgends in der Oberfläche.

### F9 (M) Hinweistext zur Szenenmarke stimmt nicht
Word-Skript-Seite: „Szenenmarken (z. B. [sz_01]) bitte nicht löschen“. Im Dokument steht tatsächlich `⟦sz:sz_01⟧` (und `⟦+bild:art_0001⟧`). Wer nach `[sz_01]` sucht, findet nichts.

### F10 (M) Fehlerfälle der API liefern HTTP 500 statt verständlicher Meldung
- Szene mit unbekanntem Sprecher (`"hans"`) anlegen: 500.
- Aufnahme mit nicht existierender Datei hinzufügen: 500.
- Quelle mit nicht existierendem Pfad importieren: Auftrag bleibt bis zu 10 Minuten auf „läuft“ (`wait_until_stable`, Timeout 600 s), ohne Abbrechen-Knopf. Bei einer Datei, die keine Videodatei ist, kommt die Meldung `RuntimeError: ffprobe fehlgeschlagen: …Invalid data found…` (englisch, technisch).
- Rohschnitt für Folge ohne Referenz: `KeyError: ''`.

### F11 (M) Folge anlegen prüft Eingaben nicht
- Staffel 0, Folge -1 und Staffel 99999 werden angelegt (Ordner `S0 E-1`, `S99999 E1`). Die Folge `S0 E-1` erscheint danach nicht in der Folgenliste, existiert aber als Ordner.
- Dieselbe Staffel/Folge noch einmal anlegen: Antwort „ok“, keine Meldung, Titel bleibt unverändert.
- Der Dialog „Neue Folge anlegen“ ist fest auf Staffel 2 / Folge 1 vorbelegt (das Heft nennt Staffel 3; sinnvoll wäre „nächste Folge nach der letzten“).

### F12 (M) Quelle erneut importieren überschreibt die Referenz-Rolle
Dieselbe Datei als „Weitere Quelle“ (Rolle Screener) importieren: Die vorhandene Quelle `q1` bekommt die Rolle Screener, `reference_source` bleibt `q1`. Die Referenz heißt dann Screener, ohne Warnung.

### F13 (M) Szene ohne Segment zeigt grüne Ampel und bekommt im Rohschnitt trotzdem Standbild und Pause/Play-Animation
Szene mit leerer Segmentliste: Ampel „grün/passt“, keine Warnung im Rohschnitt; es entsteht ein 3-s-Standbild plus Animationen für ein Nichts. Sinnvoll wäre grau/„kein Material“ und eine Rohschnitt-Warnung.

### F14 (M) Zeitfelder: Frames statt Sekunden, auch für Audio
`fmtTC`/`parseTC` rechnen die Stelle hinter dem Punkt als Bilder bei 24 fps (Projekt: 23,976). „0:10.5“ ergibt nicht 10,5 s, sondern 10 s + 5 Bilder (10,21 s). In der Aufnahme-Ansicht werden Audiozeiten ebenfalls in „Bildern“ angezeigt (7,05 s → `00:07.01`, 15,45 s → `00:15.10`). Wer die angezeigte Zeit in ein Feld tippt, trifft nicht dieselbe Stelle. Außerdem wird in den Segmentfeldern „in > out“ (62,2 s → 5,0 s) angenommen und zeigt dann „0.0 s“; auch in Aufnahme-Zeiten sind „In > Out“ und Werte hinter dem Dateiende möglich (API: 50 → 10 akzeptiert).

### F15 (M) Fenster unter ca. 1100 px: Editor unbrauchbar
- 900 px: Rechte Spalte (Kommentar) wird abgeschnitten, Zeitfelder der Segmente schrumpfen zu leeren Kästchen. Das Seitenpanel springt auf Icon-Leiste, dabei verschwindet auch die Folgenauswahl.
- 600 und 390 px: Es ist nur die Szenenliste sichtbar, die Szene selbst nicht erreichbar.
Übersicht, Aufnahme, Rohschnitt etc. bleiben bedienbar. Wirkt sich v. a. auf kleine Laptops/Splitscreen aus.

### F16 (N) Weitere kleine Fehler
- Deep-Link `#/S/E/editor?id=sz_04` funktioniert nicht (der Router liest `editor?id=…` als unbekannte Ansicht und springt auf Übersicht), obwohl der Editor `?id=` auswertet.
- Folgenauswahl links zeigt nach „Abbrechen“ im Dialog „+ Neue Folge anlegen …“ stehen.
- Der Dialog „Neue Folge“ fokussiert kein Feld, Enter schickt nicht ab (Fokus liegt auf `body`). Esc schließt korrekt.
- Dasselbe Bild zweimal aus der Bibliothek hinzufügen erzeugt ein Duplikat (art_0002 und art_0003 identisch), keine Rückmeldung.
- Credit-Vorbelegung: „Alan Lee - Celebrimbor.jpg“ → „alan lee“ (gut), „Ted Nasmith_Armenelos.png“ → „ted nasmith armenelos“ (Unterstrich wird nicht als Trenner erkannt, Werktitel landet im Credit).
- Bildsuche: Ordnername „Eregion“ wird nicht gefunden (nur Dateiname/Tags), „lee“ findet die Datei.
- Karten-Pfade absolut (`/api/maps`), Bild-Pfade relativ: uneinheitlich.
- Die Kartenid wird aus `mine.length + 1` gebildet (`map_01`, …), das kollidiert, sobald je eine Karte entfernt würde (aktuell nicht möglich).
- Protokoll: Jeder Autosave schreibt eine Zeile „Szene sz_03 gespeichert“ (nur IDs, keine Titel). Bei normalem Schreiben füllt das das Protokoll mit Rauschen.
- Rohschnitt-Standbilder überspringen Nummern (1.png, 2.png, 4.png), wenn eine Szene ohne Material dazwischen liegt.
- Standbildnummer und Szenenmarker nennen IDs statt Titel in Warnungen („sz_01 Block 2: noch keine Aufnahme zugeordnet“).
- Szene, die nur Whitespace oder Text enthält, der im Word leer ist, erzeugt einen 0,016-s-Kommentarclip auf A2.
- Der Hinweis „Szene wird bearbeitet von …“ erscheint nur beim Öffnen; ein Konflikt durch gleichzeitiges Speichern wird nicht verhindert (siehe Abschnitt 2, Live-Nachladen).

---

## 2. Fehlende oder halb umgesetzte Anforderungen laut Heft

Verweise auf Heft-Abschnitte. „Fehlt“ = im Code/der Oberfläche nicht vorhanden (per `grep` in `web/js` und Servermodulen geprüft), „halb“ = Grundlage vorhanden, Bedienung unvollständig.

### Premiere und Rahmen (Abschnitt 6, 8)
- **Premiere-UXP-Panel fehlt** (kein Ordner `premiere-panel/`), ebenso das AE-Skript `erstelle_credit_vorlagen.jsx` und `ae-scripts/`. Ohne das bleibt als Weg nur die FCP-XML, die laut Heft keine Credits, Effektvorgaben und Play/Pause enthält. Das ist die Hauptlücke zum „großen Zeitgewinn“ (Meilenstein 4). Bekannt (STATUS.md), hier nur der Vollständigkeit halber.
- Die FCP-XML ist wohlgeformt (Parser-Test), ob Premiere sie sauber öffnet, ist nicht geprüft.
- **Update-Prüfung über GitHub-Releases fehlt** (8, „Update per Klick“). Keine Spur im Code.
- **Erststart-Assistent fehlt**: Heft verlangt „beim ersten Start OneDrive-Projektordner und Bildordner wählen, Name eintragen“. Umgesetzt ist nur eine Weiterleitung auf Einstellungen, wenn der Stammordner fehlt; der Name steht auf „tester“/Standard.

### Quellen und Conform (4, 5.1, 5.9)
- **Doppelansicht zum Anker-Setzen fehlt (halb)**: Anker werden als Zeitcodes in einem Dialog getippt (`Quellen → Anker`). Das Heft beschreibt: in beiden Quellen zum selben Frame springen und „Anker hier setzen“, dann Überblendung/Differenz prüfen. Die Kontrolle zeigt zwar Referenz/Quelle/Differenz, hat aber nur einen Schieberegler mit Schritt 0,5 s, keine Bildschritte, keinen Knopf „Anker setzen“ und keine Versatz-Feinjustierung pro Bild.
- Pro Quelle wird kein Proxy automatisch erzeugt (5.1 verlangt es): Nach dem Import erscheint im Editor „Für die Vorschau fehlt der Proxy“, man muss „Proxy jetzt erzeugen“ klicken (oder auf der Quellen-Seite „Proxy“). Ob der Proxy 540p/Alle-Bilder-Keyframe ist, wurde nicht geprüft.
- OneDrive-Hinweis zu „Dateien bei Bedarf“ (nur online verfügbar) fehlt; es gibt nur das Warten auf stabile Dateigröße.
- Audio-Fingerabdruck zum Wiederfinden verschobener Dateien: Feld vorhanden; Wiederfinden in der Oberfläche nicht gesehen (nicht geprüft).

### Strang-Board (5.2)
- Nur „Erkennen → Vorschläge anklicken → Als Szenen anlegen“. Es fehlen Filmstreifen mit Drag&Drop auf Stränge, **Grenzen verschieben/teilen/zusammenführen**, Sortieren der Stränge, „dramaturgisch fixieren“ auf dem Board.
- **Strang-Reihenfolge nicht änderbar** (Zeilen haben nur Farbe, Name, Löschen). Sie bestimmt aber die Ausgabereihenfolge (siehe F5).
- Strang löschen warnt nicht, wenn Szenen ihn noch benutzen.
- Szenenvorschläge: Die Thumbnails sind je Vorschlag eines; Tonpausen/Schnittdichte als Entscheidungshilfe nicht sichtbar.

### Szenen-Editor (5.3)
- **J/K/L fehlen** (nur Leertaste, I, O, Pfeile, Umschalt+Pfeile = 10 Bilder).
- **Kommentar-Editor ohne Formatierung** (Heft: „einfache Formatierung“), nur Textfeld.
- **Namens- und Rechtschreibprüfung (LLM) hat keine Oberfläche**: Endpunkte `/api/llm/*` existieren, im Web-Code wird keiner aufgerufen; in den Einstellungen lassen sich die Funktionen nur ein-/ausschalten. Gleiches gilt für Bild- und Kartenvorschläge und Szenentitel/Strang-Vorschlag.
- Gesamtlaufzeit-Schätzung nur auf der Übersicht; im Editor pro Szene Serie/Kommentar, keine Folge-Summe, kein Anteil Serienmaterial am Video in Echtzeit.
- Rückschritt/„veraltet“ (Abschnitt 3): Der Status `veraltet` existiert im Modell, wird aber nirgends gesetzt. Beispiel: Text einer abgeglichenen Szene ändern → Status bleibt „abgeglichen“, die Zeiten der alten Aufnahme stimmen nicht mehr, der Rohschnitt nutzt sie weiter. Auch Aufnahme neu abgleichen oder Segmente kürzen markiert nichts.

### Assets (5.4)
- **Künstler-Datenbank fehlt** (`default_credit(..., artist_db=...)` ist vorbereitet, wird nirgends befüllt oder gelesen, keine Oberfläche).
- **Bridge-/XMP-Tag-Suche ohne Oberfläche**: `/api/images/keywords` wird nicht genutzt, die Suche ist ein Freitextfeld. Keine Tag-Chips, keine Ordner-/Tagfilter, keine Anzeige von Titel/Ersteller aus XMP im Raster (Raster zeigt Dateiname oder Titel).
- Bild nicht mehr entfernbar (kein Löschen/Ersetzen in der Folge). In der Bibliothek kein Hinweis „schon in dieser Folge“.
- Kein Hinweis/Pflichtfeld bei fehlendem Credit außer Text „Credit fehlt“ im Raster; Rohschnitt warnt „Credit aus Dateiname vorbelegt“.
- Konturfarbe: Auswahl per Farbfeld vorhanden, **keine Vorschau der Rahmenanimation** und keine Pipette; Bildausschnitt/Zoom-Position (optional) fehlen, nur „Langsamer Zoom“.
- Ankerdialog: Zuordnung per Wortnummer („Ab Wort Nr. 4“). Man muss Wörter zählen. Heft: Anker an eine Textstelle (Wort/Satzbereich). Es gibt keine Auswahl im Text (Markieren, Rechtsklick).

### Karten (5.5)
- **Kartenproxy-Editor fehlt praktisch ganz**: Karte wählen und „Platzhalter rendern“ sind da. Es fehlen Einzeichnen (Marker, Beschriftung, Pfeil/Pfad, Region, Kamerarahmen), Keyframe-Zeitleiste, Hinweise pro Element und Freitext. Das Backend (`maps.py`) kennt Elemente, Kamera, Hinweise und rendert Blatt und Clip, die Oberfläche setzt aber immer `elemente: []`. Damit ist der Platzhalter nur die Karte ohne Inhalt.
- Kein Download/Öffnen des Kartenblatts (PNG), keine Vorschau des Platzhalter-Clips.
- Karte aus der Folge entfernen oder umbenennen geht nicht.

### Word (5.6)
- Bild-/Kartenmarker im Word zeigen nur IDs (`⟦+bild:art_0001⟧`), nicht den Namen („Alan Lee – Celebrimbor“). Für Sprecher unlesbar und kaum ausblendbar: API-Option `markers=false` existiert, in der Oberfläche fehlt der Schalter.
- Schriftgröße: Sprechertext hat keine eingestellte Größe (Word-Standard), das Heft verlangt „gut lesbare Größe“; Sprechername nur als Großbuchstaben-Präfix, ohne Farbe oder Fett.
- Freie Blöcke: kein Ort in der Oberfläche, an dem sie sichtbar, bearbeitbar oder mit einer **Dauer** versehen werden können. Der Rohschnitt setzt eine Lücke aus Sprechlänge (Beispiel „Hier kommt die Werbung, 80 Sekunden.“ → 2,3 s), obwohl bei Intro/Werbung/Outro die Dauer bekannt ist (Heft: Werbung 81 s, Outro 68 s).
- Export legt die Datei in den Folgenordner (`Skript S3 E1.docx`, `Skript S3 E1 danny.docx`), die Oberfläche sagt nicht wo (Download über Browser). In OneDrive entstehen dadurch Dateien, die niemand bewusst angelegt hat.

### Aufnahme (5.7)
- **Retake-Umschaltung fehlt**: Die Daten enthalten `takes`/`chosen`, die Oberfläche hat keinen Schalter (der Abgleich läuft fest mit `prefer=last`). Das Heft sagt „Standard letzter Take, umschaltbar“.
- **Spontane Ergänzungen** (`ergaenzungen`) werden nicht angezeigt und können nicht ins Skript übernommen werden (nur „Als Skript“ bei Stichpunkten).
- Prüfansicht: Wellenform zeigt Szenenbereiche ohne Beschriftung; **Grenzen nicht per Drag** korrigierbar (nur Zeitfelder, siehe F14), „unsichere Stellen markiert“ nur über Prozent-Pille in der Liste.
- Sprecherfilter beim Rohschnitt (API `speakers`) hat keinen Schalter.

### Rohschnitt (5.8)
- Spurlayout und Vorlagenwerte sind im Paket vorhanden (V1, V2, V9, A2–A4, Doppelbild-Positionen, Credits). Dass die Werte zu eurem echten Schnitt passen, ist ohne Panel nicht prüfbar.
- Die Rohschnitt-Seite zeigt Warnungen nur direkt nach dem Erzeugen; beim erneuten Öffnen sind sie weg (nur Hinweis „4 Szene(n) sind noch nicht abgeglichen“ ohne Namen). Keine Version-gegen-Version-Übersicht.

### Synchronisierung (7)
- **Live-Nachladen nur als Toast**: Der Server schaut alle 8 s auf eine Versionsmarke und sagt „Ansicht neu laden (F5)“. Im Szenen-Editor ist die Prüfung abgeschaltet (`current === 'editor'`), dort sieht man Änderungen anderer gar nicht.
- **Keine Schutzmaßnahme vor Überschreiben**: `PUT /scenes/{id}` speichert die ganze Szene ohne Versions-/Zeitstempelvergleich (Last-Write-Wins). Ein Editor mit altem Stand überschreibt auch `status` und `gesprochen` (aus dem Abgleich).
- Sperre wird nur beim Öffnen gezeigt, nicht live aktualisiert; eine Sperre blockiert nichts.
- Konfliktkopien: Dialog zum Zusammenführen im Protokoll vorhanden (nicht mit Test-Konfliktdateien durchgespielt).
- Änderungsprotokoll vorhanden, aber ohne Filter/Suche und mit IDs statt Titeln.

### LLM (5.10)
- Nur die Transkript-Nachkorrektur läuft (im Abgleich). Die übrigen vier Funktionen haben keine Oberfläche, s. o.
- Kein „Verbindung testen“-Knopf in den Einstellungen (nur „API-Schlüssel gefunden“).

---

## 3. Zeitsparer und Verbesserungsvorschläge (nach Nutzen/Aufwand)

### A. Sofort: Nutzen sehr hoch, Aufwand klein
1. **Autosave-Fehler F1 beheben.** Ohne das ist jedes Skriptschreiben riskant. Zusätzlich Autosave-Anzeige mit Zeitstempel („Gespeichert 14:32:10“) und Warnung beim Verlassen des Tabs bei ungespeichertem Stand (`beforeunload`).
2. **Rohschnitt robust machen (F2, F3, F13):** `missing`-Blöcke als Schätzung behandeln (Warnung statt Abbruch), Segmentgrenzen gegen Quelldauer prüfen, Fehler mit Szenentitel nennen (statt `KeyError`).
3. **Abgleich-Fehler lesbar:** „ScaDS nicht erreichbar – Internet/Schlüssel prüfen oder Verfahren auf ‚Lokal‘ stellen“. Vor dem ersten Upload an ScaDS einmalig fragen (F6), Text in Einstellungen korrigieren.
4. **Szenen-Reihenfolge eindeutig machen (F4, F5):** Knöpfe „Nach oben/unten/an Anfang/Ende“ plus Strg+Pfeil, Strang-Reihenfolge per Hoch/Runter-Knöpfe, in der Szenenliste die tatsächliche Ausgabenummer anzeigen (z. B. „Word #3“).
5. **Dialoge:** Autofokus erstes Feld, Enter = Primäraktion, „Neue Folge“ mit „nächste Folge“ als Vorbelegung und Plausibilitätsprüfung (F11, F16).
6. **Fehlertexte vereinheitlichen:** HTTP-500 in verständliches Deutsch übersetzen (Sprecher, Datei fehlt, kein Word-Dokument).

### B. Hoher Nutzen, mittlerer Aufwand
7. **Proxy automatisch nach dem Import** (Hintergrundauftrag mit Fortschritt in der Seitenleiste), Editor lädt Player selbst nach.
8. **„Anker setzen“ in der Kontrolle:** Zwei Player (Referenz + Quelle), Bildschritt ←/→ pro Seite, Knopf „Hier verknüpfen“ übernimmt beide aktuellen Zeiten als Anker; Differenz/Überblendung wie im Heft. Spart das Abschreiben von Zeitcodes.
9. **Szenen-Editor Tempo:** Szenensuche/-filter (nach Strang, Status, Ampel) über der Liste; Tastenkürzel Strg+Pfeil auf/ab (Szene wechseln), Alt+1/2 für Sprecher, Strg+Enter = neuer Kommentarblock, J/K/L, „Nächste Szene ohne Segment“. Bei 49 Szenen pro Folge (Heft, S2 E7) ist das der häufigste Klickweg.
10. **Segmente schneller setzen:** „Segment +“ übernimmt In = aktuelle Zeit, Out = In + 5 s; besser: I startet, O beendet (existiert) plus ein Knopf „Segment aus Auswahl mit Standbild-Vorschau“ und Anzeige der Länge direkt in der Zeitleiste mit Ampelfarbe. Segmentzeilen duplizieren/umsortieren (Montage mit bis zu 15 Stücken).
11. **Bild-/Kartenanker per Textauswahl:** Im Kommentartext Wörter markieren → Popup „Bild/Karte hier einblenden“ (mit Thumbnail-Auswahl). Ersetzt den Dialog mit Wortnummern.
12. **Aufnahme-Prüfansicht bedienbar machen:** Tasten Leertaste/J/K/L, Klick auf Block springt in der Wellenform, Grenzen per Drag, Takes-Auswahl (letzter/bester/anderer), Liste „nur unsichere anzeigen“, Sprung zur nächsten Unsicheren. Aufnahmezeiten in Sekunden mit Millisekunden darstellen (F14).
13. **Word:** Marker mit Namen (`⟦+bild: Alan Lee – Celebrimbor | art_0001⟧`), Schalter „Marker ausblenden“ und „Nach Szenenreihenfolge statt Strang“, 14-pt-Schrift, Sprecher farbig/fett, Seitenumbruch vor Szenenkopf optional; nach dem Import eine Änderungsliste mit Titeln und Vorher/Nachher (ein Diff pro Szene), freie Blöcke mit Dauerfeld.
14. **Freie Blöcke in der Oberfläche:** Liste „Rahmenteile“ (Name, Dauer, Position) zwischen den Szenen; Standardvorlagen Intro/Werbung/Outro mit Dauer aus den Einstellungen. Spart händisches Nachziehen im Premiere.
15. **„Veraltet“-Logik:** Ändert sich Text/Sprecher/Segmente einer abgeglichenen Szene, Status auf „veraltet“ und Hinweis auf Übersicht/Rohschnitt („3 Szenen müssen neu zugeordnet werden“). Nach neuem Abgleich nur diese Szenen verarbeiten.
16. **Übersicht als Cockpit:** Statt vier statischer Kacheln: Liste „Als Nächstes“ (z. B. „6 Szenen ohne Segment, 2 ohne Strang, 4 Bilder ohne Credit, 1 Block ohne Aufnahme“) mit Klick auf die Stelle. Phase 3 und 4 werden aktuell nie als erledigt markiert (Phase 4 ist fest „offen“).
17. **Rohschnitt-Seite:** Letzte Warnungen speichern und anzeigen, mit Sprung zur Szene; Knopf „Ordner öffnen“ und Pfad anzeigen; Hinweis welches Paket das Panel lesen soll.
18. **Bildersuche:** Tag-Chips aus `/images/keywords`, Mehrfachauswahl, „Bild gehört schon zur Folge“-Markierung, Doppelklick = hinzufügen, Entfernen-Knopf, Ordnernamen in die Suche, Künstler-Datenbank (Alias „ted nasmith armenelos“ → „ted nasmith“ einmal korrigieren, gilt für alle Folgen).

### C. Nutzen mittel bis hoch, Aufwand größer
19. **Kartenproxy-Editor** (Marker/Pfeil/Region/Rahmen, einfache Keyframes) wie im Heft; ohne ihn bleibt Meilenstein 7 unerledigt.
20. **Strang-Board als Filmstreifen** (Drag&Drop, Grenzen verschieben/teilen, Mehrfachauswahl und „Zu Strang …“), Doppelklick öffnet Szene.
21. **Echtzeit-Sync:** Server-Sent-Events oder Polling im Editor, Hinweis „Maurice hat Szene 12 gespeichert – laden?“, Versionsprüfung beim Speichern (409 bei Konflikt mit Diff-Dialog), Konfliktkopien automatisch erkennen.
22. **LLM-Funktionen in die Oberfläche** (Reihenfolge nach Nutzen): Namensprüfung im Kommentar, Bildvorschläge aus dem Text, Kartenvorschlag, Szenentitel. Zuerst Namensprüfung, weil die Eigennamen bei jedem Skript auftreten.
23. **Undo/Papierkorb:** „Szene gelöscht – Rückgängig“ für 10 Sekunden (aktuell nur Bestätigungsdialog, endgültig), Versionsverlauf pro Szene aus dem Protokoll („Stand von 14:10 wiederherstellen“).
24. **Rohschnitt-Vorschau im Browser:** Zeitleisten-Ansicht (nur Balken) der Spuren aus `schnitt_vN.json` mit Markern, damit Philipp/Danny Länge und Dichte vor dem Schnitt sehen. Einfacher Vorabcheck ohne Premiere.
25. **Update-Prüfung und Erststart-Assistent** (Heft Abschnitt 8) mit Test von ffmpeg, OneDrive-Ordner, ScaDS-Verbindung.

### D. Kleinigkeiten mit großem Komfort
- Sprecherwechsel per Taste, Standardsprecher abwechselnd (macht `Kommentarblock hinzufügen` schon, gut).
- Wortzähler und Sprechdauer pro Szene mit Ampel („zu lang für Standbild 18 s“; Heft: Median 18 s).
- Strg+S als „jetzt speichern“, Seitenwechsel speichert (existiert beim Wechseln, wegen F1 trotzdem unzuverlässig).
- Beim Import des Skripts aus dem Altformat statt `JSON.stringify` im Toast eine lesbare Zusammenfassung („12 Szenen, 3 neue Blöcke“).
- Theme-Umschalter in der Seitenleiste statt nur in den Einstellungen.
- Auf kleinen Fenstern: Ansicht-Wechsel zwischen Liste und Szene (Zurück-Knopf) statt Abschneiden.

---

## 4. UI und Verständlichkeit

**Gut gelungen:** Klare Seitenleiste in der Reihenfolge des Ablaufs (Vorbereitung, Skript, Material, Produktion), konsistente deutsche Texte, ruhige dunkle und helle Optik (Hell-Design getestet: gut lesbar, Kontraste ausreichend), brauchbare Leerzustände mit Handlungsknopf („Zweite Quelle nötig → Zu den Quellen“), Ampelpunkte in der Szenenliste, Autosave-Anzeige, Bestätigungen vor dem Löschen, Nutzertext wird nicht als HTML eingefügt (Folge mit `<img onerror>` im Titel lief harmlos). Keine JavaScript-Fehler in der Konsole bei den geprüften Ansichten.

**Verbesserungsbedarf:**
- **Editor-Kopfbereich verbraucht Platz:** Strang, Status und Standbild stehen untereinander, jeweils volle Breite (Bildschirm 1500 px). Nebeneinander in einer Zeile gäbe dem Player/Kommentar mehr Höhe. Die Pille „Serie 0:04 min / Kommentar 0:02 min“ steht verloren rechts daneben.
- **Beschriftungen ohne Erklärung:** „Standbild am Ende / am Anfang / Kein Standbild“ (Warum? Was passiert im Rohschnitt?), „Dramaturgisch fixiert“ (keine Erklärung, siehe Heft), „Status“ (manuell oder automatisch? Wer setzt „Aufgenommen“? Im Code setzt nur der Abgleich „abgeglichen“; „Skript fertig“ und „Aufgenommen“ muss man von Hand wählen), „Ab Wort Nr. / Bis Wort Nr.“ (Zählung 1-basiert, aber nirgends erklärt).
- **Zeitfelder** ohne Format-Hinweis (mm:ss.Bilder) und ohne Hinweis auf 23,976 fps; Sekunden („4.0 s“) und Bilder gemischt (siehe F14).
- **Fehlermeldungen** erscheinen als Toast, der nach wenigen Sekunden verschwindet (Fehler doppelt so lange); lange Texte (Fehler mit Pfad) sind schwer lesbar/kopierbar. Ein „Details kopieren“-Knopf wäre hilfreich.
- **Fortschritt:** Aufträge (Proxy, Import, Abgleich, Rohschnitt) erscheinen als Spinner mit Balken im Toastbereich, ohne Abbrechen, ohne Restzeit, nach Seitenwechsel nicht wiederauffindbar. Der Szenenerkennungstext sagt „einige Minuten“, kein Fortschritt pro Schritt. Bei langen Läufen (Whisper, Conform) wäre eine Aufgabenleiste unten mit Verlauf nötig.
- **Seitenleiste:** Bei Breite unter 1100 px verschwindet die Folgenauswahl, Icons haben nur `title`-Tooltips, keine `aria-label`; Icon-Knöpfe (Papierkorb, Play) im Editor ebenso. Für Tastatur-/Screenreader-Nutzung dürftig. Fokusrahmen: Eingabefelder haben `outline: none` (Rahmenfarbe wechselt immerhin).
- **Tab-Reihenfolge im Editor** ist logisch (Titel → Löschen → Selects → Player → Segmente → Block), Szenenliste ist aber nicht per Tab erreichbar (`div`, kein Button) und Drag-Sortieren geht nur mit Maus.
- **Word-Skript-Seite:** Vier Aktionen in drei Kästen, aber keine Beschreibung, was „Alle Szenen ersetzen“ vom normalen Import unterscheidet (Altformat vs. Rückimport), und kein Hinweis, dass Freie Blöcke „Überschrift 1“ brauchen.
- **Home** („Übersicht“) heißt Projektstatus, zeigt aber nur Zahlen. Phasenkarten sind klickbar, zeigen jedoch keinen Zahlenstand („3 von 6 Szenen mit Segment“).
- **Begriffe:** „Referenz“, „Zeitabbildung“, „Anker“, „Strang“, „Standbild“ sind aus dem Heft vertraut, für Maurice/Philipp zum Teil neu. Ein kurzer „?“-Hinweis pro Seite oder eine Glossar-Zeile in der Kopfzeile würde helfen. Der Begriff „Kontrolle“ in der Seitenleiste sagt nicht, dass dort die HQ-Ausrichtung geprüft wird („Ausrichten & Kontrolle“).
- **Leerer Zustand „Szenen“**, wenn Referenz fehlt: Player-Kasten mit Hinweis, aber ohne Link zu „Quellen“.

---

## Anhang: Testprotokoll in Kürze

| Bereich | Ergebnis |
| --- | --- |
| Folge anlegen, Quellen importieren (API) | funktioniert; Fehlerfälle siehe F10–F12 |
| Szenen anlegen/ändern über UI | Autosave verliert Folgeeingaben (F1) |
| Word-Export/-Import | Rundlauf funktioniert, Stichpunkte, Marker, freie Blöcke (mit Überschrift 1) ok; F8, F9 |
| Bilder indizieren/suchen/hinzufügen | ok; Credit-Vorbelegung, Konturfarbe ok; Duplikat und Suchlücken (F16) |
| Karten wählen/Platzhalter rendern | Clip und Blatt entstehen; keine Inhalte einzeichenbar |
| Aufnahme/Abgleich | Abgleich mit simuliertem Transkript lief, Retake „letzter Take“ ok; „nicht gefunden“ führt zu F2 |
| Rohschnitt | JSON + wohlgeformte XML, Marker, Credits, freie Blöcke vorhanden; Abbruch bei F2/F3 |
| Protokoll | funktioniert; verrauscht |
| Hell-Design | in Ordnung |
| Schmale Fenster | Editor unbrauchbar unter ca. 1100 px (F15) |
| Tastatur | Tab-Folge ok im Editor, Dialoge ohne Autofokus/Enter; Esc schließt; I/O/Leertaste/Pfeile nur mit Proxy-Video (nicht testbar) |
