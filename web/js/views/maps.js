import { h, btn, empty, runJob, toast, field, icon, debounce } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';
import { openMapEditor, openMapPreview } from '../mapeditor.js';
import { modal } from '../ui.js';
import { openFrameDialog } from '../framecap.js';

export async function render(main) {
  const ep = S.ep;
  let mine = await api.get(epUrl(ep, '/maps'));
  const lib = h('div', { class: 'thumbs' }), own = h('div', { class: 'col' });
  const q = h('input', { type: 'search', placeholder: 'Karten suchen …' });
  const drawOwn = () => own.replaceChildren(...(mine.length ? mine.map((m) => h('div', { class: 'card tight row' },
    h('div', { class: 'grow' }, h('b', {}, m.titel || m.id), h('div', { class: 'help' }, m.bild), m.placeholder_clip ? h('span', { class: 'chip ok' }, 'Platzhalter-Clip vorhanden') : null),
    btn('Vorschau', { size: 'sm', icon: 'play', title: 'Animation im Browser abspielen', onClick: () => openMapPreview(m) }),
    m.placeholder_clip ? btn('Clip', { size: 'sm', icon: 'video', title: 'Gerenderten Platzhalter-Clip abspielen', onClick: () => modal({ title: `Platzhalter-Clip: ${m.titel || m.id}`, wide: true, body: h('video', { src: epUrl(ep, `/maps/${m.id}/clip?_=${Date.now()}`), controls: true, autoplay: true, style: { width: '100%', borderRadius: '8px', background: '#000' } }) }) }) : null,
    btn('Einzeichnen', { size: 'sm', icon: 'edit', onClick: () => openMapEditor(m, (saved) => { Object.assign(m, saved); drawOwn(); }) }),
    m.sheet ? btn('Blatt', { size: 'sm', icon: 'doc', title: 'Kartenblatt (Skizze + Hinweise) öffnen', onClick: () => window.open(epUrl(ep, `/maps/${m.id}/sheet?_=${Date.now()}`), '_blank') }) : null,
    btn('', { size: 'sm', icon: 'trash', kind: 'ghost', title: 'Aus Folge entfernen', onClick: async () => { try { await api.del(epUrl(ep, `/maps/${m.id}`)); mine = mine.filter((x) => x.id !== m.id); drawOwn(); } catch (e) { toast(e.message, 'err'); } } }),
    btn('Platzhalter rendern', { size: 'sm', icon: 'video', onClick: async () => { try { await runJob('Karte wird gerendert …', () => api.post(epUrl(ep, `/maps/${m.id}/render`))); mine = await api.get(epUrl(ep, '/maps')); drawOwn(); toast('Fertig.', 'ok'); } catch (e) { toast(e.message, 'err'); } } }))) : [h('p', { class: 'help' }, 'Noch keine Karte in dieser Folge. Wähle unten eine aus der Bibliothek.')]));
  const search = debounce(async () => {
    try { const r = await api.get(`/api/maps?q=${encodeURIComponent(q.value)}`);
      lib.replaceChildren(...(r.length ? r.map((m) => h('div', { class: 'thumb', style: { cursor: 'pointer' }, onClick: async () => {
        const rel = m.path.replace((S.settings.onedrive_root || '').replace(/\\/g, '/') + '/', '');
        let n = mine.length + 1; while (mine.some((x) => x.id === `map_${String(n).padStart(2, '0')}`)) n++;
        const id = `map_${String(n).padStart(2, '0')}`;
        try { const saved = await api.put(epUrl(ep, `/maps/${id}`), { id, titel: m.name.replace(/\.[^.]+$/, ''), bild: rel, elemente: [] }); mine.push(saved); drawOwn(); toast('Karte hinzugefügt.', 'ok'); } catch (e) { toast(e.message, 'err'); } } },
      h('img', { src: `/api/maps/thumb?path=${encodeURIComponent(rel0(m.path))}`, loading: 'lazy', style: { width: '100%', aspectRatio: '4/3', objectFit: 'cover', display: 'block' } }), h('div', { style: { padding: '6px 8px', fontSize: '12px' } }, m.name))) : [h('p', { class: 'help' }, 'Keine Karten gefunden (Kartenordner in den Einstellungen prüfen).')]));
    } catch (e) { toast(e.message, 'err'); }
  }, 300);
  const rel0 = (p) => p.replace((S.settings.onedrive_root || '').replace(/\\/g, '/') + '/', '');
  q.addEventListener('input', search); drawOwn(); search();
  main.append(h('div', { class: 'page' }, h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Karten'), h('p', {}, 'Karten für Kartenerklärungen auswählen. Für Premiere/After Effects wird ein Kartenblatt und ein Platzhalter-Clip erzeugt.')),
      btn('Karte aus Videobild', { icon: 'video', title: 'Ein Bild aus dem Video speichern und darin markieren', onClick: () => openFrameDialog(async () => { mine = await api.get(epUrl(ep, '/maps')); drawOwn(); }) })),
    h('h3', { style: { margin: '0 0 10px' } }, 'In dieser Folge'), own, h('h3', { style: { margin: '22px 0 10px' } }, 'Kartenbibliothek'), h('div', { style: { marginBottom: '12px' } }, q), lib));
}
