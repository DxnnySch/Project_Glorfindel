// Formatierter Kommentartext (kleines Markdown) – Gegenstück zu server/glorfindel/richtext.py (gleiche Regeln, gleiche Testfälle).
// Syntax: **fett**, *kursiv*, __unterstrichen__, ~~durchgestrichen~~, [Text]{#rrggbb} Farbe, [Text]{bg:#rrggbb} Hervorhebung,
// Zeilenanfang: "# " Überschrift, "- " Liste, "1. " Nummerierung, ">" Einzug.
import { h } from './ui.js';
import { plain, strip, wordTokens, wordCount, hasMarkup } from './richtextcore.js';
export { plain, strip, wordTokens, wordCount, hasMarkup };

const COLOR = /^#[0-9a-f]{3,8}$/i;


// ---------- Vorschau (nur DOM-Knoten, nie innerHTML) ----------
function inline(parent, s) {
  const re = /\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\*(?!\s)(.+?)\*|\[([^\]\n]*)\]\{(bg:)?(#[0-9a-fA-F]{3,8})\}/g;
  let last = 0, m;
  while ((m = re.exec(s))) {
    if (m.index > last) parent.append(document.createTextNode(s.slice(last, m.index)));
    let el;
    if (m[1] != null) { el = document.createElement('strong'); inline(el, m[1]); }
    else if (m[2] != null) { el = document.createElement('u'); inline(el, m[2]); }
    else if (m[3] != null) { el = document.createElement('s'); inline(el, m[3]); }
    else if (m[4] != null) { el = document.createElement('em'); inline(el, m[4]); }
    else { el = document.createElement('span'); if (COLOR.test(m[7])) el.style[m[6] ? 'background' : 'color'] = m[7]; if (m[6]) el.style.borderRadius = '3px'; inline(el, m[5]); }
    parent.append(el);
    last = m.index + m[0].length;
  }
  if (last < s.length) parent.append(document.createTextNode(s.slice(last)));
}

export function render(markup) {
  const box = h('div', { class: 'rt-view' });
  let list = null, listHost = null;
  for (const line of (markup || '').split('\n')) {
    const ind = /^[ \t]*(>*)[ \t]*(.*)$/.exec(line), level = ind[1].length, rest = ind[2];
    const host = (() => {                                 // Einzug: Container mit Rand und Abstand
      if (!level) return box;
      const el = h('div', { style: { marginLeft: `${level * 18}px`, borderLeft: '2px solid var(--line, #888)', paddingLeft: '8px' } });
      box.append(el); return el;
    })();
    let m;
    if ((m = /^(#{1,3})[ \t]+(.*)$/.exec(rest))) { list = null; const el = document.createElement('h' + (m[1].length + 3)); inline(el, m[2]); host.append(el); continue; }
    if ((m = /^([-•]|\d+[.)])[ \t]+(.*)$/.exec(rest))) {
      const ordered = /\d/.test(m[1]);
      if (!list || listHost !== host || list.tagName !== (ordered ? 'OL' : 'UL')) { list = document.createElement(ordered ? 'ol' : 'ul'); host.append(list); listHost = host; }
      const li = document.createElement('li'); inline(li, m[2]); list.append(li); continue;
    }
    list = null;
    const p = document.createElement('div'); if (rest.trim()) inline(p, rest); else p.append(document.createElement('br')); host.append(p);
  }
  return box;
}

// ---------- Bearbeitung ----------
function edit(ta, fn) {
  const { selectionStart: a, selectionEnd: b, value } = ta;
  const r = fn(value, a, b);
  ta.value = r.value;
  ta.setSelectionRange(r.start, r.end);
  ta.focus();
  ta.dispatchEvent(new Event('input', { bubbles: true }));
}

export function toggleWrap(ta, open, close = open) {
  edit(ta, (v, a, b) => {
    const sel = v.slice(a, b);
    if (v.slice(a - open.length, a) === open && v.slice(b, b + close.length) === close)       // schon umschlossen: entfernen
      return { value: v.slice(0, a - open.length) + sel + v.slice(b + close.length), start: a - open.length, end: b - open.length };
    return { value: v.slice(0, a) + open + sel + close + v.slice(b), start: a + open.length, end: b + open.length };
  });
}

function lineRange(v, a, b) {
  const from = v.lastIndexOf('\n', a - 1) + 1;
  let to = v.indexOf('\n', b); if (to < 0) to = v.length;
  return [from, to];
}

export function linePrefix(ta, make) {
  edit(ta, (v, a, b) => {
    const [from, to] = lineRange(v, a, b);
    const lines = v.slice(from, to).split('\n');
    const next = lines.map((l, i) => make(l, i));
    const text = next.join('\n');
    return { value: v.slice(0, from) + text + v.slice(to), start: from, end: from + text.length };
  });
}

const stripBlock = (l) => l.replace(/^[ \t]*(?:#{1,3}[ \t]+|[-•][ \t]+|\d+[.)][ \t]+)/, '');
export const heading = (ta) => linePrefix(ta, (l) => { const m = /^(#{1,3})[ \t]+/.exec(l); const n = m ? (m[1].length % 3) + 1 : 1; const body = stripBlock(l); return m && m[1].length === 3 ? body : `${'#'.repeat(n)} ${body}`; });
export const bullets = (ta) => linePrefix(ta, (l) => (/^[ \t]*[-•][ \t]+/.test(l) ? stripBlock(l) : `- ${stripBlock(l)}`));
export const numbered = (ta) => linePrefix(ta, (l, i) => (/^[ \t]*\d+[.)][ \t]+/.test(l) ? stripBlock(l) : `${i + 1}. ${stripBlock(l)}`));
export const indent = (ta) => linePrefix(ta, (l) => (/^>/.test(l) ? `>${l}` : `> ${l}`));
export const outdent = (ta) => linePrefix(ta, (l) => l.replace(/^>[ \t]?/, ''));

export function colorize(ta, color, bg = false) {
  edit(ta, (v, a, b) => {
    if (a === b) return { value: v, start: a, end: b };
    const tag = `]{${bg ? 'bg:' : ''}${color}}`;
    return { value: `${v.slice(0, a)}[${v.slice(a, b)}${tag}${v.slice(b)}`, start: a + 1, end: b + 1 };
  });
}

export function clearFormat(ta) {
  edit(ta, (v, a, b) => {
    const [from, to] = a === b ? [0, v.length] : [a, b];
    const t = plain(v.slice(from, to));
    return { value: v.slice(0, from) + t + v.slice(to), start: from, end: from + t.length };
  });
}

const SWATCH = [['Rot', '#e0524d'], ['Gelb', '#f2c14e'], ['Grün', '#4cc38a'], ['Blau', '#4da3e0'], ['Weiß', '#ffffff']];

/** Werkzeugleiste für eine Textarea (Markdown-Zeichen werden eingefügt) plus Umschalter zur Vorschau. */
export function toolbar(ta, { onPreview } = {}) {
  const b = (label, title, fn, extra = {}) => h('button', { type: 'button', class: 'rt-btn', title, onMousedown: (e) => e.preventDefault(), onClick: fn, ...extra }, label);
  const color = h('input', { type: 'color', class: 'rt-color', value: '#e0524d', title: 'Farbe für markierten Text' });
  const bar = h('div', { class: 'rt-bar' },
    b(h('b', {}, 'F'), 'Fett (Strg+B)', () => toggleWrap(ta, '**')),
    b(h('i', {}, 'K'), 'Kursiv (Strg+I)', () => toggleWrap(ta, '*')),
    b(h('u', {}, 'U'), 'Unterstrichen (Strg+U)', () => toggleWrap(ta, '__')),
    b(h('s', {}, 'S'), 'Durchgestrichen', () => toggleWrap(ta, '~~')),
    h('span', { class: 'rt-sep' }),
    b('H', 'Überschrift (mehrfach klicken: Größe wechseln)', () => heading(ta)),
    b('• Liste', 'Aufzählung', () => bullets(ta)),
    b('1. Liste', 'Nummerierung', () => numbered(ta)),
    b('→', 'Einrücken', () => indent(ta)),
    b('←', 'Ausrücken', () => outdent(ta)),
    h('span', { class: 'rt-sep' }),
    ...SWATCH.map(([n, c]) => b('', `Textfarbe ${n}`, () => colorize(ta, c), { class: 'rt-sw', style: { background: c } })),
    color, b('A', 'Markierten Text in der gewählten Farbe', () => colorize(ta, color.value)), b('▮', 'Markierten Text in der gewählten Farbe hervorheben', () => colorize(ta, color.value, true)),
    h('span', { class: 'rt-sep' }),
    b('✕', 'Formatierung entfernen (Auswahl, sonst ganzer Text)', () => clearFormat(ta)));
  if (onPreview) {
    const pv = b('Vorschau', 'Formatierten Text ansehen / zurück zum Bearbeiten', () => { pv.textContent = onPreview() ? 'Bearbeiten' : 'Vorschau'; });
    bar.append(h('span', { class: 'grow' }), pv);
  }
  ta.addEventListener('keydown', (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'b') { e.preventDefault(); toggleWrap(ta, '**'); }
    else if (k === 'i') { e.preventDefault(); toggleWrap(ta, '*'); }
    else if (k === 'u') { e.preventDefault(); toggleWrap(ta, '__'); }
  });
  return bar;
}
