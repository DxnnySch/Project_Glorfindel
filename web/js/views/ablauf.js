// Ablauf: die Reihenfolge, in der Szenen/Segmente im Video und im Word erscheinen – Stränge und einzelne Szenen per Ziehen sortieren.
import { h, btn, icon, toast, empty, fmtDur, remember, thumbOfAsset, thumbOfMap } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S, strandOf } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep;
  const [scenes, assets, maps] = await Promise.all([api.get(epUrl(ep, '/scenes')), api.get(epUrl(ep, '/assets')), api.get(epUrl(ep, '/maps'))]);
  const manual = (S.data.project.ablauf || []).length > 0;
  let order = [...scenes].sort((a, b) => a.ablauf_pos - b.ablauf_pos);   // nicht nach `ausgabe`: die fehlt Szenen ohne Segment/Kommentar
  const host = h('div', { class: 'col' });
  let drag = null;   // { kind: 'scene'|'group', ids: [...] }

  const save = async (ids, msg) => {
    try { await api.put(epUrl(ep, '/ablauf'), { order: ids }); toast(msg, 'ok', 1800); ctx.refresh(); } catch (e) { toast(e.message, 'err'); }
  };
  const move = (ids, beforeId) => {
    const all = order.map((s) => s.id).filter((i) => !ids.includes(i));
    const pos = beforeId == null ? all.length : all.indexOf(beforeId);
    all.splice(pos < 0 ? all.length : pos, 0, ...ids);
    save(all, 'Reihenfolge gespeichert.');
  };
  const groups = [];
  order.forEach((s) => { const g = groups.at(-1); if (g && g.strang === (s.strang || '')) g.scenes.push(s); else groups.push({ strang: s.strang || '', scenes: [s] }); });

  const thumbs = (s) => s.kommentar.flatMap((b) => b.anker || []).slice(0, 4).map((a) => { const it = a.karte ? maps.find((m) => m.id === a.karte) : assets.find((x) => x.id === a.asset); return it ? h('img', { class: 'mini-thumb', src: a.karte ? thumbOfMap(it) : thumbOfAsset(it) }) : null; }).filter(Boolean);
  const row = (s, i) => {
    const st = strandOf(s.strang);
    const el = h('div', { class: 'ab-row', draggable: 'true', onDragstart: (e) => { drag = { kind: 'scene', ids: [s.id] }; e.dataTransfer.setData('text/plain', s.id); e.stopPropagation(); },
      onDragover: (e) => { e.preventDefault(); el.classList.add('over'); }, onDragleave: () => el.classList.remove('over'),
      onDrop: (e) => { e.preventDefault(); e.stopPropagation(); el.classList.remove('over'); if (drag && !drag.ids.includes(s.id)) move(drag.ids, s.id); drag = null; },
      onClick: () => { location.hash = `#/${ep.season}/${ep.episode}/editor?id=${s.id}`; } },
    h('span', { class: 'faint', style: { cursor: 'grab' } }, '⋮⋮'), h('span', { class: 'no mono' }, String(order.indexOf(s) + 1).padStart(2, '0')),
    h('b', { class: 'grow' }, s.titel || s.id, s.fixiert ? icon('lock') : null),
    h('span', { class: 'chip', title: 'Segmente' }, icon('scissors'), String(s.segmente.length)), h('span', { class: 'chip', title: 'Kommentare' }, icon('edit'), String(s.kommentar.length)),
    ...thumbs(s), h('span', { class: 'mono help', style: { width: '64px', textAlign: 'right' } }, fmtDur((s.report?.series_s || 0) + (s.report?.comment_s || 0))));
    return el;
  };
  const draw = () => {
    host.replaceChildren(...(order.length ? groups.map((g) => {
      const st = strandOf(g.strang);
      const box = h('div', { class: 'ab-group', style: { borderLeftColor: st?.color || 'var(--line)' }, onDragover: (e) => { e.preventDefault(); }, onDrop: (e) => { e.preventDefault(); if (drag && !g.scenes.some((x) => drag.ids.includes(x.id))) move(drag.ids, g.scenes[0].id); drag = null; } },
        h('div', { class: 'ab-head', draggable: 'true', onDragstart: (e) => { drag = { kind: 'group', ids: g.scenes.map((x) => x.id) }; e.dataTransfer.setData('text/plain', 'g'); }, title: 'Den ganzen Block ziehen' },
          h('span', { class: 'faint', style: { cursor: 'grab' } }, '⋮⋮'), h('i', { class: 'dot', style: { background: st?.color || 'var(--faint)' } }), h('b', { class: 'grow' }, st?.name || 'Ohne Strang'), h('span', { class: 'badge' }, g.scenes.length)),
        ...g.scenes.map(row));
      return box;
    }) : [empty('layers', 'Noch keine Szenen', 'Lege im Strang-Board Szenen an.')]));
    host.append(h('div', { class: 'ab-end', onDragover: (e) => e.preventDefault(), onDrop: (e) => { e.preventDefault(); if (drag) move(drag.ids, null); drag = null; } }, 'Hierher ziehen = ans Ende'));
  };
  draw();
  main.append(h('div', { class: 'page', style: { maxWidth: '1000px' } },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Ablauf'), h('p', {}, 'So folgen die Szenen im Video und im Word aufeinander. Ganze Stränge (Kopfzeile) oder einzelne Szenen per Ziehen verschieben – z. B. wenn zwei Stränge im Lauf der Folge zusammenkommen.')),
      btn('Automatisch nach Strängen', { icon: 'refresh', disabled: !manual, title: 'Manuelle Anpassungen verwerfen', onClick: () => save([], 'Reihenfolge: automatisch nach Strängen.') }),
      btn('Strang-Reihenfolge …', { icon: 'layers', onClick: () => ctx.go('board') })),
    h('div', { class: manual ? 'banner info' : 'help', style: { marginBottom: '12px' } }, manual ? [icon('info'), 'Manuelle Reihenfolge aktiv. Änderungen an der Strang-Reihenfolge wirken erst nach „Automatisch nach Strängen“.'] : 'Aktuell automatisch nach der Strang-Reihenfolge sortiert. Verschiebst du etwas, wird die Reihenfolge manuell.'),
    host));
}
