import { h, btn, empty, runJob, toast, fmtTC, icon } from '../ui.js';
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
  const saveStrands = () => api.put(epUrl(ep, '/strands'), strands.map((s, i) => ({ ...s, order: i }))).then(() => toast('Stränge gespeichert.', 'ok')).catch((e) => toast(e.message, 'err'));
  const used = (id) => d.scenes.filter((x) => x.strang === id).length;
  const strandRow = (s, i) => h('div', { class: 'row' }, h('input', { type: 'color', value: s.color, onInput: (e) => { s.color = e.target.value; } }), h('input', { type: 'text', value: s.name, onInput: (e) => { s.name = e.target.value; } }),
    h('span', { class: 'help', style: { minWidth: '70px' } }, `${used(s.id)} Szene(n)`),
    btn('', { icon: 'up', kind: 'ghost', title: 'Weiter nach oben (kommt früher im Schnitt)', disabled: i === 0, onClick: () => { [strands[i - 1], strands[i]] = [strands[i], strands[i - 1]]; redrawStrands(); } }),
    btn('', { icon: 'down', kind: 'ghost', title: 'Weiter nach unten', disabled: i === strands.length - 1, onClick: () => { [strands[i + 1], strands[i]] = [strands[i], strands[i + 1]]; redrawStrands(); } }),
    btn('', { icon: 'trash', kind: 'ghost', onClick: () => { if (used(s.id) && !confirm(`${used(s.id)} Szene(n) gehören zu diesem Strang und hätten danach keinen. Trotzdem löschen?`)) return; strands.splice(i, 1); redrawStrands(); } }));
  const strandBox = h('div', { class: 'col gap-s' });
  const redrawStrands = () => strandBox.replaceChildren(...strands.map(strandRow));
  redrawStrands();
  const picked = new Set();
  const grid = h('div', { class: 'thumbs' });
  const info = h('span', { class: 'muted' });
  const drawGrid = () => {
    grid.replaceChildren(...board.scenes.map((s, i) => h('div', { class: `thumb ${picked.has(i) ? 'sel' : ''}`, style: picked.has(i) ? { outline: '2px solid var(--accent)' } : null, onClick: () => { picked.has(i) ? picked.delete(i) : picked.add(i); drawGrid(); } },
      s.thumb ? h('img', { src: epUrl(ep, `/thumb/${s.thumb}`), loading: 'lazy', style: { width: '100%', display: 'block', aspectRatio: '16/9', objectFit: 'cover' } }) : null,
      h('div', { style: { padding: '8px 10px' } }, h('b', { class: 'mono' }, `${fmtTC(s.start)} – ${fmtTC(s.end)}`), h('div', { class: 'help' }, `${Math.round(s.end - s.start)} s`)))));
    info.textContent = `${picked.size} ausgewählt`;
  };
  const strandSel = h('select', {}, h('option', { value: '' }, 'Strang für neue Szenen'), strands.map((s) => h('option', { value: s.id }, s.name)));
  const create = async () => {
    if (!picked.size) { toast('Nichts ausgewählt.', 'warn'); return; }
    const body = [...picked].sort((a, b) => a - b).map((i) => ({ start: board.scenes[i].start, end: board.scenes[i].end, strang: strandSel.value, titel: `Szene ab ${fmtTC(board.scenes[i].start)}` }));
    try { const r = await api.post(epUrl(ep, '/board/create-scenes'), body); toast(`${r.created.length} Szene(n) angelegt.`, 'ok'); ctx.go('editor'); } catch (e) { toast(e.message, 'err'); }
  };
  drawGrid();
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Strang-Board'), h('p', {}, 'Die Episode wird automatisch in Szenenvorschläge geteilt. Wähle die relevanten aus und lege sie als Szenen an. Stränge (Handlungsorte) legst du hier fest.')), btn(board.scenes.length ? 'Neu erkennen' : 'Szenen erkennen', { kind: 'primary', icon: 'wand', onClick: detect })),
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Stränge (Reihenfolge = Reihenfolge im Schnitt und im Word)'), btn('Strang +', { size: 'sm', icon: 'plus', onClick: () => { strands.push({ id: `st_${Date.now().toString(36)}`, name: 'Neuer Strang', color: '#5aa7ff', order: strands.length }); redrawStrands(); } }), btn('Speichern', { size: 'sm', kind: 'primary', onClick: saveStrands })), strandBox),
    board.scenes.length ? h('div', {}, h('div', { class: 'row', style: { marginBottom: '12px' } }, info, h('span', { class: 'grow' }), strandSel, btn('Als Szenen anlegen', { kind: 'primary', icon: 'plus', onClick: create })), grid)
      : h('div', { class: 'card' }, empty('layers', 'Noch keine Szenenvorschläge', 'Starte die automatische Erkennung auf der Referenz-Episode.', btn('Erkennen', { kind: 'primary', onClick: detect })))));
}
