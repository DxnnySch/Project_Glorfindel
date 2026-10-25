// Kommentartext mit farbiger Markierung der Wortbereiche, in denen ein Bild/eine Karte eingeblendet wird.
// Technik: Textarea über einer gleich formatierten Spiegel-Ebene, die die markierten Wörter hinterlegt.
import { h } from './ui.js';
import { wordTokens } from './richtext.js';

export const ANCHOR_COLORS = ['#e9b44c', '#4da3e0', '#4cc38a', '#d96ad0', '#ef6b5b', '#7ee0a0'];
export const colorOf = (i) => ANCHOR_COLORS[i % ANCHOR_COLORS.length];
export const wordsOf = (text) => (text || '').split(/\s+/).filter(Boolean);

/** Liefert { el, textarea, refresh } – `onInput(text)` bei Änderungen, `anchors()` gibt die aktuellen Anker (mit von/bis) zurück. */
export function markedTextarea({ value, placeholder, rows = 3, anchors, onInput, onFocus }) {
  const mirror = h('div', { class: 'mt-mirror', 'aria-hidden': 'true' });
  const ta = h('textarea', { class: 'mt-ta', rows, placeholder, value, spellcheck: 'true', onInput: (e) => { onInput?.(e.target.value); refresh(); grow(); }, onFocus, onScroll: () => { mirror.scrollTop = ta.scrollTop; } });
  const box = h('div', { class: 'mt-box' }, mirror, ta);
  function grow() { ta.style.height = 'auto'; ta.style.height = `${Math.max(ta.scrollHeight, rows * 24)}px`; mirror.style.height = ta.style.height; }
  function refresh() {
    const text = ta.value, list = anchors?.() || [];
    // Wörter des reinen Sprechtextes (Formatierungszeichen zählen nicht); jedes Wort bekommt seine Marken
    const toks = wordTokens(text);
    const frag = document.createDocumentFragment();
    let pos = 0;
    toks.forEach((t, wi) => {
      const hits = list.map((a, ai) => ({ a, ai })).filter(({ a }) => a.einheit !== 'stichpunkt' && wi >= a.von && (a.bis == null || wi < a.bis));
      if (t.start > pos) frag.append(document.createTextNode(text.slice(pos, t.start)));
      const span = document.createElement('span');
      span.textContent = text.slice(t.start, t.end);
      if (hits.length) {
        const c = colorOf(hits[0].ai);
        span.style.cssText = `background:${c}55;box-shadow:inset 0 -3px 0 ${c};border-radius:3px`;
        if (hits.some(({ a }) => a.von === wi)) span.classList.add('mt-start');
      }
      frag.append(span);
      pos = t.end;
    });
    frag.append(document.createTextNode(text.slice(pos) + '​'));
    mirror.replaceChildren(frag);
  }
  refresh();
  setTimeout(grow, 0);
  const api = { el: box, textarea: ta, refresh: () => { refresh(); grow(); } };
  return api;
}
