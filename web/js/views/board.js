import { h, btn, empty, runJob, toast, fmtTC, parseTC, icon, debounce } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep, d = S.data, ref = refSource();
  let strands = d.strands.map((s) => ({ ...s }));
  const board = await api.get(epUrl(ep, '/board'));
  const detect = async () => {
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
  const laneHost = h('div', { class: 'col' });
  const info = h('span', { class: 'muted' });
  const shotCard = (s) => {
    const len = Math.round(s.end - s.start);
    const t0 = h('input', { type: 'text', value: fmtTC(s.start), style: { width: '78px' }, onChange: (e) => { const v = parseTC(e.target.value); if (v != null && v < s.end) s.start = v; persist(); drawLanes(); } });
    const t1 = h('input', { type: 'text', value: fmtTC(s.end), style: { width: '78px' }, onChange: (e) => { const v = parseTC(e.target.value); if (v != null && v > s.start) s.end = v; persist(); drawLanes(); } });
    const i = board.scenes.indexOf(s);
    return h('div', { class: 'shot', draggable: s.done ? 'false' : 'true', style: { opacity: s.done ? .45 : 1, cursor: s.done ? 'default' : 'grab' }, onDragstart: (e) => { e.dataTransfer.setData('text/plain', String(i)); } },
      s.thumb ? h('img', { src: epUrl(ep, `/thumb/${s.thumb}`), loading: 'lazy' }) : null,
      h('div', { style: { padding: '6px 8px' } }, h('div', { class: 'row gap-s' }, t0, t1), h('div', { class: 'row gap-s', style: { marginTop: '4px' } }, h('span', { class: 'help grow' }, s.done ? 'angelegt' : `${len} s`),
        s.done ? null : btn('', { size: 'sm', kind: 'ghost', icon: 'scissors', title: 'Teilen …', onClick: () => { const v = parseTC(prompt('Teilen bei (mm:ss.zz):', fmtTC((s.start + s.end) / 2)) || ''); if (v != null && v > s.start && v < s.end) { board.scenes.splice(i + 1, 0, { start: v, end: s.end, thumb: '', strang: s.strang, done: false }); s.end = v; persist(); drawLanes(); } } }),
        s.done || i === board.scenes.length - 1 ? null : btn('', { size: 'sm', kind: 'ghost', icon: 'link', title: 'Mit der nächsten Szene verbinden', onClick: () => { const n = board.scenes[i + 1]; s.end = n.end; board.scenes.splice(i + 1, 1); persist(); drawLanes(); } }),
        s.done ? null : btn('', { size: 'sm', kind: 'ghost', icon: 'x', title: 'Verwerfen', onClick: () => { board.scenes.splice(i, 1); persist(); drawLanes(); } }))));
  };
  const lane = (title, color, id) => {
    const cards = board.scenes.filter((s) => (s.strang || '') === id);
    const el = h('div', { class: 'lane', onDragover: (e) => { e.preventDefault(); el.classList.add('over'); }, onDragleave: () => el.classList.remove('over'),
      onDrop: (e) => { e.preventDefault(); el.classList.remove('over'); const s = board.scenes[+e.dataTransfer.getData('text/plain')]; if (s && !s.done) { s.strang = id; persist(); drawLanes(); } } },
    h('div', { class: 'lane-head' }, h('span', { class: 'swatch', style: { background: color } }), h('b', { class: 'grow' }, title), h('span', { class: 'badge' }, cards.length)),
    h('div', { class: 'strip' }, cards.length ? cards.map(shotCard) : [h('span', { class: 'help' }, id ? 'Vorschläge hierher ziehen' : 'Alle zugeordnet')]));
    return el;
  };
  const drawLanes = () => {
    laneHost.replaceChildren(lane('Nicht zugeordnet', 'var(--faint)', ''), ...strands.map((s) => lane(s.name, s.color, s.id)));
    const todo = board.scenes.filter((s) => s.strang && !s.done).length;
    info.textContent = `${board.scenes.length} Vorschläge · ${todo} zur Anlage bereit`;
  };
  const create = async () => {
    const todo = board.scenes.filter((s) => s.strang && !s.done);
    if (!todo.length) { toast('Ziehe Vorschläge zuerst in einen Strang.', 'warn'); return; }
    const body = todo.map((s) => ({ start: s.start, end: s.end, strang: s.strang, titel: `Szene ab ${fmtTC(s.start)}` }));
    try { const r = await api.post(epUrl(ep, '/board/create-scenes'), body); todo.forEach((s) => { s.done = true; }); await api.put(epUrl(ep, '/board'), { source: board.source || '', scenes: board.scenes }); toast(`${r.created.length} Szene(n) angelegt.`, 'ok'); drawLanes(); } catch (e) { toast(e.message, 'err'); }
  };
  drawLanes();
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Strang-Board'), h('p', {}, 'Die Episode wird automatisch in Szenenvorschläge geteilt. Ziehe die relevanten Vorschläge in den passenden Strang (Teilen/Verbinden/Zeiten anpassen möglich) und lege sie als Szenen an. Stränge (Handlungsorte) legst du hier fest.')), btn(board.scenes.length ? 'Neu erkennen' : 'Szenen erkennen', { kind: 'primary', icon: 'wand', onClick: detect })),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Stränge (Reihenfolge = Reihenfolge im Schnitt und im Word)'), btn('Strang +', { size: 'sm', icon: 'plus', onClick: () => { strands.push({ id: `st_${Date.now().toString(36)}`, name: 'Neuer Strang', color: '#5aa7ff', order: strands.length }); redrawStrands(); } }), btn('Speichern', { size: 'sm', kind: 'primary', onClick: saveStrands })), strandBox),
    board.scenes.length ? h('div', {}, h('div', { class: 'row', style: { marginBottom: '12px' } }, info, h('span', { class: 'grow' }), btn('Zugeordnete als Szenen anlegen', { kind: 'primary', icon: 'plus', onClick: create })), laneHost)
      : h('div', { class: 'card' }, empty('layers', 'Noch keine Szenenvorschläge', 'Starte die automatische Erkennung auf der Referenz-Episode.', btn('Erkennen', { kind: 'primary', onClick: detect })))));
}
