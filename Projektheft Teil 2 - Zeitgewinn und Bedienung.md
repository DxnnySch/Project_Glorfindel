# Projektheft Teil 2: Zeitgewinn und Bedienung

Stand 22.10.2026 · Ergänzt das Projektheft (Teil 1) um das, was ein unabhängiger Testdurchgang als fehlend oder zeitraubend gefunden hat.
Grundlage: `docs/review/2026-10-22-test-review.md` (Detailbericht mit Reproduktionsschritten) und eine eigene Analyse unten.

## 1. Ergebnis der Analyse

**Was gut ist:** Der Kernablauf trägt (Quellen → Szenen → Aufnahme → Rohschnitt), die Datenhaltung ist robust, die Oberfläche ist ruhig und verständlich.

**Was Zeit kostet (nach Häufigkeit × Dauer):**
1. *Skript schreiben ist der häufigste Weg* (49 Szenen pro Folge). Jeder unnötige Klick multipliziert sich: keine Suche/Filter, keine Tastenkürzel zum Szenenwechsel, Bildzuordnung per Wortnummer, Kopfzeile verbraucht den Platz.
2. *Warten ohne Bescheid:* Proxys müssen von Hand angestoßen werden, Aufträge verschwinden nach einem Seitenwechsel, es gibt weder Abbrechen noch eine Liste laufender Aufgaben.
3. *Zeitcodes abtippen:* Ankerpunkte und Aufnahmegrenzen werden getippt, nicht per Klick auf das Bild bzw. die Wellenform gesetzt.
4. *Unklarer Stand:* Niemand sieht auf einen Blick, was als Nächstes zu tun ist; „veraltet“ wird nie gesetzt, sodass der Rohschnitt stillschweigend alte Aufnahmezeiten nutzt.
5. *Nacharbeit im Schnitt:* Kartenplatzhalter ohne Inhalt, Rahmenteile ohne Dauer, Word-Marker nur als IDs – alles Dinge, die später in Premiere per Hand ergänzt werden müssen.

**Fehler aus dem Test (behoben):** Datenverlust beim Autosave (kritisch), Rohschnitt-Abbruch bei „nicht gefunden“-Blöcken, Segmente hinter dem Episodenende, unverständliche Fehlermeldungen, ungeprüfte Folgennummern, „Automatisch“ sendete Audio an ScaDS, Zeitfelder rechneten in Bildern statt Sekunden.

## 2. Ziele von Teil 2
- **Z1 Tempo beim Schreiben:** Eine Szene in unter 30 s anlegen, zuordnen und mit Bildern versehen, überwiegend per Tastatur.
- **Z2 Nie raten, was als Nächstes dran ist:** Cockpit mit konkreter „Als Nächstes“-Liste und ehrlichem Status (inkl. „veraltet“).
- **Z3 Kein Zeitcode-Tippen:** Anker, Segmente, Aufnahmegrenzen per Klick/Taste auf Bild bzw. Wellenform.
- **Z4 Wartezeiten sichtbar und im Hintergrund:** Aufgabenleiste, Auto-Proxy, Abbrechen.
- **Z5 Weniger Nacharbeit in Premiere:** Karten mit Inhalt, Rahmenteile mit Dauer, lesbares Word-Skript.
- **Z6 Sicher zusammenarbeiten:** Versionsprüfung beim Speichern, Live-Hinweise, Papierkorb/Rückgängig.

## 3. Anforderungen (priorisiert)

### A. Tempo & Orientierung (Welle 1)
- A1 Aufgabenleiste: laufende und letzte Aufträge global sichtbar (auch nach Seitenwechsel), Fehler mit „Details kopieren“, Abbrechen wo möglich.
- A2 Proxy wird nach dem Quellimport automatisch erzeugt.
- A3 Szenenreihenfolge: Knöpfe Hoch/Runter/Anfang/Ende, Strg+↑/↓ im Editor; Anzeige der Ausgabenummer; Strang-Reihenfolge änderbar; Strang löschen warnt bei Nutzung.
- A4 Editor: Suche und Filter (Strang, Status, Ampel, „ohne Segment“), Strg+Alt+↑/↓ Szenenwechsel, Strg+Enter neuer Block, Alt+1/2 Sprecher, J/K/L, Strg+S, Warnung beim Verlassen mit ungespeicherten Änderungen, Zeitstempel „Gespeichert 14:32“, kompakte einzeilige Kopfzeile.
- A5 Dialoge: Autofokus, Enter bestätigt, „Neue Folge“ schlägt die nächste Nummer vor.
- A6 Status „veraltet“: Änderung an Text/Sprecher/Segmenten einer abgeglichenen Szene setzt „veraltet“; Hinweis in Übersicht und Rohschnitt; Neuabgleich verarbeitet nur betroffene Szenen.
- A7 Cockpit: „Als Nächstes“-Liste mit Zahlen und Sprungzielen, echte Phasenstände.
- A8 Papierkorb: gelöschte Szene wenige Sekunden rückgängig, danach 30 Tage in `.papierkorb`.

### B. Material & Aufnahme (Welle 2)
- B1 Anker setzen mit zwei Playern (Referenz + Quelle), Bildschritt, „Hier verknüpfen“.
- B2 Bild-/Kartenanker per Textauswahl im Kommentar (Wörter markieren → Popup mit Thumbnails).
- B3 Aufnahme-Prüfansicht: „nur Unsichere“, Sprung zur nächsten, Taktwahl (Retake-Umschaltung), spontane Ergänzungen anzeigen/übernehmen, Zeiten in Sekunden mit Millisekunden, Klick in Wellenform.
- B4 Word: Marker mit Namen, Schalter „Marker ausblenden“, Reihenfolge nach Szenen oder Strängen, lesbare Schrift, Sprecher farbig; nach Import Änderungsliste mit Titeln.
- B5 Freie Blöcke / Rahmenteile in der Oberfläche mit Dauer (Intro, Werbung, Outro), im Rohschnitt als Platzhalter exakter Länge.
- B6 Bilder: Tag-Chips, „schon in Folge“, Entfernen, Künstler-Datenbank-Editor, Ordnernamen in der Suche.
- B7 LLM-Hilfen sichtbar: Namensprüfung im Kommentarblock, Bild-Suchbegriffe, Kartenvorschlag, Titelvorschlag; „Verbindung testen“.

### C. Tiefe Funktionen (Welle 3)
- C1 Kartenproxy-Editor: Marker, Beschriftung, Pfeil/Pfad, Region, Kamerarahmen, einfache Keyframes, Hinweise; Blatt-Download.
- C2 Strang-Board als Filmstreifen: Drag&Drop auf Stränge, Grenzen verschieben, teilen/zusammenführen.
- C3 Synchronisation: Versionsprüfung beim Speichern (409 + Diff-Dialog), Live-Hinweise im Editor, Sperrenanzeige live.
- C4 Rohschnitt-Vorschau: Zeitleiste aus `schnitt_vN.json` im Browser, Warnungen gespeichert und mit Sprung zur Szene, Ordner/Pfad anzeigen.
- C5 Update-Prüfung (GitHub-Releases) und Erststart-Assistent.
- C6 Premiere-UXP-Panel und AE-Credit-Skript als dokumentierte Best-Effort-Skelette (nicht testbar ohne Premiere).

## 4. Abnahmekriterien
- Alle Fehler des Reviews haben einen Regressionstest oder eine Browserprüfung.
- Jede Funktion hat: Servertest oder Browser-Smoke-Test; kritische Pfade (Speichern, Abgleich, Rohschnitt) sind getestet.
- Keine neue Abhängigkeit ohne Not; weiterhin ohne Build-Schritt installierbar.
- Texte deutsch, Nutzertext nur über `textContent`.

## 5. Offene Punkte
Siehe `FRAGEN.md` (F9 ff.). Standardwerte gelten bis zur Antwort.
