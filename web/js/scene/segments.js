// Segmentkarten: je Segment Zeiten, Dialog, Notiz und die Kommentare dazu – mit Bildern/Karten direkt am Kommentartext.
import { h, btn, icon, toast, modal, field, confirmBox, busy, fmtTC, parseTC, thumbOfAsset, thumbOfMap } from '../ui.js';
import { api } from '../api.js';
import { S } from '../state.js';
import { markedTextarea, colorOf, wordsOf } from '../markedtext.js';
import { hasMarkup, plain, wordTokens, toolbar, render } from '../richtext.js';
import { pickMedia } from '../pickers.js';
import { openMapEditor } from '../mapeditor.js';
import { segColor } from './player.js';

const LIGHT = { gruen: 'ok', gelb: 'warn', rot: 'bad' };

export function createSegments(E) {
  const host = h('div', { class: 'seg-cards' });
  const aiOn = () => S.settings._scads_key_present && S.settings.llm.enabled;
  const blockText = (b) => (b.modus === 'stichpunkte' ? b.stichpunkte.join('\n') : b.text);
  const cards = [];

  const dialogOf = (g) => {
    const words = E.dialog.words || [];
    return words.filter((w) => { const m = (w.start + w.end) / 2; return m >= g.in - 0.1 && m <= g.out + 0.1; }).map((w) => w.w).join(' ');
  };
  const itemOf = (a) => (a.karte ? E.maps.find((m) => m.id === a.karte) : E.assets.find((x) => x.id === a.asset));
  const thumbOf = (a) => { const it = itemOf(a); return it ? (a.karte ? thumbOfMap(it) : thumbOfAsset(it)) : ''; };
  const nameOf = (a) => { const it = itemOf(a); return it ? (a.karte ? it.titel || it.id : it.title || it.credit || it.path.split('/').pop()) : (a.asset || a.karte); };

  function rangeText(b, a) {
    if (b.modus === 'stichpunkte') return `Stichpunkt ${a.von + 1}${a.bis != null && a.bis - 1 > a.von ? `–${a.bis}` : ''}`;
    const w = wordsOf(b.text), last = a.bis == null ? w.length : a.bis;
    return `Wörter ${a.von + 1}–${last}${w.length ? `: „${w.slice(a.von, Math.min(last, a.von + 4)).join(' ')}${last - a.von > 4 ? ' …' : ''}“` : ''}`;
  }

  function rangeDialog(b, a) {
    const isB = b.modus === 'stichpunkte', items = isB ? b.stichpunkte : wordsOf(b.text);
    let von = a.von, bis = a.bis, pickingEnd = false;
    const strip = h('div', { class: 'range-strip' });
    const info = h('div', { class: 'help' });
    const draw = () => {
      strip.replaceChildren(...items.map((w, i) => h('span', { class: `rw ${i >= von && (bis == null ? !isB || i === von : i < bis) ? 'on' : ''}`, onClick: () => {
        if (isB) { von = i; bis = null; } else if (!pickingEnd) { von = i; bis = null; pickingEnd = true; } else { if (i < von) { bis = von + 1; von = i; } else bis = i + 1; pickingEnd = false; }
        draw(); } }, w, ' ')));
      info.textContent = isB ? 'Klicke den Stichpunkt, ab dem das Bild erscheint.' : pickingEnd ? 'Jetzt das LETZTE Wort anklicken (oder „Bis zum Ende“).' : 'Klicke das ERSTE Wort, ab dem das Bild erscheint – danach das letzte.';
    };
    draw();
    const lay = h('select', { onChange: (e) => { a.layout = e.target.value; } }, [['einzel', 'Einzelbild'], ['doppel_links', 'Doppelbild – links'], ['doppel_rechts', 'Doppelbild – rechts']].map(([k, l]) => h('option', { value: k, selected: a.layout === k }, l)));
    const src = thumbOf(a);
    modal({ title: `Einblendung: ${nameOf(a)}`, wide: true, body: h('div', { class: 'col' },
      h('div', { class: 'row' }, src ? h('img', { src, style: { width: '120px', height: '80px', objectFit: 'cover', borderRadius: '8px', background: '#222' } }) : null, h('div', { class: 'grow' }, info), field('Layout', lay)),
      strip),
    actions: [{ label: 'Entfernen', kind: 'danger', onClick: () => { b.anker = b.anker.filter((x) => x !== a); E.touch(); redraw(); } },
      ...(isB ? [] : [{ label: 'Bis zum Ende', keep: true, onClick: () => { bis = null; pickingEnd = false; draw(); return false; } }]),
      { label: 'Übernehmen', kind: 'primary', onClick: () => { a.von = von; a.bis = bis; E.touch(); redraw(); } }] });
  }

  function selectionOf(b, ta) {
    if (b.modus === 'stichpunkte') return { von: Math.max(0, ta ? ta.value.slice(0, ta.selectionStart).split('\n').length - 1 : 0), bis: null };
    if (!ta) return { von: 0, bis: null };
    const toks = wordTokens(ta.value), a = ta.selectionStart, e = ta.selectionEnd;
    const von = toks.filter((t) => t.end <= a).length, n = toks.filter((t) => t.end > a && t.start < e).length;
    return { von: Math.min(von, Math.max(0, toks.length - 1)), bis: n ? von + n : null };
  }
  async function addMedia(b, ta) {
    const sel = selectionOf(b, ta);
    const pick = await pickMedia(E.ep, { assets: E.assets, maps: E.maps });
    if (!pick) return;
    b.anker = [...(b.anker || []), { asset: pick.kind === 'asset' ? pick.id : null, karte: pick.kind === 'karte' ? pick.id : null, von: sel.von, bis: sel.bis, layout: 'einzel', einheit: b.modus === 'stichpunkte' ? 'stichpunkt' : 'wort' }];
    E.touch(); redraw();
    if (pick.kind === 'karte' && pick.neu) { const m = E.maps.find((x) => x.id === pick.id); if (m) openMapEditor(m, (saved) => { Object.assign(m, saved); redraw(); }); }
  }

  // ---- KI ----
  async function aiNames(b) {
    try {
      const r = await busy('KI prüft Namen …', api.post('/api/llm/check-names', { text: blockText(b) }), 'ScaDS.AI antwortet meist in 5–20 Sekunden');
      if (!r.length) { toast('Keine auffälligen Namen gefunden.', 'ok'); return; }
      const picked = new Set(r.map((_, i) => i));
      modal({ title: 'Namensprüfung', body: h('div', { class: 'col' }, r.map((x, i) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: true, onChange: (e) => (e.target.checked ? picked.add(i) : picked.delete(i)) }), h('span', {}, `„${x.falsch}“ → „${x.richtig}“`)))),
        actions: [{ label: 'Abbrechen' }, { label: 'Übernehmen', kind: 'primary', onClick: () => {
          const fix = (s) => r.reduce((acc, x, i) => (picked.has(i) ? acc.split(x.falsch).join(x.richtig) : acc), s);
          if (b.modus === 'stichpunkte') b.stichpunkte = b.stichpunkte.map(fix); else { b.text = fix(b.text); b.markup = ''; }
          E.touch(); redraw(); } }] });
    } catch (e) { toast(e.message, 'err'); }
  }
  async function aiImages(b) {
    try {
      const terms = await busy('KI sucht Bild-Ideen …', api.post('/api/llm/search-terms', { text: blockText(b) }), 'ScaDS.AI antwortet meist in 5–20 Sekunden');
      if (!terms.length) { toast('Keine Vorschläge erhalten.', 'info'); return; }
      toast(`Ideen: ${terms.join(', ')} – im Bild-Picker danach suchen.`, 'ok', 9000);
      addMedia(b, null);
    } catch (e) { toast(e.message, 'err'); }
  }

  // ---- Kommentarblock ----
  function blockEl(s, b, si) {
    const isB = b.modus === 'stichpunkte';
    let mt = null, ta = null, rich = null;
    const info = h('span', { class: 'help' });
    const upd = () => { const n = isB ? b.stichpunkte.length : wordsOf(b.text).length; info.textContent = isB ? `${n} Stichpunkte` : `${n} Wörter · ca. ${(n / S.settings.thresholds.words_per_second).toFixed(0)} s`; };
    if (isB) {
      ta = h('textarea', { rows: 4, class: 'bullets-ta', placeholder: 'Ein Stichpunkt pro Zeile – wird frei ausformuliert gesprochen', value: b.stichpunkte.join('\n'),
        onInput: (e) => { b.stichpunkte = e.target.value.split('\n').map((l) => l.replace(/^\s*[-•*]\s*/, '').trim()).filter(Boolean); upd(); E.touch(); } });
    } else {
      mt = markedTextarea({ value: b.markup || b.text, rows: 3, placeholder: 'Kommentar zu diesem Segment … (Formatierung: Leiste oben, z. B. Strg+B für fett)', anchors: () => b.anker || [],
        onInput: (v) => { if (hasMarkup(v)) { b.markup = v; b.text = plain(v); } else { b.markup = ''; b.text = v; } upd(); E.touch(); }, onFocus: () => { E.focusBlock = b; } });
      ta = mt.textarea;
      const view = h('div', { class: 'rt-preview', hidden: true });
      const bar = toolbar(ta, { onPreview: () => {
        const on = view.hidden;
        view.hidden = !on; mt.el.hidden = on;
        if (on) view.replaceChildren(render(b.markup || b.text));
      } });
      rich = h('div', { class: 'rt-wrap' }, bar, mt.el, view);
    }
    upd();
    const spk = h('div', { class: 'seg' }, ['philipp', 'danny'].map((k) => h('button', { class: b.sprecher === k ? 'on' : '', onClick: () => { b.sprecher = k; E.touch(); redraw(); } }, k === 'philipp' ? 'Philipp' : 'Danny')));
    const mode = h('div', { class: 'seg' }, [['text', 'Text'], ['stichpunkte', 'Stichpunkte']].map(([k, l]) => h('button', { class: b.modus === k ? 'on' : '', onClick: () => {
      if (k === b.modus) return;
      if (k === 'stichpunkte') { b.stichpunkte = b.text.split(/\n|(?<=[.!?])\s+/).map((x) => x.trim()).filter(Boolean); b.text = ''; } else { b.text = b.stichpunkte.join(' '); b.stichpunkte = []; }
      b.modus = k; b.anker = []; b.markup = ''; E.touch(); redraw(); } }, l)));
    const segSel = (s.segmente.length > 1) ? h('select', { class: 'seg-move', title: 'Zu welchem Segment gehört der Kommentar?', onChange: (e) => { b.segment = +e.target.value; E.touch(); redraw(); } }, s.segmente.map((g, i) => h('option', { value: i, selected: i === si }, `Segment ${i + 1}`))) : null;
    const chips = (b.anker || []).map((a, ai) => h('div', { class: 'achip', style: { borderLeftColor: colorOf(ai) }, title: 'Klicken: Bereich ändern' , onClick: () => rangeDialog(b, a) },
      thumbOf(a) ? h('img', { src: thumbOf(a), loading: 'lazy' }) : h('div', { class: 'achip-noimg' }, icon(a.karte ? 'map' : 'image')),
      h('div', { class: 'achip-t' }, h('b', {}, nameOf(a)), h('small', {}, rangeText(b, a))),
      a.karte ? btn('', { icon: 'edit', size: 'sm', kind: 'ghost', title: 'Karte einzeichnen', onClick: (ev) => { ev.stopPropagation(); const m = E.maps.find((x) => x.id === a.karte); if (m) openMapEditor(m, (saved) => { Object.assign(m, saved); redraw(); }); } }) : null,
      btn('', { icon: 'x', size: 'sm', kind: 'ghost', title: 'Einblendung entfernen', onClick: (ev) => { ev.stopPropagation(); b.anker = b.anker.filter((x) => x !== a); E.touch(); redraw(); } })));
    return h('div', { class: `block ${b.sprecher}` },
      h('div', { class: 'block-head' }, spk, mode, segSel, h('span', { class: 'grow' }), info,
        btn('', { icon: 'trash', kind: 'ghost', size: 'sm', title: 'Kommentar löschen', onClick: async () => { if (await confirmBox('Kommentar löschen?', 'Dieser Kommentar wird entfernt.', 'Löschen', true)) { s.kommentar = s.kommentar.filter((x) => x !== b); E.touch(); redraw(); } } })),
      rich || ta,
      h('div', { class: 'block-foot' }, ...chips, btn('Bild / Karte einblenden', { size: 'sm', icon: 'image', title: 'Wörter im Text markieren, dann klicken: ab dort wird das Bild eingeblendet', onClick: () => addMedia(b, ta) }),
        h('span', { class: 'grow' }),
        b.gesprochen ? h('span', { class: 'help', title: b.gesprochen }, icon('mic'), ' aufgenommen') : null,
        aiOn() ? btn('', { icon: 'sparkle', size: 'sm', kind: 'ghost', title: 'KI: Namen prüfen', onClick: () => aiNames(b) }) : null, aiOn() ? btn('', { icon: 'wand', size: 'sm', kind: 'ghost', title: 'KI: Bild-Ideen', onClick: () => aiImages(b) }) : null));
  }

  // Welche Szenen überdeckt das Segment? (ganze Szene / Teil einer Szene / mehrere Szenen)
  function spanChip(s, si) {
    const info = s.segmente_info?.[si];
    if (!info || !info.nr.length) return null;
    const nr = info.nr, a = info.anteil || {};
    const whole = nr.length === 1 && (a[info.szenen[0]] || 0) >= 0.97;
    const txt = nr.length > 1 ? `über Szenen ${nr[0]}–${nr.at(-1)}` : whole ? `ganze Szene ${nr[0]}` : `Teil von Szene ${nr[0]}`;
    return h('span', { class: `chip ${nr.length > 1 ? 'accent' : ''}`, title: 'Dieses Segment liegt in den Szenen (Messeinheiten) ' + nr.join(', ') }, txt);
  }

  // Segment über mehrere Szenen: von dieser Szene bis zu einer späteren
  function pickSpan(s) {
    const units = (E.scenes?.() || []).filter((x) => x.bereich).sort((x, y) => x.bereich[0] - y.bereich[0]);
    const from = units.findIndex((x) => x.id === s.id);
    if (from < 0) return;
    const later = units.slice(from + 1, from + 41);
    if (!later.length) { toast('Nach dieser Szene folgt keine weitere.', 'info'); return; }
    let to = later[0].id;
    const sel = h('select', { onChange: (e) => { to = e.target.value; } }, later.map((x) => h('option', { value: x.id }, `Szene ${x.nr} · ${fmtTC(x.bereich[0]).slice(0, 5)}–${fmtTC(x.bereich[1]).slice(0, 5)}${x.titel ? ' · ' + x.titel : ''}`)));
    modal({ title: 'Segment über mehrere Szenen', body: h('div', { class: 'col' }, h('p', { class: 'help' }, `Das Segment beginnt am Anfang von Szene ${s.nr} und endet am Ende der gewählten Szene. Den Feinschnitt machst du danach über Anfang/Ende.`), field('Bis einschließlich', sel)),
      actions: [{ label: 'Abbrechen' }, { label: 'Segment anlegen', kind: 'primary', onClick: () => { const end = units.find((x) => x.id === to); E.addSegment(s.bereich[0], end.bereich[1]); } }] });
  }

  // ---- Segmentkarte ----
  function cardEl(s, g, si) {
    const color = segColor(si);
    const dur = Math.max(0, g.out - g.in), light = s.report?.segments?.[si]?.light || 'gruen';
    const tin = h('input', { type: 'text', value: fmtTC(g.in), title: 'Anfang (mm:ss.zz)', onChange: (e) => { const v = parseTC(e.target.value); if (v != null) { g.in = v; E.touch(); } redraw(); } });
    const tout = h('input', { type: 'text', value: fmtTC(g.out), title: 'Ende (mm:ss.zz)', onChange: (e) => { const v = parseTC(e.target.value); if (v != null) { g.out = v; E.touch(); } redraw(); } });
    const mine = s.kommentar.filter((b) => b.segment === si);
    const allAnchors = mine.flatMap((b) => b.anker || []);
    const dlg = dialogOf(g);
    const body = [
      dlg ? h('div', { class: 'seg-dialog', title: 'Gesprochener Text der Episode an dieser Stelle' }, icon('mic'), h('span', {}, `„${dlg}“`)) : (E.dialog.available ? h('div', { class: 'seg-dialog faint' }, 'Hier wird nichts gesprochen.') : null),
      h('input', { type: 'text', class: 'seg-notiz', placeholder: 'Notiz / Kontext (erscheint als Regieanweisung im Sprecherskript)', value: g.notiz || '', onInput: (e) => { g.notiz = e.target.value; E.touch(); } }),
      ...mine.map((b) => blockEl(s, b, si)),
      h('div', { class: 'row gap-s' }, btn('Kommentar hinzufügen', { size: 'sm', icon: 'plus', onClick: () => addBlock(s, si) }))];
    const el = h('div', { class: 'seg-card', id: `segcard-${si}`, style: { borderLeftColor: color } },
      h('div', { class: 'seg-card-head' },
        h('span', { class: 'seg-no', style: { background: color } }, String(si + 1)),
        btn('Abspielen', { icon: 'play', size: 'sm', kind: 'primary', class: 'playseg', title: 'Dieses Segment abspielen', onClick: () => E.player.playRange(g.in, g.out) }),
        tin, h('span', { class: 'faint' }, '–'), tout,
        h('span', { class: `pill ${LIGHT[light] || ''}`, title: 'Längenampel' }, `${dur.toFixed(1)} s`),
        h('span', { class: 'span-slot' }, spanChip(s, si)),
        h('span', { class: 'grow' }),
        ...allAnchors.slice(0, 4).map((a) => h('img', { class: 'mini-thumb', src: thumbOf(a), title: nameOf(a) })),
        mine.length ? h('span', { class: 'chip', title: 'Kommentare' }, icon('edit'), String(mine.length)) : null,
        btn('', { icon: 'trash', size: 'sm', kind: 'ghost', title: 'Segment entfernen', onClick: () => removeSegment(s, si) })),
      h('div', { class: 'seg-card-body' }, ...body.filter(Boolean)));
    el.addEventListener('mousedown', (e) => { if (e.target.closest('input,textarea,select,button,.achip')) return; E.player.seek(g.in); });
    return el;
  }

  function addBlock(s, si) {
    const last = s.kommentar.filter((b) => b.segment === si).at(-1) || s.kommentar.at(-1);
    s.kommentar.push({ sprecher: last?.sprecher === 'philipp' ? 'danny' : 'philipp', modus: 'text', text: '', stichpunkte: [], gesprochen: '', anker: [], segment: si });
    E.touch(); redraw();
    const tas = host.querySelectorAll(`#segcard-${si} .mt-ta`);
    tas[tas.length - 1]?.focus();
  }
  async function removeSegment(s, si) {
    const n = s.kommentar.filter((b) => b.segment === si).length;
    if (n && !(await confirmBox('Segment entfernen?', `Die ${n} Kommentar(e) dieses Segments werden mit entfernt.`, 'Entfernen', true))) return;
    s.kommentar = s.kommentar.filter((b) => b.segment !== si);
    s.kommentar.forEach((b) => { if (b.segment > si) b.segment -= 1; });
    s.segmente.splice(si, 1);
    E.touch(); redraw(); E.player.drawTimeline(); E.player.drawDialog();
  }

  function redraw() {
    const s = E.sel();
    const scrollTop = host.parentElement?.scrollTop;
    if (!s) { host.replaceChildren(); return; }
    const parts = s.segmente.map((g, i) => cardEl(s, g, i));
    const orphan = s.segmente.length ? [] : s.kommentar;
    const tools = s.bereich ? h('div', { class: 'row gap-s wrap seg-tools' },
      btn('Ganze Szene als Segment', { size: 'sm', icon: 'plus', title: 'Der komplette Zeitbereich dieser Szene wird ein Segment', onClick: () => E.addSegment(s.bereich[0], s.bereich[1]) }),
      btn('Über mehrere Szenen …', { size: 'sm', icon: 'layers', title: 'Segment von dieser Szene bis zu einer späteren Szene', onClick: () => pickSpan(s) }),
      h('span', { class: 'help' }, 'oder im Player mit I/O (Anfang/Ende) und im Dialog beliebige Stellen markieren')) : null;
    if (!s.segmente.length) {
      parts.push(h('div', { class: 'card seg-empty' }, icon('scissors'), h('div', {}, h('b', {}, 'Diese Szene ist (noch) nicht im Video'),
        h('p', { class: 'help' }, 'Szenen sind nur Messeinheiten. Markiere die Stelle, die ins Video soll – ganz oder in Teilen, auch über Szenengrenzen hinweg. Nur Segmente werden übernommen.'))));
      if (orphan.length) parts.push(h('div', { class: 'banner' }, icon('alert'), `${orphan.length} Kommentar(e) ohne Segment – lege zuerst ein Segment an, dann verschiebe sie dorthin.`));
    }
    if (tools) parts.push(tools);
    if ((s.beruehrt || []).length) parts.push(h('div', { class: 'card tight seg-foreign' }, h('div', { class: 'help' }, icon('scissors'), ` In diese Szene reicht ${s.beruehrt.length === 1 ? 'ein Segment' : s.beruehrt.length + ' Segmente'} aus anderen Szenen hinein:`),
      ...s.beruehrt.map((t) => h('div', { class: 'row gap-s' }, h('span', { class: 'chip' }, `Szene ${t.nr || '?'} · Segment ${t.index + 1}`), h('span', { class: 'mono faint' }, `${fmtTC(t.in)} – ${fmtTC(t.out)}`), h('span', { class: 'grow' }), btn('Dorthin', { size: 'sm', kind: 'ghost', onClick: () => E.gotoScene?.(t.scene) })))));
    host.replaceChildren(...parts);
    if (scrollTop != null && host.parentElement) host.parentElement.scrollTop = scrollTop;
  }
  function updateSpans() {          // Szenen-Hinweise nach dem Speichern auffrischen, ohne Textfelder neu zu zeichnen
    const s = E.sel(); if (!s) return;
    host.querySelectorAll('.seg-card').forEach((c) => { const si = +c.id.replace('segcard-', ''); const slot = c.querySelector('.span-slot'); if (slot) slot.replaceChildren(...[spanChip(s, si)].filter(Boolean)); });
  }
  return { el: host, redraw, updateSpans, focus(i) { const c = host.querySelector(`#segcard-${i}`); c?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); c?.classList.add('flash'); setTimeout(() => c?.classList.remove('flash'), 900); }, addBlock };
}
