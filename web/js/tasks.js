// Aufgabenleiste: zeigt laufende und letzte Hintergrundaufträge (auch nach Seitenwechsel), mit Abbrechen und Fehlerdetails.
import { h, icon, modal, toast, btn } from './ui.js';
import { api } from './api.js';

let host = null, jobs = [], seenDone = new Set(), timer = null;

export function mountTasks(el) { host = el; poll(); }

function summary() {
  const run = jobs.filter((j) => j.status === 'laeuft');
  const err = jobs.filter((j) => j.status === 'fehler' && !seenDone.has(j.id));
  return { run, err };
}
function draw() {
  if (!host) return;
  const { run, err } = summary();
  host.replaceChildren(h('button', { class: `nav ${err.length ? 'bad' : ''}`, onClick: open, title: 'Laufende und letzte Aufgaben' },
    run.length ? h('div', { class: 'spinner' }) : icon(err.length ? 'alert' : 'check'),
    h('span', {}, run.length ? `${run.length} Aufgabe${run.length > 1 ? 'n' : ''} läuft${run.length ? ` (${Math.round(run[0].progress * 100)} %)` : ''}` : err.length ? `${err.length} Fehler` : 'Aufgaben')));
}
async function poll() {
  try {
    const prev = new Map(jobs.map((j) => [j.id, j.status]));
    jobs = await api.get('/api/jobs');
    for (const j of jobs) if (prev.get(j.id) === 'laeuft' && j.status === 'fehler') toast(`${j.name}: ${j.error}`, 'err');
    draw(); refreshOpen?.();
  } catch { /* Server kurz weg */ }
  clearTimeout(timer);
  timer = setTimeout(poll, jobs.some((j) => j.status === 'laeuft') ? 1500 : 5000);
}
export const pollNow = () => poll();

let refreshOpen = null;
function open() {
  const list = h('div', { class: 'col' });
  const fill = () => {
    list.replaceChildren(...(jobs.length ? jobs.map((j) => h('div', { class: 'card tight col gap-s' },
      h('div', { class: 'row' }, h('b', { class: 'grow' }, j.name), h('span', { class: `pill ${j.status === 'fertig' ? 'ok' : j.status === 'fehler' ? 'bad' : j.status === 'laeuft' ? 'warn' : ''}` }, { laeuft: 'läuft', fertig: 'fertig', fehler: 'Fehler', abgebrochen: 'abgebrochen' }[j.status] || j.status),
        j.status === 'laeuft' ? btn('Abbrechen', { size: 'sm', onClick: async () => { await api.post(`/api/jobs/${j.id}/cancel`); poll(); } }) : null),
      j.status === 'laeuft' ? h('div', { class: 'bar' }, h('i', { style: { width: `${Math.max(2, j.progress * 100)}%` } })) : null,
      j.error && j.status === 'fehler' ? h('div', { class: 'row' }, h('span', { class: 'grow', style: { color: 'var(--bad)', userSelect: 'text' } }, j.error), btn('Kopieren', { size: 'sm', icon: 'copy', onClick: () => { navigator.clipboard?.writeText(`${j.name}: ${j.error}`); toast('Kopiert.', 'ok', 1500); } })) : null)) : [h('p', { class: 'help' }, 'Noch keine Aufgaben seit dem Start.')]));
  };
  fill(); refreshOpen = fill;
  jobs.forEach((j) => { if (j.status === 'fehler') seenDone.add(j.id); });
  modal({ title: 'Aufgaben', body: list, onClose: () => { refreshOpen = null; draw(); } });
}
