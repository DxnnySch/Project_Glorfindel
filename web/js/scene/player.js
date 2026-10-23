// Player mit Szenen-Zeitleiste (Bereich, Segmente, Kommentarmarken) und klickbarem Dialog der Episode.
import { h, $, clear, btn, icon, toast, runJob, fmtTC, empty } from '../ui.js';
import { api, epUrl } from '../api.js';

export const SEG_COLORS = ['#4da3e0', '#e9b44c', '#4cc38a', '#d96ad0', '#ef6b5b', '#7ee0a0', '#9b8cff', '#f08a4b'];
export const segColor = (i) => SEG_COLORS[i % SEG_COLORS.length];

export function createPlayer(E) {
  const { ep, ref, ui } = E;
  const box = h('div', { class: 'player' });
  let video = null, pend = { in: null, out: null }, rangeStop = null, raf = 0, sel = null;
  const fps = ref?.fps || 24;
  const tc = h('span', { class: 'tc' }, '00:00.00');
  const tl = h('div', { class: 'tl2', title: 'Klick: springen · Ziehen: Position wählen' });
  const pendEl = h('span', { class: 'chip accent hidden' });
  const playBtn = btn('', { icon: 'play', kind: 'primary', title: 'Abspielen/Pause (Leertaste)', onClick: () => toggle() });
  const dlgBox = h('div', { class: 'dlg-box' });
  const dlgBar = h('div', { class: 'dlg-bar hidden' });

  // ---- Zeitfenster ----
  const scene = () => E.sel();
  function windowRange() {
    const dur = (video && video.duration) || ref?.duration || 1;
    if (ui.allEp) return [0, dur];
    const s = scene();
    const pts = [];
    if (s?.bereich) pts.push(...s.bereich);
    (s?.segmente || []).forEach((g) => pts.push(g.in, g.out));
    (s?.beruehrt || []).forEach((t) => pts.push(t.in, t.out));
    if (!pts.length) return [0, dur];
    const a = Math.min(...pts), b = Math.max(...pts);
    const pad = Math.max(4, (b - a) * 0.04);
    return [Math.max(0, a - pad), Math.min(dur, b + pad)];
  }

  // ---- Transport ----
  function toggle() { if (!video) return; if (video.paused) video.play(); else { video.pause(); rangeStop = null; } }
  const step = (n) => { if (!video) return; video.pause(); rangeStop = null; video.currentTime = Math.max(0, video.currentTime + n / fps); };
  function seek(t) { if (video) { rangeStop = null; video.currentTime = Math.max(0, t); } }
  function playRange(a, b) { if (!video) return; video.currentTime = a; rangeStop = b; video.play(); }
  function pendUpdate() {
    pendEl.classList.toggle('hidden', pend.in == null && pend.out == null);
    pendEl.textContent = `Markierung: ${pend.in != null ? fmtTC(pend.in) : '…'} – ${pend.out != null ? fmtTC(pend.out) : '…'}`;
    if (pend.in != null && pend.out != null) {
      const a = Math.min(pend.in, pend.out), b = Math.max(pend.in, pend.out);
      pend = { in: null, out: null }; pendUpdate();
      if (b - a >= 0.2) E.addSegment(a, b);
    }
  }
  const markIn = () => { if (video) { pend.in = video.currentTime; pendUpdate(); } };
  const markOut = () => { if (video) { pend.out = video.currentTime; pendUpdate(); } };

  // ---- Zeitleiste ----
  function drawTimeline() {
    const s = scene(), [w0, w1] = windowRange(), span = Math.max(0.001, w1 - w0);
    const x = (t) => `${((t - w0) / span) * 100}%`;
    const els = [];
    if (s?.bereich) els.push(h('div', { class: 'tl2-band', title: 'Szenenbereich', style: { left: x(Math.max(w0, s.bereich[0])), width: `${(Math.min(w1, s.bereich[1]) - Math.max(w0, s.bereich[0])) / span * 100}%` } }));
    (s?.segmente || []).forEach((g, i) => {
      const left = Math.max(w0, g.in), right = Math.min(w1, g.out);
      if (right <= left) return;
      const nC = (s.kommentar || []).filter((b) => b.segment === i).length;
      els.push(h('div', { class: 'tl2-seg', title: `Segment ${i + 1}: ${fmtTC(g.in)}–${fmtTC(g.out)}${nC ? ` · ${nC} Kommentar(e)` : ''}`, style: { left: x(left), width: `${(right - left) / span * 100}%`, background: segColor(i) }, onClick: (e) => { e.stopPropagation(); E.focusSegment(i); seek(g.in); } }, h('b', {}, String(i + 1))));
      (s.kommentar || []).filter((b) => b.segment === i).forEach((b, k) => els.push(h('i', { class: `tl2-dot ${b.sprecher}`, title: `${b.sprecher}: ${(b.text || b.stichpunkte?.[0] || '').slice(0, 60)}`, style: { left: `calc(${x(left)} + ${k * 9 + 4}px)` } })));
    });
    if (pend.in != null) els.push(h('div', { class: 'tl2-pend', style: { left: x(pend.in) } }));
    if (video) els.push(h('div', { class: 'tl2-head', style: { left: x(Math.min(w1, Math.max(w0, video.currentTime))) } }));
    const ticks = [];
    for (let k = 0; k <= 4; k++) ticks.push(h('span', { class: 'tl2-tick mono', style: { left: `${k * 25}%` } }, fmtTC(w0 + span * k / 4).slice(0, 5)));
    tl.replaceChildren(...els, ...ticks);
  }
  tl.addEventListener('mousedown', (e) => {
    if (!video) return;
    const move = (ev) => { const r = tl.getBoundingClientRect(), [w0, w1] = windowRange(); seek(w0 + Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)) * (w1 - w0)); };
    move(e);
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });

  // ---- Dialog ----
  let lines = [], wordEls = [];
  function drawDialog() {
    const words = E.dialog.words || [];
    if (!E.dialog.available) {
      dlgBox.replaceChildren(h('div', { class: 'dlg-empty' }, icon('mic'), h('div', {}, h('b', {}, 'Noch kein Dialog der Episode'), h('p', { class: 'help' }, 'Der gesprochene Text der Episode wird transkribiert. Dann kannst du Dialogstellen direkt markieren und siehst in jedem Segment, was dort gesagt wird.')),
        btn('Dialog transkribieren', { kind: 'primary', icon: 'wand', onClick: async () => {
          try { await runJob('Dialog der Episode transkribieren', () => api.post(epUrl(ep, '/dialog/transcribe?sprache=auto'))); E.dialog = await api.get(epUrl(ep, '/dialog')); drawDialog(); E.redrawSegments(); } catch (e) { toast(e.message, 'err'); }
        } })));
      return;
    }
    const [w0, w1] = windowRange();
    const from = Math.max(0, w0 - 8), to = w1 + 8;
    const idx = [];
    words.forEach((w, i) => { if (w.end >= from && w.start <= to) idx.push(i); });
    lines = [];
    let cur = null;
    idx.forEach((i) => {
      const w = words[i];
      if (!cur || w.start - words[cur.at(-1)].end > 0.9 || cur.length >= 16) { cur = []; lines.push(cur); }
      cur.push(i);
    });
    wordEls = [];
    const s = scene();
    dlgBox.replaceChildren(...(lines.length ? lines.map((ln) => h('div', { class: 'dlg-line' }, h('small', { class: 'mono faint' }, fmtTC(words[ln[0]].start).slice(0, 5)),
      h('span', { class: 'dlg-words' }, ...ln.map((i) => {
        const w = words[i];
        const si = (s?.segmente || []).findIndex((g) => w.start >= g.in - 0.05 && w.end <= g.out + 0.15);
        const el = h('span', { class: `dw ${si >= 0 ? 'inseg' : ''}`, 'data-i': i, style: si >= 0 ? { boxShadow: `inset 0 -3px 0 ${segColor(si)}` } : null }, w.w, ' ');
        wordEls[i] = el;
        return el;
      })))) : [h('p', { class: 'help', style: { padding: '10px' } }, 'In diesem Zeitfenster wurde nichts gesprochen.')]));
    sel = null; dlgBar.classList.add('hidden');
  }
  function paintSel() {
    wordEls.forEach((el) => el && el.classList.remove('dsel'));
    if (!sel) { dlgBar.classList.add('hidden'); return; }
    const [a, b] = sel[0] <= sel[1] ? sel : [sel[1], sel[0]], words = E.dialog.words;
    for (let i = a; i <= b; i++) wordEls[i]?.classList.add('dsel');
    const t0 = Math.max(0, words[a].start - 0.15), t1 = words[b].end + 0.25;
    dlgBar.classList.remove('hidden');
    dlgBar.replaceChildren(h('span', { class: 'grow' }, h('b', {}, `${fmtTC(t0)} – ${fmtTC(t1)}`), ` · „${words.slice(a, b + 1).map((w) => w.w).join(' ')}“`),
      btn('Abspielen', { size: 'sm', icon: 'play', onClick: () => playRange(t0, t1) }), btn('Als Segment markieren', { size: 'sm', kind: 'primary', icon: 'plus', onClick: () => { E.addSegment(t0, t1); sel = null; paintSel(); } }));
  }
  dlgBox.addEventListener('mousedown', (e) => {
    const w = e.target.closest('.dw'); if (!w) return;
    const i0 = +w.dataset.i; let moved = false;
    sel = [i0, i0];
    const over = (ev) => { const t = ev.target.closest?.('.dw'); if (t) { sel[1] = +t.dataset.i; moved = true; paintSel(); } };
    const up = () => { document.removeEventListener('mouseover', over); document.removeEventListener('mouseup', up);
      if (!moved) { seek(E.dialog.words[i0].start); sel = null; } paintSel(); };
    document.addEventListener('mouseover', over); document.addEventListener('mouseup', up);
    e.preventDefault();
  });
  let lastWord = -1;
  function highlightWord() {
    if (!video || !E.dialog.available || !wordEls.length) return;
    const t = video.currentTime, words = E.dialog.words;
    let lo = 0, hi = words.length - 1, f = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (words[m].start <= t) { f = m; lo = m + 1; } else hi = m - 1; }
    if (f !== lastWord) { wordEls[lastWord]?.classList.remove('dnow'); const el = wordEls[f]; if (el && t - words[f].end < 1.2) { el.classList.add('dnow'); const r = dlgBox.getBoundingClientRect(), er = el.getBoundingClientRect(); if (er.top < r.top || er.bottom > r.bottom) dlgBox.scrollTop += er.top - r.top - r.height / 3; } lastWord = f; }
  }

  // ---- Video ----
  function build() {
    if (!ref) { box.append(empty('film', 'Keine Referenz', 'Importiere zuerst die Referenz-Episode unter „Quellen“.')); return; }
    video = h('video', { src: epUrl(ep, `/media/${ref.id}`), preload: 'metadata' });
    video.addEventListener('error', async () => {
      const ready = (await api.get(epUrl(ep, `/sources/${ref.id}/proxy-status`)).catch(() => ({ ready: false }))).ready;
      video.replaceWith(h('div', { class: 'player-msg' }, ready ? h('p', { class: 'muted' }, 'Das Video kann in diesem Browser nicht abgespielt werden. Bitte Chrome oder Edge verwenden.')
        : [h('p', { class: 'muted' }, 'Für die Vorschau fehlt der Proxy.'), btn('Proxy jetzt erzeugen', { kind: 'primary', onClick: async () => { await runJob('Proxy wird erzeugt …', () => api.post(epUrl(ep, `/sources/${ref.id}/proxy`))); E.redrawAll(); } })]));
    }, { once: true });
    const tick = () => { raf = 0; if (!video) return; tc.textContent = fmtTC(video.currentTime, fps); drawTimeline(); highlightWord();
      if (rangeStop != null && video.currentTime >= rangeStop) { video.pause(); rangeStop = null; } if (!video.paused) raf = requestAnimationFrame(tick); };
    const kick = () => { if (!raf) raf = requestAnimationFrame(tick); };
    video.addEventListener('timeupdate', kick); video.addEventListener('seeked', kick); video.addEventListener('play', () => { playBtn.replaceChildren(icon('pause')); kick(); }); video.addEventListener('pause', () => { playBtn.replaceChildren(icon('play')); kick(); });
    video.addEventListener('loadedmetadata', () => { drawTimeline(); E.onVideoReady?.(); });
    const bar = h('div', { class: 'player-bar' }, playBtn,
      btn('', { icon: 'stepb', kind: 'ghost', size: 'sm', title: 'Ein Bild zurück (←)', onClick: () => step(-1) }), btn('', { icon: 'step', kind: 'ghost', size: 'sm', title: 'Ein Bild vor (→)', onClick: () => step(1) }), tc,
      btn('I  Anfang', { size: 'sm', title: 'Anfang des Segments markieren (I)', onClick: markIn }), btn('O  Ende', { size: 'sm', title: 'Ende markieren (O) – danach entsteht das Segment', onClick: markOut }), pendEl,
      h('span', { class: 'grow' }),
      h('label', { class: 'check help', title: 'Zeitleiste und Dialog auf die ganze Episode ausdehnen' }, h('input', { type: 'checkbox', checked: !!ui.allEp, onChange: (e) => { ui.allEp = e.target.checked; drawTimeline(); drawDialog(); } }), 'ganze Episode'));
    box.append(video, tl, bar);
  }
  // Hinweis: Zeitleiste und Dialog funktionieren auch ohne abspielbares Video (Springen/Markieren)
  build();
  const el = h('div', { class: 'col' }, box, h('div', { class: 'card tight dlg-card' }, h('div', { class: 'card-head' }, h('h3', {}, 'Dialog der Episode'), h('span', { class: 'help grow' }, 'Klick = springen · Wörter ziehen = Stelle markieren'), E.dialog.available ? null : null), dlgBox, dlgBar));
  return {
    el, video: () => video, seek, playRange, step, toggle, markIn, markOut, drawTimeline, drawDialog,
    onScene() { lastWord = -1; drawDialog(); drawTimeline(); },
    jumpToScene() {
      const s = scene(); if (!s || !video) return;
      const t = s.segmente?.length ? s.segmente[0].in : s.bereich ? s.bereich[0] : null;
      const go = () => { if (t != null) { video.pause(); rangeStop = null; video.currentTime = t; } drawTimeline(); };
      if (video.readyState >= 1) go(); else video.addEventListener('loadedmetadata', go, { once: true });
    },
    dispose() { cancelAnimationFrame(raf); video?.pause(); },
  };
}
