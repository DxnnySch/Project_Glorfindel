// Glorfindel-Bridge für Premiere Pro (UXP). Verbindet sich mit der lokalen Glorfindel-App und führt deren Befehle aus.
// Die gesamte Logik liegt in lib/ (ohne Premiere testbar); diese Datei verdrahtet nur Oberfläche und Premiere.
'use strict';

const { Bridge } = require('./lib/bridge');

const VERSION = '0.5.8';
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

function setStatus({ state, text }) {
  const dot = $('dot'), label = $('status');
  if (dot) dot.className = 'dot ' + state;
  if (label) label.textContent = text;
}

let bridge = null;

function start() {
  const ppro = require('premierepro');
  let hostInfo = {};
  try { const host = require('uxp').host; hostInfo = { name: host.name, version: host.version }; } catch (e) { /* ohne */ }
  $('version').textContent = 'Panel ' + VERSION + ' · Premiere ' + (hostInfo.version || '?');
  bridge = new Bridge({ ppro, WebSocketImpl: WebSocket, fetchImpl: fetch.bind(globalThis), hostInfo, version: VERSION, log, onStatus: setStatus });
  bridge.run();
}

try {
  const { entrypoints } = require('uxp');
  entrypoints.setup({ panels: { glorfindelPanel: { show() { if (!bridge) start(); } } } });
} catch (e) {
  document.addEventListener('DOMContentLoaded', start);
}
