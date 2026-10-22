// Szenen-Editor: Liste mit Längenampel, Player mit I/O-Tasten, Segmente, Kommentarblöcke, Autosave.
import { h, $, clear, btn, icon, toast, modal, field, confirmBox, fmtTC, parseTC, fmtDur, debounce, empty, lightLabel } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource, strandOf } from '../state.js';

const STATUS = { neu: 'Neu', skript_fertig: 'Skript fertig', aufgenommen: 'Aufgenommen', abgeglichen: 'Abgeglichen', veraltet: 'Veraltet' };

export async function render(main, ctx) {
  const ep = S.ep;
  let scenes = await api.get(epUrl(ep, '/scenes'));
  let strands = S.data.strands;
  const [assets, maps] = await Promise.all([api.get(epUrl(ep, '/assets')), api.get(epUrl(ep, '/maps'))]);
  let sel = scenes.find((s) => s.id === location.hash.split('?id=')[1]) || scenes[0] || null;
  let dirty = false, saving = false, video = null, locked = null, query = '', filt = '', focusBlock = 0;
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
      const q = sel.geaendert_am && !forceNext ? `?base=${encodeURIComponent(sel.geaendert_am)}` : '';
      forceNext = false;
      const { scene, report, locked_by_other, problems } = await api.put(epUrl(ep, `/scenes/${sel.id}${q}`), clean(sel));
      Object.assign(sel, { report, problems: problems || [], status: scene.status, geaendert_von: scene.geaendert_von, geaendert_am: scene.geaendert_am }); dirty = false;
      setState(`${locked_by_other ? `Achtung: ${locked_by_other} bearbeitet ebenfalls · ` : ''}Gespeichert ${new Date().toLocaleTimeString('de-DE')}`);
      drawList(); drawBanner(); drawRepOnly?.();
    } catch (e) {
      setState('Nicht gespeichert');
      if (e.status === 409) conflictDialog(e.message); else toast(e.message, 'err');
    } finally { saving = false; if (dirty) save(); }
  }, 700);
  let forceNext = false, drawBanner = () => {}, drawRepOnly = null;
  function conflictDialog(msg) {
    const stop = true;
    modal({ title: 'Szene wurde inzwischen geändert', body: h('p', {}, `${msg} Möchtest du deine Version trotzdem speichern (überschreibt die andere) oder die aktuelle Version laden (deine Änderungen an dieser Szene gehen verloren)?`),
      actions: [{ label: 'Aktuelle laden', onClick: async () => { dirty = false; scenes = await api.get(epUrl(ep, '/scenes')); sel = scenes.find((x) => x.id === sel.id) || scenes[0]; drawList(); drawScene(); } },
        { label: 'Meine speichern', kind: 'primary', onClick: () => { forceNext = true; dirty = true; save(); } }] });
    return stop;
  }
  const touch = () => { dirty = true; setState('Ungespeichert …'); save(); };
  const clean = (s) => { const { report, lock, problems, ...rest } = s; return rest; };

  const matches = (s) => {
    const q = query.trim().toLowerCase();
    if (q && !`${s.titel} ${(s.kommentar || []).map((k) => `${k.text} ${(k.stichpunkte || []).join(' ')}`).join(' ')}`.toLowerCase().includes(q)) return false;
    if (!filt) return true;
    if (filt === 'ohne_segment') return !s.segmente.length;
    if (filt === 'rot') return s.report?.light === 'rot';
    if (filt.startsWith('st:')) return s.strang === filt.slice(3);
    if (filt.startsWith('status:')) return s.status === filt.slice(7);
    return true;
  };
  let listBody = null;
  function drawList() {
    if (!listEl.firstChild) {
      const search = h('input', { type: 'search', placeholder: 'Suchen (Titel, Text) …', onInput: (e) => { query = e.target.value; drawList(); } });
      const fsel = h('select', { onChange: (e) => { filt = e.target.value; drawList(); } }, h('option', { value: '' }, 'Alle Szenen'), h('option', { value: 'ohne_segment' }, 'Ohne Segment'), h('option', { value: 'rot' }, 'Zu langes Segment'),
        ...strands.map((x) => h('option', { value: `st:${x.id}` }, `Strang: ${x.name}`)), ...Object.entries(STATUS).map(([k, v]) => h('option', { value: `status:${k}` }, `Status: ${v}`)));
      listEl.append(h('div', { class: 'scene-list-head' }, h('div', { class: 'row' }, h('b', { class: 'grow' }, 'Szenen'), h('span', { class: 'help', id: 'scene-count' }), btn('Neu', { size: 'sm', icon: 'plus', onClick: addScene })), h('div', { class: 'col gap-s', style: { marginTop: '8px' } }, search, fsel)));
      listBody = h('div'); listEl.append(listBody);
    }
    clear(listBody);
    const shown = scenes.filter(matches);
    $('#scene-count', listEl).textContent = shown.length === scenes.length ? `${scenes.length}` : `${shown.length} von ${scenes.length}`;
    shown.forEach((s) => {
      const i = scenes.indexOf(s);
      const st = strandOf(s.strang), light = s.report?.light || 'grau';
      const el = h('div', { class: `scene-item ${sel?.id === s.id ? 'active' : ''}`, draggable: 'true', style: { borderLeftColor: st?.color || 'transparent' },
        onClick: () => select(s.id),
        onDragstart: (e) => { e.dataTransfer.setData('text/plain', s.id); },
        onDragover: (e) => { e.preventDefault(); el.classList.add('dragover'); }, onDragleave: () => el.classList.remove('dragover'),
        onDrop: async (e) => { e.preventDefault(); el.classList.remove('dragover'); const from = e.dataTransfer.getData('text/plain'); if (from && from !== s.id) await move(from, s.id); } },
      h('span', { class: 'no', title: s.ausgabe && s.ausgabe !== i + 1 ? `In Word/Rohschnitt Szene ${s.ausgabe} (nach Strang sortiert)` : '' }, String(s.ausgabe || i + 1).padStart(2, '0')),
      h('div', { class: 'grow' }, h('div', { class: 't' }, s.titel || '(ohne Titel)'), h('small', {}, h('span', { class: `dot ${light}`, title: lightLabel[light] || 'kein Material' }), st ? st.name : 'ohne Strang', '·', STATUS[s.status] || s.status, s.fixiert ? icon('lock') : null,
        s.lock && s.lock.user !== S.settings.user ? h('span', { class: 'chip' }, `${s.lock.user}`) : null)));
      listBody.append(el);
    });
    if (!scenes.length) listBody.append(empty('edit', 'Keine Szenen', 'Lege eine Szene an oder importiere ein Word-Skript.'));
    else if (!shown.length) listBody.append(h('p', { class: 'help', style: { padding: '14px' } }, 'Keine Szene passt zum Filter.'));
  }
  async function moveTo(id, index) {
    const ids = scenes.map((s) => s.id).filter((x) => x !== id); ids.splice(Math.max(0, Math.min(ids.length, index)), 0, id);
    await api.post(epUrl(ep, '/scenes-reorder'), { order: ids }); scenes = await api.get(epUrl(ep, '/scenes')); sel = scenes.find((s) => s.id === sel?.id) || sel; drawList();
  }
  async function move(from, to) {
    const ids = scenes.map((s) => s.id), fi = ids.indexOf(from), ti = ids.indexOf(to); ids.splice(fi, 1); ids.splice(fi < ti ? ti : ti, 0, from);
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


  function anchorDialog(b) {
    const isB = b.modus === 'stichpunkte';
    const items = [...assets.map((a) => ({ key: a.id, kind: 'asset', label: `${a.id} ${a.title || a.path.split('/').pop()}` })), ...maps.map((m) => ({ key: m.id, kind: 'karte', label: `${m.id} ${m.titel || ''} (Karte)` }))];
    const rows = (b.anker || []).map((a) => ({ ...a }));
    const words = (b.text || '').trim().split(/\s+/);
    const list = h('div', { class: 'col' });
    const draw = () => list.replaceChildren(...(rows.length ? rows.map((a, i) => {
      const cur = a.asset || a.karte;
      const pos = (k, label) => field(label, h('input', { type: 'number', min: 1, value: a[k] == null ? '' : a[k] + 1, onInput: (e) => { a[k] = e.target.value === '' ? null : Math.max(0, +e.target.value - 1); if (k === 'von' && !isB) hint.textContent = words[a.von] ? `ab „${words[a.von]}“` : ''; } }));
      const hint = h('span', { class: 'help' }, !isB && words[a.von] ? `ab „${words[a.von]}“` : '');
      return h('div', { class: 'card tight col' }, h('div', { class: 'row' }, h('select', { onChange: (e) => { const it = items.find((x) => x.key === e.target.value); delete a.asset; delete a.karte; a[it.kind] = it.key; } }, items.map((it) => h('option', { value: it.key, selected: it.key === cur }, it.label))), btn('', { icon: 'trash', kind: 'ghost', onClick: () => { rows.splice(i, 1); draw(); } })),
        h('div', { class: 'row' }, pos('von', isB ? 'Ab Stichpunkt' : 'Ab Wort Nr.'), pos('bis', isB ? 'Bis Stichpunkt (leer = Ende)' : 'Bis Wort Nr. (leer = Ende)'), field('Layout', h('select', { onChange: (e) => { a.layout = e.target.value; } }, [['einzel', 'Einzeln'], ['doppel_links', 'Doppelbild links'], ['doppel_rechts', 'Doppelbild rechts']].map(([k, l]) => h('option', { value: k, selected: a.layout === k }, l))))), hint);
    }) : [h('p', { class: 'help' }, items.length ? 'Noch nichts zugeordnet. Das Bild erscheint ab der gewählten Stelle im Kommentar.' : 'Zuerst unter „Bilder“ oder „Karten“ etwas zur Folge hinzufügen.')]));
    draw();
    modal({ title: 'Bilder & Karten zuordnen', body: h('div', { class: 'col' }, list, btn('Zuordnung hinzufügen', { icon: 'plus', disabled: !items.length, onClick: () => { const it = items[0]; rows.push({ [it.kind]: it.key, von: 0, bis: null, layout: 'einzel', einheit: isB ? 'stichpunkt' : 'wort' }); draw(); } })),
      actions: [{ label: 'Abbrechen' }, { label: 'Übernehmen', kind: 'primary', onClick: () => { b.anker = rows.map((a) => ({ ...a, einheit: isB ? 'stichpunkt' : 'wort' })); touch(); drawScene(); } }] });
  }

  async function removeScene(s) {
    await api.del(epUrl(ep, `/scenes/${s.id}`));
    const idx = scenes.indexOf(s); scenes = scenes.filter((x) => x.id !== s.id); dirty = false;
    sel = scenes[Math.min(idx, scenes.length - 1)] || null; drawList(); drawScene();
    const tt = h('div', { class: 'toast warn' }, `„${s.titel || s.id}“ gelöscht `, h('button', { class: 'btn sm', style: { marginLeft: '8px' }, onClick: async () => {
      tt.remove(); try { await api.post(epUrl(ep, `/scenes/${s.id}/restore`)); scenes = await api.get(epUrl(ep, '/scenes')); sel = scenes.find((x) => x.id === s.id); drawList(); drawScene(); toast('Wiederhergestellt.', 'ok'); } catch (e) { toast(e.message, 'err'); } } }, 'Rückgängig'));
    $('#toasts').append(tt); setTimeout(() => tt.remove(), 12000);
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
    const drawRep = () => { const r = s.report; clear(rep); if (r) rep.append(h('span', { class: `pill ${r.light === 'gruen' ? 'ok' : r.light === 'gelb' ? 'warn' : r.light === 'rot' ? 'bad' : ''}` }, `Serie ${fmtDur(r.series_s)}`), h('span', { class: 'chip' }, `Kommentar ${fmtDur(r.comment_s)}`), ...(r.montage ? [h('span', { class: 'chip accent' }, 'Montage')] : [])); };
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
        const ta = h('textarea', { rows: 5, onFocus: () => { focusBlock = i; }, placeholder: isB ? 'Ein Stichpunkt pro Zeile – wird frei ausformuliert gesprochen' : 'Gesprochener Text …',
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
        h('div', { class: 'block-foot' }, icon('image'), (b.anker || []).length ? (b.anker || []).map((a) => h('span', { class: 'chip accent' }, `${a.asset || a.karte} · ${a.einheit === 'stichpunkt' ? 'Punkt ' + (a.von + 1) : 'Wort ' + (a.von + 1)}`)) : h('span', { class: 'muted' }, 'Keine Bilder/Karten'), h('span', { class: 'grow' }), btn('Bilder & Karten …', { size: 'sm', onClick: () => anchorDialog(b) }))));
      });
      blocks.append(btn('Kommentarblock hinzufügen', { icon: 'plus', onClick: () => { s.kommentar.push({ sprecher: s.kommentar.at(-1)?.sprecher === 'philipp' ? 'danny' : 'philipp', modus: 'text', text: '', stichpunkte: [], gesprochen: '', anker: [] }); touch(); drawBlocks(); } }));
    }
    const banner = h('div');
    drawBanner = () => { clear(banner); if (s.problems?.length) { banner.className = 'banner'; banner.style.marginBottom = '12px'; banner.append(icon('alert'), s.problems.join(' · ')); } else { banner.className = ''; } };
    drawBanner();
    const player = buildPlayer(s, redraw);
    drawSegs(); drawBlocks();
    mainEl.append(...[
      lockedBy ? h('div', { class: 'lockbar' }, icon('lock'), ` ${lockedBy} bearbeitet diese Szene gerade. Änderungen können kollidieren.`) : null,
      banner,
      h('div', { class: 'row', style: { marginBottom: '14px' } }, h('div', { class: 'grow' }, title), btn('', { icon: 'up', kind: 'ghost', title: 'Szene nach oben (Alt+Umschalt+↑)', onClick: () => moveTo(s.id, scenes.indexOf(sel) - 1) }),
        btn('', { icon: 'down', kind: 'ghost', title: 'Szene nach unten (Alt+Umschalt+↓)', onClick: () => moveTo(s.id, scenes.indexOf(sel) + 1) }),
        btn('', { icon: 'trash', kind: 'ghost danger', title: 'Szene löschen (rückgängig machbar)', onClick: () => removeScene(s) })),
      h('div', { class: 'row wrap meta-row', style: { marginBottom: '14px' } }, strandSel, statusSel, standbild, fix, h('span', { class: 'grow' }), rep, stateEl),
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
      h('span', { class: 'help' }, h('span', { class: 'kbd' }, 'I'), ' ', h('span', { class: 'kbd' }, 'O'), ' ', h('span', { class: 'kbd' }, '←'), h('span', { class: 'kbd' }, '→'), ' ', h('span', { class: 'kbd' }, 'Leertaste'), ' ', h('span', { class: 'kbd' }, 'J'), h('span', { class: 'kbd' }, 'K'), h('span', { class: 'kbd' }, 'L'))));
    box._keys = { setIn, setOut, step };
    return box;
  }

  const onKey = (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (dirty) save.now(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && sel) { e.preventDefault(); sel.kommentar.push({ sprecher: sel.kommentar.at(-1)?.sprecher === 'philipp' ? 'danny' : 'philipp', modus: 'text', text: '', stichpunkte: [], gesprochen: '', anker: [] }); touch(); drawScene(); const tas = mainEl.querySelectorAll('.block textarea'); tas[tas.length - 1]?.focus(); return; }
    if (e.altKey && !e.shiftKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault(); const list = scenes.filter(matches), i = list.findIndex((x) => x.id === sel?.id), n = list[i + (e.key === 'ArrowDown' ? 1 : -1)]; if (n) select(n.id); return; }
    if (e.altKey && e.shiftKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && sel) { e.preventDefault(); moveTo(sel.id, scenes.indexOf(sel) + (e.key === 'ArrowDown' ? 1 : -1)); return; }
    if (e.altKey && (e.key === '1' || e.key === '2') && sel?.kommentar[focusBlock]) { e.preventDefault(); sel.kommentar[focusBlock].sprecher = e.key === '1' ? 'philipp' : 'danny'; touch(); const f = focusBlock; drawScene(); mainEl.querySelectorAll('.block textarea')[f]?.focus(); return; }
    if (!video || typing) return;
    const k = e.key.toLowerCase();
    if (k === ' ' || k === 'k') { e.preventDefault(); video.paused ? video.play() : video.pause(); }
    else if (k === 'i') $('.player-bar button[title^="In"]')?.click();
    else if (k === 'o') $('.player-bar button[title^="Out"]')?.click();
    else if (k === 'j') video.currentTime = Math.max(0, video.currentTime - 2);
    else if (k === 'l') video.currentTime += 2;
    else if (k === 'arrowleft') { video.pause(); video.currentTime -= (e.shiftKey ? 10 : 1) / (ref.fps || 24); }
    else if (k === 'arrowright') { video.pause(); video.currentTime += (e.shiftKey ? 10 : 1) / (ref.fps || 24); }
  };
  const beforeUnload = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
  window.addEventListener('beforeunload', beforeUnload);
  document.addEventListener('keydown', onKey);
  drawList(); drawScene();
  if (sel) api.post(epUrl(ep, `/scenes/${sel.id}/lock`)).then((l) => { if (l.held !== false) locked = sel.id; else drawScene(l.by); }).catch(() => {});
  return () => {
    document.removeEventListener('keydown', onKey); window.removeEventListener('beforeunload', beforeUnload); main.style.overflow = '';
    if (locked && sel) api.del(epUrl(ep, `/scenes/${locked}/lock`)).catch(() => {});
    if (dirty && sel) api.put(epUrl(ep, `/scenes/${sel.id}`), clean(sel)).catch(() => {});
  };
}
