// Glorfindel-Bridge für Premiere Pro (UXP). Verbindet sich mit der lokalen Glorfindel-App und führt deren Befehle aus.
// Die gesamte Logik liegt in lib/ (ohne Premiere testbar); diese Datei verdrahtet nur Oberfläche und Premiere.
'use strict';

const { Bridge } = require('./lib/bridge');
const { buildTools: build, toolsNotReady: notReady } = require('./lib/toolbar');

const VERSION = '0.6.0';
const $ = (id) => document.getElementById(id);

function log(text, cls) {
  const box = $('log');
  if (!box) return;
  const line = document.createElement('div');
  line.className = cls || '';
  line.textContent = new Date().toLocaleTimeString() + '  ' + text;
  box.prepend(line);
  while (box.childNodes.length > 200) box.removeChild(box.lastChild);
}

let bridge = null;
let lastState = '';

function setStatus({ state, text }) {
  const dot = $('dot'), label = $('status');
  if (dot) dot.className = 'dot ' + state;
  if (label) label.textContent = text;
  if (state === 'verbunden' && lastState !== 'verbunden' && lastState !== 'arbeitet') refreshTools();
  lastState = state;
}

// ---------- Werkzeuge ----------
async function run(name, args, label) {
  if (!bridge) return;
  const buttons = Array.from(document.querySelectorAll('#tools button'));
  buttons.forEach((b) => b.setAttribute('disabled', 'disabled'));
  log((label || name) + ' …');
  try {
    const r = await bridge.runTool(name, args || {});
    if (!r.ok) { log((label || name) + ': ' + r.error, 'err'); return; }
    log(r.text, 'ok');
    for (const w of r.warnings || []) log(w, 'warn');
    for (const l of r.lines || []) log(l);
  } finally {
    buttons.forEach((b) => b.removeAttribute('disabled'));
  }
}

function toolsNotReady(why) {
  const host = $('tools');
  if (host) notReady(document, host, why, () => refreshTools());
}

async function refreshTools() {
  if (!bridge) return;
  try { build(document, $('tools'), await bridge.tools().config(true), run); } catch (e) { toolsNotReady((e && e.message) || String(e)); }
}

function start() {
  const ppro = require('premierepro');
  let hostInfo = {};
  try { const host = require('uxp').host; hostInfo = { name: host.name, version: host.version }; } catch (e) { /* ohne */ }
  $('version').textContent = 'Panel ' + VERSION + ' · Premiere ' + (hostInfo.version || '?');
  bridge = new Bridge({ ppro, WebSocketImpl: WebSocket, fetchImpl: fetch.bind(globalThis), hostInfo, version: VERSION, log, onStatus: setStatus });
  toolsNotReady('Verbindung zur App wird aufgebaut …');
  bridge.run();
}

try {
  const { entrypoints } = require('uxp');
  entrypoints.setup({ panels: { glorfindelPanel: { show() { if (!bridge) start(); } } } });
} catch (e) {
  document.addEventListener('DOMContentLoaded', start);
}
