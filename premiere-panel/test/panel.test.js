'use strict';
// Tests der Panel-Logik gegen die strenge Premiere-Nachbildung (ohne Premiere). Start: node --test premiere-panel/test
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const fake = require('./fake_ppro');
const { runPlan } = require('../lib/plan');
const media = require('../lib/media');
const dump = require('../lib/dump');
const { selftest } = require('../lib/selftest');
const { Bridge } = require('../lib/bridge');
const fx = require('../lib/effects');

const PLAN = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'plan.json'), 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const newEnv = () => fake.create({ presets: { 'C:/cache/rohschnitt.sqpreset': { video: 14, audio: 16 } } });
const mainSeq = (project) => project.sequences.find((s) => s.name === PLAN.name);
const trackItems = (seq, kind, i) => seq.tracks[kind][i].items;
const compNames = (ti) => ti.chain.comps.map((c) => c.name);
const param = (comp, name) => comp.params.find((p) => p.displayName === name);

test('Bau: alle Clips landen auf den richtigen Spuren, ohne Fehler', async () => {
  const { ppro, project } = newEnv();
  const events = [];
  const rep = await runPlan(ppro, clone(PLAN), (n, d) => events.push([n, d]));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  assert.deepEqual(rep.placed, { episode: 3, still: 2, anim: 3, artwork: 4, credit: 6, voice: 1, marker: PLAN.markers.length });
  const main = mainSeq(project);
  assert.equal(main.tracks.video.length, 14);
  assert.equal(main.tracks.audio.length, 16);
  const v1 = trackItems(main, 'video', 0).sort((a, b) => a.start - b.start);
  assert.deepEqual(v1.map((t) => t.item.name.includes('Sequenz') ? 'episode' : 'still'), ['episode', 'episode', 'still', 'episode', 'still']);
  assert.equal(trackItems(main, 'audio', 3).length, 3, 'Originalton hängt als verknüpfter Clip auf A4');
  assert.equal(trackItems(main, 'audio', 1).length, 1, 'Sprecher Philipp auf A2');
  assert.equal(trackItems(main, 'video', 6).length, 3, 'Pause/Play auf V7');
  assert.ok(trackItems(main, 'video', 2).length + trackItems(main, 'video', 3).length === 4, 'Artworks auf V3/V4');
  assert.equal(trackItems(main, 'video', 8).length, 2, '© amazon studios auf V9');
  assert.equal(trackItems(main, 'video', 9).length + trackItems(main, 'video', 12).length, 4, 'Artwork-Credits auf V10/V13');
  assert.ok(events.some(([n]) => n === 'progress'));
  assert.equal(project.saved, 1);
  assert.equal(main.markers.length, PLAN.markers.length);
});

test('Episoden-Sequenz ist verschachtelt, Segmente tragen die geplanten Quellzeiten, Länge stimmt', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const ep = project.sequences.find((s) => s.name === PLAN.episode_sequence);
  assert.ok(ep, 'Episoden-Sequenz angelegt');
  const main = mainSeq(project);
  for (const c of PLAN.clips.filter((c) => c.kind === 'episode')) {
    const ti = trackItems(main, 'video', 0).find((t) => Math.abs(t.start - c.start) < 0.004);
    assert.ok(ti, 'Segment bei ' + c.start);
    assert.ok(Math.abs(ti.end - c.end) < 0.004, 'Länge ' + (ti.end - ti.start) + ' statt ' + (c.end - c.start));
    assert.equal(ti.item, ep.item);
    assert.equal(ti.inPt, c.src_in);
  }
});

test('Artwork: Zuschnitt, Skalierung, Effektkette wie im Ursprungsschnitt, Farben in 0..1, Keyframes in Clipzeit', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const main = mainSeq(project);
  const art = PLAN.clips.find((c) => c.kind === 'artwork' && c.scale === 100);
  const ti = [...trackItems(main, 'video', 2), ...trackItems(main, 'video', 3)].find((t) => Math.abs(t.start - art.start) < 0.004);
  assert.deepEqual(compNames(ti), ['Bewegung', 'Deckkraft', 'AE.ADBE Crop', 'AE.ADBE Drop Shadow', 'AE.ADBE Geometry', 'AE.ADBE Roughen Edges', 'AE.ADBE Roughen Edges']);
  const [motion, , crop, shadow, geo, out, inn] = ti.chain.comps;
  assert.equal(param(crop, 'Links').value, 25);
  assert.equal(param(crop, 'Rechts').value, 25);
  assert.equal(param(motion, 'Skalierung').value, 100);
  assert.equal(param(shadow, 'Abstand').value, 31);
  assert.deepEqual(param(geo, 'Skalierungshöhe').kfs.at(-1), [120, 240]);
  const col = param(inn, 'Konturfarbe').value;
  assert.ok(col.red > 0.8 && col.red < 0.85 && col.green > 0.3 && col.blue < 0.2 && col.alpha === 1, 'Konturfarbe #d45329 in 0..1: ' + JSON.stringify(col));
  assert.deepEqual(param(inn, 'Rahmen').kfs, [[0, 500], [0.5, 8]]);
  const dur = art.end - art.start;
  const outKf = param(out, 'Rahmen').kfs;
  assert.ok(Math.abs(outKf[0][0] - (dur - 0.5333)) < 0.01 && outKf.at(-1)[1] === 500 && Math.abs(outKf.at(-1)[0] - (dur - 0.0167)) < 0.01);
});

test('Credits blenden über die Deckkraft ein und aus; Standbild bekommt den Weichzeichner', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const main = mainSeq(project);
  const credit = PLAN.clips.find((c) => c.kind === 'credit' && c.track === 9);
  const ti = trackItems(main, 'video', 9).find((t) => Math.abs(t.start - credit.start) < 0.004);
  const op = ti.chain.comps.find((c) => c.name === 'Deckkraft').params[0];
  const dur = credit.end - credit.start;
  assert.deepEqual(op.kfs.map(([t]) => +t.toFixed(2)), [0, 0.42, +(dur - 0.42).toFixed(2), +dur.toFixed(2)]);
  assert.deepEqual(op.kfs.map(([, v]) => v), [0, 100, 100, 0]);
  const stills = trackItems(main, 'video', 0).filter((t) => t.item.name.endsWith('.png'));
  const blurred = stills.find((t) => t.chain.comps.some((c) => c.name === 'AE.ADBE Gaussian Blur 2'));
  assert.ok(blurred, 'Standbild mit Blur');
  const kf = blurred.chain.comps.find((c) => c.name === 'AE.ADBE Gaussian Blur 2').params[0].kfs;
  assert.deepEqual(kf.map(([, v]) => v), [0, 15, 15, 0]);
});

test('Import: nie als Bildfolge (1.png, 2.png); jede Datei nur einmal', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const imports = project.calls.filter((c) => c[0] === 'importFiles');
  assert.ok(imports.length >= 1 && imports.every((c) => c[2] === false));
  const root = await project.getRootItem();
  const bin = (await root.getItems()).find((i) => i.name === PLAN.bin);
  const names = (await bin.getItems()).filter((i) => i.path).map((i) => i.path);
  assert.equal(new Set(names).size, names.length);
});

test('Fehler brechen den Bau nicht ab, sondern landen im Bericht', async () => {
  const { ppro, project } = newEnv();
  const plan = clone(PLAN);
  plan.clips.find((c) => c.kind === 'still').media = 'm999';                 // Medium, das es nicht gibt
  const rep = await runPlan(ppro, plan);
  assert.equal(rep.errors.length, 1);
  assert.match(rep.errors[0].was, /still/);
  assert.equal(rep.placed.episode, 3, 'der Rest wurde gebaut');
  assert.equal(rep.placed.still, 1);
});

test('zu wenig Spuren: Warnung statt stiller Fehler; fehlende Vorgabe: klare Meldung', async () => {
  const small = fake.create({ presets: { 'C:/cache/rohschnitt.sqpreset': { video: 5, audio: 5 } } });
  const rep = await runPlan(small.ppro, clone(PLAN));
  assert.ok(rep.warnings.some((w) => /nur 5 Video/.test(w)));
  assert.ok(rep.errors.some((e) => /Videospur/.test(e.fehler)), 'Clips auf Spuren > 5 werden gemeldet');
  const none = fake.create({ presets: {} });
  await assert.rejects(() => runPlan(none.ppro, clone(PLAN)), /Vorgabe nicht gefunden/);
});

test('HQ-Tausch: nur die Datei wechselt, Clips bleiben; Standbilder werden neu geladen', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const main = mainSeq(project);
  const before = trackItems(main, 'video', 0).map((t) => [t.start, t.end, t.chain.comps.length]);
  const epPath = PLAN.media.find((m) => m.kind === 'episode').path;
  const stillsDir = PLAN.media.find((m) => m.kind === 'still').path.replace(/[\\/][^\\/]+$/, '');
  const rep = await media.swapMedia(ppro, project, { swaps: [{ from: epPath, to: 'F:/HQ/S3E1_HQ_conform.mov' }, { from: 'F:/gibt/es/nicht.mp4', to: 'x' }], refresh: [stillsDir] });
  assert.equal(rep.getauscht.length, 1);
  assert.equal(rep.fehler.length, 1);
  assert.match(rep.fehler[0].fehler, /nicht gefunden/);
  assert.equal(rep.neu_geladen, 2);
  const all = await media.allMedia(ppro, project);
  assert.ok(all.has('f:/hq/s3e1_hq_conform.mov') && !all.has(epPath.toLowerCase().replace(/\\/g, '/')));
  assert.deepEqual(trackItems(main, 'video', 0).map((t) => [t.start, t.end, t.chain.comps.length]), before, 'Schnitt unverändert');
  const bad = await media.swapMedia(ppro, project, { swaps: [{ from: 'F:/HQ/S3E1_HQ_conform.mov', to: 'F:/nichtda.mov' }] });
  assert.match(bad.fehler[0].fehler, /Datei nicht gefunden/);
});

test('Auslesen: Projekt und Sequenz mit Effekten, Parametern und Keyframes', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const pd = await dump.projectDump(ppro);
  assert.equal(pd.open, true);
  assert.deepEqual(pd.sequences.map((s) => s.name).sort(), [PLAN.name, PLAN.episode_sequence].sort());
  const sd = await dump.sequenceDump(ppro, { name: PLAN.name, maxItems: 50 });
  assert.equal(sd.video, 14);
  const v3 = sd.tracks.find((t) => t.track === 'V3') || sd.tracks.find((t) => t.track === 'V4');
  const comps = v3.items[0].components.map((c) => c.name);
  assert.ok(comps.includes('AE.ADBE Roughen Edges'));
  const rough = v3.items[0].components.find((c) => c.name === 'AE.ADBE Roughen Edges');
  assert.ok(rough.params.find((p) => p.name === 'Rahmen').keyframes.length >= 2);
  const intro = await dump.introspect(ppro);
  assert.ok(intro.exports.includes('Project') && intro.sequence.editor.includes('createOverwriteItemAction'));
});

test('Selbsttest: prüft alles, räumt vollständig auf und berührt keine vorhandene Sequenz', async () => {
  const { ppro, project } = fake.create({ presets: { 'C:/p/test.sqpreset': { video: 14, audio: 16 } } });
  const root = await project.getRootItem();
  const rep = await selftest(ppro, { png: 'F:/x/test.png', preset: 'C:/p/test.sqpreset' });
  assert.equal(rep.ok, true, JSON.stringify(rep.steps.filter((s) => !s.ok)));
  assert.equal(rep.findings.colorMode, 'unit');
  assert.deepEqual(rep.findings.keyframeTimes, [0, 0.5]);
  assert.equal(rep.findings.keyframeOrigin, 'clipanfang');
  assert.ok(rep.findings.cropParams.includes('Links') && rep.findings.roughParams.includes('Rahmen'));
  assert.equal(project.sequences.length, 0, 'Test-Sequenz entfernt');
  assert.equal((await root.getItems()).length, 0, 'Test-Fach entfernt');
});

test('Effekte: Parameter nach Namen, sonst nach Position; Farbe im dokumentierten Bereich', async () => {
  const { ppro } = newEnv();
  const comp = await ppro.VideoFilterFactory.createComponent('AE.ADBE Roughen Edges');
  assert.equal(fx.findParam(comp, ['Border', 'Rahmen'], 2).displayName, 'Rahmen');
  assert.equal(fx.findParam(comp, ['Gibt es nicht'], 2).displayName, 'Rahmen', 'Rückfall auf Listenposition');
  assert.equal(fx.findParam(comp, ['Gibt es nicht'], 99), null);
  const c = fx.toPproValue(ppro, { argb16: [0xFF00, 0xD400, 0x5300, 0x2900] }, {});
  assert.ok(Math.abs(c.red - 212 / 255) < 1e-9 && c.alpha === 1);
  assert.throws(() => fx.toPproValue(ppro, { argb16: [0xFF00, 0xD400, 0x5300, 0x2900] }, { colorMode: 'byte' }), /\[0\.0, 1\.0\]/);
  const pt = fx.toPproValue(ppro, { point: [0.5, 0.25] }, {});
  assert.ok(pt.x === 0.5 && pt.y === 0.25);
});

// ---- Protokoll ----
class FakeWS {
  constructor(url) { this.url = url; this.sent = []; FakeWS.last = this; setTimeout(() => this.onopen && this.onopen(), 0); }
  send(s) { this.sent.push(JSON.parse(s)); }
  close() { this.onclose && this.onclose(); }
  recv(o) { return this.onmessage({ data: JSON.stringify(o) }); }
}

test('Bridge: koppelt per Token, beantwortet Aufrufe, meldet Fortschritt, lehnt Unbekanntes und Paralleles ab', async () => {
  const { ppro } = newEnv();
  const states = [];
  const fetchImpl = async (url) => (/:8767\//.test(url) ? { ok: true, json: async () => ({ token: 'geheim+/=' }) } : { ok: false });
  const b = new Bridge({ ppro, WebSocketImpl: FakeWS, fetchImpl, hostInfo: { name: 'premierepro', version: '26.5.2' }, onStatus: (s) => states.push(s.state) });
  const srv = await b.findServer();
  assert.deepEqual(srv, { port: 8767, token: 'geheim+/=' });
  const session = b.session(srv);
  await new Promise((r) => setTimeout(r, 10));
  const ws = FakeWS.last;
  assert.match(ws.url, /^ws:\/\/127\.0\.0\.1:8767\/api\/bridge\/ws\?token=geheim%2B%2F%3D$/);
  assert.equal(ws.sent[0].t, 'hello');
  assert.equal(ws.sent[0].info.premiere, '26.5.2');
  assert.equal(ws.sent[0].info.project.name, 'Test.prproj');
  await ws.recv({ t: 'welcome' });
  assert.ok(states.includes('verbunden'));
  await ws.recv({ t: 'call', id: 1, op: 'ping', args: {} });
  assert.deepEqual(ws.sent.at(-1), { t: 'result', id: 1, ok: true, data: { pong: true, time: ws.sent.at(-1).data.time } });
  await ws.recv({ t: 'call', id: 2, op: 'rm -rf', args: {} });
  assert.deepEqual(ws.sent.at(-1), { t: 'result', id: 2, ok: false, error: 'Unbekannte Operation: rm -rf' });
  b.handlers['plan.run'] = async (a, emit) => { emit('progress', { text: 'läuft' }); await new Promise((r) => setTimeout(r, 60)); return { errors: [] }; };
  const run = ws.recv({ t: 'call', id: 3, op: 'plan.run', args: { plan: clone(PLAN) } });
  await new Promise((r) => setTimeout(r, 0));
  await ws.recv({ t: 'call', id: 4, op: 'project.dump', args: {} });                 // parallel: abgelehnt
  assert.match(ws.sent.find((m) => m.id === 4).error, /arbeitet noch/);
  await run;
  const res = ws.sent.find((m) => m.t === 'result' && m.id === 3);
  assert.equal(res.ok, true);
  assert.equal(res.data.errors.length, 0);
  assert.ok(ws.sent.some((m) => m.t === 'event' && m.id === 3 && m.name === 'progress'));
  ws.close();
  await session;
});
