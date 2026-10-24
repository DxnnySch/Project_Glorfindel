// Effekte an Clips: Komponente anhängen, Parameter setzen (statisch oder mit Keyframes), Zugriff auf eingebaute Effekte.
'use strict';

const { tt, tx, errText } = require('./core');

// Anzeigenamen eingebauter Effekte/Parameter in beiden Oberflächensprachen (Premiere benennt je nach Sprache).
const NAMES = {
  motion: ['Motion', 'Bewegung'],
  opacity: ['Opacity', 'Deckkraft'],
  position: ['Position'],
  scale: ['Scale', 'Skalierung'],
  crop: { left: ['Left', 'Links'], top: ['Top', 'Oben'], right: ['Right', 'Rechts'], bottom: ['Bottom', 'Unten'] },
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

async function findComponent(chain, names) {
  const want = names.map((n) => n.toLowerCase());
  for (const c of await listComponents(chain)) if (want.includes(String(c.name).toLowerCase())) return c.comp;
  return null;
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

/** Parameter setzen. `spec`: {value, keyframes: [[Sekunden, Wert], ...]}. Zeiten sind Clip-Zeit (ab Clipanfang). */
async function setParam(ppro, project, param, spec, ctx) {
  const kfs = spec.keyframes;
  if (kfs && kfs.length) {
    tx(project, 'Keyframes', (add) => add(param.createSetTimeVaryingAction(true)));
    tx(project, 'Keyframes', (add) => {
      for (const [t, val] of kfs) {
        const k = param.createKeyframe(toPproValue(ppro, val, ctx));
        k.position = tt(ppro, t + ((ctx && ctx.offset) || 0));
        add(param.createAddKeyframeAction(k));
      }
    });
    return 'keyframes';
  }
  if (spec.value === undefined || spec.value === null) return 'unveraendert';
  tx(project, 'Wert', (add) => add(param.createSetValueAction(param.createKeyframe(toPproValue(ppro, spec.value, ctx)), true)));
  return 'wert';
}

/** Effekt (Rezept aus dem Plan) an einen Clip hängen und seine Parameter setzen. Gibt {angewendet, fehlend} zurück. */
async function addEffect(ppro, project, trackItem, effect, ctx) {
  const res = { id: effect.id, angewendet: [], fehlend: [] };
  const chain = await trackItem.getComponentChain();
  const comp = await ppro.VideoFilterFactory.createComponent(effect.match_name);
  tx(project, 'Effekt ' + effect.id, (add) => add(chain.createAppendComponentAction(comp)));
  const installed = chain.getComponentAtIndex(chain.getComponentCount() - 1);
  for (const p of effect.params || []) {
    if (p.value === undefined && !(p.keyframes && p.keyframes.length)) continue;
    const param = findParam(installed, [p.name], p.index);
    if (!param) { res.fehlend.push(p.name); continue; }
    try {
      await setParam(ppro, project, param, p, ctx);
      res.angewendet.push(p.name);
    } catch (e) {
      res.fehlend.push(p.name + ' (' + errText(e) + ')');
    }
  }
  return res;
}

/** Eingebauten Effekt (Bewegung/Deckkraft) eines Clips holen. */
async function builtin(trackItem, kind) {
  const chain = await trackItem.getComponentChain();
  return findComponent(chain, NAMES[kind]);
}

/** Position/Skalierung (Bewegung). Position als normierte Werte 0..1. */
async function setMotion(ppro, project, trackItem, { position, scale }, ctx) {
  const motion = await builtin(trackItem, 'motion');
  if (!motion) throw new Error('Bewegung-Effekt nicht gefunden');
  const done = [];
  if (position) {
    const p = findParam(motion, NAMES.position, 1);
    if (p) { await setParam(ppro, project, p, { value: { point: position } }, ctx); done.push('Position'); }
  }
  if (scale != null) {
    const p = findParam(motion, NAMES.scale, 2);
    if (p) { await setParam(ppro, project, p, { value: scale }, ctx); done.push('Skalierung'); }
  }
  return done;
}

/** Ein-/Ausblenden über die Deckkraft: 0 → 100 in `fade` s, am Ende 100 → 0. */
async function setFade(ppro, project, trackItem, dur, fade, ctx) {
  const op = await builtin(trackItem, 'opacity');
  if (!op) throw new Error('Deckkraft-Effekt nicht gefunden');
  const p = findParam(op, NAMES.opacity, 0);
  if (!p) throw new Error('Deckkraft-Parameter nicht gefunden');
  const f = Math.min(fade, dur / 2);
  await setParam(ppro, project, p, { keyframes: [[0, 0], [f, 100], [Math.max(f, dur - f), 100], [dur, 0]] }, ctx);
}

/** Quadratischer Zuschnitt (Effekt „Zuschneiden“), Werte in Prozent. */
async function addCrop(ppro, project, trackItem, crop, ctx) {
  const comp = await ppro.VideoFilterFactory.createComponent('AE.ADBE Crop');
  const chain = await trackItem.getComponentChain();
  tx(project, 'Zuschneiden', (add) => add(chain.createAppendComponentAction(comp)));
  const installed = chain.getComponentAtIndex(chain.getComponentCount() - 1);
  const res = { angewendet: [], fehlend: [] };
  for (const [k, names, idx] of [['links', NAMES.crop.left, 0], ['oben', NAMES.crop.top, 1], ['rechts', NAMES.crop.right, 2], ['unten', NAMES.crop.bottom, 3]]) {
    const param = findParam(installed, names, idx);
    if (!param) { res.fehlend.push(k); continue; }
    await setParam(ppro, project, param, { value: crop[k] }, ctx);
    res.angewendet.push(k);
  }
  return res;
}

module.exports = { NAMES, listComponents, findComponent, paramList, findParam, toPproValue, setParam, addEffect, builtin, setMotion, setFade, addCrop };
