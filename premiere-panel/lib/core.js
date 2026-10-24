// Gemeinsame Hilfen. Alle Module bekommen `ppro` (= require('premierepro')) hineingereicht, damit sie ohne Premiere testbar sind.
'use strict';

const TICKS_PER_SECOND = 254016000000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (p) => String(p || '').replace(/\\/g, '/').toLowerCase();
const errText = (e) => (e && e.message) || String(e);

/** Sekunden -> TickTime */
function tt(ppro, seconds) {
  return ppro.TickTime.createWithSeconds(Math.max(0, seconds));
}

/** Eine Transaktion ausführen; `build(compound)` fügt Aktionen hinzu. Wirft, wenn Premiere sie ablehnt. */
function tx(project, undoName, build) {
  const ok = project.executeTransaction((compound) => {
    build((action) => {
      if (action == null) throw new Error('Aktion konnte nicht erzeugt werden');
      if (compound.addAction(action) === false) throw new Error('Aktion wurde nicht angenommen');
    });
  }, undoName);
  if (ok === false) throw new Error('Transaktion „' + undoName + '“ wurde von Premiere abgelehnt');
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

module.exports = { TICKS_PER_SECOND, sleep, norm, errText, tt, tx, guarded, walkItems, asClip };
