# Teil 2 – Design-Entscheidungen

Fachlich maßgeblich: `Projektheft Teil 2 - Zeitgewinn und Bedienung.md`. Hier nur das **Wie**.

## Server
- **Fehler:** zentrale Handler in `api.py` (ValueError→400, FileNotFoundError→404, FileExistsError→409), deutsche Texte. Fachfehler werfen ValueError/FileNotFoundError.
- **Jobs:** `Jobs` bekommt `cancel(jid)` (Flag, kooperativ via `progress`-Callback, wirft `Abgebrochen`), `list()` mit letzten 30 Aufträgen. `GET /api/jobs`, `POST /api/jobs/{id}/cancel`. Aufträge tragen `episode` und `kind`.
- **Auto-Proxy:** nach `import_source` wird im Job ein Proxy-Job nachgeschoben.
- **Status veraltet:** in `put_scene` Vergleich alter/neuer Inhalt (Text, Stichpunkte, Sprecher, Segmente); bei Änderung und Status ∈ {aufgenommen, abgeglichen} → `veraltet`. Abgleich setzt wieder `abgeglichen`. `run_alignment(only=…)` optional auf Szenen-ID-Liste beschränkt.
- **Versionsschutz:** Szene trägt `geaendert_am`; `PUT /scenes/{id}` mit `base` (erwarteter `geaendert_am`) → 409 `{konflikt: aktuelle Szene}` wenn Datei neuer. Ohne `base` wie bisher.
- **Papierkorb:** `delete_scene` verschiebt nach `glorfindel/papierkorb/`; `POST /scenes/{id}/restore`.
- **Cockpit:** `GET /ep/…/cockpit` liefert Zähler und Aufgabenliste (ohne Segment, ohne Strang, Bilder ohne Credit, Blöcke ohne Aufnahme, veraltet, nicht abgeglichen) mit Zielansicht.
- **Rahmenteile:** `free_blocks` bekommen `dauer` (s), `position` (nach Szenen-ID oder `anfang`/`ende`); Rohschnitt legt Platzhalter dieser Länge.
- **Word:** Marker mit Titel (`⟦+bild:art_0001|Alan Lee⟧`; Import liest den Teil vor `|`), Optionen `markers`, `by_strand`, Schriftgröße 13 pt, Sprecherfarbe.
- **Karten:** Elemente `{typ: marker|text|pfeil|region|rahmen, x, y, x2, y2, text, t0, t1}` in Normkoordinaten 0..1; Render nutzt vorhandenes `maps.draw_elements`.
- **Update-Check:** `GET /api/update` fragt GitHub-Releases (httpx, 3 s Timeout, still bei Fehler).
- **Aufnahme:** `GET /recording` liefert zusätzlich `unsicher` (Konfidenz < 0.8 oder missing); Take-Wahl `PUT /recording/take {scene, block, take}`.

## Web
- `state.js` bekommt Hilfsfunktion `order` (Ausgabenummer). Neue Module: `tasks.js` (Aufgabenleiste, pollt `/api/jobs`), `shortcuts.js` (zentrale Tastenkürzel), `anchors.js` (Zwei-Player-Anker), `mapeditor.js`.
- Editor-Kopfzeile einzeilig; Kürzel zentral registriert; `beforeunload` bei ungespeichert.
- Alle neuen Texte deutsch, `textContent`-only.

## Tests
pytest je Servermodul; Browser-Smoke (Playwright, Chromium ohne H.264 → Player-Pfade nur auf Fehlerfall) als `scripts/smoke_ui.py`, nicht Teil der Standard-Suite (Playwright optional).
