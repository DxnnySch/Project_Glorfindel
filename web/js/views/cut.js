import { h, btn, runJob, toast, fmtDur, icon, empty } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep, d = S.data;
  let versions = await api.get(epUrl(ep, '/rough-cut'));
  const sources = d.sources;
  const stillSel = h('select', {}, h('option', { value: '' }, 'Standbilder aus Referenz'), sources.map((s) => h('option', { value: s.id }, `${s.role}: ${s.path.split('/').pop()}`)));
  const strand = h('input', { type: 'checkbox', checked: true }), stills = h('input', { type: 'checkbox', checked: true });
  const out = h('div', { class: 'col' });
  const draw = () => out.replaceChildren(...(versions.length ? [...versions].reverse().map((v) => h('div', { class: 'card tight row' }, h('b', {}, `Version ${v.version}`), h('span', { class: 'muted grow' }, new Date(v.modified * 1000).toLocaleString('de-DE')),
    btn('Schnittpaket (.json)', { size: 'sm', icon: 'download', onClick: () => { location.href = epUrl(ep, `/rough-cut/${v.version}/json`); } }),
    v.xml ? btn('Premiere-XML', { size: 'sm', icon: 'download', onClick: () => { location.href = epUrl(ep, `/rough-cut/${v.version}/xml`); } }) : null)) : [h('p', { class: 'help' }, 'Noch kein Rohschnitt erzeugt.')]));
  const result = h('div');
  const build = async () => {
    try {
      const r = await runJob('Rohschnitt wird erzeugt …', () => api.post(epUrl(ep, '/rough-cut'), { still_source: stillSel.value || null, by_strand: strand.checked, with_stills: stills.checked }));
      versions = await api.get(epUrl(ep, '/rough-cut')); draw();
      result.replaceChildren(h('div', { class: 'card col' }, h('h2', {}, `Version ${r.version} erzeugt`), h('div', { class: 'row gap-l wrap' }, h('span', {}, `Länge ${fmtDur(r.duration)}`), h('span', {}, `${r.markers} Marker`), r.stills ? h('span', {}, 'Standbilder erzeugt') : null),
        (r.warnings || []).length ? h('div', { class: 'banner' }, icon('alert'), h('div', {}, r.warnings.map((w) => h('div', {}, w)))) : h('div', { class: 'banner info' }, icon('check'), 'Keine Warnungen.')));
      toast('Rohschnitt fertig.', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  };
  draw();
  const unaligned = d.scenes.filter((s) => s.status !== 'abgeglichen').length;
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Rohschnitt'), h('p', {}, 'Erzeugt das Schnittpaket für Premiere (Serien-Clips, Kommentar, Standbilder, Bildeinblendungen, Marker). Das Premiere-Panel liest die .json; als Fallback gibt es eine FCP-XML.')), btn('Rohschnitt erzeugen', { kind: 'primary', icon: 'scissors', onClick: build })),
    unaligned ? h('div', { class: 'banner', style: { marginBottom: '14px' } }, icon('alert'), `${unaligned} Szene(n) sind noch nicht mit einer Aufnahme abgeglichen – sie erhalten geschätzte Längen.`) : null,
    h('div', { class: 'card col', style: { marginBottom: '16px' } }, h('h2', {}, 'Optionen'), h('div', { class: 'row wrap gap-l' }, h('label', { class: 'check' }, strand, 'Nach Strängen sortieren'), h('label', { class: 'check' }, stills, 'Standbilder erzeugen'), stillSel)),
    result, h('h3', { style: { margin: '18px 0 10px' } }, 'Versionen'), out));
}
