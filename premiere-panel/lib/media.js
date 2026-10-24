// Medien im Premiere-Projekt: importieren, zuordnen, austauschen (Proxy → HQ), neu laden.
// Objekte werden nie über Änderungen hinweg gehalten (siehe core.js): Fächer werden per Namen frisch geholt.
'use strict';

const { norm, tx, walkItems, asClip, errText, retryStale } = require('./core');

async function getBin(ppro, project, name) {
  const root = await project.getRootItem();
  const bin = (await root.getItems()).find((i) => i.name === name && i.type === ppro.ProjectItem.TYPE_BIN);
  return bin ? ppro.FolderItem.cast(bin) : null;
}

/** Fach anlegen, falls nötig. Gibt das Fach frisch zurück (nur bis zur nächsten Änderung gültig). */
async function ensureBin(ppro, project, name) {
  let bin = await getBin(ppro, project, name);
  if (!bin) {
    const root = await project.getRootItem();
    tx(project, 'Fach anlegen', (add) => add(root.createBinAction(name, true)));
    bin = await getBin(ppro, project, name);
  }
  return bin || (await project.getRootItem());
}

/** Dateien importieren und jedem Pfad sein Projektelement zuordnen. Rückgabe: Map normierter Pfad → ClipProjectItem (frisch). */
async function importFiles(ppro, project, paths, binName, emit) {
  await ensureBin(ppro, project, binName);
  const known = await mediaByPath(ppro, await getBin(ppro, project, binName));
  const todo = paths.filter((p) => !known.has(norm(p)));
  const CHUNK = 40;
  for (let i = 0; i < todo.length; i += CHUNK) {
    const part = todo.slice(i, i + CHUNK);
    const bin = await getBin(ppro, project, binName);                  // nach jedem Import ist das alte Fach ungültig
    const ok = await project.importFiles(part, true, bin, false);      // false: nie als Bildsequenz (1.png, 2.png …)
    if (ok === false) throw new Error('Import fehlgeschlagen: ' + part[0] + ' …');
    if (emit) emit('progress', { text: 'Medien importiert: ' + Math.min(i + CHUNK, todo.length) + ' von ' + todo.length });
  }
  return mediaByPath(ppro, await getBin(ppro, project, binName));
}

async function mediaByPath(ppro, folder) {
  const map = new Map();
  for (const it of await walkItems(ppro, folder)) {
    const clip = asClip(ppro, it);
    if (!clip) continue;
    try {
      if (await clip.isSequence()) continue;
      const p = await clip.getMediaFilePath();
      if (p) map.set(norm(p), clip);
    } catch (e) { /* Platzhalter ohne Datei */ }
  }
  return map;
}

/** Alle Medien des Projekts (für Tausch und Neuladen). */
async function allMedia(ppro, project) {
  return mediaByPath(ppro, await project.getRootItem());
}

/**
 * Dateien austauschen: `swaps` = [{from, to}]. Betroffene Clips, Effekte und Schnitte bleiben erhalten, weil nur die Datei
 * des Projektelements wechselt. `refresh` = Pfade/Ordner, deren Elemente neu geladen werden.
 * Nach jedem Tausch sind Objekte ungültig, daher wird je Datei frisch gesucht.
 */
async function swapMedia(ppro, project, { swaps = [], refresh = [] }, emit) {
  const report = { getauscht: [], fehler: [], neu_geladen: 0 };
  for (const s of swaps) {
    try {
      await retryStale(async () => {
        const item = (await allMedia(ppro, project)).get(norm(s.from));
        if (!item) throw new Error('im Projekt nicht gefunden');
        if (item.canChangeMediaPath && !(await item.canChangeMediaPath())) throw new Error('Pfad dieses Elements lässt sich nicht ändern');
        const ok = await item.changeMediaFilePath(s.to, true);
        if (ok === false) throw new Error('Premiere hat den Tausch abgelehnt');
      });
      report.getauscht.push({ von: s.from, nach: s.to });
    } catch (e) {
      report.fehler.push({ von: s.from, fehler: errText(e) });
    }
    if (emit) emit('progress', { text: 'Getauscht: ' + report.getauscht.length + ' von ' + swaps.length });
  }
  const want = refresh.map(norm);
  if (want.length) {
    const paths = [...(await allMedia(ppro, project)).keys()].filter((p) => want.some((w) => p === w || p.startsWith(w.endsWith('/') ? w : w + '/')));
    for (const p of paths) {
      try {
        const item = (await allMedia(ppro, project)).get(p);
        await item.refreshMedia();
        report.neu_geladen++;
      } catch (e) { report.fehler.push({ datei: p, fehler: errText(e) }); }
    }
  }
  return report;
}

module.exports = { getBin, ensureBin, importFiles, mediaByPath, allMedia, swapMedia };
