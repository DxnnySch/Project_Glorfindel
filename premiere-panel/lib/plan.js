// Bauplan ausführen: Medien importieren, Episoden-Sequenz und Hauptsequenz anlegen, Clips setzen, Effekte/Credits/Marker.
// Jeder Schritt ist abgesichert: Fehler landen im Bericht, der Bau läuft weiter.
'use strict';

const { tt, tx, norm, guarded, errText, walkItems, asClip, sleep } = require('./core');
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

async function findSequenceItem(ppro, root, name) {
  for (const it of await walkItems(ppro, root)) {
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
  const project = await ppro.Project.getActiveProject();
  if (!project) throw new Error('In Premiere ist kein Projekt geöffnet.');
  const say = (text, done, of) => emit('progress', { text, done, of });

  // ---- 1. Medien ----
  say('Fach und Medien vorbereiten …');
  const bin = await media.ensureBin(ppro, project, plan.bin);
  const paths = plan.media.map((m) => m.path);
  const byPath = await media.importFiles(ppro, project, paths, bin, emit);
  const item = {};
  for (const m of plan.media) {
    const it = byPath.get(norm(m.path));
    if (it) item[m.id] = it; else report.errors.push({ was: 'Import ' + m.path, fehler: 'nach dem Import nicht im Projekt gefunden' });
  }

  // ---- 2. Pause/Play aus der After-Effects-Komposition ----
  let compItem = null;
  if (plan.clips.some((c) => c.kind === 'anim') && plan.anim_source && plan.anim_source.aep) {
    await guarded(report, 'After-Effects-Komposition', async () => {
      const ok = await project.importAEComps(plan.anim_source.aep, [plan.anim_source.comp], bin);
      if (ok === false) throw new Error('Import der Komposition „' + plan.anim_source.comp + '“ abgelehnt');
      for (const it of await walkItems(ppro, bin)) {
        if (String(it.name).includes(plan.anim_source.comp)) { compItem = asClip(ppro, it); break; }
      }
      if (!compItem) throw new Error('Komposition nach dem Import nicht gefunden');
    });
  }

  // ---- 3. Episoden-Sequenz (verschachtelt: hier wird später das HQ-Medium getauscht) ----
  say('Episoden-Sequenz anlegen …');
  const epMedia = plan.media.find((m) => m.kind === 'episode');
  let epSeqItem = null;
  await guarded(report, 'Episoden-Sequenz', async () => {
    const epClip = item[epMedia.id];
    if (!epClip) throw new Error('Episoden-Medium fehlt');
    const epSeq = await project.createSequenceFromMedia(plan.episode_sequence, [epClip], bin);
    epSeqItem = asClip(ppro, await epSeq.getProjectItem());
  });
  if (!epSeqItem) throw new Error('Ohne Episoden-Sequenz kann kein Rohschnitt entstehen: ' + (report.errors.at(-1) || {}).fehler);

  // ---- 4. Hauptsequenz mit allen Spuren ----
  say('Hauptsequenz anlegen …');
  const main = await project.createSequenceWithPresetPath(plan.name, plan.preset.path);
  await guarded(report, 'Sequenz aktivieren', async () => { await project.setActiveSequence(main); await project.openSequence(main); });
  const editor = ppro.SequenceEditor.getEditor(main);
  const nV = await main.getVideoTrackCount();
  const nA = await main.getAudioTrackCount();
  if (nV < plan.preset.video_tracks || nA < plan.preset.audio_tracks) {
    report.warnings.push('Hauptsequenz hat nur ' + nV + ' Video-/' + nA + ' Audiospuren (geplant ' + plan.preset.video_tracks + '/' + plan.preset.audio_tracks + '). Die Sequenz-Vorgabe wurde nicht übernommen – Clips auf höheren Spuren fehlen.');
  }

  // ---- 5. Clips ----
  const total = plan.clips.length;
  let done = 0;
  const countOk = (k) => { report.placed[k] = (report.placed[k] || 0) + 1; };
  for (const c of plan.clips) {
    done++;
    if (done % 10 === 0 || done === total) say('Clips setzen: ' + done + ' von ' + total, done, total);
    await guarded(report, c.kind + ' ' + (c.name || '') + ' @' + c.start.toFixed(2), async () => {
      const dur = c.end - c.start;
      let src = null, audioIdx = -1, videoIdx = c.track;
      let inOut = null;
      if (c.kind === 'episode') { src = epSeqItem; audioIdx = c.audio; inOut = [c.src_in, c.src_out]; }
      else if (c.kind === 'voice') { src = item[c.media]; audioIdx = c.track; videoIdx = 0; inOut = [c.src_in, c.src_out]; }
      else if (c.kind === 'anim') { src = compItem; inOut = [c.comp_in, c.comp_in + dur]; }
      else { src = item[c.media]; }
      if (!src) throw new Error('Quelle fehlt');
      if (inOut) tx(project, 'In/Out', (add) => add(src.createSetInOutPointsAction(tt(ppro, inOut[0]), tt(ppro, inOut[1]))));
      tx(project, 'Clip setzen', (add) => add(editor.createOverwriteItemAction(src, tt(ppro, c.start), videoIdx, audioIdx)));
      const isAudio = c.kind === 'voice';
      const ti = await trackItemAt(ppro, main, isAudio ? 'audio' : 'video', c.track, c.start);
      if (!ti) throw new Error('gesetzter Clip nicht auf der Spur gefunden');
      const end = (await ti.getEndTime()).seconds;
      if (Math.abs(end - c.end) > TOL) tx(project, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, c.end))));
      if (c.name) await guarded(report, 'Name ' + c.name, async () => tx(project, 'Name', (add) => add(ti.createSetNameAction(c.name))));
      countOk(c.kind);
      if (isAudio) return;

      ctx.offset = kfBase === 'sequence' ? c.start : kfBase === 'source' ? (await ti.getInPoint()).seconds : 0;
      // Effekte je nach Art des Clips
      if (c.kind === 'artwork') {
        const r1 = await fx.addCrop(ppro, project, ti, c.crop, ctx);
        if (r1.fehlend.length) report.warnings.push('Zuschneiden: Parameter nicht gefunden: ' + r1.fehlend.join(', '));
        await fx.setMotion(ppro, project, ti, { position: c.position, scale: c.scale }, ctx);
      }
      for (const e of c.effects || []) {
        const r = await fx.addEffect(ppro, project, ti, e, ctx);
        report.effects[e.id] = (report.effects[e.id] || 0) + 1;
        if (r.fehlend.length) report.warnings.push(e.id + ': Parameter nicht gesetzt: ' + r.fehlend.join(', '));
      }
      if (c.kind === 'credit' && c.fade) await fx.setFade(ppro, project, ti, dur, c.fade, ctx);
    });
  }

  // ---- 6. Marker ----
  say('Marker setzen …');
  await guarded(report, 'Marker', async () => {
    const markers = await ppro.Markers.getMarkers(main);
    for (const m of plan.markers || []) {
      tx(project, 'Marker', (add) => add(markers.createAddMarkerAction(m.name, ppro.Marker.MARKER_TYPE_COMMENT, tt(ppro, m.time), tt(ppro, 0), m.comment || '')));
    }
    report.placed.marker = (plan.markers || []).length;
  });

  // ---- 7. Speichern ----
  if (plan.save !== false) await guarded(report, 'Speichern', async () => { await project.save(); });
  report.seconds = (Date.now() - report.started) / 1000;
  return report;
}

module.exports = { runPlan, trackItemAt, findSequenceItem };
