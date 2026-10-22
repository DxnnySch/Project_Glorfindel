// Szenen-Editor: Liste mit Längenampel, Player mit I/O-Tasten, Segmente, Kommentarblöcke, Autosave.
import { h, $, clear, btn, icon, toast, confirmBox, fmtTC, parseTC, fmtDur, debounce, empty, lightLabel } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource, strandOf } from '../state.js';

const STATUS = { neu: 'Neu', skript_fertig: 'Skript fertig', aufgenommen: 'Aufgenommen', abgeglichen: 'Abgeglichen', veraltet: 'Veraltet' };

export async function render(main, ctx) {
  const ep = S.ep;
  let scenes = await api.get(epUrl(ep, '/scenes'));
  let strands = S.data.strands;
  let sel = scenes.find((s) => s.id === location.hash.split('?id=')[1]) || scenes[0] || null;
  let dirty = false, saving = false, video = null, locked = null;
  const ref = refSource();
  const listEl = h('div', { class: 'scene-list' }), mainEl = h('div', { class: 'editor-main' });
  main.append(h('div', { class: 'editor' }, listEl, mainEl));
  main.style.overflow = 'hidden';

  const stateEl = h('span', { class: 'savestate' });
  const setState = (t) => { stateEl.textContent = t; };
  const save = debounce(async () => {
    if (!sel || saving) return;
    saving = true; setState('Speichert …');
    try {
      const { scene, report, locked_by_other } = await api.put(epUrl(ep, `/scenes/${sel.id}`), clean(sel));
      Object.assign(sel, scene, { report }); dirty = false; setState(locked_by_other ? `Gespeichert (Achtung: ${locked_by_other} bearbeitet ebenfalls)` : 'Gespeichert');
      drawList();
    } catch (e) { setState('Fehler beim Speichern'); toast(e.message, 'err'); } finally { saving = false; if (dirty) save(); }
  }, 700);
  const touch = () => { dirty = true; setState('Ungespeichert …'); save(); };
  const clean = (s) => { const { report, lock, problems, ...rest } = s; return rest; };

  function drawList() {
    clear(listEl);
    listEl.append(h('div', { class: 'scene-list-head' }, h('div', { class: 'row' }, h('b', { class: 'grow' }, 'Szenen'), btn('Neu', { size: 'sm', icon: 'plus', onClick: addScene })),
      h('div', { class: 'help', style: { marginTop: '6px' } }, `${scenes.length} Szenen · Ziehen zum Sortieren`)));
    scenes.forEach((s, i) => {
      const st = strandOf(s.strang), light = s.report?.light || 'grau';
      const el = h('div', { class: `scene-item ${sel?.id === s.id ? 'active' : ''}`, draggable: 'true', style: { borderLeftColor: st?.color || 'transparent' },
        onClick: () => select(s.id),
        onDragstart: (e) => { e.dataTransfer.setData('text/plain', s.id); },
        onDragover: (e) => { e.preventDefault(); el.classList.add('dragover'); }, onDragleave: () => el.classList.remove('dragover'),
        onDrop: async (e) => { e.preventDefault(); el.classList.remove('dragover'); const from = e.dataTransfer.getData('text/plain'); if (from && from !== s.id) await move(from, s.id); } },
      h('span', { class: 'no' }, String(i + 1).padStart(2, '0')),
      h('div', { class: 'grow' }, h('div', { class: 't' }, s.titel || '(ohne Titel)'), h('small', {}, h('span', { class: `dot ${light}`, title: lightLabel[light] || '' }), st ? st.name : 'ohne Strang', '·', STATUS[s.status] || s.status, s.fixiert ? icon('lock') : null,
        s.lock && s.lock.user !== S.settings.user ? h('span', { class: 'chip' }, `${s.lock.user}`) : null)));
      listEl.append(el);
    });
    if (!scenes.length) listEl.append(empty('edit', 'Keine Szenen', 'Lege eine Szene an oder importiere ein Word-Skript.'));
  }
  async function move(from, to) {
    const ids = scenes.map((s) => s.id); ids.splice(ids.indexOf(from), 1); ids.splice(ids.indexOf(to), 0, from);
    await api.post(epUrl(ep, '/scenes-reorder'), { order: ids }); scenes = await api.get(epUrl(ep, '/scenes')); sel = scenes.find((s) => s.id === sel?.id) || sel; drawList();
  }
  async function addScene() {
    const strand = sel?.strang || strands[0]?.id || '';
    await api.post(epUrl(ep, '/scenes'), { titel: 'Neue Szene', strang: strand, kommentar: [{ sprecher: 'philipp', text: '' }] });
    scenes = await api.get(epUrl(ep, '/scenes')); select(scenes[scenes.length - 1].id);
  }
  async function select(id) {
    if (dirty && sel) { try { await api.put(epUrl(ep, `/scenes/${sel.id}`), clean(sel)); dirty = false; } catch (e) { toast(e.message, 'err'); } }
    if (sel && locked === sel.id) { api.del(epUrl(ep, `/scenes/${sel.id}/lock`)).catch(() => {}); locked = null; }
    sel = scenes.find((s) => s.id === id); drawList(); drawScene();
    if (sel) { try { const l = await api.post(epUrl(ep, `/scenes/${sel.id}/lock`)); locked = l.held === false ? null : sel.id; if (l.held === false) drawScene(l.by); } catch { /* egal */ } }
  }

  function drawScene(lockedBy) {
    clear(mainEl); video = null;
    if (!sel) { mainEl.append(empty('edit', 'Keine Szene gewählt', 'Wähle links eine Szene oder lege eine neue an.', btn('Neue Szene', { kind: 'primary', onClick: addScene }))); return; }
    const s = sel;
    const title = h('input', { type: 'text', value: s.titel, placeholder: 'Szenentitel', style: { fontSize: '18px', fontWeight: 650 }, onInput: (e) => { s.titel = e.target.value; touch(); } });
    const strandSel = h('select', { onChange: (e) => { s.strang = e.target.value; touch(); drawList(); } }, h('option', { value: '' }, 'ohne Strang'), strands.map((t) => h('option', { value: t.id, selected: s.strang === t.id }, t.name)));
    const statusSel = h('select', { onChange: (e) => { s.status = e.target.value; touch(); drawList(); } }, Object.entries(STATUS).map(([k, v]) => h('option', { value: k, selected: s.status === k }, v)));
    const standbild = h('select', { onChange: (e) => { s.standbild = e.target.value; touch(); } }, [['ende', 'Standbild am Ende'], ['start', 'Standbild am Anfang'], ['aus', 'Kein Standbild']].map(([k, v]) => h('option', { value: k, selected: s.standbild === k }, v)));
    const fix = h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: s.fixiert, onChange: (e) => { s.fixiert = e.target.checked; touch(); drawList(); } }), 'Dramaturgisch fixiert');
    const rep = h('div', { class: 'row gap-s' });
    const drawRep = () => { const r = s.report; clear(rep); if (r) rep.append(h('span', { class: `pill ${r.light === 'gruen' ? 'ok' : r.light === 'gelb' ? 'warn' : 'bad'}` }, `Serie ${fmtDur(r.series_s)}`), h('span', { class: 'chip' }, `Kommentar ${fmtDur(r.comment_s)}`), ...(r.montage ? [h('span', { class: 'chip accent' }, 'Montage')] : [])); };
    drawRep();
    const segBox = h('div'), blocks = h('div');
    const redraw = () => { drawSegs(); drawRep(); };
    function drawSegs() {
      clear(segBox);
      s.segmente.forEach((g, i) => {
        const light = s.report?.segments?.[i]?.light || 'grau';
        const tin = h('input', { type: 'text', value: fmtTC(g.in), onChange: (e) => { const v = parseTC(e.target.value); if (v != null) { g.in = v; touch(); } e.target.value = fmtTC(g.in); drawSegs(); } });
        const tout = h('input', { type: 'text', value: fmtTC(g.out), onChange: (e) => { const v = parseTC(e.target.value); if (v != null) { g.out = v; touch(); } e.target.value = fmtTC(g.out); drawSegs(); } });
        segBox.append(h('div', { class: 'seg-row' }, h('span', { class: `dot ${light}` }), tin, tout, h('span', { class: 'mono muted' }, `${Math.max(0, g.out - g.in).toFixed(1)} s`),
          btn('', { icon: 'play', kind: 'ghost', size: 'sm', title: 'Segment abspielen', onClick: () => { if (video) { video.currentTime = g.in; video.play(); } } }),
          btn('', { icon: 'trash', kind: 'ghost', size: 'sm', onClick: () => { s.segmente.splice(i, 1); touch(); drawSegs(); } })));
      });
      if (!s.segmente.length) segBox.append(h('p', { class: 'help' }, 'Noch kein Segment. Im Player mit „I“ und „O“ Anfang und Ende setzen.'));
    }
    function drawBlocks() {
      clear(blocks);
      s.kommentar.forEach((b, i) => {
        const isB = b.modus === 'stichpunkte';
        const ta = h('textarea', { rows: 5, placeholder: isB ? 'Ein Stichpunkt pro Zeile – wird frei ausformuliert gesprochen' : 'Gesprochener Text …',
          value: isB ? b.stichpunkte.join('\n') : b.text, onInput: (e) => { if (isB) b.stichpunkte = e.target.value.split('\n').map((l) => l.replace(/^\s*[-•*]\s*/, '').trim()).filter(Boolean); else b.text = e.target.value; words(); touch(); } });
        const info = h('span', { class: 'help' });
        const words = () => { const n = isB ? b.stichpunkte.length : (b.text.trim() ? b.text.trim().split(/\s+/).length : 0); info.textContent = isB ? `${n} Stichpunkte` : `${n} Wörter · ca. ${(n / S.settings.thresholds.words_per_second).toFixed(0)} s`; };
        words();
        const spk = h('div', { class: 'seg' }, ['philipp', 'danny'].map((k) => h('button', { class: b.sprecher === k ? 'on' : '', onClick: () => { b.sprecher = k; touch(); drawBlocks(); } }, k === 'philipp' ? 'Philipp' : 'Danny')));
        const mode = h('div', { class: 'seg' }, [['text', 'Text'], ['stichpunkte', 'Stichpunkte']].map(([k, l]) => h('button', { class: b.modus === k ? 'on' : '', onClick: () => {
          if (k === b.modus) return;
          if (k === 'stichpunkte') { b.stichpunkte = b.text.split(/\n|(?<=[.!?])\s+/).map((x) => x.trim()).filter(Boolean); b.text = ''; } else { b.text = b.stichpunkte.join(' '); b.stichpunkte = []; }
          b.modus = k; touch(); drawBlocks(); } }, l)));
        blocks.append(h('div', { class: `block ${b.sprecher}` }, h('div', { class: 'block-head' }, spk, mode, h('span', { class: 'grow' }), info,
          btn('', { icon: 'trash', kind: 'ghost', size: 'sm', onClick: async () => { if (await confirmBox('Block löschen?', 'Dieser Kommentarblock wird entfernt.', 'Löschen', true)) { s.kommentar.splice(i, 1); touch(); drawBlocks(); } } })),
        ta, b.gesprochen ? h('div', { class: 'block-foot' }, icon('mic'), h('span', { class: 'muted' }, 'Gesprochen: '), h('span', {}, b.gesprochen)) : null,
        (b.anker || []).length ? h('div', { class: 'block-foot' }, icon('image'), `${b.anker.length} Bild-/Kartenanker`) : null));
      });
      blocks.append(btn('Kommentarblock hinzufügen', { icon: 'plus', onClick: () => { s.kommentar.push({ sprecher: s.kommentar.at(-1)?.sprecher === 'philipp' ? 'danny' : 'philipp', modus: 'text', text: '', stichpunkte: [], gesprochen: '', anker: [] }); touch(); drawBlocks(); } }));
    }
    const player = buildPlayer(s, redraw);
    drawSegs(); drawBlocks();
    mainEl.append(...[
      lockedBy ? h('div', { class: 'lockbar' }, icon('lock'), ` ${lockedBy} bearbeitet diese Szene gerade. Änderungen können kollidieren.`) : null,
      s.problems?.length ? h('div', { class: 'banner', style: { marginBottom: '12px' } }, icon('alert'), s.problems.join(' · ')) : null,
      h('div', { class: 'row', style: { marginBottom: '14px' } }, h('div', { class: 'grow' }, title), btn('', { icon: 'trash', kind: 'ghost danger', title: 'Szene löschen', onClick: async () => {
        if (await confirmBox('Szene löschen?', `„${s.titel || s.id}“ wird gelöscht.`, 'Löschen', true)) { await api.del(epUrl(ep, `/scenes/${s.id}`)); scenes = scenes.filter((x) => x.id !== s.id); sel = scenes[0] || null; drawList(); drawScene(); } } })),
      h('div', { class: 'row wrap', style: { marginBottom: '14px' } }, strandSel, statusSel, standbild, fix, h('span', { class: 'grow' }), rep, stateEl),
      h('div', { class: 'editor-cols' },
        h('div', { class: 'col' }, player, h('div', { class: 'card tight' }, h('div', { class: 'card-head' }, h('h3', {}, 'Segmente'), h('span', { class: 'grow' }), btn('Segment +', { size: 'sm', icon: 'plus', onClick: () => { const t = video?.currentTime || 0; s.segmente.push({ in: t, out: t + 5 }); touch(); drawSegs(); } })), segBox)),
        h('div', {}, h('div', { class: 'card-head' }, h('h3', {}, 'Kommentar')), blocks))].filter(Boolean));
    // Standardmäßig Titel fokussieren bei neuer Szene
    if (s.titel === 'Neue Szene') { title.focus(); title.select(); }
  }

  function buildPlayer(s, redraw) {
    const box = h('div', { class: 'player' });
    if (!ref) { box.append(empty('film', 'Keine Referenz', 'Importiere zuerst die Referenz-Episode unter „Quellen“.')); return box; }
    video = h('video', { src: epUrl(ep, `/media/${ref.id}`), preload: 'metadata' });
    const tc = h('span', { class: 'tc' }, '00:00.00');
    video.addEventListener('timeupdate', () => { tc.textContent = fmtTC(video.currentTime, ref.fps || 24); });
    video.addEventListener('error', async () => {
      const ready = (await api.get(epUrl(ep, `/sources/${ref.id}/proxy-status`)).catch(() => ({ ready: false }))).ready;
      if (ready) { clear(box).append(h('div', { style: { padding: '30px', textAlign: 'center' } }, h('p', { class: 'muted' }, 'Das Video kann in diesem Browser nicht abgespielt werden. Bitte Chrome oder Edge verwenden.'))); return; }
      clear(box).append(h('div', { style: { padding: '30px', textAlign: 'center' } }, h('p', { class: 'muted' }, 'Für die Vorschau fehlt der Proxy.'), btn('Proxy jetzt erzeugen', { kind: 'primary', onClick: async () => {
        const { runJob } = await import('../ui.js'); await runJob('Proxy wird erzeugt …', () => api.post(epUrl(ep, `/sources/${ref.id}/proxy`))); drawScene(); } })));
    }, { once: true });
    const fps = ref.fps || 24, step = (n) => { video.pause(); video.currentTime = Math.max(0, video.currentTime + n / fps); };
    const setIn = () => { const g = s.segmente.at(-1); if (g && g.out <= g.in + 0.01) g.in = video.currentTime; else s.segmente.push({ in: video.currentTime, out: video.currentTime + 3 }); touch(); redraw(); };
    const setOut = () => { const g = s.segmente.at(-1); if (g) { g.out = video.currentTime; } else s.segmente.push({ in: Math.max(0, video.currentTime - 3), out: video.currentTime }); touch(); redraw(); };
    const marks = h('div', { class: 'scrub' });
    const drawMarks = () => { clear(marks); const dur = video.duration || ref.duration; s.segmente.forEach((g) => marks.append(h('div', { class: 'seg-mark', style: { left: `${g.in / dur * 100}%`, width: `${Math.max(0.3, (g.out - g.in) / dur * 100)}%` } }))); marks.append(h('div', { class: 'seg-mark', style: { left: `${video.currentTime / dur * 100}%`, width: '2px', background: 'var(--text)' } })); };
    video.addEventListener('timeupdate', drawMarks); video.addEventListener('loadedmetadata', drawMarks);
    marks.addEventListener('click', (e) => { const r = marks.getBoundingClientRect(); video.currentTime = (e.clientX - r.left) / r.width * (video.duration || ref.duration); });
    box.append(video, marks, h('div', { class: 'player-bar' },
      btn('', { icon: 'stepb', kind: 'ghost', size: 'sm', title: 'Ein Bild zurück (←)', onClick: () => step(-1) }), btn('', { icon: 'play', size: 'sm', title: 'Abspielen/Pause (Leertaste)', onClick: () => (video.paused ? video.play() : video.pause()) }), btn('', { icon: 'step', kind: 'ghost', size: 'sm', title: 'Ein Bild vor (→)', onClick: () => step(1) }), tc,
      btn('I', { size: 'sm', title: 'In setzen (I)', onClick: setIn }), btn('O', { size: 'sm', title: 'Out setzen (O)', onClick: setOut }),
      h('span', { class: 'help' }, h('span', { class: 'kbd' }, 'I'), ' ', h('span', { class: 'kbd' }, 'O'), ' ', h('span', { class: 'kbd' }, '←'), h('span', { class: 'kbd' }, '→'), ' ', h('span', { class: 'kbd' }, 'Leertaste'))));
    box._keys = { setIn, setOut, step };
    return box;
  }

  const onKey = (e) => {
    if (!video || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); video.paused ? video.play() : video.pause(); }
    else if (k === 'i') $('.player-bar button[title^="In"]')?.click();
    else if (k === 'o') $('.player-bar button[title^="Out"]')?.click();
    else if (k === 'arrowleft') { video.pause(); video.currentTime -= (e.shiftKey ? 10 : 1) / (ref.fps || 24); }
    else if (k === 'arrowright') { video.pause(); video.currentTime += (e.shiftKey ? 10 : 1) / (ref.fps || 24); }
  };
  document.addEventListener('keydown', onKey);
  drawList(); drawScene();
  if (sel) api.post(epUrl(ep, `/scenes/${sel.id}/lock`)).then((l) => { if (l.held !== false) locked = sel.id; else drawScene(l.by); }).catch(() => {});
  return () => {
    document.removeEventListener('keydown', onKey); main.style.overflow = '';
    if (locked && sel) api.del(epUrl(ep, `/scenes/${locked}/lock`)).catch(() => {});
    if (dirty && sel) api.put(epUrl(ep, `/scenes/${sel.id}`), clean(sel)).catch(() => {});
  };
}
