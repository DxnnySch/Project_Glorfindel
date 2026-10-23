# Projektheft Teil 3: Segment-Workflow und Bedienung auf einen Blick

Stand 23.10.2026 · Anlass: Rückmeldung nach dem Test mit echten Daten (Bilder/Karten, Strang-Board, Kommentare).

## 1. Der Ablauf, so wie er wirklich ist

1. **Folge laden und verarbeiten:** Episode importieren, Proxy erzeugen, Dialog der Episode transkribieren, Szenen vorschlagen.
2. **Nach Strängen aufteilen:** Zusammengehörige Handlung wird am Stück besprochen (erst alle Eregion-Stellen, dann alle Moria-Stellen), auch wenn die Episode anders verläuft.
3. **Durchgehen und besprechen** (z. B. Maurice): Szene für Szene die **Stellen markieren**, die wirklich ins Video kommen (Segmente), je Segment einen **Kommentar** schreiben, **Bilder und Karten** direkt dort wählen/anlegen.
4. **Reihenfolge anpassen:** Stränge verschieben, aber auch einzelne Szenen neu einsortieren (wenn Stränge zusammenlaufen).
5. **Ausgeben:** Nur markierte Segmente kommen ins Video und ins Word. Dazu ein reines **Sprecherskript** für die Aufnahme.

**Grundregel:** Kommentare gehören zu **Segmenten**, nicht zur Szene.

## 2. Anforderungen

### A. Datenmodell und Ausgabe
- A1 Segment hat eine **Beschreibung**: der gesprochene Dialog der Stelle (automatisch aus dem Transkript) plus eine eigene, editierbare **Notiz** für Kontext.
- A2 **Kommentar je Segment** (Rückwärtskompatibel: alte Kommentare hängen am letzten Segment).
- A3 **Rohschnitt:** Segment, danach – wenn es einen Kommentar hat – Standbild mit Kommentar; Segmente ohne Kommentar laufen als Montage weiter. Standbild bleibt für das letzte Segment einer Szene.
- A4 **Word-Arbeitsskript** (Rundlauf): gegliedert nach Szene → Segment → Kommentar.
- A5 **Sprecherskript** (nur Vorlesen): Regieanweisungen (Beschreibung/Notiz des Segments, Dialog), Kommentartext ungestört, Bild-/Kartenhinweise als lesbare Randnotiz statt Markierungen im Text. Vom Sprecher frei änderbar, ohne Rückwirkung.
- A6 **Reihenfolge:** Stränge in der Reihenfolge verschieben und einzelne Szenen frei einsortieren (manueller Ablauf), jederzeit zurück zu „automatisch nach Strängen“.

### B. Dialog der Episode
- B1 Episode transkribieren (Whisper lokal oder ScaDS auf Anweisung), Sprache einstellbar/automatisch; Ergebnis mit Wortzeiten gespeichert.
- B2 Im Szenen-Editor: Dialog als mitlaufender, klickbarer Text; Wörter markieren → „Als Segment übernehmen“ (Zeiten aus den Wörtern).

### C. Szenen-Editor (Bedienung auf einen Blick)
- C1 Szene anklicken springt im Player zur Stelle.
- C2 In der Liste sofort sichtbar: Anzahl Segmente, Kommentare je Sprecher, Vorschaubilder der eingeblendeten Bilder/Karten.
- C3 Im Player: Szenenbereich, Segmente und Kommentarmarken auf der Zeitleiste; Segment abspielen mit klarem Play-Symbol.
- C4 Bilder/Karten **direkt im Kommentar** wählen: Bibliothek mit Vorschaubildern und Suche, neue Karte anlegen und einzeichnen.
- C5 Im Kommentar ist **farbig markiert, von welchem bis zu welchem Wort** ein Bild/Karte eingeblendet wird; Vorschaubild am Kommentar.
- C6 Jede Ansicht **merkt sich ihren Zustand** (Filter, Auswahl, Scrollposition, gewählte Quelle …).

### D. Board, Karten, Bilder
- D1 Board: Szene in **eigenem Player** ansehen; **Mehrfachauswahl** (Strg/Umschalt) und gemeinsames Zuordnen/Ziehen.
- D2 Karten: Markierungen **farblich einstellbar**; Platzhalter/Animation **abspielbar** (Vorschau im Browser und gerenderter Clip).
- D3 Bilder: Vorschau für animierte `.mov` zuverlässig, Thumbnails überall.

## 3. Nicht-Ziele
Keine Änderung am Premiere-Panel-Stand; Audio/Mehrspur-Schnitt weiter in Premiere.
