// Gesicherter Selbsttest: legt ein Test-Fach, eine Test-Sequenz und einen Test-Clip an, prüft Effekte/Parameter/Keyframes/Farbe und
// räumt wieder auf. Ergebnis (Kalibrierung) steuert den Bau: Farbformat, Parameternamen, Zeitbezug der Keyframes.
// Läuft NUR auf ausdrückliche Anforderung und berührt keine vorhandenen Sequenzen.
'use strict';

const { tt, tx, errText, norm } = require('./core');
const media = require('./media');
const fx = require('./effects');

const BIN = 'Glorfindel-Selbsttest';

async function selftest(ppro, { png, preset }, emit = () => {}) {
  const res = { steps: [], findings: {}, ok: true };
  const step = async (name, fn) => {
    try { const detail = await fn(); res.steps.push({ name, ok: true, detail }); emit('progress', { text: 'Selbsttest: ' + name }); return detail; }
    catch (e) { res.steps.push({ name, ok: false, detail: errText(e) }); res.ok = false; return undefined; }
  };
  const project = await ppro.Project.getActiveProject();
  if (!project) throw new Error('In Premiere ist kein Projekt geöffnet.');
  let bin = null, seq = null, item = null, ti = null;

  await step('Test-Fach anlegen', async () => { bin = await media.ensureBin(ppro, project, BIN); return bin.name; });
  await step('Test-Bild importieren', async () => { const m = await media.importFiles(ppro, project, [png], bin); item = m.get(norm(png)); if (!item) throw new Error('nicht gefunden'); return 'ok'; });
  await step('Sequenz aus Vorgabe (Spuranzahl)', async () => {
    seq = await project.createSequenceWithPresetPath('GL-Selbsttest', preset);
    return { video: await seq.getVideoTrackCount(), audio: await seq.getAudioTrackCount() };
  });
  const editor = seq ? ppro.SequenceEditor.getEditor(seq) : null;
  await step('Clip setzen und Länge ändern', async () => {
    tx(project, 'Test', (add) => add(editor.createOverwriteItemAction(item, tt(ppro, 2), 12, -1)));
    const track = await seq.getVideoTrack(12);
    ti = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false)[0];
    tx(project, 'Test', (add) => add(ti.createSetEndAction(tt(ppro, 7))));
    return { start: (await ti.getStartTime()).seconds, end: (await ti.getEndTime()).seconds };
  });
  await step('Eingebaute Effekte (Namen)', async () => {
    const chain = await ti.getComponentChain();
    const comps = await fx.listComponents(chain);
    res.findings.components = comps.map((c) => c.name);
    const motion = await fx.builtin(ti, 'motion');
    res.findings.motionParams = motion ? fx.paramList(motion).map((p) => p.name) : null;
    return res.findings.components;
  });
  await step('Zuschneiden anwenden', async () => {
    const r = await fx.addCrop(ppro, project, ti, { links: 25, rechts: 25, oben: 0, unten: 0 }, {});
    const chain = await ti.getComponentChain();
    const comp = chain.getComponentAtIndex(chain.getComponentCount() - 1);
    res.findings.cropParams = fx.paramList(comp).map((p) => p.name);
    return r;
  });
  let rough = null;
  await step('Kanten aufrauen + Keyframes', async () => {
    const eff = { id: 'test', match_name: 'AE.ADBE Roughen Edges', params: [{ index: 2, name: 'Rahmen', value: 500, keyframes: [[0, 500], [0.5, 8]] }] };
    const r = await fx.addEffect(ppro, project, ti, eff, {});
    const chain = await ti.getComponentChain();
    rough = chain.getComponentAtIndex(chain.getComponentCount() - 1);
    res.findings.roughParams = fx.paramList(rough).map((p) => p.name);
    const p = fx.findParam(rough, ['Rahmen', 'Border'], 2);
    const times = p ? p.getKeyframeListAsTickTimes().map((t) => +t.seconds.toFixed(4)) : null;
    res.findings.keyframeTimes = times;
    res.findings.keyframeOrigin = times && times.length ? (Math.abs(times[0]) < 0.01 ? 'clipanfang' : 'andere:' + times[0]) : 'unbekannt';
    return { r, times };
  });
  await step('Farbformat prüfen', async () => {
    const p = fx.findParam(rough, ['Konturfarbe', 'Edge Color', 'Border Color'], 1);
    if (!p) throw new Error('Farbparameter nicht gefunden');
    const want = { argb16: [0xFF00, 0xD400, 0x5300, 0x2900] };
    const tried = {};
    for (const mode of ['unit']) {                         // dokumentiert: 0.0-1.0; die Rückgabe wird nur zur Kontrolle protokolliert
      try {
        tx(project, 'Farbe', (add) => add(p.createSetValueAction(p.createKeyframe(fx.toPproValue(ppro, want, { colorMode: mode })), true)));
        const v = await p.getStartValue();
        tried[mode] = JSON.stringify(v && v.value);
      } catch (e) { tried[mode] = 'Fehler: ' + errText(e); }
    }
    res.findings.colorTried = tried;
    res.findings.colorMode = 'unit';
    return tried;
  });
  await step('Deckkraft-Einblendung', async () => { await fx.setFade(ppro, project, ti, 5, 0.42, {}); return 'ok'; });

  // Aufräumen – immer
  await step('Aufräumen', async () => {
    if (seq) await project.deleteSequence(seq);
    const root = await project.getRootItem();
    const b = (await root.getItems()).find((i) => i.name === BIN);
    if (b) tx(project, 'Aufräumen', (add) => add(root.createRemoveItemAction(b)));
    return 'entfernt';
  });
  return res;
}

module.exports = { selftest, BIN };
