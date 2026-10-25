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

## Gemessene Eigenheiten von Premiere 26.5.2 (per `probe.bin`, `probe.place`, Selbsttest)
- **Jede Änderung braucht `project.lockedAccess(() => project.executeTransaction(...))`**; sonst „Requires locked access“ oder „script object is no longer valid“. Aktionen werden innerhalb des Callbacks erzeugt (`core.tx`).
- **Alle API-Objekte (auch das Projekt-Handle) sind nach einer Änderung ungültig.** Ein Projekt-Handle pro „Epoche“ (`core.getProj`/`invalidate`), alles andere frisch holen.
- **Schnitt-Aktionen (`createOverwriteItemAction`, `createSequenceFromMedia`) nehmen nur rohe `ProjectItem`s**; ein per `ClipProjectItem.cast` umgewandeltes Element wird mit „Invalid parameter“ abgelehnt. In/Out-Punkte (`createSetInOutPointsAction`) gehören dagegen zum `ClipProjectItem`.
- Sequenz-Vorgabe-Pfade nur mit Backslashes (`C:\…`), sonst „Preset file is invalid“.
- Effekt-Match-Namen (deutsche Oberfläche): Zuschneiden `AE.ADBE AECrop`, Transformieren `AE.ADBE Geometry2`, übrige wie im Ursprungsprojekt. Komponentenreihenfolge im Clip: Deckkraft, Bewegung. Bewegung: Position, **Skalieren** (nicht „Skalierung“), Skalierungsbreite …
- Mehrere Parameter heißen gleich („Zufallsparameter“): Position in der Liste gewinnt vor dem Namen (`findParam`).
- Keyframe-Zeiten sind clip-relativ (`keyframeOrigin: clipanfang`), Farben 0..1.
- Diagnose ohne Neubau: `POST /api/bridge/call` mit `probe.bin`, `probe.place`, `sequence.dump`, `introspect`; Selbsttest `POST /api/bridge/selftest`. Panel-Änderungen wirken erst nach einem Premiere-Neustart.

## Umbau nach Rückmeldung (Panel 0.4.0)
- **Artworks** liegen wie im Ursprungsschnitt in je einer verschachtelten Sequenz „Artwork NN <Name>“ (Vorgabe `Glorfindel-Artwork.sqpreset`, 5 Videospuren): Bild auf V3, Maske (`vorlagen/masken/Maske Quadrat.png`) auf V5, am Bild der Effekt „Spurmaske-Key“ (Maske: Spur 5, Compositing mit Alpha). Position/Größe stehen in den Motion-Werten von Bild und Maske, **alle Effekte (Schlagschatten, Zoom, Fancy In/Out) liegen auf dem Sequenz-Clip** in der Hauptsequenz. Maskengröße = Zielkante/800 · 100 %, Bildskalierung = Zielkante/kürzeste Bildseite · 100 %.
- **Pause/Play** aus `Videomaterial/VFX/Pause.mov`; Play ist daraus per ffmpeg rückwärts erzeugt (`Play.mov`, ProRes 4444 mit Alpha, einmalig im Cache). Die After-Effects-Komposition ist nur noch Rückfall.
- **Karten** bekommen „Transformieren“ mit Position-Keyframes wie die Vorgaben KarteIN/KarteOUT (0,5 s von oben hinein/hinaus). Premiere-Vorgaben (.prfpset) lassen sich per UXP nicht anwenden; ihre Werte sind in `vorlagen/premiere_rezepte.json`/Plan übernommen.
- **Gauß In/Out** als Einstellungsebene auf V2 (je Artwork-Spanne ein Clip mit Gaußscher Weichzeichner 0→15→0). Die API kann keine Einstellungsebene anlegen, nur eine vorhandene platzieren: einmal **Datei → Neu → Einstellungsebene** (Name „Einstellungsebene“) im Projekt anlegen. Fehlt sie, liegt der Weichzeichner ersatzweise direkt am Standbild (Hinweis im Bericht).
- **Schwarzstreifen** (V8, über die ganze Länge, unter den Credits): PNG 1920×1080 mit 13 % schwarz oben/unten (`Schwarzstreifen.png`).
- **© amazon studios** wird an den Künstler-Credits aufgetrennt und ist nie gleichzeitig mit ihnen zu sehen.

## Effekt-Bibliothek aus den .prfpset-Vorgaben
Premiere lässt sich per UXP nicht anweisen, eine .prfpset anzuwenden. Stattdessen liest `prfpset.effect_library` die Vorgaben direkt aus `Videomaterial/Programm-Vorgaben/PremierePro` (Einstellung `premiere.presets_dir`) und macht daraus Rezepte: alle Parameter mit Index/Name/Wert, Keyframes in Sekunden – am Einblendpunkt der Vorgabe (AnchorInPoint) am Clipanfang, am Ausblendpunkt (AnchorOutPoint) am Clipende (negativ). Das ergibt dieselben Werte wie im Ursprungsschnitt gemessen (Fancy Out −0,5333/−0,5167/−0,0167 s, Zoom 100→240 über 120 s).
- Ids: `fancy_in/out`, `gauss_in/out`, `karte_in/out`, `kreis_in/out`, `pop_in/out`, `right_in`, `trans_in/out`, `zoom_schnell`, `zoom_langsam` (Vorgaben mit mehreren Effekten, z. B. „Übergänge“, werden nicht übernommen).
- Einstellungen `premiere.artwork_effects` (Standard: drop_shadow, zoom_schnell, fancy_out, fancy_in) und `premiere.map_effects` (karte_in, karte_out) wählen die Effekte; `zoom_langsam` o. ä. lassen sich dort eintragen.
- Ist der Ordner nicht erreichbar, gilt der mitgelieferte Stand `vorlagen/effekt_bibliothek.json` (neu erzeugen: `python scripts/import_presets.py <Ordner>`).
- Gauß In/Out (`AE.Impact_Blur_FX`, Parameter „Stärke“ 0→15) bestimmt den Weichzeichner (Einstellungsebene bzw. Rückfall am Standbild).

## HQ ohne Umwandlung („direkter Einsatz“)
Ist die Zeitabbildung einer HQ-Quelle eine reine Verschiebung (HQ-Zeit = Referenzzeit + Offset, Geschwindigkeit gleich) und hat die HQ-Datei eine native Bildrate (23,976/24/25/29,97/30), dann
- stellt das Tool die Bildrate der Folge auf die der HQ-Datei (z. B. 24 fps),
- konformt die **Referenz** (klein, H.264) auf diese Bildrate und legt sie um den Offset auf die Zeitachse der HQ-Datei (Schwarz davor), alle Segment- und Standbildzeiten werden um denselben Offset verschoben,
- und der Tausch zu HQ setzt die **unveränderte HQ-Datei** ein – kein Conform, keine Neukodierung der Episode. Bildrate der HQ-Datei und der Referenz müssen gleich sein (Prüfung vor dem Tausch).
Sonst (Tempoänderungen, andere Bildrate) bleibt der bisherige HQ-Conform mit konstanter Bildrate der Folge.

## Gemessen: Dateitausch (`changeMediaFilePath`) und Tonformat
Ein Element, das in einer Sequenz verwendet wird, lässt sich nur gegen eine Datei **mit demselben Tonformat** austauschen (probe.swap, Premiere 26.5.2): AAC→AAC, AAC→PCM, E-AC-3→E-AC-3 (auch Stereo→5.1) gehen; **AAC→AC-3 oder E-AC-3 wird mit `false` abgelehnt**, `override`/`lockedAccess` ändern daran nichts. Die Kompatibilitätsprüfung betrifft nicht Bildrate (24 ↔ 24,0002), Länge oder Kanalzahl. Darum bekommt die konforme Referenz den Tonkodierer der HQ-Datei (`premiere_media.audio_for`: ac3/eac3 → E-AC-3, sonst AAC); `swap()` prüft das vorab und meldet es verständlich.
