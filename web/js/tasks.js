// Aufgabenleiste: zeigt laufende und letzte Hintergrundaufträge (auch nach Seitenwechsel) mit Schritten, Teilzählern, Dauer und Restzeit.
import { h, icon, modal, toast } from './ui.js';
import { api } from './api.js';
import { fmtSpan, jobCard } from './progressui.js';

let host = null, jobs = [], seenDone = new Set(), timer = null, cards = new Map(), listEl = null;

export function mountTasks(el) { host = el; draw(); poll(); }

function draw() {
  if (!host) return;
  const run = jobs.filter((j) => j.status === 'laeuft');
  const err = jobs.filter((j) => j.status === 'fehler' && !seenDone.has(j.id));
  const j0 = run[0];
  const line1 = j0 ? (j0.step_name || j0.name).replace(/ – .*$/, '') : err.length ? `${err.length} Fehler` : 'Aufgaben';
  const line2 = j0 ? `${Math.round(j0.progress * 100)} %${j0.eta != null ? ` · noch ${fmtSpan(j0.eta)}` : ''}${run.length > 1 ? ` · +${run.length - 1} weitere` : ''}` : '';
  host.replaceChildren(h('button', { class: `nav tasks-nav ${err.length ? 'bad' : ''}`, onClick: open, title: j0 ? `${j0.name}: ${j0.step_name} – ${j0.detail || ''}` : 'Laufende und letzte Aufgaben mit Details' },
    run.length ? h('div', { class: 'spinner' }) : icon(err.length ? 'alert' : 'check'),
    h('div', { class: 'tasks-label' }, h('div', { class: 'tl-1' }, line1), line2 ? h('small', {}, line2) : null),
    j0 ? h('div', { class: 'pbar thin tasks-bar' }, h('i', { style: { width: `${Math.max(3, j0.progress * 100)}%` } })) : null));
}
async function poll() {
  try {
    const prev = new Map(jobs.map((j) => [j.id, j.status]));
    jobs = await api.get('/api/jobs');
    for (const j of jobs) {
      if (prev.get(j.id) === 'laeuft' && j.status === 'fehler') toast(`${j.name}: ${j.error}`, 'err');
      if (prev.get(j.id) === 'laeuft' && j.status === 'fertig') toast(`${j.name} – fertig in ${fmtSpan(j.elapsed)}`, 'ok', 3500);
    }
    draw(); refresh();
  } catch { /* Server kurz weg */ }
  clearTimeout(timer);
  timer = setTimeout(poll, jobs.some((j) => j.status === 'laeuft') ? 1000 : 5000);
}
export const pollNow = () => poll();

function refresh() {
  if (!listEl) return;
  const keep = new Set(jobs.map((j) => j.id));
  for (const [id, c] of cards) if (!keep.has(id)) { c.dispose(); c.remove(); cards.delete(id); }
  jobs.forEach((j, i) => {
    let c = cards.get(j.id);
    if (!c) { c = jobCard(j, { onCancel: () => api.post(`/api/jobs/${j.id}/cancel`).then(poll) }); c.classList.add('jc-boxed'); cards.set(j.id, c); }
    else c.update(j);
    if (listEl.children[i] !== c) listEl.insertBefore(c, listEl.children[i] || null);
  });
  if (!jobs.length && !listEl.querySelector('.help')) listEl.append(h('p', { class: 'help' }, 'Noch keine Aufgaben seit dem Start.'));
}
function open() {
  listEl = h('div', { class: 'col' });
  cards = new Map();
  refresh();
  jobs.forEach((j) => { if (j.status === 'fehler') seenDone.add(j.id); });
  modal({ title: 'Aufgaben', wide: true, body: listEl, onClose: () => { cards.forEach((c) => c.dispose()); cards = new Map(); listEl = null; draw(); } });
}
