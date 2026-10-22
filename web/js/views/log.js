// Protokoll + OneDrive-Konfliktkopien zusammenführen.
import { h, btn, toast, modal, icon, empty } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

const sceneText = (s) => [`Titel: ${s.titel || ''}`, `Segmente: ${(s.segmente || []).map((g) => `${g.in.toFixed(1)}–${g.out.toFixed(1)}`).join(', ') || '–'}`,
  ...(s.kommentar || []).map((b, i) => `Block ${i + 1} (${b.sprecher}): ${b.modus === 'stichpunkte' ? (b.stichpunkte || []).map((x) => '• ' + x).join(' ') : b.text}`)].join('\n');

export async function render(main, ctx) {
  const ep = S.ep;
  const [log, conflicts] = await Promise.all([api.get(epUrl(ep, '/log?limit=200')), api.get(epUrl(ep, '/conflicts'))]);
  const resolve = (c) => {
    const col = (title, s, keep) => h('div', { class: 'card col' }, h('h2', {}, title), h('pre', { style: { whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'var(--mono)', fontSize: '12.5px' } }, sceneText(s || {})),
      btn('Diese Version behalten', { kind: 'primary', onClick: async () => { try { await api.post(epUrl(ep, '/conflicts/resolve'), { original: c.original, other: c.copy, keep }); toast('Konflikt gelöst.', 'ok'); m.close(); ctx.refresh(); } catch (e) { toast(e.message, 'err'); } } }));
    const m = modal({ title: `Konflikt: ${c.original.split(/[\\/]/).pop()} (Kopie von ${c.pc})`, wide: true, body: h('div', { class: 'grid g2' }, col('Aktuell', c.a, 'original'), col(`Kopie von ${c.pc}`, c.b, 'copy')) });
  };
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Protokoll'), h('p', {}, 'Wer hat wann was geändert – und OneDrive-Konflikte, wenn zwei gleichzeitig dieselbe Szene bearbeitet haben.'))),
    conflicts.length ? h('div', { class: 'card', style: { marginBottom: '16px', borderColor: 'var(--bad)' } }, h('div', { class: 'card-head' }, icon('alert'), h('h2', {}, `${conflicts.length} Konflikt(e)`)),
      conflicts.map((c) => h('div', { class: 'row', style: { padding: '6px 0' } }, h('b', { class: 'grow' }, c.original.split(/[\\/]/).pop()), h('span', { class: 'muted' }, `Kopie von ${c.pc}`), btn('Vergleichen & lösen', { size: 'sm', onClick: () => resolve(c) })))) : null,
    h('div', { class: 'card' }, log.length ? h('table', {}, h('thead', {}, h('tr', {}, ['Wann', 'Wer', 'Was'].map((x) => h('th', {}, x)))), h('tbody', {}, log.map((l) => h('tr', {}, h('td', { class: 'mono muted' }, new Date(l.wann).toLocaleString('de-DE')), h('td', {}, l.wer), h('td', {}, l.was))))) : empty('clock', 'Noch keine Einträge', 'Änderungen erscheinen hier automatisch.'))));
}
