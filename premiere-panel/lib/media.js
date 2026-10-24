// Medien im Premiere-Projekt: importieren, zuordnen, austauschen (Proxy → HQ), neu laden.
'use strict';

const { norm, tx, walkItems, asClip, errText } = require('./core');

async function ensureBin(ppro, project, name) {
  const root = await project.getRootItem();
  const find = async () => (await root.getItems()).find((i) => i.name === name && i.type === ppro.ProjectItem.TYPE_BIN);
  let bin = await find();
  if (!bin) {
    tx(project, 'Fach anlegen', (add) => add(root.createBinAction(name, true)));
    bin = await find();
  }
  return bin ? ppro.FolderItem.cast(bin) : root;
}

/** Dateien importieren und jedem Pfad sein Projektelement zuordnen. Rückgabe: Map normierter Pfad → ClipProjectItem. */
async function importFiles(ppro, project, paths, bin, emit) {
  const known = await mediaByPath(ppro, bin);
  const todo = paths.filter((p) => !known.has(norm(p)));
  const CHUNK = 40;
  for (let i = 0; i < todo.length; i += CHUNK) {
    const part = todo.slice(i, i + CHUNK);
    const ok = await project.importFiles(part, true, bin, false);      // false: nie als Bildsequenz (1.png, 2.png …)
    if (ok === false) throw new Error('Import fehlgeschlagen: ' + part[0] + ' …');
    if (emit) emit('progress', { text: 'Medien importiert: ' + Math.min(i + CHUNK, todo.length) + ' von ' + todo.length });
  }
  return mediaByPath(ppro, bin);
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
 * des Projektelements wechselt. `refresh` = Pfade/Ordner, deren Elemente neu geladen werden (z. B. ersetzte Standbilder).
 */
async function swapMedia(ppro, project, { swaps = [], refresh = [] }, emit) {
  const report = { getauscht: [], fehler: [], neu_geladen: 0 };
  const media = await allMedia(ppro, project);
  for (const s of swaps) {
    const item = media.get(norm(s.from));
    if (!item) { report.fehler.push({ von: s.from, fehler: 'im Projekt nicht gefunden' }); continue; }
    try {
      if (item.canChangeMediaPath && !(await item.canChangeMediaPath())) throw new Error('Pfad dieses Elements lässt sich nicht ändern');
      const ok = await item.changeMediaFilePath(s.to, true);
      if (ok === false) throw new Error('Premiere hat den Tausch abgelehnt');
      report.getauscht.push({ von: s.from, nach: s.to });
    } catch (e) {
      report.fehler.push({ von: s.from, fehler: errText(e) });
    }
    if (emit) emit('progress', { text: 'Getauscht: ' + report.getauscht.length + ' von ' + swaps.length });
  }
  const fresh = (await allMedia(ppro, project));
  const want = refresh.map(norm);
  for (const [p, item] of fresh) {
    if (!want.some((w) => p === w || p.startsWith(w.endsWith('/') ? w : w + '/'))) continue;
    try { await item.refreshMedia(); report.neu_geladen++; } catch (e) { report.fehler.push({ datei: p, fehler: errText(e) }); }
  }
  return report;
}

module.exports = { ensureBin, importFiles, mediaByPath, allMedia, swapMedia };
