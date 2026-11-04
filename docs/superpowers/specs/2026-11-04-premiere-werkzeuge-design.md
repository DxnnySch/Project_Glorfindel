# Premiere-Werkzeuge (Kurzbefehl-Leiste im Panel)

Stand 2026-11-04. Entstanden in einem autonomen Lauf (Danny nicht erreichbar); alle Entscheidungen sind meine Entscheidungen und stehen als Standardwert in `FRAGEN.md` (F12).

## Ziel
Aufgaben, die beim Schneiden der Serienvideos immer wieder vorkommen und in Premiere viele Klicks kosten, werden zu Knöpfen im Panel „Glorfindel Bridge“. Sie wirken auf die **Auswahl in der Zeitleiste** (bzw. den Abspielkopf) und benutzen dieselben Regeln wie der Rohschnitt-Bau (Effektrezepte aus den `.prfpset`, Maske + Spurmaske, Credit-Vorlagen, Überblendung 0,42 s). Wer von Hand nacharbeitet, bekommt dadurch dasselbe Ergebnis wie der automatische Bau.

Nicht-Ziele: neue Schnittfunktionen, die Premiere selbst gut kann (Ripple-Löschen, Marker springen); freie Skriptausführung; Änderungen am Rohschnitt-Bau.

## Was Zeit spart (Auswahl, begründet)
| Werkzeug | Warum |
|---|---|
| **Effekte** (Karte ein/aus, Gauß, Pop, Zoom, Kreis, Fancy, Transformieren) auf Auswahl | Premiere-Vorgaben müssen einzeln gezogen werden, Ein-/Aus-Zeiten stimmen nur am Clipanfang/-ende. Hier: ein Klick, mehrere Clips, Zeiten relativ zum Clip. |
| **Artwork bauen** | Bild → verschachtelte Sequenz mit Maske (V5) + Spurmaske-Key + Standardeffekten, an Stelle des Bildes. Sonst ~15 Schritte je Artwork. |
| **Credit aus Auswahl / mit Text** | Credit-Vorlage mit richtigem Text, Länge, Spur, Überblendung. Der Künstlername kommt aus dem Dateinamen bzw. der Künstlerdatenbank. |
| **Überblendung 0,42 s** an Auswahl | Regel aus dem Ursprungsschnitt (562 Stück). |
| **Ton-Blenden** auf Auswahl | „Konstante Leistung“ gibt es per Skript nur als Pegel-Keyframes. |
| **Länge setzen / Ende zum Abspielkopf** | Mehrere Clips auf dieselbe Länge, ohne Lücken zu ziehen. |
| **Szene am Abspielkopf** | Zeigt Szene, Titel, Aufnahme-Status; Gegenrichtung „Szene in Premiere zeigen“ aus der App. |
| **Auswahl untersuchen** | Komponenten und Parameter des gewählten Clips ins Protokoll (Fehlersuche). |

## Aufbau
* Das Panel bekommt eine Werkzeugleiste (`index.html`/`main.js`), die Logik liegt in `lib/tools.js` (ohne Premiere testbar, wie der Rest).
* **RPC Panel → Server:** Fachliche Entscheidungen (Rezepte auflösen, Bildmaße, Credit-Text, Spur, Vorlage mit Text schreiben) trifft der Server. Das Panel sendet `{t:'rpc', id, method, args}`, der Server antwortet `{t:'rpc_result', id, ok, data|error}` (`bridge.py`, Methoden in `premiere_tools.py`). Der Server weiß, welche Folge gemeint ist, aus `bridge_context.json` (zuletzt gebaute Folge).
* Das Panel führt nur Premiere-Grundoperationen aus (Auswahl lesen, Effekt anhängen, Sequenz bauen, Vorlage einsetzen, Länge setzen), nie freien Code.
* Der Server prüft Methodennamen gegen eine feste Liste (wie `OPS`).

## Annahmen, die nur Premiere prüfen kann
* `Sequence.getSelection()` liefert die gewählten Clips, `getPlayerPosition()/setPlayerPosition()` funktionieren.
* Das Ersetzen eines Bildes durch eine verschachtelte Sequenz klappt wie im Bau: Clip entfernen (ohne Lücke), Sequenz auf dieselbe Spur/Zeit setzen.
* Nicht zeitlich animierbare Parameter und Keyframes verhalten sich wie im Bau (derselbe Code `effects.js`).
Alle Werkzeuge melden Fehler im Protokoll und lassen die Auswahl unverändert, wenn ein Schritt scheitert.

## Entscheidungen (mein Standard, siehe FRAGEN.md F12)
* Effekte werden **hinzugefügt**, nicht ersetzt; ein zweiter Klick legt den Effekt doppelt an (Rückgängig: Strg+Z, jede Aktion ist eine Transaktion).
* Credit-Text: `© {Künstler klein}`, wie im Bau (`credit_text`); Spur: Credit-Spur der Rohschnitt-Vorlage; Länge wie das Bild.
* Artwork-Maske: automatisch nach Bildformat (`mask: auto`), Größe wie im Bau (`art_size_px`, `landscape_px`).
* Zeitwerkzeuge verschieben nie andere Clips.
