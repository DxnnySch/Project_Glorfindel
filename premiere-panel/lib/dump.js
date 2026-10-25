// Premiere-Inhalte auslesen: Projekt, Sequenzen, Clips, Effekte mit Parametern. Dient Diagnose und Vergleich mit dem Ursprungsschnitt.
'use strict';

const { norm, walkItems, asClip, errText } = require('./core');
const fx = require('./effects');

function plainValue(v) {
  if (v == null) return null;
  const x = v && typeof v === 'object' && 'value' in v ? v.value : v;
  if (x && typeof x === 'object') {
    if ('x' in x && 'y' in x) return { x: x.x, y: x.y };
    if ('red' in x || 'r' in x) return { r: x.red ?? x.r, g: x.green ?? x.g, b: x.blue ?? x.b, a: x.alpha ?? x.a };
    try { return JSON.parse(JSON.stringify(x)); } catch (e) { return String(x); }
  }
  return x;
}

async function projectDump(ppro) {
  const project = await ppro.Project.getActiveProject();
  if (!project) return { open: false };
  const root = await project.getRootItem();
  const items = await walkItems(ppro, root);
  const offline = [];
  let clips = 0;
  for (const it of items) {
    const c = asClip(ppro, it);
    if (!c) continue;
    clips++;
    try { if (await c.isOffline()) offline.push(it.name); } catch (e) { /* ignorieren */ }
  }
  const seqs = [];
  for (const s of await project.getSequences()) {
    seqs.push({ name: s.name, guid: String(s.guid), video: await s.getVideoTrackCount(), audio: await s.getAudioTrackCount() });
  }
  return { open: true, name: project.name, path: project.path, sequences: seqs, items: items.length, clips, offline };
}

async function readComponents(trackItem, withParams) {
  const chain = await trackItem.getComponentChain();
  const out = [];
  for (const c of await fx.listComponents(chain)) {
    const entry = { name: c.name, params: [] };
    if (withParams) {
      for (const p of fx.paramList(c.comp)) {
        const info = { index: p.index, name: p.name };
        try { info.value = plainValue((await p.param.getStartValue())); } catch (e) { info.value = null; }
        try { info.keyframes = p.param.isTimeVarying() ? p.param.getKeyframeListAsTickTimes().map((t) => +t.seconds.toFixed(4)) : []; } catch (e) { /* keine */ }
        entry.params.push(info);
      }
    }
    out.push(entry);
  }
  return out;
}

async function sequenceDump(ppro, { name, maxItems = 200, params = true } = {}) {
  const project = await ppro.Project.getActiveProject();
  const seq = name ? (await project.getSequences()).find((s) => s.name === name) : await project.getActiveSequence();
  if (!seq) throw new Error('Sequenz nicht gefunden: ' + (name || '(aktive)'));
  const tracks = [];
  const nV = await seq.getVideoTrackCount(), nA = await seq.getAudioTrackCount();
  for (const [kind, n] of [['V', nV], ['A', nA]]) {
    for (let i = 0; i < n; i++) {
      const track = kind === 'V' ? await seq.getVideoTrack(i) : await seq.getAudioTrack(i);
      const items = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false);
      const rows = [];
      for (const it of items.slice(0, maxItems)) {
        const row = { name: await it.getName(), start: +(await it.getStartTime()).seconds.toFixed(3), end: +(await it.getEndTime()).seconds.toFixed(3),
          in: +(await it.getInPoint()).seconds.toFixed(3), out: +(await it.getOutPoint()).seconds.toFixed(3) };
        try { row.components = await readComponents(it, params); } catch (e) { row.components_error = errText(e); }
        rows.push(row);
      }
      tracks.push({ track: kind + (i + 1), count: items.length, items: rows });
    }
  }
  return { name: seq.name, guid: String(seq.guid), video: nV, audio: nA, tracks: tracks.filter((t) => t.count > 0) };
}

function methodsOf(obj) {
  const names = new Set();
  let o = obj;
  for (let i = 0; o && i < 6 && o !== Object.prototype; i++, o = Object.getPrototypeOf(o)) {
    for (const n of Object.getOwnPropertyNames(o)) if (n !== 'constructor') names.add(n);
  }
  return [...names].sort();
}

/** Welche API-Funktionen gibt es tatsächlich in dieser Premiere-Version? Grundlage für Anpassungen. */
async function introspect(ppro) {
  const out = { exports: Object.keys(ppro).sort() };
  const safe = async (fn) => { try { return await fn(); } catch (e) { return { error: errText(e) }; } };
  out.project = await safe(async () => {
    const p = await ppro.Project.getActiveProject();
    return p ? { methods: methodsOf(p), name: p.name, path: p.path } : null;
  });
  out.projectStatic = methodsOf(ppro.Project);
  out.sequence = await safe(async () => {
    const p = await ppro.Project.getActiveProject();
    const s = p && (await p.getActiveSequence());
    if (!s) return null;
    const editor = ppro.SequenceEditor.getEditor(s);
    const v0 = await s.getVideoTrack(0);
    const items = v0.getTrackItems(ppro.Constants.TrackItemType.CLIP, false);
    const r = { methods: methodsOf(s), editor: methodsOf(editor), videoTrack: methodsOf(v0) };
    if (items.length) {
      r.trackItem = methodsOf(items[0]);
      const chain = await items[0].getComponentChain();
      r.chain = methodsOf(chain);
      if (chain.getComponentCount()) { const c = chain.getComponentAtIndex(0); r.component = methodsOf(c); if (c.getParamCount()) r.param = methodsOf(c.getParam(0)); }
    }
    return r;
  });
  out.projectItem = await safe(async () => {
    const p = await ppro.Project.getActiveProject();
    const items = await walkItems(ppro, await p.getRootItem());
    const clip = items.map((i) => asClip(ppro, i)).find(Boolean);
    return clip ? methodsOf(clip) : null;
  });
  out.filters = await safe(async () => (await ppro.VideoFilterFactory.getMatchNames()).filter((n) => /Crop|Roughen|Shadow|Geometry|Gaussian|Blur|Opacity|Motion/i.test(n)));
  return out;
}

/** Fehlersuche: Test-Fach auf mehrere Arten anlegen (und wieder entfernen), um zu sehen, welche Art Premiere akzeptiert. */
async function probeBin(ppro) {
  const NAME = 'GL-Probe';
  const out = [];
  const getProject = () => ppro.Project.getActiveProject();
  const cleanup = async () => {
    try {
      const project = await getProject();
      const root = await project.getRootItem();
      for (const it of await root.getItems()) {
        if (!String(it.name).startsWith(NAME)) continue;
        const p2 = await getProject();
        const r2 = await p2.getRootItem();
        const b = (await r2.getItems()).find((i) => String(i.name).startsWith(NAME));
        p2.lockedAccess(() => { p2.executeTransaction((c) => { c.addAction(r2.createRemoveItemAction(b)); }, 'GL-Probe entfernen'); });
      }
    } catch (e) { out.push({ variante: 'aufräumen', fehler: errText(e) }); }
  };
  const variants = {
    'A: Projekt, Wurzel, Transaktion': async () => {
      const project = await getProject(); const root = await project.getRootItem();
      return project.executeTransaction((c) => { c.addAction(root.createBinAction(NAME, true)); }, 'A');
    },
    'B: wie A, aber in lockedAccess': async () => {
      const project = await getProject(); const root = await project.getRootItem();
      let r; project.lockedAccess(() => { r = project.executeTransaction((c) => { c.addAction(root.createBinAction(NAME, true)); }, 'B'); });
      return r;
    },
    'C: Wurzel erst in der Transaktion holen (ohne await davor)': async () => {
      const project = await getProject();
      const root = await project.getRootItem();
      const action = root.createBinAction(NAME, true);
      return project.executeTransaction((c) => { c.addAction(action); }, 'C');
    },
    'D: Projekt per getActiveProject, Aktion außerhalb der Transaktion erzeugt, Wurzel über Projekt-Eigenschaft': async () => {
      const project = await getProject();
      const root = await project.getRootItem();
      const bin = root.createBinAction(NAME, false);
      return project.executeTransaction((c) => c.addAction(bin), 'D');
    },
  };
  for (const [name, fn] of Object.entries(variants)) {
    const r = { variante: name };
    try { r.ergebnis = String(await fn()); } catch (e) { r.fehler = errText(e); }
    try {
      const project = await getProject();
      const root = await project.getRootItem();
      r.angelegt = (await root.getItems()).some((i) => i.name === NAME);
    } catch (e) { r.pruefung = errText(e); }
    out.push(r);
    await cleanup();
  }
  return out;
}

/** Fehlersuche: Clip auf mehrere Arten in eine Test-Sequenz setzen, um zu sehen, was Premiere akzeptiert. Räumt alles wieder auf. */
async function probePlace(ppro, { png, preset }) {
  const BIN = 'GL-Probe-Clip';
  const { txp, getProj, invalidate, norm } = require('./core');
  const media = require('./media');
  const out = [];
  await media.ensureBin(ppro, await getProj(ppro), BIN);
  await media.importFiles(ppro, await getProj(ppro), [png], BIN);
  const pngName = png.split(/[\/]/).pop();
  const rawItem = async () => (await (await media.getBin(ppro, await getProj(ppro), BIN)).getItems()).find((i) => i.name === pngName);
  const TT = (sec) => ppro.TickTime.createWithSeconds(sec);
  const variants = {
    'roh, V1, A -1': (ed, item) => ed.createOverwriteItemAction(item, TT(0), 0, -1),
    'roh, V1, A 0': (ed, item) => ed.createOverwriteItemAction(item, TT(0), 0, 0),
    'roh, V13, A -1': (ed, item) => ed.createOverwriteItemAction(item, TT(2), 12, -1),
    'roh, V13, A 0': (ed, item) => ed.createOverwriteItemAction(item, TT(2), 12, 0),
    'ClipProjectItem, V1, A -1': (ed, item) => ed.createOverwriteItemAction(ppro.ClipProjectItem.cast(item), TT(0), 0, -1),
    'roh, V1, A 99': (ed, item) => ed.createOverwriteItemAction(item, TT(0), 0, 99),
    'insert roh, V1, A -1': (ed, item) => ed.createInsertProjectItemAction(item, TT(0), 0, -1, false),
  };
  for (const [name, mk] of Object.entries(variants)) {
    const r = { variante: name };
    let guid = null;
    try {
      const seq = await (await getProj(ppro)).createSequenceWithPresetPath('GL-Probe-Seq', preset);
      guid = String(seq.guid); invalidate();
      const project = await getProj(ppro);
      const ed = ppro.SequenceEditor.getEditor((await project.getSequences()).find((x) => String(x.guid) === guid));
      const item = await rawItem();
      await txp(ppro, 'GL-Probe', (add) => add(mk(ed, item)));
      r.ergebnis = 'angenommen';
      const s3 = (await (await getProj(ppro)).getSequences()).find((x) => String(x.guid) === guid);
      const counts = [];
      for (let i = 0; i < 14; i++) { const n = (await s3.getVideoTrack(i)).getTrackItems(ppro.Constants.TrackItemType.CLIP, false).length; if (n) counts.push('V' + (i + 1) + ':' + n); }
      r.spuren = counts.join(' ') || 'keine Clips';
    } catch (e) { r.fehler = errText(e); invalidate(); }
    try {
      if (guid) { const project = await getProj(ppro); const sq = (await project.getSequences()).find((x) => String(x.guid) === guid); if (sq) { await project.deleteSequence(sq); invalidate(); } }
    } catch (e) { r.aufraeumen = errText(e); }
    out.push(r);
  }
  try {
    const project = await getProj(ppro); const root = await project.getRootItem();
    const b = (await root.getItems()).find((i) => i.name === BIN);
    if (b) await txp(ppro, 'GL-Probe aufräumen', (add) => add(root.createRemoveItemAction(b)));
  } catch (e) { out.push({ variante: 'aufräumen', fehler: errText(e) }); }
  return out;
}

module.exports = { probePlace, probeBin, projectDump, sequenceDump, introspect, methodsOf, plainValue, readComponents };
