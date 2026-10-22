// Kontrolle: Doppelansicht Referenz vs. Quelle (Frames + Differenz), Szenenprüfung, HQ-Conform.
import { h, btn, runJob, toast, fmtTC, parseTC, icon, empty } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep, ref = refSource(), others = S.data.sources.filter((s) => s.id !== ref?.id);
  if (!ref || !others.length) { main.append(h('div', { class: 'page' }, h('div', { class: 'page-head' }, h('h1', {}, 'Kontrolle')), h('div', { class: 'card' }, empty('compare', 'Zweite Quelle nötig', 'Importiere unter „Quellen“ eine weitere Fassung (HQ/Screener) und setze Ankerpunkte.', btn('Zu den Quellen', { kind: 'primary', onClick: () => ctx.go('sources') }))))); return; }
  let src = others[0];
  const srcSel = h('select', { onChange: (e) => { src = others.find((s) => s.id === e.target.value); show(); } }, others.map((s) => h('option', { value: s.id }, `${s.role}: ${s.path.split('/').pop()}`)));
  const t = h('input', { type: 'range', min: 0, max: ref.duration, step: 0.5, value: 0, style: { flex: 1 } });
  const tc = h('input', { type: 'text', value: fmtTC(0), style: { width: '110px' } });
  const imgA = h('img', { style: { width: '100%', display: 'block', background: '#000', aspectRatio: '16/9', objectFit: 'contain' } }), imgB = h('img', { style: { width: '100%', display: 'block', background: '#000', aspectRatio: '16/9', objectFit: 'contain' } });
  const imgD = h('img', { style: { width: '100%', display: 'block', background: '#000', aspectRatio: '16/9', objectFit: 'contain' } });
  const verdict = h('span', { class: 'pill' });
  const mode = h('div', { class: 'seg' }, [['dual', 'Nebeneinander'], ['diff', 'Differenz']].map(([k, l]) => h('button', { class: k === 'dual' ? 'on' : '', onClick: (e) => { [...e.target.parentNode.children].forEach((b) => b.classList.remove('on')); e.target.classList.add('on'); dualBox.classList.toggle('hidden', k !== 'dual'); diffBox.classList.toggle('hidden', k !== 'diff'); } }, l)));
  const dualBox = h('div', { class: 'dual' }, h('div', {}, h('h3', {}, 'Referenz'), imgA), h('div', {}, h('h3', {}, 'Quelle (über Zeitabbildung)'), imgB));
  const diffBox = h('div', { class: 'hidden' }, h('h3', {}, 'Differenz'), imgD);
  let pending = 0;
  async function show() {
    const my = ++pending, time = +t.value; tc.value = fmtTC(time);
    try {
      const r = await api.get(epUrl(ep, `/compare?a=${ref.id}&b=${src.id}&t=${time}`));
      if (my !== pending) return;
      const bust = `?_=${Date.now()}`;
      imgA.src = r.a + bust; imgB.src = r.b + bust; imgD.src = r.diff ? r.diff + bust : '';
      verdict.textContent = r.correlation == null ? (r.error || 'nicht vergleichbar') : `Übereinstimmung ${(r.correlation * 100).toFixed(0)} %`;
      verdict.className = `pill ${r.correlation == null ? 'warn' : r.uncertain ? 'bad' : 'ok'}`;
    } catch (e) { toast(e.message, 'err'); }
  }
  const go = (() => { let to; return () => { clearTimeout(to); to = setTimeout(show, 250); }; })();
  t.addEventListener('input', () => { tc.value = fmtTC(+t.value); go(); });
  tc.addEventListener('change', () => { const v = parseTC(tc.value); if (v != null) { t.value = v; show(); } });
  const checkBody = h('tbody');
  const check = async () => {
    try { const r = await runJobSync(); checkBody.replaceChildren(...r.map((x) => h('tr', {}, h('td', {}, h('b', {}, x.titel || x.scene)), h('td', {}, cell(x.A)), h('td', {}, cell(x.B)), h('td', {}, x.uncertain ? h('span', { class: 'pill bad' }, 'prüfen') : h('span', { class: 'pill ok' }, 'ok'))))); } catch (e) { toast(e.message, 'err'); }
  };
  const cell = (v) => (v == null ? '–' : `${Math.round(v * 100)} %`);
  async function runJobSync() { const box = h('span', { class: 'help' }, 'Prüfe …'); checkBody.replaceChildren(h('tr', {}, h('td', { colspan: 4 }, box))); return api.get(epUrl(ep, `/scene-check?source=${src.id}`)); }
  const codec = h('select', { title: 'Ausgabeformat' }, [['prores', 'ProRes 422 HQ'], ['dnxhr', 'DNxHR HQ'], ['h264', 'H.264 (Test)']].map(([v, l]) => h('option', { value: v }, l)));
  const conform = async () => {
    try { const r = await runJob('HQ-Conform läuft (kann lange dauern) …', () => api.post(epUrl(ep, '/conform'), { source: src.id, codec: codec.value, stills: true })); toast(`Fertig: ${r.file}`, 'ok', 9000); } catch (e) { toast(e.message, 'err'); }
  };
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Kontrolle'), h('p', {}, 'Prüft, ob die Zeitabbildung stimmt: gleiche Bildinhalte in Referenz und Quelle. Bei geringer Übereinstimmung Ankerpunkte nachbessern.')), srcSel, codec, btn('HQ-Conform', { icon: 'film', kind: 'primary', onClick: conform })),
    h('div', { class: 'card col' }, h('div', { class: 'row' }, tc, t, mode, verdict), dualBox, diffBox),
    h('div', { class: 'card', style: { marginTop: '16px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Szenenprüfung (Anfang/Ende jedes Segments)'), btn('Alle prüfen', { icon: 'check', onClick: check })),
      h('table', {}, h('thead', {}, h('tr', {}, ['Szene', 'Anfang', 'Ende', ''].map((x) => h('th', {}, x)))), checkBody))));
  show();
}
