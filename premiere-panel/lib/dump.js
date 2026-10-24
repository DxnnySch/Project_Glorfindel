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

module.exports = { projectDump, sequenceDump, introspect, methodsOf, plainValue, readComponents };
