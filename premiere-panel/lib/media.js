// Medien im Premiere-Projekt: importieren, zuordnen, austauschen (Proxy → HQ), neu laden.
// Objekte werden nie über Änderungen hinweg gehalten (siehe core.js): Fächer werden per Namen frisch geholt.
'use strict';

const { norm, tx, txp, withTimeout, at, getProj, invalidate, walkItems, asClip, errText, retryStale } = require('./core');

const fresh = (ppro) => getProj(ppro);

async function getBin(ppro, project, name) {
  const root = await project.getRootItem();
  const bin = ((await root.getItems()) || []).find((i) => i && i.name === name && i.type === ppro.ProjectItem.TYPE_BIN);
  return bin ? ppro.FolderItem.cast(bin) : null;
}

/** Fach anlegen, falls nötig. Gibt das Fach frisch zurück (nur bis zur nächsten Änderung gültig). */
async function ensureBin(ppro, project, name) {
  let bin = await at('Fach suchen', async () => getBin(ppro, await fresh(ppro), name));
  if (!bin) {
    await at('Fach anlegen', async () => {
      const root = await (await fresh(ppro)).getRootItem();
      await txp(ppro, 'Fach anlegen', (add) => add(root.createBinAction(name, true)));
    });
    bin = await at('Fach suchen (nach Anlegen)', async () => getBin(ppro, await fresh(ppro), name));
  }
  return bin || (await (await fresh(ppro)).getRootItem());
}

/** Dateien importieren und jedem Pfad sein Projektelement zuordnen. Rückgabe: Map normierter Pfad → ClipProjectItem (frisch). */
async function importFiles(ppro, project, paths, binName, emit) {
  await ensureBin(ppro, project, binName);
  const known = await at('Vorhandene Medien lesen', async () => mediaByPath(ppro, await getBin(ppro, await fresh(ppro), binName)));
  const todo = paths.filter((p) => !known.has(norm(p)));
  const CHUNK = 10;
  for (let i = 0; i < todo.length; i += CHUNK) {
    const part = todo.slice(i, i + CHUNK);
    const bin = await at('Fach vor Import holen', async () => getBin(ppro, await fresh(ppro), binName));   // nach jedem Import sind Projekt und Fach ungültig
    if (emit) emit('progress', { text: 'Importiere ' + (i + 1) + '–' + Math.min(i + CHUNK, todo.length) + ' von ' + todo.length + ': ' + part[0].split(/[\/]/).pop() });
    const ok = await at('Import', async () => withTimeout((await fresh(ppro)).importFiles(part, true, bin, false), 180000, 'Import').finally(invalidate));      // false: nie als Bildsequenz (1.png, 2.png …)
    if (ok === false) throw new Error('Import fehlgeschlagen: ' + part[0] + ' …');
    if (emit) emit('progress', { text: 'Medien importiert: ' + Math.min(i + CHUNK, todo.length) + ' von ' + todo.length });
  }
  return at('Medien nach Import lesen', async () => mediaByPath(ppro, await getBin(ppro, await fresh(ppro), binName)));
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

/** Unverändertes ProjectItem zu einem Dateipfad (für Schnitt-Aktionen; die Umwandlung in ClipProjectItem wird dort abgelehnt). */
async function rawByPath(ppro, folder, path) {
  for (const it of await walkItems(ppro, folder)) {
    const clip = asClip(ppro, it);
    if (!clip) continue;
    try { if (!(await clip.isSequence()) && norm(await clip.getMediaFilePath()) === norm(path)) return it; } catch (e) { /* Platzhalter */ }
  }
  return null;
}

/** Alle Medien des Projekts (für Tausch und Neuladen). */
async function allMedia(ppro, project) {
  return mediaByPath(ppro, await (await fresh(ppro)).getRootItem());
}

/** Alle Elemente eines Ordners je Dateipfad (dieselbe Datei kann mehrfach im Projekt liegen, z. B. nach mehreren Bauten). */
async function itemsByPath(ppro, folder) {
  const map = new Map();
  for (const it of await walkItems(ppro, folder)) {
    const clip = asClip(ppro, it);
    if (!clip) continue;
    try {
      if (await clip.isSequence()) continue;
      const p = await clip.getMediaFilePath();
      if (p) { const k = norm(p); if (!map.has(k)) map.set(k, []); map.get(k).push(clip); }
    } catch (e) { /* Platzhalter ohne Datei */ }
  }
  return map;
}

/**
 * Dateien austauschen: `swaps` = [{from, to}]. Betroffene Clips, Effekte und Schnitte bleiben erhalten, weil nur die Datei
 * des Projektelements wechselt. `bin`: nur im Fach dieses Baus suchen (ältere Baustände mit derselben Datei bleiben unberührt).
 * `refresh` = Pfade/Ordner, deren Elemente neu geladen werden. Nach jedem Tausch sind Objekte ungültig, daher wird je Datei frisch gesucht.
 */
async function swapMedia(ppro, project, { swaps = [], refresh = [], bin = null }, emit) {
  const report = { getauscht: [], schon: [], fehler: [], neu_geladen: 0 };
  const scope = async () => {
    const proj = await fresh(ppro);
    const folder = bin ? await getBin(ppro, proj, bin) : null;
    return folder || (await proj.getRootItem());
  };
  for (const s of swaps) {
    try {
      let done = 0, firstFail = null, seen = 0;
      for (let guard = 0; guard < 20; guard++) {
        const all = await itemsByPath(ppro, await scope());
        const cands = all.get(norm(s.from)) || [];
        if (guard === 0) { seen = cands.length; if (!cands.length && all.has(norm(s.to))) { report.schon.push(s.to); break; } }
        if (!cands.length) break;
        const item = cands[0];
        try {
          if (item.canChangeMediaPath && !(await item.canChangeMediaPath())) throw new Error('Pfad dieses Elements lässt sich nicht ändern');
          let ok = await retryStale(async () => item.changeMediaFilePath(s.to, true));
          invalidate();
          if (ok === false) {                                    // andere Wege versuchen (Details für die Fehlersuche sammeln)
            const tried = ['override=true'];
            const again = (await itemsByPath(ppro, await scope())).get(norm(s.from)) || [];
            if (again[0]) {
              const proj = await fresh(ppro);
              let pr; proj.lockedAccess(() => { pr = again[0].changeMediaFilePath(s.to, true); });
              ok = await pr; invalidate(); tried.push('lockedAccess');
            }
            if (ok === false) {
              const info = [];
              const c2 = ((await itemsByPath(ppro, await scope())).get(norm(s.from)) || [])[0];
              if (c2) { for (const [k, f] of [['offline', () => c2.isOffline()], ['canChange', () => c2.canChangeMediaPath()]]) { try { info.push(k + '=' + (await f())); } catch (e) { info.push(k + '=?'); } } }
              throw new Error('Premiere hat den Tausch abgelehnt (' + tried.join(', ') + '; ' + cands.length + ' Element(e) im Fach' + (bin ? ' „' + bin + '“' : '') + '; ' + info.join(', ') + ')');
            }
          }
          done++;
        } catch (e) { firstFail = errText(e); invalidate(); break; }
      }
      if (!done && !report.schon.includes(s.to)) throw new Error(firstFail || 'im Projekt nicht gefunden');
      if (firstFail) report.warnungen = (report.warnungen || []).concat(s.from + ': ' + firstFail + ' (' + seen + ' Element(e) mit dieser Datei)');
      if (done) report.getauscht.push({ von: s.from, nach: s.to, elemente: done });
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
        invalidate();
        report.neu_geladen++;
      } catch (e) { report.fehler.push({ datei: p, fehler: errText(e) }); }
    }
  }
  return report;
}

module.exports = { itemsByPath, getBin, ensureBin, importFiles, mediaByPath, rawByPath, allMedia, swapMedia };
