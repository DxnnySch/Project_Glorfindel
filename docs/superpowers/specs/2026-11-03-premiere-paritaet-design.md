# Premiere-Parität: Bridge-Schnitt wie der handgemachte Schnitt

## Ziel
Der von der Bridge gebaute Rohschnitt soll **strukturell** so aufgebaut sein wie Dannys handgemachter Schnitt
(`F:\OneDrive\Mythen-Archiv\Videos\S2 E7\Mythen - S2 E7_1.prproj`): gleiche Objektarten, gleiche Übergänge, gleiche
Effektketten, alles in Premiere weiter editierbar. Inhalt und Timing dürfen abweichen; **Aufbau und Bearbeitbarkeit** nicht.
Nicht-Ziel: neue Funktionen der Oberfläche. Anti-Ziel: Zustände, die sich in Premiere nicht mehr sauber ändern lassen
(Zeitkopien, Rasterbilder statt Text, eingebrannte Blenden).

## Messung am Ursprungsschnitt (Hauptsequenz `MythenAusMittelerdeVideo`, `scripts/parity_report.py`)
| Befund | Zahl | Bridge vorher |
|---|---|---|
| Videoübergänge **Cross Dissolve** (`AE.ADBE Cross Dissolve New`), 0,42 s (25 Bilder @60) am Anfang **und** Ende jedes Überlagerungsclips (Artwork V3/V4, Mitglieder V5–V7, Texte V9/V10: je 27–33 Paare) | 562 | keine (Credits: Deckkraft-Keyframes, Artwork: gar nichts) |
| Audioübergänge **Constant Power** 1,0 s auf dem Serienton (A4: Anfang, Ende und Mitte der Schnitte) und der Musik (A10) | 342 | keine |
| Sprecherspuren (A2/A3, Aufnahmen) | ohne Übergang | stimmt |
| Credits/Texte: native Essential-Graphics-Textclips (`AE.ADBE Text`), links unten (x≈0,029) bzw. rechts unten (x≈0,976), y≈0,956, Skalierung 128 % | 66 | PNG (nicht editierbar) |
| Serienclips: Instanzen der Episoden-Sequenz (`S2 E7 Sequenz`) | 120 | stimmt (verschachtelte Episoden-Sequenz) |
| Artwork: verschachtelte Sequenz + Schlagschatten, Transformieren, 2× Kanten aufrauen | 25+8 | umgesetzt |

## Umsetzung (Wellen, je mit Tests und eigenem Commit)
1. **Übergänge.** Plan trägt je Clip `uebergang: {ein, aus}` (Sekunden, Cross Dissolve) und Serienton `ton_blende`. Panel setzt
   Videoübergänge mit `createAddVideoTransitionAction` (Start/Ende, einseitig). Regeln und Maße stehen in
   `vorlagen/premiere_rezepte.json` → `uebergaenge` (gemessen, nicht geraten).
   *Audio:* die UXP-API kennt nur Videoübergänge. Gleichwertiger Ersatz: **Lautstärke-Keyframes mit Gleichleistungs-Kurve**
   (Konstante Leistung: Pegel = 20·log10(sin/cos)) am Anfang/Ende der Serien-Tonclips; bleibt in Premiere frei verschiebbar.
   Der Selbsttest meldet, ob die Premiere-Version Audioübergänge anbietet (`getVideoTransitionMatchNames`).
2. **Editierbarer Text.** Credits als Motion-Graphics-Vorlage (`.mogrt`, `insertMogrtFromPath`), Text per Parameter gesetzt;
   Ort/Größe aus dem Ursprungsschnitt. Rückfall auf PNG, wenn keine Vorlage da ist oder das Einsetzen scheitert (mit Hinweis).
3. **Paritätsbericht** (`scripts/parity_report.py`, Skill `premiere-paritaet`): vergleicht ein Referenzprojekt mit einem
   Plan oder einem von der Bridge gebauten Projekt nach Kategorien (Übergänge, Text, Effektketten, Spuren) und gibt Lücken aus.
   Dieser Bericht ist der Fortschrittsmesser für alle weiteren Verbesserungen.

## Grenzen (ehrlich)
- Nicht in echtem Premiere ausführbar durch Claude: alles wird gegen die API-Doku (`docs/bridge/premierepro-26.5.d.ts`) und die
  strenge Panel-Nachbildung getestet; die Abnahme in Premiere steht als Liste in `STATUS.md`.
- Musik (A10/A11) kennt die App nicht; Musik-Übergänge entstehen erst, wenn Musik im Plan vorkommt.
