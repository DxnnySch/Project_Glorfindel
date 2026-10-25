// Effekte an Clips: Komponente anhängen, Parameter setzen (statisch oder mit Keyframes), eingebaute Effekte.
// `locate()` ist eine Funktion, die den Clip FRISCH liefert (Objekte werden bei jeder Projektänderung ungültig, siehe core.js).
'use strict';

const { tt, tx, txp, errText, retryStale } = require('./core');

// Anzeigenamen eingebauter Effekte/Parameter in beiden Oberflächensprachen.
const NAMES = {
  motion: ['Motion', 'Bewegung'],
  opacity: ['Opacity', 'Deckkraft'],
  position: ['Position'],
  scale: ['Scale', 'Skalieren', 'Skalierung'],
  crop: { left: ['Left', 'Links'], top: ['Top', 'Oben'], right: ['Right', 'Rechts'], bottom: ['Bottom', 'Unten'] },
};

// Mögliche interne Namen je Effekt; der echte wird zur Laufzeit über die Liste der installierten Effekte bestimmt.
const FILTER_HINTS = {
  'AE.ADBE Crop': { alt: ['AE.ADBE AECrop', 'ADBE Crop'], display: ['Zuschneiden', 'Crop'] },
  'AE.ADBE Geometry': { alt: ['AE.ADBE Geometry2'], display: ['Transformieren', 'Transform'] },
};

async function listComponents(chain) {
  const out = [];
  const n = chain.getComponentCount();
  for (let i = 0; i < n; i++) {
    const c = chain.getComponentAtIndex(i);
    let name = '';
    try { name = await c.getDisplayName(); } catch (e) { /* ohne Namen */ }
    out.push({ index: i, name, comp: c });
  }
  return out;
}

function paramList(comp) {
  const out = [];
  for (let i = 0; i < comp.getParamCount(); i++) {
    const p = comp.getParam(i);
    out.push({ index: i, name: p.displayName || '', param: p });
  }
  return out;
}

/** Parameter suchen: erst nach Namen (mehrere Sprachen), dann nach Listenposition. */
function findParam(comp, names, index) {
  const list = paramList(comp);
  const want = (Array.isArray(names) ? names : [names]).filter(Boolean).map((n) => String(n).toLowerCase());
  if (index != null && list[index] && want.includes(String(list[index].name).toLowerCase())) return list[index].param;   // doppelte Namen (Zufallsparameter): Position gewinnt
  const byName = list.find((p) => want.includes(String(p.name).toLowerCase()));
  if (byName) return byName.param;
  if (index != null && list[index]) return list[index].param;
  return null;
}

/** Wert aus dem Plan (Zahl, Wahrheitswert, {point}, {argb16}) in einen Premiere-Wert umwandeln. */
function toPproValue(ppro, v, ctx) {
  if (v && typeof v === 'object' && v.point) return new ppro.PointF(v.point[0], v.point[1]);
  if (v && typeof v === 'object' && v.argb16) {
    const [a, r, g, b] = v.argb16.map((x) => x >> 8);                   // 16 Bit -> 8 Bit
    const mode = (ctx && ctx.colorMode) || 'unit';                       // Premiere-Doku: Color-Werte liegen in [0.0, 1.0]
    if (mode === 'byte') return new ppro.Color(r, g, b, a);
    if (mode === 'word') return new ppro.Color(r * 257, g * 257, b * 257, a * 257);
    return new ppro.Color(r / 255, g / 255, b / 255, a / 255);
  }
  return v;
}

/** Interner Effektname in der installierten Premiere-Version bestimmen (zuerst genau, dann ohne „AE.“-Präfix, dann per Anzeigename). */
async function resolveMatchName(ppro, wanted, ctx) {
  const cands = Array.isArray(wanted) ? [...wanted] : [wanted];
  const hint = FILTER_HINTS[cands[0]];
  if (hint) cands.push(...hint.alt);
  if (!ctx.filters) ctx.filters = { m: await ppro.VideoFilterFactory.getMatchNames(), d: await ppro.VideoFilterFactory.getDisplayNames() };
  const { m, d } = ctx.filters;
  for (const c of cands) if (m.includes(c)) return c;
  for (const c of cands) {
    const base = c.replace(/^AE\./, '');
    const hit = m.find((x) => x === base || x === 'AE.' + base);
    if (hit) return hit;
  }
  const names = [...((hint && hint.display) || []), ...(ctx.displayHints || [])].map((x) => x.toLowerCase());
  for (const n of names) {
    const i = d.findIndex((x) => String(x).toLowerCase() === n);
    if (i >= 0) return m[i];
  }
  const base = cands[0].replace(/^AE\./, '').replace(/^ADBE\s*/, '').toLowerCase();
  const similar = m.filter((x) => x.toLowerCase().includes(base.split(' ')[0])).slice(0, 8);
  throw new Error('Effekt „' + cands[0] + '“ gibt es in dieser Premiere-Version nicht' + (similar.length ? ' (ähnlich: ' + similar.join(', ') + ')' : ''));
}

/** Alle Aktionen für einen Parameter in EINER Transaktion (Keyframes brauchen vorher „zeitabhängig“). */
async function setParam(ppro, project, param, spec, ctx) {
  const kfs = spec.keyframes;
  if (kfs && kfs.length) {
    await txp(ppro, 'Keyframes', (add) => {
      add(param.createSetTimeVaryingAction(true));
      for (const [t, val] of kfs) {
        const k = param.createKeyframe(toPproValue(ppro, val, ctx));
        k.position = tt(ppro, t + ((ctx && ctx.offset) || 0));
        add(param.createAddKeyframeAction(k));
      }
    });
    return 'keyframes';
  }
  if (spec.value === undefined || spec.value === null) return 'unveraendert';
  await txp(ppro, 'Wert', (add) => add(param.createSetValueAction(param.createKeyframe(toPproValue(ppro, spec.value, ctx)), true)));
  return 'wert';
}

/** Komponente `index` des Clips frisch holen. */
async function componentAt(locate, index) {
  const chain = await (await locate()).getComponentChain();
  return chain.getComponentAtIndex(index);
}

/** Position einer eingebauten Komponente (Bewegung/Deckkraft) in der Kette bestimmen. */
async function builtinIndex(locate, kind) {
  const chain = await (await locate()).getComponentChain();
  const want = NAMES[kind].map((n) => n.toLowerCase());
  const hit = (await listComponents(chain)).find((c) => want.includes(String(c.name).toLowerCase()));
  return hit ? hit.index : -1;
}

/**
 * Effekt (Rezept aus dem Plan) an einen Clip hängen und seine Parameter setzen.
 * `effect.params[]`: {name | names[], index, value, keyframes}. Rückgabe: {angewendet, fehlend, match}.
 */
async function addEffect(ppro, project, locate, effect, ctx) {
  const res = { id: effect.id, angewendet: [], fehlend: [], match: null };
  ctx.displayHints = [effect.display].filter(Boolean);
  res.match = await resolveMatchName(ppro, effect.match_name, ctx);
  const comp = await ppro.VideoFilterFactory.createComponent(res.match);
  const chain = await (await locate()).getComponentChain();
  const index = chain.getComponentCount();
  await txp(ppro, 'Effekt ' + effect.id, (add) => add(chain.createAppendComponentAction(comp)));
  for (const p of effect.params || []) {
    if (p.value === undefined && !(p.keyframes && p.keyframes.length)) continue;
    const label = p.name || (p.names && p.names[0]) || '#' + p.index;
    try {
      await retryStale(async () => {
        const param = findParam(await componentAt(locate, index), p.names || [p.name], p.index);
        if (!param) throw new Error('Parameter nicht gefunden');
        await setParam(ppro, project, param, p, ctx);
      });
      res.angewendet.push(label);
    } catch (e) {
      res.fehlend.push(label + ' (' + errText(e) + ')');
    }
  }
  return res;
}

/** Position/Skalierung (Bewegung). Position als normierte Werte 0..1. */
async function setMotion(ppro, project, locate, { position, scale }, ctx) {
  const idx = await builtinIndex(locate, 'motion');
  if (idx < 0) throw new Error('Bewegung-Effekt nicht gefunden');
  const done = [];
  for (const [label, names, pidx, spec] of [['Position', NAMES.position, 0, position ? { value: { point: position } } : null], ['Skalierung', NAMES.scale, 1, scale != null ? { value: scale } : null]]) {
    if (!spec) continue;
    const param = findParam(await componentAt(locate, idx), names, pidx);
    if (!param) continue;
    await setParam(ppro, project, param, spec, ctx);
    done.push(label);
  }
  return done;
}

/** Ein-/Ausblenden über die Deckkraft: 0 → 100 in `fade` s, am Ende 100 → 0. */
async function setFade(ppro, project, locate, dur, fade, ctx) {
  const idx = await builtinIndex(locate, 'opacity');
  if (idx < 0) throw new Error('Deckkraft-Effekt nicht gefunden');
  const param = findParam(await componentAt(locate, idx), NAMES.opacity, 0);
  if (!param) throw new Error('Deckkraft-Parameter nicht gefunden');
  const f = Math.min(fade, dur / 2);
  await setParam(ppro, project, param, { keyframes: [[0, 0], [f, 100], [Math.max(f, dur - f), 100], [dur, 0]] }, ctx);
}

/** Quadratischer Zuschnitt (Effekt „Zuschneiden“), Werte in Prozent. */
async function addCrop(ppro, project, locate, crop, ctx) {
  return addEffect(ppro, project, locate, {
    id: 'crop', match_name: 'AE.ADBE Crop', display: 'Zuschneiden',
    params: [{ names: NAMES.crop.left, index: 0, value: crop.links }, { names: NAMES.crop.top, index: 1, value: crop.oben },
      { names: NAMES.crop.right, index: 2, value: crop.rechts }, { names: NAMES.crop.bottom, index: 3, value: crop.unten }],
  }, ctx);
}

module.exports = { NAMES, listComponents, paramList, findParam, toPproValue, resolveMatchName, setParam, addEffect, builtinIndex, componentAt, setMotion, setFade, addCrop };
