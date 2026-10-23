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

## Grenzen der Premiere-API (26.5) und Umgang damit
| Fehlt in der API | Umgang |
| --- | --- |
| Spuren hinzufügen | Hauptsequenz kommt aus einer **Vorlagen-Sequenz** mit allen Spuren (Klon) |
| Textgrafik/Titel erzeugen | Credits als **PNG mit Alpha** (immer) oder **MOGRT** (wenn konfiguriert, `insertMogrtFromPath`) |
| Audio-Überblendungen „Konstante Leistung“ | wird im Bericht gemeldet; Standard-Blenden von Hand/Vorgabe |
| Einstellungsebene erzeugen | aus der Vorlage übernommen (Projektelement „Einstellungsebene“) |
| Effekt-Vorgaben (.prfpset) anwenden | Rezepte: Effekt per `VideoFilterFactory.createComponent`, Parameter/Keyframes per `ComponentParam` |

## Sicherheit
WebSocket nur auf 127.0.0.1; Token (Datei im lokalen App-Ordner) wird vom Panel per HTTP beim App-Server geholt (Browser-Seiten können die
Antwort wegen fehlender CORS-Freigabe nicht lesen); Browser-Origins (http/https) werden für den WebSocket abgelehnt. Das Panel führt nur
benannte Operationen aus (keine freie Skriptausführung).
