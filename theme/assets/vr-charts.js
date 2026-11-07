/* vr-charts.js: VitalRPA's drawing engine (the old window.VR from web/pages/_shared.html). It builds the SVG/HTML marks
   that Python would be slow to make: the 24-hour strip, 90-day uptime bars, sparklines, column bars, bar lists and the
   response-time line chart (hover crosshair), plus one shared tooltip for every [data-tip] mark, copy-to-clipboard and
   the beacon snippet. Python reaches it through client_code/vr.py and Components/Chart:
     VR.render(el, kind, dataJson, optsJson)   kind: cells | uptimeBars | spark | colbars | blist | lineChart
     VR.copy(text) -> Promise<bool>            VR.snippet(key, endpoint) -> the beacon (under 1 KB) */
(function () {
  'use strict';
  var esc = function (s) { return window.UI && UI.esc ? UI.esc(s) : String(s == null ? '' : s); };
  var VR = window.VR = window.VR || {};
  var M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  VR.num = function (n) { return n == null ? '—' : Number(n).toLocaleString('en-US'); };
  VR.ms = function (n) { return n == null ? '—' : n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 1 : 2) + ' s' : Math.round(n) + ' ms'; };
  VR.msShort = function (n) { return n >= 1000 ? (Math.round(n / 100) / 10) + 's' : Math.round(n) + 'ms'; };
  VR.pct = function (p) { return p == null ? '—' : (p >= 99.995 ? '100' : p.toFixed(p >= 99 ? 2 : 1)) + '%'; };
  VR.stamp = function (iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return M[d.getUTCMonth()] + ' ' + d.getUTCDate() + ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
  };
  VR.day = function (isoDay) { var d = new Date(isoDay + 'T12:00:00Z'); return M[d.getUTCMonth()] + ' ' + d.getUTCDate(); };

  /* 24 hourly cells, oldest first. */
  var CELL = { up: 'All checks passed', slow: 'Slow', down: 'Failed check(s)', none: 'No checks' };
  VR.cells = function (cells) {
    var now = new Date();
    cells = cells || [];
    return '<div class="vr-cells" role="img" aria-label="Last 24 hours: ' + cells.filter(function (c) { return c === 'down'; }).length + ' hours with failures">' +
      cells.map(function (c, i) {
        var h = new Date(now.getTime() - (cells.length - i) * 3600000);
        return '<i class="' + esc(c) + '" data-tip="' + pad(h.getUTCHours()) + ':00 UTC\n' + (CELL[c] || '') + '"></i>';
      }).join('') + '</div>';
  };
  /* 90 daily uptime bars. */
  VR.uptimeBars = function (bars) {
    return '<div class="vr-bars" role="img" aria-label="Uptime for the last 90 days">' + (bars || []).map(function (b) {
      var cls = b.pct == null ? '' : b.pct >= 99.9 ? 'up' : b.pct >= 98 ? 'slow' : 'down';
      var tip = VR.day(b.day) + '\n' + (b.pct == null ? 'No data' : VR.pct(b.pct) + ' up' + (b.fails ? ' · ' + b.fails + ' failed check' + (b.fails === 1 ? '' : 's') : ''));
      return '<i class="' + cls + '" data-tip="' + esc(tip) + '"></i>';
    }).join('') + '</div><div class="vr-axis"><span>90 days ago</span><span>today</span></div>';
  };
  /* A tiny response-time sparkline. */
  VR.spark = function (vals) {
    if (!vals || vals.length < 2) return '<svg class="vr-spark" aria-hidden="true"></svg>';
    var max = Math.max.apply(null, vals) * 1.1 || 1, n = vals.length - 1;
    var pts = vals.map(function (v, i) { return [(i / n) * 96, 26 - (v / max) * 24]; });
    var d = 'M' + pts.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L');
    return '<svg class="vr-spark" viewBox="0 0 96 26" preserveAspectRatio="none" aria-hidden="true"><path class="area" d="' + d + ' L96 26 L0 26 Z"/><path d="' + d + '"/></svg>';
  };
  /* Column bars (traffic per day / per hour). items: [{v, tip, cls}]; opts.height, opts.label */
  VR.colbars = function (items, opts) {
    opts = opts || {};
    items = items || [];
    var max = Math.max.apply(null, items.map(function (x) { return x.v || 0; }).concat([1]));
    return '<div class="vr-colbars" style="height:' + (opts.height || 120) + 'px" role="img" aria-label="' + esc(opts.label || 'Bar chart') + '">' + items.map(function (x) {
      var h = x.v == null ? 4 : Math.max(1, Math.round((x.v / max) * 100));
      return '<i class="' + esc(x.cls || '') + (x.v == null ? ' none' : '') + '" style="height:' + h + '%" data-tip="' + esc(x.tip) + '"></i>';
    }).join('') + '</div>';
  };
  /* Bar list (top pages, referrers, devices). items: [{name, n, pct}]; opts.empty */
  VR.blist = function (items, opts) {
    opts = opts || {};
    if (!items || !items.length) return '<p class="muted small">' + esc(opts.empty || 'Nothing yet.') + '</p>';
    var max = items[0].n || 1;
    return '<div class="vr-blist">' + items.map(function (x) {
      return '<div style="--w:' + Math.max(2, Math.round(100 * x.n / max)) + '%"><span title="' + esc(x.name) + '">' + esc(x.name) + '</span><b>' + VR.num(x.n) + ' · ' + x.pct + '%</b></div>';
    }).join('') + '</div>';
  };

  /* Response-time line chart with a hover crosshair. series: [[iso, ms, ok, slow], ...]; opts.limit = the slow limit */
  var charts = {}, chartN = 0;
  VR.lineChart = function (series, opts) {
    opts = opts || {};
    series = series || [];
    var id = 'c' + (++chartN);
    var pts = series.filter(function (s) { return s[1] != null; });
    if (pts.length < 2) return '<div class="ui-empty small"><i class="ic ic-pulse"></i><p>Not enough checks yet. The robots are on it.</p></div>';
    var t0 = new Date(series[0][0]).getTime(), t1 = new Date(series[series.length - 1][0]).getTime(), span = Math.max(1, t1 - t0);
    var okv = pts.filter(function (p) { return p[2]; }).map(function (p) { return p[1]; });
    var top = Math.max.apply(null, okv.concat([opts.limit && opts.limit < 1.6 * Math.max.apply(null, okv.concat([1])) ? opts.limit : 0, 50])) * 1.15;
    var nice = Math.pow(10, Math.floor(Math.log10(top))), maxY = Math.ceil(top / nice) * nice;
    var X = function (iso) { return ((new Date(iso).getTime() - t0) / span) * 1000; };
    var Y = function (v) { return 300 - Math.min(v, maxY) / maxY * 300; };
    var line = [], fails = [];
    series.forEach(function (s) {
      if (s[2] && s[1] != null) line.push(X(s[0]).toFixed(1) + ' ' + Y(s[1]).toFixed(1));
      else fails.push('<rect class="fail" x="' + (X(s[0]) - 3).toFixed(1) + '" y="288" width="6" height="12" rx="1.5"/>');
    });
    var d = 'M' + line.join(' L');
    var grid = [0, .5, 1].map(function (f) { return '<line x1="0" x2="1000" y1="' + (300 - f * 300) + '" y2="' + (300 - f * 300) + '"/>'; }).join('');
    charts[id] = { series: series, t0: t0, span: span, maxY: maxY };
    var limit = opts.limit && opts.limit < maxY ? '<line class="limit" x1="0" x2="1000" y1="' + Y(opts.limit) + '" y2="' + Y(opts.limit) + '"/>' : '';
    return '<div class="vr-chart" data-chart="' + id + '" role="img" aria-label="Response time chart">' +
      '<svg viewBox="0 0 1000 300" preserveAspectRatio="none"><g class="grid">' + grid + '</g>' + limit +
      (line.length > 1 ? '<path class="area" d="' + d + ' L' + line[line.length - 1].split(' ')[0] + ' 300 L' + line[0].split(' ')[0] + ' 300 Z"/><path class="line" d="' + d + '"/>' : '') +
      fails.join('') + '</svg>' +
      [0, .5, 1].map(function (f) { return '<span class="ylab" style="top:' + (100 - f * 100) + '%">' + VR.msShort(maxY * f) + '</span>'; }).join('') +
      (limit ? '<span class="limlab" style="top:' + (Y(opts.limit) / 3) + '%">slow limit ' + VR.ms(opts.limit) + '</span>' : '') +
      '<span class="xh"></span><span class="dot"></span></div>' +
      '<div class="vr-axis"><span>' + VR.stamp(series[0][0]) + '</span><span>' + VR.stamp(series[Math.floor(series.length / 2)][0]) + '</span><span>' + VR.stamp(series[series.length - 1][0]) + ' UTC</span></div>';
  };

  var KINDS = { cells: VR.cells, uptimeBars: VR.uptimeBars, spark: VR.spark, colbars: VR.colbars, blist: VR.blist, lineChart: VR.lineChart };
  /* Draw one chart into el (Python: vr.draw / Components/Chart). */
  VR.render = function (el, kind, dataJson, optsJson) {
    if (!el) return;
    var f = KINDS[kind];
    el.innerHTML = f ? f(dataJson ? JSON.parse(dataJson) : null, optsJson ? JSON.parse(optsJson) : {}) : '';
  };

  /* Copy text; resolves true when it worked. */
  VR.copy = function (text) {
    function fallback() {
      var ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      ta.remove();
      return ok;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallback(); });
    }
    return Promise.resolve(fallback());
  };

  /* The visitor beacon: under 1 KB, no cookies, runs after the page has loaded (the flow test checks the size). */
  VR.snippet = function (key, endpoint) {
    return '<!-- VitalRPA beacon: under 1 KB, no cookies, runs after the page has loaded -->\n<script>\n' +
      '!function(w,d,n,k,u){if(n.doNotTrack=="1"||n.webdriver)return;var e=0;function s(o){o.k=k;o.p=location.pathname;' +
      'var q=u+"?"+new URLSearchParams(o);n.sendBeacon?n.sendBeacon(q):(new Image).src=q}w.vrpa=s;' +
      'w.addEventListener("error",function(x){e++<3&&s({t:"e",m:String(x.message).slice(0,140),s:(x.filename||"").split("?")[0].slice(-80)+":"+x.lineno})});' +
      'function v(){setTimeout(function(){var t=performance.getEntriesByType?performance.getEntriesByType("navigation")[0]||{}:{};' +
      's({t:"v",r:d.referrer.split("/")[2]||"",w:w.innerWidth,l:Math.round(t.loadEventStart||0),f:Math.round(t.responseStart||0)})},0)}' +
      'd.readyState=="complete"?v():w.addEventListener("load",v)}(window,document,navigator,"' + key + '","' + endpoint + '");\n<\/script>';
  };
  VR.bytes = function (text) { return new Blob([text]).size; };

  /* One shared tooltip for [data-tip] marks and the line charts. */
  var tip = null;
  function showTip(text, x, y) {
    if (!tip) { tip = document.createElement('div'); tip.className = 'vr-tip'; tip.setAttribute('aria-hidden', 'true'); document.body.appendChild(tip); }
    tip.textContent = text; tip.style.display = 'block';
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(6, Math.min(innerWidth - w - 6, x - w / 2)) + 'px';
    tip.style.top = (y - h - 12 < 6 ? y + 18 : y - h - 12) + 'px';
  }
  function hideTip() { if (tip) tip.style.display = 'none'; }
  document.addEventListener('mousemove', function (e) {
    var t = e.target.closest && e.target.closest('[data-tip]');
    var c = e.target.closest && e.target.closest('.vr-chart');
    document.querySelectorAll('.vr-chart.hover').forEach(function (el) { if (el !== c) el.classList.remove('hover'); });
    if (c && charts[c.getAttribute('data-chart')]) {
      var ch = charts[c.getAttribute('data-chart')], r = c.getBoundingClientRect();
      var at = ch.t0 + ((e.clientX - r.left) / r.width) * ch.span, best = null, bd = Infinity;
      ch.series.forEach(function (s) { var dd = Math.abs(new Date(s[0]).getTime() - at); if (dd < bd) { bd = dd; best = s; } });
      if (!best) return;
      var fx = (new Date(best[0]).getTime() - ch.t0) / ch.span, fy = best[1] == null || !best[2] ? 1 : 1 - Math.min(best[1], ch.maxY) / ch.maxY;
      c.classList.add('hover');
      c.querySelector('.xh').style.left = (fx * 100) + '%';
      var dot = c.querySelector('.dot');
      dot.style.left = (fx * 100) + '%'; dot.style.top = (fy * 100) + '%';
      dot.style.background = !best[2] ? 'var(--c-bad)' : best[3] ? 'var(--c-warn)' : 'var(--c-brand)';
      showTip(VR.stamp(best[0]) + ' UTC\n' + (best[2] ? VR.ms(best[1]) + (best[3] ? ' (slow)' : '') : 'FAILED' + (best[1] ? ' after ' + VR.ms(best[1]) : '')), r.left + fx * r.width, r.top + fy * r.height);
      return;
    }
    if (t) { showTip(t.getAttribute('data-tip'), e.clientX, e.clientY); return; }
    hideTip();
  });
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-tip]');
    if (t && matchMedia('(pointer: coarse)').matches) { var r = t.getBoundingClientRect(); showTip(t.getAttribute('data-tip'), r.left + r.width / 2, r.top); }
  });
  window.addEventListener('scroll', hideTip, { passive: true });
  window.addEventListener('hashchange', hideTip);
})();
