/*!
 * Pizza Builder - participant preview for the demo page.
 * Turns the captured embedded-data fields into a readable summary: composition and diet class, normality against a
 * reference distribution, space (symmetry, contact, stacking), size and time. The same definitions as
 * analysis/analyse.py, computed for one participant in the browser. Not used in the Qualtrics survey.
 *
 *   PizzaPreview.render(element, fields)   // fields = { pz_final: '...', pz_events: '...', ... }
 */
(function (global) {
  'use strict';

  // SIMULATED reference of 200 pizzas, so the demo can show a normality score. Replace with your pilot data
  // (the analysis script's --reference) before reading anything into it.
  var REF = {"n": 200, "counts": {"pep": 114, "ham": 52, "chk": 46, "anc": 6, "mus": 99, "grp": 59, "oni": 67, "oli": 69, "crn": 33, "pin": 32, "jal": 38, "bas": 52, "shr": 8, "egg": 9, "gor": 12, "nor": 5, "kim": 5, "par": 9}, "sizes": [5, 5, 3, 8, 1, 2, 5, 5, 2, 6, 4, 4, 4, 2, 1, 3, 5, 3, 5, 4, 3, 2, 1, 6, 3, 2, 2, 7, 4, 2, 3, 5, 4, 2, 4, 6, 6, 3, 1, 3, 4, 4, 4, 3, 2, 4, 2, 4, 4, 3, 4, 2, 4, 5, 4, 3, 5, 3, 6, 6, 3, 4, 3, 1, 5, 6, 6, 6, 0, 4, 1, 5, 3, 1, 3, 6, 5, 3, 1, 1, 5, 2, 3, 4, 2, 3, 3, 3, 3, 5, 4, 2, 4, 4, 2, 5, 3, 7, 1, 5, 1, 6, 4, 4, 3, 5, 5, 2, 4, 4, 4, 4, 1, 5, 6, 3, 4, 3, 5, 3, 1, 5, 5, 3, 4, 5, 4, 3, 6, 1, 2, 3, 10, 4, 4, 1, 4, 3, 2, 5, 4, 1, 2, 3, 3, 6, 2, 2, 3, 1, 1, 6, 6, 2, 5, 4, 6, 3, 3, 2, 2, 3, 1, 2, 3, 6, 1, 4, 6, 6, 4, 4, 3, 3, 3, 2, 3, 3, 3, 4, 3, 2, 5, 2, 6, 3, 7, 5, 3, 5, 2, 1, 2, 4, 6, 4, 2, 3, 4, 5], "scores": [6.043, 6.043, 6.043, 6.043, 6.043, 6.043, 6.072, 6.072, 6.452, 6.481, 6.481, 6.481, 6.481, 6.973, 6.973, 7.002, 7.002, 7.037, 7.336, 7.381, 7.381, 7.41, 7.41, 7.446, 7.446, 7.446, 7.475, 7.475, 7.561, 7.561, 7.561, 7.561, 7.59, 7.716, 7.745, 7.826, 7.826, 7.97, 7.97, 7.97, 7.999, 8.149, 8.149, 8.237, 8.237, 8.237, 8.237, 8.266, 8.302, 8.331, 8.376, 8.4, 8.405, 8.405, 8.483, 8.491, 8.52, 8.52, 8.556, 8.556, 8.556, 8.558, 8.587, 8.587, 8.71, 8.727, 8.792, 8.821, 8.825, 8.862, 8.891, 8.9, 8.9, 8.993, 8.993, 9.079, 9.108, 9.234, 9.263, 9.263, 9.263, 9.315, 9.344, 9.344, 9.394, 9.443, 9.488, 9.488, 9.582, 9.64, 9.668, 9.751, 9.768, 9.792, 10.001, 10.02, 10.056, 10.074, 10.154, 10.228, 10.31, 10.409, 10.447, 10.508, 10.536, 10.608, 10.608, 10.719, 10.733, 10.781, 10.817, 10.862, 10.913, 10.913, 10.927, 10.932, 10.944, 10.995, 11.003, 11.015, 11.033, 11.035, 11.067, 11.085, 11.158, 11.232, 11.24, 11.286, 11.422, 11.502, 11.506, 11.522, 11.576, 11.617, 11.642, 11.747, 11.874, 12.026, 12.195, 12.264, 12.283, 12.315, 12.352, 12.402, 12.431, 12.516, 12.75, 12.862, 12.89, 13.006, 13.042, 13.042, 13.273, 13.273, 13.318, 13.32, 13.34, 13.401, 13.63, 13.659, 13.7, 13.747, 13.749, 13.78, 14.186, 14.186, 14.188, 14.256, 14.285, 14.442, 14.473, 14.487, 14.489, 14.681, 14.94, 15.127, 15.399, 15.447, 15.705, 15.806, 15.898, 16.06, 16.103, 16.257, 16.306, 16.512, 16.713, 17.399, 17.762, 17.866, 17.95, 17.964, 17.987, 18.452, 19.126, 19.264, 19.346, 19.578, 19.654, 24.642]};
  REF.simulated = true;

  var NAMES = { pep: 'Pepperoni', ham: 'Ham', chk: 'Chicken', anc: 'Anchovies', mus: 'Mushrooms', grp: 'Green pepper', oni: 'Red onion',
    oli: 'Black olives', crn: 'Sweetcorn', pin: 'Pineapple', jal: 'Jalapeños', bas: 'Basil', shr: 'Shrimp', egg: 'Egg', gor: 'Blue cheese',
    nor: 'Nori', kim: 'Kimchi', par: 'Pear', ban: 'Banana', wal: 'Walnuts', tom: 'Tomato slice' };
  var DIET = { pep: 'meat', ham: 'meat', chk: 'meat', anc: 'seafood', shr: 'seafood', egg: 'vegetarian', gor: 'vegetarian' };
  var TIER = { anc: 'mid', pin: 'mid', shr: 'mid', egg: 'mid', gor: 'mid', nor: 'unusual', kim: 'unusual', par: 'unusual', ban: 'unusual', wal: 'unusual' };
  var FOOT = { pep: [0, 13], ham: [1, 6.4], chk: [1.5, 6.5], anc: [12, 2.8], mus: [0, 11], grp: [11, 3], oni: [10, 2], oli: [0, 6.1], crn: [0, 4.7],
    pin: [0, 6.5], jal: [0, 5.6], bas: [9.5, 5], shr: [0, 8], egg: [1, 7.2], gor: [0, 5], nor: [1.5, 6.3], kim: [2, 5.8], par: [8, 4], ban: [0, 6.2],
    wal: [0.6, 5.8], tom: [0, 10] };
  var CATS = { pep: 'meat', ham: 'meat', chk: 'meat', anc: 'seafood', shr: 'seafood', mus: 'veg', grp: 'veg', oni: 'veg', oli: 'veg', crn: 'veg',
    jal: 'veg', kim: 'veg', pin: 'fruit', par: 'fruit', ban: 'fruit', bas: 'herb', egg: 'egg', gor: 'dairy', nor: 'seaweed', wal: 'nut' };
  var CLASS_LABEL = { vegan: 'Vegan', vegetarian: 'Vegetarian', pescatarian: 'Pescatarian', meat: 'Contains meat' };

  function J(v, d) { try { return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function median(a) { if (!a.length) return null; a = a.slice().sort(function (x, y) { return x - y; }); var m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; }
  function sec(ms) { return ms == null ? '-' : (ms / 1000).toFixed(1) + ' s'; }

  // ---- geometry, as in analyse.py: every piece is a capsule (segment + half-width) in radius units
  function capsule(p) {
    var f = FOOT[p.ing] || [0, 8], a = p.rot * Math.PI / 180, dx = Math.cos(a) * f[0] * p.s / 100, dy = -Math.sin(a) * f[0] * p.s / 100;
    return [[p.x - dx, p.y - dy], [p.x + dx, p.y + dy], f[1] * p.s / 100];
  }
  function pointSeg(pt, a, b) {
    var vx = b[0] - a[0], vy = b[1] - a[1], L = vx * vx + vy * vy;
    var t = L === 0 ? 0 : Math.max(0, Math.min(1, ((pt[0] - a[0]) * vx + (pt[1] - a[1]) * vy) / L));
    return Math.hypot(pt[0] - a[0] - t * vx, pt[1] - a[1] - t * vy);
  }
  function segDist(a, b, c, d) {
    function cr(o, p, q) { return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0]); }
    var d1 = cr(c, d, a), d2 = cr(c, d, b), d3 = cr(a, b, c), d4 = cr(a, b, d);
    if (((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0)) && d1 && d2 && d3 && d4) return 0;
    return Math.min(pointSeg(a, c, d), pointSeg(b, c, d), pointSeg(c, a, b), pointSeg(d, a, b));
  }
  function contacts(ps) {
    var caps = ps.map(capsule), touch = 0, stack = 0, inTouch = {}, depth = ps.map(function () { return 1; });
    for (var i = 0; i < ps.length; i++) for (var j = i + 1; j < ps.length; j++) {
      var gap = (segDist(caps[i][0], caps[i][1], caps[j][0], caps[j][1]) - caps[i][2] - caps[j][2]) * 100;
      if (gap > 1) continue;
      inTouch[i] = inTouch[j] = 1;
      if (-gap > 0.5 * Math.min(caps[i][2], caps[j][2]) * 100) { stack++; depth[j] = Math.max(depth[j], depth[i] + 1); } else touch++;
    }
    return { touch: touch, stack: stack, share: ps.length ? Object.keys(inTouch).length / ps.length : 0, pile: ps.length ? Math.max.apply(null, depth) : 0 };
  }
  // Symmetry: mean distance from each transformed piece to the nearest piece of the same topping, divided by the same
  // for random layouts of the same toppings (0 = perfect, 1 = like random). Mirror: best of 18 axes; rotation: k = 2..8.
  function symCost(ps, T) {
    var tot = 0;
    ps.forEach(function (p) {
      var t = T(p.x, p.y), best = Infinity;
      ps.forEach(function (q) { if (q.ing === p.ing) best = Math.min(best, Math.hypot(t[0] - q.x, t[1] - q.y)); });
      tot += best;
    });
    return tot / ps.length;
  }
  function mirrorT(phi) { var c = Math.cos(2 * phi), s = Math.sin(2 * phi); return function (x, y) { return [c * x + s * y, s * x - c * y]; }; }
  function rotT(a) { var c = Math.cos(a), s = Math.sin(a); return function (x, y) { return [c * x - s * y, s * x + c * y]; }; }
  function randomLike(ps, rnd) { return ps.map(function (p) { var r = 0.9 * Math.sqrt(rnd()), t = rnd() * 2 * Math.PI; return { ing: p.ing, x: r * Math.cos(t), y: r * Math.sin(t) }; }); }
  function symmetry(ps) {
    if (ps.length < 2) return null;
    var seed = 7, rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    var axes = []; for (var a = 0; a < 180; a += 10) axes.push(a * Math.PI / 180);
    function bestMirror(pts) { var b = Infinity, ax = 0; axes.forEach(function (phi) { var c = symCost(pts, mirrorT(phi)); if (c < b) { b = c; ax = phi; } }); return [b, ax]; }
    var obs = bestMirror(ps), nul = 0, N = 30;
    for (var i = 0; i < N; i++) nul += bestMirror(randomLike(ps, rnd))[0];
    var best = null;
    for (var k = 2; k <= 8; k++) {
      var T = rotT(2 * Math.PI / k), o = symCost(ps, T), nn = 0;
      for (var j = 0; j < 15; j++) nn += symCost(randomLike(ps, rnd), T);
      var ratio = o / (nn / 15);
      if (!best || ratio <= best.ratio + 0.02) best = { ratio: best ? Math.min(ratio, best.ratio) : ratio, k: k };
    }
    return { mirror: obs[0] / (nul / N), axis: obs[1], rot: best.ratio, k: best.k };
  }

  function border(ps) {
    var zones = ps.map(function (p) {
      var c = capsule(p), rOut = Math.max(Math.hypot(c[0][0], c[0][1]), Math.hypot(c[1][0], c[1][1])) + c[2];
      return { zone: rOut > 1.005 ? 'over' : rOut > 0.86 ? 'crust' : 'inside', rOut: rOut };
    });
    var maxOut = zones.reduce(function (m, z) { return Math.max(m, z.rOut); }, 0);
    return { zones: zones, crust: zones.filter(function (z) { return z.zone === 'crust'; }).length,
      over: zones.filter(function (z) { return z.zone === 'over'; }).length, overhangMm: Math.max(0, maxOut - 1) * 150 };
  }

  function fitResid(xs, ys, kind) {
    if (xs.length < 3) return 0;
    var fx = kind === 'line' ? xs : xs.map(function (x) { return x * x; });
    var mx = fx.reduce(function (a, b) { return a + b; }, 0) / fx.length, my = ys.reduce(function (a, b) { return a + b; }, 0) / ys.length;
    var vx = 0, cv = 0; fx.forEach(function (x, i) { vx += (x - mx) * (x - mx); cv += (x - mx) * (ys[i] - my); });
    var b = vx ? cv / vx : 0, worst = 0;
    fx.forEach(function (x, i) { worst = Math.max(worst, Math.abs(ys[i] - (my + b * (x - mx)))); });
    return worst;
  }
  function mean(a) { return a.reduce(function (x, y) { return x + y; }, 0) / a.length; }
  function pstdev(a) { var m = mean(a); return Math.sqrt(mean(a.map(function (x) { return (x - m) * (x - m); }))); }

  // Face detection: the same rules as face_detect() in analyse.py (see its description there).
  function faceDetect(ps) {
    var n = ps.length;
    if (n < 3) return null;
    var info = ps.map(function (p) {
      var c = capsule(p), h = Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]) / 2;
      return { x: p.x, y: p.y, w: c[2], h: h, ing: p.ing, ux: h ? (c[1][0] - c[0][0]) / (2 * h) : 1, uy: h ? (c[1][1] - c[0][1]) / (2 * h) : 0 };
    });
    var best = null, cos35 = Math.cos(35 * Math.PI / 180);
    for (var i = 0; i < n; i++) for (var j = i + 1; j < n; j++) {
      var A = info[i], B = info[j];
      if (A.h > 0.03 || B.h > 0.03 || A.ing !== B.ing) continue;
      var dx = B.x - A.x, dy = B.y - A.y, d = Math.hypot(dx, dy);
      if (d < 0.3 || d > 1.0) continue;
      var part = {}; part[i] = part[j] = 1;
      for (var k = 0; k < n; k++) if (k !== i && k !== j && (Math.hypot(info[k].x - A.x, info[k].y - A.y) <= A.w || Math.hypot(info[k].x - B.x, info[k].y - B.y) <= B.w)) part[k] = 1;
      var crowded = false;
      for (k = 0; k < n && !crowded; k++) if (!part[k] && (Math.hypot(info[k].x - A.x, info[k].y - A.y) < 0.4 * d || Math.hypot(info[k].x - B.x, info[k].y - B.y) < 0.4 * d)) crowded = true;
      if (crowded) continue;
      var ux = dx / d, uy = dy / d, mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
      [1, -1].forEach(function (sgn) {
        var px = -uy * sgn, py = ux * sgn, loc = [];
        for (var k = 0; k < n; k++) if (!part[k]) { var vx = info[k].x - mx, vy = info[k].y - my; loc.push([k, (vx * ux + vy * uy) / d, (vx * px + vy * py) / d]); }
        var mouth = null, mouthAl = 0, kind = '';
        loc.some(function (l) {
          var q = info[l[0]];
          if (q.h >= 0.04 && l[2] >= 0.45 && l[2] <= 2.2 && Math.abs(l[1]) <= 0.35 && Math.abs(q.ux * ux + q.uy * uy) >= cos35 && 2 * (q.h + q.w) >= 0.45 * d) {
            mouth = [l[0]]; mouthAl = l[1]; kind = NAMES[q.ing] || q.ing; return true;
          }
          return false;
        });
        if (!mouth) {
          var cand = loc.filter(function (l) { return l[2] >= 0.45 && l[2] <= 2.2 && Math.abs(l[1]) <= 1.1; })
            .map(function (l) { return [l[1], l[2], l[0]]; }).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1] || a[2] - b[2]; });
          var m = cand.length, len = cand.map(function () { return 1; }), prev = cand.map(function () { return -1; });
          for (var b2 = 0; b2 < m; b2++) for (var a2 = 0; a2 < b2; a2++) {
            var gap = cand[b2][0] - cand[a2][0];
            if (gap > 0 && gap <= 0.8 && Math.abs(cand[b2][1] - cand[a2][1]) <= 0.3 && len[a2] + 1 > len[b2]) { len[b2] = len[a2] + 1; prev[b2] = a2; }
          }
          var ends = cand.map(function (_, e) { return e; }).sort(function (x, y) { return len[y] - len[x] || x - y; });
          for (var e = 0; e < ends.length && len[ends[e]] >= 3; e++) {
            var chain = [], c = ends[e];
            while (c !== -1) { chain.unshift(c); c = prev[c]; }
            var als = chain.map(function (c) { return cand[c][0]; }), pps = chain.map(function (c) { return cand[c][1]; });
            var gaps = als.slice(1).map(function (x, t) { return x - als[t]; });
            var even = pstdev(gaps) <= 0.35 * mean(gaps), smooth = Math.min(fitResid(als, pps, 'line'), fitResid(als, pps, 'smile')) <= 0.08;
            if (als[als.length - 1] - als[0] >= 0.6 && Math.abs(mean(als)) <= 0.25 && Math.abs(als[0] + als[als.length - 1]) <= 0.35 && even && smooth) {
              mouth = chain.map(function (c) { return cand[c][2]; }); mouthAl = mean(als);
              var kinds = {}; mouth.forEach(function (k) { kinds[(NAMES[info[k].ing] || info[k].ing).toLowerCase()] = 1; });
              kind = 'row of ' + mouth.length + ' ' + Object.keys(kinds).join('/');
              break;
            }
          }
        }
        if (!mouth) return;
        var used = {}; Object.keys(part).forEach(function (k) { used[k] = 1; }); mouth.forEach(function (k) { used[k] = 1; });
        var mpos = {}; loc.forEach(function (l) { if (mouth.indexOf(l[0]) >= 0) mpos[l[0]] = [l[1], l[2]]; });
        if (mouth.length > 1) {
          var ms = mouth.map(function (k) { return mpos[k]; }).sort(function (a, b) { return a[0] - b[0]; });
          var step = mean(ms.slice(1).map(function (v, t) { return v[0] - ms[t][0]; }));
          var gapEye = Infinity; ms.forEach(function (v) { [-0.5, 0.5].forEach(function (ex) { gapEye = Math.min(gapEye, Math.hypot(v[0] - ex, v[1])); }); });
          if (gapEye < Math.max(0.45, 1.3 * step)) return;
          var endK = [mouth.reduce(function (a, b) { return mpos[a][0] <= mpos[b][0] ? a : b; }), mouth.reduce(function (a, b) { return mpos[a][0] >= mpos[b][0] ? a : b; })];
          var mIngs = {}; mouth.forEach(function (k) { mIngs[info[k].ing] = 1; });
          for (var k2 = 0; k2 < n; k2++) if (mIngs[info[k2].ing] && !used[k2] && endK.some(function (e2) { return Math.hypot(info[k2].x - info[e2].x, info[k2].y - info[e2].y) <= 1.5 * step * d; })) return;
        }
        var mouthTop = Math.min.apply(null, loc.filter(function (l) { return mouth.indexOf(l[0]) >= 0; }).map(function (l) { return l[2]; }));
        var nose = loc.filter(function (l) { return !used[l[0]] && l[2] >= 0.05 && l[2] <= mouthTop - 0.1 && Math.abs(l[1]) <= 0.3; }).map(function (l) { return l[0]; });
        var mv = mouth.map(function (k) { return mpos[k]; });
        var halfW = Math.max(0.5, Math.max.apply(null, mv.map(function (v) { return Math.abs(v[0]); }))) + 0.35;
        var top = -0.35, bottom = Math.max.apply(null, mv.map(function (v) { return v[1]; })) + 0.3, cy = (top + bottom) / 2, ry = (bottom - top) / 2;
        var clutter = loc.filter(function (l) { return !used[l[0]] && Math.pow(l[1] / halfW, 2) + Math.pow((l[2] - cy) / ry, 2) <= 1; }).length - Math.min(1, nose.length);
        if (clutter > 1) return;
        if (Object.keys(used).length + Math.min(1, nose.length) < 0.3 * n) return;
        var score = 1 - 0.15 * clutter - 0.6 * Math.abs(mouthAl);
        if (score >= 0.6 && (!best || score > best.score)) best = { score: score, eyes: [i, j], mouth: mouth, nose: nose.slice(0, 1), eyeIng: A.ing, mouthKind: kind };
      });
    }
    return best;
  }

  // ---- small pictures of the pizza with an analysis drawn on top
  var COLORS = { pep: '#a8281e', ham: '#e59a94', chk: '#e6cc9c', anc: '#5d3d2f', mus: '#d9c3a1', grp: '#3f8a2e', oni: '#93357a', oli: '#25231f', crn: '#f2c63a',
    pin: '#f3cf55', jal: '#6ea548', bas: '#2f7d32', shr: '#ef8a5f', egg: '#f6f1df', gor: '#d9d6c6', nor: '#1f2a1d', kim: '#d4542b', par: '#e8e2b8', ban: '#f5eab8', wal: '#9a6a3c', tom: '#d8432c' };
  function glyph(p, extra) {
    var c = capsule(p), col = COLORS[p.ing] || '#888';
    if (c[0][0] === c[1][0] && c[0][1] === c[1][1]) return '<circle cx="' + (c[0][0] * 100).toFixed(1) + '" cy="' + (-c[0][1] * 100).toFixed(1) + '" r="' + (c[2] * 100).toFixed(1) + '" fill="' + col + '"' + (extra || '') + '/>';
    return '<line x1="' + (c[0][0] * 100).toFixed(1) + '" y1="' + (-c[0][1] * 100).toFixed(1) + '" x2="' + (c[1][0] * 100).toFixed(1) + '" y2="' + (-c[1][1] * 100).toFixed(1) +
      '" stroke="' + col + '" stroke-width="' + (c[2] * 200).toFixed(1) + '" stroke-linecap="round"' + (extra || '') + '/>';
  }
  function pic(inner) { return '<svg viewBox="-112 -112 224 224" class="pv-pic" role="img"><circle r="100" fill="#dcae6c"/><circle r="86" fill="#f1e2bf"/>' + inner + '</svg>'; }
  function symPic(ps, sym) {
    if (!sym) return pic(ps.map(function (p) { return glyph(p); }).join(''));
    var ex = Math.cos(sym.axis) * 106, ey = -Math.sin(sym.axis) * 106, T = mirrorT(sym.axis), s = ps.map(function (p) { return glyph(p, ' opacity=".85"'); }).join('');
    s += '<line x1="' + (-ex).toFixed(1) + '" y1="' + (-ey).toFixed(1) + '" x2="' + ex.toFixed(1) + '" y2="' + ey.toFixed(1) + '" stroke="#2457a6" stroke-width="2" stroke-dasharray="6 4"/>';
    ps.forEach(function (p) {
      var t = T(p.x, p.y), d = Infinity;
      ps.forEach(function (q) { if (q.ing === p.ing) d = Math.min(d, Math.hypot(t[0] - q.x, t[1] - q.y)); });
      var col = d <= 0.06 ? '#2e8b57' : d <= 0.15 ? '#d08a00' : '#c23b22';
      s += '<circle cx="' + (t[0] * 100).toFixed(1) + '" cy="' + (-t[1] * 100).toFixed(1) + '" r="' + Math.max(capsule(p)[2] * 75, 3).toFixed(1) + '" fill="none" stroke="' + col + '" stroke-width="2.4"/>';
    });
    return pic(s);
  }
  function borderPic(ps, b) {
    var col = { inside: '#9a9a9a', crust: '#d08a00', over: '#c23b22' };
    return pic('<circle r="86" fill="none" stroke="#b07a2c" stroke-width="1.2" stroke-dasharray="3 3"/>' +
      ps.map(function (p, i) { var z = b.zones[i].zone; return glyph(p, ' opacity="' + (z === 'inside' ? '.35' : '1') + '"') +
        (z === 'inside' ? '' : '<circle cx="' + (p.x * 100).toFixed(1) + '" cy="' + (-p.y * 100).toFixed(1) + '" r="' + (capsule(p)[2] * 100 + 3).toFixed(1) + '" fill="none" stroke="' + col[z] + '" stroke-width="2.4"/>'); }).join(''));
  }
  function facePic(ps, f) {
    if (!f) return pic(ps.map(function (p) { return glyph(p, ' opacity=".45"'); }).join(''));
    var on = {}; f.eyes.concat(f.mouth, f.nose).forEach(function (k) { on[k] = 1; });
    var s = ps.map(function (p, i) { return glyph(p, ' opacity="' + (on[i] ? '1' : '.3') + '"'); }).join('');
    function ring(k, col) { var p = ps[k]; return '<circle cx="' + (p.x * 100).toFixed(1) + '" cy="' + (-p.y * 100).toFixed(1) + '" r="' + (capsule(p)[2] * 100 + 4).toFixed(1) + '" fill="none" stroke="' + col + '" stroke-width="2.6"/>'; }
    f.eyes.forEach(function (k) { s += ring(k, '#2457a6'); });
    f.mouth.forEach(function (k) { s += ring(k, '#c23b22'); });
    f.nose.forEach(function (k) { s += ring(k, '#3f8f4a'); });
    return pic(s);
  }

  // Size matching, as in analyse.py: for each resized piece, is another piece of the same topping / same category /
  // other category within 10% of its size? The other-category share is the chance baseline.
  function sizeMatching(ps) {
    var tol = 0.1, resized = ps.filter(function (p) { return Math.abs(p.g - 1) > tol; }), same = [], cat = [], other = [];
    function hit(p, pool) { return pool.some(function (q) { return Math.abs(p.g - q.g) <= tol * Math.max(p.g, q.g); }); }
    resized.forEach(function (p) {
      var sp = ps.filter(function (q) { return q !== p && q.ing === p.ing; });
      var cp = ps.filter(function (q) { return q.ing !== p.ing && CATS[q.ing] === CATS[p.ing]; });
      var op = ps.filter(function (q) { return CATS[q.ing] !== CATS[p.ing]; });
      if (sp.length) same.push(hit(p, sp)); if (cp.length) cat.push(hit(p, cp)); if (op.length) other.push(hit(p, op));
    });
    function share(v) { return v.length ? v.filter(Boolean).length / v.length : null; }
    return { n: resized.length, same: share(same), cat: share(cat), other: share(other) };
  }

  function coverage(ps) {
    var caps = ps.map(capsule), hit = 0, tot = 0, G = 40;
    for (var i = 0; i < G; i++) for (var j = 0; j < G; j++) {
      var x = -0.86 + 1.72 * (i + 0.5) / G, y = -0.86 + 1.72 * (j + 0.5) / G;
      if (x * x + y * y > 0.7396) continue;
      tot++;
      if (caps.some(function (c) { return pointSeg([x, y], c[0], c[1]) <= c[2]; })) hit++;
    }
    return tot ? hit / tot : 0;
  }
  function areaCm2(p) { var f = FOOT[p.ing] || [0, 8]; return (Math.PI * f[1] * f[1] + 4 * f[0] * f[1]) * p.s * p.s * 0.0225; }

  function dietClass(ps, summ) {
    var k = {}; ps.forEach(function (p) { k[DIET[p.ing] || 'vegan'] = 1; });
    if (k.meat) return 'meat';
    if (k.seafood) return 'pescatarian';
    if (k.vegetarian || (summ.cheese && summ.cheese !== 'none') || summ.sauce === 'white') return 'vegetarian';
    return 'vegan';
  }
  // Same as analyse.py: 'which toppings' (surprise in bits, as a percentile of the reference) and 'how many'
  // (two-sided extremeness of the number of different toppings); the band uses the more extreme of the two.
  function normality(set, tray) {
    var bits = 0, parts = [], size = Object.keys(set).length;
    tray.forEach(function (k) {
      if (REF.counts[k] == null) return;
      var rate = (REF.counts[k] + 0.5) / (REF.n + 1), inc = !!set[k], b = -Math.log2(inc ? rate : 1 - rate);
      bits += b; parts.push([b, k, inc, rate]);
    });
    var below = 0; REF.scores.forEach(function (x) { below += x < bits ? 1 : x === bits ? 0.5 : 0; });
    var comp = 100 * below / REF.scores.length;
    var le = 0, ge = 0, same = 0;
    REF.sizes.forEach(function (x) { if (x <= size) le++; if (x >= size) ge++; if (x === size) same++; });
    var cnt = 100 * (1 - Math.min(1, 2 * Math.min((le + 0.5) / (REF.n + 1), (ge + 0.5) / (REF.n + 1))));
    var pct = Math.max(comp, cnt);
    parts.sort(function (a, b) { return b[0] - a[0]; });
    var why = [];
    if (cnt >= 75) why.push((size === 0 ? 'no toppings' : size === 1 ? '1 topping' : size + ' different toppings') + ' (like ' + Math.round(100 * same / REF.n) + '% of pizzas)');
    parts.forEach(function (p) { if (p[0] >= 2) why.push((p[2] ? 'added ' : 'left off ') + esc((NAMES[p[1]] || p[1]).toLowerCase()) + ' (on ' + Math.round(p[3] * 100) + '%)'); });
    return { bits: bits, comp: comp, cnt: cnt, pct: pct, band: pct < 75 ? 'typical' : pct < 95 ? 'uncommon' : 'unusual', why: why.slice(0, 3).join('; ') };
  }

  function stat(label, value, note) {
    return '<div class="pv-stat"><span>' + esc(label) + '</span><b>' + value + '</b>' + (note ? '<small>' + note + '</small>' : '') + '</div>';
  }

  var CSS = '.pv{display:flex;flex-direction:column;gap:12px;margin:6px 0 12px}' +
    '.pv-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}' +
    '.pv-group{border:1px solid var(--line,#ddd);border-radius:12px;padding:10px 12px;background:var(--panel,#fff);min-width:0}' +
    '.pv-group h4{margin:0 0 6px;font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted,#666)}' +
    '.pv-stat{display:grid;grid-template-columns:1fr auto;gap:0 10px;padding:3px 0;border-bottom:1px dashed var(--line,#ddd)}' +
    '.pv-stat:last-child{border-bottom:0}.pv-stat span{color:var(--muted,#666);font-size:.88rem}.pv-stat b{font-variant-numeric:tabular-nums;text-align:right}' +
    '.pv-stat small{grid-column:1/-1;color:var(--muted,#666);font-size:.78rem}' +
    '.pv-chips{display:flex;flex-wrap:wrap;gap:6px}.pv-chip{display:inline-block;padding:2px 9px;border-radius:999px;color:#fff;font-size:.82rem;white-space:nowrap}' +
    '.pv-vegan{background:#3f8f4a}.pv-vegetarian{background:#b8890f}.pv-pescatarian,.pv-seafood{background:#2f78b5}.pv-meat{background:#b8432a}' +
    '.pv-typical{background:#2e8b57}.pv-uncommon{background:#c27f00}.pv-unusual{background:#c23b22}.pv-empty{color:var(--muted,#666)}' +
    '.pv-note{font-size:.8rem;color:var(--muted,#666);margin:0}' +
    '.pv-pics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}' +
    '.pv-pics figure{margin:0;border:1px solid var(--line,#ddd);border-radius:12px;padding:8px;background:var(--panel,#fff);min-width:0}' +
    '.pv-pics figcaption{font-weight:600;font-size:.9rem;margin-bottom:4px}.pv-pic{width:100%;max-width:220px;height:auto;display:block;margin:0 auto}' +
    '.pv-key{display:flex;flex-wrap:wrap;gap:4px 10px;font-size:.75rem;color:var(--muted,#666);margin-top:4px}' +
    '.pv-key i{display:inline-block;width:10px;height:10px;border-radius:50%;border:2.4px solid;margin-right:4px;vertical-align:-1px}';

  function render(el, f) {
    if (!document.getElementById('pv-style')) { var st = document.createElement('style'); st.id = 'pv-style'; st.textContent = CSS; document.head.appendChild(st); }
    var fin = J(f.pz_final, null);
    if (!fin) { el.innerHTML = '<p class="pv-empty">The preview appears once the pizza page has been used.</p>'; return; }
    var summ = J(f.pz_summary, {}), ev = J(f.pz_events, []), prac = J(f.pzp_summary, null), fol = J(f.pzf_data, null);
    var ps = fin.map(function (a) { var g = a.length > 8 ? a[8] : 1; return { ing: a[1], x: a[2], y: a[3], rot: a[4], s: a[5] * g, g: g }; });
    var counts = {}; ps.forEach(function (p) { counts[p.ing] = (counts[p.ing] || 0) + 1; });
    var set = {}; Object.keys(counts).forEach(function (k) { set[k] = 1; });
    var tray = summ.tray || Object.keys(REF.counts);
    var cls = dietClass(ps, summ), nrm = normality(set, tray), con = contacts(ps), sym = symmetry(ps), bor = border(ps), face = faceDetect(ps);
    var unusual = Object.keys(counts).filter(function (k) { return TIER[k] === 'unusual'; }).length;
    var adds = ev.filter(function (e) { return e[1] === 'add'; }), firstPick = (ev.filter(function (e) { return e[1] === 'pick'; })[0] || [])[0];
    var decisions = [], last = null;
    ev.forEach(function (e) {
      if (e[1] === 'pick' && last != null) decisions.push(e[0] - last);
      if (['add', 'reject', 'move', 'remove', 'tap', 'resize', 'undo', 'sauce', 'cheese'].indexOf(e[1]) >= 0) last = e[0];
    });
    var fin_t = (ev.filter(function (e) { return e[1] === 'finish'; })[0] || [])[0];
    var dones = ev.filter(function (e) { return e[1] === 'done'; }), doneT = dones.length ? dones[0][0] : null;
    var area = ps.reduce(function (a, p) { return a + areaCm2(p); }, 0);
    var grown = ps.filter(function (p) { return p.g > 1.01; }).length, shrunk = ps.filter(function (p) { return p.g < 0.99; }).length;
    var sm = sizeMatching(ps), pc = function (v) { return v == null ? '-' : Math.round(v * 100) + '%'; };
    var chips = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).map(function (k) {
      return '<span class="pv-chip pv-' + (DIET[k] || 'vegan') + '">' + esc(NAMES[k] || k) + ' ×' + counts[k] + '</span>';
    }).join('') || '<span class="pv-empty">No toppings (plain pizza)</span>';
    var why = nrm.why;
    var html = '<div class="pv">' +
      '<div class="pv-chips"><span class="pv-chip pv-' + cls + '">' + CLASS_LABEL[cls] + '</span>' +
      '<span class="pv-chip pv-' + nrm.band + '">' + nrm.band + ' · ' + Math.round(nrm.pct) + 'th percentile</span>' +
      (summ.finished ? '' : '<span class="pv-chip" style="background:#6e635b">still building</span>') + '</div>' +
      '<div class="pv-chips">' + chips + '</div>' +
      '<div class="pv-pics">' +
      '<figure><figcaption>Symmetry</figcaption>' + symPic(ps, sym) +
        '<div class="pv-key"><span><i style="border-color:#2e8b57"></i>mirror partner there</span><span><i style="border-color:#d08a00"></i>close</span><span><i style="border-color:#c23b22"></i>missing</span></div></figure>' +
      '<figure><figcaption>Border</figcaption>' + borderPic(ps, bor) +
        '<div class="pv-key"><span><i style="border-color:#d08a00"></i>on the crust</span><span><i style="border-color:#c23b22"></i>over the edge</span><span>faded = inside</span></div></figure>' +
      '<figure><figcaption>Face</figcaption>' + facePic(ps, face) +
        '<div class="pv-key">' + (face ? '<span><i style="border-color:#2457a6"></i>eyes</span><span><i style="border-color:#c23b22"></i>mouth</span>' + (face.nose.length ? '<span><i style="border-color:#3f8f4a"></i>nose</span>' : '') : '<span>no face found</span>') + '</div></figure>' +
      '</div>' +
      '<div class="pv-groups">' +
      '<div class="pv-group"><h4>Composition</h4>' + stat('Pieces', ps.length) + stat('Different toppings', Object.keys(counts).length) +
        stat('Unusual toppings', unusual) + stat('Sauce / cheese', esc((summ.sauce || '-') + ' / ' + (summ.cheese || '-'))) + '</div>' +
      '<div class="pv-group"><h4>Normality</h4>' + stat('Which toppings', Math.round(nrm.comp) + 'th %ile', nrm.bits.toFixed(1) + ' bits of surprise') +
        stat('How many', Math.round(nrm.cnt) + 'th %ile', why || 'only common choices') +
        '<p class="pv-note">Against a SIMULATED reference of ' + REF.n + ' pizzas. In the study this comes from your pilot or the sample.</p></div>' +
      '<div class="pv-group"><h4>Symmetry</h4>' + stat('Mirror', sym ? sym.mirror.toFixed(2) + ' × random' : '-', '0 = perfectly symmetric, 1 = like a random layout') +
        stat('Mirror axis', sym ? Math.round(sym.axis * 180 / Math.PI) + '°' : '-') + stat('Rotation', sym ? sym.rot.toFixed(2) + ' × random' : '-', sym ? 'best: ' + sym.k + '-fold' : '') + '</div>' +
      '<div class="pv-group"><h4>Border</h4>' + stat('Inside the sauce', ps.length - bor.crust - bor.over) + stat('On the crust', bor.crust) + stat('Over the edge', bor.over) +
        stat('Furthest overhang', bor.over ? bor.overhangMm.toFixed(0) + ' mm' : '-', 'on a 30 cm pizza') + '</div>' +
      '<div class="pv-group"><h4>Face</h4>' + stat('Face found', face ? 'yes' : 'no') +
        (face ? stat('Eyes', esc(NAMES[face.eyeIng] || face.eyeIng)) + stat('Mouth', esc(face.mouthKind)) + stat('Nose', face.nose.length ? 'yes' : 'no') + stat('Score', face.score.toFixed(2)) : '') + '</div>' +
      '<div class="pv-group"><h4>Space</h4>' +
        stat('Touching pairs', con.touch) + stat('Stacked pairs', con.stack) + stat('Tallest pile', con.pile ? con.pile + ' layer' + (con.pile > 1 ? 's' : '') : '-') +
        stat('Pizza covered', Math.round(coverage(ps) * 100) + '%') + '</div>' +
      '<div class="pv-group"><h4>Size</h4>' + stat('Topping area', area.toFixed(0) + ' cm²', 'on a 30 cm pizza') + stat('Made bigger', grown) + stat('Made smaller', shrunk) +
        stat('Sized like the same topping', pc(sm.same), sm.n ? 'of ' + sm.n + ' resized piece' + (sm.n > 1 ? 's' : '') + '; same category ' + pc(sm.cat) + ', other categories ' + pc(sm.other) + ' (chance)' : 'nothing resized yet') +
        stat('Size range', ps.length ? Math.min.apply(null, ps.map(function (p) { return p.g; })).toFixed(2) + '–' + Math.max.apply(null, ps.map(function (p) { return p.g; })).toFixed(2) : '-') + '</div>' +
      '<div class="pv-group"><h4>Time</h4>' + stat('First topping', sec(firstPick)) + stat('Median decision', sec(median(decisions)), 'end of one action to picking up the next topping') +
        stat('Placements', adds.length) + stat('Pressed "I\'m done"', sec(doneT), dones.length > 1 ? 'pressed ' + dones.length + ' times, went back to edit ' + (dones.length - 1) + '\u00d7' : '') +
        stat('Time to completion', sec(fin_t), 'confirmed and submitted') + (prac ? stat('Practice drag (motor baseline)', sec(prac.dragMsMedian)) : '') + '</div>' +
      (fol && fol.style === 'strong' ? '<div class="pv-group"><h4>Strong feelings</h4>' +
        (fol.none ? stat('Ingredients', 'none') : (fol.strong || []).map(function (k) {
          var it = (fol.items || {})[k] || {};
          return stat(NAMES[k] || k, esc(({ love: 'loves', like: 'likes', mixed: 'mixed', dislike: 'dislikes', cant: "can't stand" })[it.feel] || '...'),
            [(it.about || []).join(', '), it.safe === 'yes' ? 'safe food' : '', it.sameway === 'yes' ? 'must be a certain way' : '', it.crave === 'often' ? 'craves it' : '']
              .filter(Boolean).map(esc).join(' \u00b7 '));
        }).join('') || stat('Ingredients', 'not answered yet')) + '</div>' : '') +
      (fol && fol.style !== 'strong' ? '<div class="pv-group"><h4>Follow-up</h4>' + stat('Stated diet', esc((fol.diet || []).join(', ') || '-')) + stat('Food health', esc((fol.health || []).join(', ') || '-')) +
        stat('"Expresses who I am"', fol.pizza && fol.pizza.express != null ? fol.pizza.express + ' / 7' : '-') +
        stat('"Followed a rule or system"', fol.pizza && fol.pizza.system != null ? fol.pizza.system + ' / 7' : '-') +
        stat('Toppings rated', Object.keys(fol.items || {}).length) + '</div>' : '') +
      '</div></div>';
    el.innerHTML = html;
  }

  global.PizzaPreview = { render: render, reference: REF };
})(typeof window !== 'undefined' ? window : this);
