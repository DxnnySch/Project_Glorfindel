// Szenen-Editor (Segment-Workflow): Liste mit Status auf einen Blick, Player + Dialog, Segmentkarten mit Kommentaren, Autosave.
import { h, $, clear, btn, icon, toast, modal, confirmBox, busy, fmtDur, fmtTC, debounce, empty, lightLabel, remember, thumbOfAsset, thumbOfMap } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource, strandOf } from '../state.js';
import { createPlayer, segColor } from '../scene/player.js';
import { createSegments } from '../scene/segments.js';

const STATUS = { neu: 'Neu', skript_fertig: 'Skript fertig', aufgenommen: 'Aufgenommen', abgeglichen: 'Abgeglichen', veraltet: 'Veraltet' };

export async function render(main, ctx) {
  const ep = S.ep;
  const ui = remember(`${ep.season}-${ep.episode}:editor`, { query: '', filt: '', sel: '', allEp: false, listScroll: 0, mainScroll: 0 });
  const [scenes0, assets, maps, dialog] = await Promise.all([api.get(epUrl(ep, '/scenes')), api.get(epUrl(ep, '/assets')), api.get(epUrl(ep, '/maps')), api.get(epUrl(ep, '/dialog')).catch(() => ({ available: false, words: [] }))]);
  let scenes = scenes0;
  const normalize = (s) => { if (s.segmente?.length) s.kommentar.forEach((b) => { if (b.segment == null) b.segment = s.segmente.length - 1; }); return s; };
  scenes.forEach(normalize);
  const hashId = location.hash.split('?id=')[1];
  let sel = scenes.find((s) => s.id === hashId) || scenes.find((s) => s.id === ui.sel) || scenes[0] || null;
  let dirty = false, saving = false, blocked = false, hb = null, locked = null, forceNext = false;
  const ref = refSource();

  const E = { ep, ref, ui, assets, maps, dialog, focusBlock: null,
    sel: () => sel, touch: () => touch(), redrawSegments: () => segs.redraw(), redrawAll: () => drawScene(),
    scenes: () => scenes, gotoScene: (id) => select(id),
    addSegment, focusSegment: (i) => segs.focus(i) };
  const player = createPlayer(E);
  E.player = player;
  const segs = createSegments(E);

  const listEl = h('div', { class: 'scene-list' }), mainEl = h('div', { class: 'editor-main' });
  main.append(h('div', { class: 'editor' }, listEl, mainEl));
  main.style.overflow = 'hidden';
  const stateEl = h('span', { class: 'savestate' });
  const setState = (t) => { stateEl.textContent = t; };

  // ---------- Speichern ----------
  const clean = (s) => { const { report, lock, problems, ausgabe, ...rest } = s; return rest; };
  const save = debounce(async () => {
    if (!sel || saving || blocked) return;
    saving = true; setState('Speichert …');
    try {
      const q = sel.geaendert_am && !forceNext ? `?base=${encodeURIComponent(sel.geaendert_am)}` : '';
      forceNext = false;
      const { scene, report, locked_by_other, problems } = await api.put(epUrl(ep, `/scenes/${sel.id}${q}`), clean(sel));
      Object.assign(sel, { report, problems: problems || [], status: scene.status, geaendert_von: scene.geaendert_von, geaendert_am: scene.geaendert_am }); dirty = false;
      setState(`${locked_by_other ? `Achtung: ${locked_by_other} bearbeitet ebenfalls · ` : ''}Gespeichert ${new Date().toLocaleTimeString('de-DE')}`);
      drawList(); drawBanner(); drawPills(); refreshCoverage();
    } catch (e) {
      setState('Nicht gespeichert');
      if (e.status === 409) conflictDialog(e.message); else toast(e.message, 'err');
    } finally { saving = false; if (dirty && !blocked) save(); }
  }, 700);
  async function refreshCoverage() {   // welche Szenen ein Segment überdeckt, ändert sich beim Speichern – Inhalt bleibt unangetastet
    try {
      const fresh = new Map((await api.get(epUrl(ep, '/scenes'))).map((x) => [x.id, x]));
      for (const s of scenes) { const f = fresh.get(s.id); if (!f) continue; s.nr = f.nr; s.segmente_info = f.segmente_info; s.beruehrt = f.beruehrt; s.ausgabe = f.ausgabe; if (s !== sel) { s.report = f.report; s.problems = f.problems; } else { s.problems = f.problems; } }
      drawList(); drawBanner(); segs.updateSpans();
    } catch { /* nächstes Speichern versucht es erneut */ }
  }
  function conflictDialog(msg) {
    if (blocked) return;
    blocked = true;
    modal({ title: 'Szene wurde inzwischen geändert', onClose: () => { blocked = false; }, body: h('p', {}, `${msg} Möchtest du deine Version trotzdem speichern (überschreibt die andere) oder die aktuelle Version laden (deine Änderungen an dieser Szene gehen verloren)?`),
      actions: [{ label: 'Aktuelle laden', onClick: async () => { blocked = false; dirty = false; scenes = await api.get(epUrl(ep, '/scenes')); scenes.forEach(normalize); sel = scenes.find((x) => x.id === sel.id) || scenes[0]; drawList(); drawScene(); } },
        { label: 'Meine speichern', kind: 'primary', onClick: () => { blocked = false; forceNext = true; dirty = true; save(); } }] });
  }
  const touch = () => { dirty = true; setState('Ungespeichert …'); save(); };

  // ---------- Liste ----------
  const matches = (s) => {
    const q = ui.query.trim().toLowerCase();
    if (q && !`${s.titel} ${(s.kommentar || []).map((k) => `${k.text} ${(k.stichpunkte || []).join(' ')}`).join(' ')} ${(s.segmente || []).map((g) => g.notiz).join(' ')}`.toLowerCase().includes(q)) return false;
    const f = ui.filt;
    if (!f) return true;
    if (f === 'ohne_segment') return !s.segmente.length && !(s.beruehrt || []).length;
    if (f === 'mit_segment') return s.segmente.length || (s.beruehrt || []).length;
    if (f === 'ohne_kommentar') return !s.kommentar.length;
    if (f === 'rot') return s.report?.light === 'rot';
    if (f.startsWith('st:')) return s.strang === f.slice(3);
    if (f.startsWith('status:')) return s.status === f.slice(7);
    return true;
  };
  const anchorsOf = (s) => s.kommentar.flatMap((b) => b.anker || []);
  const thumbFor = (a) => { const it = a.karte ? maps.find((m) => m.id === a.karte) : assets.find((x) => x.id === a.asset); return it ? (a.karte ? thumbOfMap(it) : thumbOfAsset(it)) : null; };
  let listBody = null;
  function drawList() {
    if (!listEl.firstChild) {
      const search = h('input', { type: 'search', placeholder: 'Suchen (Titel, Text, Notiz) …', value: ui.query, onInput: (e) => { ui.query = e.target.value; drawList(); } });
      const fsel = h('select', { onChange: (e) => { ui.filt = e.target.value; drawList(); } }, h('option', { value: '' }, 'Alle Szenen'), h('option', { value: 'ohne_segment' }, 'Nicht im Video (ohne Segment)'), h('option', { value: 'mit_segment' }, 'Im Video (mit Segment)'), h('option', { value: 'ohne_kommentar' }, 'Ohne Kommentar'), h('option', { value: 'rot' }, 'Zu langes Segment'),
        ...S.data.strands.map((x) => h('option', { value: `st:${x.id}` }, `Strang: ${x.name}`)), ...Object.entries(STATUS).map(([k, v]) => h('option', { value: `status:${k}` }, `Status: ${v}`)));
      fsel.value = ui.filt;
      listEl.append(h('div', { class: 'scene-list-head' }, h('div', { class: 'row' }, h('b', { class: 'grow', title: 'Szenen sind die Messeinheiten aus der Szenenerkennung. Ins Video kommen nur Segmente.' }, 'Szenen'), h('span', { class: 'help', id: 'scene-count' })), h('div', { class: 'col gap-s', style: { marginTop: '8px' } }, search, fsel)));
      listBody = h('div'); listEl.append(listBody);
      listEl.addEventListener('scroll', () => { ui.listScroll = listEl.scrollTop; });
    }
    clear(listBody);
    const shown = scenes.filter(matches);
    $('#scene-count', listEl).textContent = shown.length === scenes.length ? `${scenes.length}` : `${shown.length} von ${scenes.length}`;
    shown.forEach((s) => {
      const i = scenes.indexOf(s), st = strandOf(s.strang), light = s.report?.light || 'grau';
      const nPh = s.kommentar.filter((b) => b.sprecher === 'philipp').length, nDa = s.kommentar.filter((b) => b.sprecher === 'danny').length;
      const anchors = anchorsOf(s);
      const unused = !s.segmente.length && !(s.beruehrt || []).length && !s.kommentar.length, touched = (s.beruehrt || []).length;
      const el = h('div', { class: `scene-item ${sel?.id === s.id ? 'active' : ''} ${unused ? 'unused' : ''}`, draggable: 'true', style: { borderLeftColor: st?.color || 'transparent' },
        onClick: () => select(s.id),
        onDragstart: (e) => { e.dataTransfer.setData('text/plain', s.id); },
        onDragover: (e) => { e.preventDefault(); el.classList.add('dragover'); }, onDragleave: () => el.classList.remove('dragover'),
        onDrop: async (e) => { e.preventDefault(); el.classList.remove('dragover'); const from = e.dataTransfer.getData('text/plain'); if (from && from !== s.id) await move(from, s.id); } },
      h('span', { class: 'no', title: s.nr ? `Szene ${s.nr} (Messeinheit der Szenenerkennung)${s.ausgabe ? ` · Position im Video: ${s.ausgabe}` : ''}` : '' }, String(s.nr || s.ausgabe || i + 1).padStart(2, '0')),
      h('div', { class: 'grow' }, h('div', { class: 't' }, s.titel || '(ohne Titel)'),
        h('small', {}, h('span', { class: `dot ${light}`, title: lightLabel[light] || 'kein Material' }), st ? st.name : 'ohne Strang', '·', STATUS[s.status] || s.status, s.fixiert ? icon('lock') : null,
          s.lock && s.lock.user !== S.settings.user ? h('span', { class: 'chip' }, `${s.lock.user}`) : null),
        h('div', { class: 'si-meta' },
          s.bereich ? h('span', { class: 'chip faint mono', title: 'Zeitbereich dieser Szene in der Episode' }, `${fmtTC(s.bereich[0]).slice(0, 5)}–${fmtTC(s.bereich[1]).slice(0, 5)}`) : null,
          h('span', { class: `chip ${s.segmente.length ? '' : 'faint'}`, title: `${s.segmente.length} Segment(e), die in dieser Szene beginnen` }, icon('scissors'), String(s.segmente.length)),
          touched ? h('span', { class: 'chip accent', title: `${touched} Segment(e) aus anderen Szenen reichen hier hinein` }, `+${touched}`) : null,
          unused ? h('span', { class: 'chip faint' }, 'nicht im Video') : null,
          h('span', { class: `chip ${nPh + nDa ? '' : 'faint'}`, title: `Kommentare: Philipp ${nPh}, Danny ${nDa}` }, icon('edit'), String(nPh + nDa), nPh ? h('i', { class: 'sdot philipp' }) : null, nDa ? h('i', { class: 'sdot danny' }) : null),
          ...anchors.slice(0, 4).map((a) => h('img', { class: 'mini-thumb', src: thumbFor(a) || '', title: a.karte || a.asset })),
          anchors.length > 4 ? h('small', {}, `+${anchors.length - 4}`) : null)));
      listBody.append(el);
    });
    if (!scenes.length) listBody.append(empty('edit', 'Keine Szenen', 'Szenen entstehen durch die Szenenerkennung im Strang-Board. Dort erkennen und als Szenen anlegen.'));
    else if (!shown.length) listBody.append(h('p', { class: 'help', style: { padding: '14px' } }, 'Keine Szene passt zum Filter.'));
  }
  async function moveTo(id, index) {
    const ids = scenes.map((s) => s.id).filter((x) => x !== id); ids.splice(Math.max(0, Math.min(ids.length, index)), 0, id);
    await api.post(epUrl(ep, '/scenes-reorder'), { order: ids }); scenes = await api.get(epUrl(ep, '/scenes')); scenes.forEach(normalize); sel = scenes.find((s) => s.id === sel?.id) || sel; drawList();
  }
  async function move(from, to) {
    const ids = scenes.map((s) => s.id), fi = ids.indexOf(from), ti = ids.indexOf(to); ids.splice(fi, 1); ids.splice(fi < ti ? ti : ti, 0, from);
    await api.post(epUrl(ep, '/scenes-reorder'), { order: ids }); scenes = await api.get(epUrl(ep, '/scenes')); scenes.forEach(normalize); sel = scenes.find((s) => s.id === sel?.id) || sel; drawList();
  }
  async function select(id) {
    if (dirty && sel) { await save.now(); if (dirty || blocked) return; }
    if (sel && locked === sel.id) { api.del(epUrl(ep, `/scenes/${sel.id}/lock`)).catch(() => {}); locked = null; }
    sel = scenes.find((s) => s.id === id); ui.sel = id; drawList(); drawScene(); player.onScene(); player.jumpToScene();
    listEl.querySelector('.scene-item.active')?.scrollIntoView({ block: 'nearest' });
    if (sel) { try { const l = await api.post(epUrl(ep, `/scenes/${sel.id}/lock`)); locked = l.held === false ? null : sel.id; if (l.held === false) drawLockbar(l.by); } catch { /* egal */ } }
  }

  // ---------- Segmente ----------
  function addSegment(a, b) {
    if (!sel) return;
    const g = { in: +a.toFixed(2), out: +b.toFixed(2), notiz: '' };
    let pos = sel.segmente.findIndex((x) => x.in > g.in); if (pos < 0) pos = sel.segmente.length;
    sel.kommentar.forEach((k) => { if (k.segment != null && k.segment >= pos) k.segment += 1; });
    sel.segmente.splice(pos, 0, g);
    touch(); segs.redraw(); player.drawTimeline(); player.drawDialog(); drawPills();
    segs.focus(pos);
    toast(`Segment ${pos + 1} markiert (${(g.out - g.in).toFixed(1)} s). Jetzt Kommentar dazu schreiben.`, 'ok', 3200);
  }

  // ---------- Kopf der Szene ----------
  const lockbar = h('div'), banner = h('div'), pills = h('div', { class: 'row gap-s' });
  function drawLockbar(by) { lockbar.className = by ? 'lockbar' : ''; lockbar.replaceChildren(...(by ? [icon('lock'), ` ${by} bearbeitet diese Szene gerade. Änderungen können kollidieren.`] : [])); }
  function drawBanner() { banner.replaceChildren(); if (sel?.problems?.length) { banner.className = 'banner'; banner.style.marginBottom = '10px'; banner.append(icon('alert'), sel.problems.join(' · ')); } else banner.className = ''; }
  function drawPills() {
    pills.replaceChildren();
    const r = sel?.report; if (!r) return;
    pills.append(h('span', { class: `pill ${r.light === 'gruen' ? 'ok' : r.light === 'gelb' ? 'warn' : r.light === 'rot' ? 'bad' : ''}` }, `Serie ${fmtDur(r.series_s)}`), h('span', { class: 'chip' }, `Kommentar ${fmtDur(r.comment_s)}`), ...(r.montage ? [h('span', { class: 'chip accent' }, 'Montage')] : []));
  }
  const head = h('div', { class: 'scene-head' });
  function drawHead() {
    const s = sel; clear(head); if (!s) return;
    const title = h('input', { type: 'text', value: s.titel, placeholder: 'Szenentitel', class: 'scene-title', onInput: (e) => { s.titel = e.target.value; touch(); drawList(); } });
    const strandSel = h('select', { onChange: (e) => { s.strang = e.target.value; touch(); drawList(); } }, h('option', { value: '' }, 'ohne Strang'), S.data.strands.map((t) => h('option', { value: t.id, selected: s.strang === t.id }, t.name)));
    const statusSel = h('select', { onChange: (e) => { s.status = e.target.value; touch(); drawList(); } }, Object.entries(STATUS).map(([k, v]) => h('option', { value: k, selected: s.status === k }, v)));
    const standbild = h('select', { title: 'Standbild nach Segmenten mit Kommentar', onChange: (e) => { s.standbild = e.target.value; touch(); } }, [['ende', 'Standbild am Segmentende'], ['start', 'Standbild am Segmentanfang'], ['aus', 'Kein Standbild']].map(([k, v]) => h('option', { value: k, selected: s.standbild === k }, v)));
    const fix = h('label', { class: 'check', title: 'Diese Szene behält ihre Position im Ablauf, auch wenn Stränge umsortiert werden' }, h('input', { type: 'checkbox', checked: s.fixiert, onChange: (e) => { s.fixiert = e.target.checked; touch(); drawList(); } }), 'Position fixiert');
    const titleAi = S.settings._scads_key_present && S.settings.llm.enabled ? btn('', { icon: 'sparkle', kind: 'ghost', title: 'KI: Titel vorschlagen', onClick: async () => {
      try { const r = await busy('KI formuliert einen Titel …', api.post('/api/llm/scene-title', { text: s.kommentar.map((b) => b.text).join(' ') })); if (r.titel) { s.titel = r.titel; touch(); drawHead(); drawList(); } else toast('Kein Titelvorschlag erhalten.', 'info'); } catch (e) { toast(e.message, 'err'); } } }) : null;
    head.append(h('div', { class: 'row' }, h('div', { class: 'grow' }, title), titleAi,
      btn('', { icon: 'up', kind: 'ghost', title: 'Szene nach oben (Alt+Umschalt+↑)', onClick: () => moveTo(s.id, scenes.indexOf(sel) - 1) }),
      btn('', { icon: 'down', kind: 'ghost', title: 'Szene nach unten (Alt+Umschalt+↓)', onClick: () => moveTo(s.id, scenes.indexOf(sel) + 1) }),
      s.bereich ? null : btn('', { icon: 'trash', kind: 'ghost danger', title: 'Lose Szene löschen (rückgängig machbar)', onClick: () => removeScene(s) })),
    s.bereich ? h('div', { class: 'help scene-unit', style: { marginTop: '6px' } }, icon('info'), ` Szene ${s.nr || ''} · ${fmtTC(s.bereich[0])} – ${fmtTC(s.bereich[1])} (${(s.bereich[1] - s.bereich[0]).toFixed(0)} s) · Messeinheit der Szenenerkennung, wird nicht gelöscht. Ins Video kommen nur Segmente: ein Segment kann eine Szene sein, mehrere Szenen überspannen oder nur einen Teil ausmachen.`) : null,
    h('div', { class: 'row wrap meta-row', style: { marginTop: '8px' } }, strandSel, statusSel, standbild, fix, h('span', { class: 'grow' }), pills, stateEl));
    drawPills();
  }
  async function removeScene(s) {
    await api.del(epUrl(ep, `/scenes/${s.id}`));
    const idx = scenes.indexOf(s); scenes = scenes.filter((x) => x.id !== s.id); dirty = false;
    sel = scenes[Math.min(idx, scenes.length - 1)] || null; drawList(); drawScene(); player.onScene();
    const tt = h('div', { class: 'toast warn' }, `„${s.titel || s.id}“ gelöscht `, h('button', { class: 'btn sm', style: { marginLeft: '8px' }, onClick: async () => {
      tt.remove(); try { await api.post(epUrl(ep, `/scenes/${s.id}/restore`)); scenes = await api.get(epUrl(ep, '/scenes')); scenes.forEach(normalize); sel = scenes.find((x) => x.id === s.id); drawList(); drawScene(); player.onScene(); toast('Wiederhergestellt.', 'ok'); } catch (e) { toast(e.message, 'err'); } } }, 'Rückgängig'));
    $('#toasts').append(tt); setTimeout(() => tt.remove(), 12000);
  }

  // ---------- Szene zeichnen ----------
  let leftCol = null, rightCol = null;
  function drawScene() {
    clear(mainEl);
    if (!sel) { mainEl.append(empty('edit', 'Keine Szene gewählt', 'Wähle links eine Szene. Szenen sind Messeinheiten; ins Video kommen nur die Segmente, die du darin markierst.')); return; }
    drawHead(); drawBanner();
    leftCol = h('div', { class: 'ed-left' }, player.el);
    rightCol = h('div', { class: 'ed-right' }, segs.el);
    mainEl.append(lockbar, banner, head, h('div', { class: 'ed-cols' }, leftCol, rightCol));
    segs.redraw();
    mainEl.addEventListener('scroll', () => { ui.mainScroll = mainEl.scrollTop; }, { passive: true });
  }

  // ---------- Tastatur ----------
  const onKey = (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (dirty) save.now(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && sel?.segmente.length) { e.preventDefault(); const si = E.focusBlock?.segment ?? sel.segmente.length - 1; segs.addBlock(sel, si); return; }
    if (e.altKey && !e.shiftKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault(); const list = scenes.filter(matches), i = list.findIndex((x) => x.id === sel?.id), n = list[i + (e.key === 'ArrowDown' ? 1 : -1)]; if (n) select(n.id); return; }
    if (e.altKey && e.shiftKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && sel) { e.preventDefault(); moveTo(sel.id, scenes.indexOf(sel) + (e.key === 'ArrowDown' ? 1 : -1)); return; }
    if (typing || !player.video()) return;
    const k = e.key.toLowerCase(), v = player.video();
    if (k === ' ' || k === 'k') { e.preventDefault(); player.toggle(); }
    else if (k === 'i') player.markIn();
    else if (k === 'o') player.markOut();
    else if (k === 'j') player.seek(v.currentTime - 2);
    else if (k === 'l') player.seek(v.currentTime + 2);
    else if (k === 'arrowleft') player.step(e.shiftKey ? -10 : -1);
    else if (k === 'arrowright') player.step(e.shiftKey ? 10 : 1);
  };
  document.addEventListener('keydown', onKey);
  const beforeUnload = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
  window.addEventListener('beforeunload', beforeUnload);

  drawList(); drawScene(); player.onScene();
  E.onVideoReady = () => { if (!E._jumped) { E._jumped = true; player.jumpToScene(); } };
  requestAnimationFrame(() => { listEl.scrollTop = ui.listScroll || 0; mainEl.scrollTop = ui.mainScroll || 0; });
  hb = setInterval(() => { if (locked) api.post(epUrl(ep, `/scenes/${locked}/lock`)).catch(() => {}); }, 60000);
  if (sel) api.post(epUrl(ep, `/scenes/${sel.id}/lock`)).then((l) => { if (l.held !== false) locked = sel.id; else drawLockbar(l.by); }).catch(() => {});
  return () => {
    document.removeEventListener('keydown', onKey); window.removeEventListener('beforeunload', beforeUnload); main.style.overflow = '';
    clearInterval(hb); player.dispose();
    if (locked && sel) api.del(epUrl(ep, `/scenes/${locked}/lock`)).catch(() => {});
    if (dirty && sel && !blocked) api.put(epUrl(ep, `/scenes/${sel.id}${sel.geaendert_am ? '?base=' + encodeURIComponent(sel.geaendert_am) : ''}`), clean(sel)).catch(() => {});
  };
}
