// Gemeinsame Hilfen. Alle Module bekommen `ppro` (= require('premierepro')) hineingereicht, damit sie ohne Premiere testbar sind.
//
// WICHTIG (aus dem ersten Lauf in Premiere 26.5.2): Jedes Objekt, das die API liefert (Projekt-Elemente, Sequenzen, Spuren, Clips, Komponenten,
// Parameter), wird UNGÜLTIG („The script object is no longer valid.“), sobald das Projekt verändert wurde (Transaktion, Import, neue Sequenz).
// Deshalb: Objekte nie über eine Änderung hinweg festhalten. Immer frisch holen (Locator-Funktionen) und `retryStale` nutzen.
'use strict';

const TICKS_PER_SECOND = 254016000000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (p) => String(p || '').replace(/\\/g, '/').toLowerCase();
const errText = (e) => (e && e.message) || String(e);
const isStale = (e) => /no longer valid/i.test(errText(e));

/** Sekunden -> TickTime */
function tt(ppro, seconds) {
  return ppro.TickTime.createWithSeconds(Math.max(0, seconds));
}

/** Ein Versprechen mit Zeitlimit: hängt Premiere (z. B. wegen eines offenen Dialogs), kommt eine klare Meldung statt Stillstand. */
function withTimeout(promise, ms, what) {
  let timer;
  const limit = new Promise((_, rej) => { timer = setTimeout(() => rej(new Error(what + ' dauert länger als ' + Math.round(ms / 1000) + ' s – hat Premiere einen Dialog offen?')), ms); });
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
}

/** Eine Transaktion ausführen; `build(add)` fügt Aktionen hinzu. Wirft, wenn Premiere sie ablehnt. Danach sind alle Objekte ungültig. */
function tx(project, undoName, build) {
  const ok = project.executeTransaction((compound) => {
    build((action) => {
      if (action == null) throw new Error('Aktion konnte nicht erzeugt werden');
      if (compound.addAction(action) === false) throw new Error('Aktion wurde nicht angenommen');
    });
  }, undoName);
  if (ok === false) throw new Error('Transaktion „' + undoName + '“ wurde von Premiere abgelehnt');
}

/** Fehler mit Ortsangabe versehen, damit klar ist, welcher Aufruf scheitert. */
async function at(label, fn) {
  try { return await fn(); } catch (e) { throw new Error(label + ': ' + errText(e)); }
}

/** Wie `tx`, holt aber das Projekt frisch (auch das Projekt-Objekt wird nach einer Änderung ungültig). */
async function txp(ppro, undoName, build) {
  const project = await ppro.Project.getActiveProject();
  if (!project) throw new Error('In Premiere ist kein Projekt geöffnet.');
  tx(project, undoName, build);
}

/** `fn` ausführen; bei ungültigen Objekten `refresh` (holt Caches neu) und noch einmal versuchen. */
async function retryStale(fn, refresh, tries = 2) {
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) {
      if (!isStale(e) || i >= tries) throw e;
      if (refresh) await refresh();
    }
  }
}

/** Schritt ausführen und Fehler sammeln statt abzubrechen: Der Bau läuft weiter, der Bericht nennt, was nicht ging. */
async function guarded(report, what, fn) {
  try {
    return await fn();
  } catch (e) {
    report.errors.push({ was: what, fehler: errText(e) });
    return undefined;
  }
}

/** Alle Projektelemente (rekursiv) als flache Liste. */
async function walkItems(ppro, root) {
  const out = [];
  async function visit(folder) {
    const items = await folder.getItems();
    for (const it of items) {
      out.push(it);
      if (it.type === ppro.ProjectItem.TYPE_BIN) {
        try { await visit(ppro.FolderItem.cast(it)); } catch (e) { /* leeres/gesperrtes Fach */ }
      }
    }
  }
  await visit(root);
  return out;
}

function asClip(ppro, item) {
  try { return ppro.ClipProjectItem.cast(item); } catch (e) { return null; }
}

module.exports = { TICKS_PER_SECOND, sleep, norm, errText, isStale, tt, tx, txp, at, withTimeout, retryStale, guarded, walkItems, asClip };
