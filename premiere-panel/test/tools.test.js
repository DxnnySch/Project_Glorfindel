'use strict';
// Werkzeuge (Kurzbefehle) gegen die Premiere-Nachbildung: Auswahl lesen, Effekte, Überblendung, Ton-Blende, Länge, Credit, Artwork, Szene.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const fake = require('./fake_ppro');
const { runPlan } = require('../lib/plan');
const { Tools } = require('../lib/tools');
const { Bridge, makeHandlers } = require('../lib/bridge');
const { buildTools, toolsNotReady } = require('../lib/toolbar');
const mogrtLib = require('../lib/mogrt');
Object.assign(mogrtLib.timing, { timeout: 80, step: 1 });   // Warten auf die Grafik der Vorlage: in Tests kurz

const PLAN = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'plan.json'), 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const items = (seq, kind, i) => seq.tracks[kind][i].items;
const at = (seq, kind, i, start) => items(seq, kind, i).find((t) => Math.abs(t.start - start) < 0.01);
const names = (ti) => ti.chain.comps.map((c) => c.name);

/** Antworten des Servers (premiere_tools.py), vereinfacht nachgebaut. */
function makeRpc(calls) {
  const art = PLAN.clips.find((c) => c.kind === 'artwork');
  const ton = PLAN.clips.find((c) => c.kind === 'episode' && c.ton_blende);
  return async (method, args) => {
    calls.push([method, args]);
    if (method === 'tools.config') return { effekte: [], uebergang: { match_name: 'AE.ADBE Cross Dissolve New', dauer: 0.4167 }, calibration: { colorMode: 'unit', keyframeBase: 'source' }, quellspuren: [2, 3, 0] };
    if (method === 'tools.effects') return { clips: args.clips.map(() => clone(art.effects)) };
    if (method === 'tools.audiofade') return { keyframes: args.ein === 0 && args.aus === 0 ? [] : clone((ton && ton.ton_blende.keyframes) || [[0, 0], [1, 1], [args.dur - 1, 1], [args.dur, 0]]) };
    if (method === 'tools.credit') {
      if (args.art === 'musik') throw new Error('Keine Credit-Vorlage für „Musik“');
      return { text: args.text || '© ' + String(args.name || args.path).replace(/.*[\\/]/, '').replace(/\..*/, '').toLowerCase(), art: args.art, track: args.art === 'amazon' ? 8 : 9,
        mogrt: 'C:/vorlagen/mogrt/Credit Artwork.mogrt', dur: args.dur, dx: 0, uebergang: 0.4167 };
    }
    if (method === 'tools.artwork') {
      return { nested: { name: 'Artwork ' + args.path.replace(/.*[\\/]/, '').replace(/\..*/, ''), dur: args.dur, image: args.path, mask: 'C:/vorlagen/masken/Maske.png', image_track: 2, mask_track: 4, matte_track: 5,
        image_scale: 50, mask_scale: 80, image_position: [0.5, 0.5], mask_position: [0.5, 0.5], preset: 'C:/cache/artwork.sqpreset' }, effects: clone(art.effects) };
    }
    if (method === 'tools.scene_at') return args.time < 20 ? { scene: 'sz_01', titel: 'Schmiede', status: 'neu', start: 0, end: 10.97 } : { scene: '' };
    throw new Error('unbekannt ' + method);
  };
}

async function setup() {
  const env = fake.create({ presets: { 'C:/cache/rohschnitt.sqpreset': { video: 14, audio: 16 }, 'C:/cache/artwork.sqpreset': { video: 5, audio: 1 } } });
  const rep = await runPlan(env.ppro, clone(PLAN));
  assert.deepEqual(rep.errors, [], JSON.stringify(rep.errors));
  const main = env.project.sequences.find((s) => s.name === PLAN.name);
  env.project.active = main;
  const calls = [];
  const tools = new Tools({ ppro: env.ppro, rpc: makeRpc(calls), log: () => {} });
  const select = (...tis) => { main.selected = tis; };
  return { ...env, main, tools, calls, select };
}

test('Auswahl: ohne Auswahl klare Meldung, Video/Ton getrennt', async () => {
  const { tools, main, select } = await setup();
  await assert.rejects(() => tools.run('transitions', {}), /Nichts ausgewählt|Keine Videoclips/);
  select(at(main, 'audio', 3, 0));
  await assert.rejects(() => tools.run('transitions', {}), /Keine Videoclips ausgewählt/);
  select(at(main, 'video', 2, 12.03));
  await assert.rejects(() => tools.run('audioFade', {}), /Keine Tonclips ausgewählt/);
  const sel = await tools.selection();
  assert.deepEqual(sel.items.map((i) => [i.kind, i.track, Math.round(i.start * 100) / 100]), [['video', 2, 12.03]]);
});

test('Effekte: Rezepte werden auf jeden gewählten Clip gesetzt (Zeiten kommen vom Server)', async () => {
  const { tools, main, select, calls } = await setup();
  const a = at(main, 'video', 2, 12.03), b = at(main, 'video', 3, 14.35);
  const before = names(a).length;
  select(a, b);
  const r = await tools.run('effects', { ids: ['drop_shadow', 'zoom_schnell'], label: 'Standard' });
  assert.match(r.text, /Standard auf 2 Clips gesetzt/);
  assert.equal(names(at(main, 'video', 2, 12.03)).length, before + PLAN.clips.find((c) => c.kind === 'artwork').effects.length);
  assert.ok(names(at(main, 'video', 3, 14.35)).length > before);
  const req = calls.find(([m]) => m === 'tools.effects')[1];
  assert.deepEqual(req.ids, ['drop_shadow', 'zoom_schnell']);
  assert.ok(Math.abs(req.clips[0].dur - (16.65 - 12.03)) < 0.01 && Math.abs(req.clips[1].dur - (21.27 - 14.35)) < 0.01);
  assert.ok(r.warnings.every((w) => /Parameter nicht gefunden/.test(w)), 'nur Parameter, die die Nachbildung nicht kennt: ' + r.warnings.join('|'));
});

test('Überblendung: Cross Dissolve an beiden Enden, höchstens die halbe Clipdauer; nur Anfang/nur Ende', async () => {
  const { tools, main, select } = await setup();
  const a = at(main, 'video', 0, 10.97);                             // Standbild: der Bau legt dort keine Überblendung an
  assert.equal(a.transitions.length, 0);
  select(a);
  const r = await tools.run('transitions', { ein: true, aus: true });
  assert.match(r.text, /2 Überblendungen gesetzt \(1 Clip\)/);
  const t = at(main, 'video', 0, 10.97).transitions;
  assert.equal(t.length, 2);
  assert.ok(t.every((x) => Math.abs(x.dur - 0.4167) < 1e-6 && x.single));
  assert.deepEqual(t.map((x) => x.start).sort(), [false, true]);
  const b = at(main, 'video', 0, 31.15);
  select(b);
  await tools.run('transitions', { ein: true, aus: false });
  assert.equal(at(main, 'video', 0, 31.15).transitions.length, 1);
});

test('Ton-Blende: Pegel-Keyframes an gewählten Tonclips, nur ein/aus möglich', async () => {
  const { tools, main, select, calls } = await setup();
  const a = at(main, 'audio', 3, 0);
  select(a);
  const r = await tools.run('audioFade', { ein: true, aus: true });
  assert.match(r.text, /Ton-Blende an 1 Tonclip/);
  const level = at(main, 'audio', 3, 0).chain.comps.find((c) => c.name === 'Lautstärke').params.find((p) => p.displayName === 'Pegel');
  assert.ok(level.kfs.length > 3);
  const lv1 = () => at(main, 'audio', 3, 5.97).chain.comps.find((c) => c.name === 'Lautstärke').params.find((p) => p.displayName === 'Pegel');
  const before = lv1().kfs.length;
  select(at(main, 'audio', 3, 5.97));
  const r0 = await tools.run('audioFade', { ein: false, aus: false });
  assert.equal(calls.filter(([m]) => m === 'tools.audiofade').at(-1)[1].ein, 0);
  assert.match(r0.text, /an 0 Tonclips/);
  assert.equal(lv1().kfs.length, before, 'ohne Blende nichts hinzugefügt');
});

test('Länge: feste Länge und bis zum Abspielkopf, andere Clips bleiben', async () => {
  const { tools, main, select, ppro } = await setup();
  const a = at(main, 'video', 3, 14.35), b = at(main, 'video', 2, 31.45);
  select(a, b);
  const r = await tools.run('length', { seconds: 3 });
  assert.match(r.text, /2 Clips auf 3 s gesetzt/);
  assert.ok(Math.abs(at(main, 'video', 3, 14.35).end - 17.35) < 1e-6 && Math.abs(at(main, 'video', 2, 31.45).end - 34.45) < 1e-6);
  assert.equal(items(main, 'video', 2).length, 2, 'keine Clips verschoben oder gelöscht');
  main.playhead = 19.0;
  select(at(main, 'video', 3, 14.35));
  const r2 = await tools.run('length', {});
  assert.match(r2.text, /bis zum Abspielkopf/);
  assert.ok(Math.abs(at(main, 'video', 3, 14.35).end - 19.0) < 1e-6);
  main.playhead = 10;                                              // Abspielkopf vor dem Clipanfang: nicht ändern, melden
  const r3 = await tools.run('length', {});
  assert.equal(r3.warnings.length, 1);
  assert.ok(ppro);
});

test('Credit aus Auswahl: Vorlage mit Name aus dem Bild, Länge wie der Clip, Name, Überblendung', async () => {
  const { tools, main, select, calls } = await setup();
  const still = at(main, 'video', 0, 10.97);
  select(still);
  const r = await tools.run('credit', { art: 'artwork' });
  assert.match(r.text, /1 Credit gesetzt: © 1/);
  const ti = at(main, 'video', 9, 10.97);
  assert.ok(ti && /^Credit /.test(ti.item.name));
  assert.ok(Math.abs(ti.end - 27.15) < 0.01, 'so lang wie das Bild');
  assert.equal(ti.name, '© 1');
  assert.equal(ti.transitions.length, 2);
  const req = calls.find(([m]) => m === 'tools.credit')[1];
  assert.equal(req.path, 'F:/OneDrive/Videoelemente/1.png');
  assert.equal(req.art, 'artwork');
});

test('Credit mit frei eingegebenem Text am Abspielkopf (ohne Auswahl)', async () => {
  const { tools, main, select } = await setup();
  select();
  main.playhead = 3.0;
  const r = await tools.run('credit', { art: 'amazon', text: '© amazon studios' });
  assert.match(r.text, /© amazon studios/);
  const ti = at(main, 'video', 8, 3.0);
  assert.ok(ti && Math.abs(ti.end - 8.0) < 0.01, 'Standardlänge 5 s');
  assert.equal(ti.name, '© amazon studios');
});

test('Credit: ein gewählter Credit-Clip ohne Datei nimmt das Bild darunter (nicht den Amazon-Credit auf V9)', async () => {
  const { tools, main, select, calls } = await setup();
  select(at(main, 'video', 0, 10.97));
  await tools.run('credit', { art: 'artwork' });
  const text = at(main, 'video', 9, 10.97);                        // Vorlagenclip: keine Datei; auf V9 liegt zur selben Zeit der Amazon-Credit
  assert.ok(at(main, 'video', 8, 0), 'Amazon-Credit liegt zur selben Zeit darunter');
  select(text);
  calls.length = 0;
  await tools.run('credit', { art: 'artwork' });
  const req = calls.find(([m]) => m === 'tools.credit')[1];
  assert.equal(req.path, 'F:/OneDrive/Videoelemente/1.png', JSON.stringify(req));
});

test('Credit: liegt unter dem gewählten Text-Clip kein Bild, gibt es einen Hinweis und keinen Credit', async () => {
  const { tools, main, select } = await setup();
  select();
  main.playhead = 3.0;
  await tools.run('credit', { art: 'amazon', text: '© amazon studios' });   // Text-Clip bei 3 s auf V9; darunter nur der Film
  select(at(main, 'video', 8, 3.0));
  const r = await tools.run('credit', { art: 'artwork' });
  assert.match(r.text, /0 Credits gesetzt/);
  assert.match(r.warnings[0], /liegt kein Bild/);
});

test('Credit: Fehler des Servers (keine Vorlage) landen in den Hinweisen, der Lauf bricht nicht ab', async () => {
  const { tools, main, select } = await setup();
  select(at(main, 'video', 0, 10.97));
  const r = await tools.run('credit', { art: 'musik' });
  assert.match(r.text, /0 Credits gesetzt/);
  assert.match(r.warnings[0], /Keine Credit-Vorlage/);
});

test('Artwork: Bild wird durch eine verschachtelte Sequenz mit Maske und Spurmaske ersetzt, Effekte folgen', async () => {
  const { tools, main, select, project } = await setup();
  const still = at(main, 'video', 0, 10.97);
  select(still);
  const r = await tools.run('artwork', {});
  assert.match(r.text, /1 Artwork gebaut/);
  assert.ok(r.warnings.every((w) => /Parameter nicht gesetzt|„© alan lee“ \(V10, 0:12.0\) lag im Bereich des neuen Credits und wurde ersetzt/.test(w)), r.warnings.join('|'));
  assert.equal(project.active && project.active.name, PLAN.name, 'Hauptsequenz wieder aktiv');
  const nested = project.sequences.find((s) => s.name === 'Artwork 1');
  assert.ok(nested, 'Sequenz angelegt');
  assert.equal(items(nested, 'video', 2).length, 1, 'Bild auf V3');
  assert.equal(items(nested, 'video', 4).length, 1, 'Maske auf V5');
  assert.ok(names(items(nested, 'video', 2)[0]).some((n) => /Spurmaske|Track Matte/i.test(n)), 'Spurmaske-Key auf dem Bild');
  const ti = at(main, 'video', 0, 10.97);
  assert.ok(ti && ti.item === nested.item, 'an der Stelle des Bildes liegt jetzt die Artwork-Sequenz');
  assert.ok(Math.abs(ti.end - 27.15) < 0.01);
  assert.ok(names(ti).length > 2, 'Standardeffekte gesetzt');
  assert.equal(ti.name, 'Artwork 1');
});

test('Artwork: zweite Sequenz mit gleichem Namen bekommt eine Nummer; Filme/Sequenzen werden übersprungen', async () => {
  const { tools, main, select, project } = await setup();
  select(at(main, 'video', 0, 10.97));
  await tools.run('artwork', {});
  select(at(main, 'video', 0, 31.15));                                // zweites Standbild
  await tools.run('artwork', {});
  assert.ok(project.sequences.some((s) => s.name === 'Artwork 2'));
  select(at(main, 'video', 0, 0));                                    // Episodenclip (verschachtelte Sequenz)
  await assert.rejects(() => tools.run('artwork', {}), /Kein Bild ausgewählt/);
});

test('Szene am Abspielkopf und Abspielkopf setzen', async () => {
  const { tools, main } = await setup();
  main.playhead = 5;
  const r = await tools.run('scene', {});
  assert.match(r.text, /Szene sz_01 „Schmiede“/);
  main.playhead = 25;
  assert.match((await tools.run('scene', {})).text, /liegt keine Szene/);
  const out = await tools.seek({ time: 12.5 });
  assert.equal(main.playhead, 12.5);
  assert.equal(out.time, 12.5);
});

test('Auswahl untersuchen: Komponenten und Wertetypen', async () => {
  const { tools, main, select } = await setup();
  select(at(main, 'video', 9, 12.03));
  const r = await tools.run('inspect', {});
  assert.match(r.text, /V10/);
  assert.ok(r.lines.some((l) => /Bewegung/.test(l)) && r.lines.some((l) => /Deckkraft/.test(l)));
});

test('Bridge: Werkzeug-Aufruf vom Panel aus, Server-Anfragen (rpc) und sequence.seek', async () => {
  const { ppro, main } = await setup();
  const sent = [];
  const ws = { send: (m) => sent.push(JSON.parse(m)), close() {} };
  const bridge = new Bridge({ ppro, WebSocketImpl: function () {}, fetchImpl: async () => ({ ok: false }), log: () => {}, onStatus: () => {} });
  bridge.ws = ws;
  const p = bridge.rpc('tools.config', {});
  const req = sent.at(-1);
  assert.equal(req.t, 'rpc'); assert.equal(req.method, 'tools.config');
  await bridge.onMessage(ws, JSON.stringify({ t: 'rpc_result', id: req.id, ok: true, data: { x: 1 } }));
  assert.deepEqual(await p, { x: 1 });
  const p2 = bridge.rpc('tools.effects', {});
  await bridge.onMessage(ws, JSON.stringify({ t: 'rpc_result', id: sent.at(-1).id, ok: false, error: 'Effekt unbekannt: x' }));
  await assert.rejects(p2, /Effekt unbekannt/);
  await bridge.onMessage(ws, JSON.stringify({ t: 'call', id: 7, op: 'sequence.seek', args: { time: 42 } }));
  assert.equal(main.playhead, 42);
  assert.deepEqual(sent.at(-1), { t: 'result', id: 7, ok: true, data: { time: 42 } });
  assert.ok(makeHandlers(ppro)['sequence.seek']);
});

test('Bridge: runTool meldet Fehler als Text, setzt „arbeitet“ zurück und lehnt Parallelaufträge ab', async () => {
  const { ppro, main } = await setup();
  const states = [];
  const ws = { send: () => {}, close() {} };
  const bridge = new Bridge({ ppro, WebSocketImpl: function () {}, fetchImpl: async () => ({ ok: false }), log: () => {}, onStatus: (s) => states.push(s.state) });
  bridge.ws = ws;
  bridge.rpc = makeRpc([]);
  main.selected = [];
  const r = await bridge.runTool('transitions', {});
  assert.equal(r.ok, false);
  assert.match(r.error, /Nichts ausgewählt|Keine Videoclips/);
  assert.equal(bridge.busy, false);
  assert.ok(states.includes('arbeitet'));
  bridge.busy = true;
  assert.match((await bridge.runTool('transitions', {})).error, /noch an einem anderen Auftrag/);
});

// ---------- Oberfläche ----------
class Node_ {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.textContent = ''; this.className = ''; this.onclick = null; }
  appendChild(c) { this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) { this.attrs[k] = v; if (k === 'value') this.value = v; }
  getAttribute(k) { return this.attrs[k]; }
  all(pred, out = []) { if (pred(this)) out.push(this); for (const c of this.children) c.all(pred, out); return out; }
}
const fakeDoc = { createElement: (t) => new Node_(t) };
const buttons = (host) => host.all((n) => n.tag === 'button');
const press = (host, text) => { const b = buttons(host).find((x) => x.textContent === text); assert.ok(b, 'Schaltfläche „' + text + '“ fehlt'); return b.onclick(); };

const CFG = { credits: [{ art: 'amazon', name: 'Amazon', vorlage: true }, { art: 'artwork', name: 'Künstler', vorlage: false }],
  effekte: [{ id: 'karte', name: 'Karte', ein: 'karte_in', aus: 'karte_out' }, { id: 'zoom_schnell', name: 'Zoom schnell', einzel: 'zoom_schnell' }, { id: 'right', name: 'Von rechts', ein: 'right_in' }] };

test('Oberfläche: Leiste aus der Konfiguration, jede Schaltfläche ruft das richtige Werkzeug', async () => {
  const host = new Node_('div');
  const calls = [];
  const parts = buildTools(fakeDoc, host, CFG, (name, args, label) => calls.push([name, args, label]));
  const labels = buttons(host).map((b) => b.textContent);
  for (const l of ['Artwork bauen', 'Credit setzen', 'Ein', 'Aus', 'Ein + Aus', 'Anwenden', 'Länge setzen', 'Bis Abspielkopf', 'Szene am Abspielkopf', 'Auswahl untersuchen']) assert.ok(labels.includes(l), l);
  assert.equal(labels.filter((l) => l === 'Ein + Aus').length, 1, 'nur Karte hat beides');
  press(host, 'Artwork bauen');
  press(host, 'Szene am Abspielkopf');
  assert.deepEqual(calls.map((c) => c[0]), ['artwork', 'scene']);
  const karte = buttons(host).filter((b) => b.textContent === 'Ein + Aus')[0];
  await karte.onclick();
  assert.deepEqual(calls.at(-1), ['effects', { ids: ['karte_in', 'karte_out'], label: 'Karte ein + aus' }, 'Karte ein + aus']);
  buttons(host).filter((b) => b.textContent === 'Anwenden')[0].onclick();
  assert.deepEqual(calls.at(-1)[1].ids, ['zoom_schnell']);
  buttons(host).filter((b) => b.textContent === 'Ein')[1].onclick();                    // „Von rechts“ hat nur „ein“ (vor der Ton-Blende)
  assert.deepEqual(calls.at(-1)[1].ids, ['right_in']);
  assert.ok(parts.artSel.children.some((o) => o.textContent === 'Künstler (keine Vorlage)'), 'fehlende Vorlage wird angezeigt');
});

test('Oberfläche: Credit-Text und Länge werden beim Klicken gelesen (Komma als Dezimalzeichen)', async () => {
  const host = new Node_('div');
  const calls = [];
  const parts = buildTools(fakeDoc, host, CFG, (name, args) => calls.push([name, args]));
  parts.artSel.value = 'artwork';
  parts.creditText.value = '© Ted Nasmith';
  press(host, 'Credit setzen');
  assert.deepEqual(calls.at(-1), ['credit', { art: 'artwork', text: '© Ted Nasmith' }]);
  parts.seconds.value = '6,5';
  press(host, 'Länge setzen');
  assert.deepEqual(calls.at(-1), ['length', { seconds: 6.5 }]);
  press(host, 'Bis Abspielkopf');
  assert.deepEqual(calls.at(-1), ['length', {}]);
});

test('Oberfläche: Neuaufbau ersetzt die alte Leiste; „nicht bereit“ bietet Neu laden an; Nutzertext nur als textContent', async () => {
  const host = new Node_('div');
  buildTools(fakeDoc, host, CFG, () => {});
  const n1 = host.children.length;
  buildTools(fakeDoc, host, CFG, () => {});
  assert.equal(host.children.length, n1, 'keine doppelten Abschnitte');
  let retried = 0;
  toolsNotReady(fakeDoc, host, '<b>Fehler</b>', () => { retried++; });
  assert.equal(host.children[0].textContent, 'Werkzeuge noch nicht bereit: <b>Fehler</b>');
  assert.ok(host.all((n) => n.tag === 'b').length === 0, 'kein HTML aus Text erzeugt');
  press(host, 'Neu laden');
  assert.equal(retried, 1);
});

test('Credit: Premiere fügt die Vorlage ein (schiebt die Spur) – spätere Clips der Credit-Spur kommen an ihren Platz zurück', async () => {
  const { tools, main, select } = await setup();
  const later = at(main, 'video', 9, 31.45);
  assert.ok(later, 'Credit „© alan lee“ bei 31.45 s auf V10');
  select();
  main.playhead = 20.0;
  const r = await tools.run('credit', { art: 'artwork', text: '© Ted Nasmith' });
  assert.match(r.text, /1 Credit gesetzt/);
  assert.deepEqual(r.warnings, []);
  assert.ok(at(main, 'video', 9, 20.0), 'neuer Credit');
  assert.ok(Math.abs(later.start - 31.45) < 0.004 && Math.abs(later.end - 32.95) < 0.004, 'späterer Credit unverändert: ' + later.start);
});

test('Credit: was auf der Credit-Spur im Bereich liegt, wird wie beim Überschreiben ersetzt bzw. gekürzt (keine Verschiebung)', async () => {
  const { tools, main, select } = await setup();
  const old = at(main, 'video', 9, 12.033);
  select();
  main.playhead = 13.0;
  const r = await tools.run('credit', { art: 'artwork', text: '© Ted Nasmith' });
  assert.match(r.text, /1 Credit gesetzt/);
  assert.match(r.warnings.join('|'), /lag im Bereich des neuen Credits und wurde ersetzt/);
  assert.ok(Math.abs(old.start - 12.033) < 0.004 && Math.abs(old.end - 13.0) < 0.004, 'linker Teil bleibt bis zum neuen Credit');
  const v10 = items(main, 'video', 9).filter((t) => t.end > 13.004 && t.start < 18 - 0.004);
  assert.equal(v10.length, 1, v10.map((t) => t.name + '@' + t.start).join(','));
  assert.ok(Math.abs(at(main, 'video', 9, 31.45).end - 32.95) < 0.004, 'späterer Credit am alten Platz');
});

test('Credit: ragt ein Clip der Credit-Spur über den neuen Credit hinaus, wird er vorne gekürzt und bleibt an seinem Platz', async () => {
  const { tools, main, select } = await setup();
  select();
  main.playhead = 3.0;
  await tools.run('credit', { art: 'amazon', text: '© amazon studios' });
  const v9 = items(main, 'video', 8).filter((t) => t.start < 12.04).sort((a, b) => a.start - b.start).map((t) => [+t.start.toFixed(3), +t.end.toFixed(3)]);
  assert.deepEqual(v9, [[0, 3], [3, 8], [8, 12.033]]);
});

test('Credit: lädt Premiere die Grafik nicht, setzt das Werkzeug das PNG des Servers (mit Hinweis)', async () => {
  const { tools, main, select, project } = await setup();
  project.mogrtLoad = () => null;
  const orig = tools.rpc;
  tools.rpc = async (m, a) => { const r = await orig(m, a); return m === 'tools.credit' ? { ...r, png: 'C:/cache/credits/credit_artwork_x.png' } : r; };
  select();
  main.playhead = 20.0;
  const r = await tools.run('credit', { art: 'artwork', text: '© Ted Nasmith' });
  assert.match(r.text, /1 Credit gesetzt/);
  assert.match(r.warnings[0], /nicht geladen.*als PNG gesetzt/);
  const ti = at(main, 'video', 9, 20.0);
  assert.match(ti.item.name, /\.png$/);
  assert.ok(Math.abs(ti.end - 25.0) < 0.01);
  assert.equal(ti.name, '© Ted Nasmith');
  assert.equal(items(main, 'video', 9).filter((t) => t.start > 19.9 && t.start < 25).length, 1, 'keine leere Ebene');
});
