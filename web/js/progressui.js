// Detaillierte Fortschrittsanzeige für Hintergrundaufträge: Gesamtbalken, aktueller Schritt, Teilzähler, Dauer, Restzeit, Schrittliste.
import { h, icon } from './ui.js';

export const fmtSpan = (s) => {
  if (s == null || isNaN(s)) return '–';
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  if (s < 3600) return `${m}:${String(r).padStart(2, '0')} min`;
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}:${String(r).padStart(2, '0')} h`;
};
const clock = (ts) => new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
const STATUS = { laeuft: 'läuft', fertig: 'fertig', fehler: 'Fehler', abgebrochen: 'abgebrochen' };

/** Baut eine Auftragskarte, die sich per `update(job)` aktualisiert; Dauer/Restzeit laufen lokal zwischen den Abfragen weiter. */
export function jobCard(initial, { onCancel, compact = false, stepsOpen = true } = {}) {
  const el = {};
  const root = h('div', { class: 'jc' },
    h('div', { class: 'row jc-head' }, el.spin = h('div', { class: 'spinner' }), el.title = h('b', { class: 'grow' }), el.pill = h('span', { class: 'pill' }), onCancel ? el.cancel = h('button', { class: 'btn sm', onClick: onCancel }, 'Abbrechen') : null),
    el.bar = h('div', { class: 'pbar' }, el.fill = h('i'), el.pct = h('span', { class: 'pbar-t' })),
    el.facts = h('div', { class: 'jc-facts' }),
    el.now = h('div', { class: 'jc-now' }),
    el.subbar = h('div', { class: 'pbar thin' }, el.subfill = h('i')),
    el.detail = h('div', { class: 'jc-detail' }),
    compact ? null : el.list = h('div', { class: 'jc-steps' }),
    el.err = h('div', { class: 'jc-err' }));
  let job = initial, got = Date.now();
  const factsEl = (label, value, cls = '') => h('span', { class: `jc-fact ${cls}` }, h('small', {}, label), h('b', {}, value));
  function render() {
    const j = job, running = j.status === 'laeuft';
    const dt = running ? (Date.now() - got) / 1000 : 0;
    const elapsed = (j.elapsed || 0) + dt;
    const eta = j.eta != null ? Math.max(0, j.eta - dt) : null;
    const f = j.progress || 0;
    el.title.textContent = j.name;
    el.pill.textContent = j.cancelling ? 'bricht ab …' : STATUS[j.status] || j.status;
    el.pill.className = `pill ${j.status === 'fertig' ? 'ok' : j.status === 'fehler' ? 'bad' : j.status === 'laeuft' ? 'warn' : ''}`;
    el.spin.style.display = running ? '' : 'none';
    if (el.cancel) el.cancel.style.display = running && !j.cancelling ? '' : 'none';
    el.root_cls = running ? 'running' : j.status;
    root.className = `jc ${running ? 'running' : j.status}${root.classList.contains('open') ? ' open' : ''}`;
    el.fill.style.width = `${Math.max(running ? 2 : 0, f * 100)}%`;
    el.pct.textContent = `${Math.round(f * 100)} %`;
    el.facts.replaceChildren(...[
      factsEl(running ? 'Läuft seit' : 'Dauer', fmtSpan(elapsed)),
      running ? factsEl('Noch ca.', eta != null ? fmtSpan(eta) : 'wird berechnet …', eta == null ? 'faint' : '') : null,
      running && eta != null ? factsEl('Fertig gegen', clock(Date.now() + eta * 1000)) : null,
      j.step_total > 1 || (j.steps || []).length ? factsEl('Schritt', `${Math.min(j.step_index || 0, j.step_total)} von ${j.step_total}`) : null].filter(Boolean));
    const sub = j.sub;
    const stepName = j.step_name;
    el.now.replaceChildren(...(running && stepName ? [h('b', {}, stepName), j.step_elapsed != null ? h('span', { class: 'faint' }, ` · seit ${fmtSpan(j.step_elapsed + dt)}${j.step_eta != null ? ` · Schritt noch ca. ${fmtSpan(Math.max(0, j.step_eta - dt))}` : ''}`) : null].filter(Boolean) : []));
    const sf = j.step_fraction;
    el.subbar.style.display = running && sf != null && (j.steps || []).length ? '' : 'none';
    el.subfill.style.width = `${Math.max(2, (sf || 0) * 100)}%`;
    const parts = [];
    if (running && sub && sub.total) parts.push(h('b', {}, `${Math.min(Math.round(sub.done), sub.total)} von ${sub.total}${sub.unit ? ' ' + sub.unit : ''}`), ` (${Math.round((sf || 0) * 100)} %)`, j.detail ? ' · ' : '');
    if (running && j.detail) parts.push(j.detail);
    el.detail.replaceChildren(...parts);
    if (el.list) {
      el.list.replaceChildren(...(j.steps || []).map((s, i) => h('div', { class: `jc-step ${s.status}` },
        s.status === 'läuft' ? h('div', { class: 'spinner sm' }) : icon(s.status === 'fertig' ? 'check' : s.status === 'fehler' ? 'alert' : s.status === 'übersprungen' ? 'x' : 'clock'),
        h('span', { class: 'grow' }, `${i + 1}. ${s.name}`, s.detail && s.status !== 'wartet' && s.status !== 'läuft' ? h('small', {}, ` – ${s.detail}`) : null),
        s.seconds != null && s.status !== 'wartet' ? h('small', { class: 'mono' }, s.status === 'läuft' ? `${fmtSpan(s.seconds + dt)}…` : fmtSpan(s.seconds)) : null)));
    }
    el.err.textContent = j.status === 'fehler' ? j.error : '';
    el.err.style.display = j.status === 'fehler' ? '' : 'none';
  }
  let seen = false;
  const timer = setInterval(() => { if (root.isConnected) seen = true; else if (seen) { clearInterval(timer); return; } else return; render(); }, 300);
  root.update = (j) => { job = j; got = Date.now(); render(); };
  root.dispose = () => clearInterval(timer);
  root.querySelector('.jc-head').addEventListener('click', (e) => { if (e.target.closest('button')) return; root.classList.toggle('open'); });
  render();
  return root;
}
