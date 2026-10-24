# Premiere-Bridge – Entwurf

Ziel (Danny): Ein hochwertiger Rohschnitt direkt in Premiere, der die Struktur des Ursprungsschnitts (S2 E7) trifft,
und ein Austausch Proxy → HQ, der Animationen, Effekte und manuelle Änderungen **nicht** verliert.

## Warum eine Bridge statt XML
FCP-XML kennt keine Effekte, Grafiken, verschachtelten Sequenzen mit Maske, Pause/Play-Animationen und gibt Medien nur als
Pfade weiter (offline bei Abweichung). Premiere 26.5 bietet aber eine offizielle UXP-API (`require('premierepro')`), mit der ein Plugin
Projekte lesen und ändern kann. Die Typdeklarationen liegen in `premierepro-26.5.d.ts` (Referenz, Version passt zu Premiere 26.5.2).

## Bausteine
```
Browser-App ──REST──► Glorfindel-Server ◄──WebSocket (127.0.0.1, Token)── UXP-Panel in Premiere
                          │ ffmpeg: konforme CFR-Referenz, HQ-Konform, Standbilder, Credit-PNGs
```
* **Hub** (`bridge.py`): genau ein Panel verbunden; `call(op, args)` mit Zeitlimit, Ereignisse (Fortschritt/Log) werden in Jobs gespiegelt.
* **Plan** (`premiere_plan.py`): macht aus dem Schnittpaket einen deklarativen Bauplan (Medien, Clips mit Spur/Zeit, Effekt-Rezepte, Marker).
* **Panel** (`premiere-panel/`): führt den Plan aus. Jede Operation ist einzeln abgesichert; Fehler stoppen den Bau nicht, sondern landen im Bericht.
* **Tausch**: Die Episode liegt in einer **verschachtelten Episoden-Sequenz**. Beim Wechsel Proxy → HQ wird nur die Datei dieses
  einen Projektelements getauscht (`ClipProjectItem.changeMediaFilePath`); alle Clips, Effekte, Ein-/Ausblendungen bleiben. Standbilder
  werden unter **gleichem Dateinamen am gleichen Ort** ersetzt (Sicherung des Proxy-Stands) und mit `refreshMedia()` neu geladen.

## Konsistenz Bild ↔ Standbild (Ursache der Abweichungen)
Der Bildschirmmitschnitt hat variable Bildrate und Letterbox. Premiere und ffmpeg rechnen darauf unterschiedlich. Deshalb entsteht **eine
konforme Referenz** (konstante Bildrate, zugeschnitten, ein Ton). **Dieselbe Datei** liegt in Premiere in der Episoden-Sequenz **und**
liefert die Standbilder. Die HQ-Datei wird auf dieselbe Zeitachse konformiert → Tausch ohne Versatz.

## Struktur des Ursprungsschnitts (aus `Mythen - S2 E7_1.prproj` gelesen)
Hauptsequenz „MythenAusMittelerdeVideo“: 14 Video- / 16 Audiospuren.
| Spur | Inhalt |
| --- | --- |
| V1 | Szenen (verschachtelte „S2 E7 Sequenz“) und Standbilder |
| V2 | Einstellungsebenen mit Gaußschem Weichzeichner (Blur), Intro, Werbung |
| V3/V4 | Artworks (verschachtelte Sequenzen; Effekte: Drop Shadow, Transformieren, 2× Kanten aufrauen = Fancy In/Out) |
| V7 | Pause-/Play-Animation (verschachtelte Sequenzen), Mitglieder-PSDs |
| V9 | Credit „© amazon studios“ (Grafik) |
| V10 | Artwork-Credits (Grafik), Abo-Animation |
| V11 | Musik-Credits, V12 Bauchbinde / Pop-ups |
| A2/A3 | Sprecher Philipp / Danny |
| A4 | Originalton der Szenen |
| A10 | Musik |
Artwork-Sequenz: Bild + „Maske Quadrat.png“ als Track-Matte (Legacy Key Track Matte).

## Umgesetzte Entscheidungen (Stand: Bridge v0.2)
Die Premiere-API (26.5) kann keine Spuren hinzufügen, keine Titel/Grafiken, keine Einstellungsebenen, keine Audio-Überblendungen und keine
Effektvorgaben (.prfpset) anwenden. Statt Vorlagen-Projekt wurde deshalb so gelöst:

| Baustein | Lösung | Warum |
| --- | --- | --- |
| Hauptsequenz mit 14 V / 16 A Spuren | Die App erzeugt eine **Sequenz-Vorgabe** (.sqpreset) aus Adobes „AVCHD 1080p60“ mit der Spuranzahl; `createSequenceWithPresetPath` | keine Vorlage nötig, Spuren garantiert da |
| Episode (tauschbar) | **Konforme Referenz** (CFR, zugeschnitten) in einer **verschachtelten Episoden-Sequenz** (`createSequenceFromMedia`) | Tausch Proxy → HQ = ein `changeMediaFilePath` |
| Standbilder | aus **derselben Datei** wie die Sequenz, Segmentgrenzen auf dem Episodenraster; gleiche Dateinamen → Austausch in place + `refreshMedia()` | Bild und Standbild stimmen exakt überein |
| Pause/Play | `importAEComps` aus `Play-Pause.aep` (Komposition ab 28,7 s bzw. 0 s, je 1,32 s) auf V7 | wie im Original (Dynamic Link) |
| Artwork | Bild/Wallpaper direkt auf V3/V4 mit **Zuschneiden (quadratisch)**, Bewegung (Skalierung/Position), Schlagschatten, Transformieren-Zoom, 2× Kanten aufrauen (Fancy Out/In) – Werte aus dem echten Schnitt | Track-Matte-Sequenzen sind per API nicht zuverlässig reproduzierbar; gleiches Ergebnis |
| Blur | Gaußscher Weichzeichner **am Standbild** (0 → 15, Rampen 0,5 s) statt Einstellungsebene | sichtbar ist Blur nur auf dem Standbild darunter; keine Vorlage |
| Credits | **PNG mit Alpha** (GrandCentral-Light, weiß, Schatten) an den Originalpositionen, Ein-/Ausblendung über Deckkraft; gleichzeitige Artworks → Spur V10/V13 | Text-Grafiken sind per API nicht erzeugbar |
| Marker | `Markers.createAddMarkerAction` | – |
| Zeitraster | Hauptsequenz 60 fps, Segmentgrenzen auf 24000/1001 | keine Teilbild-Überlappungen |

Nicht möglich / offen: Audio-Überblendung „Konstante Leistung“ (API bietet nur Video-Übergänge), Credits als editierbarer Text (nur über ein MOGRT mit Textfeld).

## Sicherheit
WebSocket nur auf 127.0.0.1; Token (Datei im lokalen App-Ordner) wird vom Panel per HTTP beim App-Server geholt (Browser-Seiten können die
Antwort wegen fehlender CORS-Freigabe nicht lesen); Browser-Origins (http/https) werden für den WebSocket abgelehnt. Das Panel führt nur
benannte Operationen aus (keine freie Skriptausführung).
