/*!
 * Pizza Builder - a drag-and-drop pizza task for Qualtrics / Prolific studies.
 *
 * Three modes, each mounted on its own survey page:
 *   practice  - learn to place, move and remove (records motor baseline)
 *   build     - the real pizza (ingredients, positions, order, timing)
 *   followup  - per-topping ratings and reasons for avoiding toppings
 *
 *   PizzaBuilder.mount(element, { mode: 'build', onSave: fn(name, value), onFinish: fn(data) })
 *
 * No dependencies. Works with mouse, touch and pen (Pointer Events).
 * Coordinates are stored relative to the pizza: x right, y up, 1 = outer crust edge.
 * See README.md and CODEBOOK.md next to this file.
 */
(function (global) {
  'use strict';
  if (global.PizzaBuilder) return;

  var VERSION = '0.1.0';
  var VIEW = 105;        // half-width of every pizza viewBox; the pizza's outer radius is 100
  var R_SNAP = 0.9;      // with snapIn, a topping centre dropped on the crust is pulled in to this radius
  var R_OFF = 1.0;       // dropped further out than this = off the pizza

  // ---------------------------------------------------------------- helpers

  function P(n) { return Math.round(n * 100) / 100; }
  function r3(n) { return Math.round(n * 1000) / 1000; }
  function rng(seed) {   // mulberry32: the same seed always draws the same topping
    return function () {
      seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function extend(a) {
    for (var i = 1; i < arguments.length; i++) {
      var b = arguments[i]; if (!b) continue;
      for (var k in b) if (Object.prototype.hasOwnProperty.call(b, k) && b[k] !== undefined) a[k] = b[k];
    }
    return a;
  }
  function shuffle(a) { a = a.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function median(a) { if (!a.length) return null; a = a.slice().sort(function (x, y) { return x - y; }); var m = a.length >> 1; return a.length % 2 ? a[m] : Math.round((a[m - 1] + a[m]) / 2); }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmt(s, o) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
  function now() { return (global.performance && performance.now) ? performance.now() : Date.now(); }
  function circ(cx, cy, r, fill, extra) { return '<circle cx="' + P(cx) + '" cy="' + P(cy) + '" r="' + P(r) + '" fill="' + fill + '"' + (extra || '') + '/>'; }
  function blob(pts) {
    var n = pts.length;
    function mid(i) { var a = pts[i % n], b = pts[(i + 1) % n]; return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; }
    var m = mid(0), s = 'M' + P(m[0]) + ' ' + P(m[1]);
    for (var i = 1; i <= n; i++) { var c = pts[i % n], e = mid(i); s += 'Q' + P(c[0]) + ' ' + P(c[1]) + ' ' + P(e[0]) + ' ' + P(e[1]); }
    return s + 'Z';
  }
  function countsString(counts) { var a = []; for (var k in counts) a.push(k + ':' + counts[k]); return a.join(','); }
  function parseCounts(s) {
    var o = {}; if (!s) return o;
    if (typeof s === 'object') return s;
    String(s).split(',').forEach(function (kv) { var p = kv.split(':'); if (p.length === 2 && p[0]) o[p[0].trim()] = +p[1]; });
    return o;
  }

  // ---------------------------------------------------------------- toppings
  // size = bounding radius in pizza units (pizza radius 100 ~ a 30 cm pizza, so 1 unit ~ 1.5 mm).
  // draw(rnd) returns SVG markup centred on 0,0; rnd is seeded so each variant looks the same every time.

  var ING = {
    pep: { name: 'Pepperoni', cat: 'meat', size: 13, draw: function (r) {
      var s = circ(0, 0, 13, 'url(#pzb-g-pep)'), i, a, d;
      for (i = 0; i < 8; i++) { a = r() * 6.283; d = Math.sqrt(r()) * 10; s += circ(Math.cos(a) * d, Math.sin(a) * d, 0.7 + r() * 1.4, '#f2b8a0', ' opacity=".5"'); }
      for (i = 0; i < 6; i++) { a = r() * 6.283; d = Math.sqrt(r()) * 10.5; s += circ(Math.cos(a) * d, Math.sin(a) * d, 0.5 + r(), '#5e100c', ' opacity=".45"'); }
      return s + '<circle r="12.3" fill="none" stroke="#6a120d" stroke-width="1.5" opacity=".7"/>';
    } },
    ham: { name: 'Ham', cat: 'meat', size: 10, draw: function (r) {
      var w = 6.4 + r() * 1.2, h = 5.4 + r();
      return '<rect x="' + P(-w) + '" y="' + P(-h) + '" width="' + P(2 * w) + '" height="' + P(2 * h) + '" rx="2.4" fill="url(#pzb-g-ham)" stroke="#c97670" stroke-width=".7"/>' +
        '<path d="M' + P(-w + 1.6) + ' ' + P(1 + r() * 2) + 'C-2 ' + P(-1 - r() * 2) + ' 2 ' + P(2 + r() * 2) + ' ' + P(w - 1.6) + ' ' + P(r() * 2 - 1) + '" stroke="#fbe6e2" stroke-width="1.3" fill="none" opacity=".85" stroke-linecap="round"/>';
    } },
    chk: { name: 'Chicken', cat: 'meat', size: 8.5, draw: function (r) {
      var pts = [], i, a, rr;
      for (i = 0; i < 9; i++) { a = i / 9 * 6.283; rr = 5.2 + r() * 2.2; pts.push([Math.cos(a) * rr * 1.1, Math.sin(a) * rr * 0.85]); }
      return '<path d="' + blob(pts) + '" fill="url(#pzb-g-chk)" stroke="#bf8d52" stroke-width=".9"/>' +
        '<path d="M-4 -2.5L3 -4.5M-3.5 2L4.5 0" stroke="#8a5a2b" stroke-width="1.2" opacity=".45" stroke-linecap="round"/>';
    } },
    anc: { name: 'Anchovies', cat: 'fish', size: 15, draw: function (r) {
      var b = (r() - 0.5) * 3;
      return '<path d="M-15 0C-10 ' + P(-3.4 + b) + ' 8 ' + P(-3.2 + b) + ' 15 -.4C8 ' + P(2.6 + b) + ' -10 ' + P(3.2 + b) + ' -15 0Z" fill="url(#pzb-g-anc)"/>' +
        '<path d="M-13 .1C-6 ' + P(-0.9 + b) + ' 6 ' + P(-0.9 + b) + ' 13 -.3" stroke="#cfc8ba" stroke-width=".9" fill="none" opacity=".7"/>';
    } },
    mus: { name: 'Mushrooms', cat: 'veg', size: 12, draw: function (r) {
      return '<g transform="scale(' + P(0.92 + r() * 0.16) + ' 1)">' +
        '<path d="M-11.5 2.5C-11.8-6-6.5-11 0-11S11.8-6 11.5 2.5C9 3.6 6.5 2.6 4.2 2.8L3.6 9.8C3.3 11.8-3.3 11.8-3.6 9.8L-4.2 2.8C-6.5 2.6-9 3.6-11.5 2.5Z" fill="url(#pzb-g-mus)" stroke="#7a5534" stroke-width="1.2" stroke-linejoin="round"/>' +
        '<path d="M-9.5 1.2C-6-1.5 6-1.5 9.5 1.2" fill="none" stroke="#a88560" stroke-width=".8" opacity=".7"/>' +
        '<path d="M-11.2 1.5C-11.4-6-6.3-10.3 0-10.3S11.4-6 11.2 1.5" fill="none" stroke="#5e3e22" stroke-width="1.6" opacity=".55"/></g>';
    } },
    grp: { name: 'Green pepper', cat: 'veg', size: 13.5, draw: function (r) {
      var d = 'M-12 4Q0 ' + P(-(5 + r() * 5)) + ' 12 4';
      return '<path d="' + d + '" stroke="#2c6a20" stroke-width="4.6" fill="none" stroke-linecap="round"/>' +
        '<path d="' + d + '" stroke="#4f9a35" stroke-width="3" fill="none" stroke-linecap="round"/>' +
        '<path d="' + d + '" stroke="#a6dc84" stroke-width=".7" fill="none" opacity=".7" transform="translate(0 -.9)"/>';
    } },
    oni: { name: 'Red onion', cat: 'veg', size: 12.5, draw: function (r) {
      var k = -(6 + r() * 4);
      function arc(d) {
        return '<path d="' + d + '" stroke="#87306a" stroke-width="2.3" fill="none" stroke-linecap="round"/>' +
          '<path d="' + d + '" stroke="#f0d9e8" stroke-width="1" fill="none" stroke-linecap="round"/>';
      }
      return arc('M-11 3.5Q0 ' + P(k) + ' 11 3.5') + (r() < 0.6 ? arc('M-8 5.8Q0 ' + P(k + 3.6) + ' 8 5.8') : '');
    } },
    oli: { name: 'Black olives', cat: 'veg', size: 6.2, draw: function () {
      return '<circle r="4.5" fill="none" stroke="#25231f" stroke-width="3.2"/>' +
        '<path d="M-3.3-3A4.5 4.5 0 0 1 2.3-3.9" stroke="#8a877c" stroke-width=".8" fill="none" opacity=".7" stroke-linecap="round"/>';
    } },
    crn: { name: 'Sweetcorn', cat: 'veg', size: 6, draw: function (r) {
      var s = '', i, a, x, y;
      for (i = 0; i < 3; i++) {
        a = i * 2.094 + r() * 0.6; x = P(Math.cos(a) * 2.6); y = P(Math.sin(a) * 2.6);
        s += '<ellipse cx="' + x + '" cy="' + y + '" rx="1.9" ry="2.3" transform="rotate(' + Math.round(r() * 180) + ' ' + x + ' ' + y + ')" fill="url(#pzb-g-crn)" stroke="#c99614" stroke-width=".4"/>';
      }
      return s;
    } },
    pin: { name: 'Pineapple', cat: 'fruit', size: 8.6, draw: function (r) {
      var t = P(5.8 + r() * 1.4), b = P(3.8 + r() * 1.2);
      return '<path d="M-' + t + ' -5.2L' + t + ' -5.2 ' + b + ' 5.6-' + b + ' 5.6Z" fill="url(#pzb-g-pin)" stroke="#e2ae2f" stroke-width="1.3" stroke-linejoin="round"/>' +
        '<path d="M-3-3.5L-2 4M0-3.8V4.2M3-3.5L2 4" stroke="#d29a1c" stroke-width=".6" opacity=".6"/>';
    } },
    jal: { name: 'Jalapeños', cat: 'veg', size: 6, draw: function (r) {
      var s = '<circle r="5.6" fill="#2f6a22"/><circle r="4.4" fill="#9fc263"/><circle r="3" fill="#d3e4a2"/>', i, a, x, y;
      for (i = 0; i < 5; i++) {
        a = i * 1.2566 + r() * 0.5; x = P(Math.cos(a) * 1.8); y = P(Math.sin(a) * 1.8);
        s += '<ellipse cx="' + x + '" cy="' + y + '" rx=".8" ry=".55" fill="#f3edcd" transform="rotate(' + Math.round(a * 57.3) + ' ' + x + ' ' + y + ')"/>';
      }
      return s;
    } },
    bas: { name: 'Basil', cat: 'herb', size: 12, draw: function (r) {
      return '<g transform="scale(' + P(0.85 + r() * 0.25) + ')">' +
        '<path d="M-11 0C-6-6.6 5-7 11 0 5 7-6 6.6-11 0Z" fill="url(#pzb-g-bas)"/>' +
        '<path d="M-11 0H10M-5 0L-2-4M0 0L3-4.2M4 0L6.5-3M-5 0L-2 4M0 0L3 4.2M4 0L6.5 3" stroke="#5aa85b" stroke-width=".6" fill="none" opacity=".75"/></g>';
    } },
    // less conventional toppings
    nor: { name: 'Nori', cat: 'seaweed', size: 9.5, draw: function (r) {
      var pts = [[-7, -5.5], [7, -6], [6.6, 5.8], [-6.8, 5.2]].map(function (p) { return P(p[0] + (r() - 0.5) * 1.6) + ' ' + P(p[1] + (r() - 0.5) * 1.6); });
      var s = '<path d="M' + pts.join('L') + 'Z" fill="#1d2a1d" stroke="#0f170f" stroke-width=".8" stroke-linejoin="round"/>', i;
      for (i = 0; i < 10; i++) s += circ((r() - 0.5) * 11, (r() - 0.5) * 9, 0.3 + r() * 0.5, '#4c6b3c', ' opacity=".6"');
      return s + '<path d="M-5 -3.5L4.5 -4M-4.5 1.5L5 1" stroke="#6f8f5c" stroke-width=".5" opacity=".5"/>';
    } },
    kim: { name: 'Kimchi', cat: 'veg', size: 9, draw: function (r) {
      var pts = [], i, a, rr;
      for (i = 0; i < 8; i++) { a = i / 8 * 6.283; rr = 5.4 + r() * 2; pts.push([Math.cos(a) * rr * 1.15, Math.sin(a) * rr * 0.8]); }
      var s = '<path d="' + blob(pts) + '" fill="#d4542b" stroke="#a83a1b" stroke-width=".6"/>' +
        '<path d="M-5.5 -1.5C-2 -3 2 -2.6 5.5 -3.2M-5 2C-1 .8 2.5 1.6 5.8 .6" stroke="#f3d2a2" stroke-width="1.6" fill="none" opacity=".85" stroke-linecap="round"/>';
      for (i = 0; i < 6; i++) s += circ((r() - 0.5) * 10, (r() - 0.5) * 7, 0.35 + r() * 0.35, '#8f1d10', ' opacity=".7"');
      return s;
    } },
    par: { name: 'Pear', cat: 'fruit', size: 12, draw: function (r) {
      var k = P(0.9 + r() * 0.2);
      return '<g transform="scale(1 ' + k + ')"><path d="M-11 2C-8-6 6-8 11-3C7 3-4 6-11 2Z" fill="#f3eccb" stroke="#b9c048" stroke-width="1.6" stroke-linejoin="round"/>' +
        '<path d="M-3.5 .6C-1-1.6 2-1.6 4.2-.6" stroke="#e2d6a2" stroke-width="1.3" fill="none"/>' +
        '<ellipse cx="-.3" cy="-.3" rx=".9" ry=".5" fill="#5b3a1f"/><ellipse cx="2" cy="-.7" rx=".9" ry=".5" fill="#5b3a1f"/></g>';
    } },
    shr: { name: 'Shrimp', cat: 'seafood', size: 9.5, draw: function () {
      var d = 'M-6 3A6.5 6.5 0 1 1 5.5 4.5';
      return '<path d="' + d + '" stroke="#e8784f" stroke-width="5" fill="none" stroke-linecap="round"/>' +
        '<path d="' + d + '" stroke="#f6b08c" stroke-width="2.2" fill="none" stroke-linecap="round" opacity=".8"/>' +
        '<path d="M-4.2-2.5L-1.8-1.6M-1.2-5.2L-.2-2.7M3.2-4.8L2-2.4M5.6-1.4L3.2-.6" stroke="#c95a35" stroke-width=".6" opacity=".7"/>' +
        '<path d="M5.4 4.4L9 7.6 8 3.2Z" fill="#d9603a"/>';
    } },
    egg: { name: 'Egg', cat: 'egg', size: 8.5, draw: function (r) {
      return '<ellipse rx="8.3" ry="7" fill="#fbfaf3" stroke="#e1dbc8" stroke-width=".6"/>' +
        circ(r() - 0.5, r() - 0.5, 3.8, '#f2b830') + '<circle r="2" fill="#f7cf55" opacity=".7"/>';
    } },
    gor: { name: 'Blue cheese', cat: 'dairy', size: 6.5, draw: function (r) {
      var pts = [], i, a;
      for (i = 0; i < 7; i++) { a = i / 7 * 6.283; pts.push([Math.cos(a) * (4 + r() * 1.8), Math.sin(a) * (4 + r() * 1.8)]); }
      var s = '<path d="' + blob(pts) + '" fill="#f1ecdc" stroke="#d6ceb4" stroke-width=".5"/>';
      for (i = 0; i < 5; i++) s += circ((r() - 0.5) * 6, (r() - 0.5) * 6, 0.4 + r() * 0.6, '#4f6f7a', ' opacity=".75"');
      return s;
    } },
    ban: { name: 'Banana', cat: 'fruit', size: 6.5, draw: function (r) {
      var s = '<circle r="6.2" fill="#efe0a0"/><circle r="5.3" fill="#f8f0c6"/>', i, a;
      for (i = 0; i < 5; i++) { a = i * 1.2566 + r() * 0.3; s += circ(Math.cos(a) * 1.4, Math.sin(a) * 1.4, 0.35, '#8a7a4a'); }
      return s;
    } },
    wal: { name: 'Walnuts', cat: 'nut', size: 7, draw: function (r) {
      var pts = [], i, a;
      for (i = 0; i < 10; i++) { a = i / 10 * 6.283; pts.push([Math.cos(a) * (5.2 + (i % 2) * 1.3 + r() * 0.6), Math.sin(a) * (4.4 + (i % 2) * 1.1)]); }
      return '<path d="' + blob(pts) + '" fill="#9a6a3c" stroke="#6e4523" stroke-width=".7"/>' +
        '<path d="M-4 0C-2.5-2 -1 2 0 0S2.5-2 4 0M0-4V4" stroke="#6e4523" stroke-width=".7" fill="none" opacity=".8"/>';
    } },
    // practice-only item, never shown in the real build or the ratings
    tom: { name: 'Tomato slice', cat: 'practice', size: 10, draw: function (r) {
      var s = '<circle r="10" fill="#c8321f"/><circle r="8.6" fill="#e2503a"/>', i, a, x, y;
      for (i = 0; i < 6; i++) {
        a = i * 1.0472 + r() * 0.2; x = P(Math.cos(a) * 4.9); y = P(Math.sin(a) * 4.9);
        s += '<ellipse cx="' + x + '" cy="' + y + '" rx="2.6" ry="1.6" fill="#f6a17c" transform="rotate(' + Math.round(a * 57.3) + ' ' + x + ' ' + y + ')"/>';
        s += circ(Math.cos(a) * 5.3, Math.sin(a) * 5.3, 0.5, '#fbe7b5');
      }
      return s + '<circle r="2.2" fill="#ef7a5c"/>';
    } }
  };
  // a-priori conventionality as a pizza topping; check it against your own sample's norm ratings
  var TIER = { pep: 'common', ham: 'common', chk: 'common', mus: 'common', grp: 'common', oni: 'common', oli: 'common',
    crn: 'common', jal: 'common', bas: 'common', anc: 'mid', pin: 'mid', shr: 'mid', egg: 'mid', gor: 'mid',
    nor: 'unusual', kim: 'unusual', par: 'unusual', ban: 'unusual', wal: 'unusual' };
  Object.keys(TIER).forEach(function (k) { ING[k].tier = TIER[k]; });
  var DEFAULT_INGREDIENTS = ['pep', 'ham', 'chk', 'anc', 'mus', 'grp', 'oni', 'oli', 'crn', 'pin', 'jal', 'bas',
    'shr', 'egg', 'gor', 'nor', 'kim', 'par'];

  var markupCache = {};
  function pieceMarkup(code, v) {
    var k = code + v;
    if (!markupCache[k]) markupCache[k] = ING[code].draw(rng(hash(code) * 31 + v));
    return markupCache[k];
  }
  function placed(code, x, y, rot, v, s) {
    return '<g transform="translate(' + P(x) + ' ' + P(y) + ') rotate(' + rot + ')' + (s ? ' scale(' + s + ')' : '') + '">' + pieceMarkup(code, v) + '</g>';
  }
  function iconMarkup(code) {
    var s = ING[code].size, inner, half;
    if (s < 9) {        // small toppings show as a little heap of three
      inner = placed(code, 0, -s * 0.75, 20, 0) + placed(code, -s * 0.85, s * 0.6, 140, 1) + placed(code, s * 0.85, s * 0.6, 260, 2);
      half = s * 2;
    } else {
      inner = placed(code, 0, 0, (code === 'anc' || code === 'bas') ? -30 : 15, 0);
      half = s * 1.12;
    }
    return '<svg viewBox="' + P(-half) + ' ' + P(-half) + ' ' + P(2 * half) + ' ' + P(2 * half) + '" aria-hidden="true" focusable="false">' + inner + '</svg>';
  }

  // ---------------------------------------------------------------- shared SVG definitions

  function noiseFilter(id, freq, seed, matrix, extra, octaves) {
    if (typeof extra === 'number') { octaves = extra; extra = ''; }
    return '<filter id="' + id + '" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">' +
      '<feTurbulence type="fractalNoise" baseFrequency="' + freq + '" numOctaves="' + (octaves || 3) + '" seed="' + seed + '"/>' +
      '<feColorMatrix type="matrix" values="' + matrix + '"/>' + (extra || '') + '</filter>';
  }
  function grad(id, kind, stops, attrs) {
    return '<' + kind + 'Gradient id="' + id + '"' + (attrs || '') + '>' + stops.map(function (s) {
      return '<stop offset="' + s[0] + '" stop-color="' + s[1] + '"/>';
    }).join('') + '</' + kind + 'Gradient>';
  }
  var V = ' x1="0" y1="0" x2="0" y2="1"';
  var CHEESE = { light: -4.5, normal: -3.55, extra: -2.6 };   // alpha = 9 * noise + k: where melted cheese covers the sauce
  var DEFS = '<svg class="pzb-defs" aria-hidden="true" focusable="false" style="position:absolute;width:0;height:0;overflow:hidden"><defs>' +
    grad('pzb-g-crust', 'radial', [[0, '#e7c07c'], [0.8, '#e2b46a'], [0.87, '#dba055'], [0.93, '#cf8e44'], [0.975, '#b8752f'], [1, '#94592a']]) +
    grad('pzb-g-dough', 'radial', [[0, '#f0dbae'], [0.85, '#ebcf98'], [1, '#e3bd7c']]) +
    grad('pzb-g-sauce-tomato', 'radial', [[0, '#c63a22'], [1, '#a32c19']]) +
    grad('pzb-g-sauce-white', 'radial', [[0, '#f4eddd'], [1, '#e2d5bb']]) +
    grad('pzb-g-sauce-bbq', 'radial', [[0, '#7c2e17'], [1, '#5a1e0d']]) +
    grad('pzb-g-pep', 'radial', [[0, '#c63d2d'], [0.8, '#a42a20'], [1, '#7a1913']], ' cx=".45" cy=".42" r=".6"') +
    grad('pzb-g-ham', 'radial', [[0, '#f4bcb6'], [1, '#dc8c86']]) +
    grad('pzb-g-chk', 'radial', [[0, '#f3e2c1'], [1, '#dab680']]) +
    grad('pzb-g-anc', 'linear', [[0, '#8a6250'], [1, '#4a3024']], V) +
    grad('pzb-g-mus', 'linear', [[0, '#efdfc4'], [1, '#cbb08a']], V) +
    grad('pzb-g-pin', 'linear', [[0, '#f9db6c'], [1, '#ebb63a']], V) +
    grad('pzb-g-bas', 'linear', [[0, '#41974a'], [1, '#1f5d24']], V) +
    grad('pzb-g-crn', 'radial', [[0, '#fde27a'], [1, '#eebc2c']]) +
    '<filter id="pzb-f-blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.5"/></filter>' +
    '<filter id="pzb-f-rough" x="-6%" y="-6%" width="112%" height="112%"><feTurbulence type="fractalNoise" baseFrequency="0.08" numOctaves="2" seed="2" result="n"/>' +
    '<feDisplacementMap in="SourceGraphic" in2="n" scale="5" xChannelSelector="R" yChannelSelector="G"/></filter>' +
    noiseFilter('pzb-f-sauce', 0.15, 4, '0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  2.6 0 0 0 -1.1', '<feComposite in2="SourceGraphic" operator="in"/>') +
    Object.keys(CHEESE).map(function (k) {
      return noiseFilter('pzb-f-cheese-' + k, 0.032, 7, '0.5 0 0 0 0.72  0.55 0 0 0 0.57  0.6 0 0 0 0.17  9 0 0 0 ' + CHEESE[k], 4);
    }).join('') +
    noiseFilter('pzb-f-brown', 0.1, 9, '0 0 0 0 .64  0 0 0 0 .38  0 0 0 0 .14  7 0 0 0 -4.0') +
    '<clipPath id="pzb-cp-pie"><circle r="84"/></clipPath>' +
    '</defs></svg>';

  function baseMarkup() {
    var s = '<circle r="100" cy="3" fill="#000" opacity=".38" filter="url(#pzb-f-blur)"/><circle r="100" fill="url(#pzb-g-crust)"/>';
    var r = rng(42), i, a, d, x, y;
    for (i = 0; i < 22; i++) {     // charred blisters on the rim
      a = r() * 6.283; d = 89 + r() * 9; x = P(Math.cos(a) * d); y = P(Math.sin(a) * d);
      s += '<ellipse cx="' + x + '" cy="' + y + '" rx="' + P(1 + r() * 2.5) + '" ry="' + P(0.6 + r() * 1.2) + '" transform="rotate(' + Math.round(a * 57.3 + 90) + ' ' + x + ' ' + y + ')" fill="#6f3f17" opacity="' + P(0.12 + r() * 0.22) + '"/>';
    }
    for (i = 0; i < 40; i++) {     // flour dust
      a = r() * 6.283; d = 87 + r() * 12;
      s += circ(Math.cos(a) * d, Math.sin(a) * d, 0.3 + r() * 0.4, '#fff', ' opacity=".35"');
    }
    return s + '<circle r="86" fill="url(#pzb-g-dough)"/>' +     // bare dough, seen when there is no sauce
      '<circle class="pzb-sauce" r="86" fill="url(#pzb-g-sauce-tomato)" filter="url(#pzb-f-rough)"/>' +
      '<circle class="pzb-sauce-tex" r="85" fill="#000" filter="url(#pzb-f-sauce)" opacity=".28"/>' +
      '<g clip-path="url(#pzb-cp-pie)"><rect class="pzb-cheese" x="-86" y="-86" width="172" height="172" filter="url(#pzb-f-cheese-normal)"/>' +
      '<rect class="pzb-brown" x="-86" y="-86" width="172" height="172" filter="url(#pzb-f-brown)"/></g>';
  }

  // ---------------------------------------------------------------- styles

  var CSS = [
    '.pzb{--pzb-ink:#2b2622;--pzb-muted:#6d655d;--pzb-line:#e3dbd2;--pzb-card:#fbf8f4;--pzb-accent:#b23a1f;--pzb-accent-ink:#fff;',
    'color:var(--pzb-ink);max-width:980px;margin:0 auto;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent;line-height:1.35;text-align:left}',
    '.pzb *,.pzb *:before,.pzb *:after{box-sizing:border-box}',
    '.pzb button{font:inherit;color:inherit;margin:0;-webkit-appearance:none;appearance:none;cursor:pointer;text-transform:none;letter-spacing:normal}',
    '.pzb input[type=text]{font:inherit;-webkit-user-select:text;user-select:text}',
    '.pzb-prompt{margin:0 0 12px;font-size:1.05em}',
    '.pzb-main{display:flex;gap:18px;align-items:flex-start;justify-content:center}',
    '.pzb-narrow .pzb-main{flex-direction:column;align-items:center;gap:10px}',
    '.pzb-board{flex:none;padding:12px;border-radius:16px;background:repeating-linear-gradient(90deg,rgba(0,0,0,.035) 0 2px,transparent 2px 9px),linear-gradient(90deg,#c89a63,#b9894f 40%,#c99d66 70%,#b58447);box-shadow:inset 0 0 0 1px rgba(0,0,0,.08),0 2px 8px rgba(0,0,0,.12)}',
    '.pzb-narrow .pzb-board{padding:6px;border-radius:12px}',
    '.pzb-pizza{position:relative;touch-action:none}',
    '.pzb-pizza>svg{position:absolute;left:0;top:0;width:100%;height:100%;display:block;overflow:visible}',
    '.pzb-tops{filter:drop-shadow(0 .7px .9px rgba(0,0,0,.45))}',
    '.pzb-ring{position:absolute;left:2.38%;top:2.38%;right:2.38%;bottom:2.38%;border-radius:50%;pointer-events:none;transition:box-shadow .15s}',
    '.pzb-over .pzb-ring{box-shadow:0 0 0 3px rgba(255,255,255,.85),0 0 18px 4px rgba(255,220,150,.65)}',
    '.pzb-base,.pzb-tops{transition:filter 1.6s}',
    '.pzb-brown{opacity:0;transition:opacity 1.6s}',
    '.pzb-baked .pzb-brown{opacity:.55}',
    '.pzb-baked .pzb-base{filter:saturate(1.12) brightness(.95) sepia(.08)}',
    '.pzb-baked .pzb-tops{filter:drop-shadow(0 .7px .9px rgba(0,0,0,.45)) saturate(1.1) brightness(.94) sepia(.1)}',
    '.pzb-target{fill:none;stroke:#fff;stroke-width:2;stroke-dasharray:5 4;animation:pzb-pulse 2.4s ease-in-out infinite}',
    '@keyframes pzb-pulse{50%{opacity:.55}}',
    '.pzb-side{flex:0 0 300px;width:300px}',
    '.pzb-narrow .pzb-side{flex:none;width:100%;max-width:560px}',
    '.pzb-label{font-size:.85em;color:var(--pzb-muted);margin:0 0 6px}',
    '.pzb-tray{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}',
    '.pzb-narrow .pzb-tray{grid-template-columns:repeat(6,minmax(0,1fr));gap:4px}',
    '.pzb-xs .pzb-iname{font-size:8.5px}',
    '.pzb-item{position:relative;display:flex;flex-direction:column;align-items:center;gap:4px;padding:8px 3px 6px;border-radius:12px;background:var(--pzb-card);border:1px solid var(--pzb-line);cursor:grab;touch-action:none;transition:transform .1s,border-color .1s}',
    '.pzb-narrow .pzb-item{padding:5px 0 4px;border-radius:10px;gap:2px}',
    '.pzb-item:hover{border-color:#c9bba9}',
    '.pzb-item.pzb-active{transform:scale(.95);border-color:var(--pzb-accent)}',
    '.pzb-bowl{width:54px;height:54px;border-radius:50%;background:radial-gradient(circle at 50% 38%,#fff 0,#f2ede7 58%,#dcd3c8 100%);box-shadow:inset 0 -2px 3px rgba(0,0,0,.08);display:flex;align-items:center;justify-content:center}',
    '.pzb-narrow .pzb-bowl{width:40px;height:40px}',
    '.pzb-bowl svg{width:78%;height:78%;overflow:visible}',
    '.pzb-iname{font-size:12px;text-align:center;line-height:1.1}',
    '.pzb-narrow .pzb-iname{font-size:9.5px;letter-spacing:-.02em;max-width:100%}',
    '.pzb-badge{position:absolute;top:3px;right:4px;min-width:18px;padding:0 4px;border-radius:9px;background:var(--pzb-accent);color:#fff;font-size:11px;line-height:18px;text-align:center}',
    '.pzb-ctl{margin-top:12px;display:flex;flex-direction:column;gap:8px}',
    '.pzb-seg{display:flex;align-items:center;gap:8px}',
    '.pzb-seg>span{flex:0 0 52px;font-size:.85em;color:var(--pzb-muted)}',
    '.pzb-segbtns{flex:1;display:flex;border:1px solid var(--pzb-line);border-radius:10px;overflow:hidden;background:#fff}',
    '.pzb-segbtns button{flex:1;min-height:36px;border:0;border-left:1px solid var(--pzb-line);background:transparent;font-size:.85em;padding:4px 2px}',
    '.pzb-segbtns button:first-child{border-left:0}',
    '.pzb-segbtns button[aria-pressed=true]{background:var(--pzb-accent);color:var(--pzb-accent-ink)}',
    '.pzb-btns{display:flex;gap:8px}',
    '.pzb-btn{flex:1;min-height:44px;border-radius:10px;border:1px solid var(--pzb-line);background:#fff;padding:6px 10px}',
    '.pzb-btn.pzb-primary{background:var(--pzb-accent);border-color:var(--pzb-accent);color:var(--pzb-accent-ink);font-weight:600}',
    '.pzb-btn:disabled{opacity:.45;cursor:default}',
    '.pzb-note{min-height:1.2em;font-size:.85em;color:var(--pzb-muted)}',
    '.pzb-locked .pzb-item,.pzb-locked .pzb-ctl button{pointer-events:none;opacity:.5}',
    '.pzb-steps{margin:12px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px}',
    '.pzb-steps li{display:flex;gap:8px;align-items:flex-start;font-size:.92em;color:var(--pzb-muted)}',
    '.pzb-steps li:before{content:"";flex:none;width:18px;height:18px;margin-top:1px;border-radius:50%;border:2px solid var(--pzb-line);background:#fff}',
    '.pzb-steps li.pzb-cur{color:var(--pzb-ink);font-weight:600}',
    '.pzb-steps li.pzb-cur:before{border-color:var(--pzb-accent)}',
    '.pzb-steps li.pzb-ok{color:var(--pzb-ink)}',
    '.pzb-steps li.pzb-ok:before{background:#3d8b3d;border-color:#3d8b3d;box-shadow:inset 0 0 0 3px #fff}',
    '.pzb-ghost{position:fixed;left:0;top:0;pointer-events:none;z-index:2147483000;will-change:transform;filter:drop-shadow(0 6px 6px rgba(0,0,0,.35));transition:opacity .12s}',
    '.pzb-ghost svg{width:100%;height:100%;display:block;overflow:visible}',
    '.pzb-ghost.pzb-out{opacity:.55}',
    '.pzb-modal{position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(30,20,10,.45);display:flex;align-items:center;justify-content:center;z-index:2147483001;padding:16px}',
    '.pzb-dialog{background:#fff;color:var(--pzb-ink);border-radius:16px;padding:20px;max-width:360px;width:100%;box-shadow:0 10px 30px rgba(0,0,0,.25)}',
    '.pzb-dialog h3{margin:0 0 6px;font-size:1.1em}',
    '.pzb-dialog p{margin:0 0 16px;color:var(--pzb-muted)}',
    '.pzb-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);max-width:90vw;background:rgba(40,30,20,.92);color:#fff;padding:10px 14px;border-radius:10px;font-size:14px;opacity:0;transition:opacity .2s;pointer-events:none;z-index:2147483002}',
    '.pzb-toast.pzb-show{opacity:1}',
    // follow-up
    '.pzb-card{max-width:620px;margin:0 auto;background:var(--pzb-card);border:1px solid var(--pzb-line);border-radius:16px;padding:18px}',
    '.pzb-narrow .pzb-card{padding:14px 12px}',
    '.pzb-prog{font-size:.85em;color:var(--pzb-muted);margin-bottom:8px}',
    '.pzb-head{display:flex;align-items:center;gap:14px;margin-bottom:10px}',
    '.pzb-head .pzb-bowl{width:84px;height:84px;flex:none}',
    '.pzb-head h3{margin:0;font-size:1.25em}',
    '.pzb-q{margin:16px 0 0}',
    '.pzb-q>p{margin:0 0 8px;font-weight:600}',
    '.pzb-pts{display:flex;gap:4px}',
    '.pzb-pts button{flex:1;min-width:0;min-height:42px;border-radius:9px;border:1px solid var(--pzb-line);background:#fff;font-size:.95em}',
    '.pzb-pts button[aria-pressed=true]{background:var(--pzb-accent);border-color:var(--pzb-accent);color:var(--pzb-accent-ink)}',
    '.pzb-ends{display:flex;justify-content:space-between;gap:12px;font-size:.78em;color:var(--pzb-muted);margin-top:3px}',
    '.pzb-ends span:last-child{text-align:right}',
    '.pzb-checks{display:flex;flex-direction:column;gap:6px}',
    '.pzb-check{display:flex;align-items:center;gap:10px;min-height:40px;padding:6px 10px;border-radius:9px;border:1px solid var(--pzb-line);background:#fff;text-align:left;width:100%}',
    '.pzb-check:before{content:"";flex:none;width:18px;height:18px;border-radius:4px;border:2px solid #b9ada0;background:#fff}',
    '.pzb-check.pzb-radio:before{border-radius:50%}',
    '.pzb-card h3{margin:0 0 4px;font-size:1.15em}',
    '.pzb-sub{margin:0;color:var(--pzb-muted);font-size:.9em}',
    '.pzb-check[aria-pressed=true]{border-color:var(--pzb-accent)}',
    '.pzb-check[aria-pressed=true]:before{background:var(--pzb-accent);border-color:var(--pzb-accent);box-shadow:inset 0 0 0 3px #fff}',
    '.pzb-other{margin-top:6px;width:100%;min-height:40px;border:1px solid var(--pzb-line);border-radius:9px;padding:6px 10px}',
    '.pzb-opt{margin-top:6px}',
    '.pzb-nav{display:flex;justify-content:flex-end;margin-top:18px}',
    '.pzb-nav .pzb-btn{flex:0 1 200px}',
    '.pzb-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:8px;margin:12px 0 4px}',
    '.pzb-narrow .pzb-tiles{grid-template-columns:repeat(auto-fill,minmax(78px,1fr));gap:6px}',
    '.pzb-tile{position:relative;display:flex;flex-direction:column;align-items:center;gap:4px;padding:8px 4px;border-radius:12px;border:2px solid var(--pzb-line);background:#fff;font-size:.82em;line-height:1.15;text-align:center}',
    '.pzb-tile[aria-pressed=true]{border-color:var(--pzb-accent);background:#fdf3ef}',
    '.pzb-tile[aria-pressed=true]:after{content:"";position:absolute;top:5px;right:5px;width:16px;height:16px;border-radius:50%;background:var(--pzb-accent);box-shadow:inset 0 0 0 4px #fdf3ef}',
    '.pzb-tile .pzb-bowl{width:52px;height:52px}',
    '.pzb-narrow .pzb-tile .pzb-bowl{width:44px;height:44px}',
    '@media (prefers-reduced-motion: reduce){.pzb *,.pzb-ghost,.pzb-toast{animation:none!important;transition:none!important}}'
  ].join('\n');

  function injectOnce() {
    if (document.getElementById('pzb-style')) return;
    var st = el('style'); st.id = 'pzb-style'; st.textContent = CSS; document.head.appendChild(st);
    var d = el('div', null, DEFS); document.body.appendChild(d.firstChild);
  }

  // ---------------------------------------------------------------- text

  var TEXT = {
    promptBuild: 'Make the pizza you would like to eat. Drag toppings onto the pizza. Hold a topping still to change its size: it grows and shrinks until you let go. To remove a topping, drag it off the pizza.',
    promptPractice: 'Practice round: learn how to place, move and remove toppings. Nothing you do here counts as your choice.',
    toppings: 'Toppings', sauce: 'Sauce', cheese: 'Cheese',
    sauceNames: { none: 'None', tomato: 'Tomato', white: 'White', bbq: 'BBQ' },
    cheeseNames: { none: 'None', light: 'Light', normal: 'Normal', extra: 'Extra' },
    undo: 'Undo', clear: 'Start over', done: "I'm done", practiceDone: 'Continue',
    confirmTitle: 'Is your pizza finished?', confirmBody: 'You will not be able to change it after this.',
    confirmYes: 'Yes, bake it', confirmNo: 'Keep editing',
    clearTitle: 'Remove all toppings?', clearBody: 'You can undo this.', clearYes: 'Remove all', cancel: 'Cancel',
    tapHint: 'Hold and drag the topping onto the pizza', full: 'There is no room for more toppings',
    waitNote: 'You can finish in {s} s', minNote: 'Add at least {n} toppings to finish',
    baked: 'Your pizza is ready!',
    steps: ['Drag a tomato slice into the dashed circle', 'Add two more slices anywhere on the pizza',
      'Move a slice that is already on the pizza: press it and drag it somewhere else',
      'Change a slice\'s size: press it and hold still, then let go when it is the size you want', 'Remove a slice: drag it from the pizza off the edge'],
    growHint: 'This time, press a slice on the pizza and keep holding still: it will grow and shrink',
    tryAgain: 'Nearly - drop it inside the dashed circle',
    moveHint: 'This time, press a slice that is already on the pizza and drag it to a new place',
    removeHint: 'This time, press a slice on the pizza and drag it off the edge', practiceReady: 'Well done! Press Continue to make your own pizza.',
    // follow-up
    next: 'Next', finish: 'Finish',
    pizzaTitle: 'About your pizza',
    pizzaSub: 'How much do you agree with each statement?',
    agree: ['Strongly disagree', 'Strongly agree'],
    pizzaItems: [['express', 'My pizza expresses who I am.'], ['distinct', 'My pizza is different from the pizza most people would make.'],
      ['auton', 'I made my pizza exactly the way I wanted to.'], ['control', 'While making my pizza, I felt in control of the result.'],
      ['system', 'I followed a rule or system when arranging the toppings.'], ['safety', 'I chose toppings I was confident would be safe for me to eat.']],
    dietTitle: 'About how you eat',
    dietQ: 'Do you follow any of these diets? Choose all that apply.',
    diets: [['vegetarian', 'Vegetarian'], ['vegan', 'Vegan'], ['pescatarian', 'Pescatarian'], ['nopork', "I don't eat pork"], ['nobeef', "I don't eat beef"],
      ['halal', 'Halal'], ['kosher', 'Kosher'], ['glutenfree', 'Gluten-free'], ['dairyfree', 'Lactose- or dairy-free'], ['other', 'Other'], ['none', 'None of these']],
    dietOtherPh: 'Please describe (optional)',
    healthQ: 'Do any of these apply to you? Choose all that apply.',
    health: [['allergy', 'A food allergy'], ['intolerance', 'A food intolerance (e.g. lactose, gluten)'],
      ['digestive', 'Digestive problems (e.g. IBS, reflux, coeliac disease)'], ['badexp', 'A bad experience with food (e.g. food poisoning, a strong reaction)'],
      ['sensory', 'I avoid some foods because of their texture, smell or look'], ['none', 'None of these']],
    healthOtherPh: 'Which foods? (optional)',
    freqQ: 'How often do you eat pizza?',
    freqs: [['never', 'Never'], ['lt1m', 'Less than once a month'], ['1-3m', '1-3 times a month'], ['1w', 'About once a week'], ['gt1w', 'More than once a week']],
    progress: 'Topping {i} of {n}',
    scales: {
      like: ['How much do you like {x} on a pizza?', 'Dislike a lot', 'Like a lot'],
      fam: ['How familiar are you with {x} as a pizza topping?', 'Not at all familiar', 'Very familiar'],
      safe: ['How safe would it feel to eat {x} on a pizza?', 'Not at all safe', 'Completely safe'],
      disg: ['How disgusting do you find {x} on a pizza?', 'Not at all disgusting', 'Extremely disgusting'],
      norm: ['How appropriate would most people think {x} is as a pizza topping?', 'Very inappropriate', 'Very appropriate'],
      ident: ['To what extent does {x} on your pizza reflect who you are?', 'Not at all', 'Very much']
    },
    neverTasted: "I've never tasted it",
    strongQ: 'Do you have strong feelings about any of these ingredients?',
    strongSub: 'Tap every one you do: good or bad. Tap again to undo.',
    strongNone: 'None of these',
    strongProgress: 'Ingredient {i} of {n}',
    feel: {
      feel: ['How do you feel about {x}?', false, [['love', 'I love it'], ['like', 'I like it'], ['mixed', 'Mixed feelings'], ['dislike', 'I dislike it'], ['cant', "I can't stand it"]]],
      about: ['What is it about {x}? Choose all that apply.', true, [['texture', 'Its texture'], ['smell', 'Its smell'], ['taste', 'Its taste'],
        ['look', 'How it looks'], ['touching', 'It touching other food'], ['other', 'Something else']]],
      safe: ['Is {x} a "safe food" for you, one you can nearly always eat?', false, [['yes', 'Yes'], ['sometimes', 'Sometimes'], ['no', 'No']]],
      sameway: ['Does {x} have to be a certain way for you to eat it (a brand, how it is cut or cooked)?', false, [['yes', 'Yes'], ['sometimes', 'Sometimes'], ['no', 'No']]],
      crave: ['Do you crave {x} or go looking for it?', false, [['often', 'Often'], ['sometimes', 'Sometimes'], ['never', 'Never']]]
    },
    reasonsQ: 'You did not put {x} on your pizza. Why not? Choose all that apply.',
    reasons: [['taste', "I don't like the taste or texture"], ['diet', 'My diet (e.g. vegetarian, vegan)'], ['culture', 'Religious or cultural reasons'],
      ['allergy', 'Allergy or intolerance'], ['health', 'Health or calories'], ['safety', 'Worried it might not be safe to eat'],
      ['disgust', 'It puts me off / disgusts me'], ['unfamiliar', "I don't know it well"], ['notpizza', "It doesn't belong on a pizza"],
      ['nofit', 'It does not go with my other toppings'], ['noreason', 'No particular reason'], ['other', 'Something else']],
    reasonOtherPh: 'Please describe (optional)'
  };

  function iname(o, code) { return (o.names && o.names[code]) || ING[code].name; }

  // ================================================================= practice + build

  var BUILD_DEFAULTS = {
    mode: 'build', prefix: null, condition: '', prompt: null,
    ingredients: DEFAULT_INGREDIENTS, shuffle: true,
    sauces: ['none', 'tomato', 'white', 'bbq'], cheeses: ['none', 'light', 'normal', 'extra'],
    sauce: 'tomato', cheese: 'normal', baseChoices: true,
    minSeconds: 0, minPieces: 0, maxPieces: 250, showCounts: false,
    touchLift: 44, logHover: true, confirm: true, bake: true, autoScroll: true, snapIn: false,
    grow: true, growDelay: 500, growMin: 0.5, growMax: 2.5, growPeriod: 3000, stillPx: 8,
    target: [0.42, 0.3], targetTol: 0.12, maxEventChars: 60000,
    names: null, text: null, onSave: null, onFinish: null, onEvent: null
  };

  function Builder(root, opts) {
    injectOnce();
    var o = this.o = extend({}, BUILD_DEFAULTS, opts);
    this.practice = o.mode === 'practice';
    if (o.prefix == null) o.prefix = this.practice ? 'pzp_' : 'pz_';
    if (this.practice) { o.ingredients = ['tom']; o.baseChoices = false; o.confirm = false; o.bake = false; o.shuffle = false; }
    this.T = extend({}, TEXT, o.text);
    this.root = root;
    this.pieces = []; this.stack = []; this.ev = [];
    this.nextId = 1; this.seq = 0; this.drag = null;
    this.locked = false; this.finished = false;
    this.sauce = o.sauce; this.cheese = o.cheese;
    this.hiddenMs = 0; this.hiddenAt = null; this.pointer = null;
    this.tray = o.shuffle ? shuffle(o.ingredients) : o.ingredients.slice();
    this.startIso = new Date().toISOString();
    this.step = 0; this.stepAdds = 0; this.tries = []; this.stepT = [];
    this._build();
    this.t0 = now();
    this._bind();
    this.log('start', this.tray.join(' '));
    this._tick();
    if (o.autoScroll) { var self = this; setTimeout(function () { self._fit(); }, 60); }
  }

  // On a phone, scroll once so the pizza and the whole tray are on screen together: a drag cannot scroll the page.
  Builder.prototype._fit = function () {
    if (this.layout !== 'narrow') return;
    var vh = global.innerHeight, top = this.boardEl.getBoundingClientRect().top;
    var bottom = this.w.querySelector('.pzb-tray').getBoundingClientRect().bottom;
    if (bottom <= vh - 8 || bottom - top > vh) return;
    global.scrollBy(0, Math.min(top - 8, bottom - vh + 8));
  };

  Builder.prototype._build = function () {
    var o = this.o, T = this.T, self = this;
    var w = this.w = el('div', 'pzb pzb-mode-' + o.mode);
    var prompt = o.prompt != null ? o.prompt : (this.practice ? T.promptPractice : T.promptBuild);
    if (prompt) w.appendChild(el('p', 'pzb-prompt', esc(prompt)));
    var main = el('div', 'pzb-main'); w.appendChild(main);
    var board = this.boardEl = el('div', 'pzb-board'); main.appendChild(board);
    var pz = this.pizzaEl = el('div', 'pzb-pizza'); board.appendChild(pz);
    var vb = ' viewBox="' + (-VIEW) + ' ' + (-VIEW) + ' ' + (2 * VIEW) + ' ' + (2 * VIEW) + '" aria-hidden="true" focusable="false"';
    pz.innerHTML = '<svg class="pzb-base"' + vb + '>' + baseMarkup() + '</svg>' +
      '<svg class="pzb-guide"' + vb + '></svg><svg class="pzb-tops"' + vb + '></svg><div class="pzb-ring"></div>';
    this.baseSvg = pz.children[0]; this.guideSvg = pz.children[1]; this.topsSvg = pz.children[2];
    this._applyBase();

    var side = el('div', 'pzb-side'); main.appendChild(side);
    side.appendChild(el('div', 'pzb-label', esc(T.toppings)));
    var tray = el('div', 'pzb-tray'); side.appendChild(tray);
    if (this.practice) {
      this.stepsEl = el('ol', 'pzb-steps');
      T.steps.forEach(function (s) { self.stepsEl.appendChild(el('li', null, esc(s))); });
      side.appendChild(this.stepsEl);
      this.guideSvg.innerHTML = '<circle class="pzb-target" cx="' + P(o.target[0] * 100) + '" cy="' + P(-o.target[1] * 100) + '" r="' + P(o.targetTol * 100) + '"/>';
    }
    this.items = {};
    this.tray.forEach(function (code) {
      var it = el('div', 'pzb-item', '<div class="pzb-bowl">' + iconMarkup(code) + '</div><div class="pzb-iname">' + esc(iname(o, code)) + '</div>');
      it.setAttribute('role', 'button'); it.setAttribute('aria-label', iname(o, code));
      it.setAttribute('data-ing', code);
      if (o.showCounts) { it.appendChild(el('span', 'pzb-badge')); }
      tray.appendChild(it); self.items[code] = it;
    });

    var ctl = el('div', 'pzb-ctl'); side.appendChild(ctl);
    if (o.baseChoices) {
      ctl.appendChild(this._seg('sauce', T.sauce, o.sauces, T.sauceNames));
      ctl.appendChild(this._seg('cheese', T.cheese, o.cheeses, T.cheeseNames));
    }
    var btns = el('div', 'pzb-btns'); ctl.appendChild(btns);
    if (!this.practice) {
      this.undoBtn = el('button', 'pzb-btn', esc(T.undo)); this.undoBtn.type = 'button'; btns.appendChild(this.undoBtn);
      this.clearBtn = el('button', 'pzb-btn', esc(T.clear)); this.clearBtn.type = 'button'; btns.appendChild(this.clearBtn);
      this.undoBtn.onclick = function () { self.undo(); };
      this.clearBtn.onclick = function () { self._clearAsk(); };
    }
    this.doneBtn = el('button', 'pzb-btn pzb-primary', esc(this.practice ? T.practiceDone : T.done)); this.doneBtn.type = 'button';
    btns.appendChild(this.doneBtn);
    this.doneBtn.onclick = function () { self._doneClick(); };
    this.noteEl = el('div', 'pzb-note'); ctl.appendChild(this.noteEl);

    this.toastEl = el('div', 'pzb-toast'); document.body.appendChild(this.toastEl);
    this.root.appendChild(w);
    this._layout();
    this._render();
    this._steps();
  };

  Builder.prototype._seg = function (k, label, vals, names) {
    var self = this, row = el('div', 'pzb-seg'), box = el('div', 'pzb-segbtns');
    row.appendChild(el('span', null, esc(label))); row.appendChild(box);
    vals.forEach(function (v) {
      var b = el('button', null, esc(names[v] || v)); b.type = 'button'; b.setAttribute('data-v', v);
      b.setAttribute('aria-pressed', String(self[k] === v));
      b.onclick = function () {
        if (self.locked || self[k] === v) return;
        self[k] = v; self._applyBase(); self.log(k, v);
        [].forEach.call(box.children, function (c) { c.setAttribute('aria-pressed', String(c.getAttribute('data-v') === v)); });
      };
      box.appendChild(b);
    });
    return row;
  };

  Builder.prototype._applyBase = function () {
    var s = this.baseSvg.querySelector('.pzb-sauce'), c = this.baseSvg.querySelector('.pzb-cheese');
    var t = this.baseSvg.querySelector('.pzb-sauce-tex');
    if (this.sauce === 'none') { s.setAttribute('display', 'none'); t.setAttribute('display', 'none'); }
    else { s.removeAttribute('display'); t.removeAttribute('display'); s.setAttribute('fill', 'url(#pzb-g-sauce-' + this.sauce + ')'); }
    if (this.cheese === 'none') c.setAttribute('display', 'none');
    else { c.removeAttribute('display'); c.setAttribute('filter', 'url(#pzb-f-cheese-' + this.cheese + ')'); }
  };

  // Size the pizza to the space the survey gives us, not the window: Qualtrics questions are narrower than the page.
  Builder.prototype._layout = function () {
    var W = this.root.clientWidth || this.w.clientWidth || 320;
    var narrow = W < 680, vh = global.innerHeight || 700;
    this.w.classList.toggle('pzb-narrow', narrow);
    this.w.classList.toggle('pzb-xs', W < 330);
    var pad = narrow ? 12 : 24;
    var size = narrow ? Math.min(W - pad, vh * 0.52, 560) : Math.min(W - 318 - pad, vh * 0.8, 600);
    size = Math.max(220, Math.floor(size));
    this.pizzaEl.style.width = this.pizzaEl.style.height = size + 'px';
    this.layout = narrow ? 'narrow' : 'wide';
  };

  Builder.prototype._bind = function () {
    var self = this, o = this.o;
    this.h = {
      move: function (e) { self._move(e); },
      up: function (e) { self._up(e, false); },
      cancel: function (e) { self._up(e, true); },
      resize: function () { self._layout(); },
      vis: function () {
        var hidden = document.visibilityState === 'hidden';
        if (hidden) { self.hiddenAt = now(); self.log('hide'); }
        else if (self.hiddenAt != null) { self.hiddenMs += now() - self.hiddenAt; self.hiddenAt = null; self.log('show'); }
      },
      pagehide: function () { self.save(true); },
      menu: function (e) { e.preventDefault(); }
    };
    global.addEventListener('pointermove', this.h.move, { passive: false });
    global.addEventListener('pointerup', this.h.up);
    global.addEventListener('pointercancel', this.h.cancel);
    global.addEventListener('resize', this.h.resize);
    global.addEventListener('pagehide', this.h.pagehide);
    document.addEventListener('visibilitychange', this.h.vis);
    this.w.addEventListener('contextmenu', this.h.menu);
    if (global.ResizeObserver) { this.ro = new ResizeObserver(this.h.resize); this.ro.observe(this.root); }

    this.tray.forEach(function (code) {
      var it = self.items[code], hoverT = null;
      it.addEventListener('pointerdown', function (e) {
        if (self.locked || self.drag || (e.pointerType === 'mouse' && e.button !== 0)) return;
        e.preventDefault();
        if (self.pieces.length >= o.maxPieces) { self.toast(self.T.full); return; }
        var p = { id: self.nextId++, ing: code, x: 0, y: 0, rot: Math.round(Math.random() * 360), s: Math.round((0.9 + Math.random() * 0.2) * 100) / 100, v: Math.floor(Math.random() * 3), n: 0, g: 1 };
        self.log('pick', code, p.id, (e.pointerType || 'mouse').charAt(0));
        it.classList.add('pzb-active');
        self._startDrag(e, p, it);
      });
      if (o.logHover) {
        it.addEventListener('pointerenter', function (e) { if (e.pointerType === 'mouse' && !self.drag) hoverT = now(); });
        it.addEventListener('pointerleave', function (e) {
          if (e.pointerType !== 'mouse' || hoverT == null) return;
          var d = Math.round(now() - hoverT); hoverT = null;
          if (d >= 150 && !self.locked) self.log('hover', code, d);
        });
      }
    });

    this.pizzaEl.addEventListener('pointerdown', function (e) {
      if (self.locked || self.drag || (e.pointerType === 'mouse' && e.button !== 0)) return;
      var p = self._hit(e);
      if (!p) return;
      e.preventDefault();
      self.log('grab', p.ing, p.id);
      self._startDrag(e, p, null);
    });
  };

  Builder.prototype.destroy = function () {
    global.removeEventListener('pointermove', this.h.move);
    global.removeEventListener('pointerup', this.h.up);
    global.removeEventListener('pointercancel', this.h.cancel);
    global.removeEventListener('resize', this.h.resize);
    global.removeEventListener('pagehide', this.h.pagehide);
    document.removeEventListener('visibilitychange', this.h.vis);
    if (this.ro) this.ro.disconnect();
    clearInterval(this.timer); clearTimeout(this.saveT);
    if (this.toastEl.parentNode) this.toastEl.parentNode.removeChild(this.toastEl);
    if (this.w.parentNode) this.w.parentNode.removeChild(this.w);
  };

  Builder.prototype._geom = function () {
    var r = this.pizzaEl.getBoundingClientRect();
    return { left: r.left, top: r.top, ppu: r.width / (2 * VIEW) };
  };
  Builder.prototype._toPizza = function (cx, cy, g) {
    var ux = (cx - g.left) / g.ppu - VIEW, uy = (cy - g.top) / g.ppu - VIEW;
    return { x: ux / 100, y: -uy / 100 };
  };

  // Placed toppings can be tiny, so pick the topping whose centre is nearest (relative to its size) rather than relying on exact hits.
  Builder.prototype._hit = function (e) {
    var g = this._geom(), q = this._toPizza(e.clientX, e.clientY, g);
    var tol = (e.pointerType === 'touch' ? 10 : 3) / g.ppu, best = null, bestScore = Infinity;
    for (var i = this.pieces.length - 1; i >= 0; i--) {
      var p = this.pieces[i], dx = (q.x - p.x) * 100, dy = (q.y - p.y) * 100;
      var rad = ING[p.ing].size * p.s * (p.g || 1) * 0.85 + tol, d = Math.sqrt(dx * dx + dy * dy);
      if (d <= rad && d / rad < bestScore - 0.15) { best = p; bestScore = d / rad; }
    }
    return best;
  };

  Builder.prototype._startDrag = function (e, p, trayEl) {
    var g = this._geom(), lift = e.pointerType === 'touch' ? this.o.touchLift : 0, offX = 0, offY = -lift;
    if (!this.pointer) this.pointer = e.pointerType || 'mouse';
    if (!trayEl) {
      offX = g.left + (p.x * 100 + VIEW) * g.ppu - e.clientX;
      offY = g.top + (-p.y * 100 + VIEW) * g.ppu - e.clientY;   // lifted above the finger only once it moves
      var node = this.topsSvg.querySelector('[data-pid="' + p.id + '"]');
      if (node) node.style.visibility = 'hidden';
    }
    var g0 = p.g || 1, S = ING[p.ing].size * 1.3 * p.s * g0, half = S * g.ppu * 1.08;
    var gh = el('div', 'pzb-ghost', '<svg viewBox="' + P(-S) + ' ' + P(-S) + ' ' + P(2 * S) + ' ' + P(2 * S) + '"><g transform="rotate(' + p.rot + ') scale(' + P(p.s * g0) + ')">' + pieceMarkup(p.ing, p.v) + '</g></svg>');
    gh.style.width = gh.style.height = (2 * half) + 'px';
    document.body.appendChild(gh);
    try { (trayEl || this.pizzaEl).setPointerCapture(e.pointerId); } catch (err) { /* capture is a nicety */ }
    var t = now();
    this.drag = { p: p, tray: trayEl, id: e.pointerId, t0: t, offX: offX, offY: offY, sx: e.clientX, sy: e.clientY,
      lx: e.clientX, ly: e.clientY, moved: false, ghost: gh, half: half, x0: p.x, y0: p.y,
      g0: g0, g: g0, hx: e.clientX, hy: e.clientY, ht: t, lt: t, lift: trayEl ? 0 : lift };
    this._frame();
  };

  // Runs every frame while dragging. While the pointer stays still the piece pulses smoothly between growMin and
  // growMax, starting from its current size and growing first; letting go keeps the size of that moment.
  Builder.prototype._frame = function () {
    var d = this.drag, o = this.o, self = this;
    if (!d) return;
    var t = now();
    if (o.grow) {
      if (Math.abs(d.lx - d.hx) + Math.abs(d.ly - d.hy) > o.stillPx) { d.hx = d.lx; d.hy = d.ly; d.ht = t; d.ph = null; }
      else if (t - d.ht > o.growDelay) {
        var mid = (o.growMax + o.growMin) / 2, amp = (o.growMax - o.growMin) / 2;
        if (d.ph == null) d.ph = Math.asin(Math.max(-1, Math.min(1, (d.g - mid) / amp)));
        d.ph += 2 * Math.PI * (t - d.lt) / o.growPeriod;
        d.g = mid + amp * Math.sin(d.ph);
      }
    }
    d.lt = t;
    this._paint();
    d.raf = requestAnimationFrame(function () { if (self.drag === d) self._frame(); });
  };

  Builder.prototype._move = function (e) {
    var d = this.drag;
    if (!d || e.pointerId !== d.id) return;
    e.preventDefault();
    d.lx = e.clientX; d.ly = e.clientY;
    if (!d.moved && Math.abs(d.lx - d.sx) + Math.abs(d.ly - d.sy) > 6) { d.moved = true; d.offY -= d.lift; }
  };

  Builder.prototype._paint = function () {
    var d = this.drag; if (!d) return;
    var cx = d.lx + d.offX, cy = d.ly + d.offY;
    d.ghost.style.transform = 'translate3d(' + (cx - d.half) + 'px,' + (cy - d.half) + 'px,0) scale(' + (d.g / d.g0) + ')';
    var q = this._toPizza(cx, cy, this._geom()), on = Math.sqrt(q.x * q.x + q.y * q.y) <= R_OFF;
    d.ghost.classList.toggle('pzb-out', !on);
    this.w.classList.toggle('pzb-over', on);
  };

  Builder.prototype._up = function (e, cancelled) {
    var d = this.drag;
    if (!d || e.pointerId !== d.id) return;
    this.drag = null;
    if (d.raf) cancelAnimationFrame(d.raf);
    this.w.classList.remove('pzb-over');
    if (d.tray) d.tray.classList.remove('pzb-active');
    var p = d.p, ms = Math.round(now() - d.t0), gNew = Math.round(d.g * 100) / 100, grew = Math.abs(gNew - (p.g || 1)) > 0.01;
    var g = this._geom(), q = this._toPizza(e.clientX + d.offX, e.clientY + d.offY, g);
    var r = Math.sqrt(q.x * q.x + q.y * q.y), snap = 0;
    if (this.o.snapIn && r > R_SNAP && r <= R_OFF) { q.x *= R_SNAP / r; q.y *= R_SNAP / r; snap = 1; }
    var on = r <= R_OFF, x = r3(q.x), y = r3(q.y);
    this._dropGhost(d, on && !cancelled);

    if (cancelled) { this.log('abort', p.ing, p.id); if (!d.tray) this._render(); return; }
    if (!d.moved && grew && !d.tray) {  // pressed and held in place: the topping changed size where it lies
      this.stack.push({ a: 'resize', p: p, g: p.g });
      p.g = gNew;
      this.log('resize', p.ing, p.id, gNew, ms);
      if (this.practice && this.step === 3) this._nextStep();
      this._render();
      return;
    }
    if (!d.moved) {                     // a tap, not a drag
      this.log('tap', p.ing, p.id);
      if (d.tray) this.toast(this.T.tapHint); else this._render();
      return;
    }
    if (d.tray) {
      if (on) {
        p.x = x; p.y = y; p.n = ++this.seq; p.g = gNew;
        this.pieces.push(p); this.stack.push({ a: 'add', p: p });
        this.log('add', p.ing, p.id, x, y, ms, snap, gNew);
        if (this.practice && this.step === 3 && grew) this._nextStep(); else this._practiceAdd(p);
      } else {
        this.log('reject', p.ing, p.id, x, y, ms);
      }
    } else if (on) {
      this.stack.push({ a: 'move', p: p, x: p.x, y: p.y, g: p.g });
      p.x = x; p.y = y; p.g = gNew;
      this.pieces.splice(this.pieces.indexOf(p), 1); this.pieces.push(p);   // a moved topping lands on top
      this.log('move', p.ing, p.id, x, y, ms, snap, gNew);
      if (this.practice && (this.step === 2 || (this.step === 3 && grew))) this._nextStep();
    } else {
      var i = this.pieces.indexOf(p);
      this.pieces.splice(i, 1); this.stack.push({ a: 'remove', p: p, i: i });
      this.log('remove', p.ing, p.id, x, y, ms);
      if (this.practice && this.step === 4) this._nextStep();
    }
    this._render();
  };

  Builder.prototype._dropGhost = function (d, landed) {
    var gh = d.ghost;
    if (landed) { gh.parentNode.removeChild(gh); return; }
    gh.style.transition = 'opacity .25s, transform .25s';
    gh.style.opacity = '0';
    setTimeout(function () { if (gh.parentNode) gh.parentNode.removeChild(gh); }, 260);
  };

  Builder.prototype._render = function () {
    var s = '', counts = this.counts();
    for (var i = 0; i < this.pieces.length; i++) {
      var p = this.pieces[i];
      s += '<g data-pid="' + p.id + '" transform="translate(' + P(p.x * 100) + ' ' + P(-p.y * 100) + ') rotate(' + p.rot + ') scale(' + P(p.s * (p.g || 1)) + ')">' + pieceMarkup(p.ing, p.v) + '</g>';
    }
    this.topsSvg.innerHTML = s;
    if (this.o.showCounts) for (var k in this.items) {
      var b = this.items[k].querySelector('.pzb-badge');
      b.textContent = counts[k] || ''; b.style.display = counts[k] ? '' : 'none';
    }
    if (this.undoBtn) this.undoBtn.disabled = !this.stack.length;
    if (this.clearBtn) this.clearBtn.disabled = !this.pieces.length;
    this._tick();
    this.save();
  };

  Builder.prototype.undo = function () {
    if (this.locked) return;
    var a = this.stack.pop(); if (!a) return;
    if (a.a === 'add') this.pieces.splice(this.pieces.indexOf(a.p), 1);
    else if (a.a === 'move') { a.p.x = a.x; a.p.y = a.y; a.p.g = a.g; }
    else if (a.a === 'resize') a.p.g = a.g;
    else if (a.a === 'remove') this.pieces.splice(a.i, 0, a.p);
    else if (a.a === 'clear') this.pieces = a.ps;
    this.log('undo', a.a, a.p ? a.p.id : a.ps.length);
    this._render();
  };

  Builder.prototype._clearAsk = function () {
    var self = this, T = this.T;
    if (!this.pieces.length || this.locked) return;
    this.modal(T.clearTitle, T.clearBody, T.clearYes, T.cancel, function (yes) {
      if (!yes) return;
      self.stack.push({ a: 'clear', ps: self.pieces.slice() });
      self.log('clear', self.pieces.length);
      self.pieces = [];
      self._render();
    });
  };

  // ---- practice steps
  Builder.prototype._practiceAdd = function (p) {
    if (!this.practice) return;
    if (this.step === 0) {
      var dx = p.x - this.o.target[0], dy = p.y - this.o.target[1], err = Math.sqrt(dx * dx + dy * dy);
      this.tries.push(r3(err));
      if (err <= this.o.targetTol || this.tries.length >= 3) this._nextStep();
      else this.toast(this.T.tryAgain);
    } else if (this.step === 1) { if (++this.stepAdds >= 2) this._nextStep(); }
    else if (this.step === 2) this.toast(this.T.moveHint);
    else if (this.step === 3) this.toast(this.T.growHint);
    else if (this.step === 4) this.toast(this.T.removeHint);
  };
  Builder.prototype._nextStep = function () {
    this.stepT.push(Math.round(now() - this.t0));
    this.step++;
    if (this.step === 1) this.guideSvg.innerHTML = '';
    if (this.step >= 5) this.toast(this.T.practiceReady);
    this._steps(); this._tick();
  };
  Builder.prototype._steps = function () {
    if (!this.stepsEl) return;
    var st = this.step;
    [].forEach.call(this.stepsEl.children, function (li, i) {
      li.className = i < st ? 'pzb-ok' : (i === st ? 'pzb-cur' : '');
    });
  };

  // ---- finishing
  Builder.prototype._tick = function () {
    if (this.finished) return;
    var self = this, o = this.o, T = this.T, el2 = (now() - this.t0) / 1000, note = '';
    var ok = true;
    if (this.practice) ok = this.step >= 5;
    else {
      if (this.pieces.length < o.minPieces) { ok = false; note = fmt(T.minNote, { n: o.minPieces }); }
      if (el2 < o.minSeconds) { ok = false; note = note || fmt(T.waitNote, { s: Math.ceil(o.minSeconds - el2) }); }
    }
    this.doneBtn.disabled = !ok;
    this.noteEl.textContent = note;
    if (!this.timer && !this.practice && o.minSeconds > 0) this.timer = setInterval(function () { self._tick(); }, 500);
  };

  Builder.prototype._doneClick = function () {
    var self = this, T = this.T;
    if (this.locked || this.doneBtn.disabled) return;
    this.log('done');
    if (!this.o.confirm) { this._finish(); return; }
    this.modal(T.confirmTitle, T.confirmBody, T.confirmYes, T.confirmNo, function (yes) {
      if (yes) self._finish(); else self.log('cancel');
    });
  };

  Builder.prototype._finish = function () {
    var self = this;
    this.locked = this.finished = true;
    clearInterval(this.timer);
    this.w.classList.add('pzb-locked');
    this.log('finish');
    this.save(true);
    try { global.sessionStorage.setItem('pzb:' + this.o.prefix + 'counts', countsString(this.counts())); } catch (e) { /* storage blocked */ }
    if (this.o.bake) {
      this.w.classList.add('pzb-baked');
      this.noteEl.textContent = this.T.baked;
      setTimeout(function () { if (self.o.onFinish) self.o.onFinish(self.data()); }, 1700);
    } else if (this.o.onFinish) this.o.onFinish(this.data());
  };

  // ---- data
  Builder.prototype.log = function () {
    if (this.finished && arguments[0] !== 'finish') return;
    var a = [Math.round(now() - (this.t0 || now()))].concat([].slice.call(arguments));
    this.ev.push(a);
    if (this.o.onEvent) this.o.onEvent(a);
    this.save();
  };

  Builder.prototype.counts = function () {
    var c = {}, self = this;
    this.o.ingredients.forEach(function (k) { c[k] = 0; });
    this.pieces.forEach(function (p) { c[p.ing] = (c[p.ing] || 0) + 1; });
    return c;
  };

  Builder.prototype.data = function () {
    var o = this.o, counts = this.counts(), ev = this.ev, n = {}, drags = [], adds = [], first = {};
    ev.forEach(function (e) {
      n[e[1]] = (n[e[1]] || 0) + 1;
      if (e[1] === 'add' || e[1] === 'move') drags.push(e[6]);
      if (e[1] === 'add') { adds.push(e[0]); if (first.add == null) first.add = e[0]; }
      if (e[1] === 'pick' && first.pick == null) first.pick = e[0];
      if (e[1] === 'done' && first.done == null) first.done = e[0];
    });
    var gaps = []; for (var i = 1; i < adds.length; i++) gaps.push(adds[i] - adds[i - 1]);
    var last = ev.length ? ev[ev.length - 1][0] : 0, fin = null;
    ev.forEach(function (e) { if (e[1] === 'finish') fin = e[0]; });
    var mq = function (q) { try { return global.matchMedia(q).matches; } catch (e) { return null; } };
    var summary = {
      v: VERSION, mode: o.mode, prefix: o.prefix, cond: o.condition, start: this.startIso, finished: this.finished,
      tFinish: fin, tDone: first.done == null ? null : first.done, tSubmit: fin, nDone: n.done || 0, nDoneCancelled: n.cancel || 0,
      tFirstPick: first.pick == null ? null : first.pick, tFirstAdd: first.add == null ? null : first.add, tLast: last,
      nPieces: this.pieces.length, nDistinct: Object.keys(counts).filter(function (k) { return counts[k] > 0; }).length,
      counts: counts, sauce: o.baseChoices ? this.sauce : null, cheese: o.baseChoices ? this.cheese : null, tray: this.tray,
      n: { pick: n.pick || 0, add: n.add || 0, reject: n.reject || 0, tap: n.tap || 0, move: n.move || 0, remove: n.remove || 0, resize: n.resize || 0, undo: n.undo || 0, clear: n.clear || 0, hover: n.hover || 0 },
      nGrown: this.pieces.filter(function (p) { return (p.g || 1) > 1.01; }).length,
      nShrunk: this.pieces.filter(function (p) { return (p.g || 1) < 0.99; }).length,
      dragMsMedian: median(drags), addGapMsMedian: median(gaps),
      hiddenMs: Math.round(this.hiddenMs + (this.hiddenAt != null ? now() - this.hiddenAt : 0)), hides: n.hide || 0,
      pointer: this.pointer, coarse: mq('(pointer: coarse)'), hover: mq('(hover: hover)'),
      vw: global.innerWidth, vh: global.innerHeight, dpr: global.devicePixelRatio || 1,
      pizzaPx: Math.round(this.pizzaEl.getBoundingClientRect().width * 200 / (2 * VIEW)), layout: this.layout
    };
    if (this.practice) { summary.targetErr = this.tries; summary.stepT = this.stepT; summary.stepsDone = this.step; }
    var final = this.pieces.map(function (p) { return [p.id, p.ing, p.x, p.y, p.rot, p.s, p.v, p.n, p.g || 1]; });
    var events = JSON.stringify(ev);
    if (events.length > o.maxEventChars) {      // keep the record small enough for embedded data: hovers go first
      events = JSON.stringify(ev.filter(function (e) { return e[1] !== 'hover'; }));
      summary.trimmed = 1;
    }
    var fields = {};
    fields[o.prefix + 'final'] = JSON.stringify(final);
    fields[o.prefix + 'events'] = events;
    fields[o.prefix + 'summary'] = JSON.stringify(summary);
    fields[o.prefix + 'counts'] = countsString(counts);
    return { fields: fields, final: final, events: ev, summary: summary };
  };

  Builder.prototype.save = function (immediate) {
    var self = this;
    clearTimeout(this.saveT);
    if (!immediate) { this.saveT = setTimeout(function () { self.save(true); }, 300); return; }
    if (!this.o.onSave) return;
    var f = this.data().fields;
    for (var k in f) { try { this.o.onSave(k, f[k]); } catch (e) { /* never let saving break the task */ } }
  };

  // ---- small UI
  Builder.prototype.toast = function (msg) {
    var t = this.toastEl; t.textContent = msg; t.classList.add('pzb-show');
    clearTimeout(this.toastT); this.toastT = setTimeout(function () { t.classList.remove('pzb-show'); }, 2600);
  };
  Builder.prototype.modal = modal;

  function modal(title, body, yes, no, cb) {
    var m = el('div', 'pzb-modal pzb', '<div class="pzb-dialog" role="dialog" aria-modal="true"><h3>' + esc(title) + '</h3><p>' + esc(body) + '</p>' +
      '<div class="pzb-btns"><button type="button" class="pzb-btn">' + esc(no) + '</button><button type="button" class="pzb-btn pzb-primary">' + esc(yes) + '</button></div></div>');
    var b = m.querySelectorAll('button');
    function close(v) { m.parentNode.removeChild(m); cb(v); }
    b[0].onclick = function () { close(false); };
    b[1].onclick = function () { close(true); };
    document.body.appendChild(m);
    b[1].focus();
  }

  // ================================================================= follow-up ratings

  var FOLLOW_DEFAULTS = {
    mode: 'followup', prefix: 'pzf_', ingredients: DEFAULT_INGREDIENTS, shuffle: true,
    // style 'strong': one tappable list ("strong feelings?"), then five questions per ingredient tapped.
    // style 'ratings': every ingredient rated on scales, reasons for those left off. askPizza / askDiet default to on only there.
    style: 'strong', feelQuestions: ['feel', 'about', 'safe', 'sameway', 'crave'],
    counts: null, countsFrom: 'pz_', askPizza: null, askDiet: null, askReasons: true, askIdentity: true, force: true,
    scales: ['like', 'fam', 'safe', 'disg', 'norm'], pizzaItems: null, names: null, text: null, onSave: null, onFinish: null
  };

  function Followup(root, opts) {
    injectOnce();
    var o = this.o = extend({}, FOLLOW_DEFAULTS, opts);
    var strong = o.style !== 'ratings';
    if (o.askPizza == null) o.askPizza = !strong;
    if (o.askDiet == null) o.askDiet = !strong;
    this.T = extend({}, TEXT, o.text);
    if (o.text && o.text.feel) this.T.feel = extend({}, TEXT.feel, o.text.feel);
    if (o.text && o.text.scales) this.T.scales = extend({}, TEXT.scales, o.text.scales);
    this.counts = parseCounts(o.counts);
    if (!Object.keys(this.counts).length) {     // piping gave nothing: use what the build page left in this tab
      try { this.counts = parseCounts(global.sessionStorage.getItem('pzb:' + o.countsFrom + 'counts')); } catch (e) { /* storage blocked */ }
    }
    this.haveCounts = Object.keys(this.counts).length > 0;
    this.order = o.shuffle ? shuffle(o.ingredients) : o.ingredients.slice();
    this.root = root; this.t0 = now();
    this.res = { v: VERSION, style: strong ? 'strong' : 'ratings', start: new Date().toISOString(), countsKnown: this.haveCounts, order: this.order, pizza: {},
      diet: [], dietOther: '', health: [], healthOther: '', freq: null, items: {} };
    if (strong) { this.res.strong = []; this.res.none = false; }
    this.screens = strong ? ['@pick'].concat(o.askPizza ? ['@pizza'] : [], o.askDiet ? ['@diet'] : [])
      : (o.askPizza ? ['@pizza'] : []).concat(this.order, o.askDiet ? ['@diet'] : []);
    this.w = el('div', 'pzb pzb-mode-followup');
    root.appendChild(this.w);
    var self = this;
    this.h = function () { self.w.classList.toggle('pzb-narrow', (root.clientWidth || 320) < 520); };
    this.h(); global.addEventListener('resize', this.h);
    this.i = 0;
    this._show();
  }

  Followup.prototype._show = function () {
    this.w.innerHTML = '';
    this.cardT = now();
    var sc = this.screens[this.i];
    if (sc === '@diet') this._diet(); else if (sc === '@pizza') this._pizza(); else if (sc === '@pick') this._pick();
    else if (sc.indexOf('f:') === 0) this._feel(sc.slice(2)); else this._item(sc);
    try { this.w.scrollIntoView({ block: 'start' }); } catch (e) { /* old browsers */ }
  };

  Followup.prototype._checks = function (opts, multi, sel, onChange, exclusive) {
    var box = el('div', 'pzb-checks');
    opts.forEach(function (op) {
      var b = el('button', 'pzb-check' + (multi ? '' : ' pzb-radio'), esc(op[1])); b.type = 'button';
      b.setAttribute('data-v', op[0]); b.setAttribute('aria-pressed', String(sel.indexOf(op[0]) >= 0));
      b.onclick = function () {
        var v = op[0], i = sel.indexOf(v);
        if (!multi) { sel.length = 0; sel.push(v); }
        else if (i >= 0) sel.splice(i, 1);
        else {
          if (exclusive && exclusive.indexOf(v) >= 0) sel.length = 0;
          else if (exclusive) exclusive.forEach(function (x) { var j = sel.indexOf(x); if (j >= 0) sel.splice(j, 1); });
          sel.push(v);
        }
        [].forEach.call(box.children, function (c) { c.setAttribute('aria-pressed', String(sel.indexOf(c.getAttribute('data-v')) >= 0)); });
        onChange();
      };
      box.appendChild(b);
    });
    return box;
  };

  Followup.prototype._scale = function (question, ends, onPick) {
    var q = el('div', 'pzb-q'), pts = el('div', 'pzb-pts');
    q.appendChild(el('p', null, esc(question)));
    for (var v = 1; v <= 7; v++) (function (v) {
      var b = el('button', null, String(v)); b.type = 'button'; b.setAttribute('aria-pressed', 'false');
      b.setAttribute('aria-label', v + (v === 1 ? ' - ' + ends[0] : v === 7 ? ' - ' + ends[1] : ''));
      b.onclick = function () {
        [].forEach.call(pts.children, function (c, i) { c.setAttribute('aria-pressed', String(i + 1 === v)); });
        onPick(v);
      };
      pts.appendChild(b);
    })(v);
    q.appendChild(pts);
    q.appendChild(el('div', 'pzb-ends', '<span>' + esc(ends[0]) + '</span><span>' + esc(ends[1]) + '</span>'));
    q.clear = function () { [].forEach.call(pts.children, function (c) { c.setAttribute('aria-pressed', 'false'); }); };
    return q;
  };

  Followup.prototype._pizza = function () {
    var T = this.T, self = this, card = el('div', 'pzb-card'), items = this.o.pizzaItems || T.pizzaItems, pz = this.res.pizza, upd;
    pz.t = {};
    card.appendChild(el('h3', null, esc(T.pizzaTitle)));
    card.appendChild(el('p', 'pzb-sub', esc(T.pizzaSub)));
    items.forEach(function (it) {
      pz[it[0]] = null;
      card.appendChild(self._scale(it[1], T.agree, function (v) {
        pz[it[0]] = v; if (pz.t[it[0]] == null) pz.t[it[0]] = Math.round(now() - self.cardT); upd();
      }));
    });
    upd = this._nav(card, function () { return items.every(function (it) { return pz[it[0]] != null; }); }, T.next);
    this.w.appendChild(card);
  };

  Followup.prototype._nav = function (card, ready, label) {
    var self = this, nav = el('div', 'pzb-nav'), b = el('button', 'pzb-btn pzb-primary', esc(label)); b.type = 'button';
    nav.appendChild(b); card.appendChild(nav);
    function upd() { b.disabled = self.o.force && !ready(); }
    b.onclick = function () { if (!b.disabled) self._next(); };
    upd();
    return upd;
  };

  Followup.prototype._diet = function () {
    var T = this.T, r = this.res, card = el('div', 'pzb-card'), upd, last = this.i === this.screens.length - 1;
    card.appendChild(el('h3', null, esc(T.dietTitle)));
    function multi(self, question, opts, sel, ph, otherKey, showFor) {
      var q = el('div', 'pzb-q'); q.appendChild(el('p', null, esc(question))); card.appendChild(q);
      var other = el('input', 'pzb-other'); other.type = 'text'; other.placeholder = ph;
      other.oninput = function () { r[otherKey] = other.value.slice(0, 200); };
      function show() { other.style.display = sel.some(function (v) { return showFor.indexOf(v) >= 0; }) ? '' : 'none'; }
      q.appendChild(self._checks(opts, true, sel, function () { show(); upd(); }, ['none']));
      q.appendChild(other); show();
    }
    multi(this, T.dietQ, T.diets, r.diet, T.dietOtherPh, 'dietOther', ['other']);
    multi(this, T.healthQ, T.health, r.health, T.healthOtherPh, 'healthOther', ['allergy', 'intolerance', 'digestive', 'badexp', 'sensory']);
    var q2 = el('div', 'pzb-q'); q2.appendChild(el('p', null, esc(T.freqQ))); card.appendChild(q2);
    var fsel = [];
    q2.appendChild(this._checks(T.freqs, false, fsel, function () { r.freq = fsel[0]; upd(); }));
    upd = this._nav(card, function () { return r.diet.length > 0 && r.health.length > 0 && r.freq; }, last ? T.finish : T.next);
    this.w.appendChild(card);
  };

  Followup.prototype._item = function (code) {
    var T = this.T, o = this.o, self = this, card = el('div', 'pzb-card'), name = iname(o, code), upd, likeQ;
    var placed = this.haveCounts ? (this.counts[code] || 0) : null;
    var it = this.res.items[code] = { placed: placed, t: {} };
    var nItems = this.order.length, nth = this.order.indexOf(code) + 1;
    card.appendChild(el('div', 'pzb-prog', esc(fmt(T.progress, { i: nth, n: nItems }))));
    card.appendChild(el('div', 'pzb-head', '<div class="pzb-bowl">' + iconMarkup(code) + '</div><h3>' + esc(name) + '</h3>'));
    var scales = o.scales.slice();
    if (o.askIdentity && placed !== 0) scales.push('ident');      // only for toppings they used (all, if counts are unknown)
    scales.forEach(function (k) {
      var sc = T.scales[k];
      it[k] = null;
      var q = self._scale(fmt(sc[0], { x: name.toLowerCase() }), [sc[1], sc[2]], function (v) {
        it[k] = v; if (it.t[k] == null) it.t[k] = Math.round(now() - self.cardT);
        if (k === 'like' && it.never) { it.never = false; neverBtn.setAttribute('aria-pressed', 'false'); }
        upd();
      });
      if (k === 'like') {
        likeQ = q; it.never = false;
        var neverBtn = el('button', 'pzb-check pzb-opt', esc(T.neverTasted)); neverBtn.type = 'button'; neverBtn.setAttribute('aria-pressed', 'false');
        neverBtn.onclick = function () {
          it.never = !it.never; neverBtn.setAttribute('aria-pressed', String(it.never));
          if (it.never) { it.like = null; likeQ.clear(); }
          upd();
        };
        q.appendChild(neverBtn);
      }
      card.appendChild(q);
    });
    var askWhy = o.askReasons && this.haveCounts && !(this.counts[code] > 0);
    if (askWhy) {
      it.reasons = []; it.other = '';
      var q = el('div', 'pzb-q'); q.appendChild(el('p', null, esc(fmt(T.reasonsQ, { x: name.toLowerCase() }))));
      var other = el('input', 'pzb-other'); other.type = 'text'; other.placeholder = T.reasonOtherPh; other.style.display = 'none';
      other.oninput = function () { it.other = other.value.slice(0, 200); };
      q.appendChild(this._checks(T.reasons, true, it.reasons, function () {
        if (it.t.reasons == null) it.t.reasons = Math.round(now() - self.cardT);
        other.style.display = it.reasons.indexOf('other') >= 0 ? '' : 'none'; upd();
      }, ['noreason']));
      q.appendChild(other); card.appendChild(q);
    }
    var last = this.i === this.screens.length - 1;
    upd = this._nav(card, function () {
      for (var j = 0; j < scales.length; j++) { var k = scales[j]; if (it[k] == null && !(k === 'like' && it.never)) return false; }
      return !askWhy || it.reasons.length > 0;
    }, last ? T.finish : T.next);
    this.w.appendChild(card);
  };

  // One screen: every ingredient as a tile to tap, "do you have strong feelings about any of these?"
  Followup.prototype._pick = function () {
    var T = this.T, o = this.o, r = this.res, self = this, card = el('div', 'pzb-card'), upd;
    card.appendChild(el('h3', null, esc(T.strongQ)));
    card.appendChild(el('p', 'pzb-sub', esc(T.strongSub)));
    var grid = el('div', 'pzb-tiles'), noneBtn;
    this.order.forEach(function (code) {
      var b = el('button', 'pzb-tile', '<div class="pzb-bowl">' + iconMarkup(code) + '</div><span>' + esc(iname(o, code)) + '</span>');
      b.type = 'button'; b.setAttribute('aria-pressed', 'false'); b.setAttribute('data-ing', code);
      b.onclick = function () {
        var i = r.strong.indexOf(code);
        if (i >= 0) r.strong.splice(i, 1); else { r.strong.push(code); r.none = false; noneBtn.setAttribute('aria-pressed', 'false'); }
        b.setAttribute('aria-pressed', String(i < 0));
        if (r.firstTapMs == null) r.firstTapMs = Math.round(now() - self.cardT);
        upd();
      };
      grid.appendChild(b);
    });
    card.appendChild(grid);
    noneBtn = el('button', 'pzb-check pzb-opt', esc(T.strongNone)); noneBtn.type = 'button'; noneBtn.setAttribute('aria-pressed', 'false');
    noneBtn.onclick = function () {
      r.none = !r.none; noneBtn.setAttribute('aria-pressed', String(r.none));
      if (r.none) { r.strong.length = 0; [].forEach.call(grid.children, function (t) { t.setAttribute('aria-pressed', 'false'); }); }
      upd();
    };
    card.appendChild(noneBtn);
    upd = this._nav(card, function () { return r.strong.length > 0 || r.none; }, T.next);
    this.w.appendChild(card);
  };

  // Up to five questions about one ingredient the participant has strong feelings about.
  Followup.prototype._feel = function (code) {
    var T = this.T, o = this.o, self = this, card = el('div', 'pzb-card'), name = iname(o, code), upd;
    var picked = this.screens.filter(function (x) { return x.indexOf('f:') === 0; });
    var it = this.res.items[code] = { placed: this.haveCounts ? (this.counts[code] || 0) : null, t: {} };
    card.appendChild(el('div', 'pzb-prog', esc(fmt(T.strongProgress, { i: picked.indexOf('f:' + code) + 1, n: picked.length }))));
    card.appendChild(el('div', 'pzb-head', '<div class="pzb-bowl">' + iconMarkup(code) + '</div><h3>' + esc(name) + '</h3>'));
    var qs = o.feelQuestions.filter(function (k) { return T.feel[k]; }).slice(0, 5);
    qs.forEach(function (k) {
      var def = T.feel[k], multi = def[1], sel = [];
      it[k] = multi ? [] : null;
      var q = el('div', 'pzb-q'); q.appendChild(el('p', null, esc(fmt(def[0], { x: name.toLowerCase() }))));
      q.appendChild(self._checks(def[2], multi, multi ? it[k] : sel, function () {
        if (!multi) it[k] = sel[0];
        if (it.t[k] == null) it.t[k] = Math.round(now() - self.cardT);
        upd();
      }));
      card.appendChild(q);
    });
    var last = this.i === this.screens.length - 1;
    upd = this._nav(card, function () {
      return qs.every(function (k) { return T.feel[k][1] ? it[k].length > 0 : it[k] != null; });
    }, last ? T.finish : T.next);
    this.w.appendChild(card);
  };

  Followup.prototype._next = function () {
    var ms = Math.round(now() - this.cardT), sc = this.screens[this.i];
    if (sc === '@diet') this.res.dietMs = ms; else if (sc === '@pizza') this.res.pizza.ms = ms;
    else if (sc === '@pick') {
      this.res.pickMs = ms;
      var picked = this.order.filter(function (k) { return this.res.strong.indexOf(k) >= 0; }, this);   // asked in the list's order
      this.screens.splice.apply(this.screens, [this.i + 1, 0].concat(picked.map(function (k) { return 'f:' + k; })));
    } else this.res.items[sc.indexOf('f:') === 0 ? sc.slice(2) : sc].ms = ms;
    this.i++;
    this.save();
    if (this.i >= this.screens.length) {
      this.res.finished = true; this.res.tTotal = Math.round(now() - this.t0);
      this.save();
      this.w.innerHTML = '';
      global.removeEventListener('resize', this.h);
      if (this.o.onFinish) this.o.onFinish(this.res);
      return;
    }
    this._show();
  };

  Followup.prototype.data = function () { var f = {}; f[this.o.prefix + 'data'] = JSON.stringify(this.res); return { fields: f, result: this.res }; };
  Followup.prototype.save = function () {
    if (!this.o.onSave) return;
    var f = this.data().fields;
    for (var k in f) { try { this.o.onSave(k, f[k]); } catch (e) { /* ignore */ } }
  };

  // ================================================================= public API

  global.PizzaBuilder = {
    version: VERSION,
    ingredients: ING,
    defaultIngredients: DEFAULT_INGREDIENTS.slice(),
    text: TEXT,
    mount: function (root, opts) {
      if (typeof root === 'string') root = document.querySelector(root);
      return (opts && opts.mode === 'followup') ? new Followup(root, opts) : new Builder(root, opts);
    },
    parseCounts: parseCounts,
    // Writes each field to Qualtrics embedded data. Older layouts read setEmbeddedData;
    // the Simple layout reads setJSEmbeddedData, which stores the field as __js_<name>.
    qualtricsSaver: function () {
      return function (k, v) {
        var SE = global.Qualtrics && global.Qualtrics.SurveyEngine;
        if (!SE) return;
        try { if (SE.setEmbeddedData) SE.setEmbeddedData(k, v); } catch (e) { /* not in this layout */ }
        try { if (SE.setJSEmbeddedData) SE.setJSEmbeddedData(k, v); } catch (e) { /* not in this layout */ }
      };
    }
  };
})(typeof window !== 'undefined' ? window : this);
