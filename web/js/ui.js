// UI-Bausteine: h(), Icons, Toasts, Dialoge, Dateiauswahl, Jobs, Formatierung.
import { api, waitJob } from './api.js';

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
export const $ = (sel, root = document) => root.querySelector(sel);
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

const P = {
  home: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  film: 'M4 4h16v16H4zM8 4v16M16 4v16M4 9h4M4 15h4M16 9h4M16 15h4',
  layers: 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5',
  edit: 'M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4',
  doc: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7',
  mic: 'M12 3a3 3 0 013 3v6a3 3 0 01-6 0V6a3 3 0 013-3zM6 11a6 6 0 0012 0M12 17v4',
  scissors: 'M6 6a3 3 0 100 .01M6 18a3 3 0 100 .01M8.5 8l11 9M8.5 16l11-9',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9.5a1.5 1.5 0 100 .01',
  map: 'M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2zM9 4v14M15 6v14',
  gear: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19 12l2-1-2-4-2 1a7 7 0 00-2-1l-.5-2h-4L10 7a7 7 0 00-2 1l-2-1-2 4 2 1a7 7 0 000 2l-2 1 2 4 2-1a7 7 0 002 1l.5 2h4l.5-2a7 7 0 002-1l2 1 2-4-2-1a7 7 0 000-2z',
  plus: 'M12 5v14M5 12h14', x: 'M6 6l12 12M18 6L6 18', check: 'M5 12l5 5 9-10', trash: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13',
  play: 'M7 4l13 8-13 8z', pause: 'M7 4h4v16H7zM13 4h4v16h-4z', step: 'M5 5l9 7-9 7zM17 5v14', stepb: 'M19 5l-9 7 9 7zM7 5v14',
  folder: 'M3 6h6l2 2h10v11H3z', file: 'M6 3h9l4 4v14H6z', download: 'M12 4v11M7 11l5 5 5-5M5 20h14', upload: 'M12 16V5M7 9l5-5 5 5M5 20h14',
  link: 'M10 14a4 4 0 005.6 0l3-3a4 4 0 00-5.6-5.6l-1 1M14 10a4 4 0 00-5.6 0l-3 3a4 4 0 005.6 5.6l1-1',
  lock: 'M6 11h12v9H6zM8 11V8a4 4 0 018 0v3', sparkle: 'M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z', alert: 'M12 4l10 17H2zM12 10v5M12 18v.5',
  refresh: 'M20 11a8 8 0 10-2 6M20 4v7h-7', search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5', layout: 'M3 4h18v16H3zM3 10h18M9 10v10',
  sun: 'M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0', clock: 'M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z', copy: 'M8 8h11v12H8zM5 16V4h11',
  chevron: 'M9 6l6 6-6 6', wand: 'M4 20L16 8M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM19 12l.7 1.3L21 14l-1.3.7L19 16l-.7-1.3L17 14l1.3-.7z',
  video: 'M3 6h12v12H3zM15 10l6-3v10l-6-3', compare: 'M4 4h7v16H4zM13 4h7v16h-7z', info: 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v6M12 7.5v.5',
};
export function icon(name, cls = '') {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor');
  s.setAttribute('stroke-width', '1.8'); s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
  if (cls) s.setAttribute('class', cls);
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', P[name] || P.file); s.appendChild(p); return s;
}
export const btn = (label, opts = {}) => h('button', { class: `btn ${opts.kind || ''} ${opts.size || ''}`, title: opts.title, disabled: opts.disabled, onClick: opts.onClick, type: 'button' },
  opts.icon ? icon(opts.icon) : null, label ? h('span', {}, label) : null);

export function toast(msg, kind = 'info', ms = 4200) {
  const t = h('div', { class: `toast ${kind}` }, msg);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), kind === 'err' ? ms * 2 : ms);
}

export function modal({ title, body, actions = [], wide = false, onClose }) {
  const ov = h('div', { class: 'overlay' });
  const close = () => { ov.remove(); onClose?.(); };
  const m = h('div', { class: `modal ${wide ? 'wide' : ''}`, role: 'dialog' },
    h('div', { class: 'modal-head' }, h('h2', { class: 'grow' }, title), h('button', { class: 'btn ghost icon', onClick: close, 'aria-label': 'Schließen' }, icon('x'))),
    h('div', { class: 'modal-body' }, body),
    actions.length ? h('div', { class: 'modal-foot' }, actions.map((a) => btn(a.label, { kind: a.kind, icon: a.icon, onClick: async () => { if ((await a.onClick?.(close)) !== false && !a.keep) close(); } }))) : null);
  ov.append(m);
  ov.addEventListener('mousedown', (e) => { if (e.target === ov) close(); });
  const esc = (e) => { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } };
  document.addEventListener('keydown', esc);
  $('#overlays').append(ov);
  return { close, el: m };
}
export const confirmBox = (title, text, okLabel = 'OK', danger = false) => new Promise((res) => {
  modal({ title, body: h('p', {}, text), onClose: () => res(false),
    actions: [{ label: 'Abbrechen', onClick: () => res(false) }, { label: okLabel, kind: danger ? 'danger' : 'primary', onClick: () => { res(true); } }] });
});

// Datei- oder Ordnerauswahl über den lokalen Browser-Endpunkt
export function pickPath({ title = 'Auswählen', start = '', files = false, accept = null }) {
  return new Promise((res) => {
    let cur = start, done = false;
    const list = h('div', { class: 'fs-list' }), pathEl = h('input', { type: 'text', value: start });
    const finish = (v, close) => { done = true; res(v); close?.(); };
    const load = async (p) => {
      try {
        const d = await api.get(`/api/fs?path=${encodeURIComponent(p)}&files=${files}`);
        cur = d.path; pathEl.value = d.path; clear(list);
        if (d.parent !== null) list.append(h('div', { class: 'fs-item', onClick: () => load(d.parent) }, icon('folder'), '..'));
        for (const e of d.entries) {
          const ok = e.dir || !accept || accept.some((x) => e.name.toLowerCase().endsWith(x));
          if (!ok) continue;
          list.append(h('div', { class: 'fs-item', onClick: () => (e.dir ? load(e.path) : finish(e.path, m.close)) }, icon(e.dir ? 'folder' : 'file'), e.name));
        }
      } catch (e) { toast(e.message, 'err'); }
    };
    const m = modal({ title, wide: false, onClose: () => { if (!done) res(null); },
      body: h('div', { class: 'col' }, h('div', { class: 'row' }, pathEl, btn('Öffnen', { onClick: () => load(pathEl.value) })), list),
      actions: files ? [] : [{ label: 'Diesen Ordner wählen', kind: 'primary', onClick: () => { finish(cur); } }] });
    load(start);
  });
}

// Hintergrundjob mit Fortschrittsanzeige
export async function runJob(label, startFn, host) {
  const bar = h('i', { style: { width: '2%' } });
  const box = h('div', { class: 'job' }, h('div', { class: 'spinner' }), h('span', {}, label), h('div', { class: 'bar' }, bar));
  (host || $('#toasts')).append(box);
  try {
    const { job } = await startFn();
    const result = await waitJob(job, (j) => { bar.style.width = `${Math.max(2, j.progress * 100)}%`; });
    return result;
  } finally { box.remove(); }
}

export const fmtTC = (s, fps = 24) => {
  if (s == null || isNaN(s)) return '–';
  const sign = s < 0 ? '-' : ''; s = Math.abs(s);
  const m = Math.floor(s / 60), sec = Math.floor(s % 60), cs = Math.min(99, Math.floor((s % 1) * 100 + 1e-6));
  return `${sign}${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
};
export const parseTC = (str, fps = 24) => {
  str = String(str).trim().replace(',', '.');
  let m = str.match(/^(?:(\d+):)?(\d+):(\d+)\.(\d+)$/);   // mm:ss.zz = Dezimalsekunden
  if (m) return (Number(m[1] || 0) * 3600) + Number(m[2]) * 60 + Number(`${m[3]}.${m[4]}`);
  m = str.match(/^(?:(\d+):)?(\d+):(\d+)(?::(\d+))?$/);   // mm:ss oder mm:ss:bb (Bilder)
  if (m) return (Number(m[1] || 0) * 3600) + Number(m[2]) * 60 + Number(m[3]) + (m[4] ? Number(m[4]) / fps : 0);
  const n = Number(str); return isNaN(n) ? null : n;
};
export const fmtDur = (s) => { s = Math.round(s || 0); const m = Math.floor(s / 60); return `${m}:${String(s % 60).padStart(2, '0')} min`; };
export const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const lightLabel = { gruen: 'passt', gelb: 'knapp', rot: 'zu lang' };
export const empty = (iconName, title, text, ...actions) => h('div', { class: 'empty' }, icon(iconName), h('h2', {}, title), h('p', {}, text), h('div', { class: 'row', style: { justifyContent: 'center', marginTop: '14px' } }, actions));
export const field = (label, input) => h('label', { class: 'field' }, h('span', {}, label), input);
