// Werkzeuge (Kurzbefehle): wirken auf die Auswahl in der Zeitleiste bzw. den Abspielkopf.
// Fachliche Entscheidungen (Rezepte, Artwork-Maße, Credit-Text/-Vorlage, Ton-Blenden, Szenen) trifft der Server über `rpc`;
// hier stehen nur Premiere-Grundoperationen. Objekte werden nie über Änderungen hinweg gehalten (siehe core.js):
// die Auswahl wird als (Art, Spur, Start) beschrieben und der Clip vor jedem Zugriff frisch geholt.
'use strict';

const { tt, txp, errText, getProj, invalidate, walkItems, asClip, norm, retryStale } = require('./core');
const fx = require('./effects');
const trans = require('./transitions');
const mogrt = require('./mogrt');
const media = require('./media');
const { trackItemAt, placeClip, sequenceByGuid } = require('./plan');

const TOOL_BIN = 'Glorfindel-Werkzeuge';
const fmt = (s) => { const m = Math.floor(s / 60); return m + ':' + (s - m * 60).toFixed(1).padStart(4, '0'); };

/** Ein Clip der Auswahl als reine Daten. */
async function describe(ppro, it) {
  const kind = typeof it.createAddVideoTransitionAction === 'function' ? 'video' : 'audio';
  const start = (await it.getStartTime()).seconds;
  const end = (await it.getEndTime()).seconds;
  let path = null, isSeq = false, src = '';
  try {
    const pi = await it.getProjectItem();
    const clip = asClip(ppro, pi);
    if (clip) { isSeq = await clip.isSequence(); if (!isSeq) path = (await clip.getMediaFilePath()) || null; }
    src = (pi && pi.name) || '';                                                  // Name der Quelle: bei Artwork „Artwork 01 <Bild>“, der Clip selbst heißt nur wie das Bild
  } catch (e) { /* Grafik ohne Datei */ }
  return { kind, track: await it.getTrackIndex(), start, end, dur: end - start, name: await it.getName(), path, isSeq, src };
}

class Tools {
  constructor({ ppro, rpc, log = () => {} }) {
    this.ppro = ppro;
    this.rpc = rpc;
    this.log = log;
    this.cfg = null;
  }

  async config(force = false) {
    if (!this.cfg || force) this.cfg = await this.rpc('tools.config', {});
    return this.cfg;
  }

  // ---------- Auswahl ----------
  async activeSequence() {
    const seq = await (await getProj(this.ppro)).getActiveSequence();
    if (!seq) throw new Error('In Premiere ist keine Sequenz geöffnet.');
    return seq;
  }

  /** Gewählte Clips (nach Zeit sortiert). `kind`: nur Video oder nur Ton. */
  async selection(kind = null) {
    const seq = await this.activeSequence();
    const guid = String(seq.guid);
    const sel = await seq.getSelection();
    const raw = sel ? await sel.getTrackItems() : [];
    const items = [];
    for (const it of raw) items.push(await describe(this.ppro, it));
    items.sort((a, b) => a.start - b.start || a.track - b.track);
    const use = kind ? items.filter((i) => i.kind === kind) : items;
    if (!use.length) throw new Error(kind === 'audio' ? 'Keine Tonclips ausgewählt (Clip in der Zeitleiste anklicken, ggf. den Ton).'
      : kind === 'video' ? 'Keine Videoclips ausgewählt (Clip in der Zeitleiste anklicken).' : 'Nichts ausgewählt (Clip in der Zeitleiste anklicken).');
    return { guid, items: use };
  }

  locator(guid, item) {
    return async () => {
      const ti = await trackItemAt(this.ppro, await sequenceByGuid(this.ppro, await getProj(this.ppro), guid), item.kind, item.track, item.start);
      if (!ti) throw new Error('Clip „' + item.name + '“ (' + (item.kind === 'video' ? 'V' : 'A') + (item.track + 1) + ', ' + fmt(item.start) + ') nicht mehr gefunden');
      return ti;
    };
  }

  async playhead() {
    return (await (await this.activeSequence()).getPlayerPosition()).seconds;
  }

  /** Keyframe-Zeitbezug wie im Bau: Einstiegspunkt des Clips (Standard) oder Sequenzzeit. */
  async keyframeOffset(item, locate) {
    const cfg = await this.config();
    const base = (cfg.calibration && cfg.calibration.keyframeBase) === 'sequence' ? 'sequence' : 'source';
    return base === 'sequence' ? item.start : (await (await locate()).getInPoint()).seconds;
  }

  async fxCtx() {
    const cfg = await this.config();
    return { colorMode: (cfg.calibration && cfg.calibration.colorMode) || 'unit', offset: 0 };
  }

  // ---------- Werkzeuge ----------
  /** Effektrezepte (Karte, Gauß, Zoom, …) auf die gewählten Videoclips. `ids`: Rezepte, z. B. ['karte_in', 'karte_out']. */
  async effects({ ids, label = '' }) {
    const { guid, items } = await this.selection('video');
    const res = await this.rpc('tools.effects', { ids, clips: items.map((i) => ({ dur: i.dur })) });
    const ctx = await this.fxCtx();
    const warnings = [];
    for (let i = 0; i < items.length; i++) {
      const loc = this.locator(guid, items[i]);
      for (const e of res.clips[i]) {
        ctx.offset = await this.keyframeOffset(items[i], loc);
        try {
          const r = await fx.addEffect(this.ppro, await getProj(this.ppro), loc, e, ctx);
          if (r.fehlend.length) warnings.push(items[i].name + ' / ' + e.id + ': ' + r.fehlend.join(', '));
        } finally { ctx.offset = 0; }
      }
    }
    return { text: (label || ids.join(' + ')) + ' auf ' + items.length + ' Clip' + (items.length === 1 ? '' : 's') + ' gesetzt', warnings };
  }

  /** Cross Dissolve an Anfang und/oder Ende der gewählten Videoclips (Dauer wie im Bau, höchstens die halbe Clipdauer). */
  async transitions({ ein = true, aus = true }) {
    const { guid, items } = await this.selection('video');
    const cfg = await this.config();
    const ctx = {};
    let n = 0;
    for (const it of items) {
      const h = Math.min(cfg.uebergang.dauer, it.dur / 2);
      if (h < 0.05) continue;
      n += await trans.addVideoTransitions(this.ppro, this.locator(guid, it), { ein: ein ? h : 0, aus: aus ? h : 0 }, { match_name: cfg.uebergang.match_name }, ctx);
    }
    return { text: n + ' Überblendung' + (n === 1 ? '' : 'en') + ' gesetzt (' + items.length + ' Clip' + (items.length === 1 ? '' : 's') + ')', warnings: [] };
  }

  /** Gleichleistungs-Blende (Pegel-Keyframes) an den gewählten Tonclips. */
  async audioFade({ ein = true, aus = true }) {
    const { guid, items } = await this.selection('audio');
    const ctx = await this.fxCtx();
    let n = 0;
    for (const it of items) {
      const r = await this.rpc('tools.audiofade', { dur: it.dur, ein: ein ? null : 0, aus: aus ? null : 0 });
      if (!r.keyframes.length) continue;
      const loc = this.locator(guid, it);
      ctx.offset = await this.keyframeOffset(it, loc);
      try { await trans.setAudioFade(this.ppro, await getProj(this.ppro), loc, r.keyframes, ctx); } finally { ctx.offset = 0; }
      n++;
    }
    return { text: 'Ton-Blende an ' + n + ' Tonclip' + (n === 1 ? '' : 's') + ' gesetzt', warnings: [] };
  }

  /** Ende der gewählten Clips setzen (ohne andere Clips zu verschieben). `seconds`: neue Länge; sonst bis zum Abspielkopf. */
  async setLength({ seconds = null }) {
    const { guid, items } = await this.selection();
    const head = seconds == null ? await this.playhead() : null;
    let n = 0;
    const skipped = [];
    for (const it of items) {
      const end = seconds != null ? it.start + seconds : head;
      if (!(end > it.start + 0.01)) { skipped.push(it.name); continue; }
      if (Math.abs(end - it.end) < 0.002) continue;
      const loc = this.locator(guid, it);
      await retryStale(async () => { const ti = await loc(); await txp(this.ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(this.ppro, end)))); });
      n++;
    }
    return { text: n + ' Clip' + (n === 1 ? '' : 's') + (seconds != null ? ' auf ' + seconds + ' s' : ' bis zum Abspielkopf (' + fmt(head) + ')') + ' gesetzt',
      warnings: skipped.length ? ['Nicht geändert (Ende läge vor dem Anfang): ' + skipped.join(', ')] : [] };
  }

  /** Bild unter einem Credit/Text: auf den Inhaltsspuren (Artwork, Standbilder; `quellspuren` vom Server) unterhalb von `track` der Clip, der `t` überdeckt. */
  async clipBeneath(guid, track, t) {
    const cfg = await this.config();
    const seq = await sequenceByGuid(this.ppro, await getProj(this.ppro), guid);
    for (const tr of (cfg.quellspuren || [2, 3, 0]).filter((x) => x < track)) {
      let list;
      try { list = (await seq.getVideoTrack(tr)).getTrackItems(this.ppro.Constants.TrackItemType.CLIP, false); } catch (e) { continue; }
      for (const raw of list) {
        const s0 = (await raw.getStartTime()).seconds, e0 = (await raw.getEndTime()).seconds;
        if (s0 <= t + 0.004 && t < e0 - 0.004) {
          const d = await describe(this.ppro, raw);
          if (d.path || (d.isSeq && /^artwork/i.test(d.name))) return d;
        }
      }
    }
    return null;
  }

  /** Credit zu den gewählten Clips (Name aus der Bilddatei bzw. dem Clip darunter) oder mit freiem Text am Abspielkopf. */
  async credit({ art = 'artwork', text = '' }) {
    const typed = String(text || '').trim();
    const warnings = [];
    let guid, jobs;
    if (typed && !(await this.hasSelection())) {
      const seq = await this.activeSequence();
      guid = String(seq.guid);
      jobs = [{ start: await this.playhead(), dur: 5, text: typed, path: null, name: null }];
    } else {
      const sel = await this.selection('video');
      guid = sel.guid;
      jobs = [];
      for (const it of sel.items) {
        const named = (c) => (c.isSeq && /^artwork\b/i.test(c.src || '') ? { ...c, name: c.src } : c);   // Artwork-Clip heißt wie das Bild; die Sequenz dahinter „Artwork 01 <Bild>“
        let src = named(it);
        if (!typed && !src.path && !/^artwork\b/i.test(src.name)) {                   // z. B. ein Text-/Credit-Clip: der Clip darunter liefert den Namen
          const under = await this.clipBeneath(guid, it.track, it.start);
          if (under) src = named(under); else { warnings.push('Unter „' + it.name + '“ liegt kein Bild.'); continue; }
        }
        jobs.push({ start: it.start, dur: it.dur, text: typed || null, path: src.path, name: src.name });
      }
    }
    let n = 0;
    const done = [];
    const ctx = {};
    for (const j of jobs) {
      try { done.push(await this.placeCredit(guid, art, j, ctx, warnings)); n++; } catch (e) { warnings.push(errText(e)); }
    }
    return { text: n + ' Credit' + (n === 1 ? '' : 's') + ' gesetzt' + (done.length ? ': ' + done.join(' · ') : ''), warnings };
  }

  /** Clips einer Videospur, die nach `t` enden (Zeit, Name) – zum Vergleich vor/nach dem Einsetzen einer Vorlage. */
  async itemsAfter(guid, track, t) {
    const seq = await sequenceByGuid(this.ppro, await getProj(this.ppro), guid);
    let list = [];
    try { list = (await seq.getVideoTrack(track)).getTrackItems(this.ppro.Constants.TrackItemType.CLIP, false) || []; } catch (e) { return []; }
    const out = [];
    for (const raw of list) {
      if (!raw) continue;
      const s = (await raw.getStartTime()).seconds, e = (await raw.getEndTime()).seconds;
      if (e > t + 0.004) out.push({ start: s, end: e, name: await raw.getName() });
    }
    return out.sort((a, b) => a.start - b.start);
  }

  /** `insertMogrtFromPath` fügt EIN statt zu überschreiben (gemessen in Test10.prproj: spätere Clips derselben Spur rücken um die Vorlagenlänge
   *  nach hinten, ein Clip an der Einfügestelle wird geteilt). Danach wie beim Überschreiben aufräumen: was im Bereich des neuen Credits lag,
   *  entfällt (ganz darin: entfernt, darüber hinaus: vorne gekürzt), alles Spätere rückt an seinen alten Platz. `before`: Clips vor dem Einsetzen. */
  async restoreShifted(guid, track, t, dur, before, warnings) {
    const ppro = this.ppro;
    const end = t + dur;
    const old = before.map((x) => ({ ...x, start: Math.max(x.start, t) }));          // ein geteilter Clip: der rechte Teil wurde verschoben
    const now = (await this.itemsAfter(guid, track, t)).filter((x) => x.start > t + 0.004);
    if (now.length !== old.length) { if (old.length) warnings.push('V' + (track + 1) + ': Clips hinter dem Credit wurden beim Einsetzen verschoben – bitte prüfen.'); return; }
    const seqOf = async () => sequenceByGuid(ppro, await getProj(ppro), guid);
    for (let i = 0; i < old.length; i++) {
      const o = old[i];
      let cur = now[i].start;
      const shift = cur - o.start;
      if (Math.abs(shift) < 0.004) continue;
      const at = (s) => async () => { const ti = await trackItemAt(ppro, await seqOf(), 'video', track, s); if (!ti) throw new Error('nicht gefunden'); return ti; };
      try {
        if (o.end <= end + 0.004) {                    // ganz im Bereich des neuen Credits: entfällt (wie beim Überschreiben)
          await retryStale(() => mogrt.removeClip(ppro, seqOf, at(cur)));
          warnings.push('„' + o.name + '“ (V' + (track + 1) + ', ' + fmt(o.start) + ') lag im Bereich des neuen Credits und wurde ersetzt.');
          continue;
        }
        if (o.start < end - 0.004) {                   // ragt hinein: vorne kürzen
          const ns = cur + (end - o.start);
          await retryStale(async () => { const ti = await at(cur)(); await txp(ppro, 'Kürzen', (add) => add(ti.createSetStartAction(tt(ppro, ns)))); });
          cur = ns;
        }
        const back = cur - Math.max(o.start, end);
        await retryStale(async () => { const ti = await at(cur)(); await txp(ppro, 'Zurückschieben', (add) => add(ti.createMoveAction(ppro.TickTime.createWithSeconds(-back)))); });
      } catch (e) {
        warnings.push('„' + o.name + '“ (V' + (track + 1) + ') wurde beim Einsetzen um ' + shift.toFixed(2) + ' s nach hinten verschoben und ließ sich nicht zurückholen: ' + errText(e) + ' – bitte von Hand zurückschieben.');
      }
    }
  }

  /** Einen Credit setzen (Vorlage mit festem Text vom Server, Länge, Name, Überblendung). Gibt den Credit-Text zurück; Fehler werden geworfen.
   *  Wie im Bau: nach dem Einsetzen auf die Grafik warten; kommt sie nicht, einmal neu einsetzen, dann das PNG des Servers (mit Hinweis). */
  async placeCredit(guid, art, j, ctx, warnings = []) {
    const ppro = this.ppro;
    const cfg = await this.config();
    const r = await this.rpc('tools.credit', { art, path: j.path, name: j.name, text: j.text, dur: j.dur });
    const seqOf = async () => sequenceByGuid(ppro, await getProj(ppro), guid);
    const loc = async () => {
      const ti = await trackItemAt(ppro, await seqOf(), 'video', r.track, j.start);
      if (!ti) throw new Error('eingesetzter Credit nicht auf V' + (r.track + 1) + ' gefunden');
      return ti;
    };
    const before = await retryStale(() => this.itemsAfter(guid, r.track, j.start));
    let state = null, ok = false;
    for (let attempt = 1; attempt <= 2 && !ok; attempt++) {
      await retryStale(async () => {
        const project = await getProj(ppro);
        await mogrt.insertTemplate(ppro, project, await sequenceByGuid(ppro, project, guid), { path: r.mogrt, start: j.start, track: r.track });
      });
      if (!mogrt.canVerify(ppro)) { ok = true; break; }
      state = await mogrt.waitForGraphic(loc);
      if (state.ok) { ok = true; break; }
      await retryStale(() => mogrt.removeClip(ppro, seqOf, loc));
    }
    if (!ok) {
      const why = 'Premiere hat die Grafik der Vorlage nicht geladen (nur ' + ((state && state.comps.join(', ')) || 'keine Komponenten') + ')';
      if (!r.png) throw new Error('Credit „' + r.text + '“: ' + why + '.');
      await media.importFiles(ppro, await getProj(ppro), [r.png], TOOL_BIN);
      await placeClip(ppro, guid, async () => media.rawByPath(ppro, await media.getBin(ppro, await getProj(ppro), TOOL_BIN), r.png), j.start, r.track, -1);
      warnings.push('Credit „' + r.text + '“: ' + why + ' – als PNG gesetzt.');
    }
    await retryStale(async () => {
      const ti = await loc();
      if (Math.abs((await ti.getEndTime()).seconds - (j.start + j.dur)) > 0.004) await txp(ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, j.start + j.dur))));
    });
    await this.restoreShifted(guid, r.track, j.start, j.dur, before, warnings);
    await retryStale(async () => { const t2 = await loc(); await txp(ppro, 'Name', (add) => add(t2.createSetNameAction(r.text))); });
    const h = Math.min(r.uebergang, j.dur / 2);
    if (h >= 0.05) {
      try { await trans.addVideoTransitions(ppro, loc, { ein: h, aus: h }, { match_name: cfg.uebergang.match_name }, ctx); }
      catch (e) { throw new Error('Übergang am Credit „' + r.text + '“ nicht gesetzt: ' + errText(e)); }
    }
    return r.text;
  }

  /** Sequenz wieder aktiv machen (eine neu angelegte Sequenz wird in Premiere automatisch aktiv und geöffnet). */
  async activate(guid) {
    await retryStale(async () => {
      const project = await getProj(this.ppro);
      await project.setActiveSequence(await sequenceByGuid(this.ppro, project, guid));
      invalidate();
    });
  }

  /** Gewählte Bilder in verschachtelte Artwork-Sequenzen mit Maske und Spurmaske-Key umwandeln (an derselben Stelle) und die Standardeffekte setzen. */
  async artwork() {
    const { guid, items } = await this.selection('video');
    const imgs = items.filter((i) => i.path && !i.isSeq);
    if (!imgs.length) throw new Error('Kein Bild ausgewählt: Ein Standbild/Bild (kein Film, keine Sequenz) in der Zeitleiste anklicken.');
    const ctx = await this.fxCtx();
    const warnings = [];
    let n = 0;
    for (const it of imgs) {
      try { await this.artworkOne(guid, it, ctx, warnings); n++; } catch (e) { warnings.push('Artwork „' + it.name + '“: ' + errText(e)); continue; }
      try { await this.placeCredit(guid, 'artwork', { start: it.start, dur: it.dur, text: null, path: it.path, name: it.name }, {}, warnings); }
      catch (e) { warnings.push('Bildcredit zu „' + it.name + '“: ' + errText(e)); }
    }
    if (items.length > imgs.length) warnings.push((items.length - imgs.length) + ' ausgewählte Clip(s) ohne Bilddatei übersprungen.');
    return { text: n + ' Artwork' + (n === 1 ? '' : 's') + ' gebaut', warnings };
  }

  async artworkOne(guid, it, ctx, warnings) {
    const ppro = this.ppro;
    const spec = await this.rpc('tools.artwork', { path: it.path, dur: it.dur });
    const nspec = spec.nested;
    const getProject = () => getProj(ppro);
    await media.importFiles(ppro, await getProject(), [nspec.image, nspec.mask], TOOL_BIN);
    const rawItem = async (p) => media.rawByPath(ppro, await media.getBin(ppro, await getProject(), TOOL_BIN), p);
    // freier Sequenzname
    const taken = new Set();
    for (const x of await walkItems(ppro, await (await getProject()).getRootItem())) taken.add(x.name);
    let name = nspec.name, k = 2;
    while (taken.has(name)) name = nspec.name + ' ' + k++;
    // verschachtelte Sequenz bauen (wie im Bau)
    const nguid = await retryStale(async () => {
      const seq = await (await getProject()).createSequenceWithPresetPath(name, nspec.preset);
      const g = String(seq.guid);
      invalidate();
      return g;
    });
    const nloc = (track) => async () => {
      const ti = await trackItemAt(ppro, await sequenceByGuid(ppro, await getProject(), nguid), 'video', track, 0);
      if (!ti) throw new Error('Clip auf V' + (track + 1) + ' nicht gefunden');
      return ti;
    };
    const parts = [[nspec.image, nspec.image_track, nspec.image_scale, nspec.image_position], [nspec.mask, nspec.mask_track, nspec.mask_scale, nspec.mask_position]];
    for (const [file, track] of parts) {
      await placeClip(ppro, nguid, () => rawItem(file), 0, track, -1);
      await retryStale(async () => {
        const ti = await nloc(track)();
        if (Math.abs((await ti.getEndTime()).seconds - nspec.dur) > 0.004) await txp(ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, nspec.dur))));
      });
    }
    for (const [, track, scale, position] of parts) await fx.setMotion(ppro, await getProject(), nloc(track), { position, scale }, ctx);
    const matte = { id: 'spurmaske', match_name: 'AE.ADBE Legacy Key Track Matte', display: 'Spurmaske-Key',
      params: [{ index: 0, names: ['Maske:', 'Matte:', 'Mask:'], value: nspec.matte_track }, { index: 1, names: ['Compositing mit', 'Composite Using'], value: 0 }] };
    const rm = await fx.addEffect(ppro, await getProject(), nloc(nspec.image_track), matte, ctx);
    if (rm.fehlend.length) warnings.push('Spurmaske-Key (' + name + '): ' + rm.fehlend.join(', '));
    // Das Bild in der Hauptsequenz durch die Artwork-Sequenz ersetzen.
    // Premiere macht die eben angelegte Artwork-Sequenz aktiv; die Hauptsequenz erst wieder aktivieren (wie im Bau, „Hauptsequenz wieder aktivieren“),
    // sonst landeten Entfernen und Setzen nicht in der Hauptsequenz und das Bild blieb stehen.
    await this.activate(guid);
    const seqItem = async () => {
      for (const x of await walkItems(ppro, await (await getProject()).getRootItem())) {
        if (x.name !== name) continue;
        const c = asClip(ppro, x);
        if (c && (await c.isSequence())) return x;
      }
      return null;
    };
    // Überschreiben statt erst Entfernen: die Artwork-Sequenz ist genau so lang wie das Bild und ersetzt es; scheitert das Setzen, bleibt das Bild stehen
    await placeClip(ppro, guid, seqItem, it.start, it.track, -1);
    const after = this.locator(guid, it);
    const placed = await retryStale(async () => describe(ppro, await after()));
    if (!placed.isSeq) {
      throw new Error('Artwork-Sequenz „' + name + '“ ist angelegt, aber Premiere hat sie nicht an die Stelle des Bildes gesetzt (V' + (it.track + 1) + ', ' + fmt(it.start)
        + '; dort liegt „' + placed.name + '“). Bitte die Sequenz aus dem Projektfenster von Hand auf das Bild ziehen.');
    }
    await retryStale(async () => {
      const ti = await after();
      if (Math.abs((await ti.getEndTime()).seconds - it.end) > 0.004) await txp(ppro, 'Länge', (add) => add(ti.createSetEndAction(tt(ppro, it.end))));
    });
    const rest = (await this.itemsAfter(guid, it.track, it.start)).filter((x) => x.start > it.start + 0.004 && x.start < it.end - 0.004 && x.name === it.name);
    if (rest.length) warnings.push('Vom Bild „' + it.name + '“ ist hinter der Artwork-Sequenz ein Rest stehen geblieben (' + fmt(rest[0].start) + ') – bitte löschen.');
    await retryStale(async () => { const t2 = await after(); await txp(ppro, 'Name', (add) => add(t2.createSetNameAction(name))); });
    for (const e of spec.effects) {
      ctx.offset = await this.keyframeOffset(it, after);
      try {
        const r = await fx.addEffect(ppro, await getProject(), after, e, ctx);
        if (r.fehlend.length) warnings.push(e.id + ': Parameter nicht gesetzt: ' + r.fehlend.join(', '));
      } finally { ctx.offset = 0; }
    }
  }

  /** Szene am Abspielkopf (aus dem letzten Bau) anzeigen. */
  async sceneAtPlayhead() {
    const t = await this.playhead();
    const r = await this.rpc('tools.scene_at', { time: t });
    if (!r.scene) return { text: 'Am Abspielkopf (' + fmt(t) + ') liegt keine Szene aus dem Rohschnitt.', warnings: [] };
    return { text: 'Szene ' + r.scene + (r.titel ? ' „' + r.titel + '“' : '') + ' · ' + fmt(r.start) + '–' + fmt(r.end) + (r.status ? ' · Status: ' + r.status : ''), warnings: [] };
  }

  /** Abspielkopf setzen (vom Server aufgerufen: „Szene in Premiere zeigen“). */
  async seek({ time }) {
    const seq = await this.activeSequence();
    if ((await seq.setPlayerPosition(tt(this.ppro, Number(time)))) === false) throw new Error('Premiere hat den Abspielkopf nicht verschoben.');
    return { time: Number(time) };
  }

  /** Komponenten und Parameter des ersten gewählten Clips mit dem Typ ihrer Werte (Fehlersuche). */
  async inspect() {
    const { guid, items } = await this.selection();
    const it = items[0];
    const chain = await (await this.locator(guid, it)()).getComponentChain();
    const lines = [];
    for (const c of await fx.listComponents(chain)) {
      const ps = [];
      for (const p of fx.paramList(c.comp)) {
        let t;
        try {
          const v = await p.param.getStartValue();
          t = v === null || v === undefined ? 'null' : (v.constructor && v.constructor.name && v.constructor.name !== 'Object' ? v.constructor.name : typeof v);
        } catch (e) { t = 'Fehler'; }
        ps.push((p.name || '#' + p.index) + ':' + t);
      }
      lines.push(c.index + ' ' + c.name + ' → ' + ps.join(', '));
    }
    return { text: (it.kind === 'video' ? 'V' : 'A') + (it.track + 1) + ' „' + it.name + '“ ' + fmt(it.start) + '–' + fmt(it.end) + (it.path ? ' · ' + it.path : ''), warnings: [], lines };
  }

  /** Werkzeug nach Name ausführen (Oberfläche und Tests). */
  async run(name, args = {}) {
    const table = {
      effects: (a) => this.effects(a), transitions: (a) => this.transitions(a), audioFade: (a) => this.audioFade(a), length: (a) => this.setLength(a),
      credit: (a) => this.credit(a), artwork: () => this.artwork(), scene: () => this.sceneAtPlayhead(), inspect: () => this.inspect(),
    };
    if (!table[name]) throw new Error('Unbekanntes Werkzeug: ' + name);
    return table[name](args);
  }

  async hasSelection() {
    try { await this.selection(); return true; } catch (e) { return false; }
  }
}

module.exports = { Tools, describe, TOOL_BIN, fmt };
