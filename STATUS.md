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

## Offen
- Review 2, noch nicht umgesetzt: Rohschnitt warnt nicht bei „veraltet“; Papierkorb ohne Übersicht in der UI; Aufnahme-Grenzen nur tippbar (Wellenform-Ziehen); `@`-Autovervollständigung für Bilder im Text; ffmpeg-Jobs nicht abbrechbar; Zeitfelder ohne Bereichsprüfung; ScaDS-Netzfehler beim Abgleich noch technisch formuliert.
- Premiere-UXP-Panel und AE-Skript sind nur Skelette (nicht testbar ohne Premiere), End-to-End mit echter S2-E7-Konformierung.
