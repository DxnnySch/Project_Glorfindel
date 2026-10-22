import { h, btn, empty, runJob, toast, modal, field, icon, debounce } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main) {
  const ep = S.ep;
  let assets = await api.get(epUrl(ep, '/assets'));
  const grid = h('div', { class: 'thumbs' }), res = h('div', { class: 'thumbs' }), mine = h('div', { class: 'thumbs' });
  const q = h('input', { type: 'search', placeholder: 'Bildbibliothek durchsuchen (Name, Tags, Titel) …' });
  const addAsset = async (body) => { try { const a = await api.post(epUrl(ep, '/assets'), body); assets.push(a); drawMine(); toast('Zur Folge hinzugefügt.', 'ok'); edit(a); } catch (e) { toast(e.message, 'err'); } };
  const search = debounce(async () => {
    try { const r = await api.get(`/api/images/search?q=${encodeURIComponent(q.value)}`);
      res.replaceChildren(...(r.length ? r.map((i) => h('div', { class: 'thumb', style: { cursor: 'pointer' }, title: 'Zur Folge hinzufügen', onClick: () => addAsset({ path: i.path }) },
        h('img', { src: `/api/images/thumb?path=${encodeURIComponent(i.path)}`, loading: 'lazy', style: { width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block' } }), h('div', { style: { padding: '6px 8px', fontSize: '12px' } }, i.title || i.path.split('/').pop()))) : [h('p', { class: 'help' }, 'Keine Treffer. Ist der Bildindex aufgebaut?')]));
    } catch (e) { toast(e.message, 'err'); }
  }, 300);
  q.addEventListener('input', search);
  function edit(a) {
    const f = { ...a };
    const inp = (k, label) => field(label, h('input', { type: 'text', value: f[k] || '', onInput: (e) => { f[k] = e.target.value; } }));
    modal({ title: 'Bild bearbeiten', body: h('div', { class: 'col' }, h('img', { src: epUrl(ep, `/asset-file?path=${encodeURIComponent(a.path)}`), style: { maxHeight: '240px', objectFit: 'contain', background: '#000', borderRadius: '8px' } }),
      inp('title', 'Titel'), inp('credit', 'Credit (Künstler)'), inp('credit_link', 'Link zur Quelle'),
      h('div', { class: 'row' }, field('Konturfarbe', h('input', { type: 'color', value: f.contour_color || '#888888', onInput: (e) => { f.contour_color = e.target.value; } })), h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: f.zoom, onChange: (e) => { f.zoom = e.target.checked; } }), 'Langsamer Zoom'))),
    actions: [{ label: 'Abbrechen' }, { label: 'Speichern', kind: 'primary', onClick: async () => { try { Object.assign(a, await api.put(epUrl(ep, `/assets/${a.id}`), f)); drawMine(); } catch (e) { toast(e.message, 'err'); return false; } } }] });
  }
  function drawMine() {
    mine.replaceChildren(...(assets.length ? assets.map((a) => h('div', { class: 'thumb', style: { cursor: 'pointer' }, onClick: () => edit(a) }, h('img', { src: epUrl(ep, `/asset-file?path=${encodeURIComponent(a.path)}`), loading: 'lazy', style: { width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block', borderBottom: `3px solid ${a.contour_color || 'transparent'}` } }),
      h('div', { style: { padding: '6px 8px', fontSize: '12px' } }, h('b', {}, a.id), ' ', a.title || ''), h('div', { class: 'help', style: { padding: '0 8px 8px' } }, a.credit || 'Credit fehlt'))) : [h('p', { class: 'help' }, 'Noch keine Bilder in dieser Folge.')]));
  }
  const url = h('input', { type: 'text', placeholder: 'https://… (Bildadresse einer Webseite)' });
  const index = async () => { try { const r = await runJob('Bildindex wird aufgebaut …', () => api.post('/api/images/index')); toast(`Index fertig: ${r.added} neu, ${r.unchanged} unverändert.`, 'ok'); search(); } catch (e) { toast(e.message, 'err'); } };
  drawMine(); search();
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Bilder'), h('p', {}, 'Aus der Bibliothek oder dem Web in die Folge übernehmen. Credit und Konturfarbe werden vorbelegt.')), btn('Bildindex aktualisieren', { icon: 'refresh', onClick: index })),
    h('h3', { style: { margin: '0 0 10px' } }, 'In dieser Folge'), mine,
    h('div', { class: 'card', style: { margin: '22px 0 14px' } }, h('div', { class: 'row' }, url, btn('Aus Web holen', { icon: 'download', onClick: () => url.value && addAsset({ url: url.value }) }))),
    h('h3', { style: { margin: '0 0 10px' } }, 'Bibliothek'), h('div', { style: { marginBottom: '12px' } }, q), res));
}
