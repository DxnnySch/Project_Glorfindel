// Reine Textfunktionen des formatierten Kommentars (ohne DOM, auch in Node testbar) – Gegenstück zu server/glorfindel/richtext.py.
const LINE_PREFIX = /^[ \t]*(?:>+[ \t]*)?(?:#{1,3}[ \t]+|[-•][ \t]+|\d+[.)][ \t]+)?/;      // Einzug und/oder Block-Zeichen (darf leer sein)
const DETECT = /^[ \t]*(?:>|#{1,3}[ \t]|[-•][ \t]|\d+[.)][ \t])/m;
const INLINE = /\*\*|__|~~|\*|\[(?=[^\]\n]*\]\{[^}\n]*\})|\]\{[^}\n]*\}/g;
const SIGNS = /\*\*|__|~~|\*[^\s*]|\[[^\]\n]*\]\{[^}\n]*\}/;

export function hasMarkup(text) {
  return SIGNS.test(text) || DETECT.test(text);
}

/** Reiner Text samt Zuordnung: map[i] = Position des Zeichens i des reinen Textes im Markup. */
export function strip(markup) {
  const src = markup || '';
  let out = '';
  const map = [];
  let pos = 0;
  for (const line of src.split('\n')) {
    const from = LINE_PREFIX.exec(line)[0].length;
    const body = line.slice(from);
    let last = 0;
    INLINE.lastIndex = 0;
    let m;
    const keep = (a, b) => { for (let i = a; i < b; i++) { out += body[i]; map.push(pos + from + i); } };
    while ((m = INLINE.exec(body))) { keep(last, m.index); last = m.index + m[0].length; }
    keep(last, body.length);
    out += '\n'; map.push(pos + line.length);          // Zeilenumbruch
    pos += line.length + 1;
  }
  return { text: out.slice(0, -1), map };
}

export const plain = (markup) => strip(markup).text;

/** Wörter des reinen Textes mit Bereich im Markup: [{start, end, word}] (Index = Wortnummer für Anker). */
export function wordTokens(markup) {
  const { text, map } = strip(markup);
  const out = [];
  for (const m of text.matchAll(/\S+/g)) out.push({ word: m[0], start: map[m.index], end: map[m.index + m[0].length - 1] + 1 });
  return out;
}

export const wordCount = (markup) => wordTokens(markup).length;

