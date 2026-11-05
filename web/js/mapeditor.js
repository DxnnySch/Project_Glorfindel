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
  const box = h('div', { class: 'map-canvas', style: { position: 'relative', transformOrigin: '0 0' } }, img, cv);
  const viewport = h('div', { class: 'map-viewport' }, box);
  const zoomLabel = h('span', { class: 'help', style: { minWidth: '44px', textAlign: 'center' } }, '100 %');
  let zoom = 1, panX = 0, panY = 0, panning = null, spaceDown = false;
  const applyView = () => {
    const h0 = box.offsetHeight;
    if (h0) viewport.style.height = `${h0}px`;                 // Rahmen behält die Größe, das Bild darin wird vergrößert
    const vw = viewport.clientWidth, vh = viewport.clientHeight;
    panX = Math.min(0, Math.max(vw - vw * zoom, panX)); panY = Math.min(0, Math.max(vh - vh * zoom, panY));   // Bild füllt immer den Rahmen
    box.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
    zoomLabel.textContent = `${Math.round(zoom * 100)} %`;
    draw();
  };
  const zoomAt = (f, cx, cy) => {
    const nz = Math.min(8, Math.max(1, zoom * f)), k = nz / zoom;
    panX = cx - (cx - panX) * k; panY = cy - (cy - panY) * k; zoom = nz; applyView();
  };
  viewport.addEventListener('wheel', (e) => { e.preventDefault(); const r = viewport.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top); }, { passive: false });
  viewport.addEventListener('mousedown', (e) => { if (e.button === 1 || e.button === 2 || spaceDown) { e.preventDefault(); panning = { x: e.clientX, y: e.clientY, px: panX, py: panY }; viewport.style.cursor = 'grabbing'; } }, true);
  const panMove = (e) => { if (panning) { panX = panning.px + e.clientX - panning.x; panY = panning.py + e.clientY - panning.y; applyView(); } };
  const panUp = () => { if (panning) { panning = null; viewport.style.cursor = ''; } };
  window.addEventListener('mousemove', panMove);
  window.addEventListener('mouseup', panUp);
  viewport.addEventListener('contextmenu', (e) => e.preventDefault());
  const zoomBar = h('div', { class: 'row gap-s' }, btn('', { icon: 'minus', size: 'sm', title: 'Verkleinern', onClick: () => zoomAt(1 / 1.4, viewport.clientWidth / 2, viewport.clientHeight / 2) }), zoomLabel,
    btn('', { icon: 'plus', size: 'sm', title: 'Vergrößern (auch Mausrad)', onClick: () => zoomAt(1.4, viewport.clientWidth / 2, viewport.clientHeight / 2) }),
    btn('Einpassen', { size: 'sm', onClick: () => { zoom = 1; panX = panY = 0; applyView(); } }),
    h('span', { class: 'help' }, 'Mausrad = zoomen · Leertaste oder mittlere/rechte Maustaste halten und ziehen = verschieben'));
  const list = h('div', { class: 'col gap-s' });
  const toolBar = h('div', { class: 'seg' });
  const info = h('div', { class: 'help' });

  const N = (e) => { const r = cv.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  function draw() {
    const q = devicePixelRatio * Math.min(zoom, 4);          // beim Zoomen schärfer zeichnen
    const W = cv.width = cv.clientWidth * q, H = cv.height = cv.clientHeight * q, g = cv.getContext('2d');
    const P = (p) => [p[0] * W, p[1] * H], lw = Math.max(2, W / 400);
    g.clearRect(0, 0, W, H); g.font = `${Math.max(12, W / 55)}px sans-serif`; g.lineWidth = lw; g.lineJoin = 'round';
    const text = (s, p) => { g.strokeStyle = '#000'; g.lineWidth = lw * 1.5; g.strokeText(s, p[0] + 8, p[1] - 8); g.fillStyle = '#fff'; g.fillText(s, p[0] + 8, p[1] - 8); g.lineWidth = lw; };
    m.elemente.forEach((el, i) => {
      g.strokeStyle = g.fillStyle = el.farbe || COL[el.typ] || '#fff';
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
  const keys = (e) => { if (e.key === ' ' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) { spaceDown = e.type === 'keydown'; if (e.type === 'keydown') e.preventDefault(); } if (e.type === 'keyup') return; if (e.key === 'Enter' && draft.length) finish(); if (e.key === 'Escape' && draft.length) { draft = []; draw(); e.stopPropagation(); } };
  document.addEventListener('keydown', keys); document.addEventListener('keyup', keys);

  const num = (v, cb, w = '78px') => h('input', { type: 'text', value: fmtTC(v), style: { width: w }, onChange: (e) => { const x = parseTC(e.target.value); if (x != null) cb(x); e.target.value = fmtTC(x ?? v); } });
  // Ende der Einblendung: leer = bleibt bis zum Ende der Animation
  const endTime = (el) => h('input', { type: 'text', value: el.t1 != null ? fmtTC(el.t1) : '', placeholder: 'Ende', title: 'Ende der Einblendung (leer = bis zum Schluss)', style: { width: '78px' },
    onChange: (e) => { const v = e.target.value.trim(); if (!v) { delete el.t1; } else { const x = parseTC(v); if (x != null && x > (el.t0 || 0)) el.t1 = x; else e.target.value = el.t1 != null ? fmtTC(el.t1) : ''; } } });
  function drawList() {
    list.replaceChildren(
      ...m.elemente.map((el, i) => h('div', { class: 'row' }, h('input', { type: 'color', class: 'colorpick', value: el.farbe || COL[el.typ], title: 'Farbe dieses Elements', onInput: (e) => { el.farbe = e.target.value; draw(); } }), h('span', { style: { width: '56px' } }, { marker: 'Marker', label: 'Text', pfeil: 'Pfeil', region: 'Region' }[el.typ]),
        h('input', { type: 'text', value: el.text || '', placeholder: 'Beschriftung', onInput: (e) => { el.text = e.target.value; draw(); } }), h('span', { class: 'help' }, 'ab'), num(el.t0 || 0, (x) => { el.t0 = x; }),
        h('span', { class: 'help' }, 'bis'), endTime(el),
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
  const dlg = modal({ title: `Karte: ${m.titel || m.id}`, wide: true, onClose: () => { document.removeEventListener('keydown', keys); document.removeEventListener('keyup', keys); window.removeEventListener('mousemove', panMove); window.removeEventListener('mouseup', panUp); playing = false; cancelAnimationFrame(raf); },
    body: h('div', { class: 'grid', style: { gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr)' } },
      h('div', { class: 'col' }, toolBar, zoomBar, viewport, info),
      h('div', { class: 'col' }, h('div', { class: 'row' }, field('Dauer (s)', dauer)), list, h('label', { class: 'field' }, h('span', {}, 'Hinweise'), hint))),
    actions: [{ label: 'Vorschau abspielen', keep: true, onClick: () => { openMapPreview(m); return false; } }, { label: 'Schließen' }, { label: 'Speichern', kind: 'primary', onClick: save }] });
  img.addEventListener('load', () => { applyView(); drawList(); }); setTimeout(() => { applyView(); drawList(); }, 200);
  return dlg;
}


// ---------- Vorschau der Animation (Kamerafahrt + Elemente) direkt im Browser ----------
const ease = (x) => { x = Math.min(1, Math.max(0, x)); return x * x * (3 - 2 * x); };
function camAt(m, t) {
  const k = [...(m.kamera || [])].sort((a, b) => a.t - b.t);
  if (!k.length) return [0, 0, 1, 1];
  if (t <= k[0].t) return k[0].rect;
  for (let i = 0; i < k.length - 1; i++) if (t >= k[i].t && t <= k[i + 1].t) { const f = ease((t - k[i].t) / Math.max(1e-6, k[i + 1].t - k[i].t)); return k[i].rect.map((v, j) => v + (k[i + 1].rect[j] - v) * f); }
  return k.at(-1).rect;
}
export function openMapPreview(m) {
  const W = 960, H = 400, img = new Image();
  img.src = `/api/maps/thumb?path=${encodeURIComponent(m.bild)}`;
  const cv = h('canvas', { width: W, height: H, style: { width: '100%', background: '#000', borderRadius: '8px', display: 'block' } });
  const dur = Math.max(1, m.dauer || 6);
  const slider = h('input', { type: 'range', min: 0, max: dur, step: 0.02, value: 0 });
  const lbl = h('span', { class: 'tc' }, '0.0 s');
  let t = 0, playing = false, last = 0, raf = 0;
  const frame = () => {
    const g = cv.getContext('2d'); g.clearRect(0, 0, W, H);
    if (!img.complete || !img.naturalWidth) return;
    let [x, y, w, hh] = camAt(m, t);
    const ia = img.naturalWidth / img.naturalHeight, va = W / H;       // Ausschnitt ans Clip-Format anpassen (um die Mitte)
    let vw = w, vh = hh;
    if ((w * ia) / hh > va) vh = (w * ia) / va / ia; else vw = (hh * va) / ia * 1;
    vw = Math.min(1, vw); vh = Math.min(1, vh);
    const vx = Math.min(1 - vw, Math.max(0, x + w / 2 - vw / 2)), vy = Math.min(1 - vh, Math.max(0, y + hh / 2 - vh / 2));
    g.drawImage(img, vx * img.naturalWidth, vy * img.naturalHeight, vw * img.naturalWidth, vh * img.naturalHeight, 0, 0, W, H);
    const P = (p) => [(p[0] - vx) / vw * W, (p[1] - vy) / vh * H], lw = 4;
    g.lineJoin = 'round'; g.lineCap = 'round'; g.font = '700 20px sans-serif';
    for (const el of m.elemente || []) {
      const t0 = el.t0 || 0, t1 = el.t1 ?? null; if (t < t0 || (t1 != null && t >= t1 + 0.3)) continue;
      const a = ease((t - t0) / 0.4) * (t1 != null && t > t1 ? 1 - ease((t - t1) / 0.3) : 1), col = el.farbe || COL[el.typ] || '#fff';
      g.globalAlpha = a; g.strokeStyle = g.fillStyle = col; g.lineWidth = lw;
      const label = (txt, p) => { if (!txt) return; g.lineWidth = 5; g.strokeStyle = '#000'; g.strokeText(txt, p[0] + 12, p[1] - 10); g.fillStyle = '#fff'; g.fillText(txt, p[0] + 12, p[1] - 10); g.strokeStyle = g.fillStyle = col; g.lineWidth = lw; };
      if (el.typ === 'marker') { const p = P([el.x, el.y]); g.beginPath(); g.arc(p[0], p[1], 10, 0, 7); g.fill(); g.strokeStyle = '#fff'; g.stroke(); label(el.text, p); }
      else if (el.typ === 'label') label(el.text || '', P([el.x, el.y]));
      else if (el.typ === 'pfeil' && el.punkte?.length > 1) {
        const prog = ease((t - t0) / Math.max(0.1, el.dauer || 1.5)); g.globalAlpha = a;
        const pts = el.punkte.map(P); const segLen = pts.slice(1).map((q, i) => Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1])), total = segLen.reduce((u, v) => u + v, 0);
        let rest = total * prog; g.beginPath(); g.moveTo(...pts[0]); let end = pts[0];
        for (let i = 0; i < segLen.length && rest > 0; i++) { const f = Math.min(1, rest / segLen[i]); end = [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f]; g.lineTo(...end); rest -= segLen[i]; }
        g.stroke(); label(el.text, pts[0]);
      } else if (el.typ === 'region' && el.punkte?.length > 2) { g.beginPath(); el.punkte.map(P).forEach((q, i) => (i ? g.lineTo(...q) : g.moveTo(...q))); g.closePath(); g.globalAlpha = a * 0.28; g.fill(); g.globalAlpha = a; g.stroke(); label(el.text, P(el.punkte[0])); }
      g.globalAlpha = 1;
    }
    lbl.textContent = `${t.toFixed(1)} s / ${dur.toFixed(1)} s`; slider.value = t;
  };
  const loop = (now) => { if (!playing) return; t += (now - last) / 1000; last = now; if (t >= dur) { t = dur; playing = false; playBtn.replaceChildren(icon('play'), h('span', {}, 'Abspielen')); } frame(); if (playing) raf = requestAnimationFrame(loop); };
  const playBtn = btn('Abspielen', { kind: 'primary', icon: 'play', onClick: () => { if (playing) { playing = false; playBtn.replaceChildren(icon('play'), h('span', {}, 'Abspielen')); return; } if (t >= dur) t = 0; playing = true; last = performance.now(); playBtn.replaceChildren(icon('pause'), h('span', {}, 'Pause')); raf = requestAnimationFrame(loop); } });
  slider.addEventListener('input', () => { t = +slider.value; frame(); });
  img.onload = frame;
  modal({ title: `Vorschau: ${m.titel || m.id}`, wide: true, onClose: () => { playing = false; cancelAnimationFrame(raf); },
    body: h('div', { class: 'col' }, cv, h('div', { class: 'row' }, playBtn, slider, lbl), h('p', { class: 'help' }, 'Vorschau der Platzhalter-Animation (Kamerafahrt, Marker, Pfeile, Regionen) – so ähnlich entsteht auch der gerenderte Platzhalter-Clip.')) });
  frame();
}
