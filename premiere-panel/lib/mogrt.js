// Editierbarer Text über Motion-Graphics-Vorlagen (.mogrt): Vorlage einsetzen, Textparameter füllen.
// Die Vorlage trägt Schrift, Farbe, Schatten und Ort selbst (einmal aus dem eigenen Schnitt exportiert: Essential Graphics → Als Vorlage exportieren).
// `locate()` liefert den Clip FRISCH (siehe core.js).
'use strict';

const { tt, txp, invalidate, rawValue, sleep, at } = require('./core');
const fx = require('./effects');

/** Textwert der Vorlage (Premiere 27.0): Objekt mit getText/setText. Ältere Annahme: Zeichenkette bzw. JSON-Textdokument. */
const isMogrtText = (v) => !!v && typeof v === 'object' && typeof v.getText === 'function' && typeof v.setText === 'function';

/** Aktueller Text eines Parameters (null, wenn nicht lesbar). */
async function readText(param) {
  try {
    const v = rawValue(await param.getStartValue());
    if (isMogrtText(v)) return v.getText();
    return typeof v === 'string' ? v : null;
  } catch (e) { return null; }
}

/** Synchroner Aufruf mit Ortsangabe im Fehler (Aktionen entstehen synchron innerhalb der Transaktion). */
function at0(label, fn, next) {
  let r;
  try { r = fn(); } catch (e) { throw new Error(label + ': ' + ((e && e.message) || e)); }
  return next ? next(r) : r;
}

const TEXT_NAMES = ['TextLayer', 'Text', 'Titel', 'Quelltext', 'Source Text'];

let lastInserted = null;

/** Vorlage an Zeit und Spur einsetzen. Die API wirkt sofort (keine Aktion) und verlangt „locked access“. */
async function insertTemplate(ppro, project, seq, { path, start, track }) {
  const editor = ppro.SequenceEditor.getEditor(seq);
  let items;
  project.lockedAccess(() => { items = editor.insertMogrtFromPath(path, tt(ppro, start), track, 0); });
  items = await items;
  if (!items || !items.length) { invalidate(); throw new Error('Premiere hat keinen Clip aus der Vorlage geliefert'); }
  invalidate();
  lastInserted = items[0];                          // frisch zurückgegeben: erst dieses Objekt kennt die Grafik-Parameter sicher
  return items.length;
}

/** Neuer Parameterwert: Premiere führt Text als JSON-Textdokument (textEditValue + Länge der Textläufe); sonst ist der Wert der Text selbst. */
function withText(current, text) {
  try {
    const doc = JSON.parse(current);
    if (doc && typeof doc === 'object' && 'textEditValue' in doc) {
      doc.textEditValue = text;
      if (Array.isArray(doc.fontTextRunLength)) doc.fontTextRunLength = [Array.from(text).length];
      return JSON.stringify(doc);
    }
  } catch (e) { /* kein JSON: einfacher Textwert */ }
  return text;
}

const CAPSULE = 'AE.ADBE Capsule';                    // Komponente einer Vorlage (Essential Graphics) ab Premiere 27.0

/** Alle Parameter, die den Text tragen könnten. `item`: bereits vorliegender Clip, sonst frisch per `locate`.
 *  Rangfolge: Textobjekt (27.0) > Zeichenkette > nicht lesbarer Parameter der Vorlagen-Komponente > nicht lesbarer Parameter mit passendem Namen. */
async function scanText(locate, want, item) {
  const chain = await (item || await locate()).getComponentChain();
  const objs = [], strs = [], capsule = [], named = [], dump = [];
  const list = await fx.listComponents(chain);
  for (const c of list) {
    let match = '';
    try { match = await c.comp.getMatchName(); } catch (e) { /* ältere API */ }
    for (const p of fx.paramList(c.comp)) {
      let v, art;
      try { v = rawValue(await p.param.getStartValue()); art = isMogrtText(v) ? 'MogrtText' : v == null ? 'leer' : typeof v; } catch (e) { art = 'Fehler(' + ((e && e.message) || e) + ')'; }
      dump.push(c.name + (match ? '[' + match + ']' : '') + '/' + p.name + ':' + art);
      const cand = { comp: c.index, index: p.index, name: p.name, value: typeof v === 'string' ? v : '' };
      if (isMogrtText(v)) objs.push({ ...cand, kind: 'objekt' });
      else if (typeof v === 'string') strs.push({ ...cand, kind: 'text' });
      else if (match === CAPSULE) capsule.push({ ...cand, kind: 'unlesbar' });
      else if (want.includes(String(p.name).toLowerCase())) named.push({ ...cand, kind: 'unlesbar' });
    }
  }
  return { found: [...objs, ...strs, ...capsule, ...named], dump, comps: list.map((c) => c.name) };
}

/** Textparameter des Clips finden und setzen.
 *  Die Grafik-Parameter erscheinen manchmal erst kurz nach dem Einfügen: bis zu ~5 s wiederholen. */
async function setText(ppro, project, locate, text, names = TEXT_NAMES) {
  const want = names.map((n) => n.toLowerCase());
  let scan = null;
  for (let i = 0; i < 8; i++) {
    const first = i === 0 && lastInserted ? lastInserted : null;
    try { scan = await scanText(locate, want, first); } catch (e) { if (!first) throw e; scan = null; }   // das Objekt kann schon ungültig sein
    lastInserted = null;
    if (scan && scan.found.length) break;
    await sleep(700);
  }
  if (!scan || !scan.found.length) {
    throw new Error('Die Vorlage hat keinen Textparameter. Komponenten: ' + (scan ? scan.comps.join(', ') : '?') + '. Parameter: '
      + ((scan ? scan.dump.filter((d) => !/^(Deckkraft|Bewegung|Vektorbewegung|Opacity|Motion|Vector Motion)[\[/]/.test(d)).join('; ') : '') || 'keine weiteren').slice(0, 900));
  }
  const pick = scan.found.find((f) => want.includes(String(f.name).toLowerCase())) || scan.found[0];
  const param = fx.findParam(await fx.componentAt(locate, pick.comp), [pick.name], pick.index);
  if (!param) throw new Error('Textparameter nicht mehr gefunden');
  const commit = (val, label) => txp(ppro, 'Credit-Text', (add) => add(
    at0(label + ': createKeyframe', () => param.createKeyframe(val), (kf) => at0(label + ': createSetValueAction', () => param.createSetValueAction(kf, true)))));
  const info = () => ' [' + pick.kind + '; ' + scan.dump.filter((d) => d.includes('/' + pick.name + ':')).join('; ') + ']';

  if (pick.kind === 'objekt') {                       // Premiere 27.0: Textobjekt ändern und per Aktion zurückschreiben
    const val = await at('MogrtText lesen', async () => rawValue(await param.getStartValue()));
    if (await at('MogrtText.setText', async () => val.setText(text)) === false) throw new Error('Premiere hat den Text nicht angenommen');
    await commit(val, 'MogrtText');
    return pick.name;
  }
  if (pick.kind === 'unlesbar' && typeof ppro.MogrtText === 'function') {
    // Der aktuelle Wert lässt sich nicht lesen: neues Textobjekt anlegen (die Formatierung kommt dann vom Parameter, nicht aus dem Objekt)
    const val = at0('new MogrtText', () => new ppro.MogrtText());
    if (at0('MogrtText.setText', () => val.setText(text)) === false) throw new Error('Premiere hat den Text nicht angenommen');
    try { await commit(val, 'MogrtText (neu)'); } catch (e) { throw new Error(((e && e.message) || e) + info()); }
    return pick.name;
  }
  try { await commit(withText(pick.value, text), 'Zeichenkette'); } catch (e) { throw new Error(((e && e.message) || e) + info()); }
  return pick.name;
}

// ---- Ist die Grafik der Vorlage geladen? ----
// Gemessen an Test8–Test10.prproj (Premiere 27.1): `insertMogrtFromPath` liefert sofort einen Clip „Grafik“, die Grafik selbst (Komponente
// „Text“ [AE.ADBE Text] mit „Quelltext“, Quellbereich der Vorlage) lädt Premiere erst danach. Bei den meisten Credits kam sie nie an: leere
// Ebene mit richtigem Namen, ohne Komponenten. Ein Credit, dessen Grafik schon da war, behielt sie über Länge, Name und Übergänge hinweg.
// Darum: nach dem Einsetzen warten, bis die Grafik da ist, und erst dann weiterarbeiten; kommt sie nicht, PNG-Rückfall mit Hinweis.
const GRAPHIC_MATCH = ['AE.ADBE Text', 'AE.ADBE Capsule'];
const INTRINSIC = ['deckkraft', 'bewegung', 'vektorbewegung', 'opacity', 'motion', 'vector motion', 'zeitverzerrung', 'time remapping'];
const timing = { timeout: 12000, step: 300 };      // Tests verkürzen das; der Bauplan kann `calibration.mogrt_wait_ms` vorgeben

/** Ob sich das Laden der Grafik prüfen lässt: erst Premiere 27.x zeigt die Text-Komponente eingesetzter Vorlagen (26.5 nur Deckkraft/Bewegung). */
const canVerify = (ppro) => typeof ppro.MogrtText === 'function';

/** Komponenten des Clips und ob eine Grafik (Text/Vorlage) darunter ist. */
async function graphicState(locate) {
  const chain = await (await locate()).getComponentChain();
  const comps = [];
  let ok = false;
  for (const c of await fx.listComponents(chain)) {
    let match = '';
    try { match = await c.comp.getMatchName(); } catch (e) { /* ältere API */ }
    comps.push(c.name || match || '?');
    if (GRAPHIC_MATCH.includes(match) || (c.name && !INTRINSIC.includes(String(c.name).toLowerCase()))) ok = true;
  }
  return { ok, comps };
}

/** Warten, bis die Grafik des eingesetzten Clips geladen ist. Liest nur (ändert nichts), ungültige Objekte werden frisch geholt.
 *  Rückgabe: {ok, comps, ms, error}. */
async function waitForGraphic(locate, opts = {}) {
  const timeout = opts.timeout != null ? opts.timeout : timing.timeout;
  const step = opts.step != null ? opts.step : timing.step;
  const t0 = Date.now();
  let last = { ok: false, comps: [] }, error = null;
  for (;;) {
    try { last = await graphicState(locate); error = null; } catch (e) { error = (e && e.message) || String(e); invalidate(); }
    const ms = Date.now() - t0;
    if (last.ok || ms >= timeout) return { ...last, ms, error };
    await sleep(step);
  }
}

/** Den eingesetzten Vorlagen-Clip wieder entfernen (ohne Lücke zu schließen), z. B. wenn sich sein Text nicht setzen ließ. */
async function removeClip(ppro, seqOf, locate) {
  let sel;
  await new Promise((res) => { ppro.TrackItemSelection.createEmptySelection((s) => { sel = s; res(); }); });
  sel.addItem(await locate());
  const editor = ppro.SequenceEditor.getEditor(await seqOf());
  await txp(ppro, 'Vorlage entfernen', (add) => add(editor.createRemoveItemsAction(sel, false, ppro.Constants.MediaType.ANY)));
}

module.exports = { insertTemplate, setText, removeClip, readText, isMogrtText, withText, TEXT_NAMES, graphicState, waitForGraphic, canVerify, timing, GRAPHIC_MATCH };
