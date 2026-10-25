// Bild aus dem Video holen (volle Auflösung, ohne Letterbox) und als Karte anlegen, um darin zu markieren.
import { h, btn, modal, toast, field, fmtTC, parseTC, busy } from './ui.js';
import { api, epUrl } from './api.js';
import { S, refSource } from './state.js';
import { openMapEditor } from './mapeditor.js';

/** Aktuelles Bild speichern und im Karteneditor öffnen. */
export async function captureFrame(ep, sourceId, t, title = '', onMap) {
  const r = await busy('Bild wird aus dem Video geholt …', api.post(epUrl(ep, '/frame'), { source: sourceId, t, title, as_map: true }));
  toast(`Bild bei ${fmtTC(r.t)} gespeichert: ${r.path}`, 'ok', 5000);
  onMap?.(r.map);
  openMapEditor(r.map, (saved) => onMap?.(saved));
  return r;
}

/** Dialog: Zeitpunkt im Video wählen (Vorschau-Proxy), dann „Bild als Karte“. */
export function openFrameDialog(onMap) {
  const ep = S.ep, srcs = (S.data?.sources || []).filter((s) => s.proxy_ready ?? true);
  const ref = refSource() || srcs[0];
  if (!ref) { toast('Keine Videoquelle vorhanden.', 'warn'); return; }
  let sid = ref.id;
  const video = h('video', { src: epUrl(ep, `/media/${sid}`), controls: true, preload: 'metadata', style: { width: '100%', background: '#000', borderRadius: '8px' } });
  const tc = h('input', { type: 'text', value: fmtTC(0), style: { width: '100px' }, onChange: (e) => { const v = parseTC(e.target.value); if (v != null) video.currentTime = v; } });
  video.addEventListener('timeupdate', () => { if (document.activeElement !== tc) tc.value = fmtTC(video.currentTime); });
  const step = (n) => { video.pause(); video.currentTime = Math.max(0, video.currentTime + n / (ref.fps || 24)); };
  const title = h('input', { type: 'text', placeholder: 'Name der Karte (optional)' });
  const pick = srcs.length > 1 ? h('select', { onChange: (e) => { sid = e.target.value; video.src = epUrl(ep, `/media/${sid}`); } }, srcs.map((s) => h('option', { value: s.id, selected: s.id === sid }, `${s.id} · ${s.path.split('/').pop()}`))) : null;
  modal({ title: 'Karte aus Videobild', wide: true,
    body: h('div', { class: 'col' }, h('p', { class: 'help' }, 'Zum gewünschten Bild spulen, dann „Bild als Karte“. Gespeichert wird das Bild in voller Auflösung; im Karteneditor kannst du darin markieren.'),
      pick ? field('Quelle', pick) : null, video,
      h('div', { class: 'row gap-s' }, btn('', { icon: 'stepb', size: 'sm', onClick: () => step(-1), title: 'Ein Bild zurück' }), btn('', { icon: 'step', size: 'sm', onClick: () => step(1), title: 'Ein Bild vor' }), tc),
      field('Name', title)),
    actions: [{ label: 'Abbrechen' }, { label: 'Bild als Karte', kind: 'primary', icon: 'image', onClick: async () => { try { await captureFrame(ep, sid, video.currentTime, title.value, onMap); } catch (e) { toast(e.message, 'err'); return false; } } }] });
}
