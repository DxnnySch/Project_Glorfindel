// Kartenproxy-Editor: Marker, Beschriftung, Pfeil, Region und Kamerarahmen (Keyframes) auf der Karte einzeichnen.
import { h, btn, modal, toast, icon, field, fmtTC, parseTC } from './ui.js';
import { api, epUrl } from './api.js';
import { S } from './state.js';

const COL = { marker: '#e0524d', label: '#ffffff', pfeil: '#f2c14e', region: '#4da3e0' };
const TOOLS = [['marker', 'Marker', 'sparkle'], ['label', 'Text', 'edit'], ['pfeil', 'Pfeil/Pfad', 'chevron'], ['region', 'Region', 'layout'], ['kamera', 'Kamerarahmen', 'video']];

export function openMapEditor(map, onSaved) {
  const m = JSON.parse(JSON.stringify({ elemente: [], kamera: [], hinweise: '', dauer: 6, ...map }));
  let tool = 'marker', draft = [], drag = null, hover = null;
  const root = (S.settings.onedrive_root || '').replace(/\\/g, '/');
  const img = h('img', { src: `/api/maps/thumb?path=${encodeURIComponent(m.bild)}`, style: { display: 'block', width: '100%', userSelect: 'none' }, draggable: 'false' });
  const cv = h('canvas', { style: { position: 'absolute', inset: 0, width: '100%', height: '100%', cursor: 'crosshair' } });
  const box = h('div', { class: 'map-canvas', style: { position: 'relative' } }, img, cv);
  const list = h('div', { class: 'col gap-s' });
  const toolBar = h('div', { class: 'seg' });
  const info = h('div', { class: 'help' });

  const N = (e) => { const r = cv.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  function draw() {
    const W = cv.width = cv.clientWidth * devicePixelRatio, H = cv.height = cv.clientHeight * devicePixelRatio, g = cv.getContext('2d');
    const P = (p) => [p[0] * W, p[1] * H], lw = Math.max(2, W / 400);
    g.clearRect(0, 0, W, H); g.font = `${Math.max(12, W / 55)}px sans-serif`; g.lineWidth = lw; g.lineJoin = 'round';
    const text = (s, p) => { g.strokeStyle = '#000'; g.lineWidth = lw * 1.5; g.strokeText(s, p[0] + 8, p[1] - 8); g.fillStyle = '#fff'; g.fillText(s, p[0] + 8, p[1] - 8); g.lineWidth = lw; };
    m.elemente.forEach((el, i) => {
      g.strokeStyle = g.fillStyle = COL[el.typ] || '#fff';
      if (el.typ === 'marker') { const p = P([el.x, el.y]); g.beginPath(); g.arc(p[0], p[1], lw * 3, 0, 7); g.fill(); g.strokeStyle = '#fff'; g.stroke(); if (el.text) text(el.text, p); }
      else if (el.typ === 'label') { text(el.text || 'Text', P([el.x, el.y])); }
      else if (el.punkte?.length) { g.beginPath(); el.punkte.forEach((q, k) => { const p = P(q); k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]); }); if (el.typ === 'region') { g.closePath(); g.globalAlpha = .25; g.fill(); g.globalAlpha = 1; } g.stroke(); if (el.text) text(el.text, P(el.punkte[0])); }
    });
    // Kamera-Keyframes
    m.kamera.forEach((k, i) => { g.strokeStyle = '#7ee0a0'; g.setLineDash([lw * 3, lw * 2]); const [x, y, w, hh] = k.rect; g.strokeRect(x * W, y * H, w * W, hh * H); g.setLineDash([]); g.fillStyle = '#7ee0a0'; g.fillText(`K${i + 1}`, x * W + 6, y * H + 18); });
    // Entwurf
    if (draft.length) { g.strokeStyle = COL[tool] || '#fff'; g.beginPath(); draft.forEach((q, k) => { const p = P(q); k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]); }); if (hover) { const p = P(hover); g.lineTo(p[0], p[1]); } g.stroke(); }
    if (drag) { g.strokeStyle = '#7ee0a0'; const [a, b] = drag; g.strokeRect(Math.min(a[0], b[0]) * W, Math.min(a[1], b[1]) * H, Math.abs(b[0] - a[0]) * W, Math.abs(b[1] - a[1]) * H); }
  }
  const finish = () => {
    if (draft.length >= (tool === 'region' ? 3 : 2)) { m.elemente.push({ typ: tool, punkte: draft.map((p) => p.map((v) => +v.toFixed(4))), text: '', t0: 0, dauer: 1.5 }); }
    draft = []; hover = null; drawAll();
  };
  cv.addEventListener('mousedown', (e) => { if (tool === 'kamera') { drag = [N(e), N(e)]; } });
  cv.addEventListener('mousemove', (e) => { hover = N(e); if (drag) drag[1] = hover; if (draft.length || drag) draw(); });
  cv.addEventListener('mouseup', () => {
    if (tool === 'kamera' && drag) {
      const [a, b] = drag, x = Math.min(a[0], b[0]), y = Math.min(a[1], b[1]), w = Math.abs(b[0] - a[0]), hh = Math.abs(b[1] - a[1]);
      drag = null;
      if (w > 0.03 && hh > 0.03) { const t = m.kamera.length ? m.kamera.at(-1).t + 2 : 0; m.kamera.push({ t, rect: [x, y, w, hh].map((v) => +v.toFixed(4)) }); drawAll(); }
      else draw();
    }
  });
  cv.addEventListener('click', (e) => {
    const p = N(e);
    if (tool === 'marker') { m.elemente.push({ typ: 'marker', x: +p[0].toFixed(4), y: +p[1].toFixed(4), text: '', t0: 0 }); drawAll(); }
    else if (tool === 'label') { const s = prompt('Beschriftung:'); if (s) { m.elemente.push({ typ: 'label', x: +p[0].toFixed(4), y: +p[1].toFixed(4), text: s, t0: 0 }); drawAll(); } }
    else if (tool === 'pfeil' || tool === 'region') { draft.push(p); draw(); }
  });
  cv.addEventListener('dblclick', () => { if (draft.length) { draft.pop(); finish(); } });
  const keys = (e) => { if (e.key === 'Enter' && draft.length) finish(); if (e.key === 'Escape' && draft.length) { draft = []; draw(); e.stopPropagation(); } };
  document.addEventListener('keydown', keys);

  const num = (v, cb, w = '78px') => h('input', { type: 'text', value: fmtTC(v), style: { width: w }, onChange: (e) => { const x = parseTC(e.target.value); if (x != null) cb(x); e.target.value = fmtTC(x ?? v); } });
  function drawList() {
    list.replaceChildren(
      ...m.elemente.map((el, i) => h('div', { class: 'row' }, h('span', { class: 'dot', style: { background: COL[el.typ] } }), h('span', { style: { width: '62px' } }, { marker: 'Marker', label: 'Text', pfeil: 'Pfeil', region: 'Region' }[el.typ]),
        h('input', { type: 'text', value: el.text || '', placeholder: 'Beschriftung', onInput: (e) => { el.text = e.target.value; draw(); } }), h('span', { class: 'help' }, 'ab'), num(el.t0 || 0, (x) => { el.t0 = x; }),
        btn('', { icon: 'trash', size: 'sm', kind: 'ghost', onClick: () => { m.elemente.splice(i, 1); drawAll(); } }))),
      ...m.kamera.map((k, i) => h('div', { class: 'row' }, h('span', { class: 'dot', style: { background: '#7ee0a0' } }), h('span', { style: { width: '62px' } }, `Kamera ${i + 1}`), h('span', { class: 'help grow' }, `Ausschnitt ${k.rect.map((v) => Math.round(v * 100)).join('/')} %`), h('span', { class: 'help' }, 'bei'), num(k.t, (x) => { k.t = x; }),
        btn('', { icon: 'trash', size: 'sm', kind: 'ghost', onClick: () => { m.kamera.splice(i, 1); drawAll(); } }))));
    if (!m.elemente.length && !m.kamera.length) list.append(h('p', { class: 'help' }, 'Noch nichts eingezeichnet. Werkzeug wählen und ins Bild klicken.'));
  }
  const drawAll = () => { draw(); drawList(); };
  const setTool = (k) => { tool = k; draft = []; toolBar.replaceChildren(...TOOLS.map(([id, l]) => h('button', { class: id === tool ? 'on' : '', onClick: () => setTool(id) }, l))); info.textContent = ({ marker: 'Klick setzt einen Marker.', label: 'Klick setzt eine Beschriftung.', pfeil: 'Klicks setzen Punkte, Doppelklick oder Enter beendet den Pfeil.', region: 'Klicks setzen Eckpunkte, Doppelklick oder Enter schließt die Region.', kamera: 'Rahmen aufziehen = Kamera-Ausschnitt (Keyframe). Mehrere Rahmen ergeben eine Fahrt.' })[tool]; };
  setTool('marker');
  const dauer = h('input', { type: 'number', min: 1, value: m.dauer, style: { width: '80px' }, onInput: (e) => { m.dauer = +e.target.value; } });
  const hint = h('textarea', { rows: 3, placeholder: 'Hinweise für die Animation (z. B. „erst Eregion, dann Fahrt nach Osten“)', value: m.hinweise || '', onInput: (e) => { m.hinweise = e.target.value; } });
  const save = async () => { try { const r = await api.put(epUrl(S.ep, `/maps/${m.id}`), m); onSaved?.(r); toast('Karte gespeichert.', 'ok'); } catch (e) { toast(e.message, 'err'); return false; } };
  const dlg = modal({ title: `Karte: ${m.titel || m.id}`, wide: true, onClose: () => document.removeEventListener('keydown', keys),
    body: h('div', { class: 'grid', style: { gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr)' } },
      h('div', { class: 'col' }, toolBar, box, info),
      h('div', { class: 'col' }, h('div', { class: 'row' }, field('Dauer (s)', dauer)), list, h('label', { class: 'field' }, h('span', {}, 'Hinweise'), hint))),
    actions: [{ label: 'Schließen' }, { label: 'Speichern', kind: 'primary', onClick: save }] });
  img.addEventListener('load', drawAll); setTimeout(drawAll, 200);
  return dlg;
}
