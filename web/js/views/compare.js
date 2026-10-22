// Kontrolle: Doppelansicht Referenz vs. Quelle (Frames + Differenz), Szenenprüfung, HQ-Conform.
import { h, btn, runJob, toast, fmtTC, parseTC, icon, empty } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, refSource } from '../state.js';

let chosen = '';
export async function render(main, ctx) {
  const ep = S.ep, ref = refSource(), others = S.data.sources.filter((s) => s.id !== ref?.id);
  if (!ref || !others.length) { main.append(h('div', { class: 'page' }, h('div', { class: 'page-head' }, h('h1', {}, 'Kontrolle')), h('div', { class: 'card' }, empty('compare', 'Zweite Quelle nötig', 'Importiere unter „Quellen“ eine weitere Fassung (HQ/Screener) und setze Ankerpunkte.', btn('Zu den Quellen', { kind: 'primary', onClick: () => ctx.go('sources') }))))); return; }
  let src = others.find((s) => s.id === chosen) || others[0];
  const srcSel = h('select', { onChange: (e) => { chosen = e.target.value; ctx.refresh(); } }, others.map((s) => h('option', { value: s.id, selected: s.id === src.id }, `${s.role}: ${s.path.split('/').pop()}`)));
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

  // ---- Anker setzen: zwei Player, Bildschritt, „Hier verknüpfen“ ----
  const mapTime = (anchors, tt) => {
    const a = [...anchors].sort((x, y) => x.ref - y.ref);
    if (!a.length) return tt;
    if (a.length === 1) return tt - a[0].ref + a[0].src;
    let i = a.findIndex((x) => x.ref >= tt); i = i === -1 ? a.length - 1 : Math.max(1, i);
    const p = a[i - 1], q = a[i], k = (q.src - p.src) / (q.ref - p.ref || 1);
    return p.src + (tt - p.ref) * k;
  };
  const mkVideo = (id) => h('video', { src: epUrl(ep, `/media/${id}`), preload: 'auto', muted: true, style: { width: '100%', background: '#000', display: 'block', aspectRatio: '16/9' } });
  const vRef = mkVideo(ref.id), vSrc = mkVideo(src.id);
  let anchors = src.anchors.map((x) => ({ ...x }));
  const tcLbl = (v) => h('span', { class: 'tc' }, fmtTC(v.currentTime));
  const lblR = h('span', { class: 'tc' }, '00:00.00'), lblS = h('span', { class: 'tc' }, '00:00.00');
  vRef.addEventListener('timeupdate', () => { lblR.textContent = fmtTC(vRef.currentTime); }); vSrc.addEventListener('timeupdate', () => { lblS.textContent = fmtTC(vSrc.currentTime); });
  vRef.addEventListener('seeked', () => { lblR.textContent = fmtTC(vRef.currentTime); }); vSrc.addEventListener('seeked', () => { lblS.textContent = fmtTC(vSrc.currentTime); });
  const ctl = (v, fps) => h('div', { class: 'row wrap gap-s' }, ...[['−10 s', -10], ['−1 s', -1], ['‹ Bild', -1 / fps], ['Bild ›', 1 / fps], ['+1 s', 1], ['+10 s', 10]].map(([l, d]) => btn(l, { size: 'sm', onClick: () => { v.pause(); v.currentTime = Math.max(0, v.currentTime + d); } })),
    btn('', { icon: 'play', size: 'sm', onClick: () => (v.paused ? v.play() : v.pause()) }));
  const anchorList = h('div', { class: 'col gap-s' });
  const drawAnchors = () => anchorList.replaceChildren(...(anchors.length ? anchors.sort((x, y) => x.ref - y.ref).map((a, i) => h('div', { class: 'row' }, h('span', { class: 'chip accent' }, `Referenz ${fmtTC(a.ref)}`), icon('chevron'), h('span', { class: 'chip' }, `Quelle ${fmtTC(a.src)}`), h('span', { class: 'grow' }),
    btn('Hin', { size: 'sm', onClick: () => { vRef.currentTime = a.ref; vSrc.currentTime = a.src; } }), btn('', { icon: 'trash', size: 'sm', kind: 'ghost', onClick: async () => { anchors.splice(i, 1); await saveAnchors(); } }))) : [h('p', { class: 'help' }, 'Noch keine Anker. Beide Player auf dasselbe Bild stellen, dann „Hier verknüpfen“.')]));
  const saveAnchors = async () => { try { await api.put(epUrl(ep, `/sources/${src.id}/anchors`), { anchors }); src.anchors = anchors.map((x) => ({ ...x })); drawAnchors(); show(); toast('Anker gespeichert.', 'ok', 1800); } catch (e) { toast(e.message, 'err'); } };
  const linkHere = async () => { anchors.push({ ref: +vRef.currentTime.toFixed(3), src: +vSrc.currentTime.toFixed(3) }); await saveAnchors(); };
  const follow = () => { vRef.pause(); vSrc.currentTime = Math.max(0, mapTime(anchors, vRef.currentTime)); };
  drawAnchors();
  const anchorCard = h('div', { class: 'card col', style: { marginTop: '16px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Anker setzen'), btn('Quelle auf Referenzzeit springen', { size: 'sm', title: 'Setzt die Quelle über die aktuellen Anker auf dieselbe Stelle', onClick: follow }), btn('Hier verknüpfen', { kind: 'primary', icon: 'link', onClick: linkHere })),
    h('p', { class: 'help' }, 'Mit zwei oder mehr Ankern gleicht das Tool Versatz und Tempo stückweise aus. Setze einen Anker am Anfang und einen am Ende, bei Schnitt-Unterschieden (z. B. Werbepausen) zusätzliche dazwischen.'),
    h('div', { class: 'dual' }, h('div', { class: 'col gap-s' }, h('h3', {}, 'Referenz'), vRef, h('div', { class: 'row' }, lblR, ctl(vRef, ref.fps || 24))), h('div', { class: 'col gap-s' }, h('h3', {}, 'Quelle'), vSrc, h('div', { class: 'row' }, lblS, ctl(vSrc, src.fps || 24)))),
    h('h3', {}, 'Gesetzte Anker'), anchorList);

  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Kontrolle'), h('p', {}, 'Prüft, ob die Zeitabbildung stimmt: gleiche Bildinhalte in Referenz und Quelle. Bei geringer Übereinstimmung Ankerpunkte nachbessern (unten „Anker setzen“).')), srcSel, codec, btn('HQ-Conform', { icon: 'film', kind: 'primary', onClick: conform })),
    h('div', { class: 'card col' }, h('div', { class: 'row' }, tc, t, mode, verdict), dualBox, diffBox),
    h('div', { class: 'card', style: { marginTop: '16px' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Szenenprüfung (Anfang/Ende jedes Segments)'), btn('Alle prüfen', { icon: 'check', onClick: check })),
      h('table', {}, h('thead', {}, h('tr', {}, ['Szene', 'Anfang', 'Ende', ''].map((x) => h('th', {}, x)))), checkBody)), anchorCard));
  show();
}
