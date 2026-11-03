// Bauplan ausführen: Medien importieren, Episoden-Sequenz und Hauptsequenz anlegen, Clips setzen, Effekte/Credits/Marker.
// Jeder Schritt ist abgesichert: Fehler landen im Bericht, der Bau läuft weiter.
// Objekte werden nie über Änderungen hinweg gehalten (siehe core.js): Sequenzen per GUID, Clips per Spur+Startzeit, Medien per Pfad frisch geholt.
'use strict';

const { tt, tx, txp, at, norm, guarded, errText, walkItems, asClip, retryStale, getProj, invalidate } = require('./core');
const media = require('./media');
const fx = require('./effects');
const trans = require('./transitions');

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

/** Clip in die Sequenz setzen. `getItem` liefert das Quellelement frisch. Premiere lehnt je nach Medium einen Audio-Index -1 ab („Invalid parameter“): dann mit 0 versuchen. */
async function placeClip(ppro, seqGuid, getItem, startSec, videoIdx, audioIdx) {
  const tries = audioIdx < 0 ? [audioIdx, 0] : [audioIdx];
  const errors = [];
  for (const a of tries) {
    try {
      const item = await getItem();
      if (!item) throw new Error('Quelle fehlt');
      const project = await getProj(ppro);
      const editor = ppro.SequenceEditor.getEditor(await sequenceByGuid(ppro, project, seqGuid));
      await txp(ppro, 'Clip setzen', (add) => add(editor.createOverwriteItemAction(item, tt(ppro, startSec), videoIdx, a)));
      return;
    } catch (e) {
      errors.push('Spur V' + (videoIdx + 1) + ', Audio-Index ' + a + ': ' + errText(e));
      invalidate();
    }
  }
  throw new Error(errors.join(' | '));
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
  const getProject = () => getProj(ppro);
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
  // `raw`: unverändertes ProjectItem (so verlangt es SequenceEditor/createSequenceFromMedia; ein ClipProjectItem wird mit „Invalid parameter“ abgelehnt)
  const fresh = async (key, raw = false) => {
    if (!names[key]) return null;
    const project = await getProject();
    const bin = await media.getBin(ppro, project, plan.bin);
    const it = (await bin.getItems()).find((i) => i.name === names[key]);
    return it ? (raw ? it : asClip(ppro, it)) : null;
  };

  // ---- 2. Pause/Play aus der After-Effects-Komposition ----
  if (plan.clips.some((c) => c.kind === 'anim' && !c.media) && plan.anim_source && plan.anim_source.aep) {
    await guarded(report, 'After-Effects-Komposition', async () => {
      const project = await getProject();
      const bin = await media.getBin(ppro, project, plan.bin);
      const ok = await project.importAEComps(plan.anim_source.aep, [plan.anim_source.comp], bin);
      invalidate();
      if (ok === false) throw new Error('Import der Komposition „' + plan.anim_source.comp + '“ abgelehnt');
    });
  }

  // ---- 2b. Artwork-Sequenzen: Bild (V3) + Maske (V5) + Spurmaske-Key, wie im Ursprungsschnitt ----
  const nestedItem = async (name) => {
    const project = await getProject();
    const root = await project.getRootItem();
    for (const it of await walkItems(ppro, root)) {
      if (it.name !== name) continue;
      const c = asClip(ppro, it);
      if (c && (await c.isSequence())) return it;            // rohes ProjectItem (nur das nimmt der SequenceEditor an)
    }
    return null;
  };

  // Einstellungsebene (für Gauß In/Out): die API kann keine anlegen, aber eine vorhandene im Projekt platzieren.
  const adjustmentItem = async () => {
    const want = (plan.adjustment_names || []).map((x) => x.toLowerCase());
    const root = await (await getProject()).getRootItem();
    for (const it of await walkItems(ppro, root)) {
      if (!want.includes(String(it.name).toLowerCase())) continue;
      const c = asClip(ppro, it);
      if (c && !(await c.isSequence())) return it;
    }
    return null;
  };
  let useAdjust = false;
  if (plan.clips.some((c) => c.kind === 'adjust')) {
    useAdjust = !!(await guarded(report, 'Einstellungsebene suchen', adjustmentItem));
    if (!useAdjust) report.warnings.push('Keine Einstellungsebene im Projekt gefunden (Datei → Neu → Einstellungsebene, Name „Einstellungsebene“): Gauß In/Out liegt vorerst direkt auf den Standbildern.');
  }

  // ---- 3. Episoden-Sequenz (verschachtelt: hier wird später das HQ-Medium getauscht) ----
  say('Episoden-Sequenz anlegen …');
  const epMedia = plan.media.find((m) => m.kind === 'episode');
  await refresh();
  await guarded(report, 'Episoden-Sequenz', async () => {
    const epClip = await fresh(epMedia.id, true);
    if (!epClip) throw new Error('Episoden-Medium fehlt');
    const project = await getProject();
    const bin = await media.getBin(ppro, project, plan.bin);
    try { await project.createSequenceFromMedia(plan.episode_sequence, [epClip], bin); } finally { invalidate(); }
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
    invalidate();
  }
  await guarded(report, 'Sequenz aktivieren', async () => {
    const project = await getProject();
    const main = await sequenceByGuid(ppro, project, mainGuid);
    await project.setActiveSequence(main);
    invalidate();
    const p2 = await getProject();
    await p2.openSequence(await sequenceByGuid(ppro, p2, mainGuid));
    invalidate();
  });
  if (nV < plan.preset.video_tracks || nA < plan.preset.audio_tracks) {
    report.warnings.push('Hauptsequenz hat nur ' + nV + ' Video-/' + nA + ' Audiospuren (geplant ' + plan.preset.video_tracks + '/' + plan.preset.audio_tracks + '). Die Sequenz-Vorgabe wurde nicht übernommen – Clips auf höheren Spuren fehlen.');
  }
  await refresh();

  // ---- 4b. Artwork-Sequenzen bauen ----
  const nestedName = {};
  const nestedFailed = new Set();
  const buildNested = async (n) => {
    const guid = await retryStale(async () => {
      const seq = await (await getProject()).createSequenceWithPresetPath(n.name, plan.nested_preset);
      const g = String(seq.guid);
      invalidate();
      return g;
    });
    const locator = (track) => async () => {
      const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, await getProject(), guid), 'video', track, 0);
      if (!ti) throw new Error('Clip auf V' + (track + 1) + ' nicht gefunden');
      return ti;
    };
    const parts = [['Bild', n.image, n.image_track, n.image_scale, n.image_position || n.position], ['Maske', n.mask, n.mask_track, n.mask_scale, n.mask_position || n.position]];
    for (const [label, media_, track] of parts) {
      await at('Artwork ' + label + ' setzen', async () => {
        await placeClip(ppro, guid, () => fresh(media_, true), 0, track, -1);
        const ti = await locator(track)();
        if (Math.abs((await ti.getEndTime()).seconds - n.dur) > TOL) await txp(ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, n.dur))));
      });
    }
    for (const [label, , track, scale, position] of parts) {
      await at('Artwork ' + label + ': Position/Größe', async () => { await fx.setMotion(ppro, await getProject(), locator(track), { position, scale }, ctx); });
    }
    const matte = { id: 'spurmaske', match_name: 'AE.ADBE Legacy Key Track Matte', display: 'Spurmaske-Key',
      params: [{ index: 0, names: ['Maske:', 'Matte:', 'Mask:'], value: n.matte_track }, { index: 1, names: ['Compositing mit', 'Composite Using'], value: 0 }] };
    const r = await at('Spurmaske-Key', async () => fx.addEffect(ppro, await getProject(), locator(n.image_track), matte, ctx));
    if (r.fehlend.length) report.warnings.push('Spurmaske-Key (' + n.name + '): ' + r.fehlend.join(', '));
    nestedName[n.id] = n.name;
  };
  if ((plan.nested || []).length) {
    say('Artwork-Sequenzen anlegen …');
    for (const n of plan.nested) {
      await guarded(report, 'Artwork-Sequenz ' + n.name, async () => {
        try { await buildNested(n); } catch (e) { nestedFailed.add(n.id); throw e; }
      });
    }
    await guarded(report, 'Hauptsequenz wieder aktivieren', async () => {
      const project = await getProject();
      await project.setActiveSequence(await sequenceByGuid(ppro, project, mainGuid));
      invalidate();
    });
  }

  // ---- 5. Clips ----
  const total = plan.clips.length;
  let done = 0;
  let transWarned = false;
  const countOk = (k) => { report.placed[k] = (report.placed[k] || 0) + 1; };
  for (const c of plan.clips) {
    done++;
    if (done % 10 === 0 || done === total) say('Clips setzen: ' + done + ' von ' + total, done, total);
    if (c.kind === 'adjust' && !useAdjust) continue;
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
        else if (c.kind === 'anim' && !c.media) { key = 'comp'; inOut = [c.comp_in, c.comp_in + dur]; }
        else if (c.nested) { key = 'nested'; }
        else if (c.kind === 'adjust') { key = 'adjust'; }
        else { key = c.media; }
        const getItem = key === 'adjust' ? adjustmentItem : key === 'nested'
          ? async () => { if (!nestedName[c.nested]) throw new Error('Artwork-Sequenz wurde nicht angelegt'); return nestedItem(nestedName[c.nested]); }
          : () => fresh(key, true);
        if (inOut) {
          const src = await fresh(key);
          if (!src) throw new Error('Quelle fehlt');
          await txp(ppro, 'In/Out', (add) => add(src.createSetInOutPointsAction(tt(ppro, inOut[0]), tt(ppro, inOut[1]))));
        }
        await placeClip(ppro, mainGuid, getItem, c.start, videoIdx, audioIdx);   // nach der Änderung (In/Out) ist `src` ungültig
      }, refresh);
      const ti = await locate();
      if (Math.abs((await ti.getEndTime()).seconds - c.end) > TOL) await txp(ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, c.end))));
      if (c.name) await guarded(report, 'Name ' + c.name, async () => { const t2 = await locate(); await txp(ppro, 'Name', (add) => add(t2.createSetNameAction(c.name))); });
      countOk(c.kind);
      if (isAudio) return;

      // Effekte je nach Art des Clips
      if (c.kind === 'artwork' && c.crop) {
        const r1 = await fx.addCrop(ppro, await getProject(), locate, c.crop, ctx);
        if (r1.fehlend.length) report.warnings.push('Zuschneiden: nicht gesetzt: ' + r1.fehlend.join(', '));
        await fx.setMotion(ppro, await getProject(), locate, { position: c.position, scale: c.scale }, ctx);
      }
      for (const e of [...(c.effects || []), ...(useAdjust ? [] : c.fallback_effects || [])]) {
        ctx.offset = kfBase === 'sequence' ? c.start : kfBase === 'source' ? (await (await locate()).getInPoint()).seconds : 0;
        const r = await fx.addEffect(ppro, await getProject(), locate, e, ctx);
        report.effects[e.id] = (report.effects[e.id] || 0) + 1;
        if (r.fehlend.length) report.warnings.push(e.id + ': Parameter nicht gesetzt: ' + r.fehlend.join(', '));
      }
      ctx.offset = 0;

      // Übergänge: Cross Dissolve wie im Ursprungsschnitt. Scheitert das, bleibt die Deckkraft-Blende der Credits als Rückfall.
      let blended = false;
      if (c.uebergang && plan.transitions && plan.transitions.video) {
        try {
          const n = await trans.addVideoTransitions(ppro, locate, c.uebergang, plan.transitions.video, ctx);
          report.effects.uebergang = (report.effects.uebergang || 0) + n;
          blended = true;
        } catch (e) {
          if (!transWarned) { transWarned = true; report.warnings.push('Übergang (Cross Dissolve) nicht gesetzt: ' + errText(e) + (c.kind === 'credit' ? ' – Credits blenden stattdessen über die Deckkraft.' : '')); }
        }
      }
      if (c.kind === 'credit' && c.fade && !blended) await fx.setFade(ppro, await getProject(), locate, dur, c.fade, ctx);

      // Serienton: Gleichleistungs-Blende als Pegel-Keyframes (die API kennt keine Audioübergänge)
      if (c.kind === 'episode' && c.ton_blende && c.ton_blende.keyframes && c.ton_blende.keyframes.length) {
        await guarded(report, 'Ton-Blende @' + c.start.toFixed(2), async () => {
          const locateA = async () => {
            const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, await getProject(), mainGuid), 'audio', c.audio, c.start);
            if (!ti) throw new Error('Ton des Serienclips nicht auf A' + (c.audio + 1) + ' gefunden');
            return ti;
          };
          ctx.offset = kfBase === 'sequence' ? c.start : kfBase === 'source' ? (await (await locateA()).getInPoint()).seconds : 0;
          try { await trans.setAudioFade(ppro, await getProject(), locateA, c.ton_blende.keyframes, ctx); } finally { ctx.offset = 0; }
          report.effects.ton_blende = (report.effects.ton_blende || 0) + 1;
        });
      }
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
  if (plan.save !== false) await guarded(report, 'Speichern', async () => { await (await getProject()).save(); invalidate(); });
  report.seconds = (Date.now() - report.started) / 1000;
  return report;

}

module.exports = { runPlan, placeClip, trackItemAt, findSequenceItem, sequenceByGuid };
