# Teil 3 – Design (Segment-Workflow)

## Datenmodell (rückwärtskompatibel)
- `Segment.notiz: str = ""`
- `CommentBlock.segment: int | None = None` – Index des zugehörigen Segments; `None` = letztes Segment (Altdaten, neue Blöcke ohne Zuordnung).
- `Scene.bereich: [start, end] | None` – Zeitbereich der Szene in der Referenz (vom Board), für „Springen“ und Dialoganzeige.
- `Project.ablauf: list[str]` – manuelle Gesamtreihenfolge der Szenen-IDs; leer = automatisch (Stränge). Neue/fehlende Szenen werden an die automatische Reihenfolge angehängt.
- `Project.dialog_sprache: str = "auto"`.
- Dialog: `glorfindel/dialog.json` `{sprache, quelle, words:[{w,start,end}]}`.
- Kartenelemente: `farbe: "#rrggbb"` optional.

## Rohschnitt
`segment_of(block, scene)` löst den Index auf. `still_plan(scene)` = Segmente mit Kommentar plus letztes Segment (wenn `standbild != aus`). `still_times()` und `build_package()` nutzen dieselbe Funktion, damit die Nummern der Standbild-Dateien übereinstimmen (`{k}.png` laufend über alle Szenen).
Je Standbild: Pause-Animation davor, Kommentarblöcke des Segments nacheinander, Artworks, bei Bedarf Verlängerung. Credit „Amazon“ je Szene vom Szenenanfang bis zum letzten Standbild. Play-Animation nach dem letzten Standbild der Szene.

## Word
- Arbeitsskript: Szenenüberschrift (`⟦sz:ID⟧`) → pro Segment Zwischenüberschrift `Segment k · TC · Notiz ⟦sg:k⟧` → Blöcke. Import liest `⟦sg:k⟧` und setzt `block.segment`; ohne Marke wie bisher.
- Sprecherskript (`export_speaker_docx`): keine Marken; Regie-Zeile je Segment (Notiz, Dialog), Kommentartext, Randnotiz „Bildeinblendung: … (bei „…“)“.

## UI
Szenen-Editor neu aufgebaut (Dialog-Panel, Segmentkarten mit Kommentaren, Bild-Picker-Modal, markierter Text per Spiegel-Overlay). `remember()` speichert Ansichtszustand in `sessionStorage` je Folge. Board mit Auswahlmodell (Set), Vorschau-Modal. Neue Ansicht „Ablauf“ für die Reihenfolge.
