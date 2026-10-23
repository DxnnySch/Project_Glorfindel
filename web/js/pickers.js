// Bild-/Kartenauswahl mit Vorschaubildern: Folge, Bibliothek (Suche, Stichwörter), Web-Adresse, neue Karte.
import { h, btn, icon, modal, toast, debounce, thumbOfAsset, thumbOfMap, busy } from './ui.js';
import { api, epUrl } from './api.js';
import { S } from './state.js';

const relPath = (p) => p.replace((S.settings.onedrive_root || '').replace(/\\/g, '/') + '/', '');

/** Öffnet die Auswahl. Löst mit { kind: 'asset'|'karte', id } auf (oder null bei Abbruch). `lists` = { assets, maps } der Folge (werden ergänzt). */
export function pickMedia(ep, lists, { start = 'bild' } = {}) {
  return new Promise((resolve) => {
    let done = false, tab = start;
    const finish = (v) => { if (done) return; done = true; resolve(v); dlg.close(); };
    const body = h('div', { class: 'col' });
    const tabs = h('div', { class: 'seg' });
    const content = h('div', { class: 'col', style: { minHeight: '420px' } });
    body.append(tabs, content);

    const card = (src, label, sub, onClick, picked) => h('div', { class: 'thumb pick', style: { cursor: 'pointer', outline: picked ? '2px solid var(--ok)' : '' }, title: label, onClick },
      h('img', { src, loading: 'lazy', style: { width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block', background: '#222' } }),
      h('div', { style: { padding: '5px 8px', fontSize: '12px' } }, picked ? '✔ ' : '', label), sub ? h('div', { class: 'help', style: { padding: '0 8px 6px' } }, sub) : null);

    async function addAsset(body) {
      try { const a = await busy('Bild wird zur Folge hinzugefügt …', api.post(epUrl(ep, '/assets'), body));
        if (!lists.assets.find((x) => x.id === a.id)) lists.assets.push(a);
        finish({ kind: 'asset', id: a.id }); } catch (e) { toast(e.message, 'err'); }
    }
    function drawImages() {
      const grid = h('div', { class: 'thumbs pick-grid' }), mine = h('div', { class: 'thumbs pick-grid' });
      const q = h('input', { type: 'search', placeholder: 'Bibliothek durchsuchen (Name, Stichwort, Ordner) …', autofocus: true });
      const tags = h('div', { class: 'row wrap gap-s' });
      const url = h('input', { type: 'text', placeholder: 'oder Bildadresse aus dem Web (https://…)' });
      mine.replaceChildren(...lists.assets.map((a) => card(thumbOfAsset(a), a.title || a.id, a.credit || 'Credit fehlt', () => finish({ kind: 'asset', id: a.id }))));
      const search = debounce(async () => {
        try {
          const r = await api.get(`/api/images/search?q=${encodeURIComponent(q.value)}&limit=48`);
          grid.replaceChildren(...(r.length ? r.map((i) => card(`/api/images/thumb?path=${encodeURIComponent(i.path)}`, i.title || i.path.split('/').pop(), i.creator || '',
            () => { const ex = lists.assets.find((a) => a.path === i.path); ex ? finish({ kind: 'asset', id: ex.id }) : addAsset({ path: i.path }); }, lists.assets.some((a) => a.path === i.path))) : [h('p', { class: 'help' }, 'Keine Treffer. Ist der Bildindex aufgebaut (Ansicht „Bilder“)?')]));
        } catch (e) { toast(e.message, 'err'); }
      }, 250);
      q.addEventListener('input', search);
      api.get('/api/images/keywords').then((k) => tags.replaceChildren(...k.slice(0, 24).map((x) => h('button', { class: 'chip', style: { cursor: 'pointer' }, onClick: () => { q.value = x[0]; search(); } }, x[0])))).catch(() => {});
      content.replaceChildren(
        lists.assets.length ? h('div', {}, h('h3', { style: { margin: '0 0 8px' } }, 'Schon in dieser Folge'), mine) : null,
        h('div', {}, h('h3', { style: { margin: '6px 0 8px' } }, 'Bibliothek'), q, h('div', { style: { height: '8px' } }), tags, h('div', { style: { height: '8px' } }), grid),
        h('div', { class: 'row' }, url, btn('Aus Web holen', { icon: 'download', onClick: () => url.value && addAsset({ url: url.value }) })));
      search();
    }
    function drawMaps() {
      const mine = h('div', { class: 'thumbs pick-grid' }), lib = h('div', { class: 'thumbs pick-grid' });
      const q = h('input', { type: 'search', placeholder: 'Kartenbibliothek durchsuchen …' });
      mine.replaceChildren(...lists.maps.map((m) => card(thumbOfMap(m), m.titel || m.id, `${(m.elemente || []).length} Elemente`, () => finish({ kind: 'karte', id: m.id }))));
      const search = debounce(async () => {
        try {
          const r = await api.get(`/api/maps?q=${encodeURIComponent(q.value)}`);
          lib.replaceChildren(...(r.length ? r.map((m) => card(`/api/maps/thumb?path=${encodeURIComponent(relPath(m.path))}`, m.name.replace(/\.[^.]+$/, ''), 'Neue Karte aus Bibliothek', async () => {
            let n = lists.maps.length + 1;
            while (lists.maps.some((x) => x.id === `map_${String(n).padStart(2, '0')}`)) n++;
            const id = `map_${String(n).padStart(2, '0')}`;
            try { const saved = await api.put(epUrl(ep, `/maps/${id}`), { id, titel: m.name.replace(/\.[^.]+$/, ''), bild: relPath(m.path), dauer: 6, elemente: [], kamera: [], hinweise: '' });
              lists.maps.push(saved); finish({ kind: 'karte', id, neu: true }); } catch (e) { toast(e.message, 'err'); } })) : [h('p', { class: 'help' }, 'Keine Karten gefunden (Kartenordner in den Einstellungen prüfen).')]));
        } catch (e) { toast(e.message, 'err'); }
      }, 250);
      q.addEventListener('input', search);
      content.replaceChildren(
        lists.maps.length ? h('div', {}, h('h3', { style: { margin: '0 0 8px' } }, 'Karten dieser Folge'), mine) : null,
        h('div', {}, h('h3', { style: { margin: '6px 0 8px' } }, 'Neue Karte anlegen (und danach einzeichnen)'), q, h('div', { style: { height: '8px' } }), lib));
      search();
    }
    const drawTabs = () => { tabs.replaceChildren(...[['bild', 'Bilder'], ['karte', 'Karten']].map(([k, l]) => h('button', { class: k === tab ? 'on' : '', onClick: () => { tab = k; drawTabs(); } }, l))); (tab === 'bild' ? drawImages : drawMaps)(); };
    const dlg = modal({ title: 'Bild oder Karte einblenden', wide: true, body, onClose: () => { if (!done) { done = true; resolve(null); } } });
    drawTabs();
  });
}
