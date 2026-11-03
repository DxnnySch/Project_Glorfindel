---
name: premiere-paritaet
description: Use when improving how closely the Premiere Bridge output matches Danny's hand-made edit (structure, transitions, editable text, effect chains) - runs the measure, find-gap, fix, test, commit loop against the reference .prproj
---

# Premiere-Parität: Bridge-Schnitt wie der handgemachte Schnitt

Ziel: Aufbau und Bearbeitbarkeit des Bridge-Schnitts gleichen dem Ursprungsschnitt (`F:\OneDrive\Mythen-Archiv\Videos\S2 E7\Mythen - S2 E7_1.prproj`).
Inhalt und Timing dürfen abweichen. Spec: `docs/superpowers/specs/2026-11-03-premiere-paritaet-design.md`.

## Schleife (autonom, keine blockierenden Fragen – offene Punkte in `FRAGEN.md` mit Standardwert)
1. **Messen.** `.venv/Scripts/python scripts/parity_report.py "<Referenz.prproj>" --plan <plan.json>` (Plan: `python scripts/make_plan_fixture.py` oder ein gebauter Plan).
   Mit `--built <bridge.prproj>` wird ein in Premiere gespeichertes Bridge-Projekt statt des Plans gemessen.
2. **Lücke wählen** nach eingesparter Handarbeit (Zahl × Aufwand je Stück). Die Referenz mit `prproj_reader` (`Project.open`, `.sequence("MythenAusMittelerdeVideo")`) genauer ansehen:
   Übergänge sind Elemente ohne Namen (`kind == "unbekannt"`), Texte `AE.ADBE Text`, Effekte in `Item.comps`. Regeln **messen, nicht raten**, und in
   `vorlagen/premiere_rezepte.json` ablegen (Quelle vermerken).
3. **Test zuerst.** Python-Plan: `tests/test_premiere_*.py`; Panel: `premiere-panel/test/panel.test.js` gegen die strenge Nachbildung `fake_ppro.js`
   (die Nachbildung muss die Premiere-Regeln erzwingen: Typen, `lockedAccess`, ungültige Objekte nach Änderung).
4. **Umsetzen.** Plan-Builder (`premiere_plan.py`) liefert fertig aufgelöste Daten; das Panel (`premiere-panel/lib/`) führt nur aus. Premiere-API nur laut
   `docs/bridge/premierepro-26.5.d.ts` (Wächter: `tests/test_panel_api_names.py`). Jede Annahme, die nur Premiere klären kann, gehört in den Selbsttest
   (`lib/selftest.js`) **und** bekommt einen Rückfall mit Hinweis im Bericht (`report.warnings`) – nie stilles Scheitern.
5. **Alles prüfen.** `python scripts/make_plan_fixture.py` (Vertrag Python↔Panel), `node --test premiere-panel/test/panel.test.js`, `.venv/Scripts/python -m pytest -q`.
6. **Commit** (ohne Attributionszeilen), Panel-Version in `manifest.json`, `main.js`, `lib/bridge.js` erhöhen, `STATUS.md` (Abnahmeliste für Premiere) aktualisieren.

## Grundsätze
- „Wie von Hand gemacht“ heißt: gleiche Objektarten (Text bleibt Text, Übergang bleibt Übergang, Sequenzen bleiben Sequenzen), nichts eingebrannt.
- Was die API nicht kann (z. B. Audioübergänge), bekommt ein gleichwertiges, editierbares Ersatzmittel und steht unter „Grenzen“ in der Spec.
- Claude kann Premiere nicht ausführen: nie „funktioniert in Premiere“ behaupten, nur „getestet gegen die Nachbildung; Abnahme siehe STATUS.md“.
