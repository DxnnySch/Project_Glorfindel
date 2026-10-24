import { h, btn, runJob, toast, fmtDur, icon, empty, remember } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep, d = S.data;
  let versions = await api.get(epUrl(ep, '/rough-cut'));
  const sources = d.sources;
  const stillSel = h('select', {}, h('option', { value: '' }, 'Standbilder aus Referenz'), sources.map((s) => h('option', { value: s.id }, `${s.role}: ${s.path.split('/').pop()}`)));
  const ui = remember(`${S.ep.season}-${S.ep.episode}:cut`, { strand: true, stills: true, still: '' });
  const strand = h('input', { type: 'checkbox', checked: ui.strand, onChange: (e) => { ui.strand = e.target.checked; } }), stills = h('input', { type: 'checkbox', checked: ui.stills, onChange: (e) => { ui.stills = e.target.checked; } });
  stillSel.value = ui.still || ''; stillSel.addEventListener('change', () => { ui.still = stillSel.value; });
  const out = h('div', { class: 'col' });
  const draw = () => out.replaceChildren(...(versions.length ? [...versions].reverse().map((v) => h('div', { class: 'card tight row' }, h('b', {}, `Version ${v.version}`), h('span', { class: 'muted grow' }, new Date(v.modified * 1000).toLocaleString('de-DE')),
    btn('Ansehen', { size: 'sm', onClick: () => showPkg(v) }),
    btn('Schnittpaket (.json)', { size: 'sm', icon: 'download', onClick: () => { location.href = epUrl(ep, `/rough-cut/${v.version}/json`); } }),
    v.xml ? btn('Premiere-XML', { size: 'sm', icon: 'download', onClick: () => { location.href = epUrl(ep, `/rough-cut/${v.version}/xml`); } }) : null)) : [h('p', { class: 'help' }, 'Noch kein Rohschnitt erzeugt.')]));
  const bridgeHint = h('div', { class: 'banner info', style: { marginBottom: '14px' } }, icon('video'), h('span', {}, 'Besser als die XML: Rohschnitt direkt in Premiere bauen (mit Effekten, Credits, Animationen) und später Proxy gegen HQ tauschen. '), btn('Zur Premiere-Ansicht', { size: 'sm', kind: 'primary', onClick: () => ctx.go('premiere') }));
  const result = h('div'), preview = h('div');
  const COLORS = { scene_segment: '#4da3e0', scene_audio: '#3b7fb0', still: '#8e97a8', comment: '#d4aa4f', artwork: '#4cc38a', map: '#b06be0', credit: '#e0524d', anim: '#e9b44c', free_block: '#5d6678', fx: '#7ee0a0' };
  const showPkg = async (v, host = preview) => {
    let pkg; try { pkg = await api.get(epUrl(ep, `/rough-cut/${v.version}/json`)); } catch { return; }
    const dur = pkg.duration || 1, zoom = h('input', { type: 'range', min: 1, max: 12, value: 1, step: 0.5, style: { width: '160px' } });
    const rows = h('div', { class: 'timeline', style: { overflowX: 'auto' } });
    const draw = () => {
      const W = Math.max(900, rows.parentElement?.clientWidth || 900) * +zoom.value, px = (s) => `${s / dur * W}px`;
      rows.replaceChildren(h('div', { style: { position: 'relative', height: '22px', width: `${W + 110}px`, marginLeft: '110px' } }, ...pkg.markers.filter((m) => m.kind === 'scene').map((m) => h('span', { class: 'mono', title: m.text, style: { position: 'absolute', left: px(m.time), fontSize: '10px', color: 'var(--faint)', borderLeft: '1px solid var(--line)', paddingLeft: '2px', whiteSpace: 'nowrap' } }, m.text.slice(0, 9)))),
        ...Object.entries(pkg.tracks).sort(([a], [b]) => a.localeCompare(b, 'de', { numeric: true })).map(([name, clips]) => h('div', { style: { display: 'flex', borderTop: '1px solid var(--line)', width: `${W + 110}px` } },
          h('div', { class: 'mono muted', style: { width: '110px', padding: '8px', flex: 'none', position: 'sticky', left: 0, background: 'var(--panel)', zIndex: 1 } }, name),
          h('div', { style: { position: 'relative', height: '30px', width: `${W}px` } }, ...clips.map((c) => h('div', { title: `${c.type} ${c.scene || ''} ${(c.text || c.title || c.name || '')} · ${(c.end - c.start).toFixed(1)} s`, style: { position: 'absolute', left: px(c.start), width: `${Math.max(2, (c.end - c.start) / dur * W)}px`, top: '4px', bottom: '4px', background: COLORS[c.type] || '#888', borderRadius: '3px', opacity: .85 } }))))));
    };
    zoom.addEventListener('input', draw);
    host.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, `Vorschau Version ${v.version} · ${fmtDur(pkg.duration)}`), h('span', { class: 'help' }, 'Zoom'), zoom),
      rows, h('div', { class: 'row wrap gap-s', style: { marginTop: '8px' } }, Object.entries(COLORS).map(([k, c]) => h('span', { class: 'chip' }, h('i', { class: 'dot', style: { background: c } }), k)))),
      pkg.warnings?.length ? h('div', { class: 'card', style: { marginTop: '12px' } }, h('h2', { style: { marginBottom: '8px' } }, `Warnungen (${pkg.warnings.length})`),
        pkg.warnings.map((w) => { const id = (w.match(/\[(sz_\d+)\]/) || [])[1]; return h('div', { class: 'row', style: { padding: '5px 0', borderTop: '1px solid var(--line)' } }, icon('alert'), h('span', { class: 'grow' }, w), id ? btn('Zur Szene', { size: 'sm', onClick: () => { location.hash = `#/${ep.season}/${ep.episode}/editor?id=${id}`; } }) : null); })) : null);
    draw();
  };
  if (versions.length) showPkg(versions.at(-1));
  const build = async () => {
    try {
      const r = await runJob('Rohschnitt wird erzeugt …', () => api.post(epUrl(ep, '/rough-cut'), { still_source: stillSel.value || null, by_strand: strand.checked, with_stills: stills.checked }));
      versions = await api.get(epUrl(ep, '/rough-cut')); draw(); showPkg(versions.at(-1));
      result.replaceChildren(h('div', { class: 'card col' }, h('h2', {}, `Version ${r.version} erzeugt`), h('div', { class: 'row gap-l wrap' }, h('span', {}, `Länge ${fmtDur(r.duration)}`), h('span', {}, `${r.markers} Marker`), r.stills ? h('span', {}, 'Standbilder erzeugt') : null),
        (r.warnings || []).length ? h('div', { class: 'banner' }, icon('alert'), h('div', {}, r.warnings.map((w) => h('div', {}, w)))) : h('div', { class: 'banner info' }, icon('check'), 'Keine Warnungen.')));
      toast('Rohschnitt fertig.', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  };
  draw();
  const unaligned = d.scenes.filter((s) => s.status !== 'abgeglichen').length;
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Rohschnitt'), h('p', {}, 'Erzeugt das Schnittpaket für Premiere (Serien-Clips, Kommentar, Standbilder, Bildeinblendungen, Marker). Das Premiere-Panel liest die .json; als Fallback gibt es eine FCP-XML.')), btn('Rohschnitt erzeugen', { kind: 'primary', icon: 'scissors', onClick: build })),
    bridgeHint,
    unaligned ? h('div', { class: 'banner', style: { marginBottom: '14px' } }, icon('alert'), `${unaligned} Szene(n) sind noch nicht mit einer Aufnahme abgeglichen – sie erhalten geschätzte Längen.`) : null,
    h('div', { class: 'card col', style: { marginBottom: '16px' } }, h('h2', {}, 'Optionen'), h('div', { class: 'row wrap gap-l' }, h('label', { class: 'check' }, strand, 'Nach Strängen sortieren'), h('label', { class: 'check' }, stills, 'Standbilder erzeugen'), stillSel)),
    result, preview, h('h3', { style: { margin: '18px 0 10px' } }, 'Versionen'), versions.length ? h('p', { class: 'help' }, `Ablage: ${versions.at(-1).path}`) : null, out));
}
