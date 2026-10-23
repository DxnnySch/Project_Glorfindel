// Kontrolle: Referenz und Quelle ausrichten (Anker setzen) – flüssig im Browser, ohne Server-Rechnerei beim Scrubben.
import { h, btn, runJob, toast, fmtTC, parseTC, icon, empty, remember } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource } from '../state.js';

let chosen = '';
const mapTime = (anchors, tt) => {
  const a = [...anchors].sort((x, y) => x.ref - y.ref);
  if (!a.length) return tt;
  if (a.length === 1) return tt - a[0].ref + a[0].src;
  let i = a.findIndex((x) => x.ref >= tt); i = i === -1 ? a.length - 1 : Math.max(1, i);
  const p = a[i - 1], q = a[i], k = (q.src - p.src) / (q.ref - p.ref || 1);
  return p.src + (tt - p.ref) * k;
};

export async function render(main, ctx) {
  const ep = S.ep, ref = refSource(), others = S.data.sources.filter((s) => s.id !== ref?.id);
  if (!ref || !others.length) { main.append(h('div', { class: 'page' }, h('div', { class: 'page-head' }, h('h1', {}, 'Kontrolle')), h('div', { class: 'card' }, empty('compare', 'Zweite Quelle nötig', 'Importiere unter „Quellen“ eine weitere Fassung (HQ/Screener).', btn('Zu den Quellen', { kind: 'primary', onClick: () => ctx.go('sources') }))))); return; }
  const ui = remember(`${ep.season}-${ep.episode}:compare`, { t: 0, src: '', mode: 'dual', opacity: 50 });
  let src = others.find((s) => s.id === chosen) || others.find((s) => s.id === ui.src) || others[0];
  let anchors = src.anchors.map((x) => ({ ...x }));
  const fpsR = ref.fps || 24, fpsS = src.fps || 24;

  // ---------- Videos ----------
  const mk = (id) => h('video', { src: epUrl(ep, `/media/${id}`), preload: 'metadata', muted: true, playsinline: true, class: 'cmp-video' });
  const vR = mk(ref.id), vS = mk(src.id);
  // Ein Seek zur Zeit: erst wenn die Metadaten da sind (vorher geht ein Seek verloren und das Video bleibt schwarz),
  // nie mehrere gleichzeitig, mit Wächter gegen hängende Seeks.
  const seeker = (v) => {
    v._want = 0; v._busy = false; v._busyAt = 0;
    const go = (vid, t) => {
      vid._want = Math.max(0, t);
      if (vid.readyState < 1) return;                       // wird bei loadedmetadata nachgeholt
      if (vid._busy && Date.now() - vid._busyAt < 3000) return;
      vid._busy = true; vid._busyAt = Date.now(); vid.currentTime = vid._want;
    };
    v.addEventListener('loadedmetadata', () => { v._busy = false; go(v, v._want); });
    v.addEventListener('seeked', () => { v._busy = false; if (Math.abs(v.currentTime - v._want) > 0.03) go(v, v._want); else scheduleMatch(); });
    v.addEventListener('loadeddata', () => scheduleMatch());
    return go;
  };
  const goR = seeker(vR), goS = seeker(vS);
  const labelR = h('span', { class: 'tc' }, '00:00.00'), labelS = h('span', { class: 'tc' }, '00:00.00');
  const upd = () => { labelR.textContent = fmtTC(vR.currentTime); labelS.textContent = fmtTC(vS.currentTime); slider.value = vR.currentTime; refTc.value = fmtTC(vR.currentTime); linkBtn.querySelector('span').textContent = `Hier verknüpfen  (Referenz ${fmtTC(vR.currentTime)} = Quelle ${fmtTC(vS.currentTime)})`; };
  vR.addEventListener('timeupdate', upd); vS.addEventListener('timeupdate', upd); vR.addEventListener('seeked', upd); vS.addEventListener('seeked', upd);
  for (const v of [vR, vS]) v.addEventListener('error', () => { errBox.textContent = 'Ein Video kann nicht abgespielt werden (Proxy fehlt oder Browser unterstützt H.264 nicht). Proxys unter „Quellen“ erzeugen; Chrome/Edge verwenden.'; errBox.style.display = ''; }, { once: true });
  const errBox = h('div', { class: 'banner', style: { display: 'none' } });
  const loading = (v, label) => { const o = h('div', { class: 'cmp-loading' }, h('div', { class: 'spinner' }), `${label} lädt …`);
    const upd2 = () => { o.style.display = v.readyState >= 2 && !v.seeking ? 'none' : ''; };
    for (const ev of ['loadedmetadata', 'loadeddata', 'canplay', 'seeking', 'seeked', 'waiting', 'playing', 'emptied']) v.addEventListener(ev, upd2);
    upd2(); return o; };

  // ---------- Live-Übereinstimmung (im Browser, ohne Server) ----------
  const cw = 64, ch = 36, ca = document.createElement('canvas'), cb = document.createElement('canvas');
  ca.width = cb.width = cw; ca.height = cb.height = ch;
  const ga = ca.getContext('2d', { willReadFrequently: true }), gb = cb.getContext('2d', { willReadFrequently: true });
  const match = h('span', { class: 'pill' }, 'Übereinstimmung …');
  let matchT = 0;
  function scheduleMatch(ms = 120) { clearTimeout(matchT); matchT = setTimeout(computeMatch, ms); }
  function computeMatch() {
    try {
      if (vR.readyState < 2 || vS.readyState < 2 || vR.seeking || vS.seeking) { scheduleMatch(500); return; }
      ga.drawImage(vR, 0, 0, cw, ch); gb.drawImage(vS, 0, 0, cw, ch);
      const A = ga.getImageData(0, 0, cw, ch).data, B = gb.getImageData(0, 0, cw, ch).data;
      let sa = 0, sb = 0, n = cw * ch; const ya = new Float32Array(n), yb = new Float32Array(n);
      for (let i = 0; i < n; i++) { ya[i] = A[i * 4] * .3 + A[i * 4 + 1] * .59 + A[i * 4 + 2] * .11; yb[i] = B[i * 4] * .3 + B[i * 4 + 1] * .59 + B[i * 4 + 2] * .11; sa += ya[i]; sb += yb[i]; }
      const ma = sa / n, mb = sb / n; let num = 0, da = 0, db = 0;
      for (let i = 0; i < n; i++) { const x = ya[i] - ma, y = yb[i] - mb; num += x * y; da += x * x; db += y * y; }
      const r = da && db ? num / Math.sqrt(da * db) : 0;
      match.textContent = `Übereinstimmung ${Math.max(0, Math.round(r * 100))} %`;
      match.className = `pill ${r > 0.9 ? 'ok' : r > 0.7 ? 'warn' : 'bad'}`;
    } catch { match.textContent = 'Übereinstimmung: nicht messbar'; match.className = 'pill'; }
  }

  // ---------- Steuerung ----------
  const dur = ref.duration || 1;
  const slider = h('input', { type: 'range', min: 0, max: dur, step: 0.1, value: ui.t || 0, class: 'cmp-slider' });
  const refTc = h('input', { type: 'text', value: fmtTC(ui.t || 0), style: { width: '104px' } });
  const flags = h('div', { class: 'cmp-flags' });
  const drawFlags = () => flags.replaceChildren(...anchors.map((a) => h('i', { class: 'cmp-flag', title: `Anker ${fmtTC(a.ref)} = ${fmtTC(a.src)}`, style: { left: `${a.ref / dur * 100}%` }, onClick: () => moveRef(a.ref) })));
  function moveRef(t) { t = Math.min(dur, Math.max(0, t)); ui.t = t; goR(vR, t); goS(vS, mapTime(anchors, t)); }
  slider.addEventListener('input', () => moveRef(+slider.value));
  refTc.addEventListener('change', () => { const v = parseTC(refTc.value); if (v != null) moveRef(v); });
  const stepR = (n) => { vR.pause(); goR(vR, vR.currentTime + n / fpsR); goS(vS, mapTime(anchors, vR.currentTime + n / fpsR)); };
  const nudge = (d) => { vS.pause(); goS(vS, vS.currentTime + d); };
  const nudgeBar = (label, fn, fps) => h('div', { class: 'row wrap gap-s' }, h('b', { class: 'help', style: { width: '74px' } }, label),
    ...[['−10 s', -10], ['−1 s', -1], ['−10 B', -10 / fps], ['‹ Bild', -1 / fps], ['Bild ›', 1 / fps], ['+10 B', 10 / fps], ['+1 s', 1], ['+10 s', 10]].map(([l, d]) => btn(l, { size: 'sm', onClick: () => fn(d) })));

  // ---------- Anzeige ----------
  const loadR = loading(vR, 'Referenz'), loadS = loading(vS, 'Quelle');
  const viewer = h('div', { class: 'cmp-view' });
  function drawViewer() {
    const mode = ui.mode;
    const capR = h('div', { class: 'cmp-cap' }, h('b', {}, 'Referenz'), labelR), capS = h('div', { class: 'cmp-cap' }, h('b', {}, 'Quelle'), labelS);
    if (mode === 'dual') viewer.replaceChildren(h('div', { class: 'dual' }, h('div', {}, capR, h('div', { class: 'cmp-frame' }, vR, loadR)), h('div', {}, capS, h('div', { class: 'cmp-frame' }, vS, loadS))));
    else {
      const stack = h('div', { class: 'cmp-frame cmp-stack' }, vR, vS);
      vS.style.opacity = mode === 'overlay' ? ui.opacity / 100 : 1; vS.style.mixBlendMode = mode === 'diff' ? 'difference' : 'normal';
      viewer.replaceChildren(...[h('div', { class: 'row' }, capR, capS), stack, mode === 'overlay' ? h('div', { class: 'row' }, h('span', { class: 'help' }, 'Referenz'), h('input', { type: 'range', min: 0, max: 100, value: ui.opacity, onInput: (e) => { ui.opacity = +e.target.value; vS.style.opacity = ui.opacity / 100; } }), h('span', { class: 'help' }, 'Quelle')) : null].filter(Boolean));
    }
    if (mode === 'dual') { vS.style.opacity = 1; vS.style.mixBlendMode = 'normal'; }
  }
  const modeBtns = h('div', { class: 'seg' }, [['dual', 'Nebeneinander'], ['overlay', 'Überblendung'], ['diff', 'Differenz']].map(([k, l]) => h('button', { class: ui.mode === k ? 'on' : '', onClick: (e) => { ui.mode = k; [...e.target.parentNode.children].forEach((b) => b.classList.toggle('on', b === e.target)); drawViewer(); } }, l)));

  // ---------- Anker ----------
  const anchorList = h('div', { class: 'col gap-s' });
  const saveAnchors = async () => { try { await api.put(epUrl(ep, `/sources/${src.id}/anchors`), { anchors }); src.anchors = anchors.map((x) => ({ ...x })); drawAnchors(); drawFlags(); toast('Anker gespeichert.', 'ok', 1500); } catch (e) { toast(e.message, 'err'); } };
  function drawAnchors() {
    anchors.sort((x, y) => x.ref - y.ref);
    anchorList.replaceChildren(...(anchors.length ? anchors.map((a, i) => h('div', { class: 'row' }, h('span', { class: 'chip accent' }, `Referenz ${fmtTC(a.ref)}`), icon('chevron'), h('span', { class: 'chip' }, `Quelle ${fmtTC(a.src)}`), h('span', { class: 'grow' }),
      btn('Hin', { size: 'sm', onClick: () => { goR(vR, a.ref); goS(vS, a.src); ui.t = a.ref; } }), btn('', { icon: 'trash', size: 'sm', kind: 'ghost', onClick: async () => { anchors.splice(i, 1); await saveAnchors(); } }))) : [h('p', { class: 'help' }, 'Noch keine Anker. Stelle die Referenz auf ein markantes Bild (z. B. ein Standbild oder einen harten Schnitt), richte die Quelle auf dasselbe Bild aus und klicke „Hier verknüpfen“.')]));
  }
  const linkBtn = btn('Hier verknüpfen', { kind: 'primary', icon: 'link', onClick: async () => { anchors.push({ ref: +vR.currentTime.toFixed(3), src: +vS.currentTime.toFixed(3) }); await saveAnchors(); } });

  // ---------- Gemeinsam abspielen ----------
  let following = false;
  const playBtn = btn('Beide abspielen', { icon: 'play', onClick: () => {
    if (!vR.paused) { vR.pause(); vS.pause(); following = false; playBtn.replaceChildren(icon('play'), h('span', {}, 'Beide abspielen')); return; }
    goS(vS, mapTime(anchors, vR.currentTime)); following = true; vR.play(); vS.play(); playBtn.replaceChildren(icon('pause'), h('span', {}, 'Pause'));
  } });
  vR.addEventListener('timeupdate', () => { if (following && Math.abs(vS.currentTime - mapTime(anchors, vR.currentTime)) > 0.2) goS(vS, mapTime(anchors, vR.currentTime)); });

  // ---------- Szenenprüfung, Conform ----------
  const srcSel = h('select', { onChange: (e) => { chosen = e.target.value; ui.src = chosen; ctx.refresh(); } }, others.map((s) => h('option', { value: s.id, selected: s.id === src.id }, `${s.role}: ${s.path.split('/').pop()}`)));
  const codec = h('select', { title: 'Ausgabeformat' }, [['prores', 'ProRes 422 HQ'], ['dnxhr', 'DNxHR HQ'], ['h264', 'H.264 (Test)']].map(([v, l]) => h('option', { value: v }, l)));
  const conform = async () => { try { const r = await runJob('HQ-Conform', () => api.post(epUrl(ep, '/conform'), { source: src.id, codec: codec.value, stills: true })); toast(`Fertig: ${r.file}`, 'ok', 9000); } catch (e) { toast(e.message, 'err'); } };
  const checkBody = h('tbody');
  const cell = (v) => (v == null ? '–' : `${Math.round(v * 100)} %`);
  const check = async () => {
    try { const r = await runJob('Szenenprüfung', () => api.post(epUrl(ep, `/scene-check?source=${src.id}`)));
      checkBody.replaceChildren(...r.map((x) => h('tr', {}, h('td', {}, h('b', {}, x.titel || x.scene)), h('td', {}, cell(x.A)), h('td', {}, cell(x.B)), h('td', {}, x.uncertain ? h('span', { class: 'pill bad' }, 'prüfen') : h('span', { class: 'pill ok' }, 'ok'))))); } catch (e) { toast(e.message, 'err'); }
  };

  const onKey = (e) => {
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
    const k = e.key;
    if (k === 'ArrowLeft' || k === 'ArrowRight') { e.preventDefault(); const d = (k === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 10 : 1); if (e.altKey) stepR(d); else nudge(d / fpsS); }
    else if (k === 'Enter') { e.preventDefault(); linkBtn.click(); }
    else if (k === ' ') { e.preventDefault(); playBtn.click(); }
  };
  document.addEventListener('keydown', onKey);

  drawViewer(); drawAnchors(); drawFlags();
  const startRef = () => { moveRef(ui.t || 0); };
  vR.addEventListener('loadedmetadata', startRef, { once: true });
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Kontrolle'), h('p', {}, 'Referenz und Quelle ausrichten: Zeit in der Referenz wählen, die Quelle auf dasselbe Bild nachjustieren, „Hier verknüpfen“. Beim Verschieben wird nichts auf dem Server gerechnet – es bleibt flüssig.')), srcSel, codec, btn('HQ-Conform', { icon: 'film', kind: 'primary', onClick: conform })),
    errBox,
    h('div', { class: 'card col' },
      h('div', { class: 'row' }, h('b', {}, 'Referenz-Zeit'), refTc, h('div', { class: 'grow cmp-slider-wrap' }, slider, flags), modeBtns, match),
      viewer,
      h('div', { class: 'col gap-s' }, nudgeBar('Quelle', (d) => nudge(d), fpsS), nudgeBar('Referenz', (d) => { vR.pause(); goR(vR, vR.currentTime + d); goS(vS, mapTime(anchors, vR.currentTime + d)); }, fpsR),
        h('div', { class: 'help' }, h('span', { class: 'kbd' }, '←'), h('span', { class: 'kbd' }, '→'), ' Quelle Bild für Bild (mit Umschalt: 10)  ·  ', h('span', { class: 'kbd' }, 'Alt'), '+', h('span', { class: 'kbd' }, '←/→'), ' Referenz  ·  ', h('span', { class: 'kbd' }, 'Enter'), ' verknüpfen  ·  ', h('span', { class: 'kbd' }, 'Leertaste'), ' beide abspielen')),
      h('div', { class: 'row wrap' }, linkBtn, playBtn)),
    h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Gesetzte Anker'), h('span', { class: 'help' }, 'Mit zwei oder mehr Ankern werden Versatz und Tempo stückweise ausgeglichen – einer am Anfang, einer am Ende, weitere bei Schnittunterschieden.')), anchorList),
    h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Szenenprüfung (Anfang/Ende jedes Segments)'), btn('Alle prüfen', { icon: 'check', onClick: check })),
      h('table', {}, h('thead', {}, h('tr', {}, ['Szene', 'Anfang', 'Ende', ''].map((x) => h('th', {}, x)))), checkBody))));
  return () => { document.removeEventListener('keydown', onKey); vR.pause(); vS.pause(); vR.removeAttribute('src'); vS.removeAttribute('src'); clearTimeout(matchT); };
}
