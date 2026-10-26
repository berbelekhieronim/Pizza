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
  var REF = {"n": 200, "counts": {"pep": 110, "ham": 53, "chk": 47, "tun": 29, "anc": 13, "mus": 102, "grp": 63, "oni": 82, "oli": 71, "crn": 43, "pin": 41, "jal": 40, "bas": 49, "shr": 11, "egg": 10, "gor": 20, "nor": 5, "kim": 6, "kan": 6, "fig": 12}, "sizes": [5, 6, 1, 7, 6, 4, 2, 4, 2, 2, 3, 2, 4, 7, 4, 3, 4, 5, 3, 4, 4, 6, 5, 1, 5, 3, 3, 4, 6, 4, 5, 8, 6, 2, 4, 2, 3, 5, 2, 3, 4, 3, 3, 3, 1, 6, 3, 6, 7, 5, 3, 0, 6, 4, 5, 3, 3, 6, 4, 5, 2, 3, 4, 2, 6, 4, 3, 1, 3, 2, 4, 1, 3, 4, 2, 6, 3, 5, 3, 7, 6, 5, 3, 4, 7, 4, 4, 4, 6, 5, 5, 2, 1, 2, 3, 3, 1, 4, 3, 7, 2, 5, 7, 6, 4, 2, 6, 7, 3, 3, 3, 1, 1, 4, 7, 5, 5, 5, 3, 7, 4, 4, 2, 7, 4, 1, 8, 2, 6, 2, 4, 5, 4, 5, 4, 7, 7, 4, 8, 4, 3, 4, 3, 8, 4, 6, 7, 5, 3, 4, 5, 6, 3, 2, 7, 4, 4, 5, 3, 2, 5, 8, 4, 5, 3, 4, 5, 7, 6, 1, 10, 6, 3, 5, 4, 5, 1, 2, 3, 3, 5, 5, 2, 3, 1, 3, 1, 2, 2, 2, 5, 5, 4, 3, 3, 5, 3, 5, 6, 6], "scores": [7.008, 7.008, 7.008, 7.008, 7.241, 7.241, 7.241, 7.299, 7.477, 7.768, 7.826, 8.107, 8.107, 8.165, 8.165, 8.343, 8.343, 8.368, 8.426, 8.43, 8.43, 8.583, 8.634, 8.634, 8.663, 8.721, 8.83, 8.874, 8.888, 8.888, 8.918, 8.932, 8.963, 9.016, 9.111, 9.169, 9.179, 9.209, 9.209, 9.249, 9.312, 9.402, 9.449, 9.46, 9.491, 9.529, 9.645, 9.707, 9.71, 9.737, 9.819, 9.848, 9.848, 9.882, 9.987, 10.015, 10.057, 10.059, 10.081, 10.103, 10.103, 10.133, 10.144, 10.178, 10.268, 10.268, 10.282, 10.296, 10.355, 10.376, 10.407, 10.457, 10.543, 10.573, 10.573, 10.61, 10.656, 10.745, 10.776, 10.867, 10.967, 10.988, 11.029, 11.03, 11.14, 11.217, 11.222, 11.243, 11.247, 11.247, 11.273, 11.301, 11.326, 11.33, 11.367, 11.395, 11.474, 11.496, 11.498, 11.526, 11.679, 11.796, 11.854, 11.877, 11.935, 12.027, 12.135, 12.177, 12.192, 12.265, 12.32, 12.323, 12.363, 12.393, 12.423, 12.425, 12.457, 12.478, 12.61, 12.62, 12.759, 12.87, 12.89, 12.906, 12.948, 12.983, 13.004, 13.171, 13.173, 13.268, 13.276, 13.373, 13.636, 13.637, 13.778, 13.811, 13.875, 13.933, 14.076, 14.079, 14.15, 14.15, 14.159, 14.274, 14.298, 14.382, 14.396, 14.496, 14.535, 14.628, 14.629, 14.762, 14.823, 14.91, 14.975, 15.015, 15.041, 15.091, 15.175, 15.177, 15.186, 15.215, 15.254, 15.318, 15.394, 15.462, 15.52, 15.586, 15.692, 15.72, 15.847, 16.181, 16.301, 16.594, 16.726, 16.73, 16.909, 16.933, 17.039, 17.378, 17.47, 17.53, 17.635, 17.9, 18.093, 18.438, 18.629, 18.778, 18.924, 19.114, 19.583, 19.611, 19.742, 21.187, 21.668, 21.756, 22.357, 22.783, 24.348, 31.316]};
  REF.simulated = true;

  var NAMES = { pep: 'Pepperoni', ham: 'Ham', chk: 'Chicken', anc: 'Anchovies', mus: 'Mushrooms', grp: 'Green pepper', oni: 'Red onion',
    oli: 'Black olives', crn: 'Sweetcorn', pin: 'Pineapple', jal: 'Jalapeños', bas: 'Basil', shr: 'Shrimp', egg: 'Egg', gor: 'Blue cheese',
    nor: 'Nori', kim: 'Kimchi', par: 'Pear', ban: 'Banana', wal: 'Walnuts', tom: 'Tomato slice', tun: 'Tuna', kan: 'Kangaroo', fig: 'Fig' };
  var DIET = { pep: 'meat', ham: 'meat', chk: 'meat', kan: 'meat', anc: 'seafood', shr: 'seafood', tun: 'seafood', egg: 'vegetarian', gor: 'vegetarian' };
  var TIER = { anc: 'mid', pin: 'mid', shr: 'mid', egg: 'mid', gor: 'mid', nor: 'unusual', kim: 'unusual', par: 'unusual', ban: 'unusual', wal: 'unusual', kan: 'unusual', fig: 'unusual' };
  var FOOT = { pep: [0, 13], ham: [1, 6.4], chk: [1.5, 6.5], anc: [12, 2.8], mus: [0, 11], grp: [11, 3], oni: [10, 2], oli: [0, 6.1], crn: [0, 4.7],
    pin: [0, 6.5], jal: [0, 5.6], bas: [9.5, 5], shr: [0, 8], egg: [1, 7.2], gor: [0, 5], nor: [1.5, 6.3], kim: [2, 5.8], par: [8, 4], ban: [0, 6.2],
    wal: [0.6, 5.8], tom: [0, 10], tun: [1, 6], kan: [7, 4.2], fig: [0, 9] };
  var SIZE = { pep: 13, ham: 10, chk: 8.5, anc: 15, mus: 12, grp: 13.5, oni: 12.5, oli: 6.2, crn: 6, pin: 8.6, jal: 6, bas: 12, shr: 9.5, egg: 8.5, gor: 6.5,
    nor: 9.5, kim: 9, par: 12, ban: 6.5, wal: 7, tom: 10, tun: 8, kan: 11, fig: 10 };
  var CATS = { pep: 'meat', ham: 'meat', chk: 'meat', anc: 'seafood', shr: 'seafood', mus: 'veg', grp: 'veg', oni: 'veg', oli: 'veg', crn: 'veg',
    jal: 'veg', kim: 'veg', pin: 'fruit', par: 'fruit', ban: 'fruit', bas: 'herb', egg: 'egg', gor: 'dairy', nor: 'seaweed', wal: 'nut', tun: 'seafood', kan: 'meat', fig: 'fruit' };
  var CLASS_LABEL = { vegan: 'Vegan', vegetarian: 'Vegetarian', pescatarian: 'Pescatarian', meat: 'Contains meat' };

  function J(v, d) { try { return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function median(a) { if (!a.length) return null; a = a.slice().sort(function (x, y) { return x - y; }); var m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; }
  var ABOUT_NAMES = { autistic: 'Autistic', adhd: 'ADHD', dys: 'Dyslexic / dyspraxic / dyscalculic', otherND: 'Other neurodivergent', none: 'None of these',
    pnts: 'Prefer not to say', formal: 'formally diagnosed', self: 'self-identified', waiting: 'waiting for assessment', picky: 'Picky since childhood',
    arfid: 'ARFID', ed: 'Eating disorder', allergy: 'Allergy or intolerance' };
  function fmedian(a) { a = a.filter(function (x) { return x != null; }).sort(function (x, y) { return x - y; }); if (!a.length) return null; var m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; }
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
  // Symmetry: the same rules, in the same order, as sym_match / best_mirror / best_rotation / symmetry() in analyse.py.
  // A piece is matched when its mirror (or rotated) image lands on a piece of the same topping, within half the sum of
  // the two pieces' radii; one-to-one, closest pairs first. Chance comes from 12 random layouts of the same pieces.
  function pieceRad(p) { return (SIZE[p.ing] || 8) * p.s / 100; }
  function symMatch(ps, T) {
    var groups = {}, cand = [];
    ps.forEach(function (p, i) { (groups[p.ing] = groups[p.ing] || []).push([i, p.x, p.y, pieceRad(p)]); });
    Object.keys(groups).forEach(function (k) {
      var g = groups[k];
      g.forEach(function (a) {
        var t = T(a[1], a[2]);
        g.forEach(function (b) {
          var d = Math.sqrt((t[0] - b[1]) * (t[0] - b[1]) + (t[1] - b[2]) * (t[1] - b[2]));
          if (d <= 0.5 * (a[3] + b[3])) cand.push([d, a[0], b[0]]);
        });
      });
    });
    cand.sort(function (u, v) { return u[0] - v[0] || u[1] - v[1] || u[2] - v[2]; });
    var src = {}, dst = {}, pairs = [];
    cand.forEach(function (c) { if (!src[c[1]] && !dst[c[2]]) { src[c[1]] = dst[c[2]] = true; pairs.push(c); } });
    return pairs;
  }
  function mirrorAbout(cx, cy, phi) { var c = Math.cos(2 * phi), s = Math.sin(2 * phi); return function (x, y) { return [cx + c * (x - cx) + s * (y - cy), cy + s * (x - cx) - c * (y - cy)]; }; }
  function rotateAbout(cx, cy, a) { var c = Math.cos(a), s = Math.sin(a); return function (x, y) { return [cx + c * (x - cx) - s * (y - cy), cy + s * (x - cx) + c * (y - cy)]; }; }
  function symCentres(ps) {
    var cx = 0, cy = 0; ps.forEach(function (p) { cx += p.x; cy += p.y; }); cx /= ps.length; cy /= ps.length;
    return [[0, 0]].concat(Math.sqrt(cx * cx + cy * cy) > 0.02 ? [[cx, cy]] : []);
  }
  function bestMirror(ps) {
    function score(c, deg) { var pr = symMatch(ps, mirrorAbout(c[0], c[1], deg * Math.PI / 180)), sd = 0; pr.forEach(function (q) { sd += q[0]; }); return [pr.length, Math.round(sd * 1e6) / 1e6, deg, c]; }
    function better(a, b) { return a[0] > b[0] || (a[0] === b[0] && a[1] < b[1]); }
    var coarse = [];
    symCentres(ps).forEach(function (c) { for (var a = 0; a < 180; a += 3) coarse.push(score(c, a)); });
    var top = coarse.slice().sort(function (u, v) { return v[0] - u[0] || u[1] - v[1]; }).slice(0, 3), best = null;
    top.forEach(function (t) { for (var k = -6; k <= 6; k++) { var cand = score(t[3], (((t[2] + 0.25 * k) % 180) + 180) % 180); if (!best || better(cand, best)) best = cand; } });
    return { m: best[0], axis: best[2], c: best[3] };
  }
  function bestRotation(ps) {
    var best = null;
    symCentres(ps).forEach(function (c) {
      for (var k = 2; k <= 8; k++) { var m = symMatch(ps, rotateAbout(c[0], c[1], 2 * Math.PI / k)).length; if (!best || m > best.m || (m === best.m && k > best.k)) best = { m: m, k: k, c: c }; }
    });
    return best;
  }
  function randomLike(ps, rnd) { return ps.map(function (p) { var r = 0.9 * Math.sqrt(rnd()), t = rnd() * 2 * Math.PI; return { ing: p.ing, s: p.s, x: r * Math.cos(t), y: r * Math.sin(t) }; }); }
  function symScore(share, ch) { return share >= ch ? (ch < 1 ? (share - ch) / (1 - ch) : 0) : (share - ch) / ch; }
  function symmetry(ps) {
    if (ps.length < 2) return null;
    var seed = 7, rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }, n = ps.length;
    var mi = bestMirror(ps), ro = bestRotation(ps), m0 = 0, r0 = 0;
    for (var i = 0; i < 12; i++) { var f = randomLike(ps, rnd); m0 += bestMirror(f).m / n / 12; r0 += bestRotation(f).m / n / 12; }
    return { match: mi.m / n, matched: mi.m, axis: mi.axis, c: mi.c, chance: m0, score: symScore(mi.m / n, m0),
      rotMatch: ro.m / n, rotMatched: ro.m, k: ro.k, rc: ro.c, rotChance: r0, rotScore: symScore(ro.m / n, r0) };
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

  // Face detection: the same rules, in the same order, as face_features() and face_detect() in analyse.py
  // (see the description there); tests compare the two on hundreds of pizzas.
  function faceFeatures(ps) {
    var n = ps.length, caps = ps.map(capsule), parent = ps.map(function (_, i) { return i; });
    function find(x) { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; }
    for (var i = 0; i < n; i++) for (var j = i + 1; j < n; j++) {
      var gap = segDist(caps[i][0], caps[i][1], caps[j][0], caps[j][1]) - caps[i][2] - caps[j][2];
      if ((ps[i].ing === ps[j].ing && gap <= 0.01) || gap <= -0.5 * Math.min(caps[i][2], caps[j][2])) parent[find(i)] = find(j);
    }
    var groups = new Map();
    for (i = 0; i < n; i++) { var r = find(i); if (!groups.has(r)) groups.set(r, []); groups.get(r).push(i); }
    var feats = [];
    groups.forEach(function (members) {
      var areas = members.map(function (i) { var c = caps[i], h = Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]) / 2; return Math.PI * c[2] * c[2] + 4 * h * c[2]; });
      var A = areas.reduce(function (x, y) { return x + y; }, 0);
      var cx = 0, cy = 0; members.forEach(function (i, k) { cx += ps[i].x * areas[k]; cy += ps[i].y * areas[k]; }); cx /= A; cy /= A;
      var pts = []; members.forEach(function (i) { pts.push(caps[i][0], caps[i][1]); });
      var sxx = 0, syy = 0, sxy = 0; pts.forEach(function (q) { sxx += (q[0] - cx) * (q[0] - cx); syy += (q[1] - cy) * (q[1] - cy); sxy += (q[0] - cx) * (q[1] - cy); });
      var th = 0.5 * Math.atan2(2 * sxy, sxx - syy), ux = Math.cos(th), uy = Math.sin(th);
      var wbar = members.reduce(function (x, i) { return x + caps[i][2]; }, 0) / members.length;
      var along = pts.map(function (q) { return (q[0] - cx) * ux + (q[1] - cy) * uy; }), across = pts.map(function (q) { return -(q[0] - cx) * uy + (q[1] - cy) * ux; });
      var length = Math.max.apply(null, along) - Math.min.apply(null, along) + 2 * wbar, width = Math.max.apply(null, across) - Math.min.apply(null, across) + 2 * wbar;
      var cnt = {}, top = null; members.forEach(function (i) { cnt[ps[i].ing] = (cnt[ps[i].ing] || 0) + 1; if (top === null || cnt[ps[i].ing] > cnt[top]) top = ps[i].ing; });
      feats.push({ members: members, x: cx, y: cy, r: Math.sqrt(A / Math.PI), elong: length / Math.max(width, 1e-6), len: length, ux: ux, uy: uy, ing: top });
    });
    return feats;
  }

  function faceDetect(ps) {
    var n = ps.length;
    if (n < 3) return null;
    var F = faceFeatures(ps), m = F.length, best = null, cos35 = Math.cos(35 * Math.PI / 180);
    function halfLen(pc) { var c = capsule(ps[pc]); return Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]) / 2; }
    function eyeLike(f) {
      if (f.elong > 1.7) return false;
      var mem = f.members;
      if (mem.length === 1) return capsule(ps[mem[0]])[2] > 0 && halfLen(mem[0]) <= 0.03;
      if (mem.length > 6) return false;
      var ings = {}; mem.forEach(function (pc) { ings[ps[pc].ing] = 1; });
      if (Object.keys(ings).length === 1) return true;
      var host = mem.reduce(function (h, pc) { return capsule(ps[pc])[2] > capsule(ps[h])[2] ? pc : h; }, mem[0]), hw = capsule(ps[host])[2];
      return mem.every(function (pc) { return pc === host || Math.hypot(ps[pc].x - ps[host].x, ps[pc].y - ps[host].y) <= hw; });
    }
    var eyesOk = F.map(eyeLike);
    for (var i = 0; i < m; i++) for (var j = i + 1; j < m; j++) {
      var A = F[i], B = F[j];
      if (!(eyesOk[i] && eyesOk[j])) continue;
      if (Math.max(A.r, B.r) / Math.max(1e-6, Math.min(A.r, B.r)) > 1.6) continue;
      var same = A.ing === B.ing, dx = B.x - A.x, dy = B.y - A.y, d = Math.hypot(dx, dy);
      if (d < 0.25 || d > 1.3 || d < 1.1 * (A.r + B.r)) continue;
      var ux = dx / d, uy = dy / d, mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
      [1, -1].forEach(function (sgn) {
        var px = -uy * sgn, py = ux * sgn, loc = [], pos = {};
        for (var k = 0; k < m; k++) if (k !== i && k !== j) { var vx = F[k].x - mx, vy = F[k].y - my, l = [k, (vx * ux + vy * uy) / d, (vx * px + vy * py) / d]; loc.push(l); pos[k] = [l[1], l[2]]; }
        function mirroredPair(zone) {
          var found = null;
          loc.forEach(function (a) { loc.forEach(function (b) {
            if (a[0] < b[0] && F[a[0]].ing === F[b[0]].ing && a[1] * b[1] < 0 && Math.abs(a[1] + b[1]) <= 0.15 && Math.abs(a[2] - b[2]) <= 0.15 && zone(a[1], a[2]) && zone(b[1], b[2])) found = [a[0], b[0]];
          }); });
          return found || [];
        }
        var brows = mirroredPair(function (al, pp) { return pp >= -0.6 && pp <= -0.1 && Math.abs(Math.abs(al) - 0.5) <= 0.3; });
        var cheeks = mirroredPair(function (al, pp) { return pp >= 0.1 && pp <= 1.0 && Math.abs(al) >= 0.55 && Math.abs(al) <= 1.1; });
        var deco = {}; brows.concat(cheeks).forEach(function (k) { deco[k] = 1; });
        if (loc.some(function (l) { return brows.indexOf(l[0]) < 0 && (Math.hypot(l[1] + 0.5, l[2]) < 0.4 || Math.hypot(l[1] - 0.5, l[2]) < 0.4); })) return;
        var taken = {}; F[i].members.concat(F[j].members).forEach(function (pc) { taken[pc] = 1; });
        Object.keys(deco).forEach(function (k) { F[k].members.forEach(function (pc) { taken[pc] = 1; }); });
        var ploc = [], ppos = {};
        ps.forEach(function (p, pc) { if (!taken[pc]) { var vx = p.x - mx, vy = p.y - my, l = [pc, (vx * ux + vy * uy) / d, (vx * px + vy * py) / d]; ploc.push(l); ppos[pc] = [l[1], l[2]]; } });
        var mouth = null, mouthAl = 0, kind = '';
        ploc.some(function (l) {
          var c = capsule(ps[l[0]]), h = halfLen(l[0]);
          if (h >= 0.04 && l[2] >= 0.45 && l[2] <= 2.2 && Math.abs(l[1]) <= 0.35 && Math.abs(((c[1][0] - c[0][0]) * ux + (c[1][1] - c[0][1]) * uy) / (2 * h)) >= cos35 && 2 * (h + c[2]) >= 0.45 * d) {
            mouth = [l[0]]; mouthAl = l[1]; kind = NAMES[ps[l[0]].ing] || ps[l[0]].ing; return true;
          }
          return false;
        });
        if (!mouth) {
          var cand = ploc.filter(function (l) { return l[2] >= 0.45 && l[2] <= 2.2 && Math.abs(l[1]) <= 1.1; })
            .map(function (l) { return [l[1], l[2], l[0]]; }).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1] || a[2] - b[2]; });
          var cn = cand.length, len = cand.map(function () { return 1; }), prev = cand.map(function () { return -1; });
          for (var b2 = 0; b2 < cn; b2++) for (var a2 = 0; a2 < b2; a2++) {
            var gp = cand[b2][0] - cand[a2][0];
            if (gp > 0 && gp <= 0.8 && Math.abs(cand[b2][1] - cand[a2][1]) <= 0.3 && len[a2] + 1 > len[b2]) { len[b2] = len[a2] + 1; prev[b2] = a2; }
          }
          var order = cand.map(function (_, e) { return e; }).sort(function (x, y) { return len[y] - len[x] || x - y; });
          for (var e = 0; e < order.length && len[order[e]] >= 3; e++) {
            var chain = [], c = order[e];
            while (c !== -1) { chain.unshift(c); c = prev[c]; }
            var als = chain.map(function (c) { return cand[c][0]; }), pps = chain.map(function (c) { return cand[c][1]; });
            var gaps = als.slice(1).map(function (x, t) { return x - als[t]; });
            var even = pstdev(gaps) <= 0.35 * mean(gaps), smooth = Math.min(fitResid(als, pps, 'line'), fitResid(als, pps, 'smile')) <= 0.08;
            if (als[als.length - 1] - als[0] >= 0.6 && Math.abs(mean(als)) <= 0.25 && Math.abs(als[0] + als[als.length - 1]) <= 0.35 && even && smooth) {
              mouth = chain.map(function (c) { return cand[c][2]; }); mouthAl = mean(als);
              var kinds = []; mouth.forEach(function (pc) { var nm = (NAMES[ps[pc].ing] || ps[pc].ing).toLowerCase(); if (kinds.indexOf(nm) < 0) kinds.push(nm); });
              kind = 'row of ' + mouth.length + ' ' + kinds.join('/');
              break;
            }
          }
        }
        if (!mouth) return;
        if (mouth.length > 1) {
          var ms = mouth.map(function (pc) { return ppos[pc]; }).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
          var step = mean(ms.slice(1).map(function (v, t) { return v[0] - ms[t][0]; }));
          var gapEye = Infinity; ms.forEach(function (v) { [-0.5, 0.5].forEach(function (ex) { gapEye = Math.min(gapEye, Math.hypot(v[0] - ex, v[1])); }); });
          if (gapEye < Math.max(0.45, 1.3 * step)) return;
          var endL = mouth.reduce(function (a, b) { return ppos[b][0] < ppos[a][0] ? b : a; }), endR = mouth.reduce(function (a, b) { return ppos[b][0] > ppos[a][0] ? b : a; });
          var mIngs = {}; mouth.forEach(function (pc) { mIngs[ps[pc].ing] = 1; });
          var eyePcs = {}; F[i].members.concat(F[j].members).forEach(function (pc) { eyePcs[pc] = 1; });
          for (var q = 0; q < n; q++) {
            if (mIngs[ps[q].ing] && mouth.indexOf(q) < 0 && !eyePcs[q] &&
                [endL, endR].some(function (e2) { return Math.hypot(ps[q].x - ps[e2].x, ps[q].y - ps[e2].y) <= 1.5 * step * d; })) return;
          }
        }
        var mouthFeats = {}; for (k = 0; k < m; k++) if (F[k].members.some(function (pc) { return mouth.indexOf(pc) >= 0; })) mouthFeats[k] = 1;
        var mv = mouth.map(function (pc) { return ppos[pc]; });
        var alMax = Math.max.apply(null, mv.map(function (v) { return Math.abs(v[0]); }));
        var mouthTop = Math.min.apply(null, mv.map(function (v) { return v[1]; })), mouthBottom = Math.max.apply(null, mv.map(function (v) { return v[1]; }));
        var used = {}; Object.keys(mouthFeats).concat(Object.keys(deco)).forEach(function (k) { used[k] = 1; });
        var nose = loc.filter(function (l) { return !used[l[0]] && l[2] >= 0.05 && l[2] <= mouthTop - 0.1 && Math.abs(l[1]) <= 0.3 && F[l[0]].members.length <= 2 && F[l[0]].r <= 1.5 * Math.max(A.r, B.r); }).map(function (l) { return l[0]; });
        var halfW = Math.max(0.5, alMax) + 0.35, top = -0.35, bottom = mouthBottom + 0.3, cy = (top + bottom) / 2, ry = (bottom - top) / 2;
        var clutter = loc.filter(function (l) { return !used[l[0]] && Math.pow(l[1] / halfW, 2) + Math.pow((l[2] - cy) / ry, 2) <= 1; }).length - Math.min(1, nose.length);
        if (clutter > 1 || (!same && (clutter > 0 || (mouth.length === 1 && !nose.length)))) return;
        var faceFeats = [i, j].concat(Object.keys(mouthFeats).map(Number), nose.slice(0, 1), Object.keys(deco).map(Number));
        var facePieces = {}; faceFeats.forEach(function (f) { F[f].members.forEach(function (pc) { facePieces[pc] = 1; }); });
        var nFace = Object.keys(facePieces).length, fcx = mx + px * d * (mouthTop / 2), fcy = my + py * d * (mouthTop / 2);
        var near = ps.filter(function (p) { return Math.hypot(p.x - fcx, p.y - fcy) <= 1.4 * d; }).length;
        if (nFace < 0.3 * Math.max(near, 1) || nFace < 0.3 * n) return;
        var score = 1 - 0.15 * clutter - 0.6 * Math.abs(mouthAl) - (same ? 0 : 0.1);
        function pieceList(fs) { var out = []; fs.forEach(function (f) { out = out.concat(F[f].members); }); return out.sort(function (a, b) { return a - b; }); }
        if (score >= 0.6 && (!best || score > best.score)) {
          best = { score: score, eyes: pieceList([i]).concat(pieceList([j])), mouth: mouth.slice().sort(function (a, b) { return a - b; }), nose: pieceList(nose.slice(0, 1)),
            deco: pieceList(Object.keys(deco).map(Number).sort(function (a, b) { return a - b; })), clutter: clutter, brows: brows.length ? 1 : 0, cheeks: cheeks.length ? 1 : 0,
            eyeIng: same ? A.ing : A.ing + '+' + B.ing, mouthKind: kind };
        }
      });
    }
    return best;
  }

  // ---- small pictures of the pizza with an analysis drawn on top
  var COLORS = { pep: '#a8281e', ham: '#e59a94', chk: '#e6cc9c', anc: '#5d3d2f', mus: '#d9c3a1', grp: '#3f8a2e', oni: '#93357a', oli: '#25231f', crn: '#f2c63a',
    pin: '#f3cf55', jal: '#6ea548', bas: '#2f7d32', shr: '#ef8a5f', egg: '#f6f1df', gor: '#d9d6c6', nor: '#1f2a1d', kim: '#d4542b', par: '#e8e2b8', ban: '#f5eab8', wal: '#9a6a3c', tom: '#d8432c', tun: '#bf7a64', kan: '#7a2e24', fig: '#6b2f5c' };
  function glyph(p, extra) {
    var c = capsule(p), col = COLORS[p.ing] || '#888';
    if (c[0][0] === c[1][0] && c[0][1] === c[1][1]) return '<circle cx="' + (c[0][0] * 100).toFixed(1) + '" cy="' + (-c[0][1] * 100).toFixed(1) + '" r="' + (c[2] * 100).toFixed(1) + '" fill="' + col + '"' + (extra || '') + '/>';
    return '<line x1="' + (c[0][0] * 100).toFixed(1) + '" y1="' + (-c[0][1] * 100).toFixed(1) + '" x2="' + (c[1][0] * 100).toFixed(1) + '" y2="' + (-c[1][1] * 100).toFixed(1) +
      '" stroke="' + col + '" stroke-width="' + (c[2] * 200).toFixed(1) + '" stroke-linecap="round"' + (extra || '') + '/>';
  }
  function pic(inner) { return '<svg viewBox="-112 -112 224 224" class="pv-pic" role="img"><circle r="100" fill="#dcae6c"/><circle r="86" fill="#f1e2bf"/>' + inner + '</svg>'; }
  function symPic(ps, sym) {
    if (!sym) return pic(ps.map(function (p) { return glyph(p); }).join(''));
    var phi = sym.axis * Math.PI / 180, cx = sym.c[0] * 100, cy = -sym.c[1] * 100, ex = Math.cos(phi) * 150, ey = -Math.sin(phi) * 150;
    var T = mirrorAbout(sym.c[0], sym.c[1], phi), matched = {}, s = ps.map(function (p) { return glyph(p, ' opacity=".85"'); }).join('');
    symMatch(ps, T).forEach(function (q) { matched[q[1]] = true; });
    s += '<clipPath id="pv-cl"><circle r="104"/></clipPath><line clip-path="url(#pv-cl)" x1="' + (cx - ex).toFixed(1) + '" y1="' + (cy - ey).toFixed(1) + '" x2="' + (cx + ex).toFixed(1) + '" y2="' + (cy + ey).toFixed(1) + '" stroke="#2457a6" stroke-width="2" stroke-dasharray="6 4"/>';
    ps.forEach(function (p, i) {
      var t = T(p.x, p.y);
      s += '<circle cx="' + (t[0] * 100).toFixed(1) + '" cy="' + (-t[1] * 100).toFixed(1) + '" r="' + Math.max(capsule(p)[2] * 75, 3).toFixed(1) + '" fill="none" stroke="' + (matched[i] ? '#2e8b57' : '#c23b22') + '" stroke-width="2.4"/>';
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
    var on = {}; f.eyes.concat(f.mouth, f.nose, f.deco || []).forEach(function (k) { on[k] = 1; });
    var s = ps.map(function (p, i) { return glyph(p, ' opacity="' + (on[i] ? '1' : '.3') + '"'); }).join('');
    function ring(k, col) { var p = ps[k]; return '<circle cx="' + (p.x * 100).toFixed(1) + '" cy="' + (-p.y * 100).toFixed(1) + '" r="' + (capsule(p)[2] * 100 + 4).toFixed(1) + '" fill="none" stroke="' + col + '" stroke-width="2.6"/>'; }
    f.eyes.forEach(function (k) { s += ring(k, '#2457a6'); });
    f.mouth.forEach(function (k) { s += ring(k, '#c23b22'); });
    f.nose.forEach(function (k) { s += ring(k, '#3f8f4a'); });
    (f.deco || []).forEach(function (k) { s += ring(k, '#8a4fa8'); });
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
    var mvs = ev.filter(function (e) { return e[9] && e[9].length >= 7; }).map(function (e) { return e[9]; }), ab = fol && fol.about && fol.about.neuro ? fol.about : null;
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
        '<div class="pv-key">' + (face ? '<span><i style="border-color:#2457a6"></i>eyes</span><span><i style="border-color:#c23b22"></i>mouth</span>' + (face.nose.length ? '<span><i style="border-color:#3f8f4a"></i>nose</span>' : '') + ((face.deco || []).length ? '<span><i style="border-color:#8a4fa8"></i>' + (face.brows && face.cheeks ? 'eyebrows, cheeks' : face.brows ? 'eyebrows' : 'cheeks') + '</span>' : '') : '<span>no face found</span>') + '</div></figure>' +
      '</div>' +
      '<div class="pv-groups">' +
      '<div class="pv-group"><h4>Composition</h4>' + stat('Pieces', ps.length) + stat('Different toppings', Object.keys(counts).length) +
        stat('Unusual toppings', unusual) + stat('Sauce / cheese', esc((summ.sauce || '-') + ' / ' + (summ.cheese || '-'))) + '</div>' +
      '<div class="pv-group"><h4>Normality</h4>' + stat('Which toppings', Math.round(nrm.comp) + 'th %ile', nrm.bits.toFixed(1) + ' bits of surprise') +
        stat('How many', Math.round(nrm.cnt) + 'th %ile', why || 'only common choices') +
        '<p class="pv-note">Against a SIMULATED reference of ' + REF.n + ' pizzas. In the study this comes from your pilot or the sample.</p></div>' +
      '<div class="pv-group"><h4>Symmetry</h4>' + stat('Mirror', sym ? sym.matched + ' of ' + ps.length + ' pieces matched (' + Math.round(100 * sym.match) + '%)' : '-',
          sym ? 'chance ' + Math.round(100 * sym.chance) + '% · score ' + sym.score.toFixed(2) + ' (0 = chance, 1 = all matched) · axis ' + sym.axis.toFixed(1) + '°' : '') +
        stat('Rotation', sym ? sym.k + '-fold: ' + sym.rotMatched + ' of ' + ps.length + ' matched (' + Math.round(100 * sym.rotMatch) + '%)' : '-',
          sym ? 'chance ' + Math.round(100 * sym.rotChance) + '% · score ' + sym.rotScore.toFixed(2) : '') + '</div>' +
      '<div class="pv-group"><h4>Border</h4>' + stat('Inside the sauce', ps.length - bor.crust - bor.over) + stat('On the crust', bor.crust) + stat('Over the edge', bor.over) +
        stat('Furthest overhang', bor.over ? bor.overhangMm.toFixed(0) + ' mm' : '-', 'on a 30 cm pizza') + '</div>' +
      '<div class="pv-group"><h4>Face</h4>' + stat('Face found', face ? 'yes' : 'no') +
        (face ? stat('Eyes', esc(face.eyeIng.split('+').map(function (k) { return NAMES[k] || k; }).join(' + '))) + stat('Mouth', esc(face.mouthKind)) + stat('Nose', face.nose.length ? 'yes' : 'no') + stat('Score', face.score.toFixed(2)) : '') + '</div>' +
      '<div class="pv-group"><h4>Space</h4>' +
        stat('Touching pairs', con.touch) + stat('Stacked pairs', con.stack) + stat('Tallest pile', con.pile ? con.pile + ' layer' + (con.pile > 1 ? 's' : '') : '-') +
        stat('Pizza covered', Math.round(coverage(ps) * 100) + '%') + '</div>' +
      '<div class="pv-group"><h4>Size</h4>' + stat('Topping area', area.toFixed(0) + ' cm²', 'on a 30 cm pizza') + stat('Made bigger', grown) + stat('Made smaller', shrunk) +
        stat('Sized like the same topping', pc(sm.same), sm.n ? 'of ' + sm.n + ' resized piece' + (sm.n > 1 ? 's' : '') + '; same category ' + pc(sm.cat) + ', other categories ' + pc(sm.other) + ' (chance)' : 'nothing resized yet') +
        stat('Size range', ps.length ? Math.min.apply(null, ps.map(function (p) { return p.g; })).toFixed(2) + '–' + Math.max.apply(null, ps.map(function (p) { return p.g; })).toFixed(2) : '-') + '</div>' +
      '<div class="pv-group"><h4>Time</h4>' + stat('First topping', sec(firstPick)) + stat('Median decision', sec(median(decisions)), 'end of one action to picking up the next topping') +
        stat('Placements', adds.length) + stat('Pressed "I\'m done"', sec(doneT), dones.length > 1 ? 'pressed ' + dones.length + ' times, went back to edit ' + (dones.length - 1) + '\u00d7' : '') +
        stat('Time to completion', sec(fin_t), 'confirmed and submitted') + (prac ? stat('Practice drag (motor baseline)', sec(prac.dragMsMedian)) : '') + '</div>' +
      (mvs.length ? '<div class="pv-group"><h4>Movement</h4>' + stat('Direct drags', (function (v) { return v == null ? '-' : v.toFixed(2); })(fmedian(mvs.map(function (m) { return m[1]; }))), 'straight-line distance / path; 1 = straight') +
        stat('Pauses per drag', (mvs.reduce(function (a, m) { return a + m[2]; }, 0) / mvs.length).toFixed(2), Math.round(100 * mvs.filter(function (m) { return m[2] > 0; }).length / mvs.length) + '% of drags paused (250 ms+)') +
        stat('Dwell before letting go', sec(fmedian(mvs.map(function (m) { return m[4]; }))), 'median') +
        stat('Hold before moving', sec(fmedian(mvs.map(function (m) { return m[6]; }))), 'median') + '</div>' : '') +
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
      (ab ? '<div class="pv-group"><h4>About you</h4>' + stat('Describes self as', esc(ab.neuro.map(function (v) { return ABOUT_NAMES[v] || v; }).join(', ') || '-'),
          esc(Object.keys(ab.dx || {}).map(function (c) { return (ABOUT_NAMES[c] || c) + ': ' + (ABOUT_NAMES[ab.dx[c]] || ab.dx[c]); }).join(' \u00b7 '))) +
        stat('Eating', esc((ab.eating || []).map(function (v) { return ABOUT_NAMES[v] || v; }).join(', ') || '-')) +
        stat('"I am a picky eater"', ab.picky != null ? ab.picky + ' / 7' : '-') + stat('"Food textures, smells or looks bother me"', ab.sensoryfood != null ? ab.sensoryfood + ' / 7' : '-') +
        stat('Age, gender', esc([ab.age, ab.gender].filter(Boolean).join(', ') || '-')) + '</div>' : '') +
      '</div></div>';
    el.innerHTML = html;
  }

  global.PizzaPreview = { render: render, reference: REF, faceDetect: faceDetect, symmetry: symmetry };
})(typeof window !== 'undefined' ? window : this);
