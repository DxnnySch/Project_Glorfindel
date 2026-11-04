// Editierbarer Text über Motion-Graphics-Vorlagen (.mogrt): Vorlage einsetzen, Textparameter füllen.
// Die Vorlage trägt Schrift, Farbe, Schatten und Ort selbst (einmal aus dem eigenen Schnitt exportiert: Essential Graphics → Als Vorlage exportieren).
// `locate()` liefert den Clip FRISCH (siehe core.js).
'use strict';

const { tt, txp, invalidate, rawValue } = require('./core');
const fx = require('./effects');

const TEXT_NAMES = ['TextLayer', 'Text', 'Titel', 'Quelltext', 'Source Text'];

/** Vorlage an Zeit und Spur einsetzen. Die API wirkt sofort (keine Aktion) und verlangt „locked access“. */
async function insertTemplate(ppro, project, seq, { path, start, track }) {
  const editor = ppro.SequenceEditor.getEditor(seq);
  let items;
  project.lockedAccess(() => { items = editor.insertMogrtFromPath(path, tt(ppro, start), track, 0); });
  items = await items;
  invalidate();
  if (!items || !items.length) throw new Error('Premiere hat keinen Clip aus der Vorlage geliefert');
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

/** Textparameter des Clips finden (nach Namen, sonst der erste Parameter mit Textwert) und setzen. */
async function setText(ppro, project, locate, text, names = TEXT_NAMES) {
  const chain = await (await locate()).getComponentChain();
  const want = names.map((n) => n.toLowerCase());
  const found = [], named = [], dump = [];
  const list = await fx.listComponents(chain);
  const comps = list.map((c) => c.name);
  for (const c of list) {
    for (const p of fx.paramList(c.comp)) {
      let v, art;
      try { v = rawValue(await p.param.getStartValue()); art = typeof v; } catch (e) { art = 'Fehler'; }
      dump.push(c.name + '/' + p.name + ':' + art);
      if (typeof v === 'string') found.push({ comp: c.index, index: p.index, name: p.name, value: v });
      else if (want.includes(String(p.name).toLowerCase())) named.push({ comp: c.index, index: p.index, name: p.name, value: '' });   // Wert nicht lesbar, Name passt
    }
  }
  if (!found.length && named.length) found.push(named[0]);
  if (!found.length) throw new Error('Die Vorlage hat keinen Textparameter. Komponenten: ' + comps.join(', ') + '. Parameter: ' + (dump.filter((d) => !/^(Deckkraft|Bewegung|Vektorbewegung)\//.test(d)).join('; ') || 'keine weiteren').slice(0, 900));
  const pick = found.find((f) => want.includes(String(f.name).toLowerCase())) || found[0];
  const param = fx.findParam(await fx.componentAt(locate, pick.comp), [pick.name], pick.index);
  if (!param) throw new Error('Textparameter nicht mehr gefunden');
  await txp(ppro, 'Credit-Text', (add) => add(param.createSetValueAction(param.createKeyframe(withText(pick.value, text)), true)));
  return pick.name;
}

module.exports = { insertTemplate, setText, withText, TEXT_NAMES };
