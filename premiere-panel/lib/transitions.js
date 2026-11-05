// Übergänge wie im Ursprungsschnitt: Cross Dissolve an Videoclips, Gleichleistungs-Blenden am Ton.
// `locate()` liefert den Clip frisch (siehe core.js). Die Premiere-API hat nur Videoübergänge (createAddVideoTransitionAction);
// Audioübergänge („Konstante Leistung“) gibt es dort nicht – der Ton bekommt stattdessen Pegel-Keyframes mit Gleichleistungs-Kurve.
'use strict';

const { tt, txp, errText, rawValue, retryStale } = require('./core');
const fx = require('./effects');

const LEVEL = { comp: ['Volume', 'Lautstärke'], param: ['Level', 'Pegel'] };

/** Internen Namen des Übergangs in der installierten Premiere-Version bestimmen. */
async function resolveTransition(ppro, spec, ctx) {
  if (!ctx.transitions) ctx.transitions = await ppro.TransitionFactory.getVideoTransitionMatchNames();
  const names = ctx.transitions;
  const want = spec.match_name;
  const hit = names.find((n) => n === want) || names.find((n) => n.replace(/^AE\./, '') === want.replace(/^AE\./, ''));
  if (hit) return hit;
  const similar = names.filter((n) => /dissolve|blende|fade/i.test(n)).slice(0, 6);
  throw new Error('Übergang „' + want + '“ gibt es in dieser Premiere-Version nicht' + (similar.length ? ' (ähnlich: ' + similar.join(', ') + ')' : ''));
}

/**
 * Videoübergang(e) an Anfang/Ende eines Clips: `u` = {ein, aus} in Sekunden (0 = keiner). Einseitig, damit die Clipgrenzen bleiben.
 * Rückgabe: Anzahl gesetzter Übergänge.
 */
async function addVideoTransitions(ppro, locate, u, spec, ctx) {
  const match = await resolveTransition(ppro, spec, ctx);
  let n = 0;
  for (const [applyToStart, dur] of [[true, u.ein || 0], [false, u.aus || 0]]) {
    if (!(dur > 0)) continue;
    await retryStale(async () => {                    // je Seite eigener Versuch: der Clip wird frisch geholt, die Änderung steht zuletzt
      const ti = await locate();
      const opts = new ppro.AddTransitionOptions();
      opts.setApplyToStart(applyToStart);
      opts.setDuration(tt(ppro, dur));
      opts.setForceSingleSided(true);
      const tr = ppro.TransitionFactory.createVideoTransition(match);
      await txp(ppro, 'Übergang', (add) => add(ti.createAddVideoTransitionAction(tr, opts)));
    });
    n++;
  }
  return n;
}

/** Wie Premiere den Pegel führt: lineare Amplitude (1 = 0 dB, so liegt sie im Projekt) oder dB (0 = unverändert). Erkannt am Ausgangswert. */
function levelMode(startValue) {
  const v = rawValue(startValue);
  if (typeof v === 'number' && Math.abs(v) < 1e-6) return 'db';
  return 'linear';
}

const DB_FLOOR = -80;
const toLevel = (gain, mode) => (mode === 'db' ? (gain <= 1e-4 ? DB_FLOOR : Math.max(DB_FLOOR, 20 * Math.log10(gain))) : gain);

/** Pegel-Keyframes (Gleichleistungs-Blende) an einem Audioclip. `keyframes`: [[Sekunden ab Clipanfang, Verstärkung 0..1]]. */
async function setAudioFade(ppro, project, locate, keyframes, ctx) {
  return retryStale(async () => {                     // gemessen: „The script object is no longer valid.“ mitten im Bau – alles frisch holen, Änderung zuletzt
    const idx = await levelComponentIndex(locate);
    if (idx < 0) throw new Error('Lautstärke-Effekt am Audioclip nicht gefunden');
    const param = fx.findParam(await fx.componentAt(locate, idx), LEVEL.param, 1);
    if (!param) throw new Error('Pegel-Parameter nicht gefunden');
    const mode = levelMode(await param.getStartValue());
    await fx.setParam(ppro, project, param, { keyframes: keyframes.map(([t, g]) => [t, toLevel(g, mode)]) }, ctx);
    return mode;
  });
}

async function levelComponentIndex(locate) {
  const chain = await (await locate()).getComponentChain();
  const want = LEVEL.comp.map((n) => n.toLowerCase());
  const hit = (await fx.listComponents(chain)).find((c) => want.includes(String(c.name).toLowerCase()));
  return hit ? hit.index : -1;
}

module.exports = { resolveTransition, addVideoTransitions, setAudioFade, levelMode, toLevel, errText };
