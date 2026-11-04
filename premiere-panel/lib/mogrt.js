// Editierbarer Text über Motion-Graphics-Vorlagen (.mogrt): Vorlage einsetzen, Textparameter füllen.
// Die Vorlage trägt Schrift, Farbe, Schatten und Ort selbst (einmal aus dem eigenen Schnitt exportiert: Essential Graphics → Als Vorlage exportieren).
// `locate()` liefert den Clip FRISCH (siehe core.js).
'use strict';

const { tt, txp, invalidate, rawValue, sleep } = require('./core');
const fx = require('./effects');

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

/** Alle Parameter mit Textwert (oder passendem Namen) des Clips. `item`: bereits vorliegender Clip, sonst frisch per `locate`. */
async function scanText(locate, want, item) {
  const chain = await (item || await locate()).getComponentChain();
  const found = [], named = [], dump = [];
  const list = await fx.listComponents(chain);
  for (const c of list) {
    for (const p of fx.paramList(c.comp)) {
      let v, art;
      try { v = rawValue(await p.param.getStartValue()); art = typeof v; } catch (e) { art = 'Fehler'; }
      dump.push(c.name + '/' + p.name + ':' + art);
      if (typeof v === 'string') found.push({ comp: c.index, index: p.index, name: p.name, value: v });
      else if (want.includes(String(p.name).toLowerCase())) named.push({ comp: c.index, index: p.index, name: p.name, value: '' });
    }
  }
  return { found: found.length ? found : named.slice(0, 1), dump, comps: list.map((c) => c.name) };
}

/** Textparameter des Clips finden (nach Namen, sonst der erste Parameter mit Textwert) und setzen.
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
      + ((scan ? scan.dump.filter((d) => !/^(Deckkraft|Bewegung|Vektorbewegung|Opacity|Motion|Vector Motion)\//.test(d)).join('; ') : '') || 'keine weiteren').slice(0, 900));
  }
  const found = scan.found;
  const pick = found.find((f) => want.includes(String(f.name).toLowerCase())) || found[0];
  const param = fx.findParam(await fx.componentAt(locate, pick.comp), [pick.name], pick.index);
  if (!param) throw new Error('Textparameter nicht mehr gefunden');
  await txp(ppro, 'Credit-Text', (add) => add(param.createSetValueAction(param.createKeyframe(withText(pick.value, text)), true)));
  return pick.name;
}

/** Den eingesetzten Vorlagen-Clip wieder entfernen (ohne Lücke zu schließen), z. B. wenn sich sein Text nicht setzen ließ. */
async function removeClip(ppro, seqOf, locate) {
  let sel;
  await new Promise((res) => { ppro.TrackItemSelection.createEmptySelection((s) => { sel = s; res(); }); });
  sel.addItem(await locate());
  const editor = ppro.SequenceEditor.getEditor(await seqOf());
  await txp(ppro, 'Vorlage entfernen', (add) => add(editor.createRemoveItemsAction(sel, false, ppro.Constants.MediaType.ANY)));
}

module.exports = { insertTemplate, setText, removeClip, withText, TEXT_NAMES };
