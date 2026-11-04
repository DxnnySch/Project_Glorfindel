// Werkzeugleiste des Panels: baut die Schaltflächen aus der Konfiguration des Servers. Nur `textContent`, nie innerHTML.
// `doc`: das Dokument (in Premiere `document`, im Test eine Nachbildung); `run(name, args, label)`: führt ein Werkzeug aus.
'use strict';

function make(doc) {
  const el = (tag, props = {}, ...kids) => {
    const e = doc.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else if (k === 'onclick') e.onclick = v; else e.setAttribute(k, v);
    }
    for (const k of kids) e.appendChild(k);
    return e;
  };
  return el;
}

/** Leitet die Werkzeugleiste in `host` neu auf. */
function buildTools(doc, host, cfg, run) {
  const el = make(doc);
  const btn = (text, name, args, cls, label) => el('button', { text, class: cls || '', onclick: () => run(name, args, label || text) });
  const section = (title, ...rows) => { const box = el('div', {}, el('h2', { text: title })); for (const r of rows) box.appendChild(r); return box; };
  const row = (cls, ...kids) => el('div', { class: cls }, ...kids);
  while (host.firstChild) host.removeChild(host.firstChild);

  const artSel = el('select', { id: 'credit-art' });
  for (const c of cfg.credits || []) artSel.appendChild(el('option', { value: c.art, text: c.name + (c.vorlage ? '' : ' (keine Vorlage)') }));
  const creditText = el('input', { id: 'credit-text', class: 'text', type: 'text', placeholder: 'Text (leer = Name aus dem Bild)' });
  const seconds = el('input', { id: 'len-sec', class: 'num', type: 'text', value: '7' });
  const val = (node) => (node.value !== undefined ? node.value : node.getAttribute('value'));

  const effectRow = (e) => {
    const r = row('row wrap', el('span', { class: 'label', text: e.name }));
    if (e.einzel) r.appendChild(btn('Anwenden', 'effects', { ids: [e.einzel], label: e.name }, '', e.name));
    if (e.ein) r.appendChild(btn('Ein', 'effects', { ids: [e.ein], label: e.name + ' ein' }, '', e.name + ' ein'));
    if (e.aus) r.appendChild(btn('Aus', 'effects', { ids: [e.aus], label: e.name + ' aus' }, '', e.name + ' aus'));
    if (e.ein && e.aus) r.appendChild(btn('Ein + Aus', 'effects', { ids: [e.ein, e.aus], label: e.name + ' ein + aus' }, 'primary', e.name + ' ein + aus'));
    return r;
  };

  host.appendChild(section('Artwork', row('row wrap', btn('Artwork bauen', 'artwork', {}, 'primary', 'Artwork bauen'))));
  host.appendChild(section('Credit',
    row('row', artSel, creditText),
    row('row wrap', el('button', { text: 'Credit setzen', class: 'primary', onclick: () => run('credit', { art: val(artSel), text: val(creditText) }, 'Credit setzen') }))));
  host.appendChild(section('Effekte auf die Auswahl', ...(cfg.effekte || []).map(effectRow)));
  host.appendChild(section('Überblendung und Ton',
    row('row wrap', el('span', { class: 'label', text: 'Überblendung' }),
      btn('Beide', 'transitions', { ein: true, aus: true }, '', 'Überblendung beide'), btn('Anfang', 'transitions', { ein: true, aus: false }, '', 'Überblendung Anfang'),
      btn('Ende', 'transitions', { ein: false, aus: true }, '', 'Überblendung Ende')),
    row('row wrap', el('span', { class: 'label', text: 'Ton-Blende' }),
      btn('Beide', 'audioFade', { ein: true, aus: true }, '', 'Ton-Blende beide'), btn('Ein', 'audioFade', { ein: true, aus: false }, '', 'Ton-Blende ein'),
      btn('Aus', 'audioFade', { ein: false, aus: true }, '', 'Ton-Blende aus'))));
  host.appendChild(section('Länge',
    row('row wrap', seconds, el('span', { class: 'muted', text: 's  ' }),
      el('button', { text: 'Länge setzen', onclick: () => run('length', { seconds: parseFloat(String(val(seconds)).replace(',', '.')) }, 'Länge setzen') }),
      btn('Bis Abspielkopf', 'length', {}, '', 'Ende bis Abspielkopf'))));
  host.appendChild(section('Information', row('row wrap', btn('Szene am Abspielkopf', 'scene', {}), btn('Auswahl untersuchen', 'inspect', {}))));
  return { artSel, creditText, seconds };
}

/** Hinweis statt Leiste, solange die App keine Konfiguration geliefert hat. */
function toolsNotReady(doc, host, why, onRetry) {
  const el = make(doc);
  while (host.firstChild) host.removeChild(host.firstChild);
  host.appendChild(el('div', { class: 'muted', text: 'Werkzeuge noch nicht bereit: ' + why }));
  host.appendChild(el('div', { class: 'row' }, el('button', { text: 'Neu laden', onclick: onRetry })));
}

module.exports = { buildTools, toolsNotReady };
