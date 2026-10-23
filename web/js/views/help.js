// Hilfe: Anleitung aus web/help/anleitung.md, ohne innerHTML gerendert; Inhaltsverzeichnis und Suche.
import { h, icon } from '../ui.js';

function inline(text) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const s = m[0];
    out.push(s.startsWith('**') ? h('b', {}, s.slice(2, -2)) : h('code', { class: 'mono' }, s.slice(1, -1)));
    last = m.index + s.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function parseSections(md) {
  const sections = [];
  let cur = { title: 'Einleitung', id: 's0', blocks: [] }, list = null, brk = true;
  const flush = () => { list = null; };
  for (const line of md.split('\n')) {
    if (line.startsWith('# ')) continue;
    if (line.startsWith('## ')) { flush(); cur = { title: line.slice(3), id: `s${sections.length + 1}`, blocks: [] }; sections.push(cur); continue; }
    if (/^\s*$/.test(line)) { flush(); brk = true; continue; }
    if (line.startsWith('- ')) { if (!list) { list = { type: 'ul', items: [] }; cur.blocks.push(list); } list.items.push(line.slice(2)); continue; }
    flush();
    if (/^\d+\.\s/.test(line)) { const last = cur.blocks.at(-1); if (last?.type === 'ol') last.items.push(line.replace(/^\d+\.\s/, '')); else cur.blocks.push({ type: 'ol', items: [line.replace(/^\d+\.\s/, '')] }); continue; }
    if (line.startsWith('**') && line.endsWith('**') && !line.slice(2, -2).includes('**')) { cur.blocks.push({ type: 'h', text: line.slice(2, -2) }); continue; }
    const last = cur.blocks.at(-1);
    if (last?.type === 'p' && !brk) last.text += ' ' + line; else cur.blocks.push({ type: 'p', text: line });
    brk = false;
  }
  if (cur.blocks.length && !sections.includes(cur)) sections.unshift(cur);
  return sections;
}

const renderBlock = (b) => (b.type === 'ul' ? h('ul', {}, b.items.map((i) => h('li', {}, inline(i))))
  : b.type === 'ol' ? h('ol', {}, b.items.map((i) => h('li', {}, inline(i))))
    : b.type === 'h' ? h('h3', { style: { margin: '14px 0 4px', textTransform: 'none', letterSpacing: 0, color: 'var(--text)', fontSize: '14px' } }, b.text)
      : h('p', {}, inline(b.text)));

export async function render(main) {
  let md = '';
  try { md = await (await fetch('/static/help/anleitung.md')).text(); } catch { /* unten Hinweis */ }
  const sections = parseSections(md);
  const body = h('div', { class: 'help-body' }), toc = h('div', { class: 'col gap-s' });
  const search = h('input', { type: 'search', placeholder: 'In der Anleitung suchen …', onInput: () => draw() });
  const text = (s) => `${s.title} ${s.blocks.map((b) => (b.items ? b.items.join(' ') : b.text)).join(' ')}`.toLowerCase();
  function draw() {
    const q = search.value.trim().toLowerCase();
    const shown = sections.filter((s) => !q || text(s).includes(q));
    toc.replaceChildren(...shown.map((s) => h('a', { href: `#help-${s.id}`, class: 'nav', style: { padding: '5px 8px' }, onClick: (e) => { e.preventDefault(); document.getElementById(`help-${s.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, s.title)));
    body.replaceChildren(...(shown.length ? shown.map((s) => h('section', { id: `help-${s.id}`, class: 'card', style: { marginBottom: '14px', scrollMarginTop: '12px' } }, h('h2', { style: { marginBottom: '8px' } }, s.title), s.blocks.map(renderBlock))) : [h('p', { class: 'help' }, md ? 'Nichts gefunden.' : 'Die Anleitung konnte nicht geladen werden.')]));
  }
  draw();
  main.append(h('div', { class: 'page', style: { maxWidth: '1100px' } },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Hilfe'), h('p', {}, 'Schritt-für-Schritt-Anleitung vom Import bis zum Rohschnitt.'))),
    h('div', { class: 'grid', style: { gridTemplateColumns: '240px minmax(0, 1fr)', alignItems: 'start' } },
      h('div', { class: 'card', style: { position: 'sticky', top: '12px', maxHeight: '85vh', overflow: 'auto' } }, search, h('div', { style: { height: '8px' } }), toc), body)));
}
