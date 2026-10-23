import { h, btn, empty, runJob, toast, modal, field, icon, debounce, remember, thumbOfAsset } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main) {
  const ep = S.ep;
  const ui = remember(`${ep.season}-${ep.episode}:images`, { q: '' });
  let assets = await api.get(epUrl(ep, '/assets'));
  const grid = h('div', { class: 'thumbs' }), res = h('div', { class: 'thumbs' }), mine = h('div', { class: 'thumbs' });
  const q = h('input', { type: 'search', placeholder: 'Bildbibliothek durchsuchen (Name, Tags, Titel) …' });
  const addAsset = async (body) => { try { const a = await api.post(epUrl(ep, '/assets'), body); if (!assets.find((x) => x.id === a.id)) assets.push(a); drawMine(); toast('Zur Folge hinzugefügt.', 'ok'); edit(a); } catch (e) { toast(e.message, 'err'); } };
  const search = debounce(async () => {
    try { const r = await api.get(`/api/images/search?q=${encodeURIComponent(q.value)}`);
      res.replaceChildren(...(r.length ? r.map((i) => h('div', { class: 'thumb', style: { cursor: 'pointer', outline: assets.some((a) => a.path === i.path) ? '2px solid var(--ok)' : '' }, title: assets.some((a) => a.path === i.path) ? 'Schon in dieser Folge' : 'Zur Folge hinzufügen', onClick: () => (assets.some((a) => a.path === i.path) ? toast('Schon in dieser Folge.', 'info') : addAsset({ path: i.path })) },
        h('img', { src: `/api/images/thumb?path=${encodeURIComponent(i.path)}`, loading: 'lazy', style: { width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block' } }), h('div', { style: { padding: '6px 8px', fontSize: '12px' } }, assets.some((a) => a.path === i.path) ? '✔ ' : '', i.title || i.path.split('/').pop()))) : [h('p', { class: 'help' }, 'Keine Treffer. Ist der Bildindex aufgebaut?')]));
    } catch (e) { toast(e.message, 'err'); }
  }, 300);
  q.value = ui.q || '';
  q.addEventListener('input', () => { ui.q = q.value; search(); });
  function edit(a) {
    const f = { ...a };
    const inp = (k, label) => field(label, h('input', { type: 'text', value: f[k] || '', onInput: (e) => { f[k] = e.target.value; } }));
    modal({ title: 'Bild bearbeiten', body: h('div', { class: 'col' }, (/\.(mov|mp4|webm|m4v)$/i.test(a.path) ? h('video', { src: epUrl(ep, `/asset-file?path=${encodeURIComponent(a.path)}`), poster: thumbOfAsset(a), controls: true, loop: true, muted: true, style: { maxHeight: '260px', background: '#1d222b', borderRadius: '8px' } }) : h('img', { src: epUrl(ep, `/asset-file?path=${encodeURIComponent(a.path)}`), onError: (e) => { e.target.src = thumbOfAsset(a); }, style: { maxHeight: '260px', objectFit: 'contain', background: '#1d222b', borderRadius: '8px' } })),
      inp('title', 'Titel'), inp('credit', 'Credit (Künstler)'), inp('credit_link', 'Link zur Quelle'),
      h('div', { class: 'row' }, field('Konturfarbe', h('input', { type: 'color', value: f.contour_color || '#888888', onInput: (e) => { f.contour_color = e.target.value; } })), h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: f.zoom, onChange: (e) => { f.zoom = e.target.checked; } }), 'Langsamer Zoom'))),
    actions: [{ label: 'Abbrechen' }, { label: 'Speichern', kind: 'primary', onClick: async () => { try { Object.assign(a, await api.put(epUrl(ep, `/assets/${a.id}`), f)); drawMine(); } catch (e) { toast(e.message, 'err'); return false; } } }] });
  }
  function drawMine() {
    mine.replaceChildren(...(assets.length ? assets.map((a) => h('div', { class: 'thumb', style: { cursor: 'pointer' }, onClick: () => edit(a) }, h('img', { src: thumbOfAsset(a), loading: 'lazy', style: { width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block', background: '#222', borderBottom: `3px solid ${a.contour_color || 'transparent'}` } }),
      h('div', { style: { padding: '6px 8px', fontSize: '12px' } }, h('b', {}, a.id), ' ', a.title || ''), h('div', { class: 'row', style: { padding: '0 8px 8px' } }, h('span', { class: `help grow ${a.credit ? '' : 'warn'}`, style: a.credit ? null : { color: 'var(--warn)' } }, a.credit || 'Credit fehlt'), btn('', { icon: 'trash', size: 'sm', kind: 'ghost', title: 'Aus Folge entfernen', onClick: async (ev) => { ev.stopPropagation(); try { await api.del(epUrl(ep, `/assets/${a.id}`)); assets = assets.filter((x) => x.id !== a.id); drawMine(); search(); } catch (e) { toast(e.message, 'err'); } } })))) : [h('p', { class: 'help' }, 'Noch keine Bilder in dieser Folge.')]));
  }
  const url = h('input', { type: 'text', placeholder: 'https://… (Bildadresse einer Webseite)' });
  const index = async () => { try { const r = await runJob('Bildindex wird aufgebaut …', () => api.post('/api/images/index')); toast(`Index fertig: ${r.added} neu, ${r.unchanged} unverändert.`, 'ok'); search(); } catch (e) { toast(e.message, 'err'); } };
  const tags = h('div', { class: 'row wrap gap-s', style: { marginBottom: '12px' } });
  api.get('/api/images/keywords').then((k) => tags.replaceChildren(...k.slice(0, 40).map((x) => h('button', { class: 'chip', style: { cursor: 'pointer' }, onClick: () => { q.value = Array.isArray(x) ? x[0] : x; search(); } }, Array.isArray(x) ? x[0] : x)))).catch(() => {});
  const artists = async () => {
    let db = {}; try { db = await api.get('/api/artists'); } catch (e) { toast(e.message, 'err'); return; }
    const rows = Object.entries(db).map(([k, v]) => ({ k, v })), list = h('div', { class: 'col gap-s' });
    const draw = () => list.replaceChildren(...rows.map((r, i) => h('div', { class: 'row' }, h('input', { type: 'text', value: r.k, placeholder: 'Dateiname-Schlüssel', onInput: (e) => { r.k = e.target.value; } }), icon('chevron'), h('input', { type: 'text', value: r.v, placeholder: 'Credit-Text', onInput: (e) => { r.v = e.target.value; } }), btn('', { icon: 'trash', kind: 'ghost', onClick: () => { rows.splice(i, 1); draw(); } }))));
    draw();
    modal({ title: 'Künstler-Datenbank', body: h('div', { class: 'col' }, h('p', { class: 'help' }, 'Aus dem Dateinamen abgeleiteter Name → Credit-Text. Gilt für alle Folgen und wird mit OneDrive geteilt.'), list, btn('Eintrag +', { icon: 'plus', onClick: () => { rows.push({ k: '', v: '' }); draw(); } })),
      actions: [{ label: 'Abbrechen' }, { label: 'Speichern', kind: 'primary', onClick: async () => { try { await api.put('/api/artists', Object.fromEntries(rows.map((r) => [r.k, r.v]))); toast('Gespeichert.', 'ok'); } catch (e) { toast(e.message, 'err'); return false; } } }] });
  };
  drawMine(); search();
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Bilder'), h('p', {}, 'Aus der Bibliothek oder dem Web in die Folge übernehmen. Credit und Konturfarbe werden vorbelegt.')), btn('Künstler-Datenbank', { icon: 'user', onClick: artists }), btn('Bildindex aktualisieren', { icon: 'refresh', onClick: index })),
    h('h3', { style: { margin: '0 0 10px' } }, 'In dieser Folge'), mine,
    h('div', { class: 'card', style: { margin: '22px 0 14px' } }, h('div', { class: 'row' }, url, btn('Aus Web holen', { icon: 'download', onClick: () => url.value && addAsset({ url: url.value }) }))),
    h('h3', { style: { margin: '0 0 10px' } }, 'Bibliothek'), h('div', { style: { marginBottom: '12px' } }, q), tags, res));
}
