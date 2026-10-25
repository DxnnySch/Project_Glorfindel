// Strenge Nachbildung der Premiere-UXP-API (Teilmenge) für Tests ohne Premiere.
// Erzwingt die Regeln aus der offiziellen Doku (premierepro-26.5.d.ts): TickTime-Typen, Color 0..1, createSetValueAction nur für nicht
// animierte Parameter, Spur muss existieren, Aktionen nur über executeTransaction, Import als Bildsequenz nur auf Wunsch.
'use strict';

const TPS = 254016000000;

// Wie in Premiere 26.5: Nach JEDER Projektänderung sind alle zuvor gelieferten Objekte ungültig.
let EPOCH = 0;
let HANDLE = 0;   // jeder getActiveProject()-Aufruf liefert ein neues Handle; Objekte älterer Handles gelten als ungültig (Annahme, deckt „Fach anlegen“ ab)
const bump = () => { EPOCH++; };
const RAW = new WeakMap();
const unwrap = (o) => (o && typeof o === 'object' && RAW.get(o)) || o;
function wrap(o) {
  if (Array.isArray(o)) return o.map(wrap);
  if (!o || typeof o !== 'object' || o instanceof Action || o instanceof TickTime) return o;
  const born = EPOCH, handle = HANDLE;
  const px = new Proxy(o, {
    get(t, k, r) {
      if (typeof k !== 'symbol' && (born !== EPOCH || handle !== HANDLE)) throw new Error('The script object is no longer valid.');
      const v = Reflect.get(t, k, r);
      return v;
    },
  });
  RAW.set(px, o);
  return px;
}
function guardReturns(cls, names) {
  for (const n of names) {
    const orig = cls.prototype[n];
    cls.prototype[n] = function (...a) {
      const r = orig.apply(this, a);
      return r && typeof r.then === 'function' ? r.then(wrap) : wrap(r);
    };
  }
}

class TickTime { constructor(s) { this.seconds = s; this.ticks = String(Math.round(s * TPS)); } get ticksNumber() { return +this.ticks; } }
class PointF { constructor(x = 0, y = 0) { this.x = x; this.y = y; } }
class Color {
  constructor(red = 0, green = 0, blue = 0, alpha = 1) {
    for (const v of [red, green, blue, alpha]) if (!(v >= 0 && v <= 1)) throw new Error('Color-Werte müssen in [0.0, 1.0] liegen, war ' + v);
    Object.assign(this, { red, green, blue, alpha });
  }
}
class Action { constructor(run, label) { this.run = run; this.label = label; } }

const DISPLAY = { 'ADBE Crop': 'Zuschneiden', 'AE.ADBE Roughen Edges': 'Kanten aufrauen', 'AE.ADBE Drop Shadow': 'Schlagschatten', 'AE.ADBE Geometry': 'Transformieren', 'AE.ADBE Gaussian Blur 2': 'Gaußscher Weichzeichner' };
const PARAMS = {
  'ADBE Crop': [['Links', 'num', 0], ['Oben', 'num', 0], ['Rechts', 'num', 0], ['Unten', 'num', 0], ['Zoom', 'bool', false], ['Kantenweichzeichnung', 'num', 0]],
  'AE.ADBE Roughen Edges': [['Kantenart', 'num', 1], ['Konturfarbe', 'color', null], ['Rahmen', 'num', 8], ['Kantenschärfe', 'num', 0], ['Fraktaleinfluss', 'num', 1], ['Skalieren', 'num', 100],
    ['Breite oder Höhe dehnen', 'num', 0], ['Offset (Turbulenz)', 'point', null], ['Komplexität', 'num', 10], ['Evolution', 'num', 0]],
  'AE.ADBE Drop Shadow': [['Schattenfarbe', 'color', null], ['Deckkraft', 'num', 50], ['Richtung', 'num', 135], ['Abstand', 'num', 10], ['Weiche Kante', 'num', 5], ['Nur Schatten', 'bool', false]],
  'AE.ADBE Geometry': [['Ankerpunkt', 'point', null], ['Position', 'point', null], ['Einheitliche Skalierung', 'bool', true], ['Skalierungshöhe', 'num', 100], ['Skalierungsbreite', 'num', 100],
    ['Verzerren', 'num', 0], ['Achse der Verzerrung', 'num', 0], ['Drehung', 'num', 0], ['Deckkraft', 'num', 100]],
  'AE.ADBE Gaussian Blur 2': [['Weichzeichnung', 'num', 0], ['Weichzeichnungsdimensionen', 'num', 0], ['Kantenpixel wiederholen', 'bool', false]],
};

class Param {
  constructor(name, type, init) { this.displayName = name; this.type = type; this.value = init; this.varying = false; this.kfs = []; this.log = []; }
  _check(v) {
    const ok = { num: typeof v === 'number', bool: typeof v === 'boolean', point: v instanceof PointF, color: v instanceof Color }[this.type];
    if (!ok) throw new Error('Wert passt nicht zum Parametertyp ' + this.type + ' (' + this.displayName + ')');
  }
  createKeyframe(v) { this._check(v); return { position: new TickTime(0), value: { value: v } }; }
  createSetTimeVaryingAction(on) { return new Action(() => { this.varying = !!on; }, 'timevarying'); }
  createAddKeyframeAction(k) {
    return new Action(() => {
      if (!this.varying) throw new Error('Keyframes brauchen createSetTimeVaryingAction(true)');
      if (!(k.position instanceof TickTime)) throw new Error('Keyframe-Position muss TickTime sein');
      this.kfs.push([k.position.seconds, k.value.value]); this.kfs.sort((a, b) => a[0] - b[0]);
    }, 'addkf');
  }
  createSetValueAction(k) {
    return new Action(() => { if (this.varying) throw new Error('createSetValueAction nur für nicht animierte Parameter'); this.value = k.value.value; }, 'setvalue');
  }
  isTimeVarying() { return this.varying; }
  getKeyframeListAsTickTimes() { return this.kfs.map(([t]) => new TickTime(t)); }
  async getStartValue() { return { value: this.kfs.length ? this.kfs[0][1] : this.value }; }
}

class Component {
  constructor(name, spec) { this.name = name; this.params = spec.map(([n, t, v]) => new Param(n, t, v ?? (t === 'point' ? new PointF(0.5, 0.5) : t === 'color' ? new Color(0, 0, 0, 1) : v))); }
  async getDisplayName() { return this.name; }
  getParamCount() { return this.params.length; }
  getParam(i) { return this.params[i]; }
}

class Chain {
  constructor(isVideo) {
    this.comps = isVideo ? [new Component('Bewegung', [['Position', 'point'], ['Skalierung', 'num', 100], ['Einheitliche Skalierung', 'bool', true]].map(([a, b, c]) => [a, b, c])),
      new Component('Deckkraft', [['Deckkraft', 'num', 100]])] : [];
    this.comps[0] && (this.comps[0].params[0].value = new PointF(0.5, 0.5));
  }
  getComponentCount() { return this.comps.length; }
  getComponentAtIndex(i) { return this.comps[i]; }
  createAppendComponentAction(c) { return new Action(() => { this.comps.push(c); }, 'append'); }
}

class TrackItem {
  constructor(seq, kind, idx, item, start, end, inPt) { Object.assign(this, { seq, kind, idx, item, start, end, inPt, name: item.name, chain: new Chain(kind === 'video') }); }
  async getStartTime() { return new TickTime(this.start); }
  async getEndTime() { return new TickTime(this.end); }
  async getInPoint() { return new TickTime(this.inPt); }
  async getOutPoint() { return new TickTime(this.inPt + (this.end - this.start)); }
  async getName() { return this.name; }
  async getComponentChain() { return this.chain; }
  createSetEndAction(t) { if (!(t instanceof TickTime)) throw new Error('TickTime erwartet'); return new Action(() => { this.end = t.seconds; }, 'setend'); }
  createSetNameAction(n) { return new Action(() => { this.name = n; }, 'name'); }
}

class Track {
  constructor(seq, kind, idx) { this.seq = seq; this.kind = kind; this.idx = idx; this.items = []; }
  getTrackItems(type) { return type === 1 ? [...this.items] : []; }
}

class Sequence {
  constructor(project, name, v, a, extra = {}) {
    this.project = project; this.name = name; this.guid = 'guid-' + name; this.tracks = { video: Array.from({ length: v }, (_, i) => new Track(this, 'video', i)), audio: Array.from({ length: a }, (_, i) => new Track(this, 'audio', i)) };
    this.markers = []; Object.assign(this, extra);
  }
  async getVideoTrackCount() { return this.tracks.video.length; }
  async getAudioTrackCount() { return this.tracks.audio.length; }
  async getVideoTrack(i) { return this.tracks.video[i]; }
  async getAudioTrack(i) { return this.tracks.audio[i]; }
  async getProjectItem() { return this.item; }
}

class ProjectItem {
  constructor(project, name, type) { this.project = project; this.name = name; this.type = type; }
}
class FolderItem extends ProjectItem {
  constructor(project, name, type) { super(project, name, type); this.children = []; }
  async getItems() { return [...this.children]; }
  createBinAction(name) { return new Action(() => { this.children.push(new FolderItem(this.project, name, 2)); }, 'bin'); }
  createRemoveItemAction(item) { const raw = unwrap(item); return new Action(() => { this.children = this.children.filter((c) => c !== raw); }, 'rm'); }
}
class ClipItem extends ProjectItem {
  constructor(project, name, path, opts = {}) {
    super(project, name, 1); Object.assign(this, { path, seq: null, offline: false, inPt: null, outPt: null, hasVideo: opts.hasVideo !== false, hasAudio: !!opts.hasAudio, length: opts.length ?? 5, refreshed: 0 });
  }
  async getMediaFilePath() { return this.path; }
  async isSequence() { return !!this.seq; }
  async isOffline() { return this.offline; }
  async canChangeMediaPath() { return true; }
  async changeMediaFilePath(p, override) { if (/nichtda/.test(p)) throw new Error('Datei nicht gefunden'); this.path = p; bump(); return true; }
  async refreshMedia() { this.refreshed++; bump(); return true; }
  createSetInOutPointsAction(i, o) {
    if (!(i instanceof TickTime) || !(o instanceof TickTime)) throw new Error('TickTime erwartet');
    return new Action(() => { this.inPt = i.seconds; this.outPt = o.seconds; }, 'inout');
  }
}

guardReturns(Chain, ['getComponentAtIndex']);
guardReturns(Component, ['getParam']);
guardReturns(TrackItem, ['getComponentChain']);
guardReturns(Track, ['getTrackItems']);
guardReturns(Sequence, ['getVideoTrack', 'getAudioTrack', 'getProjectItem']);
guardReturns(FolderItem, ['getItems']);

function trim(track, a, b) {   // Überschreiben: Teile alter Clips im Bereich [a, b) fallen weg
  const keep = [];
  for (const x of track.items) {
    if (x.end <= a || x.start >= b) { keep.push(x); continue; }
    if (x.start < a) x.end = a;                       // Anfang bleibt
    else if (x.end > b) { x.inPt += b - x.start; x.start = b; }   // Ende bleibt
    else continue;                                     // vollständig überdeckt
    keep.push(x);
  }
  track.items = keep;
}

function kindOfPath(p) {
  const ext = String(p).toLowerCase().split('.').pop();
  if (['wav', 'mp3'].includes(ext)) return { hasVideo: false, hasAudio: true, length: 600 };
  if (['mp4', 'mov'].includes(ext)) return { hasVideo: true, hasAudio: true, length: 4000 };
  return { hasVideo: true, hasAudio: false, length: 5 };            // Standbild: Standardlänge 5 s
}

function create({ presets = {}, aeComps = ['Play-Pause'] } = {}) {
  const calls = [];
  const project = { name: 'Test.prproj', path: 'F:/Test.prproj', sequences: [], saved: 0, calls };
  const root = new FolderItem(project, 'Root', 3);
  project.root = root;
  const findBin = (b) => b || root;

  Object.assign(project, {
    async getRootItem() { return root; },
    async importFiles(paths, suppress, bin, numbered) {
      calls.push(['importFiles', paths.length, numbered]);
      if (numbered === undefined) throw new Error('asNumberedStills nicht gesetzt: Bildfolgen-Gefahr');
      for (const p of paths) findBin(bin).children.push(new ClipItem(project, p.split(/[\\/]/).pop(), p, kindOfPath(p)));
      return true;
    },
    async importAEComps(aep, names, bin) {
      if (!aeComps.includes(names[0])) return false;
      findBin(bin).children.push(new ClipItem(project, names[0] + '/' + aep.split('/').pop(), aep, { hasVideo: true, length: 120 }));
      return true;
    },
    async createSequenceFromMedia(name, clips, bin) {
      const s = new Sequence(project, name, 3, 3, { fps: 23.976 });
      s.item = new ClipItem(project, name, null, { hasVideo: true, hasAudio: true, length: clips[0].length }); s.item.seq = s;
      findBin(bin).children.push(s.item); project.sequences.push(s);
      return s;
    },
    async createSequenceWithPresetPath(name, preset) {
      const p = presets[preset];
      if (!p) throw new Error('Vorgabe nicht gefunden: ' + preset);
      const s = new Sequence(project, name, p.video, p.audio, { fps: 60 });
      s.item = new ClipItem(project, name, null, { hasVideo: true, hasAudio: true, length: 0 }); s.item.seq = s;
      root.children.push(s.item); project.sequences.push(s);
      return s;
    },
    async createSequence() { throw new Error('createSequence mit Vorgabe ist veraltet – createSequenceWithPresetPath verwenden'); },
    async deleteSequence(s) {
      project.sequences = project.sequences.filter((x) => x !== s); root.children = root.children.filter((c) => c.seq !== s); return true; },
    async getSequences() { return [...project.sequences]; },
    async getActiveSequence() { return project.active || project.sequences.at(-1); },
    async setActiveSequence(s) { project.active = unwrap(s); return true; },
    async openSequence() { return true; },
    async save() { project.saved++; return true; },
    lockedAccess(cb) { project.locked = true; try { cb(); } finally { project.locked = false; } },
    executeTransaction(cb, undo) {
      if (!project.locked) throw new Error('Requires locked access');
      const actions = [];
      cb({ addAction(a) { if (!(a instanceof Action)) throw new Error('keine Aktion'); actions.push(a); return true; } });
      calls.push(['tx', undo, actions.length]);
      for (const a of actions) a.run();
      bump();
      return true;
    },
  });
  for (const n of ['getRootItem', 'getSequences', 'getActiveSequence']) {
    const orig = project[n];
    project[n] = async (...a) => wrap(await orig(...a));
  }
  for (const n of ['importFiles', 'importAEComps', 'createSequenceFromMedia', 'createSequenceWithPresetPath', 'deleteSequence']) {
    const orig = project[n];
    project[n] = async (...a) => { const r = await orig(...a.map(unwrap)); bump(); return wrap(r); };
  }
  root.createBinAction = FolderItem.prototype.createBinAction.bind(root);
  root.createRemoveItemAction = FolderItem.prototype.createRemoveItemAction.bind(root);
  project.sequences.push();

  const ppro = {
    TickTime: { createWithSeconds: (s) => { if (typeof s !== 'number' || isNaN(s)) throw new Error('Zahl erwartet'); return new TickTime(s); } },
    PointF, Color,
    Constants: { TrackItemType: { EMPTY: 0, CLIP: 1, TRANSITION: 2 }, MediaType: { ANY: 0, DATA: 1, VIDEO: 2, AUDIO: 3 } },
    ProjectItem: { TYPE_BIN: 2, TYPE_CLIP: 1, TYPE_ROOT: 3 },
    FolderItem: { cast: (i) => { if (!(i instanceof FolderItem)) throw new Error('kein Fach'); return i; } },
    ClipProjectItem: { cast: (i) => { if (!(i instanceof ClipItem)) throw new Error('kein Clip'); return i; } },
    Marker: { MARKER_TYPE_COMMENT: 'Comment' },
    Markers: { async getMarkers(seq) { return { createAddMarkerAction: (name, type, start, dur, comments) => new Action(() => seq.markers.push({ name, type, start: start.seconds, comments }), 'marker') }; } },
    VideoFilterFactory: {
      async createComponent(match) { if (!PARAMS[match]) throw new Error('Unbekannter Effekt ' + match); return new Component(match, PARAMS[match]); },
      async getMatchNames() { return Object.keys(PARAMS); },
      async getDisplayNames() { return Object.keys(PARAMS).map((k) => DISPLAY[k]); },
    },
    Project: { async getActiveProject() { HANDLE++; return wrap(project); } },
    SequenceEditor: {
      getEditor(seq) {
        return {
          createOverwriteItemAction(item, time, v, a) {
            item = unwrap(item);
            if (!(time instanceof TickTime)) throw new Error('TickTime erwartet');
            return new Action(() => {
              const len = (item.inPt != null ? item.outPt - item.inPt : item.length);
              if (item.hasVideo && v >= 0) {
                if (v >= seq.tracks.video.length) throw new Error('Videospur ' + (v + 1) + ' existiert nicht');
                const tr = seq.tracks.video[v];
                trim(tr, time.seconds, time.seconds + len);
                tr.items.push(new TrackItem(seq, 'video', v, item, time.seconds, time.seconds + len, item.inPt || 0));
              }
              if (item.hasAudio && a >= 0) {
                if (a >= seq.tracks.audio.length) throw new Error('Audiospur ' + (a + 1) + ' existiert nicht');
                const tr = seq.tracks.audio[a];
                tr.items.push(new TrackItem(seq, 'audio', a, item, time.seconds, time.seconds + len, item.inPt || 0));
              }
            }, 'overwrite');
          },
        };
      },
    },
  };
  return { ppro, project, ClipItem, TickTime };
}

module.exports = { create, TickTime, PointF, Color };
