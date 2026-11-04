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
const { getProj } = require('../lib/core');

const PLAN = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'plan.json'), 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const newEnv = () => fake.create({ presets: { 'C:/cache/rohschnitt.sqpreset': { video: 14, audio: 16 }, 'C:/cache/artwork.sqpreset': { video: 5, audio: 1 } } });
const mainSeq = (project) => project.sequences.find((s) => s.name === PLAN.name);
const trackItems = (seq, kind, i) => seq.tracks[kind][i].items;
const compNames = (ti) => ti.chain.comps.map((c) => c.name);
const param = (comp, name) => comp.params.find((p) => p.displayName === name);

test('Bau: alle Clips landen auf den richtigen Spuren, ohne Fehler', async () => {
  const { ppro, project } = newEnv();
  const events = [];
  const rep = await runPlan(ppro, clone(PLAN), (n, d) => events.push([n, d]));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  assert.deepEqual(rep.placed, { episode: 3, still: 2, anim: 3, artwork: 4, credit: 8, credit_text: 8, voice: 1, bars: 1, marker: PLAN.markers.length });
  const main = mainSeq(project);
  assert.equal(main.tracks.video.length, 14);
  assert.equal(main.tracks.audio.length, 16);
  const v1 = trackItems(main, 'video', 0).sort((a, b) => a.start - b.start);
  assert.deepEqual(v1.map((t) => t.item.name.includes('Sequenz') ? 'episode' : 'still'), ['episode', 'episode', 'still', 'episode', 'still']);
  assert.equal(trackItems(main, 'audio', 3).length, 3, 'Originalton hängt als verknüpfter Clip auf A4');
  assert.equal(trackItems(main, 'audio', 1).length, 1, 'Sprecher Philipp auf A2');
  assert.equal(trackItems(main, 'video', 6).length, 3, 'Pause/Play auf V7');
  assert.ok(trackItems(main, 'video', 2).length + trackItems(main, 'video', 3).length === 4, 'Artworks auf V3/V4');
  assert.equal(trackItems(main, 'video', 8).length, 4, '© amazon studios auf V9, an den Künstler-Credits unterbrochen');
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

test('Artwork: verschachtelte Sequenz mit Bild, Maske und Spurmaske-Key; Effekte liegen auf der Sequenz, Farben 0..1, Keyframes in Clipzeit', async () => {
  const { ppro, project } = newEnv();
  const rep = await runPlan(ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const main = mainSeq(project);
  const art = PLAN.clips.find((c) => c.kind === 'artwork');
  const n = PLAN.nested.find((x) => x.id === art.nested);
  const nested = project.sequences.find((s) => s.name === n.name);
  assert.ok(nested, 'Artwork-Sequenz angelegt');
  assert.equal(nested.tracks.video.length, 5);
  const img = trackItems(nested, 'video', 2)[0], mask = trackItems(nested, 'video', 4)[0];
  assert.ok(img && mask, 'Bild auf V3, Maske auf V5');
  assert.ok(/Maske/.test(mask.item.path));
  assert.ok(Math.abs(img.end - n.dur) < 0.004 && Math.abs(mask.end - n.dur) < 0.004, 'beide so lang wie das Artwork');
  assert.equal(param(img.chain.comps[0], 'Skalieren').value, n.image_scale);
  assert.equal(param(mask.chain.comps[0], 'Skalieren').value, n.mask_scale);
  const matte = img.chain.comps.find((c) => c.name === 'AE.ADBE Legacy Key Track Matte');
  assert.ok(matte, 'Spurmaske-Key am Bild');
  assert.equal(param(matte, 'Maske:').value, 5);
  const ti = [...trackItems(main, 'video', 2), ...trackItems(main, 'video', 3)].find((t) => Math.abs(t.start - art.start) < 0.004);
  assert.equal(ti.item, nested.item, 'Hauptsequenz enthält die verschachtelte Sequenz');
  assert.deepEqual(compNames(ti), ['Bewegung', 'Deckkraft', 'AE.ADBE Drop Shadow', 'AE.ADBE Geometry2', 'AE.ADBE Roughen Edges', 'AE.ADBE Roughen Edges']);
  const [, , shadow, geo, out, inn] = ti.chain.comps;
  assert.equal(param(shadow, 'Abstand').value, 31);
  assert.deepEqual(param(geo, 'Skalierungshöhe').kfs.at(-1), [120, 240]);
  const col = param(inn, 'Konturfarbe').value;
  assert.ok(col.red > 0.8 && col.red < 0.85 && col.green > 0.3 && col.blue < 0.2 && col.alpha === 1, 'Konturfarbe #d45329 in 0..1: ' + JSON.stringify(col));
  assert.deepEqual(param(inn, 'Rahmen').kfs, [[0, 500], [0.5, 8]]);
  const dur = art.end - art.start;
  const outKf = param(out, 'Rahmen').kfs;
  assert.ok(Math.abs(outKf[0][0] - (dur - 0.5333)) < 0.01 && outKf.at(-1)[1] === 500 && Math.abs(outKf.at(-1)[0] - (dur - 0.0167)) < 0.01);
});

test('Pause/Play kommen aus eigenen .mov-Dateien (keine After-Effects-Komposition)', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const v7 = trackItems(mainSeq(project), 'video', 6);
  assert.equal(v7.length, 3);
  assert.ok(v7.every((t) => /(Pause|Play)\.mov$/.test(t.item.path)));
  assert.ok(!project.calls.some((c) => c[0] === 'importAEComps'));
});

test('Credits blenden per Cross Dissolve ein und aus (Deckkraft bleibt unberührt); Standbild bekommt den Weichzeichner', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const main = mainSeq(project);
  const credit = PLAN.clips.find((c) => c.kind === 'credit' && c.track === 9);
  const ti = trackItems(main, 'video', 9).find((t) => Math.abs(t.start - credit.start) < 0.004);
  const op = ti.chain.comps.find((c) => c.name === 'Deckkraft').params[0];
  assert.equal(ti.transitions.length, 2, 'Cross Dissolve am Anfang und Ende');
  assert.ok(!op.varying, 'keine zusätzliche Deckkraft-Animation');
  const stills = trackItems(main, 'video', 0).filter((t) => t.item.name.endsWith('.png'));
  const blurred = stills.find((t) => t.chain.comps.some((c) => c.name === 'AE.Impact_Blur_FX'));
  assert.ok(blurred, 'Standbild mit Blur');
  const kf = blurred.chain.comps.find((c) => c.name === 'AE.Impact_Blur_FX').params.find((p) => p.displayName === 'Stärke').kfs;
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

test('HQ-Tausch ist wiederholbar: bereits getauschte Dateien gelten als erledigt', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const stills = PLAN.media.filter((m) => m.kind === 'still').map((m) => m.path);
  const swaps = stills.map((p) => ({ from: p, to: p.replace('/Videoelemente/', '/Videoelemente_HQ/') }));
  const first = await media.swapMedia(ppro, project, { swaps });
  assert.equal(first.getauscht.length, stills.length);
  const again = await media.swapMedia(ppro, project, { swaps });
  assert.deepEqual(again.fehler, []);
  assert.equal(again.schon.length, stills.length);
});

test('Auslesen: Projekt und Sequenz mit Effekten, Parametern und Keyframes', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const pd = await dump.projectDump(ppro);
  assert.equal(pd.open, true);
  assert.deepEqual(pd.sequences.map((s) => s.name).filter((n) => !n.startsWith('Artwork ')).sort(), [PLAN.name, PLAN.episode_sequence].sort());
  assert.equal(pd.sequences.filter((s) => s.name.startsWith('Artwork ')).length, PLAN.nested.length);
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
  const rep = await selftest(ppro, { png: 'F:/x/test.png', preset: 'C:/p/test.sqpreset', mogrts: { amazon: 'C:/vorlagen/mogrt/Credit Amazon.mogrt', artwork: 'C:/vorlagen/mogrt/Credit Artwork.mogrt' } });
  assert.equal(rep.ok, true, JSON.stringify(rep.steps.filter((s) => !s.ok)));
  assert.ok(rep.steps.some((s) => s.name === 'Eigene Vorlage: amazon' && s.ok) && rep.findings.eigeneVorlagen.artwork.parameter);
  assert.equal(rep.findings.colorMode, 'unit');
  assert.deepEqual(rep.findings.keyframeTimes, [0, 0.5]);
  assert.equal(rep.findings.keyframeOrigin, 'clipanfang');
  assert.equal(rep.findings.cropMatch, 'AE.ADBE AECrop', 'Zuschneiden-Name zur Laufzeit gefunden');
  assert.ok(rep.findings.filters.some((f) => f.match === 'AE.ADBE AECrop' && f.display === 'Zuschneiden'));
  assert.ok(rep.findings.cropParams.includes('Links') && rep.findings.roughParams.includes('Rahmen'));
  assert.equal(project.sequences.length, 0, 'Test-Sequenz entfernt');
  assert.equal((await (await project.getRootItem()).getItems()).length, 0, 'Test-Fach entfernt');
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

test('Amazon-Credit ist nie zugleich mit einem Künstler-Credit zu sehen; Schwarzstreifen liegen auf V8 über die ganze Länge', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const main = mainSeq(project);
  const amazon = trackItems(main, 'video', 8);
  const artists = [...trackItems(main, 'video', 9), ...trackItems(main, 'video', 12)];
  for (const a of amazon) for (const b of artists) assert.ok(a.end <= b.start + 0.004 || a.start >= b.end - 0.004, 'Überlappung ' + [a.start, a.end, b.start, b.end]);
  const bars = trackItems(main, 'video', 7);
  assert.equal(bars.length, 1);
  assert.equal(bars[0].name, 'Schwarzstreifen');
  assert.ok(bars[0].start < 0.01 && Math.abs(bars[0].end - Math.max(...PLAN.clips.filter((c) => c.kind !== 'bars' && c.kind !== 'adjust').map((c) => c.end))) < 0.01);
});

test('Gauß In/Out: Einstellungsebene beginnt bei 3600 s – Keyframes gelten dann für beide Zeitbezüge (ab Clipanfang und im Quellmaterial)', async () => {
  const env = newEnv();
  const adj = new env.ClipItem(env.project, 'Einstellungsebene', null, { hasVideo: true, length: 5 });
  adj.adjustment = true; adj.inPt = 3600; adj.outPt = 3605;           // wie im Ursprungsschnitt: Quellmaterial beginnt bei 1:00:00:00
  (await env.project.getRootItem()).children.push(adj);
  const rep = await runPlan(env.ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const c = PLAN.clips.find((x) => x.kind === 'adjust');
  const ti = trackItems(mainSeq(env.project), 'video', 1).find((t) => Math.abs(t.start - c.start) < 0.004);
  const kf = ti.chain.comps.find((k) => k.name === 'AE.Impact_Blur_FX').params.find((p) => p.displayName === 'Stärke').kfs;
  const rel = c.effects[0].params[0].keyframes;
  assert.equal(kf.length, rel.length * 2);
  rel.forEach(([t, v], i) => { assert.ok(Math.abs(kf[i][0] - t) < 1e-3 && kf[i][1] === v); assert.ok(Math.abs(kf[i + rel.length][0] - (3600 + t)) < 1e-3 && kf[i + rel.length][1] === v); });
  assert.ok(kf.every(([t], i) => i === 0 || t >= kf[i - 1][0]), 'Zeiten aufsteigend');
});

test('Gauß In/Out: mit Einstellungsebene im Projekt liegt es auf V2, ohne Einstellungsebene als Rückfall am Standbild (mit Hinweis)', async () => {
  const withAdj = newEnv();
  const adj = new withAdj.ClipItem(withAdj.project, 'Einstellungsebene', null, { hasVideo: true, length: 5 });
  adj.adjustment = true;
  (await withAdj.project.getRootItem()).children.push(adj);       // roh angelegt wie „Datei → Neu → Einstellungsebene“
  const rep = await runPlan(withAdj.ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const v2 = trackItems(mainSeq(withAdj.project), 'video', 1);
  assert.equal(v2.length, PLAN.clips.filter((c) => c.kind === 'adjust').length);
  const kf = v2[0].chain.comps.find((c) => c.name === 'AE.Impact_Blur_FX').params.find((p) => p.displayName === 'Stärke').kfs;
  assert.deepEqual(kf.map(([, v]) => v), [0, 15, 15, 0]);
  const stills = trackItems(mainSeq(withAdj.project), 'video', 0).filter((t) => t.item.name.endsWith('.png'));
  assert.ok(stills.every((t) => !t.chain.comps.some((c) => c.name === 'AE.Impact_Blur_FX')), 'kein Doppel-Blur');
  assert.ok(!rep.warnings.some((w) => /Einstellungsebene/.test(w)));
  const without = newEnv();
  const rep2 = await runPlan(without.ppro, clone(PLAN));
  assert.ok(rep2.warnings.some((w) => /Keine Einstellungsebene/.test(w)));
  assert.equal(trackItems(mainSeq(without.project), 'video', 1).length, 0);
});

test('Tausch: nur im Fach dieses Baus; gleiche Datei in mehreren Fächern bleibt in älteren Ständen unberührt', async () => {
  const { ppro, project } = newEnv();
  const f = 'F:/Test/ref.mp4';
  for (const bin of ['Bau v1', 'Bau v2']) {
    await media.ensureBin(ppro, await getProj(ppro), bin);
    await media.importFiles(ppro, await getProj(ppro), [f], bin);
  }
  const rep = await media.swapMedia(ppro, project, { swaps: [{ from: f, to: 'F:/HQ/hq.mp4' }], bin: 'Bau v2' });
  assert.deepEqual(rep.fehler, []);
  const inBin = async (bin) => [...(await media.mediaByPath(ppro, await media.getBin(ppro, await getProj(ppro), bin))).keys()];
  assert.deepEqual(await inBin('Bau v2'), ['f:/hq/hq.mp4']);
  assert.deepEqual(await inBin('Bau v1'), ['f:/test/ref.mp4']);
  const all = await media.swapMedia(ppro, project, { swaps: [{ from: f, to: 'F:/HQ/hq1.mp4' }] });      // ohne Fach: ganzes Projekt
  assert.deepEqual(all.fehler, []);
  assert.deepEqual(await inBin('Bau v1'), ['f:/hq/hq1.mp4']);
});

test('Übergänge: Überlagerungen bekommen Cross Dissolve an Anfang und Ende, Serienclips nur an den Szenenkanten', async () => {
  const { ppro, project } = newEnv();
  const rep = await runPlan(ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const main = mainSeq(project);
  const all = (kind) => main.tracks.video.flatMap((t) => t.items);
  const plan = PLAN.clips.filter((c) => c.uebergang);
  assert.ok(plan.length >= 8, 'Plan enthält Übergänge');
  for (const c of plan) {
    const ti = all().find((t) => t.kind === 'video' && Math.abs(t.start - c.start) < 0.004 && t.idx === c.track);
    assert.ok(ti, c.kind + ' @' + c.start);
    const want = [c.uebergang.ein && ['start', c.uebergang.ein], c.uebergang.aus && ['end', c.uebergang.aus]].filter(Boolean);
    assert.equal(ti.transitions.length, want.length, c.kind + ' @' + c.start + ' ' + JSON.stringify(ti.transitions));
    for (const [side, d] of want) {
      const tr = ti.transitions.find((x) => x.start === (side === 'start'));
      assert.ok(tr, side);
      assert.equal(tr.match, PLAN.transitions.video.match_name);
      assert.ok(Math.abs(tr.dur - d) < 1e-6 && tr.single === true, 'Dauer ' + tr.dur + ' einseitig');
    }
  }
  assert.equal(rep.effects.uebergang, plan.reduce((n, c) => n + (c.uebergang.ein ? 1 : 0) + (c.uebergang.aus ? 1 : 0), 0));
});

test('Übergänge: Credits fallen auf Deckkraft-Ein-/Ausblendung zurück, wenn Premiere den Übergang nicht kennt', async () => {
  const { ppro, project } = newEnv();
  const p = clone(PLAN);
  p.transitions.video.match_name = 'AE.ADBE Gibt Es Nicht';
  const rep = await runPlan(ppro, p);
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  assert.ok(rep.warnings.some((w) => /Übergang/.test(w)), rep.warnings.join('|'));
  const credit = mainSeq(project).tracks.video.flatMap((t) => t.items).find((t) => t.name.startsWith('© alan lee'));
  const op = credit.chain.comps.find((c) => c.name === 'Deckkraft').params[0];
  assert.ok(op.varying && op.kfs.length === 4, 'Rückfall: Deckkraft-Keyframes');
  assert.equal(credit.transitions.length, 0);
});

test('Serienton: Gleichleistungs-Blenden als Pegel-Keyframes auf der Tonspur des Serienclips', async () => {
  const { ppro, project } = newEnv();
  const rep = await runPlan(ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const main = mainSeq(project);
  for (const c of PLAN.clips.filter((c) => c.kind === 'episode')) {
    const ti = trackItems(main, 'audio', c.audio).find((t) => Math.abs(t.start - c.start) < 0.004);
    assert.ok(ti, 'Ton bei ' + c.start);
    const level = ti.chain.comps.find((k) => k.name === 'Lautstärke').params.find((q) => q.displayName === 'Pegel');
    assert.ok(level.varying && level.kfs.length === c.ton_blende.keyframes.length);
    assert.equal(level.kfs.length, c.ton_blende.keyframes.length);
    assert.ok(ti.inPt > 1, 'Serienclip beginnt nicht am Quellanfang');
    level.kfs.forEach(([t], i) => assert.ok(Math.abs(t - (ti.inPt + c.ton_blende.keyframes[i][0])) < 1e-3, 'Zeit im Quellmaterial ' + i));   // Premiere führt Keyframes im Quellmaterial: ohne Einstiegspunkt läge die Blende vor dem Clip (Ton stumm)
    assert.ok(level.kfs.every(([, v]) => v >= 0 && v <= 1), 'lineare Amplitude 0..1');
    assert.ok(Math.abs(level.kfs[0][1] - (c.ton_blende.ein > 0 ? 0 : 1)) < 1e-9);
  }
  assert.equal(rep.effects.ton_blende, PLAN.clips.filter((c) => c.kind === 'episode').length);
});

test('Serienton: Pegel in dB, wenn Premiere den Pegel so führt (Modus wird am Clip erkannt)', async () => {
  const { ppro: p2, project: pr2 } = newEnv();
  const origOverwrite = p2.SequenceEditor.getEditor;
  p2.SequenceEditor.getEditor = (seq) => {
    const ed = origOverwrite(seq);
    const o = ed.createOverwriteItemAction;
    ed.createOverwriteItemAction = (...a) => { const act = o(...a); const r = act.run; act.run = () => { r(); for (const t of seq.tracks.audio) for (const ti of t.items) ti.chain.comps.find((c) => c.name === 'Lautstärke').params[1].value = 0; }; return act; };
    return ed;
  };
  const rep = await runPlan(p2, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const c = PLAN.clips.find((x) => x.kind === 'episode');
  const ti = trackItems(mainSeq(pr2), 'audio', c.audio).find((t) => Math.abs(t.start - c.start) < 0.004);
  const level = ti.chain.comps.find((k) => k.name === 'Lautstärke').params[1];
  assert.ok(level.kfs.every(([, v]) => v <= 1e-9 && v >= -90 - 1e-9), 'dB-Werte ≤ 0');
  assert.ok(level.kfs.some(([, v]) => v < -20) && level.kfs.some(([, v]) => v === 0));
});

const creditItems = (main) => main.tracks.video.flatMap((t) => t.items).filter((t) => PLAN.clips.some((c) => c.kind === 'credit' && c.track === t.idx && Math.abs(c.start - t.start) < 0.004));

test('Credits als Text: Vorlage eingesetzt, Text über das Textobjekt gesetzt (Formatierung bleibt), Länge, Name, Übergänge', async () => {
  const { ppro, project } = newEnv();
  const rep = await runPlan(ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  assert.equal(rep.placed.credit, PLAN.clips.filter((c) => c.kind === 'credit').length);
  assert.equal(rep.placed.credit_text, rep.placed.credit, 'alle Credits als editierbarer Text');
  const main = mainSeq(project);
  for (const c of PLAN.clips.filter((x) => x.kind === 'credit')) {
    const ti = trackItems(main, 'video', c.track).find((t) => Math.abs(t.start - c.start) < 0.004);
    assert.ok(ti, c.name + ' @' + c.start);
    assert.match(ti.item.name, /^Credit /, 'aus der Vorlage, nicht das PNG');
    assert.ok(Math.abs(ti.end - c.end) < 0.004, 'Länge');
    assert.equal(ti.name, c.name);
    const text = ti.chain.comps.find((k) => k.name === 'Grafikparameter').params.find((p) => p.displayName === 'Quelltext');
    assert.equal(text.value.getText(), c.mogrt.text, 'Text über das Textobjekt (Premiere 27.0) gesetzt');
    assert.equal(text.value.getFontName(), 'GrandCentral-Light', 'Formatierung der Vorlage unberührt');
    assert.equal(ti.transitions.length, 2);
  }
});

test('Credits als Text: ältere Vorlagen mit Textdokument (JSON) werden weiter unterstützt', async () => {
  const { ppro, project } = newEnv();
  project.mogrts.push('C:/vorlagen/mogrt/Credit JsonText.mogrt');
  const plan = clone(PLAN);
  for (const c of plan.clips) if (c.mogrt) c.mogrt.path = 'C:/vorlagen/mogrt/Credit JsonText.mogrt';
  const rep = await runPlan(ppro, plan);
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const c = plan.clips.find((x) => x.kind === 'credit' && x.mogrt);
  const ti = trackItems(mainSeq(project), 'video', c.track).find((t) => Math.abs(t.start - c.start) < 0.004);
  const doc = JSON.parse(ti.chain.comps.find((k) => k.name === 'Grafikparameter').params.find((p) => p.displayName === 'Text').value);
  assert.equal(doc.textEditValue, c.mogrt.text);
  assert.equal(doc.fontSizeEditValue, 50);
});

test('Credits als Text: fehlt die Vorlage, wird das PNG gesetzt (mit Hinweis), der Bau läuft weiter', async () => {
  const { ppro, project } = newEnv();
  project.mogrts.length = 0;
  const rep = await runPlan(ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  assert.ok(rep.warnings.some((w) => /Vorlage|MOGRT/i.test(w)), rep.warnings.join('|'));
  assert.equal(rep.placed.credit, PLAN.clips.filter((c) => c.kind === 'credit').length);
  assert.equal(rep.placed.credit_text || 0, 0);
  assert.ok(creditItems(mainSeq(project)).every((t) => /\.png$/.test(t.item.name)));
});

test('Credits als Text: lässt sich der Text nicht setzen, wird die Vorlage wieder entfernt und das PNG gesetzt (kein Standardtext)', async () => {
  const { ppro, project } = newEnv();
  project.mogrts.push('C:/vorlagen/mogrt/Credit OhneText.mogrt');
  const plan = clone(PLAN);
  for (const c of plan.clips) if (c.mogrt) c.mogrt.path = 'C:/vorlagen/mogrt/Credit OhneText.mogrt';
  const rep = await runPlan(ppro, plan);
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  assert.ok(rep.warnings.some((w) => /Credit-Text konnte nicht/.test(w)), rep.warnings.join('|'));
  assert.equal(rep.placed.credit, PLAN.clips.filter((c) => c.kind === 'credit').length);
  const items = creditItems(mainSeq(project));
  assert.ok(items.length && items.every((t) => /\.png$/.test(t.item.name)), items.map((t) => t.item.name).join(','));
}).timeout?.(30000);

test('Credits als Text: Doppelbild-Credit wird seitlich verschoben, Einzelbild bleibt am Vorgabeort', async () => {
  const { ppro, project } = newEnv();
  await runPlan(ppro, clone(PLAN));
  const main = mainSeq(project);
  const shifted = PLAN.clips.filter((c) => c.kind === 'credit' && c.mogrt && c.mogrt.dx !== 0);
  assert.ok(shifted.length >= 1, 'Plan enthält Doppelbild-Credits');
  for (const c of shifted) {
    const ti = trackItems(main, 'video', c.track).find((t) => Math.abs(t.start - c.start) < 0.004);
    const pos = param(ti.chain.comps.find((k) => k.name === 'Bewegung'), 'Position');
    assert.ok(Math.abs(pos.value.x - (0.5 + c.mogrt.dx)) < 1e-9 && pos.value.y === 0.5);
  }
  const plain = PLAN.clips.find((c) => c.kind === 'credit' && c.mogrt && c.mogrt.dx === 0);
  const ti = trackItems(main, 'video', plain.track).find((t) => Math.abs(t.start - plain.start) < 0.004);
  assert.deepEqual([param(ti.chain.comps.find((k) => k.name === 'Bewegung'), 'Position').value.x], [0.5]);
});
