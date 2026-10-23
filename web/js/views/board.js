import { h, btn, empty, runJob, toast, fmtTC, parseTC, icon, debounce, modal, remember } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep, d = S.data, ref = refSource();
  let strands = d.strands.map((s) => ({ ...s }));
  const board = await api.get(epUrl(ep, '/board'));
  const ui = remember(`${ep.season}-${ep.episode}:board`, { sel: [] });
  const selected = new Set((ui.sel || []).filter((i) => i < board.scenes.length));
  let lastClicked = null;
  const detect = async () => {
    if (board.scenes.some((s) => s.strang || s.done) && !confirm('Die bisherigen Vorschläge und Strang-Zuordnungen werden verworfen (bereits angelegte Szenen bleiben). Neu erkennen?')) return;
    if (!ref) { toast('Zuerst eine Referenz importieren.', 'warn'); return; }
    try { await runJob('Szenen werden erkannt (das dauert einige Minuten) …', () => api.post(epUrl(ep, '/board/detect'), { source: ref.id })); ctx.refresh(); } catch (e) { toast(e.message, 'err'); }
  };
  const saveStrands = () => api.put(epUrl(ep, '/strands'), strands.map((s, i) => ({ ...s, order: i }))).then(() => { drawLanes?.(); toast('Stränge gespeichert.', 'ok'); }).catch((e) => toast(e.message, 'err'));
  const used = (id) => d.scenes.filter((x) => x.strang === id).length;
  const strandRow = (s, i) => h('div', { class: 'row' }, h('input', { type: 'color', value: s.color, onInput: (e) => { s.color = e.target.value; } }), h('input', { type: 'text', value: s.name, onInput: (e) => { s.name = e.target.value; } }),
    h('span', { class: 'help', style: { minWidth: '70px' } }, `${used(s.id)} Szene(n)`),
    btn('', { icon: 'up', kind: 'ghost', title: 'Weiter nach oben (kommt früher im Schnitt)', disabled: i === 0, onClick: () => { [strands[i - 1], strands[i]] = [strands[i], strands[i - 1]]; redrawStrands(); } }),
    btn('', { icon: 'down', kind: 'ghost', title: 'Weiter nach unten', disabled: i === strands.length - 1, onClick: () => { [strands[i + 1], strands[i]] = [strands[i], strands[i + 1]]; redrawStrands(); } }),
    btn('', { icon: 'trash', kind: 'ghost', onClick: () => { if (used(s.id) && !confirm(`${used(s.id)} Szene(n) gehören zu diesem Strang und hätten danach keinen. Trotzdem löschen?`)) return; strands.splice(i, 1); redrawStrands(); } }));
  const strandBox = h('div', { class: 'col gap-s' });
  const redrawStrands = () => strandBox.replaceChildren(...strands.map(strandRow));
  redrawStrands();
  const persist = debounce(() => api.put(epUrl(ep, '/board'), { source: board.source || '', scenes: board.scenes }).catch((e) => toast(e.message, 'err')), 600);
  const laneHost = h('div', { class: 'col' }), toolbar = h('div', { class: 'board-bar card tight' });
  const info = h('span', { class: 'muted' });
  const saveSel = () => { ui.sel = [...selected]; };

  // ---- Vorschau-Player für einen Vorschlag ----
  function preview(startIdx) {
    let idx = startIdx, loop = true;
    const video = h('video', { src: epUrl(ep, `/media/${ref?.id}`), controls: true, style: { width: '100%', background: '#000', borderRadius: '8px', maxHeight: '58vh' } });
    const title = h('b', {}), tcl = h('span', { class: 'tc' }, '');
    const cur = () => board.scenes[idx];
    const go = (i) => { idx = Math.max(0, Math.min(board.scenes.length - 1, i)); const s = cur(); title.textContent = `Vorschlag ${idx + 1} von ${board.scenes.length}: ${fmtTC(s.start)} – ${fmtTC(s.end)} (${Math.round(s.end - s.start)} s)`; video.currentTime = s.start; video.play().catch(() => {}); };
    video.addEventListener('timeupdate', () => { const s = cur(); tcl.textContent = `${fmtTC(video.currentTime)}`; if (video.currentTime >= s.end - 0.05) { if (loop) video.currentTime = s.start; else video.pause(); } });
    video.addEventListener('error', () => { video.replaceWith(h('div', { class: 'player-msg' }, 'Das Video kann nicht abgespielt werden. Proxy erzeugen (Quellen) und Chrome/Edge verwenden.')); }, { once: true });
    video.addEventListener('loadedmetadata', () => go(idx), { once: true });
    const strandBtns = strands.map((st) => btn(st.name, { size: 'sm', onClick: () => { cur().strang = st.id; persist(); drawLanes(); toast(`→ ${st.name}`, 'ok', 1200); } }));
    const m = modal({ title: 'Szene ansehen', wide: true, onClose: () => video.pause(),
      body: h('div', { class: 'col' }, video, h('div', { class: 'row' }, title, h('span', { class: 'grow' }), tcl),
        h('div', { class: 'row wrap' }, btn('Vorherige', { size: 'sm', icon: 'stepb', onClick: () => go(idx - 1) }), btn('Nächste', { size: 'sm', icon: 'step', onClick: () => go(idx + 1) }),
          h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: true, onChange: (e) => { loop = e.target.checked; } }), 'Wiederholen'), h('span', { class: 'grow' }), h('span', { class: 'help' }, 'Zuordnen zu:'), ...strandBtns)) });
    go(idx);
    return m;
  }

  // ---- Auswahl ----
  function clickCard(i, e) {
    if (board.scenes[i].done) return;
    if (e.shiftKey && lastClicked != null) { const [a, b] = [Math.min(lastClicked, i), Math.max(lastClicked, i)]; for (let k = a; k <= b; k++) if (!board.scenes[k].done) selected.add(k); }
    else if (e.ctrlKey || e.metaKey) { selected.has(i) ? selected.delete(i) : selected.add(i); lastClicked = i; }
    else { if (selected.size === 1 && selected.has(i)) selected.clear(); else { selected.clear(); selected.add(i); } lastClicked = i; }
    saveSel(); drawLanes();
  }
  const assign = (strangId) => { selected.forEach((i) => { board.scenes[i].strang = strangId; }); persist(); drawLanes(); toast(`${selected.size} Vorschlag/Vorschläge zugeordnet.`, 'ok', 1500); };
  function mergeSelected() {
    const idx = [...selected].sort((a, b) => a - b);
    if (idx.length < 2) return;
    const first = board.scenes[idx[0]], last = board.scenes[idx.at(-1)];
    first.end = Math.max(...idx.map((i) => board.scenes[i].end)); first.start = Math.min(...idx.map((i) => board.scenes[i].start));
    for (let k = idx.length - 1; k >= 1; k--) board.scenes.splice(idx[k], 1);
    void last; selected.clear(); selected.add(idx[0]); saveSel(); persist(); drawLanes();
  }
  function drawToolbar() {
    const n = selected.size;
    toolbar.replaceChildren(
      h('span', { class: n ? 'chip accent' : 'help' }, n ? `${n} ausgewählt` : 'Klick = auswählen · Strg+Klick = mehrere · Umschalt+Klick = von … bis'),
      h('span', { class: 'grow' }),
      ...(n ? [h('span', { class: 'help' }, 'Zuordnen zu:'), ...strands.map((s) => h('button', { class: 'chip', style: { cursor: 'pointer', borderColor: s.color }, onClick: () => assign(s.id) }, h('i', { class: 'dot', style: { background: s.color } }), s.name)),
        h('button', { class: 'chip', style: { cursor: 'pointer' }, onClick: () => assign('') }, 'Nicht zugeordnet'),
        btn('Ansehen', { size: 'sm', icon: 'play', onClick: () => preview(Math.min(...selected)) }),
        n > 1 ? btn('Zu einer Szene verbinden', { size: 'sm', icon: 'link', onClick: mergeSelected }) : null,
        btn('', { size: 'sm', kind: 'ghost', icon: 'x', title: 'Auswahl aufheben', onClick: () => { selected.clear(); saveSel(); drawLanes(); } })] : []));
  }

  const shotCard = (s) => {
    const len = Math.round(s.end - s.start), i = board.scenes.indexOf(s);
    const t0 = h('input', { type: 'text', value: fmtTC(s.start), style: { width: '78px' }, onClick: (e) => e.stopPropagation(), onChange: (e) => { const v = parseTC(e.target.value); if (v != null && v < s.end) s.start = v; persist(); drawLanes(); } });
    const t1 = h('input', { type: 'text', value: fmtTC(s.end), style: { width: '78px' }, onClick: (e) => e.stopPropagation(), onChange: (e) => { const v = parseTC(e.target.value); if (v != null && v > s.start) s.end = v; persist(); drawLanes(); } });
    const on = selected.has(i);
    return h('div', { class: `shot ${on ? 'selected' : ''}`, draggable: s.done ? 'false' : 'true', style: { opacity: s.done ? .45 : 1, cursor: s.done ? 'default' : 'grab' },
      onClick: (e) => clickCard(i, e), onDblclick: () => preview(i),
      onDragstart: (e) => { if (!selected.has(i)) { selected.clear(); selected.add(i); saveSel(); } e.dataTransfer.setData('text/plain', JSON.stringify([...selected])); } },
    h('div', { class: 'shot-img' }, s.thumb ? h('img', { src: epUrl(ep, `/thumb/${s.thumb}`), loading: 'lazy' }) : null, h('span', { class: 'shot-len' }, s.done ? 'angelegt' : `${len} s`)),
    h('div', { style: { padding: '6px 8px' } }, h('div', { class: 'row gap-s' }, t0, t1), h('div', { class: 'row gap-s', style: { marginTop: '4px', justifyContent: 'space-between' } },
      btn('', { size: 'sm', kind: 'primary', icon: 'play', title: 'Ansehen (Doppelklick)', onClick: (e) => { e.stopPropagation(); preview(i); } }),
      s.done ? null : btn('', { size: 'sm', kind: 'ghost', icon: 'scissors', title: 'Teilen …', onClick: (e) => { e.stopPropagation(); const v = parseTC(prompt('Teilen bei (mm:ss.zz):', fmtTC((s.start + s.end) / 2)) || ''); if (v != null && v > s.start && v < s.end) { board.scenes.splice(i + 1, 0, { start: v, end: s.end, thumb: '', strang: s.strang, done: false }); s.end = v; selected.clear(); saveSel(); persist(); drawLanes(); } } }),
      s.done || i === board.scenes.length - 1 ? null : btn('', { size: 'sm', kind: 'ghost', icon: 'link', title: 'Mit der nächsten Szene verbinden', onClick: (e) => { e.stopPropagation(); const nx = board.scenes[i + 1]; s.end = nx.end; board.scenes.splice(i + 1, 1); selected.clear(); saveSel(); persist(); drawLanes(); } }),
      s.done ? null : btn('', { size: 'sm', kind: 'ghost', icon: 'x', title: 'Verwerfen', onClick: (e) => { e.stopPropagation(); board.scenes.splice(i, 1); selected.clear(); saveSel(); persist(); drawLanes(); } }))));
  };
  let dragStrand = null;
  const lane = (title, color, id) => {
    const cards = board.scenes.filter((s) => (s.strang || '') === id);
    const el = h('div', { class: 'lane', onDragover: (e) => { e.preventDefault(); el.classList.add('over'); }, onDragleave: () => el.classList.remove('over'),
      onDrop: (e) => {
        e.preventDefault(); el.classList.remove('over');
        if (dragStrand != null) { const from = strands.findIndex((x) => x.id === dragStrand), to = strands.findIndex((x) => x.id === id); dragStrand = null; if (from >= 0 && to >= 0 && from !== to) { const [m] = strands.splice(from, 1); strands.splice(to, 0, m); redrawStrands(); drawLanes(); saveStrands(); } return; }
        let idxs = []; try { idxs = JSON.parse(e.dataTransfer.getData('text/plain')); } catch { /* egal */ }
        idxs.forEach((k) => { if (board.scenes[k] && !board.scenes[k].done) board.scenes[k].strang = id; }); persist(); drawLanes();
      } },
    h('div', { class: 'lane-head', draggable: id ? 'true' : 'false', onDragstart: (e) => { dragStrand = id; e.dataTransfer.setData('text/plain', '[]'); e.stopPropagation(); }, title: id ? 'Strang ziehen, um die Reihenfolge zu ändern' : '' },
      id ? h('span', { class: 'faint', style: { cursor: 'grab' } }, '⋮⋮') : null, h('span', { class: 'swatch', style: { background: color } }), h('b', { class: 'grow' }, title), h('span', { class: 'badge' }, cards.length),
      id && cards.length > 1 ? btn('Alle wählen', { size: 'sm', kind: 'ghost', onClick: () => { cards.forEach((c) => selected.add(board.scenes.indexOf(c))); saveSel(); drawLanes(); } }) : null),
    h('div', { class: 'strip' }, cards.length ? cards.map(shotCard) : [h('span', { class: 'help' }, id ? 'Vorschläge hierher ziehen' : 'Alle zugeordnet')]));
    return el;
  };
  const drawLanes = () => {
    drawToolbar();
    laneHost.replaceChildren(lane('Nicht zugeordnet', 'var(--faint)', ''), ...strands.map((s) => lane(s.name, s.color, s.id)));
    const todo = board.scenes.filter((s) => s.strang && !s.done).length;
    info.textContent = `${board.scenes.length} Vorschläge · ${todo} zur Anlage bereit`;
  };
  const create = async () => {
    const todo = board.scenes.filter((s) => s.strang && !s.done);
    if (!todo.length) { toast('Ordne Vorschläge zuerst einem Strang zu.', 'warn'); return; }
    const body = todo.map((s) => ({ start: s.start, end: s.end, strang: s.strang, titel: `Szene ab ${fmtTC(s.start)}` }));
    try { const r = await api.post(epUrl(ep, '/board/create-scenes'), body); todo.forEach((s) => { s.done = true; }); selected.clear(); saveSel(); await api.put(epUrl(ep, '/board'), { source: board.source || '', scenes: board.scenes }); toast(`${r.created.length} Szene(n) angelegt – im Szenen-Editor markierst du jetzt die Segmente.`, 'ok'); drawLanes(); } catch (e) { toast(e.message, 'err'); }
  };
  drawLanes();
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Strang-Board'), h('p', {}, 'Die Episode wird automatisch in Szenenvorschläge geteilt. Sortiere die Vorschläge nach Strängen: mehrere mit Strg/Umschalt wählen, per Klick zuordnen oder ziehen, mit „Ansehen“ prüfen. Danach als Szenen anlegen. Szenen sind nur Messeinheiten (sie werden nicht gelöscht und kommen nicht automatisch ins Video); die Segmente markierst du frei im Szenen-Editor. Stränge (Handlungsorte) legst du hier fest.')), btn(board.scenes.length ? 'Neu erkennen' : 'Szenen erkennen', { kind: 'primary', icon: 'wand', onClick: detect })),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Stränge (Reihenfolge = Reihenfolge im Schnitt und im Word)'), btn('Strang +', { size: 'sm', icon: 'plus', onClick: () => { strands.push({ id: `st_${Date.now().toString(36)}`, name: 'Neuer Strang', color: '#5aa7ff', order: strands.length }); redrawStrands(); } }), btn('Speichern', { size: 'sm', kind: 'primary', onClick: saveStrands })), strandBox),
    board.scenes.length ? h('div', {}, toolbar, h('div', { class: 'row', style: { margin: '10px 0 12px' } }, info, h('span', { class: 'grow' }), btn('Zugeordnete als Szenen anlegen', { kind: 'primary', icon: 'plus', onClick: create })), laneHost)
      : h('div', { class: 'card' }, empty('layers', 'Noch keine Szenenvorschläge', 'Starte die automatische Erkennung auf der Referenz-Episode.', btn('Erkennen', { kind: 'primary', onClick: detect })))));
}
