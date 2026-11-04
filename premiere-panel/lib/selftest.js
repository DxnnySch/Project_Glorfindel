// Gesicherter Selbsttest: legt ein Test-Fach, eine Test-Sequenz und einen Test-Clip an, prüft Effekte/Parameter/Keyframes/Farbe und
// räumt wieder auf. Ergebnis (Kalibrierung) steuert den Bau: Farbformat, Parameternamen, Zeitbezug der Keyframes.
// Läuft NUR auf ausdrückliche Anforderung und berührt keine vorhandenen Sequenzen.
// Objekte werden nie über Änderungen hinweg gehalten (siehe core.js): alles wird per Locator frisch geholt.
'use strict';

const { tt, tx, txp, errText, norm, getProj, invalidate, rawValue } = require('./core');
const media = require('./media');
const fx = require('./effects');
const trans = require('./transitions');
const mogrt = require('./mogrt');
const { trackItemAt, sequenceByGuid, placeClip } = require('./plan');

const BIN = 'Glorfindel-Selbsttest';
const FILTER_RE = /Crop|Zuschn|Roughen|Kanten|Shadow|Schatten|Geometry|Transform|Gaussian|Blur|Weichz|Opacity|Motion/i;

async function selftest(ppro, { png, preset, mogrts = {} }, emit = () => {}) {
  const res = { steps: [], findings: {}, ok: true };
  const step = async (name, fn) => {
    try { const detail = await fn(); res.steps.push({ name, ok: true, detail }); emit('progress', { text: 'Selbsttest: ' + name }); return detail; }
    catch (e) { res.steps.push({ name, ok: false, detail: errText(e) }); res.ok = false; return undefined; }
  };
  const getProject = () => getProj(ppro);
  await getProject();
  let seqGuid = null, haveItem = false, haveClip = false;
  const ctx = {};
  const locate = async () => {
    const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, await getProject(), seqGuid), 'video', 12, 2);
    if (!ti) throw new Error('Test-Clip nicht gefunden');
    return ti;
  };

  // Welche Effekte kennt diese Premiere-Version? (unabhängig von allen anderen Schritten)
  await step('Verfügbare Effekte', async () => {
    const m = await ppro.VideoFilterFactory.getMatchNames();
    const d = await ppro.VideoFilterFactory.getDisplayNames().catch(() => []);
    res.findings.filters = m.map((x, i) => ({ match: x, display: d[i] })).filter((f) => FILTER_RE.test(f.match) || FILTER_RE.test(String(f.display)));
    return res.findings.filters.length + ' Treffer';
  });

  await step('Test-Fach anlegen', async () => { await media.ensureBin(ppro, await getProject(), BIN); return BIN; });
  await step('Test-Bild importieren', async () => {
    const m = await media.importFiles(ppro, await getProject(), [png], BIN);
    haveItem = m.has(norm(png));
    if (!haveItem) throw new Error('nicht gefunden');
    return 'ok';
  });
  await step('Sequenz aus Vorgabe (Spuranzahl)', async () => {
    const seq = await (await getProject()).createSequenceWithPresetPath('GL-Selbsttest', preset);
    seqGuid = String(seq.guid);
    const counts = { video: await seq.getVideoTrackCount(), audio: await seq.getAudioTrackCount() };
    invalidate();
    return counts;
  });
  await step('Clip setzen und Länge ändern', async () => {
    if (!haveItem) throw new Error('kein Test-Bild');
    await placeClip(ppro, seqGuid, async () => {
      const bin = await media.getBin(ppro, await getProject(), BIN);
      return media.rawByPath(ppro, bin, png);
    }, 2, 12, -1);
    haveClip = true;
    const ti = await locate();
    await txp(ppro, 'Test', (add) => add(ti.createSetEndAction(tt(ppro, 7))));
    const t2 = await locate();
    return { start: (await t2.getStartTime()).seconds, end: (await t2.getEndTime()).seconds };
  });
  await step('Eingebaute Effekte (Namen)', async () => {
    const chain = await (await locate()).getComponentChain();
    const comps = await fx.listComponents(chain);
    res.findings.components = comps.map((c) => c.name);
    const idx = await fx.builtinIndex(locate, 'motion');
    res.findings.motionParams = idx >= 0 ? fx.paramList(await fx.componentAt(locate, idx)).map((p) => p.name) : null;
    return res.findings.components;
  });
  await step('Zuschneiden anwenden', async () => {
    const r = await fx.addCrop(ppro, await getProject(), locate, { links: 25, rechts: 25, oben: 0, unten: 0 }, ctx);
    res.findings.cropMatch = r.match;
    const chain = await (await locate()).getComponentChain();
    res.findings.cropParams = fx.paramList(chain.getComponentAtIndex(chain.getComponentCount() - 1)).map((p) => p.name);
    if (r.fehlend.length) throw new Error('Parameter nicht gesetzt: ' + r.fehlend.join(', '));
    return r;
  });
  let roughIdx = -1;
  await step('Kanten aufrauen + Keyframes', async () => {
    roughIdx = (await (await locate()).getComponentChain()).getComponentCount();
    const eff = { id: 'test', match_name: 'AE.ADBE Roughen Edges', display: 'Kanten aufrauen', params: [{ index: 2, names: ['Rahmen', 'Border'], value: 500, keyframes: [[0, 500], [0.5, 8]] }] };
    const r = await fx.addEffect(ppro, await getProject(), locate, eff, ctx);
    res.findings.roughMatch = r.match;
    const comp = await fx.componentAt(locate, roughIdx);
    res.findings.roughParams = fx.paramList(comp).map((p) => p.name);
    const p = fx.findParam(comp, ['Rahmen', 'Border'], 2);
    const times = p ? p.getKeyframeListAsTickTimes().map((t) => +t.seconds.toFixed(4)) : null;
    res.findings.keyframeTimes = times;
    res.findings.keyframeOrigin = times && times.length ? (Math.abs(times[0]) < 0.01 ? 'clipanfang' : 'andere:' + times[0]) : 'unbekannt';
    if (r.fehlend.length) throw new Error('Parameter nicht gesetzt: ' + r.fehlend.join(', '));
    return { r, times };
  });
  await step('Farbformat prüfen', async () => {
    const want = { argb16: [0xFF00, 0xD400, 0x5300, 0x2900] };
    const tried = {};
    const p = fx.findParam(await fx.componentAt(locate, roughIdx), ['Konturfarbe', 'Edge Color', 'Border Color'], 1);
    if (!p) throw new Error('Farbparameter nicht gefunden');
    try {                                                    // dokumentiert: 0.0-1.0; die Rückgabe wird nur zur Kontrolle protokolliert
      await txp(ppro, 'Farbe', (add) => add(p.createSetValueAction(p.createKeyframe(fx.toPproValue(ppro, want, { colorMode: 'unit' })), true)));
      const p2 = fx.findParam(await fx.componentAt(locate, roughIdx), ['Konturfarbe', 'Edge Color', 'Border Color'], 1);
      const v = await p2.getStartValue();
      tried.unit = JSON.stringify(v && v.value);
    } catch (e) { tried.unit = 'Fehler: ' + errText(e); }
    res.findings.colorTried = tried;
    res.findings.colorMode = 'unit';
    return tried;
  });
  await step('Deckkraft-Einblendung', async () => {
    await fx.setFade(ppro, await getProject(), locate, 5, 0.42, ctx);
    const idx = await fx.builtinIndex(locate, 'opacity');
    const p = fx.findParam(await fx.componentAt(locate, idx), fx.NAMES.opacity, 0);
    const ts = p.getKeyframeListAsTickTimes();
    const vals = [];
    for (const t of ts) vals.push({ t: +t.seconds.toFixed(3), v: await p.getValueAtTime(t) });
    for (const sec of [0, 0.2, 2.5]) vals.push({ t: sec, v: await p.getValueAtTime(ppro.TickTime.createWithSeconds(sec)), interpoliert: true });
    res.findings.opacityValues = vals;
    return vals;
  });

  // Videoübergang (Cross Dissolve) und Angebot an Übergängen: bestätigt, ob die Namen aus dem Ursprungsschnitt in dieser Version gelten
  await step('Übergänge (Cross Dissolve)', async () => {
    const names = await ppro.TransitionFactory.getVideoTransitionMatchNames();
    res.findings.transitions = names.filter((n) => /dissolve|fade|power|gain|blende/i.test(n));
    res.findings.audioTransitions = names.some((n) => /constant power|konstante leistung/i.test(n));
    const match = await trans.resolveTransition(ppro, { match_name: 'AE.ADBE Cross Dissolve New' }, ctx);
    const n = await trans.addVideoTransitions(ppro, locate, { ein: 0.42, aus: 0.42 }, { match_name: match }, ctx);
    res.findings.crossDissolve = match;
    return { match, gesetzt: n, audio_uebergaenge_in_api: res.findings.audioTransitions };
  });

  // Editierbarer Text: Adobes „Basic Title“ einsetzen, Text schreiben und zurücklesen. Bestätigt das Textformat des Parameters.
  await step('Text-Vorlage (MOGRT)', async () => {
    const dir = await ppro.SequenceEditor.getInstalledMogrtPath();
    const path = String(dir).replace(/[\\/]+$/, '') + '/Basic Title.mogrt';
    res.findings.mogrtPath = path;
    const seq = await sequenceByGuid(ppro, await getProject(), seqGuid);
    await mogrt.insertTemplate(ppro, await getProject(), seq, { path, start: 10, track: 11 });
    const loc = async () => {
      const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, await getProject(), seqGuid), 'video', 11, 10);
      if (!ti) throw new Error('Vorlagen-Clip nicht gefunden');
      return ti;
    };
    const name = await mogrt.setText(ppro, await getProject(), loc, 'Glorfindel Test ä');
    const chain = await (await loc()).getComponentChain();
    let back = null;
    for (const c of await fx.listComponents(chain)) for (const p of fx.paramList(c.comp)) {
      if (p.name !== name) continue;
      back = (await mogrt.readText(p.param)) ?? back;
    }
    res.findings.mogrtTextParam = name;
    res.findings.mogrtTextBack = back && back.slice(0, 160);
    res.findings.mogrtTextIsJson = /^\s*\{/.test(back || '');
    if (!back) res.findings.mogrtTextReadable = false;       // Setzen ging durch, Zurücklesen nicht möglich: kein Fehler
    else if (!back.includes('Glorfindel Test')) throw new Error('Text nicht zurückgelesen: ' + String(back).slice(0, 80));
    return { parameter: name, json: res.findings.mogrtTextIsJson };
  });

  // Die eigenen Credit-Vorlagen (vorlagen/mogrt): einsetzen, Text schreiben, zurücklesen – genau wie beim Bau
  let slot = 0;
  for (const [art, path] of Object.entries(mogrts)) {
    const track = 9 - slot++;
    await step('Eigene Vorlage: ' + art, async () => {
      const seq = await sequenceByGuid(ppro, await getProject(), seqGuid);
      await mogrt.insertTemplate(ppro, await getProject(), seq, { path, start: 20, track });
      const loc = async () => {
        const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, await getProject(), seqGuid), 'video', track, 20);
        if (!ti) throw new Error('Vorlagen-Clip nicht gefunden');
        return ti;
      };
      const name = await mogrt.setText(ppro, await getProject(), loc, '© Glorfindel Test ä');
      let back = null;
      for (const c of await fx.listComponents(await (await loc()).getComponentChain())) for (const p of fx.paramList(c.comp)) {
        if (p.name !== name) continue;
        back = (await mogrt.readText(p.param)) ?? back;
      }
      (res.findings.eigeneVorlagen = res.findings.eigeneVorlagen || {})[art] = { parameter: name, zurueck: back && back.slice(0, 120) };
      if (back && !back.includes('Glorfindel Test')) throw new Error('Text nicht übernommen: ' + back.slice(0, 80));
      return { parameter: name, lesbar: !!back };
    });
  }

  // Aufräumen – immer
  await step('Aufräumen', async () => {
    const project = await getProject();
    if (seqGuid) {
      const seq = (await project.getSequences()).find((s) => String(s.guid) === seqGuid);
      if (seq) { await project.deleteSequence(seq); invalidate(); }
    }
    const p2 = await getProject();
    const root = await p2.getRootItem();
    const b = (await root.getItems()).find((i) => i.name === BIN);
    if (b) await txp(ppro, 'Aufräumen', (add) => add(root.createRemoveItemAction(b)));
    return 'entfernt';
  });
  return res;
}

module.exports = { selftest, BIN };
