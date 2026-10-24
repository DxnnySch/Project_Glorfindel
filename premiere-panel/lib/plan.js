// Bauplan ausführen: Medien importieren, Episoden-Sequenz und Hauptsequenz anlegen, Clips setzen, Effekte/Credits/Marker.
// Jeder Schritt ist abgesichert: Fehler landen im Bericht, der Bau läuft weiter.
// Objekte werden nie über Änderungen hinweg gehalten (siehe core.js): Sequenzen per GUID, Clips per Spur+Startzeit, Medien per Pfad frisch geholt.
'use strict';

const { tt, tx, txp, norm, guarded, errText, walkItems, asClip, retryStale } = require('./core');
const media = require('./media');
const fx = require('./effects');

const TOL = 0.004; // Sekunden: so genau muss ein gesetzter Clip auf dem geplanten Zeitpunkt liegen

async function trackItemAt(ppro, seq, kind, index, startSec) {
  const track = kind === 'video' ? await seq.getVideoTrack(index) : await seq.getAudioTrack(index);
  const items = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false);
  let best = null;
  for (const it of items) {
    const s = (await it.getStartTime()).seconds;
    if (Math.abs(s - startSec) < TOL) best = it;
  }
  return best;
}

async function sequenceByGuid(ppro, project, guid) {
  const seq = (await project.getSequences()).find((s) => String(s.guid) === guid);
  if (!seq) throw new Error('Sequenz nicht mehr im Projekt');
  return seq;
}

async function findSequenceItem(ppro, folder, name) {
  for (const it of await walkItems(ppro, folder)) {
    if (it.name !== name) continue;
    const clip = asClip(ppro, it);
    if (clip && (await clip.isSequence())) return clip;
  }
  return null;
}

/** Hauptfunktion. `emit(name, data)` meldet Fortschritt. Rückgabe: Bericht. */
async function runPlan(ppro, plan, emit = () => {}) {
  const report = { errors: [], warnings: [...(plan.warnings || [])], placed: {}, effects: {}, sequence: plan.name, started: Date.now() };
  const ctx = { colorMode: (plan.calibration && plan.calibration.colorMode) || 'unit', offset: 0 };
  const kfBase = (plan.calibration && plan.calibration.keyframeBase) || 'clip';   // 'clip' | 'sequence' | 'source'
  const say = (text, done, of) => emit('progress', { text, done, of });
  const getProject = async () => {
    const p = await ppro.Project.getActiveProject();
    if (!p) throw new Error('In Premiere ist kein Projekt geöffnet.');
    return p;
  };
  const project0 = await getProject();

  // ---- 1. Medien ----
  say('Fach und Medien vorbereiten …');
  await media.importFiles(ppro, project0, plan.media.map((m) => m.path), plan.bin, emit);

  // Plan-Medium -> Name des Projektelements. Elemente selbst werden vor jeder Verwendung frisch per Namen geholt
  // (alte Objekte sind nach jeder Änderung ungültig; ein Aufruf `getItems()` genügt, kein kompletter Neuaufbau).
  const names = {};
  const refresh = async () => {
    const project = await getProject();
    const bin = await media.getBin(ppro, project, plan.bin);
    const byPath = await media.mediaByPath(ppro, bin);
    for (const m of plan.media) { const it = byPath.get(norm(m.path)); if (it) names[m.id] = it.name; else delete names[m.id]; }
    const epSeq = await findSequenceItem(ppro, bin, plan.episode_sequence);
    names.epSeq = epSeq ? epSeq.name : undefined;
    names.comp = undefined;
    if (plan.anim_source && plan.anim_source.comp) {
      for (const it of await walkItems(ppro, bin)) {
        if (String(it.name).includes(plan.anim_source.comp) && !(await asClip(ppro, it).isSequence())) { names.comp = it.name; break; }
      }
    }
  };
  const fresh = async (key) => {
    if (!names[key]) return null;
    const project = await getProject();
    const bin = await media.getBin(ppro, project, plan.bin);
    const it = (await bin.getItems()).find((i) => i.name === names[key]);
    return it ? asClip(ppro, it) : null;
  };

  // ---- 2. Pause/Play aus der After-Effects-Komposition ----
  if (plan.clips.some((c) => c.kind === 'anim') && plan.anim_source && plan.anim_source.aep) {
    await guarded(report, 'After-Effects-Komposition', async () => {
      const project = await getProject();
      const bin = await media.getBin(ppro, project, plan.bin);
      const ok = await project.importAEComps(plan.anim_source.aep, [plan.anim_source.comp], bin);
      if (ok === false) throw new Error('Import der Komposition „' + plan.anim_source.comp + '“ abgelehnt');
    });
  }

  // ---- 3. Episoden-Sequenz (verschachtelt: hier wird später das HQ-Medium getauscht) ----
  say('Episoden-Sequenz anlegen …');
  const epMedia = plan.media.find((m) => m.kind === 'episode');
  await refresh();
  await guarded(report, 'Episoden-Sequenz', async () => {
    const epClip = await fresh(epMedia.id);
    if (!epClip) throw new Error('Episoden-Medium fehlt');
    const project = await getProject();
    const bin = await media.getBin(ppro, project, plan.bin);
    await project.createSequenceFromMedia(plan.episode_sequence, [epClip], bin);
  });
  await refresh();
  if (!names.epSeq) throw new Error('Ohne Episoden-Sequenz kann kein Rohschnitt entstehen: ' + ((report.errors.at(-1) || {}).fehler || 'nicht gefunden'));

  // ---- 4. Hauptsequenz mit allen Spuren ----
  say('Hauptsequenz anlegen …');
  let mainGuid, nV, nA;
  {
    const project = await getProject();
    const main = await project.createSequenceWithPresetPath(plan.name, plan.preset.path);
    mainGuid = String(main.guid);
    nV = await main.getVideoTrackCount();
    nA = await main.getAudioTrackCount();
  }
  await guarded(report, 'Sequenz aktivieren', async () => {
    const project = await getProject();
    const main = await sequenceByGuid(ppro, project, mainGuid);
    await project.setActiveSequence(main);
    await (await getProject()).openSequence(await sequenceByGuid(ppro, await getProject(), mainGuid));
  });
  if (nV < plan.preset.video_tracks || nA < plan.preset.audio_tracks) {
    report.warnings.push('Hauptsequenz hat nur ' + nV + ' Video-/' + nA + ' Audiospuren (geplant ' + plan.preset.video_tracks + '/' + plan.preset.audio_tracks + '). Die Sequenz-Vorgabe wurde nicht übernommen – Clips auf höheren Spuren fehlen.');
  }
  await refresh();

  // ---- 5. Clips ----
  const total = plan.clips.length;
  let done = 0;
  const countOk = (k) => { report.placed[k] = (report.placed[k] || 0) + 1; };
  for (const c of plan.clips) {
    done++;
    if (done % 10 === 0 || done === total) say('Clips setzen: ' + done + ' von ' + total, done, total);
    await guarded(report, c.kind + ' ' + (c.name || '') + ' @' + c.start.toFixed(2), async () => {
      const dur = c.end - c.start;
      const isAudio = c.kind === 'voice';
      const kind = isAudio ? 'audio' : 'video';
      // Clip immer frisch holen: nach jeder Änderung sind alte Objekte ungültig
      const locate = async () => {
        const project = await getProject();
        const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, project, mainGuid), kind, c.track, c.start);
        if (!ti) throw new Error('gesetzter Clip nicht auf der Spur gefunden');
        return ti;
      };
      await retryStale(async () => {
        const project = await getProject();
        let key, audioIdx = -1, videoIdx = c.track, inOut = null;
        if (c.kind === 'episode') { key = 'epSeq'; audioIdx = c.audio; inOut = [c.src_in, c.src_out]; }
        else if (c.kind === 'voice') { key = c.media; audioIdx = c.track; videoIdx = 0; inOut = [c.src_in, c.src_out]; }
        else if (c.kind === 'anim') { key = 'comp'; inOut = [c.comp_in, c.comp_in + dur]; }
        else { key = c.media; }
        const src = await fresh(key);
        if (!src) throw new Error('Quelle fehlt');
        if (inOut) await txp(ppro, 'In/Out', (add) => add(src.createSetInOutPointsAction(tt(ppro, inOut[0]), tt(ppro, inOut[1]))));
        const p2 = await getProject();
        const main = await sequenceByGuid(ppro, p2, mainGuid);
        const editor = ppro.SequenceEditor.getEditor(main);
        const src2 = await fresh(key);                       // nach der Änderung (In/Out) ist `src` ungültig
        await txp(ppro, 'Clip setzen', (add) => add(editor.createOverwriteItemAction(src2, tt(ppro, c.start), videoIdx, audioIdx)));
      }, refresh);
      const ti = await locate();
      if (Math.abs((await ti.getEndTime()).seconds - c.end) > TOL) await txp(ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, c.end))));
      if (c.name) await guarded(report, 'Name ' + c.name, async () => { const t2 = await locate(); await txp(ppro, 'Name', (add) => add(t2.createSetNameAction(c.name))); });
      countOk(c.kind);
      if (isAudio) return;

      // Effekte je nach Art des Clips
      if (c.kind === 'artwork') {
        const r1 = await fx.addCrop(ppro, await getProject(), locate, c.crop, ctx);
        if (r1.fehlend.length) report.warnings.push('Zuschneiden: nicht gesetzt: ' + r1.fehlend.join(', '));
        await fx.setMotion(ppro, await getProject(), locate, { position: c.position, scale: c.scale }, ctx);
      }
      for (const e of c.effects || []) {
        ctx.offset = kfBase === 'sequence' ? c.start : kfBase === 'source' ? (await (await locate()).getInPoint()).seconds : 0;
        const r = await fx.addEffect(ppro, await getProject(), locate, e, ctx);
        report.effects[e.id] = (report.effects[e.id] || 0) + 1;
        if (r.fehlend.length) report.warnings.push(e.id + ': Parameter nicht gesetzt: ' + r.fehlend.join(', '));
      }
      ctx.offset = 0;
      if (c.kind === 'credit' && c.fade) await fx.setFade(ppro, await getProject(), locate, dur, c.fade, ctx);
    });
  }

  // ---- 6. Marker ----
  say('Marker setzen …');
  await guarded(report, 'Marker', async () => {
    for (const m of plan.markers || []) {
      await retryStale(async () => {
        const project = await getProject();
        const main = await sequenceByGuid(ppro, project, mainGuid);
        const markers = await ppro.Markers.getMarkers(main);
        await txp(ppro, 'Marker', (add) => add(markers.createAddMarkerAction(m.name, ppro.Marker.MARKER_TYPE_COMMENT, tt(ppro, m.time), tt(ppro, 0), m.comment || '')));
      });
    }
    report.placed.marker = (plan.markers || []).length;
  });

  // ---- 7. Speichern ----
  if (plan.save !== false) await guarded(report, 'Speichern', async () => { await (await getProject()).save(); });
  report.seconds = (Date.now() - report.started) / 1000;
  return report;

}

module.exports = { runPlan, trackItemAt, findSequenceItem, sequenceByGuid };
