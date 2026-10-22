# Projektheft: Projekt Glorfindel

Oct 22, 2026 · @Danny

## 1. Ziel und Rahmen

**Projekt Glorfindel** erzeugt aus einer Episodendatei, gemeinsam geschriebenem Skript, Bildern, Kartenplatzhaltern und der Sprachaufnahme einen Premiere-Rohschnitt für die Folgenbesprechungen zu „Die Ringe der Macht“ Staffel 3. Von Hand bleiben Feinschnitt, Musik, Karten und die Rahmenteile. Im Code und in Ordnernamen heißt das Projekt kurz `glorfindel`.

**Ziele**

- Rohschnitt einer Folge per Klick statt mehrerer Stunden manueller Arbeit.
- Gemeinsames Arbeiten von Danny, Maurice und Philipp über OneDrive, phasenweise und ohne Dateikonflikte.
- Arbeit komplett mit Screener oder Screencapture, Austausch gegen die HQ-Version vor dem Render ohne Verlust des Feinschnitts.
- Word-Export des Sprechertexts für die Aufnahme.
- Läuft als lokales Webinterface unter Windows und macOS, verteilt über GitHub.

**Nicht-Ziele (vorerst)**

- Kein eigener Videoeditor: Feinschnitt, Color und Export bleiben in Premiere.
- **Keine Musik:** Hintergrundmusik und Musik-Credits setzt ihr weiter von Hand im Schnitt.
- **Keine fertigen Karten:** Das Tool liefert nur Platzhalter mit Skizze und Hinweisen, die Karten animiert Danny von Hand.
- **Keine Rahmenteile:** Cold Open, Intro, Werbung, Outro und Abspann werden außerhalb geplant und höchstens im Word-Dokument ergänzt.
- Kein Cloud-Server: Alles läuft lokal, synchronisiert wird über OneDrive.
- Spätere Idee, nicht Teil dieses Projekts: ein Hilfswerkzeug, das Künstlernamen per Websuche prüft und in die XMP-Metadaten schreibt.

## 2. Aufbau der Videos (Ist-Stand, ausgewertet an S2 E7)

Die Sequenz „MythenAusMittelerdeVideo“ aus dem Projekt zu S2 E7 dauert 25:21 min und besteht zu einem Drittel aus Serienmaterial: 49 Szenenblöcke mit zusammen 8:32 min, getrennt durch 47 Standbilder, über denen Philipp und Danny abwechselnd kommentieren. Die Sequenz läuft in 1920×1080 mit 60 fps, die Folge selbst in 1920×800 mit 23,976 fps.

**Ablauf eines Szenenblocks (wie im Projekt gebaut)**

1. **Szene** aus der verschachtelten Sequenz „S2 E7 Sequenz“, in der die HQ-Folge liegt. Ton auf A4, an jedem Schnitt mit „Konstante Leistung“ geblendet.
2. **Pause-Animation** (verschachtelte Sequenz „Pause“, 1,32 s, aus `Play-Pause.aep` per Dynamic Link) startet konstant 0,63 s vor dem Standbild.
3. **Standbild** als exportiertes PNG (`Videoelemente/1.png` bis `47.png`), im Median 18 s lang. Darunter der Kommentar.
4. **Hintergrundmusik** auf A10 setzt etwa 0,3 bis 0,5 s vor dem Standbild ein, Blenden mit „Konstante Leistung“. Bei kurzen Szenen läuft ein Track teils durch.
5. **Artworks** (33 Stück, im Median 9 s): je eine verschachtelte Sequenz mit Bild oder animiertem Wallpaper (`.mov`) und Spurmaske (`Maske Quadrat.png`). Im Hauptschnitt bekommen sie „Kanten aufrauen“ mit den Vorgaben „Fancy In“ und „Fancy Out“ (Rahmen fährt in 0,5 s auf bzw. zu, mit einer **Konturfarbe passend zum Bild**), einen Schlagschatten und „Transformieren“ mit „Zoom 1.0“ (langsamer Zoom). Überlappende Artworks wechseln zwischen V3 und V4.
6. **Blur** über eine Einstellungsebene mit Gaußschem Weichzeichner auf V2: zuerst die Vorgabe „Gauß In“ (2 s), dann ein Abschnitt bis zum Ende des Artworks.
7. **Credit** pro Artwork als Premiere-Textgrafik auf V10, exakt so lang wie das Artwork (31 von 33). Text klein geschrieben, z. B. „© alan lee“, meist identisch mit dem Dateinamen.
8. **Play-Animation** (Sequenz „Play“, 1,32 s) startet konstant 0,68 s vor der nächsten Szene.

**Erkenntnisse für das Tool**

- **Szenen sind oft Montagen:** 23 der 49 Blöcke bestehen aus mehreren Teilstücken mit Sprüngen in der Folge (bis zu 15 Stücke). Eine Szene im Tool braucht deshalb eine Liste von Segmenten, nicht nur ein In/Out.
- **Kein Segment ist länger als 9,5 s.** Das ist offenbar eure gelebte Content-ID-Grenze und wird Standardwert der Längenampel.
- **Ein Standbild pro Lücke**, nicht zwei. Ein Überblenden zum Startbild der nächsten Szene kommt in S2 E7 nicht vor (siehe offene Fragen).
- **Zwei Sprecher mit getrennten Aufnahmen:** Philipp (A2, 24 Clips, 10:47 min) und Danny (A3, 29 Clips, 11:38 min), beide mit Essential-Sound-Vorgabe „Dialog“. Jeder Kommentarabschnitt braucht also einen Sprecher.
- **Drei Credit-Arten** als Textgrafiken: „© amazon studios“ während Serienmaterial (V9, 29×), Artwork-Credits (V10), Musik-Credits beim ersten Einsatz eines Tracks (V11, z. B. „© scott buckley - i walk with ghosts“).
- **Die Folge liegt bereits verschachtelt** in „S2 E7 Sequenz“ (mit 3,4 s Versatz). Alle 120 Szenen-Clips verweisen darauf. Das ist der ideale Punkt für den Screener→HQ-Tausch.

**Feste Rahmenteile, die nicht pro Szene entstehen**

- Cold Open: Montage mit Überblendungen, Philipp-Kommentar, Musik, „Spoilerwarnung!“-Text, Abo-Animation
- `Intro S2 E7.mp4`, Werbeblock aus `Werbung.aep` (81 s, Danny), Bauchbinden über `Bauchbinde.aegraphic` (3×), Instagram-Pop-ups
- Outro-Montage (68 s, 15 Stücke) und Abspann mit Kanalmitgliedern (`Mitglieder Gold/Silber/Kupfer/Mithril/Silima.psd`) und `Credits.psd`

## 3. Rollen und Phasen

Die Arbeit an einer Folge läuft in acht Phasen, die nacheinander über den gemeinsamen OneDrive-Ordner weitergereicht werden. Jede Phase hat eine zuständige Person, alle anderen können jederzeit lesen und kommentieren.

&#91;embedded content: Workflow · 8 Phasen mit Zuständigkeit\]

- Phasen 3 und 4 können parallel laufen, ebenso Feinschnitt und AE-Karten in Phase 7.
- Phase 1 ist optional: Ohne Screencapture kann Maurice direkt im Screener Szenen markieren und Stränge vergeben.
- Rückschritte sind jederzeit möglich (z. B. Szene nach der Aufnahme kürzen). Betroffene spätere Schritte werden als „veraltet“ markiert.
- Philipp und Danny sprechen beide ein (getrennte Aufnahmen). Jeder Kommentarabschnitt trägt deshalb einen Sprecher, und der Word-Export kann pro Sprecher gefiltert werden.

## 4. Zeitmodell: Referenzzeit statt Dateizeit

Alle Zeitangaben im Projekt (Szenen, Freeze Frames, Strang-Abschnitte) beziehen sich auf eine abstrakte **Episodenzeit**, nie auf eine konkrete Videodatei. Dadurch können Screencapture, Screener und HQ-Version gleichzeitig im Projekt sein, obwohl sie nicht framegenau übereinstimmen.

**Quellen**

- Die erste importierte Datei einer Folge wird zur **Referenzquelle**. Ihre Zeitachse ist die Episodenzeit.
- Jede weitere Quelle erhält eine Abbildung `t_quelle = a · t_ref + b`. `b` ist der Versatz, `a` gleicht unterschiedliche Bildraten bzw. Laufgeschwindigkeiten aus.
- **Ausrichten von Hand (Standard):** Eine Doppelansicht zeigt beide Quellen nebeneinander. Ihr springt in beiden zum selben Frame, am besten an einen harten Schnitt, und setzt dort einen **Ankerpunkt**. Ein Anker ergibt den Versatz, ein zweiter gegen Ende der Folge zusätzlich den Geschwindigkeitsfaktor. Eine Überblendungs- bzw. Differenzansicht zeigt sofort, ob es passt. Das dauert erfahrungsgemäß ein bis zwei Minuten und funktioniert unabhängig von Ton, Sprache und Bildqualität.
- **Stückweise Abweichungen** (Ruckler oder Lücken in der Bildschirmaufnahme): weitere Anker an den betroffenen Stellen setzen. Zwischen den Ankern wird dann jeweils eigen abgebildet. Die Kontrollansicht pro Szene (unten) zeigt, wo noch ein Anker fehlt.
- **Automatischer Vorschlag (später, optional):** Das Tool kann Ankerpunkte über die Abfolge der Schnitte vorschlagen. Ihr bestätigt sie nur noch. Das ist ein Komfortmerkmal und keine Voraussetzung.

**Prüfung durch den Nutzer**

- Pro Szene zeigt eine Kontrollansicht Freeze Frame A und B aus beiden Quellen nebeneinander, plus eine Differenzanzeige.
- Unsichere Stellen (geringe Korrelation) werden markiert, der Versatz kann frameweise nachjustiert werden.

**Screener → HQ mit einem Klick (Conform)**

1. HQ-Datei importieren und in der Doppelansicht über ein oder zwei Ankerpunkte an der Schnittquelle ausrichten.
2. Das Tool erzeugt per ffmpeg eine **konformierte HQ-Datei**: so geschnitten bzw. am Anfang mit Schwarz aufgefüllt und bei Bedarf in der Geschwindigkeit angepasst, dass sie zeitlich exakt deckungsgleich mit der Schnittquelle ist. Ausgabe als Schnittcodec (ProRes 422 HQ oder DNxHR HQ).
3. Standbilder und andere aus dem Video abgeleitete Dateien werden aus der HQ-Quelle unter **gleichem Dateinamen** in einen parallelen Ordner gerendert.
4. In Premiere tauscht der Panel-Befehl „Auf HQ umschalten“ den Inhalt der Episoden-Sequenz und verknüpft die Standbilder neu. Da In- und Out-Punkte identisch bleiben, bleibt **jeder manuelle Feinschnitt erhalten**.
5. Umgekehrt lässt sich jederzeit zurück auf den Screener schalten.

**Hinweis:** Bild-Seitenverhältnis und Auflösung dürfen abweichen. Die Sequenz skaliert Clips auf Framegröße, das Panel setzt das beim Umschalten automatisch.

**Anschluss an euren bisherigen Aufbau**

Ihr legt die Folge bereits in eine eigene Sequenz („S2 E7 Sequenz“), auf die alle Szenen-Clips verweisen. Das Tool übernimmt dieses Prinzip: Der Rohschnitt referenziert nur eine **Episoden-Sequenz**. Beim HQ-Tausch wird nur deren Inhalt ausgetauscht (konformierte HQ-Datei, Versatz gesetzt), die Hauptsequenz bleibt unberührt.

Im Projekt liegt außerdem `Folge 7 [ENGLISCH].mov` mit 1920×1080 und rund 26,8 fps, vermutlich eine Bildschirmaufnahme mit variabler Bildrate. Solche Quellen werden beim Import auf konstante 23,976 fps umgerechnet und auf 1920×800 zugeschnitten, sonst passen Frames und Standbilder nicht zur HQ-Folge.

**Testdaten (später im Repository):** Solange es keine Screener zu Staffel 3 gibt, eignet sich S2 E7: `Folge 7 [ENGLISCH].mov` als Screener-Ersatz (Bildschirmaufnahme, Englisch) gegen die deutsche HQ-Folge. Andere Sprache, Bildrate und anderes Seitenverhältnis machen das zum schwierigsten Fall.

## 5. Funktionsmodule

Das Tool besteht aus neun Modulen, die den Phasen aus Abschnitt 3 folgen.

### 5.1 Projekt und Quellen

- Neues Projekt pro Folge (z. B. `RdM_S3E01`), Metadaten: Staffel, Folge, Titel, Bildrate.
- Quellen importieren (MP4, MKV, MOV). Pro Quelle: Audio-Fingerabdruck, Dauer, Bildrate, Auflösung, Rolle (Referenz, Screener, HQ, Screencapture).
- Das Tool erzeugt pro Quelle einen **Arbeits-Proxy** (540p, H.264, jeder Frame ein Keyframe), damit Scrubben und Frame-Stepping im Browser exakt und flüssig sind.
- Quellen liegen in OneDrive und werden über den Pfad relativ zum OneDrive-Stammordner gefunden, ersatzweise über den Audio-Fingerabdruck.

### 5.2 Strang-Board (Phase 1)

- Automatische Szenenerkennung (PySceneDetect) zerlegt die Folge in Shots und fasst sie zu Szenen-Vorschlägen zusammen (Schnittdichte, Tonpausen).
- Darstellung als Filmstreifen mit Thumbnails. Abschnitte werden per Drag & Drop farbigen **Handlungssträngen** zugeordnet (z. B. Eregion, Númenor, Rhûn, Khazad-dûm).
- Grenzen lassen sich verschieben, teilen und zusammenführen.
- Stränge werden in die gewünschte Videoreihenfolge sortiert. Eine Option „dramaturgisch fixieren“ hält einzelne Abschnitte an ihrer Originalposition.

### 5.3 Szenen- und Skript-Editor (Phase 2)

- Pro Strang: Player mit Frame-Stepping (Pfeiltasten), Shortcuts `I`/`O` für In/Out, `J`/`K`/`L` für Abspielen.
- Jede **Szene** besteht aus einem oder mehreren **Segmenten** (je In/Out). So lassen sich Montagen bauen: In S2 E7 hatten 23 von 49 Szenen mehrere Segmente. Segmente werden mit „Konstante Leistung“ (Ton) aneinandergesetzt.
- Weitere Felder pro Szene: Strang, Reihenfolge, Titel, Status und ein oder mehrere **Kommentarabschnitte**, jeweils mit **Sprecher** (Philipp oder Danny) und Text.
- **Längenampel** pro Segment und pro Szene: Standard-Grenze 9,5 s je Segment (längstes Segment in S2 E7), zusätzlich Gesamtanteil Serienmaterial am Video (S2 E7: 34 %). Werte einstellbar.
- Kommentar-Editor mit einfacher Formatierung, geschätzte Sprechdauer pro Abschnitt und Gesamtlaufzeit-Schätzung.
- Rahmenteile (Cold Open, Intro, Werbung, Outro, Abspann) plant ihr außerhalb. Im Tool erscheinen sie nur, wenn sie über den Word-Rückimport als freie Blöcke hinzukommen (5.6).

### 5.4 Asset-Verknüpfung (Phase 3)

- Assets werden an eine **Textstelle** im Kommentar geheftet (Anker: Wort oder Satzbereich), nicht nur an die Szene. Daraus ergibt sich später das Einblendtiming.
- Optional: Dauer „bis Wort X“ oder „bis Ende des Kommentars“.
- **OneDrive-Bildsuche:** Indizierung eines oder mehrerer Bildordner. Gelesen werden XMP-Keywords (`dc:subject`, hierarchische Lightroom/Bridge-Keywords), Titel, Beschreibung und Ersteller (`dc:creator`) aus der Datei oder dem `.xmp`-Sidecar. Suche nach Tags und Freitext mit Thumbnail-Raster.
- **Web-Import:** URL einfügen → Bild wird in den Projektordner geladen, Quell-URL gespeichert.
- **Credit-Pflichtfeld** pro Asset (Künstlername, optional Link). Vorbelegung aus dem Dateinamen (wie bisher), ersatzweise aus einer gemeinsamen **Künstler-Datenbank**, die über alle Folgen wächst.
- Optionale Angaben pro Asset: Bildausschnitt, Zoom an/aus, Position.
- **Konturfarbe für Fancy In/Out:** Das Tool schlägt pro Artwork automatisch eine passende Farbe vor (dominanter Farbton am Bildrand, bei animierten Wallpapern über mehrere Frames gemittelt). Vorschau der Rahmenanimation direkt im Tool, Farbe per Pipette oder Farbwähler überschreibbar. Die Farbe wird mit dem Asset in der Bibliothek gespeichert und bei erneuter Verwendung übernommen.

### 5.5 Kartenproxy-Editor (Phase 4)

Karten bleiben im Tool bewusst einfache **Platzhalter**. Sie zeigen im Rohschnitt Timing und Inhalt an, die eigentliche Karte baut und animiert Danny danach von Hand.

- **Beliebige Karte wählen** aus `F:\OneDrive\Videomaterial\Karten` (Bildformate, auch große Dateien, mit Vorschau und Suche nach Dateiname).
- **Einzeichnen:** Marker, Beschriftung, Pfeil bzw. Pfad, Region (Polygon), Kamerarahmen.
- **Triviale Animation:** wenige Keyframes auf einer kleinen Zeitleiste, z. B. Kamerafahrt von Rahmen A zu B, Pfad zeichnet sich, Marker blendet ein.
- **Hinweise für den Schnitt:** Freitext zur Karte und Kommentare an einzelnen Elementen („hier Heerzug der Orks in Rot“).
- Ausgabe: ein **Platzhalterclip** (Karte mit Skizze und Animation, gut erkennbar als Platzhalter markiert) in der richtigen Länge für den Rohschnitt, plus ein **Kartenblatt** (PNG oder PDF) mit Skizze und Hinweisen. Die Daten liegen als JSON im Folgenordner.
- Karten werden wie Bilder an Textstellen im Kommentar geheftet. Im Rohschnitt bekommen sie die Vorgaben KarteIN und KarteOUT und einen Marker mit den Hinweisen.

### 5.6 Word-Export (Phase 5)

- Ein `.docx` für die Aufnahme: pro Szene eine Kopfzeile (Nummer, Strang, Kurztitel, Timecode), darunter die Kommentarabschnitte mit **Sprechername** (Philipp, Danny) in gut lesbarer Größe.
- Bild- und Kartenmarker erscheinen klein und grau, damit die Sprecher sie überlesen. Optional ganz ausblendbar.
- Szenen-Kopfzeilen tragen eindeutige Marken, damit das Dokument zurück ins Tool geladen werden kann.
- **Rückimport:** Ihr könnt das Dokument in Word überarbeiten und Rahmenteile (Intro, Werbung, Outro) als eigene Abschnitte ergänzen. Beim Rückimport übernimmt das Tool geänderte Texte in die Szenen. Ergänzte Abschnitte ohne Szenenmarke werden **freie Blöcke**: Sie zählen beim Abgleich der Aufnahme mit und erscheinen im Rohschnitt als Lücke mit Marker.

### 5.7 Aufnahme-Import und Abgleich (Phase 6)

- Import einer oder mehrerer Audiodateien (auch pro Sprecher getrennt).
- Whisper-Transkription mit Wort-Zeitstempeln, dann Text-Alignment mit dem Skript (Fuzzy-Matching auf Wortebene).
- Erkennung von **Retakes** (gleiche Sätze mehrfach): Standard ist der letzte Take, umschaltbar.
- Ergebnis: pro Szene ein Audio-Abschnitt (In/Out in der Aufnahme) und für jeden Asset-Anker ein Zeitpunkt.
- Prüfansicht: Wellenform mit Skripttext darunter, unsichere Stellen markiert, Grenzen per Drag korrigierbar.
- Erkannte spontane Ergänzungen werden angezeigt und können zurück ins Skript übernommen werden.

### 5.8 Rohschnitt-Generator (Phase 7)

Erzeugt die Premiere-Sequenz im Spurlayout von S2 E7. Alle Zeitversatz-Werte stammen aus dem Projekt und sind als Vorlage einstellbar.

| Spur | Inhalt | Regel aus S2 E7 |
| --- | --- | --- |
| V1 | Szenen-Segmente aus der verschachtelten Episoden-Sequenz, dazwischen Standbild-PNGs | Standbild = letzter Frame der Szene, bis Beginn der nächsten |
| V2 | Pause- und Play-Animation, Blur-Einstellungsebene | Pause −0,63 s vor Standbild, Play −0,68 s vor Szene, Blur „Gauß In“ 2 s + Rest bis Artwork-Ende |
| V3/V4 | Artworks und Kartenplatzhalter, abwechselnd | Artworks: Fancy In / Zoom 1.0 / Fancy Out, Karten: KarteIN / KarteOUT |
| V9 | Credit „© amazon studios“ | während Szenen und Standbildern |
| V10 | Artwork-Credit „© künstler“ | exakt Artwork-Dauer |
| A2 | Kommentar Philipp | Abschnitte aus dem Abgleich |
| A3 | Kommentar Danny | Abschnitte aus dem Abgleich |
| A4 | Originalton der Szenen | Blende „Konstante Leistung“ an jedem Segment |

Musik (A10), Musik-Credits (V11), Bauchbinden und Pop-ups (V12) bleiben frei und werden von Hand gesetzt.

- Standbilder rendert das Tool selbst per ffmpeg aus dem letzten Frame jeder Szene und legt sie wie bisher im Folgenordner unter `Videoelemente/1.png` … ab. Seitenverhältnis wie die Folge (1920×800), Platzierung mittig.
- Freie Blöcke aus dem Word-Rückimport (Intro, Werbung usw.) werden als Lücke in Sprechlänge mit Marker eingesetzt.
- Szenenreihenfolge nach Strang-Reihenfolge. Marker in der Sequenz für jede Szene und jeden Bild- und Kartenanker, Kartenhinweise im Markertext.
- Neu-Generieren erzeugt immer eine neue Sequenz mit Versionsnummer, damit kein Feinschnitt überschrieben wird.

### 5.9 HQ-Conform

Umsetzung wie in Abschnitt 4 beschrieben, inklusive Kontrollansicht und Panel-Befehl in Premiere.

### 5.10 LLM-Unterstützung (optional, über ScaDS.AI)

Wo Sprachverständnis hilft, ruft das Tool ein Sprachmodell über eine OpenAI-kompatible Schnittstelle auf. Voreingestellt ist der LLM-Dienst von ScaDS.AI (u. a. GLM und DeepSeek). Adresse und Modell stehen in den Einstellungen, das Modell ist pro Funktion wählbar. Der API-Schlüssel wird nur lokal auf dem jeweiligen Rechner gespeichert, nie in OneDrive oder im Repository. Jede Funktion ist abschaltbar, das Tool funktioniert ohne LLM vollständig. Gesendet werden nur Texte (Skript, Transkripte, Dateinamen), nie Video oder Audio.

| Funktion | Wo | Nutzen |
| --- | --- | --- |
| Nachkorrektur der Whisper-Transkripte mit Tolkien-Glossar | Aufnahme-Abgleich (5.7) | Eigennamen wie Celebrimbor, Khazad-dûm, Ost-in-Edhil werden richtig erkannt. Das verbessert den Abgleich mit dem Skript. |
| Namens- und Rechtschreibprüfung im Kommentar | Skript-Editor (5.3) | Markiert falsch geschriebene Namen und Orte, bevor sie im Word-Export landen. |
| Bildvorschläge aus dem Kommentartext | Bilder (5.4) | Leitet Suchbegriffe ab (Figuren, Orte, Ereignisse) und schlägt passende Bilder aus der Bibliothek vor. |
| Kartenvorschlag | Kartenplatzhalter (5.5) | Schlägt zur Textstelle eine Karte aus dem Kartenordner und die zu markierenden Orte vor. |
| Szenentitel und Strang-Vorschlag | Strang-Board (5.2) | Aus dem Transkript der Folge, nur wenn der Ton der Quelle brauchbar ist. |

Die LLM-Funktionen kommen erst nach dem MVP (Meilenstein 3 und 6). Vorher wird geprüft, welche Modelle bei ScaDS.AI verfügbar sind und wie gut sie mit deutschen Tolkien-Namen umgehen.

## 6. Premiere- und After-Effects-Integration

Ein **Premiere-Panel** baut den Rohschnitt direkt im Projekt, weil Textgrafiken, verschachtelte Sequenzen, Effektvorgaben und Audio-Blenden über einen XML-Import nicht vollständig ankommen.

**Premiere-Panel**

- Technik: UXP-Plugin für Premiere Pro 2026, die von euch genutzte Version. ExtendScript/CEP nur als Notlösung für einzelne Funktionen, die UXP noch nicht abdeckt. Das klärt der Vorab-Test in Meilenstein 0.
- Das Panel liest ein **Schnittpaket** (`schnitt.json` + Medienliste) aus dem Projektordner oder direkt vom lokalen Tool-Server.
- Funktionen:
  - **Rohschnitt bauen:** Sequenz aus Vorlage, Szenen-Segmente aus der Episoden-Sequenz, Standbilder, **Play/Pause als verschachtelte Sequenzen** aus der Vorlage (wie bisher über `Play-Pause.aep`), Artwork-Sequenzen mit Maske, Effektvorgaben (Kanten aufrauen, Schlagschatten, Fancy In/Out, Gauß In), Blur-Einstellungsebene, Audio-Blenden, Marker.
  - **Credits als Textfelder:** Credits kommen als MOGRT mit Textfeld aus austauschbaren Grafik-Slots (siehe unten). Nur über ein solches Feld kann ein Skript den Text zuverlässig setzen. In der Timeline bleibt er im Fenster „Essential Graphics“ als Textfeld editierbar.
  - **Auf HQ umschalten / zurück:** Inhalt der Episoden-Sequenz tauschen, Standbilder und Kartenproxys neu verknüpfen.
  - **Abgleich-Bericht:** Liste aller Szenen mit Prüfstatus und Längenampel.
- Fallback ohne Panel: Final-Cut-Pro-XML für Clips, Standbilder, Audio und Marker. Credits, Effektvorgaben und Play/Pause müssten dann von Hand ergänzt werden.

**Vorlagen aus eurem bestehenden Projekt**

- Eine **Vorlagen-Projektdatei** mit: Sequenzeinstellungen (1920×1080, 60 fps), Sequenzen „Play“ und „Pause“, Einstellungsebene mit Gaußschem Weichzeichner, Artwork-Vorlage mit `Maske Quadrat.png`, Effektvorgaben (`Fancy In`, `Fancy Out`, `Zoom 1.0`, `Gauß In`), Credit-MOGRTs, Musik-Pegel.
- Die Vorlage wird einmal hinterlegt und für jede Folge ins neue Projekt importiert.
- Artwork-Credits werden aus dem Dateinamen vorbelegt (in S2 E7 entsprach der Credit fast immer dem Dateinamen), überschreibbar per Künstler-Datenbank oder XMP.

**Effekt-Rezepte aus euren Vorgaben**

Das Tool liest eure `.prfpset`-Dateien ein und speichert jede Vorgabe als Rezept: Effekt, Verankerung am Clip-Anfang oder -Ende und Keyframes relativ dazu. Das Panel setzt diese Keyframes selbst. Ob Premiere das direkte Anwenden gespeicherter Vorgaben per Skript erlaubt, wird in Meilenstein 0 geprüft. Der Rezept-Weg funktioniert in jedem Fall und erlaubt pro Clip abweichende Werte wie die Konturfarbe. Neue Vorgaben werden einfach in den Vorlagenordner gelegt.

| Vorgabe | Effekt | Verankert an | Animation |
| --- | --- | --- | --- |
| Fancy In | Kanten aufrauen | Clip-Anfang | 0,5 s: Rahmen 500 → 8, Kantenschärfe 0 → 0,2, Skalieren 204 → 192 |
| Fancy Out | Kanten aufrauen | Clip-Ende | letzte 0,5 s: Rahmen 8 → 500, Skalieren 192 → 204 |
| Zoom 1.0 | Transformieren | Clip-Anfang | Skalierung 100 → 240 % über 120 s (langsamer Zoom) |
| Gauß In | Gaußscher Weichzeichner | Clip-Anfang | Stärke 0 → 15 in 0,5 s |
| Gauß Out | Gaußscher Weichzeichner | Clip-Ende | Stärke 15 → 0 in den letzten 0,5 s |
| KarteIN | Transformieren | Clip-Anfang | Position von oben in die Bildmitte in 0,5 s |
| KarteOUT | Transformieren | Clip-Ende | Position aus der Bildmitte nach oben in den letzten 0,5 s |

Die **Konturfarbe** von Fancy In/Out ist in der Vorgabe fest auf ein dunkles Rotbraun (#752416) gesetzt. Das Panel überschreibt sie pro Artwork mit der Farbe aus dem Asset (Abschnitt 5.4). Premiere speichert sie als 16 Bit pro Kanal (ARGB).

**Play/Pause**

`Play-Pause.aep` enthält die Kompositionen „Play-Pause“ und „Pause“ aus PSD-Ebenen. Die Sequenzen „Play“ und „Pause“ im Projekt nutzen dieselbe Komposition ab 0 s bzw. ab 28,7 s, je 1,32 s lang. Vorschlag: beide Animationen einmal als ProRes 4444 mit Alpha rendern und als normale Clips einsetzen. Das spart Dynamic Link, rendert schneller und kann beim Projektwechsel nicht brechen. Das Panel kann aber auch weiterhin die verschachtelten Sequenzen verwenden.

**Grafik-Slots (austauschbare Vorlagen)**

Jede Grafik, die das Tool einsetzt, hängt an einem Slot in `vorlagen/grafiken.json`. Ein Slot legt fest: welche `.mogrt`-Datei, welches Textfeld darin gefüllt wird, die Textregel (z. B. `© {kuenstler}`, klein geschrieben), Spur und Dauer. Zum Austauschen legt ihr eine neue Vorlage ab und wählt sie im Tool. Das Tool liest die Felder aus der Vorlage aus, bietet sie zur Auswahl an und meldet, wenn das konfigurierte Textfeld fehlt.

| Slot | Text | Position | Spur | Dauer |
| --- | --- | --- | --- | --- |
| credit\_artwork | © künstler | immer oben mittig über dem jeweiligen Bild; bei zwei Bildern gleichzeitig je ein Credit über jedem Bild | V10 | wie das Artwork, Blende 0,42 s |
| credit\_amazon | © amazon studios | unten links | V9 | über Serienmaterial |
| credit\_musik | © interpret - titel | unten rechts | V11 | vorbereitet, aber aus (Musik wird von Hand gesetzt) |

Der Artwork-Credit ist in der Vorlage horizontal zentriert. Das Panel setzt ihn über die Position des Clips an die Oberkante des zugehörigen Bildes. Pro Bild wählt ihr im Tool eines von zwei Layouts:

- **Einzelbild:** mittig, wie bisher.
- **Doppelbild:** zwei Bilder gleichzeitig, beide mit der Spurmaske `Maske Quadrat.png` quadratisch zugeschnitten, ein Bild an fester Position links, eines rechts. Jedes bekommt seinen eigenen Credit oben mittig darüber und läuft auf einer eigenen Spur (V3/V4, Credits auf zwei Credit-Spuren). Die festen Positionen und Größen werden einmal aus eurer Vorlage übernommen und in den Einstellungen hinterlegt.

Die ersten Vorlagen erzeugt ein After-Effects-Skript (`erstelle_credit_vorlagen.jsx`) im Stil eurer bisherigen Textgrafiken: GrandCentral-Light, 20 pt bei 128 % Skalierung, weiß, Schlagschatten. Ein- und Ausblendung liegen in geschützten Bereichen und bleiben deshalb bei jeder Cliplänge gleich lang. Das AE-Projekt wird mitgespeichert, damit ihr die Gestaltung anpassen und neu exportieren könnt.

**After Effects**

- Keine Automatisierung in After Effects: Karten baut und animiert Danny von Hand.
- Das Tool liefert pro Karte den Platzhalterclip, das Kartenblatt mit Skizze und Hinweisen und die Daten als JSON. Danach rendert Danny die fertige Karte unter gleichem Namen in den Ordner `karten/final/` der Folge. Das Panel tauscht dann die Platzhalter aus.
- After Effects wird nur einmalig für die Credit-Vorlagen genutzt (Skript `erstelle_credit_vorlagen.jsx`).

## 7. Architektur, Datenmodell und Synchronisierung

Das Tool ist eine lokale Web-App: Ein Python-Server übernimmt Medienverarbeitung und Dateizugriff, die Oberfläche läuft im Browser unter `http://localhost`. Gemeinsamer Zustand liegt als viele kleine JSON-Dateien in einem OneDrive-Ordner.

**Komponenten**

| Komponente | Technik | Aufgabe |
| --- | --- | --- |
| Server | Python, FastAPI | Projekt-API, Dateizugriff, Jobs |
| Medien | ffmpeg, PySceneDetect | Proxys, Stills, Blur-Stills, Conform |
| Abgleich | faster-whisper, NumPy/SciPy | Transkription, Text- und Audio-Alignment |
| Bildindex | exiftool bzw. python-xmp, SQLite | XMP-Keywords und Credits durchsuchbar |
| Export | python-docx, eigenes JSON, FCP-XML | Word, Schnittpaket, Fallback-XML |
| Oberfläche | TypeScript, Svelte oder React, Canvas | Strang-Board, Editor, Kartenproxy |
| Premiere | UXP-Panel (Fallback CEP) | Rohschnitt bauen, Medien umschalten |

**Ordnerstruktur pro Folge (OneDrive)**

Alle Bibliotheksordner sind in den Einstellungen hinterlegt und relativ zum OneDrive-Stammordner gespeichert (bei Danny `F:\OneDrive`, unter macOS z. B. `~/Library/CloudStorage/OneDrive-Persönlich`).

```
F:\OneDrive\                         Stammordner (bei jedem anders, einmal einstellen)
  Videomaterial\
    Bilder\                          Bildbibliothek, Suche über Dateiname und Bridge-Tags
    Karten\                          Kartenbibliothek (Bilddateien) für Platzhalter
    Filme\Ringe der Macht\           Episoden: HQ-Dateien und Screener
    VFX\                             Kreise und andere Effekte
    Sound Effects\
    Programm-Vorgaben\               eure bestehenden Vorgaben (Play-Pause.aep, PSDs …)
    Project_Glorfindel\              Tool-Vorlagen: grafiken.json, MOGRTs,
                                     Effekt-Rezepte, Künstler-Datenbank
  Mythen-Archiv\Videos\
    S3 E1\                           ein Ordner pro Folge, Schema „S3 E1“
      glorfindel\                    projekt.json, quellen.json, szenen\, karten\,
                                     assets\ (Web-Bilder), aufnahme\abgleich.json
      Videoelemente\                 Standbilder 1.png … (wie bisher)
      Skript S3 E1.docx              Word-Export für die Aufnahme
```

Auch die **Videodateien liegen in OneDrive** (wie bisher unter `Videomaterial/Filme/...`). Das Projekt speichert alle Pfade **relativ zum OneDrive-Stammordner**, weil dieser bei jedem anders heißt (z. B. `E:\OneDrive` oder `C:\Users\Maurice\OneDrive`). Jeder Nutzer gibt seinen Stammordner einmal beim ersten Start an. Nur Arbeits-Proxys, Thumbnails und Caches liegen lokal und unsynchronisiert (z. B. `%LOCALAPPDATA%/Glorfindel bzw. ~/Library/Caches/Glorfindel`), weil jeder Rechner sie selbst erzeugen kann.

**Folgen für OneDrive**

- Videoordner der aktuellen Folge auf „Immer auf diesem Gerät behalten“ stellen. Sonst lädt OneDrive die Datei erst beim ersten Zugriff, und Proxy-Erzeugung oder Abgleich hängen minutenlang. Das Tool erkennt nur online verfügbare Dateien und zeigt einen Hinweis.
- Das Tool wartet, bis eine neue Videodatei vollständig synchronisiert ist (Dateigröße stabil, kein Sperrstatus), bevor es sie verarbeitet.
- Konformierte HQ-Dateien (ProRes/DNxHR) werden sehr groß. Sie werden daher nur auf dem Schnittrechner erzeugt und standardmäßig **nicht** in OneDrive abgelegt. Eine Option erlaubt das trotzdem.
- Zusätzlich zum Pfad speichert das Tool den Audio-Fingerabdruck. Wird eine Datei verschoben oder umbenannt, findet das Tool sie im OneDrive-Ordner wieder.

**Beispiel einer Szenendatei**

```json
{
  "id": "sz_07",
  "strang": "eregion",
  "reihenfolge": 7,
  "titel": "Celebrimbor in der Schmiede",
  "segmente": [
    {"in": 1834.208, "out": 1841.541},
    {"in": 1851.290, "out": 1859.040}
  ],
  "standbild": "ende",
  "kommentar": [
    {"sprecher": "philipp", "text": "Hier sehen wir ...",
     "anker": [{"asset": "art_0142", "von": 12, "bis": 31}]},
    {"sprecher": "danny", "text": "Und das passt zu ...",
     "anker": [{"karte": "k_eregion_moria", "von": 4, "bis": null}]}
  ],
  "status": "skript_fertig",
  "geändert_von": "maurice", "geändert_am": "2026-11-03T20:14:00"
}
```

Zeiten in Sekunden Episodenzeit, Anker als Wortindizes im Kommentar.

**Synchronisierung und Konflikte**

- Kleine Dateien pro Szene, Karte und Asset senken die Chance, dass zwei Personen dieselbe Datei gleichzeitig ändern.
- Der Server beobachtet den Ordner und lädt Änderungen anderer live nach.
- **Weiche Sperre:** Wer eine Szene bearbeitet, hinterlegt eine Sperrdatei mit Name und Zeit. Andere sehen „Maurice bearbeitet gerade“ und können trotzdem lesen.
- Erkennt das Tool eine OneDrive-Konfliktkopie (`Datei-PCNAME.json`), zeigt es beide Versionen zum Zusammenführen an.
- Zusätzlich wird jede Änderung in einem Änderungsprotokoll pro Folge festgehalten (wer, was, wann).

## 8. Verteilung, Plattformen und Installation

Das Tool wird als GitHub-Repository mit Releases verteilt und läuft auf Windows und macOS mit einem Starter, der den lokalen Server startet und den Browser öffnet.

**Plattformen**

| Person | System | Nutzung |
| --- | --- | --- |
| Danny | Windows | alle Phasen, inkl. Abgleich, Rohschnitt, Premiere-Panel, HQ-Conform |
| Maurice | Windows | Szenen, Skript, Kartenplatzhalter |
| Philipp | macOS | Skript, Word-Export, Sprecher; voller Funktionsumfang möglich |

**Installation**

- Repository-Struktur: `server/` (Python), `web/` (Oberfläche, im Release vorgebaut), `premiere-panel/`, `ae-scripts/`, `docs/`.
- Ein Installationsskript (`install.ps1` für Windows, `install.sh` für macOS) richtet Python über `uv` ein, installiert Abhängigkeiten und lädt ein statisches ffmpeg.
- Whisper-Modelle werden beim ersten Abgleich heruntergeladen. Nur wer den Abgleich ausführt, braucht eine starke GPU (CUDA unter Windows, Apple Silicon unter macOS).
- Start über eine Verknüpfung „Glorfindel starten“. Beim ersten Start: OneDrive-Projektordner und Bildordner auswählen, Name eintragen.
- Updates: Das Tool prüft GitHub-Releases und bietet ein Update per Klick an. Projektdateien tragen eine Schema-Version, Migrationen laufen automatisch.
- Premiere-Panel als `.ccx`-Paket im Release, Installation per Doppelklick bzw. über den Creative-Cloud-Plugin-Manager.

## 9. Meilensteine

Die Reihenfolge ist so gewählt, dass ab Meilenstein 1 jede Stufe sofort im Alltag hilft, auch wenn die späteren noch fehlen. Termine werden festgelegt, sobald der Starttermin von Staffel 3 und eure Verfügbarkeit klar sind.

0. **Technischer Vorab-Test (im Repository):** UXP-Panel in Premiere 2026 legt Sequenz an, setzt MOGRT-Text und -Position, Keyframes und Konturfarbe, verknüpft Medien neu. Credit-Vorlagen in AE erzeugen. *Ergebnis: Go/No-Go für das Panel.*
1. **Grundgerüst und Skript (MVP):** Projekt und Quellen, Arbeits-Proxys, Szenen-Editor mit Segmenten, Sprechern und Längenampel, OneDrive-Ablage mit Sperren, Word-Export und -Rückimport. *Nutzen: gemeinsames Skripten ab Folge 1.*
2. **Strang-Board:** Szenenerkennung, Zuordnung zu Strängen, Sortierung, Übernahme in den Editor.
3. **Aufnahme-Abgleich:** Whisper, Alignment, Retake-Erkennung, Prüfansicht, optional LLM-Nachkorrektur.
4. **Rohschnitt:** Standbilder, Schnittpaket, Premiere-Panel mit Play/Pause, Blur, Effekt-Rezepten, Credits über dem jeweiligen Bild, Markern. *Nutzen: der große Zeitgewinn.*
5. **HQ-Conform:** Doppelansicht mit Ankerpunkten von Hand, Kontrollansicht, Conform per ffmpeg, Panel „Auf HQ umschalten“. Später optional automatische Ankervorschläge.
6. **Bilder:** Suche über Dateiname und Bridge-Tags, Web-Import, Credits aus Dateinamen, Konturfarbe, Layout bei zwei Bildern, optional LLM-Bildvorschläge.
7. **Kartenplatzhalter:** Karte wählen, einzeichnen, einfache Keyframes, Hinweise, Platzhalterclip und Kartenblatt.
8. **Feinschliff:** Installer für Windows und macOS, Auto-Update, Änderungsprotokoll, Dokumentation.

Meilenstein 5 muss spätestens vor dem ersten finalen Render einer Folge stehen. Bis dahin kann der Screener bereits durchgehend genutzt werden.

## 10. Risiken, offene Fragen und benötigte Unterlagen

**Risiken**

| Risiko | Auswirkung | Gegenmaßnahme |
| --- | --- | --- |
| Premiere-Plugin-Schnittstelle kann MOGRT-Parameter oder Keyframes nicht setzen | Credits und Blenden nicht automatisierbar | Vorab-Test (M0), Fallback CEP/ExtendScript oder Credits als gerenderte Clips |
| HQ-Version weicht inhaltlich ab (anderer Schnitt, andere Logos) | Conform passt nicht überall | stückweise Zeitabbildung, Kontrollansicht pro Szene |
| OneDrive „Dateien bei Bedarf“: Bilder nur online | Bildindex langsam, Thumbnails fehlen | Index nur aus Metadaten/Sidecars, Ordner als „immer lokal“ markieren |
| OneDrive-Konflikte bei gleichzeitiger Arbeit | Datenverlust | kleine Dateien, weiche Sperren, Konflikt-Zusammenführung |
| Whisper-Fehler bei Eigennamen (Celebrimbor, Khazad-dûm) | schlechteres Alignment | Glossar als Prompt, Alignment toleriert Abweichungen |
| Weitergabe der Screener-Datei | Verstoß gegen Screener-Bedingungen | Freigaben des OneDrive-Videoordners auf euch drei beschränken |

**Offene Fragen**

- [x] Tool-Vorlagen unter `Videomaterial\Project_Glorfindel`
- [x] Zwei Bilder gleichzeitig: feste Positionen links und rechts, quadratisch mit Spurmaske zugeschnitten
- [x] Artwork-Credit: immer oben mittig über dem jeweiligen Bild
- [x] Ordner je Folge nach dem Schema „S3 E1“
- [x] Karten sind Bilddateien
- [x] ScaDS.AI: API-Schlüssel vorhanden, Modelle u. a. GLM und DeepSeek
- [x] Screener und HQ-Version werden von Hand ausgerichtet, automatische Vorschläge nur optional
- [x] Projektname: Projekt Glorfindel
- [x] Philipp arbeitet unter macOS
- [x] Längengrenze 9,5 s pro Segment, aus S2 E7 abgeleitet
- [x] Zwei Sprecher (Philipp, Danny) mit getrennten Aufnahmen
- [x] Bildraten: Folge 23,976 fps in 1920×800, Sequenz 60 fps in 1920×1080
- [x] Standbild = letzter Frame der vorherigen Szene
- [x] Screener sind Bildschirmaufnahmen mit teils schlechtem Ton
- [x] Musik und Musik-Credits: von Hand im Schnitt
- [x] Rahmenteile: außerhalb geplant, ggf. im Word-Dokument ergänzt
- [x] Künstlernamen: Dateiname reicht
- [x] Premiere Pro 2026

**Benötigte Unterlagen von Danny**

- [x] Premiere-Projektdatei von S2 E7 (ausgewertet, siehe Abschnitt 2)
- [x] `Play-Pause.aep` und die Effektvorgaben als `.prfpset`
- [ ] Testpaar für den Abgleich: `Folge 7 [ENGLISCH].mov` und die deutsche HQ-Folge S2 E7. Alternativ je ein Ausschnitt von 5 bis 10 Minuten, falls das Hochladen zu groß ist.
- [ ] Das Skript zu S2 E7 (Word) und die beiden Sprachaufnahmen, für den Test des Aufnahme-Abgleichs
- [ ] Ein paar Beispielbilder aus `Videomaterial\Bilder` samt Bridge-Tags
- [ ] Zwei oder drei Beispielkarten aus `Videomaterial\Karten`

Getestet wird erst im Repository. Die Unterlagen oben werden dort als Testdaten gebraucht.
