/* core.js: the shared front-end engine (window.UI). Same in every app made from APP_MAKER/template;
   app-specific things live in web/app.js (brand, nav, footer) and web/pages/*.html (the pages).

   Pages:   UI.page(name, {title, nav, icon, auth, order, chrome}, mount)
              auth: null (anyone) | 'guest' (signed-out only) | 'user' | 'admin'
              nav: label for the header / phone tab bar (omit to keep it out of the menus)
              mount(view, ctx) draws into `view`; ctx = {args, me, go, api}. Return a Promise (the page
              is "ready" when it resolves) or {ready, destroy}. URLs are #name/arg1/arg2.
   Server:  UI.api(fn, ...args) -> Promise of the server function's return value. A reply of
              {ok: false, error} rejects with that message (shown as a toast unless you .catch it).
            UI.apiQuiet(fn, ...args) is the same without Anvil's loading spinner.
   Auth:    UI.auth('login'|'signup'|'reset'|'logout', {...}) -> Promise of {ok, me, message}
   Helpers: UI.esc, UI.icon, UI.toast, UI.modal, UI.confirm, UI.busy, UI.formData, UI.fmtDate, UI.ago,
            UI.store, UI.setTheme, UI.feedback, UI.go, UI.refresh
   Tests:   window.UI_READY is true when the current page has finished loading. */
(function () {
  'use strict';
  if (window.UI && window.UI.__v) return;
  var UI = window.UI = { __v: 1, pages: {}, me: null, config: { name: 'App', key: 'app', home: 'home', landing: 'landing' } };
  window.UI_READY = false;

  UI.configure = function (cfg) { Object.keys(cfg).forEach(function (k) { UI.config[k] = cfg[k]; }); };

  /* ------------------------------------------------------------------ small helpers */
  UI.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  UI.plural = function (n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); };
  UI.initials = function (name) {
    var p = String(name || '?').trim().split(/\s+/);
    return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
  };
  UI.fmtDate = function (iso, opts) {
    if (!iso) return '';
    var d = iso.length <= 10 ? new Date(iso + 'T12:00:00') : new Date(iso);
    return d.toLocaleDateString(undefined, opts || { day: 'numeric', month: 'short', year: 'numeric' });
  };
  UI.fmtDateTime = function (iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  };
  UI.ago = function (iso) {
    if (!iso) return '';
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'just now';
    var steps = [[60, 'minute'], [24, 'hour'], [7, 'day'], [4.35, 'week'], [12, 'month'], [Infinity, 'year']], n = s / 60;
    for (var i = 0; i < steps.length; i++) {
      if (n < steps[i][0]) { n = Math.floor(n); return UI.plural(n, steps[i][1]) + ' ago'; }
      n = n / steps[i][0];
    }
    return '';
  };
  UI.store = {
    get: function (k, dflt) { try { var v = localStorage.getItem(UI.config.key + '.' + k); return v == null ? dflt : JSON.parse(v); } catch (e) { return dflt; } },
    set: function (k, v) { try { localStorage.setItem(UI.config.key + '.' + k, JSON.stringify(v)); } catch (e) {} }
  };
  UI.formData = function (form) {
    var out = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled) return;
      if (el.type === 'checkbox') out[el.name] = el.checked;
      else if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; }
      else out[el.name] = el.value;
    });
    return out;
  };
  /* Disable a button while a Promise runs; returns the Promise. */
  UI.busy = function (btn, promise) {
    if (!btn) return promise;
    btn.disabled = true; btn.classList.add('is-busy');
    var done = function () { btn.disabled = false; btn.classList.remove('is-busy'); };
    promise.then(done, done);
    return promise;
  };

  var ICONS = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.5 3-5.5 6.5-5.5s6.5 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18 14.7c2.2.6 3.5 2.4 3.5 5.3"/>',
    sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z"/>',
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    back: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    bug: '<rect x="7" y="8" width="10" height="12" rx="5"/><path d="M12 8V5M9 5.5 7.5 4M15 5.5 16.5 4M7 13H3M21 13h-4M7.5 18l-3 2M16.5 18l3 2M7.5 9.5l-3-2M16.5 9.5l3-2"/>',
    bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    heart: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    database: '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/><path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13"/><path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    pin: '<path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    camera: '<path d="M4 8h3l2-3h6l2 3h3v12H4z"/><circle cx="12" cy="13.5" r="3.5"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    filter: '<path d="M4 5h16l-6 7.5V19l-4 1.5v-8z"/>',
    more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>'
  };
  UI.ICONS = ICONS;
  UI.icon = function (name, cls) {
    return '<svg class="ui-ic ' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || ICONS.sparkle) + '</svg>';
  };

  /* ------------------------------------------------------------------ toasts, modals */
  UI.toast = function (msg, kind) {
    var box = document.querySelector('.ui-toasts');
    if (!box) { box = document.createElement('div'); box.className = 'ui ui-toasts'; box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    var t = document.createElement('div');
    t.className = 'ui-toast' + (kind ? ' ' + kind : '');
    t.innerHTML = (kind === 'error' ? UI.icon('info') : kind === 'ok' ? UI.icon('check') : '') + '<span>' + UI.esc(msg) + '</span>';
    box.appendChild(t);
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 300); }, kind === 'error' ? 6500 : 3200);
  };
  UI.modal = function (html, opts) {
    opts = opts || {};
    var prev = document.activeElement;
    var wrap = document.createElement('div');
    wrap.className = 'ui ui-modal-wrap';
    wrap.innerHTML = '<div class="ui-modal' + (opts.wide ? ' wide' : '') + '" role="dialog" aria-modal="true">' +
      '<button class="ui-btn ghost icon ui-modal-x" data-close aria-label="Close">' + UI.icon('x') + '</button>' + html + '</div>';
    document.body.appendChild(wrap);
    document.documentElement.classList.add('ui-modal-open');
    function key(e) { if (e.key === 'Escape') close(); }
    function close() {
      if (!wrap.parentNode) return;
      wrap.remove(); document.removeEventListener('keydown', key);
      if (!document.querySelector('.ui-modal-wrap')) document.documentElement.classList.remove('ui-modal-open');
      if (opts.onclose) opts.onclose();
      if (prev && prev.focus) prev.focus();
    }
    document.addEventListener('keydown', key);
    wrap.addEventListener('mousedown', function (e) { if (e.target === wrap) close(); });
    wrap.addEventListener('click', function (e) { if (e.target.closest('[data-close]')) close(); });
    var first = wrap.querySelector('input, textarea, select');
    setTimeout(function () { (first || wrap.querySelector('.ui-modal')).focus && (first || wrap.querySelector('.ui-modal')).focus(); }, 30);
    return { el: wrap.querySelector('.ui-modal'), close: close };
  };
  UI.confirm = function (o) {
    o = typeof o === 'string' ? { title: o } : (o || {});
    return new Promise(function (resolve) {
      var answered = false;
      var m = UI.modal('<h2>' + UI.esc(o.title || 'Are you sure?') + '</h2>' + (o.text ? '<p class="muted">' + UI.esc(o.text) + '</p>' : '') +
        '<div class="ui-row end" style="margin-top:20px"><button class="ui-btn ghost" data-close>' + UI.esc(o.cancel || 'Cancel') + '</button>' +
        '<button class="ui-btn ' + (o.danger ? 'danger solid' : 'primary') + '" data-ok>' + UI.esc(o.ok || 'OK') + '</button></div>',
      { onclose: function () { if (!answered) resolve(false); } });
      m.el.querySelector('[data-ok]').onclick = function () { answered = true; m.close(); resolve(true); };
    });
  };

  /* ------------------------------------------------------------------ theme */
  UI.theme = function () { return UI.store.get('theme', 'auto'); };
  UI.applyTheme = function (t) {
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
    else document.documentElement.removeAttribute('data-theme');
    var dark = t === 'dark' || (t !== 'light' && window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('ui-dark', !!dark);
  };
  UI.setTheme = function (t) { UI.store.set('theme', t); UI.applyTheme(t); };
  UI.applyTheme(UI.theme());
  if (window.matchMedia) {
    try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { UI.applyTheme(UI.theme()); }); } catch (e) {}
  }

  /* ------------------------------------------------------------------ server bridge */
  var bridge = null;
  function send(kind, payload) {
    if (!bridge) return Promise.reject(new Error('The app is still starting.'));
    var out;
    try { out = bridge(kind, JSON.stringify(payload || {})); } catch (e) { return Promise.reject(e); }
    return Promise.resolve(out).then(function (r) {
      r = typeof r === 'string' ? JSON.parse(r) : (r || {});
      if (r.error) {
        var err = new Error(r.error); err.uiApi = true; err.denied = !!r.denied;
        if (r.detail) console.error(kind, payload && payload.fn, r.detail);
        if (r.reload) setTimeout(function () { location.reload(); }, 2500);
        throw err;
      }
      return r.result;
    });
  }
  function apiCall(quiet, fn, args) {
    return send('call', { fn: fn, args: args, quiet: quiet }).then(function (res) {
      if (res && typeof res === 'object' && res.ok === false) {
        var err = new Error(res.error || 'That didn\'t work.'); err.uiApi = true; err.expected = true; err.result = res;
        throw err;
      }
      return res;
    });
  }
  UI.api = function (fn) { return apiCall(false, fn, Array.prototype.slice.call(arguments, 1)); };
  UI.apiQuiet = function (fn) { return apiCall(true, fn, Array.prototype.slice.call(arguments, 1)); };
  /* Errors nobody caught become a toast, so a failed action is never silent. */
  window.addEventListener('unhandledrejection', function (e) {
    if (e.reason && e.reason.uiApi) { e.preventDefault(); UI.toast(e.reason.message, 'error'); }
  });

  /* Sign in / up / out. On success it navigates: to where the visitor was heading (UI.after) or home
     after signing in, to the landing page after signing out. */
  UI.auth = function (kind, payload) {
    return send(kind, payload || {}).then(function (r) {
      if (r && r.ok === false) { var err = new Error(r.error); err.uiApi = true; err.expected = true; throw err; }
      if (r && 'me' in r && (r.me || kind === 'logout')) {
        UI.me = r.me || null;
        var target = r.me ? (UI.after || '#' + UI.config.home) : '#' + UI.config.landing;
        UI.after = null;
        if (location.hash === target) route(); else location.hash = target;
      }
      return r;
    });
  };
  /* Update the signed-in user's details (e.g. a new name) and redraw the header, without reloading the page. */
  UI.setMe = function (me) {
    UI.me = me || null;
    if (shellRoot) renderChrome(current.name);
  };

  /* ------------------------------------------------------------------ pages and routing */
  UI.page = function (name, opts, mount) {
    if (typeof opts === 'function') { mount = opts; opts = {}; }
    opts.name = name; opts.mount = mount;
    UI.pages[name] = opts;
  };
  UI.allowed = function (p) {
    if (!p) return false;
    if (p.auth === 'user') return !!UI.me;
    if (p.auth === 'admin') return !!(UI.me && UI.me.is_admin);
    if (p.auth === 'guest') return !UI.me;
    return true;
  };
  UI.navPages = function () {
    return Object.keys(UI.pages).map(function (k) { return UI.pages[k]; })
      .filter(function (p) { return p.nav && UI.allowed(p) && (!p.when || p.when()); })
      .sort(function (a, b) { return (a.order || 50) - (b.order || 50); });
  };
  UI.parseHash = function () {
    var h = (location.hash || '').replace(/^#!?\/?/, '');
    var parts = h.split('?')[0].split('/').filter(function (x) { return x !== ''; }).map(decodeURIComponent);
    return { name: parts[0] || '', args: parts.slice(1) };
  };
  UI.hashFor = function (name) {
    var args = Array.prototype.slice.call(arguments, 1).filter(function (a) { return a != null && a !== ''; });
    return '#' + [name].concat(args.map(encodeURIComponent)).join('/');
  };
  UI.go = function (name) {
    var h = UI.hashFor.apply(null, arguments);
    if (location.hash === h) route(); else location.hash = h;
  };
  UI.refresh = function () { route(); };
  UI.after = null;  // where to go after signing in

  var shellRoot = null, view = null, current = { name: null, destroy: null }, routeSeq = 0;

  function defaultPage() { return UI.me ? UI.config.home : UI.config.landing; }

  function route() {
    var r = UI.parseHash(), name = r.name || defaultPage(), p = UI.pages[name];
    if (!p) { name = defaultPage(); p = UI.pages[name]; r.args = []; }
    if (p.auth === 'guest' && UI.me) { p = UI.pages[UI.config.home]; name = UI.config.home; r.args = []; }
    if ((p.auth === 'user' || p.auth === 'admin') && !UI.me) {
      UI.after = location.hash && location.hash !== '#' ? location.hash : null;
      p = UI.pages.auth; name = 'auth'; r.args = [];
    }
    if (p.auth === 'admin' && !(UI.me && UI.me.is_admin)) {
      UI.toast('That page is for admins only.', 'error');
      p = UI.pages[UI.config.home]; name = UI.config.home; r.args = [];
    }
    var seq = ++routeSeq;
    window.UI_READY = false;
    if (current.destroy) { try { current.destroy(); } catch (e) { console.error(e); } }
    current = { name: name, args: r.args, destroy: null };
    if (shellRoot) {
      shellRoot.className = 'ui ui-shell page-' + name + (UI.me ? ' signed-in' : ' signed-out') + (p.chrome === false ? ' no-chrome' : '');
      renderChrome(name);
    }
    // A fresh element for every page, so listeners a page adds to `view` never pile up.
    var fresh = view.cloneNode(false);
    view.parentNode.replaceChild(fresh, view);
    view = fresh;
    window.scrollTo(0, 0);
    document.title = (p.title ? (typeof p.title === 'function' ? p.title(r.args) : p.title) + ' · ' : '') + UI.config.name;
    var ctx = { name: name, args: r.args, me: UI.me, go: UI.go, api: UI.api, page: p };
    var out;
    try { out = p.mount(view, ctx); } catch (e) { console.error(e); out = Promise.reject(e); }
    var ready = out && typeof out.then === 'function' ? out : (out && out.ready) || Promise.resolve();
    if (out && out.destroy) current.destroy = out.destroy;
    Promise.resolve(ready).then(function () { if (seq === routeSeq) window.UI_READY = true; },
      function (e) {
        if (seq !== routeSeq) return;
        console.error(e);
        if (!view.innerHTML) view.innerHTML = '<div class="ui-wrap"><div class="ui-empty">' + UI.icon('info') +
          '<h3>This page didn\'t load</h3><p class="muted">' + UI.esc(e && e.message || 'Something went wrong.') + '</p>' +
          '<button class="ui-btn" onclick="UI.refresh()">Try again</button></div></div>';
        window.UI_READY = true;
      });
  }
  UI.current = function () { return current; };

  /* The shell's parts come from web/app.js: UI.shell = {header(me, active), footer(me), tabbar(me, active)} */
  function renderChrome(active) {
    var S = UI.shell || {};
    var hd = shellRoot.querySelector('[data-ui-header]'), ft = shellRoot.querySelector('[data-ui-footer]'), tb = shellRoot.querySelector('[data-ui-tabbar]');
    if (hd) hd.innerHTML = S.header ? S.header(UI.me, active) : '';
    if (ft) ft.innerHTML = S.footer ? S.footer(UI.me, active) : '';
    if (tb) tb.innerHTML = S.tabbar ? S.tabbar(UI.me, active) : '';
  }
  UI.renderChrome = function () { if (shellRoot) renderChrome(current.name); };

  /* Called by client_code/Main.py (and by the local harness) once the page is up. */
  UI.start = function (node, bridgeFn, bootJson) {
    bridge = bridgeFn;
    var boot = typeof bootJson === 'string' ? JSON.parse(bootJson || '{}') : (bootJson || {});
    UI.me = boot.me || null;
    var host = node && node.matches && node.matches('[data-ui-app]') ? node : (node && node.querySelector('[data-ui-app]')) || node || document.body;
    host.innerHTML = '<div class="ui ui-shell">' +
      '<header class="ui-header" data-ui-header></header>' +
      '<main class="ui-main" data-ui-view></main>' +
      '<footer class="ui-footer" data-ui-footer></footer>' +
      '<nav class="ui-tabbar" data-ui-tabbar aria-label="Main"></nav></div>';
    shellRoot = host.firstChild;
    view = host.querySelector('[data-ui-view]');
    if (UI.shell && UI.shell.wire) UI.shell.wire(shellRoot);
    window.addEventListener('hashchange', route);
    route();
  };

  /* ------------------------------------------------------------------ feedback (footer + menu)
     All feedback goes to Prepsto. The widget tag in head.html (data-prepsto="CODE") slides its panel in;
     any [data-feedback] or [data-prepsto-open] element opens it. If the widget hasn't loaded, the panel opens in a new tab.
     There is no in-app feedback form any more: Admin -> Feedback only lists older messages (and app requests). */
  UI.feedback = function () {
    if (window.Prepsto && window.Prepsto.open) { window.Prepsto.open(); return; }
    var tag = document.querySelector('script[data-prepsto]');
    var code = tag && tag.getAttribute('data-prepsto');
    if (code && code.indexOf('__') !== 0) window.open('https://prepsto.com/#f/' + encodeURIComponent(code), '_blank', 'noopener');
    else UI.toast('Feedback is not set up yet.', 'error');
  };

  /* Shared clicks: [data-go="page/arg"], [data-feedback], [data-theme-set] anywhere in the app. */
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-go],[data-feedback],[data-theme-set]');
    if (!el) return;
    if (el.hasAttribute('data-go')) { e.preventDefault(); UI.go.apply(null, el.getAttribute('data-go').split('/')); }
    else if (el.hasAttribute('data-feedback')) { e.preventDefault(); UI.feedback(el.getAttribute('data-feedback') || null); }
    else if (el.hasAttribute('data-theme-set')) { e.preventDefault(); UI.setTheme(el.getAttribute('data-theme-set')); if (UI.shell && UI.shell.onTheme) UI.shell.onTheme(); }
  });
})();


/* app.js: this app's identity and frame: name, header (with a UTC clock and the open-incident count),
   footer, phone tab bar, and the extra icons. Pages live in web/pages/*.html; shared VitalRPA helpers
   (status lights, charts, tooltips) in web/pages/_shared.html. The engine (window.UI) is web/core.js. */
(function () {
  'use strict';
  UI.configure({
    name: 'VitalRPA',
    key: 'vitalrpa',
    tagline: 'Robots that watch your websites, around the clock.',
    home: 'home',
    landing: 'landing'
  });

  var I = UI.ICONS;
  I.pulse = '<path d="M3 12h4l2.5-6 4 12 3-9 1.5 3H21"/>';
  I.robot = '<rect x="5" y="8" width="14" height="11" rx="2.5"/><path d="M12 4v4M9 13h.01M15 13h.01M9.5 16.5h5M3 12v3M21 12v3"/><circle cx="12" cy="3.5" r="1"/>';
  I.radar = '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18 6"/><circle cx="12" cy="12" r="1"/>';
  I.server = '<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 7.5h.01M7 16.5h.01M11 7.5h6M11 16.5h6"/>';
  I.code = '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>';
  I.play = '<path d="M7 5v14l11-7z"/>';
  I.pause = '<path d="M8 5v14M16 5v14"/>';
  I.zap = '<path d="M13 3 5 13h6l-1 8 8-10h-6z"/>';
  I.terminal = '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M12.5 15H17"/>';
  I.key = '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M14.5 8.5l2 2"/>';
  I.link = '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>';
  I.gauge = '<path d="M4 18a8 8 0 1 1 16 0"/><path d="m12 18 4-6"/>';
  I.alert = '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4.5M12 17.5h.01"/>';
  I.tag = '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.3"/>';
  I.eye = '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>';
  I.heart = '<path d="M3 12h3l2-4 3 8 2-5h3"/><path d="M12 20s-8-4.8-8-11a4.3 4.3 0 0 1 8-2.2A4.3 4.3 0 0 1 20 9c0 1.1-.2 2.1-.7 3"/>';
  I.status = '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h2M7 13h2M7 17h2M12 9h5M12 13h5M12 17h5"/>';
  I.send = '<path d="M21 3 10 14"/><path d="m21 3-7 18-4-7-7-4z"/>';
  I.cog = '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>';

  var esc = UI.esc;
  UI.vrOpen = 0;  // open incidents in the visible fleet: pages set it with VR.setOpen(n)

  function brand() {
    return '<a class="ui-brand" href="#" data-go="' + (UI.me ? UI.config.home : UI.config.landing) + '" aria-label="' + esc(UI.config.name) + ' home">' +
      '<img src="_/theme/icon.svg" alt="" width="28" height="28"><span>' + esc(UI.config.name) + '</span></a>';
  }

  function clockText() {
    var d = new Date();
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return 'UTC ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds());
  }
  setInterval(function () {
    var c = document.querySelector('[data-clock]');
    if (c) c.textContent = clockText();
  }, 1000);

  function themeSwitch() {
    var t = UI.theme();
    return '<div class="ui-seg" role="group" aria-label="Appearance">' + [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']].map(function (o) {
      return '<button type="button" data-theme-set="' + o[0] + '" class="' + (t === o[0] ? 'on' : '') + '">' + o[1] + '</button>';
    }).join('') + '</div>';
  }

  function userMenu(me) {
    return '<div class="ui-menu" data-menu hidden>' +
      '<div class="ui-menu-head"><strong>' + esc(me.name) + '</strong><span class="muted small">' + esc(me.email) + '</span></div>' +
      '<a href="#profile" data-go="profile">' + UI.icon('user') + 'Profile &amp; alerts</a>' +
      (me.is_admin ? '<a href="#admin" data-go="admin">' + UI.icon('shield') + 'Admin</a>' : '') +
      '<div class="ui-menu-block"><span class="small muted">Appearance</span>' + themeSwitch() + '</div>' +
      '<button type="button" data-feedback>' + UI.icon('chat') + 'Submit feedback</button>' +
      '<button type="button" data-lk-open="overview">' + UI.icon('lock') + 'Privacy &amp; Terms</button>' +
      '<button type="button" data-signout>' + UI.icon('logout') + 'Sign out</button></div>';
  }

  function count(p) {
    return p.name === 'incidents' && UI.vrOpen ? ' <span class="vr-count" aria-label="' + UI.vrOpen + ' open">' + UI.vrOpen + '</span>' : '';
  }

  UI.shell = {
    header: function (me, active) {
      var nav = UI.navPages();
      return '<div class="ui-header-in">' + brand() +
        (me ? '<nav class="ui-nav" aria-label="Main">' + nav.map(function (p) {
          return '<a href="#' + p.name + '" class="' + (p.name === active ? 'on' : '') + '">' + UI.icon(p.icon) + '<span>' + esc(p.nav) + '</span>' + count(p) + '</a>';
        }).join('') + '</nav>' : '') +
        '<div class="ui-header-right">' +
        (me ? '<span class="vr-clock" title="Robot time (UTC)"><i></i><span data-clock>' + clockText() + '</span></span>' +
          '<button type="button" class="ui-avatar-btn" data-menu-toggle aria-label="Your account" aria-haspopup="true">' + esc(UI.initials(me.name)) + '</button>' + userMenu(me)
          : (active === 'auth' ? '' : '<a class="ui-btn ghost" href="#auth" data-go="auth">Sign in</a><a class="ui-btn primary" href="#auth/signup" data-go="auth/signup">Start monitoring</a>')) +
        '</div></div>';
    },
    footer: function (me) {
      return '<div class="ui-footer-in"><div class="ui-footer-brand">' + brand() + '<p class="muted small">' + esc(UI.config.tagline) + '</p></div>' +
        '<div class="ui-footer-links">' +
        '<a href="#landing" data-go="landing">About</a>' +
        '<a href="#status/northwind" data-go="status/northwind">Sample status page</a>' +
        '<a href="https://prepsto.com/#f/ny2cnbz" target="_blank" rel="noopener" data-prepsto-open>Submit feedback</a>' +
        '<button type="button" data-lk-open="overview">Privacy &amp; Terms</button>' +
        '</div><p class="ui-footer-legal small muted">© ' + new Date().getFullYear() + ' ' + esc(UI.config.name) + ' · robot time is UTC</p></div>';
    },
    tabbar: function (me, active) {
      var nav = UI.navPages();
      if (!me || nav.length < 2) return '';
      return nav.slice(0, 4).map(function (p) {
        return '<a href="#' + p.name + '" class="' + (p.name === active ? 'on' : '') + '">' + UI.icon(p.icon) + '<span>' + esc(p.nav) + '</span>' + count(p) + '</a>';
      }).join('') + '<a href="#profile" class="' + (active === 'profile' ? 'on' : '') + '">' + UI.icon('user') + '<span>You</span></a>';
    },
    wire: function (root) {
      root.addEventListener('click', function (e) {
        var t = e.target.closest('[data-menu-toggle]');
        var menu = root.querySelector('[data-menu]');
        if (t && menu) { menu.hidden = !menu.hidden; t.setAttribute('aria-expanded', String(!menu.hidden)); return; }
        if (e.target.closest('[data-signout]')) { UI.auth('logout').then(function () { UI.toast('Signed out. The robots keep watching.'); }); }
        if (menu && !menu.hidden && !e.target.closest('[data-menu] .ui-seg')) menu.hidden = true;
      });
      document.addEventListener('keydown', function (e) {
        var menu = root.querySelector('[data-menu]');
        if (e.key === 'Escape' && menu) menu.hidden = true;
      });
    },
    onTheme: function () {
      var menu = document.querySelector('[data-menu]'), open = menu && !menu.hidden;
      UI.renderChrome();
      if (open) document.querySelector('[data-menu]').hidden = false;
    }
  };
})();


/* ===== _shared.html ===== */
(function () {
  var esc = UI.esc;
  var VR = window.VR = {};
  VR.STATUS = { up: 'Up', slow: 'Slow', retrying: 'Retrying', down: 'Down', paused: 'Paused', pending: 'Pending' };

  VR.led = function (s) { return '<span class="vr-led s-' + esc(s || 'pending') + '" aria-hidden="true"></span>'; };
  VR.badge = function (s) { return '<span class="ui-badge vr-st s-' + esc(s) + '">' + VR.led(s) + esc(VR.STATUS[s] || s) + '</span>'; };
  VR.sev = function (sev, resolved) {
    if (resolved) return '<span class="ui-badge good">' + UI.icon('check') + 'Resolved</span>';
    return sev === 'critical' ? '<span class="ui-badge bad">' + UI.icon('alert') + 'Critical</span>'
      : '<span class="ui-badge warn">' + UI.icon('info') + 'Warning</span>';
  };
  VR.num = function (n) { return n == null ? '—' : Number(n).toLocaleString('en-US'); };
  VR.ms = function (n) { return n == null ? '—' : n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 1 : 2) + ' s' : Math.round(n) + ' ms'; };
  VR.msShort = function (n) { return n >= 1000 ? (Math.round(n / 100) / 10) + 's' : Math.round(n) + 'ms'; };
  VR.pct = function (p) { return p == null ? '—' : (p >= 99.995 ? '100' : p.toFixed(p >= 99 ? 2 : 1)) + '%'; };
  VR.bytes = function (n) { return n == null ? '—' : n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n >= 1024 ? Math.round(n / 1024) + ' KB' : n + ' B'; };
  VR.every = function (m) { return m >= 1440 ? (m / 1440) + ' day' : m >= 60 ? (m / 60) + ' h' : m + ' min'; };
  VR.perDay = function (m) { return Math.round(1440 / m); };
  VR.dur = function (min) {
    if (min < 1) return '<1 min';
    if (min < 60) return min + ' min';
    if (min < 1440) return Math.floor(min / 60) + ' h ' + (min % 60 ? (min % 60) + ' min' : '');
    return Math.floor(min / 1440) + ' d ' + Math.floor((min % 1440) / 60) + ' h';
  };
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  VR.hhmm = function (iso) { if (!iso) return '—'; var d = new Date(iso); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); };
  VR.stamp = function (iso) {
    if (!iso) return '—';
    var d = new Date(iso), M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return M[d.getUTCMonth()] + ' ' + d.getUTCDate() + ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
  };
  VR.day = function (isoDay) {
    var d = new Date(isoDay + 'T12:00:00Z'), M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return M[d.getUTCMonth()] + ' ' + d.getUTCDate();
  };
  VR.until = function (iso) {
    if (!iso) return '';
    var m = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
    return m <= 0 ? 'due now' : 'in ' + (m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min');
  };
  VR.daysTag = function (n, warn) {
    if (n == null) return '<span class="faint">—</span>';
    var cls = n <= 3 ? 'bad' : n <= (warn || 14) ? 'warn' : '';
    return '<span class="ui-badge ' + cls + '">' + n + 'd</span>';
  };
  VR.setOpen = function (n) { if (UI.vrOpen !== n) { UI.vrOpen = n; UI.renderChrome(); } };
  VR.copy = function (text, what) {
    var done = function () { UI.toast((what || 'Copied') + ' to the clipboard', 'ok'); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    else fallback();
    function fallback() {
      var ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { UI.toast('Select the text and copy it by hand', 'error'); }
      ta.remove();
    }
  };

  /* 24 hourly cells, oldest first. */
  var CELL = { up: 'All checks passed', slow: 'Slow', down: 'Failed check(s)', none: 'No checks' };
  VR.cells = function (cells) {
    var now = new Date();
    return '<div class="vr-cells" role="img" aria-label="Last 24 hours: ' + cells.filter(function (c) { return c === 'down'; }).length + ' hours with failures">' +
      cells.map(function (c, i) {
        var h = new Date(now.getTime() - (24 - i) * 3600000);
        return '<i class="' + c + '" data-tip="' + pad(h.getUTCHours()) + ':00 UTC\n' + CELL[c] + '"></i>';
      }).join('') + '</div>';
  };
  /* 90 daily uptime bars. */
  VR.uptimeBars = function (bars) {
    return '<div class="vr-bars" role="img" aria-label="Uptime for the last 90 days">' + bars.map(function (b) {
      var cls = b.pct == null ? '' : b.pct >= 99.9 ? 'up' : b.pct >= 98 ? 'slow' : 'down';
      var tip = VR.day(b.day) + '\n' + (b.pct == null ? 'No data' : VR.pct(b.pct) + ' up' + (b.fails ? ' · ' + b.fails + ' failed check' + (b.fails === 1 ? '' : 's') : ''));
      return '<i class="' + cls + '" data-tip="' + esc(tip) + '"></i>';
    }).join('') + '</div><div class="vr-axis"><span>90 days ago</span><span>today</span></div>';
  };
  VR.legend = function () {
    return '<div class="vr-legend"><span><i class="up"></i>up</span><span><i class="slow"></i>slow / partial</span><span><i class="down"></i>down</span><span><i></i>no data</span></div>';
  };
  /* A tiny response-time sparkline. */
  VR.spark = function (vals) {
    if (!vals || vals.length < 2) return '<svg class="vr-spark" aria-hidden="true"></svg>';
    var max = Math.max.apply(null, vals) * 1.1 || 1, n = vals.length - 1;
    var pts = vals.map(function (v, i) { return [(i / n) * 96, 26 - (v / max) * 24]; });
    var d = 'M' + pts.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L');
    return '<svg class="vr-spark" viewBox="0 0 96 26" preserveAspectRatio="none" aria-hidden="true"><path class="area" d="' + d + ' L96 26 L0 26 Z"/><path d="' + d + '"/></svg>';
  };
  /* Column bars (traffic per day / per hour). items: [{v, label, tip, cls}] */
  VR.colbars = function (items, height) {
    var max = Math.max.apply(null, items.map(function (x) { return x.v || 0; }).concat([1]));
    return '<div class="vr-colbars" style="height:' + (height || 120) + 'px" role="img" aria-label="Bar chart">' + items.map(function (x) {
      var h = x.v == null ? 4 : Math.max(1, Math.round((x.v / max) * 100));
      return '<i class="' + (x.cls || '') + (x.v == null ? ' none' : '') + '" style="height:' + h + '%" data-tip="' + esc(x.tip) + '"></i>';
    }).join('') + '</div>';
  };
  VR.blist = function (items, empty) {
    if (!items || !items.length) return '<p class="muted small">' + esc(empty || 'Nothing yet.') + '</p>';
    var max = items[0].n || 1;
    return '<div class="vr-blist">' + items.map(function (x) {
      return '<div style="--w:' + Math.max(2, Math.round(100 * x.n / max)) + '%"><span title="' + esc(x.name) + '">' + esc(x.name) + '</span><b>' + VR.num(x.n) + ' · ' + x.pct + '%</b></div>';
    }).join('') + '</div>';
  };

  /* Response-time line chart with a hover crosshair. series: [[iso, ms, ok, slow], ...] */
  var charts = {}, chartN = 0;
  VR.lineChart = function (series, opts) {
    opts = opts || {};
    var id = 'c' + (++chartN);
    var pts = series.filter(function (s) { return s[1] != null; });
    if (pts.length < 2) return '<div class="ui-empty small">' + UI.icon('pulse') + '<p>Not enough checks yet. The robots are on it.</p></div>';
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

  /* One shared tooltip for [data-tip] marks and the line charts. */
  var tip = null;
  function showTip(text, x, y) {
    if (!tip) { tip = document.createElement('div'); tip.className = 'vr-tip'; document.body.appendChild(tip); }
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

/* ===== admin.html ===== */
(function () {
  var esc = UI.esc;
  var TABS = [['overview', 'Overview', 'grid'], ['robots', 'Robots', 'robot'], ['feedback', 'Feedback', 'inbox'], ['users', 'Users', 'users'], ['demo', 'Demo data', 'database']];

  UI.page('admin', { title: 'Admin', auth: 'admin' }, function (view, ctx) {
    var tab = TABS.some(function (t) { return t[0] === ctx.args[0]; }) ? ctx.args[0] : 'overview';
    var fbFilter = 'new';
    view.innerHTML = '<div class="ui-wrap"><div class="ui-page-head"><div><h1>Admin</h1><p class="muted">Only admins see this page.</p></div></div>' +
      '<nav class="ui-tabs">' + TABS.map(function (t) {
        return '<a href="#admin/' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '">' + UI.icon(t[2]) + t[1] + '</a>';
      }).join('') + '</nav><div data-body><div class="ui-skel"></div></div></div>';
    var body = view.querySelector('[data-body]');

    function overview() {
      return UI.api('admin_overview').then(function (d) {
        var stat = function (n, label, go) { return '<a class="ui-card ui-stat" href="#admin/' + go + '" style="text-decoration:none;color:inherit"><b>' + n + '</b><span>' + label + '</span></a>'; };
        body.innerHTML = '<div class="ad-stats">' + stat(d.users, 'people signed up', 'users') + stat(d.admins, UI.plural(d.admins, 'admin').replace(/^\d+ /, ''), 'users') +
          stat(d.feedback_new, 'new feedback', 'feedback') + stat(d.sites, 'sites watched (real)', 'robots') + stat(d.open_incidents, 'open incidents (real)', 'robots') + '</div>' +
          '<p class="muted small" style="margin-top:18px">Demo data is <b>' + esc(d.demo.state) + '</b> (' + d.demo.counts.users + ' demo people). Manage it in the Demo data tab.</p>';
      });
    }

    function feedback() {
      return UI.api('list_feedback', null).then(function (d) {
        var items = d.items.filter(function (i) { return fbFilter === 'all' || i.status === fbFilter; });
        body.innerHTML = '<div class="ui-row" style="margin-bottom:16px"><div class="ui-seg">' + [['new', 'New'], ['read', 'Read'], ['done', 'Done'], ['all', 'All']].map(function (f) {
          var n = f[0] === 'all' ? d.items.length : d.counts[f[0]];
          return '<button data-filter="' + f[0] + '" class="' + (fbFilter === f[0] ? 'on' : '') + '">' + f[1] + ' (' + n + ')</button>';
        }).join('') + '</div></div>' +
          (items.length ? '<div class="ad-fb">' + items.map(function (i) {
            var c = i.context || {};
            return '<div class="ui-item" data-id="' + esc(i.id) + '"><div class="meta"><span class="ui-badge ' + (i.kind === 'bug' ? 'bad' : i.kind === 'idea' ? 'brand' : '') + '">' + esc(i.kind_label) + '</span>' +
              '<b>' + esc(i.name) + '</b>' + (i.email ? '<a href="mailto:' + esc(i.email) + '">' + esc(i.email) + '</a>' : '') + '<span>' + esc(UI.fmtDateTime(i.created)) + '</span></div>' +
              '<p class="msg">' + esc(i.message) + '</p>' +
              '<div class="ctx">' + esc([c.page, c.screen, c.theme, c.browser].filter(Boolean).join(' · ')) + '</div>' +
              '<textarea data-note placeholder="Private note (only admins see it)">' + esc(i.note) + '</textarea>' +
              '<div class="ui-row" style="margin-top:10px">' + ['new', 'read', 'done'].map(function (s) {
                return '<button class="ui-btn sm' + (i.status === s ? ' primary' : '') + '" data-status="' + s + '">' + s[0].toUpperCase() + s.slice(1) + '</button>';
              }).join('') + '<span class="ui-spacer"></span><button class="ui-btn sm danger" data-del-fb>' + UI.icon('trash') + 'Delete</button></div></div>';
          }).join('') + '</div>'
            : '<div class="ui-empty">' + UI.icon('inbox') + '<h3>No ' + (fbFilter === 'all' ? '' : fbFilter + ' ') + 'messages</h3><p>New feedback goes to Prepsto (prepsto.com). Older messages and requests from the app show up here.</p></div>');
      });
    }

    function users(query) {
      return UI.api('list_users', query || null).then(function (d) {
        body.innerHTML = '<form class="ui-row" data-search style="margin-bottom:14px"><input type="search" name="q" placeholder="Search by name or email" value="' + esc(query || '') + '" style="max-width:360px">' +
          '<button class="ui-btn" type="submit">' + UI.icon('search') + 'Search</button><span class="muted small">' + UI.plural(d.total, 'person', 'people') + '</span></form>' +
          '<table class="ad-users"><thead><tr><th>Name</th><th>Email</th><th>Joined</th><th>Admin</th><th>Active</th></tr></thead><tbody>' +
          d.users.map(function (u) {
            return '<tr data-id="' + esc(u.id) + '"><td><b>' + esc(u.name) + '</b></td><td class="email">' + esc(u.email) + '</td><td class="joined muted">' + esc(UI.fmtDate(u.joined)) + '</td>' +
              '<td><label class="ui-check"><input type="checkbox" data-admin' + (u.is_admin ? ' checked' : '') + '> Admin</label></td>' +
              '<td><label class="ui-check"><input type="checkbox" data-enabled' + (u.enabled ? ' checked' : '') + '> Active</label></td></tr>';
          }).join('') + '</tbody></table>';
      });
    }

    function demo() {
      return UI.api('admin_overview').then(function (d) {
        var c = d.demo.counts;
        body.innerHTML = '<div class="ui-card ui-narrow" style="margin:0"><h3>Demo data</h3>' +
          '<p class="muted">Example people and content, so the app never looks empty for the first visitors. Demo rows are flagged, so removing them never touches real data. Once removed, it stays removed until you load it again.</p>' +
          '<p>Status: <b>' + esc(d.demo.state) + '</b> · ' + Object.keys(c).map(function (k) { return c[k] + ' ' + esc(k); }).join(', ') + '</p>' +
          '<div class="ui-row"><button class="ui-btn primary" data-demo="load">' + UI.icon('refresh') + (d.demo.state === 'loaded' ? 'Reload demo data' : 'Load demo data') + '</button>' +
          '<button class="ui-btn danger" data-demo="remove">' + UI.icon('trash') + 'Remove demo data</button></div></div>';
      });
    }

    function robots() {
      return UI.api('admin_bots').then(function (d) {
        var st = d.stats;
        body.innerHTML = '<div class="ad-stats">' + [[st.sites, 'sites (all)'], [st.heartbeats, 'heartbeats'], [VR.num(st.checks_today), 'checks today'], [VR.num(st.views_today), 'page views today'], [st.open_incidents, 'open incidents']].map(function (x) {
          return '<div class="ui-card ui-stat"><b>' + x[0] + '</b><span>' + x[1] + '</span></div>'; }).join('') + '</div>' +
          '<div class="ui-card" style="margin-top:16px"><div class="ui-row between"><div><h3 style="margin:0">' + (d.paused ? 'All robots are paused' : 'Robots are running') + '</h3>' +
          '<p class="muted small" style="margin:4px 0 0">Anvil Scheduled Tasks call bot_tick every 5 minutes and bot_daily at 06:00 UTC. Pausing stops both (the beacon keeps listening).</p></div>' +
          '<button class="ui-btn ' + (d.paused ? 'primary' : 'danger') + '" data-bots-pause="' + (d.paused ? '0' : '1') + '">' + UI.icon(d.paused ? 'play' : 'pause') + (d.paused ? 'Resume robots' : 'Pause all robots') + '</button></div>' +
          '<div class="ui-row" style="margin-top:14px">' + d.bots.filter(function (b) { return b.runnable; }).map(function (b) {
            return '<button class="ui-btn sm" data-run-bot="' + esc(b.key) + '">' + UI.icon('play') + 'Run ' + esc(b.name) + '</button>'; }).join('') + '</div></div>' +
          '<h3 style="margin:22px 0 10px">Recent runs</h3>' + (d.runs.length ? '<table class="ad-users"><thead><tr><th>When (UTC)</th><th>Robot</th><th>Took</th><th>Result</th></tr></thead><tbody>' +
          d.runs.map(function (r) { return '<tr><td class="mono small">' + VR.stamp(r.at) + '</td><td>' + esc(r.bot) + '</td><td class="mono small">' + VR.ms(r.ms) + '</td><td' + (r.ok ? '' : ' style="color:var(--c-bad)"') + '>' + esc(r.summary) + '</td></tr>'; }).join('') +
          '</tbody></table>' : '<p class="muted">No runs yet. Check that the Scheduled Tasks exist in the Anvil editor.</p>');
      });
    }

    var DRAW = { overview: overview, robots: robots, feedback: feedback, users: users, demo: demo };

    view.addEventListener('click', function (e) {
      var f = e.target.closest('[data-filter]');
      if (f) { fbFilter = f.getAttribute('data-filter'); feedback(); return; }
      var st = e.target.closest('[data-status]');
      if (st) {
        var card = st.closest('[data-id]');
        UI.api('set_feedback_status', card.getAttribute('data-id'), st.getAttribute('data-status'), card.querySelector('[data-note]').value).then(function () { UI.toast('Saved', 'ok'); feedback(); });
        return;
      }
      var del = e.target.closest('[data-del-fb]');
      if (del) {
        UI.confirm({ title: 'Delete this message?', ok: 'Delete', danger: true }).then(function (yes) {
          if (yes) UI.api('delete_feedback', del.closest('[data-id]').getAttribute('data-id')).then(feedback);
        });
        return;
      }
      var rb = e.target.closest('[data-run-bot]');
      if (rb) { UI.busy(rb, UI.api('admin_run_bot', rb.getAttribute('data-run-bot'))).then(function () { UI.toast('Started: results appear below in a moment', 'ok'); setTimeout(robots, 1500); }); return; }
      var bp = e.target.closest('[data-bots-pause]');
      if (bp) { UI.busy(bp, UI.api('admin_set_bots_paused', bp.getAttribute('data-bots-pause') === '1')).then(function () { UI.toast('Saved', 'ok'); robots(); }); return; }
      var dm = e.target.closest('[data-demo]');
      if (dm) {
        var load = dm.getAttribute('data-demo') === 'load';
        UI.confirm({ title: load ? 'Load the demo data?' : 'Remove the demo data?', text: load ? 'Demo people and content are added (any old demo rows are replaced).' : 'Every demo row is deleted. Real data stays.', ok: load ? 'Load' : 'Remove', danger: !load })
          .then(function (yes) { if (yes) UI.busy(dm, UI.api(load ? 'demo_load' : 'demo_remove')).then(function () { UI.toast('Done', 'ok'); demo(); }); });
      }
    });
    view.addEventListener('change', function (e) {
      var row = e.target.closest('tr[data-id]');
      if (!row) return;
      var id = row.getAttribute('data-id'), box = e.target;
      var fn = box.hasAttribute('data-admin') ? 'set_admin' : box.hasAttribute('data-enabled') ? 'set_enabled' : null;
      if (fn) UI.api(fn, id, box.checked).then(function () { UI.toast('Saved', 'ok'); }, function (err) { box.checked = !box.checked; UI.toast(err.message, 'error'); });
    });
    view.addEventListener('submit', function (e) {
      if (e.target.matches('[data-search]')) { e.preventDefault(); users(UI.formData(e.target).q); }
    });
    return DRAW[tab]();
  });
})();

/* ===== auth.html ===== */
(function () {
  var esc = UI.esc;
  function pw(name, auto) {
    return '<div class="au-pw"><input type="password" name="' + name + '" autocomplete="' + auto + '" required minlength="8">' +
      '<button type="button" data-show>Show</button></div>';
  }
  UI.page('auth', { title: 'Sign in', auth: 'guest' }, function (view, ctx) {
    var mode = ['signup', 'reset'].indexOf(ctx.args[0]) >= 0 ? ctx.args[0] : 'login';
    function draw(msg, isErr) {
      var heading = { login: 'Back to the console', signup: 'Put robots on your sites', reset: 'Reset your password' }[mode];
      var sub = { login: 'Sign in to continue to ' + esc(UI.config.name) + '.', signup: 'Free while in early access. Your first check runs within a minute.',
        reset: 'We\'ll email you a link to choose a new password.' }[mode];
      view.innerHTML = '<div class="au-wrap"><div class="ui-card au-card">' +
        '<h1>' + heading + '</h1><p class="muted">' + sub + '</p>' +
        (mode !== 'reset' ? '<div class="ui-seg" role="tablist"><button type="button" data-mode="login" class="' + (mode === 'login' ? 'on' : '') + '">Sign in</button>' +
          '<button type="button" data-mode="signup" class="' + (mode === 'signup' ? 'on' : '') + '">Create account</button></div>' : '<div style="height:14px"></div>') +
        '<form class="ui-stack" data-form="' + mode + '" novalidate>' +
        (mode === 'signup' ? '<label class="ui-field"><span>Your name</span><input type="text" name="name" autocomplete="name" required maxlength="60"></label>' : '') +
        '<label class="ui-field"><span>Email</span><input type="email" name="email" autocomplete="email" required></label>' +
        (mode === 'login' ? '<label class="ui-field"><span>Password</span>' + pw('password', 'current-password') + '</label>' : '') +
        (mode === 'signup' ? '<label class="ui-field"><span>Password <em>(at least 8 characters)</em></span>' + pw('password', 'new-password') + '</label>' +
          (window.LegalKit ? '<div>' + LegalKit.consentField() + '</div>' : '') : '') +
        '<div data-msg role="alert"' + (msg ? ' class="' + (isErr ? 'ui-error' : 'ui-note') + '">' + esc(msg) : ' hidden>') + '</div>' +
        '<button class="ui-btn primary block" type="submit">' + { login: 'Sign in', signup: 'Create account', reset: 'Send the link' }[mode] + '</button></form>' +
        '<div class="au-links">' + (mode === 'login' ? '<a data-mode="reset">Forgot your password?</a>' : '<a data-mode="login">' + UI.icon('back') + ' Back to sign in</a>') +
        '<a href="#landing" data-go="landing">About ' + esc(UI.config.name) + '</a></div></div></div>';
      var first = view.querySelector('input');
      if (first && !msg) first.focus();
    }
    view.addEventListener('click', function (e) {
      var m = e.target.closest('[data-mode]');
      if (m) { e.preventDefault(); mode = m.getAttribute('data-mode'); history.replaceState(null, '', '#auth' + (mode === 'login' ? '' : '/' + mode)); draw(); return; }
      var s = e.target.closest('[data-show]');
      if (s) { var i = s.parentNode.querySelector('input'); i.type = i.type === 'password' ? 'text' : 'password'; s.textContent = i.type === 'password' ? 'Show' : 'Hide'; }
    });
    view.addEventListener('submit', function (e) {
      e.preventDefault();
      var form = e.target, v = UI.formData(form);
      var problem = !/^\S+@\S+\.\S+$/.test(v.email || '') ? 'Please enter a valid email address.'
        : mode !== 'reset' && (v.password || '').length < (mode === 'signup' ? 8 : 1) ? (mode === 'signup' ? 'Please choose a password of at least 8 characters.' : 'Please enter your password.')
        : mode === 'signup' && (v.name || '').trim().length < 2 ? 'Please tell us your name.' : null;
      if (problem) { say(problem, true); return; }
      if (mode === 'signup' && window.LegalKit && !LegalKit.consentChecked(form)) return;  // the kit shows its own message
      UI.busy(form.querySelector('[type=submit]'), UI.auth(mode, v)).then(function (r) {
        if (mode === 'reset' || (r && !r.me)) { mode = 'login'; draw(r && r.message, false); restore({ email: v.email }); }
        else UI.toast(mode === 'signup' ? 'Welcome to ' + UI.config.name + '!' : 'Welcome back!', 'ok');
      }, function (err) { say(err.message, true); });
    });
    function say(msg, isErr) {
      var box = view.querySelector('[data-msg]');
      box.className = isErr ? 'ui-error' : 'ui-note'; box.textContent = msg; box.hidden = false;
    }
    function restore(v) {
      ['name', 'email'].forEach(function (k) { var i = view.querySelector('[name=' + k + ']'); if (i && v[k]) i.value = v[k]; });
    }
    draw();
  });
})();

/* ===== bots.html ===== */
(function () {
  var esc = UI.esc;
  var ACT = { email: ['mail', 'Email'], webhook: ['link', 'Webhook'], recheck: ['refresh', 'Recheck'] };
  var PERIODS = [[5, '5 min'], [15, '15 min'], [30, '30 min'], [60, '1 hour'], [180, '3 hours'], [360, '6 hours'], [720, '12 hours'], [1440, '1 day'], [10080, '1 week']];

  function actChip(a) {
    var label = a.type === 'email' ? (a.to || 'my alert email') : a.type === 'webhook' ? a.url.replace(/^https:\/\//, '') : 'second robot';
    return '<span class="bt-act" title="' + esc(label) + '">' + UI.icon(ACT[a.type][0]) + esc(ACT[a.type][1]) + ': ' + esc(label) + '</span>';
  }

  function playbookForm(d, pb) {
    pb = pb || { name: '', trigger: 'down', site_id: null, actions: [{ type: 'email', to: '' }], enabled: true };
    var has = function (t) { return pb.actions.filter(function (a) { return a.type === t; })[0]; };
    var em = has('email'), wh = has('webhook');
    return '<h2>' + (pb.id ? 'Edit playbook' : 'New playbook') + '</h2><p class="muted">When this happens, the robot does that, day or night.</p>' +
      '<form class="ui-stack" data-pbform>' +
      '<label class="ui-field"><span>Name</span><input type="text" name="name" maxlength="80" required value="' + esc(pb.name) + '" placeholder="Page the on-call"></label>' +
      '<div class="ui-grid two" style="gap:12px"><label class="ui-field"><span>When</span><select name="trigger">' + d.triggers.map(function (t) {
        return '<option value="' + t.key + '"' + (t.key === pb.trigger ? ' selected' : '') + '>' + esc(t.label) + '</option>';
      }).join('') + '</select></label>' +
      '<label class="ui-field"><span>On</span><select name="site_id"><option value="">Any site</option>' + d.sites.map(function (s) {
        return '<option value="' + esc(s.id) + '"' + (s.id === pb.site_id ? ' selected' : '') + '>' + esc(s.name) + '</option>';
      }).join('') + '</select></label></div>' +
      '<div class="ui-field"><span>The robot will</span><div class="pb-acts">' +
      '<div class="pb-act"><label class="ui-check"><input type="checkbox" name="a_email"' + (em ? ' checked' : '') + '> ' + UI.icon('mail') + 'Send an email</label>' +
        '<input type="email" name="email_to" value="' + esc(em ? em.to : '') + '" placeholder="Blank = my alert address" aria-label="Email to"></div>' +
      '<div class="pb-act"><label class="ui-check"><input type="checkbox" name="a_webhook"' + (wh ? ' checked' : '') + '> ' + UI.icon('link') + 'Call a webhook (Slack, Teams, Discord, Zapier…)</label>' +
        '<input type="text" name="webhook_url" value="' + esc(wh ? wh.url : '') + '" placeholder="https://hooks.slack.com/services/…" aria-label="Webhook address"></div>' +
      '<div class="pb-act"><label class="ui-check"><input type="checkbox" name="a_recheck"' + (has('recheck') ? ' checked' : '') + '> ' + UI.icon('refresh') + 'Recheck with a second robot and note the result on the incident</label></div>' +
      '</div></div>' +
      '<div class="ui-row end"><button type="button" class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn primary" type="submit">' + UI.icon('check') + 'Save playbook</button></div></form>';
  }

  function hbForm(hb) {
    hb = hb || { name: '', period_min: 1440, grace_min: 30 };
    return '<h2>' + (hb.id ? 'Edit heartbeat' : 'New heartbeat') + '</h2><p class="muted">For things that should happen on a schedule: backups, cron jobs, imports. ' +
      'They call a URL when they finish; if the call doesn\'t come, the watchdog opens an incident.</p>' +
      '<form class="ui-stack" data-hbform><label class="ui-field"><span>Name</span><input type="text" name="name" maxlength="60" required value="' + esc(hb.name) + '" placeholder="Nightly database backup"></label>' +
      '<div class="ui-grid two" style="gap:12px"><label class="ui-field"><span>Checks in every</span><select name="period_min">' + PERIODS.map(function (p) {
        return '<option value="' + p[0] + '"' + (p[0] === hb.period_min ? ' selected' : '') + '>' + p[1] + '</option>';
      }).join('') + '</select></label>' +
      '<label class="ui-field"><span>Grace time (minutes)</span><input type="number" name="grace_min" min="0" max="1440" value="' + hb.grace_min + '"></label></div>' +
      '<div class="ui-row end"><button type="button" class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn primary" type="submit">' + UI.icon('check') + 'Save</button></div></form>';
  }

  UI.page('bots', { title: 'Robots', nav: 'Robots', icon: 'robot', auth: 'user', order: 30 }, function (view, ctx) {
    var d = null;
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:420px"></div></div>';

    function draw() {
      var mine = d.mode === 'mine';
      var robots = '<div class="bt-robots">' + d.bots.map(function (b) {
        if (b.key === 'beacon') b.fleet = b.last_beat ? 'last page view ' + UI.ago(b.last_beat) : 'no snippet installed yet';
        var last = b.key === 'beacon' ? 'listening' : b.last ? UI.ago(b.last.at) + ' · ' + VR.ms(b.last.ms) : 'not run yet';
        return '<div class="bt-robot"><header>' + UI.icon(b.icon) + '<div><h3>' + esc(b.name) + '</h3><code>' + esc(b.cron) + '</code></div></header>' +
          '<p>' + esc(b.does) + '</p><footer><span>last: <b>' + esc(last) + '</b></span><span>' + esc(b.next ? 'next ' + VR.until(b.next) : b.fleet) + '</span></footer></div>';
      }).join('') + '</div>';
      var pbs = d.playbooks.length ? d.playbooks.map(function (p) {
        return '<div class="bt-pb' + (p.enabled ? '' : ' off') + '" data-pb="' + esc(p.id) + '">' +
          '<label class="bt-switch" title="On / off"><input type="checkbox" data-pb-toggle' + (p.enabled ? ' checked' : '') + (p.can_edit ? '' : ' disabled') + ' aria-label="Playbook on"><span></span></label>' +
          '<div style="min-width:0"><h3>' + esc(p.name) + (p.demo ? ' <span class="ui-badge">Sample</span>' : '') + '</h3>' +
          '<div class="bt-flow"><span class="if">IF</span><span class="ui-badge brand">' + esc(p.trigger_label) + '</span><span class="if">ON</span><span class="ui-badge">' + esc(p.site_name) + '</span>' +
          '<span class="arrow">→</span>' + p.actions.map(actChip).join('') + '</div>' +
          '<div class="meta">fired ' + p.fired + '×' + (p.last_fired ? ' · last ' + UI.ago(p.last_fired) : '') + '</div></div>' +
          (p.can_edit ? '<div class="ui-row"><button class="ui-btn sm" data-pb-test>' + UI.icon('send') + 'Test</button><button class="ui-btn sm" data-pb-edit>' + UI.icon('edit') + 'Edit</button>' +
            '<button class="ui-btn sm ghost icon" data-pb-del aria-label="Delete">' + UI.icon('trash') + '</button></div>' : '<span></span>') + '</div>';
      }).join('') : '<div class="ui-empty">' + UI.icon('zap') + '<h3>No playbooks yet</h3><p>Tell the robots what to do when something breaks.</p></div>';
      var hbs = d.heartbeats.length ? d.heartbeats.map(function (h) {
        var st = h.status === 'late' ? 'down' : h.status === 'up' ? 'up' : h.status === 'paused' ? 'paused' : 'pending';
        var url = h.token ? d.ping_base + h.token : null;
        return '<div class="bt-hb" data-hb="' + esc(h.id) + '">' + VR.led(st) + '<div style="min-width:0"><h3>' + esc(h.name) + (h.demo ? ' <span class="ui-badge">Sample</span>' : '') + '</h3>' +
          '<div class="meta">every ' + esc(h.every) + ' (+' + h.grace_min + ' min grace) · ' + (h.last_ping ? 'last ping ' + UI.ago(h.last_ping) : 'never pinged') +
          (h.status === 'late' ? ' · <span style="color:var(--c-bad)">LATE</span>' : h.status === 'up' ? ' · next due ' + VR.until(h.next_due) : '') + ' · ' + VR.num(h.pings) + ' pings</div></div>' +
          (h.can_edit ? '<div class="ui-row"><button class="ui-btn sm" data-hb-ping>' + UI.icon('send') + 'Test ping</button><button class="ui-btn sm" data-hb-pause>' + UI.icon(h.status === 'paused' ? 'play' : 'pause') + (h.status === 'paused' ? 'Resume' : 'Pause') + '</button>' +
            '<button class="ui-btn sm ghost icon" data-hb-del aria-label="Delete">' + UI.icon('trash') + '</button></div>' : '<span></span>') +
          (url ? '<div class="url"><code title="' + esc(url) + '">curl -fsS ' + esc(url) + '</code><button class="ui-btn sm" data-copy-hb="' + esc(url) + '">' + UI.icon('copy') + 'Copy</button></div>' : '') + '</div>';
      }).join('') : '<div class="ui-empty">' + UI.icon('heart') + '<h3>No heartbeats yet</h3><p>Add one for your backups or cron jobs: they call a URL when they run, and the watchdog notices when they don\'t.</p></div>';
      var log = d.log.length ? '<div style="overflow:auto;border:1px solid var(--c-line);border-radius:var(--radius)"><table class="bt-log"><thead><tr><th>When (UTC)</th><th class="hide-sm">Playbook</th><th>About</th><th>Did</th><th>Result</th></tr></thead><tbody>' +
        d.log.map(function (l) {
          return '<tr><td class="mono">' + VR.stamp(l.at) + '</td><td class="hide-sm">' + esc(l.playbook) + '</td><td>' + esc(l.subject) + '</td><td class="did">' + UI.icon(ACT[l.action] ? ACT[l.action][0] : 'zap') + ' ' + esc(l.action) +
            '</td><td class="res' + (l.ok ? '' : ' bad') + '">' + esc(l.result) + '</td></tr>';
        }).join('') + '</tbody></table></div>' : '<p class="muted">Nothing yet. Every email, webhook and recheck the robots do shows up here.</p>';
      view.innerHTML = '<div class="ui-wrap"><div class="ui-page-head"><div><div class="eyebrow">' + (mine ? 'Robotic process automation' : 'Sample fleet') + '</div><h1>Robots</h1>' +
        '<p class="muted">The routine work, automated: checks around the clock, and playbooks that act the moment something breaks.</p></div></div>' +
        (d.paused ? '<p class="ui-error">' + UI.icon('pause') + ' An admin has paused all robots for maintenance. Checks resume when they\'re switched back on.</p>' : '') +
        (!mine ? '<div class="vr-sample"><span>' + UI.icon('eye') + ' Playbooks and heartbeats below belong to the sample fleet. Add a site to make your own.</span><button class="ui-btn primary sm" data-add>' + UI.icon('plus') + 'Add a site</button></div>' : '') +
        robots +
        '<section class="bt-sec"><div class="ui-row between"><div><h2>Playbooks</h2><p class="muted small" style="margin:2px 0 0">If this happens → the robot does that.</p></div>' +
        (mine ? '<button class="ui-btn primary" data-pb-new>' + UI.icon('plus') + 'New playbook</button>' : '') + '</div>' + pbs + '</section>' +
        '<section class="bt-sec"><div class="ui-row between"><div><h2>Cron heartbeats</h2><p class="muted small" style="margin:2px 0 0">A dead man\'s switch for backups and scheduled jobs.</p></div>' +
        '<button class="ui-btn" data-hb-new>' + UI.icon('plus') + 'New heartbeat</button></div>' + hbs + '</section>' +
        '<section class="bt-sec"><div class="ui-row"><h2>What the robots did</h2></div>' + log + '</section></div>';
    }
    function load() { return UI.api('get_bots').then(function (r) { d = r; draw(); }); }

    function savePlaybook(m, id) {
      var f = m.el.querySelector('[data-pbform]');
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        var v = UI.formData(f), actions = [];
        if (v.a_email) actions.push({ type: 'email', to: v.email_to });
        if (v.a_webhook) actions.push({ type: 'webhook', url: v.webhook_url });
        if (v.a_recheck) actions.push({ type: 'recheck' });
        UI.busy(f.querySelector('[type=submit]'), UI.api('save_playbook', { id: id, name: v.name, trigger: v.trigger, site_id: v.site_id || null, actions: actions }))
          .then(function () { m.close(); UI.toast('Playbook saved', 'ok'); load(); });
      });
    }
    function saveHeartbeat(m, id) {
      var f = m.el.querySelector('[data-hbform]');
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        var v = UI.formData(f);
        UI.busy(f.querySelector('[type=submit]'), UI.api('save_heartbeat', { id: id, name: v.name, period_min: +v.period_min, grace_min: +v.grace_min }))
          .then(function () { m.close(); UI.toast('Heartbeat ready: copy its URL into your job', 'ok'); load(); });
      });
    }

    view.addEventListener('click', function (e) {
      var b, row, id;
      if (e.target.closest('[data-add]')) { VR.addSite(); return; }
      if (e.target.closest('[data-pb-new]')) { savePlaybook(UI.modal(playbookForm(d), { wide: true }), null); return; }
      if (e.target.closest('[data-hb-new]')) { saveHeartbeat(UI.modal(hbForm()), null); return; }
      if ((b = e.target.closest('[data-copy-hb]'))) { VR.copy('curl -fsS ' + b.getAttribute('data-copy-hb'), 'Command copied'); return; }
      if ((row = e.target.closest('[data-pb]'))) {
        id = row.getAttribute('data-pb');
        var pb = d.playbooks.filter(function (p) { return p.id === id; })[0];
        if (e.target.closest('[data-pb-edit]')) { savePlaybook(UI.modal(playbookForm(d, pb), { wide: true }), id); return; }
        if ((b = e.target.closest('[data-pb-test]'))) {
          UI.busy(b, UI.api('test_playbook', id)).then(function (r) {
            var bad = r.results.filter(function (x) { return !x.ok; });
            UI.toast(bad.length ? bad[0].result : 'Test sent: ' + r.results.map(function (x) { return x.result; }).join(', '), bad.length ? 'error' : 'ok');
            load();
          });
          return;
        }
        if (e.target.closest('[data-pb-del]')) {
          UI.confirm({ title: 'Delete “' + pb.name + '”?', ok: 'Delete', danger: true }).then(function (yes) { if (yes) UI.api('delete_playbook', id).then(load); });
        }
        return;
      }
      if ((row = e.target.closest('[data-hb]'))) {
        id = row.getAttribute('data-hb');
        var hb = d.heartbeats.filter(function (h) { return h.id === id; })[0];
        if ((b = e.target.closest('[data-hb-ping]'))) { UI.busy(b, UI.api('ping_heartbeat_now', id)).then(function () { UI.toast('Ping received', 'ok'); load(); }); return; }
        if ((b = e.target.closest('[data-hb-pause]'))) { UI.busy(b, UI.api('set_heartbeat_paused', id, hb.status !== 'paused')).then(load); return; }
        if (e.target.closest('[data-hb-del]')) {
          UI.confirm({ title: 'Delete “' + hb.name + '”?', text: 'Jobs still calling its URL will get "unknown token".', ok: 'Delete', danger: true }).then(function (yes) { if (yes) UI.api('delete_heartbeat', id).then(load); });
        }
      }
    });
    view.addEventListener('change', function (e) {
      if (!e.target.matches('[data-pb-toggle]')) return;
      var box = e.target, id = box.closest('[data-pb]').getAttribute('data-pb');
      UI.api('set_playbook_enabled', id, box.checked).then(function () { UI.toast(box.checked ? 'Playbook on' : 'Playbook off', 'ok'); load(); },
        function (err) { box.checked = !box.checked; UI.toast(err.message, 'error'); });
    });
    return load();
  });
})();

/* ===== home.html ===== */
(function () {
  var esc = UI.esc;

  /* The "Add a site" dialog (used by the console, empty states and the bots page). */
  VR.addSite = function () {
    var opts = [5, 15, 30, 60, 180, 360, 720, 1440];
    var m = UI.modal('<h2>Watch a new site</h2><p class="muted">No code needed for this part: the robots load the page like a visitor and read what the server says. ' +
      'The visitor beacon is optional and comes next.</p>' +
      '<form class="ui-stack" data-addsite>' +
      '<label class="ui-field"><span>Address</span><input type="text" name="url" placeholder="https://www.example.com" required autocomplete="off" inputmode="url"></label>' +
      '<label class="ui-field"><span>Name <em>(optional)</em></span><input type="text" name="name" maxlength="60" placeholder="Company website"></label>' +
      '<label class="ui-field"><span>Check every</span><select name="interval_min">' + opts.map(function (o) {
        return '<option value="' + o + '"' + (o === 60 ? ' selected' : '') + '>' + VR.every(o) + '</option>';
      }).join('') + '</select><div class="as-int" data-perday>24 check-ins a day</div></label>' +
      '<details class="as-adv"><summary>More checks (keyword, status, speed, tags)</summary><div class="ui-stack">' +
      '<label class="ui-field"><span>Text that must be on the page <em>(catches blank or hacked pages)</em></span><input type="text" name="keyword" maxlength="80" placeholder="e.g. Add to cart"></label>' +
      '<div class="as-grid"><label class="ui-field"><span>Expected status <em>(blank = any 2xx/3xx)</em></span><input type="number" name="expect_status" min="100" max="599" placeholder="200"></label>' +
      '<label class="ui-field"><span>Slow above (ms)</span><input type="number" name="slow_ms" min="300" max="30000" step="100" value="3000"></label></div>' +
      '<label class="ui-field"><span>Tags <em>(comma separated)</em></span><input type="text" name="tags" placeholder="client-a, shop"></label>' +
      '</div></details>' +
      '<div class="ui-row end"><button type="button" class="ui-btn ghost" data-close>Cancel</button><button class="ui-btn primary" type="submit">' + UI.icon('robot') + 'Start watching</button></div></form>');
    var f = m.el.querySelector('[data-addsite]');
    f.interval_min.addEventListener('change', function () {
      var n = VR.perDay(+f.interval_min.value);
      m.el.querySelector('[data-perday]').textContent = n === 1 ? '1 check-in a day' : n + ' check-ins a day';
    });
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = UI.formData(f), btn = f.querySelector('[type=submit]');
      UI.busy(btn, UI.api('add_site', v).then(function (r) {
        return UI.apiQuiet('check_now', r.site_id).then(function (c) { return [r.site_id, c.result]; }, function () { return [r.site_id, null]; });
      })).then(function (x) {
        m.close();
        var res = x[1];
        if (res) UI.toast(res.state === 'fail' ? 'First check failed: ' + res.problem : 'First check: HTTP ' + res.code + ' in ' + VR.ms(res.ms), res.state === 'fail' ? 'error' : 'ok');
        UI.go('site', x[0], 'install');
      });
    });
  };

  function kpi(label, icon, value, cls, sub) {
    return '<div class="cn-kpi"><small>' + UI.icon(icon) + esc(label) + '</small><b class="' + (cls || '') + '">' + value + '</b>' + (sub ? '<em>' + sub + '</em>' : '') + '</div>';
  }

  function row(s) {
    var resp = s.status === 'down' || s.status === 'retrying' ? '<span class="mono" style="color:var(--c-bad)">' + esc(s.last_code || 'ERR') + '</span>'
      : '<span class="mono">' + VR.ms(s.avg_ms) + '</span>';
    return '<a class="cn-row' + (s.paused ? ' cn-paused' : '') + '" href="#site/' + esc(s.id) + '" data-site="' + esc(s.id) + '">' +
      '<div class="cn-name">' + VR.led(s.status) + '<div><b>' + esc(s.name) + '</b><small>' + esc(s.host) +
        (s.status === 'down' || s.status === 'retrying' ? ' · ' + esc(s.last_error || 'down') : s.paused ? ' · paused' : '') + '</small></div></div>' +
      '<div class="cn-strip"><span class="cn-label">Last 24 h</span>' + VR.cells(s.cells) + '</div>' +
      '<div><span class="cn-label">30 days</span><span class="mono">' + VR.pct(s.up30) + '</span></div>' +
      '<div class="cn-resp"><div><span class="cn-label">Response</span>' + resp + '</div>' + VR.spark(s.spark) + '</div>' +
      '<div><span class="cn-label">Visitors</span><span class="mono">' + (s.beacon === 'none' ? '<span class="faint">—</span>' : VR.num(s.visitors)) + '</span></div>' +
      '<div class="cn-ssl">' + (s.ssl_error ? '<span class="ui-badge bad">ERR</span>' : VR.daysTag(s.ssl_days)) + '</div>' +
      '<div class="cn-bcn"><span class="cn-beacon ' + esc(s.beacon) + '">' + ({ live: '● live', idle: 'idle', quiet: 'silent', none: 'none' })[s.beacon] + '</span></div></a>';
  }

  UI.page('home', { title: 'Console', nav: 'Console', icon: 'pulse', auth: 'user', order: 10 }, function (view, ctx) {
    var sample = ctx.args[0] === 'sample' ? true : null, tag = 'all', query = '', data = null, timer = null;
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:90px;margin-bottom:16px"></div><div class="ui-skel" style="height:380px"></div></div>';

    function draw() {
      var d = data, t = d.totals;
      var list = d.sites.filter(function (s) {
        return (tag === 'all' || s.tags.indexOf(tag) >= 0) && (!query || (s.name + ' ' + s.host).toLowerCase().indexOf(query) >= 0);
      });
      var mine = d.mode === 'mine';
      var head = '<div class="ui-page-head"><div><div class="eyebrow">' + (mine ? 'Your fleet' : 'Sample fleet') + '</div><h1>Console</h1>' +
        '<p class="muted mono small">' + UI.plural(t.sites, 'site') + ' · ' + VR.num(t.checks24) + ' robot checks in 24 h · ' + VR.pct(t.up24) + ' passed</p></div>' +
        '<div class="ui-row"><button class="ui-btn" data-refresh aria-label="Refresh">' + UI.icon('refresh') + '<span>Refresh</span></button>' +
        '<button class="ui-btn primary" data-add>' + UI.icon('plus') + 'Add site</button></div></div>';
      var banner = mine ? '' : '<div class="vr-sample"><div class="ui-row">' + UI.icon('eye') + '<span><b>You\'re looking at a sample fleet</b> (' + esc(d.sample_owner || 'demo') +
        '\'s agency, fictional sites). It\'s read-only and the robots keep it live. Add your own site and this becomes your console.</span></div>' +
        '<div class="ui-row">' + (d.has_own ? '<a class="ui-btn sm" href="#home" data-go="home">Back to my fleet</a>' : '') +
        '<button class="ui-btn primary sm" data-add>' + UI.icon('plus') + 'Add my first site</button></div></div>';
      var kpis = '<div class="cn-kpis">' +
        kpi('Sites up', 'server', t.up + '<span class="faint">/' + (t.sites - t.paused) + '</span>', t.down ? 'bad' : 'good', t.down ? t.down + ' down' + (t.slow ? ', ' + t.slow + ' slow' : '') : t.slow ? t.slow + ' slow' : 'all answering') +
        kpi('Open incidents', 'bell', t.incidents, t.critical ? 'bad' : t.incidents ? 'warn' : 'good', t.critical ? t.critical + ' critical' : 'nothing urgent') +
        kpi('Visitors today', 'eye', VR.num(t.visitors), '', VR.num(t.views) + ' page views') +
        kpi('Avg response', 'gauge', VR.ms(t.avg_ms), '', 'last 24 h') +
        kpi('Certificates', 'lock', t.certs_soon ? t.certs_soon : 'OK', t.certs_soon ? 'warn' : 'good', t.certs_soon ? 'expiring ≤ 14 days' : 'none expiring soon') + '</div>';
      var tools = '<div class="cn-tools"><input type="search" data-q placeholder="Filter sites" value="' + esc(query) + '" aria-label="Filter sites">' +
        ['all'].concat(d.tags).map(function (g) { return '<button class="cn-chip' + (tag === g ? ' on' : '') + '" data-tag="' + esc(g) + '">' + (g === 'all' ? 'all' : '#' + esc(g)) + '</button>'; }).join('') + '</div>';
      var table = d.sites.length ? '<div class="cn-table" role="table" aria-label="Sites">' +
        '<div class="cn-row head"><span>Site</span><span>Last 24 h (hourly)</span><span>30 d up</span><span>Response</span><span>Visitors</span><span>SSL</span><span>Beacon</span></div>' +
        (list.length ? list.map(row).join('') : '<div class="cn-row"><span class="muted">No site matches that filter.</span></div>') + '</div>'
        : '<div class="ui-empty">' + UI.icon('server') + '<h3>No sites yet</h3><p>Add a website and the robots start checking it within minutes.</p><button class="ui-btn primary" data-add>' + UI.icon('plus') + 'Add a site</button></div>';
      var term = '<aside class="cn-term" aria-label="Robot log"><header><b>' + UI.icon('terminal') + ' Robot log</b><span>UTC</span></header><ol>' +
        (d.feed.length ? d.feed.map(function (l) {
          return '<li class="' + esc(l.level) + '"><time>' + VR.hhmm(l.at) + '</time><i></i><span><em>' + esc(l.bot) + '</em> ' + esc(l.text) + '</span></li>';
        }).join('') : '<li><time></time><i></i><span><em>idle</em> Waiting for the first robot run…</span></li>') +
        '<li><time></time><i style="background:none"></i><span class="cn-cursor"></span></li></ol></aside>';
      view.innerHTML = '<div class="ui-wrap">' + head + banner + kpis + '<div class="cn-main"><div>' + tools + table + VR.legend() +
        '<div class="cn-foot"><span>Updated ' + VR.hhmm(d.now) + ' UTC · refreshes every minute</span>' +
        (mine && d.can_sample ? '<a href="#home/sample" data-go="home/sample">View the sample fleet</a>' : '') + '</div></div>' + term + '</div></div>';
      VR.setOpen(mine ? t.incidents : 0);
    }

    function load(quiet) {
      return (quiet ? UI.apiQuiet : UI.api)('get_console', sample).then(function (d) { data = d; draw(); });
    }
    view.addEventListener('click', function (e) {
      if (e.target.closest('[data-add]')) { VR.addSite(); return; }
      if (e.target.closest('[data-refresh]')) { UI.busy(e.target.closest('[data-refresh]'), load()); return; }
      var tg = e.target.closest('[data-tag]');
      if (tg) { tag = tg.getAttribute('data-tag'); draw(); }
    });
    view.addEventListener('input', function (e) {
      if (!e.target.matches('[data-q]')) return;
      query = e.target.value.trim().toLowerCase();
      var pos = e.target.selectionStart;
      draw();
      var q = view.querySelector('[data-q]'); q.focus(); q.setSelectionRange(pos, pos);
    });
    timer = setInterval(function () { if (!document.hidden && !document.querySelector('.ui-modal-wrap')) load(true).catch(function () {}); }, 60000);
    return { ready: load(), destroy: function () { clearInterval(timer); } };
  });
})();

/* ===== incidents.html ===== */
(function () {
  var esc = UI.esc;
  var KIND_ICON = { down: 'server', slow: 'gauge', ssl: 'lock', domain: 'globe', silence: 'eye', jserrors: 'bug', heartbeat: 'heart' };

  function card(i) {
    var notes = i.notes || [];
    return '<article class="in-card ' + esc(i.severity) + (i.resolved ? ' resolved' : '') + '" data-id="' + esc(i.id) + '">' +
      '<div class="in-top"><div style="min-width:0"><div class="ui-row" style="gap:6px">' + VR.sev(i.severity, i.resolved) +
      '<span class="ui-badge">' + UI.icon(KIND_ICON[i.kind] || 'info') + esc(i.kind_label) + '</span>' + (i.acked && !i.resolved ? '<span class="ui-badge brand">' + UI.icon('user') + 'Acknowledged</span>' : '') +
      (i.demo ? '<span class="ui-badge">Sample</span>' : '') + '</div><h3>' + esc(i.title) + '</h3>' +
      '<div class="in-meta"><span>' + UI.icon('clock') + ' opened ' + VR.stamp(i.started) + ' UTC</span><span>' + (i.resolved ? 'lasted ' : 'open for ') + VR.dur(i.minutes) + '</span>' +
      (i.site_id ? '<a href="#site/' + esc(i.site_id) + '">' + esc(i.subject) + '</a>' : '<a href="#bots" data-go="bots">' + esc(i.subject) + '</a>') + '</div></div></div>' +
      (i.detail ? '<p class="in-detail">' + esc(i.detail) + '</p>' : '') +
      (i.resolved ? '<p class="in-res">' + UI.icon('check') + ' ' + esc(i.resolution) + ' · ' + VR.stamp(i.resolved) + ' UTC</p>' : '') +
      (notes.length ? '<ol class="in-tl">' + notes.map(function (n) {
        return '<li><b>' + esc(n.by) + '</b><time>' + VR.stamp(n.at) + '</time><p>' + esc(n.text) + '</p></li>';
      }).join('') + '</ol>' : '') +
      (i.can_edit && !i.resolved ? '<div class="in-actions">' + (i.acked ? '' : '<button class="ui-btn sm" data-ack>' + UI.icon('user') + 'I\'m on it</button>') +
        '<button class="ui-btn sm" data-resolve>' + UI.icon('check') + 'Mark resolved</button></div>' +
        '<form class="in-note" data-note><input type="text" name="text" maxlength="600" placeholder="Add a note for the timeline" aria-label="Note"><button class="ui-btn sm" type="submit">Add</button></form>' : '') +
      '</article>';
  }

  UI.page('incidents', { title: 'Incidents', nav: 'Incidents', icon: 'bell', auth: 'user', order: 20 }, function (view, ctx) {
    var filter = ['open', 'resolved', 'all'].indexOf(ctx.args[0]) >= 0 ? ctx.args[0] : 'open';
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:300px"></div></div>';
    function draw(d) {
      var crit = d.incidents.filter(function (i) { return !i.resolved && i.severity === 'critical'; }).length;
      view.innerHTML = '<div class="ui-wrap ui-narrow" style="max-width:860px"><div class="ui-page-head"><div><div class="eyebrow">' + (d.mode === 'mine' ? 'Your fleet' : 'Sample fleet') + '</div><h1>Incidents</h1>' +
        '<p class="muted">Opened by the robots when something breaks, closed by them when it recovers. Your playbooks decide who hears about it.</p></div></div>' +
        (d.mode === 'sample' ? '<div class="vr-sample"><span>' + UI.icon('eye') + ' Sample incidents from the demo fleet. Add a site to see your own.</span><button class="ui-btn primary sm" data-add>' + UI.icon('plus') + 'Add a site</button></div>' : '') +
        '<div class="in-sum"><div class="ui-seg">' + [['open', 'Open'], ['resolved', 'Resolved'], ['all', 'All']].map(function (f) {
          return '<button data-filter="' + f[0] + '" class="' + (filter === f[0] ? 'on' : '') + '">' + f[1] + (f[0] === 'open' ? ' (' + d.open + ')' : '') + '</button>';
        }).join('') + '</div>' + (filter === 'open' && crit ? '<span class="ui-badge bad">' + crit + ' critical</span>' : '') + '</div>' +
        (d.incidents.length ? '<div class="in-list">' + d.incidents.map(card).join('') + '</div>'
          : '<div class="ui-empty">' + UI.icon('check') + '<h3>' + (filter === 'open' ? 'All quiet' : 'Nothing here') + '</h3><p>' +
            (filter === 'open' ? 'No open incidents. The robots are watching.' : 'No incidents yet.') + '</p></div>') + '</div>';
      VR.setOpen(d.mode === 'mine' ? d.open : 0);
    }
    function load() { return UI.api('list_incidents', filter).then(draw); }
    view.addEventListener('click', function (e) {
      var b;
      if (e.target.closest('[data-add]')) { VR.addSite(); return; }
      if ((b = e.target.closest('[data-filter]'))) { filter = b.getAttribute('data-filter'); UI.busy(b, load()); return; }
      var cardEl = e.target.closest('[data-id]');
      if (!cardEl) return;
      var id = cardEl.getAttribute('data-id');
      if ((b = e.target.closest('[data-ack]'))) { UI.busy(b, UI.api('ack_incident', id)).then(function () { UI.toast('Acknowledged', 'ok'); load(); }); return; }
      if ((b = e.target.closest('[data-resolve]'))) {
        UI.confirm({ title: 'Mark as resolved?', text: 'If the problem is still there, the robots will open a new incident on their next check.', ok: 'Resolve' }).then(function (yes) {
          if (yes) UI.api('resolve_incident', id, '').then(function () { UI.toast('Resolved', 'ok'); load(); });
        });
      }
    });
    view.addEventListener('submit', function (e) {
      if (!e.target.matches('[data-note]')) return;
      e.preventDefault();
      var id = e.target.closest('[data-id]').getAttribute('data-id');
      UI.busy(e.target.querySelector('[type=submit]'), UI.api('add_incident_note', id, UI.formData(e.target).text)).then(load);
    });
    return load();
  });
})();

/* ===== landing.html ===== */
(function () {
  var COPY = {
    eyebrow: 'Robotic process automation for your web fleet',
    title: 'Robots that watch <em>every</em> website you run',
    lead: 'VitalRPA checks your sites around the clock: up or down, fast or slow, certificates and domains about to expire, visitors that suddenly stop. When something breaks, your playbooks act: an email, a Slack message, a second-robot recheck. Most of it needs no code at all.',
    cta: 'Start monitoring, free',
    proof: ['24 check-ins a day per site (or every 5 min)', 'No-code checks', 'Beacon under 1 KB, no cookies'],
    stepsTitle: 'From "is it up?" to "it\'s handled" in three steps',
    stepsLead: 'Start with the address. Add the beacon later, or never.',
    steps: [['01', 'Add your sites', 'Paste the address. The robots load it like a visitor every hour (or every 5 minutes) and read what the server says: status code, response time, the text that must be on the page.', 'no code'],
            ['02', 'Paste one line, if you like', 'The optional beacon adds real visitors, real page-load times and the JavaScript errors people hit. It waits until your page has loaded and weighs less than your favicon.', '&lt;script&gt; &lt; 1 KB'],
            ['03', 'Let the playbooks handle it', 'If a site goes down, the robot rechecks from a second run, emails the on-call and posts to Slack or Teams. It writes everything to the incident timeline.', 'if → then']],
    featuresTitle: 'Everything a sysadmin checks at 3 a.m.',
    featuresLead: 'Without being awake at 3 a.m.',
    features: [['pulse', 'Uptime, 24× a day', 'Hourly by default, every 5 minutes if it matters. A failure is retried before anyone is woken up.', 'no code'],
               ['search', 'Keyword check', 'Catch the page that answers "200 OK" but is blank, broken or defaced.', 'no code'],
               ['lock', 'Certificates', 'Warned 14 days before a TLS certificate expires, or the minute it\'s broken.', 'no code'],
               ['globe', 'Domain expiry', 'Read from the registry. Nobody loses a domain to an expired card again.', 'no code'],
               ['shield', 'Security headers', 'An A to F grade for HSTS, CSP, frame and referrer policies.', 'no code'],
               ['heart', 'Cron heartbeats', 'Backups and scheduled jobs call a URL. Silence opens an incident.', 'one curl'],
               ['eye', 'Real visitors & speed', 'Page views, unique visitors, load time and server response from real browsers.', 'beacon'],
               ['bug', 'JavaScript errors', 'The errors your visitors hit, grouped, counted, with the page they were on.', 'beacon'],
               ['bell', 'Silence alarm', 'Visitors stopped arriving? The site may be broken for humans only, or the snippet was removed.', 'beacon'],
               ['zap', 'Playbooks', 'If this, then that: email, webhooks for Slack, Teams, Discord or Zapier, and robot rechecks.', 'automation'],
               ['status', 'Public status page', 'A page your customers can bookmark, with 90 days of uptime per service.', 'share'],
               ['terminal', 'Incident timeline', 'Opened and closed by the robots; acknowledge, add notes, see who did what.', 'teamwork']],
    faq: [['Do I have to install anything?', 'No. Uptime, response time, keyword, certificate, domain and security-header checks all run from our servers without touching your site. The beacon is optional and only needed for visitors, page speed and JavaScript errors.'],
          ['Will the snippet slow my site down?', 'No. It\'s about 800 bytes of inline code, so there\'s no extra file to download. It does nothing until your page has finished loading, then sends one background ping with navigator.sendBeacon, which the browser handles after everything else.'],
          ['What does the beacon collect?', 'The page path, the site the visitor came from, the screen width, how long the page took to load, and up to 3 JavaScript error messages per page. No cookies, nothing stored in the browser, and it respects Do Not Track. Unique visitors are counted with a fingerprint whose secret changes every day; IP addresses are never stored.'],
          ['How often do the robots check?', 'Every site has its own rhythm: every 5, 15 or 30 minutes, hourly (24 check-ins a day, the default) or less often. While a site is down, the robots look every 5 minutes so you know the moment it\'s back.'],
          ['How will I hear about problems?', 'Through playbooks. Every new account starts with "email me when something breaks, and when it\'s fixed". Add webhooks for Slack, Microsoft Teams, Discord or Zapier, a morning digest, or a second-robot recheck before anyone is paged.'],
          ['Can I try it before adding my own site?', 'Yes. Sign up and you land in a sample fleet: eight fictional sites with outages, slow pages, an expiring certificate and a late backup, so you can see every feature working. Add your first site and the console becomes yours.'],
          ['Is it free?', 'Yes, during early access: up to 50 sites and 50 heartbeats per account.']],
    bandTitle: 'Put robots on your websites tonight',
    bandLead: 'Add an address, and the first check runs within a minute.'
  };

  // The console, working: a robot sweeps the fleet, harbordental goes down, the playbook rechecks, alerts and sees it recover
  function heroArt() {
    var rows = [['up', 'shop.northwind.ca', 'uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuusuu', '184 ms'], ['down', 'harbordental.com', 'uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuudd', '502', 1],
                ['slow', 'pinecrest-realty.ca', 'ssusssuussssuussssusssssssusssuussssuussssusss', '2.7 s'], ['up', 'api.atlasfreight.io', 'uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu', '92 ms'],
                ['up', 'littlefern.shop', 'uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu', '310 ms']];
    var map = { u: 'up', s: 'slow', d: 'down' };
    var step = function (ic, cls, text, sub) { return '<div class="lp-step2"><i class="' + cls + '">' + ic + '</i><span><span class="' + cls + '">' + text + '</span><small>' + sub + '</small></span></div>'; };
    return '<div class="lp-console" aria-hidden="true"><div class="lp-win"><div class="lp-bar"><i></i><i></i><i></i><span>vitalrpa · console</span><em>● robots on patrol</em></div>' +
      '<div class="lp-kp"><div>Sites up<b>7<span class="faint">/8</span></b></div><div>Incidents<b class="bad">1</b></div><div>Visitors today<b>2,418</b></div></div>' +
      '<div class="lp-rows">' + rows.map(function (r) {
        return '<div class="lp-row' + (r[4] ? ' hit' : '') + '"><span class="nm">' + VR.led(r[0]) + '<b>' + r[1] + '</b></span>' + VR.cells(r[2].split('').map(function (c) { return map[c]; })) + '<span class="ms">' + r[3] + '</span></div>';
      }).join('') + '<span class="lp-scan"></span></div></div>' +
      '<div class="lp-play"><div class="hd"><span>Playbook · site down</span><b>no code</b></div>' +
        step('!', 'bad', '14:05 GET harbordental → 502', 'robot 1, Montréal') +
        step('↻', 'w', '14:06 second robot rechecks', 'robot 2, Frankfurt: still failing') +
        step('✉', 'w', '14:07 email → oncall@', 'with the error and a screenshot') +
        step('#', 'w', '14:07 Slack → #web', '"harbordental is down (502)"') +
        step('✓', 'ok', '14:19 back up, 211 ms', 'incident closed, 14 min') +
        '<span class="lp-chip">&lt;script&gt; <b>&lt; 1 KB</b> · no cookies</span></div></div>';
  }

  UI.page('landing', { title: 'Website robots' }, function (view, ctx) {
    var me = ctx.me, C = COPY, esc = UI.esc;
    var primary = me ? '<a class="ui-btn primary lg" href="#home" data-go="home">Open the console ' + UI.icon('arrow') + '</a>'
      : '<a class="ui-btn primary lg" href="#auth/signup" data-go="auth/signup">' + esc(C.cta) + ' ' + UI.icon('arrow') + '</a>';
    view.innerHTML =
      '<section class="lp-hero"><div class="ui-wrap"><div class="lp-top">' +
        '<div><div class="eyebrow">' + esc(C.eyebrow) + '</div><h1>' + C.title + '</h1></div><div><p class="lp-lead">' + esc(C.lead) + '</p>' +
        '<div class="lp-cta">' + primary + '<a class="ui-btn lg" href="#status/northwind" data-go="status/northwind">' + UI.icon('status') + 'See a live status page</a></div>' +
        '<div class="lp-proof">' + C.proof.map(function (p) { return '<span>' + UI.icon('check') + esc(p) + '</span>'; }).join('') + '</div>' +
      '</div></div>' + heroArt() + '</div></section>' +
      '<section class="lp-section" id="how"><div class="ui-wrap"><div class="lp-head"><div class="eyebrow">How it works</div><h2>' + esc(C.stepsTitle) + '</h2><p>' + esc(C.stepsLead) + '</p></div>' +
        '<div class="lp-steps">' + C.steps.map(function (s) { return '<div class="lp-step"><span class="n">' + s[0] + '</span><h3>' + esc(s[1]) + '</h3><p>' + esc(s[2]) + '</p><code>' + s[3] + '</code></div>'; }).join('') + '</div></div></section>' +
      '<section class="lp-section alt"><div class="ui-wrap"><div class="lp-head"><div class="eyebrow">What the robots check</div><h2>' + esc(C.featuresTitle) + '</h2><p>' + esc(C.featuresLead) + '</p></div>' +
        '<div class="lp-feats">' + C.features.map(function (f) { return '<div class="lp-feat">' + UI.icon(f[0]) + '<h3>' + esc(f[1]) + '<span class="tag">' + esc(f[3]) + '</span></h3><p>' + esc(f[2]) + '</p></div>'; }).join('') + '</div></div></section>' +
      '<section class="lp-section"><div class="ui-wrap lp-weight"><div><div class="eyebrow">The beacon</div><h2>Lighter than your favicon</h2>' +
        '<p class="muted">Monitoring that slows the site down defeats the point. The VitalRPA beacon is a few hundred bytes of inline code that starts after your page has loaded.</p>' +
        '<ul class="lp-list"><li>' + UI.icon('zap') + '<span>Inline: no extra file, no extra connection before your content.</span></li>' +
        '<li>' + UI.icon('clock') + '<span>Waits for the load event, then sends one background ping.</span></li>' +
        '<li>' + UI.icon('lock') + '<span>No cookies, no storage, Do Not Track respected, IPs never stored.</span></li></ul></div>' +
        '<div><div class="lp-wbars" role="img" aria-label="Size comparison: VitalRPA beacon about 0.8 KB, a small favicon about 4 KB, a typical analytics tag 40 to 100 KB">' +
        '<div class="lp-wbar us"><small><b>VitalRPA beacon</b><span>~0.8 KB</span></small><div style="width:1.1%"></div></div>' +
        '<div class="lp-wbar"><small><span>A 32×32 favicon</span><span>~4 KB</span></small><div style="width:5.5%"></div></div>' +
        '<div class="lp-wbar"><small><span>A typical analytics tag</span><span>40–100 KB</span></small><div style="width:100%"></div></div></div>' +
        '<div class="lp-code">&lt;script&gt;!function(w,d,n,k,u){if(n.doNotTrack=="1"…<b>n.sendBeacon(q)</b>…d.readyState=="complete"?v():w.addEventListener("load",v)}(…)&lt;/script&gt;</div></div></div></section>' +
      '<section class="lp-section alt"><div class="ui-wrap"><div class="lp-head c"><h2>Questions</h2></div><div class="lp-faq">' +
        C.faq.map(function (q) { return '<details><summary>' + esc(q[0]) + '</summary><p>' + esc(q[1]) + '</p></details>'; }).join('') + '</div></div></section>' +
      '<section class="lp-section"><div class="ui-wrap"><div class="lp-band"><div><h2>' + esc(C.bandTitle) + '</h2><p>' + esc(C.bandLead) + '</p></div>' +
        (me ? '<a class="ui-btn primary lg" href="#home" data-go="home">Open the console</a>' : '<a class="ui-btn primary lg" href="#auth/signup" data-go="auth/signup">' + esc(C.cta) + '</a>') +
      '</div></div></section>';
  });
})();

/* ===== profile.html ===== */
(function () {
  var esc = UI.esc;
  UI.page('profile', { title: 'Your profile', auth: 'user' }, function (view, ctx) {
    var me = ctx.me;
    view.innerHTML = '<div class="ui-wrap ui-narrow"><div class="pf-head"><span class="ui-avatar">' + esc(UI.initials(me.name)) + '</span>' +
      '<div><h1>' + esc(me.name) + '</h1><div class="muted">' + esc(me.email) + (me.joined ? ' · member since ' + esc(UI.fmtDate(me.joined, { month: 'long', year: 'numeric' })) : '') + '</div></div></div>' +
      '<div class="pf-grid"><form class="ui-card ui-stack" data-name><h3>Your name</h3><label class="ui-field"><span>Shown to other people</span>' +
      '<input type="text" name="name" value="' + esc(me.name) + '" maxlength="60" required></label><button class="ui-btn primary" type="submit">Save</button></form>' +
      '<div class="ui-card ui-stack"><h3>Appearance</h3><p class="muted small">Follow your device, or pick one.</p><div data-theme-box></div>' +
      '<h3 style="margin-top:22px">Password</h3><p class="muted small">We\'ll email you a link to choose a new one.</p>' +
      '<button class="ui-btn" data-reset>' + UI.icon('mail') + 'Email me a reset link</button></div></div>' +
      '<form class="ui-card ui-stack" style="margin-top:16px" data-alerts><h3>' + UI.icon('bell') + ' Alerts</h3>' +
      '<p class="muted small" style="margin:0">Playbooks with an empty email address send to this one. Leave it blank to use your sign-in email.</p>' +
      '<label class="ui-field"><span>Alert email</span><input type="email" name="alert_email" placeholder="' + esc(me.email) + '" autocomplete="email"></label>' +
      '<label class="ui-check"><input type="checkbox" name="digest_on"><span><b>Morning digest</b>: a one-screen summary of the last 24 hours, every day at 06:00 UTC</span></label>' +
      '<div class="ui-row end"><a class="ui-btn ghost" href="#bots" data-go="bots">' + UI.icon('robot') + 'Playbooks</a><button class="ui-btn primary" type="submit">Save alerts</button></div></form>' +
      '<div class="ui-card" style="margin-top:16px"><div class="pf-links">' +
      (me.is_admin ? '<a href="#admin" data-go="admin">' + UI.icon('shield') + 'Admin</a>' : '') +
      '<button data-feedback>' + UI.icon('chat') + 'Submit feedback</button>' +
      '<button data-lk-open="overview">' + UI.icon('lock') + 'Privacy &amp; Terms, and your data</button>' +
      '<button data-signout-here>' + UI.icon('logout') + 'Sign out</button></div></div></div>';
    function themeBox() {
      var t = UI.theme();
      view.querySelector('[data-theme-box]').innerHTML = '<div class="ui-seg">' + [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']].map(function (o) {
        return '<button type="button" data-theme-pick="' + o[0] + '" class="' + (t === o[0] ? 'on' : '') + '">' + o[1] + '</button>';
      }).join('') + '</div>';
    }
    themeBox();
    var af = view.querySelector('[data-alerts]');
    var alertsReady = UI.api('get_alerts').then(function (a) { af.alert_email.value = a.alert_email; af.digest_on.checked = a.digest_on; });
    af.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = UI.formData(af);
      UI.busy(af.querySelector('[type=submit]'), UI.api('save_alerts', v.alert_email, v.digest_on)).then(function () { UI.toast('Alert settings saved', 'ok'); });
    });
    view.addEventListener('click', function (e) {
      var t = e.target.closest('[data-theme-pick]');
      if (t) { UI.setTheme(t.getAttribute('data-theme-pick')); themeBox(); UI.renderChrome(); return; }
      if (e.target.closest('[data-reset]')) {
        UI.busy(e.target.closest('[data-reset]'), UI.auth('reset', { email: me.email })).then(function (r) { UI.toast(r.message, 'ok'); });
      }
      if (e.target.closest('[data-signout-here]')) UI.auth('logout');
    });
    view.querySelector('[data-name]').addEventListener('submit', function (e) {
      e.preventDefault();
      var v = UI.formData(e.target);
      UI.busy(e.target.querySelector('[type=submit]'), UI.api('update_profile', v.name)).then(function (r) {
        UI.setMe(r.me); ctx.me = r.me; UI.toast('Saved', 'ok');
        view.querySelector('.pf-head h1').textContent = r.me.name;
      });
    });
    return alertsReady;
  });
})();

/* ===== site.html ===== */
(function () {
  var esc = UI.esc;
  var TABS = [['overview', 'Overview', 'pulse'], ['traffic', 'Traffic', 'eye'], ['checks', 'Checks', 'robot'], ['errors', 'JS errors', 'bug'],
              ['install', 'Install beacon', 'code'], ['settings', 'Settings', 'cog']];

  function snippet(key, endpoint) {
    return '<!-- VitalRPA beacon: under 1 KB, no cookies, runs after the page has loaded -->\n<script>\n' +
      '!function(w,d,n,k,u){if(n.doNotTrack=="1"||n.webdriver)return;var e=0;function s(o){o.k=k;o.p=location.pathname;' +
      'var q=u+"?"+new URLSearchParams(o);n.sendBeacon?n.sendBeacon(q):(new Image).src=q}w.vrpa=s;' +
      'w.addEventListener("error",function(x){e++<3&&s({t:"e",m:String(x.message).slice(0,140),s:(x.filename||"").split("?")[0].slice(-80)+":"+x.lineno})});' +
      'function v(){setTimeout(function(){var t=performance.getEntriesByType?performance.getEntriesByType("navigation")[0]||{}:{};' +
      's({t:"v",r:d.referrer.split("/")[2]||"",w:w.innerWidth,l:Math.round(t.loadEventStart||0),f:Math.round(t.responseStart||0)})},0)}' +
      'd.readyState=="complete"?v():w.addEventListener("load",v)}(window,document,navigator,"' + key + '","' + endpoint + '");\n<\/script>';
  }
  VR.snippet = snippet;

  function kpi(label, value, sub) { return '<div class="st-kpi"><small>' + esc(label) + '</small><b>' + value + '</b>' + (sub ? '<em>' + sub + '</em>' : '') + '</div>'; }

  UI.page('site', { title: 'Site', auth: 'user' }, function (view, ctx) {
    var id = ctx.args[0], tab = TABS.some(function (t) { return t[0] === ctx.args[1]; }) ? ctx.args[1] : 'overview';
    var s = null, range = '7d';
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:120px;margin-bottom:14px"></div><div class="ui-skel" style="height:300px"></div></div>';

    function head() {
      var demo = s.demo, can = s.can_edit;
      return '<a class="st-back" href="#home" data-go="home' + (demo && !can ? '/sample' : '') + '">' + UI.icon('back') + 'Console</a>' +
        '<div class="st-head"><div style="min-width:0"><div class="st-title">' + VR.led(s.status) + '<h1>' + esc(s.name) + '</h1></div>' +
        '<div class="st-url">' + VR.badge(s.status) + '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.url) + '</a>' +
        (demo ? '<span class="ui-badge brand">Sample</span>' : '') + s.tags.map(function (t) { return '<span class="ui-badge">#' + esc(t) + '</span>'; }).join('') + '</div></div>' +
        '<div class="ui-row"><button class="ui-btn primary" data-check>' + UI.icon('play') + 'Run check now</button>' +
        (can ? '<button class="ui-btn" data-inspect title="Certificate + domain">' + UI.icon('lock') + 'Inspect TLS & domain</button>' +
          '<button class="ui-btn" data-pause>' + UI.icon(s.paused ? 'play' : 'pause') + (s.paused ? 'Resume' : 'Pause') + '</button>' : '') + '</div></div>' +
        '<nav class="ui-tabs">' + TABS.filter(function (t) { return can || t[0] !== 'settings'; }).map(function (t) {
          var n = t[0] === 'errors' && s.jserrors.length ? ' <span class="count">' + s.jserrors.length + '</span>' : '';
          return '<a href="#site/' + esc(s.id) + '/' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '">' + UI.icon(t[2]) + t[1] + n + '</a>';
        }).join('') + '</nav>';
    }

    function overview() {
      var series = range === '24h' ? s.series.filter(function (p) { return Date.now() - new Date(p[0]).getTime() <= 86400000; }) : s.series;
      var sec = s.security, last = s.last_check ? (s.last_code ? 'HTTP ' + s.last_code : 'no answer') + ' · ' + VR.ms(s.last_ms) : 'not yet';
      var next = s.paused ? 'paused' : VR.until(s.next_check);
      var html = '<div class="st-kpis">' +
        kpi('Uptime 24 h / 30 d', VR.pct(s.up24), '30 days: ' + VR.pct(s.up30) + ' · 90 days: ' + VR.pct(s.up90)) +
        kpi('Avg response, 24 h', VR.ms(s.avg_ms), 'slow above ' + VR.ms(s.settings.slow_ms)) +
        kpi('Last check', last, s.last_check ? UI.ago(s.last_check) + (s.last_error ? ' · ' + esc(s.last_error) : '') : 'the robots are on their way') +
        kpi('Next check', next, 'every ' + VR.every(s.interval) + ' = ' + VR.perDay(s.interval) + ' check-ins a day') + '</div>' +
        '<div class="st-card"><h3>Uptime, last 90 days <b>' + VR.pct(s.up90) + '</b></h3>' + VR.uptimeBars(s.uptime90) + '<div style="margin-top:10px">' + VR.legend() + '</div></div>' +
        '<div class="st-card"><h3>Response time <span class="ui-seg st-toggle">' + [['24h', '24 h'], ['7d', '7 days']].map(function (r) {
          return '<button data-range="' + r[0] + '" class="' + (range === r[0] ? 'on' : '') + '">' + r[1] + '</button>';
        }).join('') + '</span></h3>' + VR.lineChart(series, { limit: s.settings.slow_ms }) +
        '<p class="small muted" style="margin:10px 0 0">Red marks along the bottom are failed checks. Hover the line for each robot visit.</p></div>' +
        '<div class="st-grid3">' +
        '<div class="st-card"><h3>' + UI.icon('lock') + ' TLS certificate</h3>' + (s.url.indexOf('https://') !== 0 ? '<p class="ui-error">This site isn\'t served over HTTPS.</p>'
          : s.ssl_error ? '<p class="ui-error">' + esc(s.ssl_error) + '</p>'
            : '<div class="st-big">' + (s.ssl_days == null ? '—' : s.ssl_days) + ' <small>days left</small></div><dl class="vr-kv"><dt>Expires</dt><dd>' + esc(UI.fmtDate(s.ssl_expires)) + '</dd><dt>Issuer</dt><dd>' + esc(s.ssl_issuer || '—') + '</dd></dl>') +
          '<p class="small faint" style="margin:10px 0 0">Inspected ' + (s.inspected ? UI.ago(s.inspected) : 'not yet') + ' · warns at 14 days</p></div>' +
        '<div class="st-card"><h3>' + UI.icon('globe') + ' Domain</h3>' + (s.domain_days == null ? '<p class="muted small">' + esc(s.domain_error || 'Not inspected yet.') + '</p>'
          : '<div class="st-big">' + s.domain_days + ' <small>days left</small></div>') +
          '<dl class="vr-kv"><dt>Domain</dt><dd>' + esc(s.domain) + '</dd><dt>Renew by</dt><dd>' + esc(s.domain_expires ? UI.fmtDate(s.domain_expires) : '—') + '</dd></dl>' +
          '<p class="small faint" style="margin:10px 0 0">From the registry (RDAP) · warns at 30 days</p></div>' +
        '<div class="st-card"><h3>' + UI.icon('shield') + ' Security headers ' + (sec.grade ? '<span class="st-grade ' + sec.grade + '">' + sec.grade + '</span>' : '') + '</h3>' +
          (sec.grade ? '<ul class="st-hdrs">' + [{ ok: sec.https, name: 'HTTPS', why: 'Encrypted connection' }].concat(sec.items).map(function (h) {
            return '<li class="' + (h.ok ? 'ok' : 'no') + '">' + UI.icon(h.ok ? 'check' : 'x') + '<div><b>' + esc(h.name) + '</b> <span>' + esc(h.why) + '</span></div></li>';
          }).join('') + '</ul>' : '<p class="muted small">Read on the next robot visit.</p>') + '</div></div>' +
        '<div class="st-grid2" style="margin-top:14px"><div class="st-card"><h3>' + UI.icon('server') + ' The page itself</h3><dl class="vr-kv">' +
          '<dt>HTML weight</dt><dd>' + VR.bytes(s.page_bytes) + '</dd><dt>Server says</dt><dd>' + esc(s.server || '—') + '</dd>' +
          '<dt>Keyword</dt><dd>' + (s.settings.keyword ? '“' + esc(s.settings.keyword) + '” must appear' : 'not checked') + '</dd>' +
          '<dt>Expected status</dt><dd>' + (s.settings.expect_status || 'any 2xx / 3xx') + '</dd>' +
          '<dt>Silence alarm</dt><dd>' + (s.settings.quiet_hours ? 'after ' + s.settings.quiet_hours + ' h without visitors' : 'off') + '</dd></dl></div>' +
        '<div class="st-card"><h3>' + UI.icon('bell') + ' Incidents <a href="#incidents" data-go="incidents" class="small">All</a></h3>' +
          (s.incidents.length ? '<div class="st-inc">' + s.incidents.slice(0, 5).map(function (i) {
            return '<a href="#incidents" data-go="incidents"><span>' + VR.sev(i.severity, i.resolved) + ' ' + esc(i.title) + '</span><span class="mono small muted">' + VR.stamp(i.started) + ' · ' + VR.dur(i.minutes) + '</span></a>';
          }).join('') + '</div>' : '<p class="muted small">No incidents. The robots will open one if something breaks.</p>') + '</div></div>';
      return html;
    }

    function traffic() {
      var t = s.traffic;
      if (s.beacon === 'none' && !t.views7) {
        return '<div class="ui-empty">' + UI.icon('eye') + '<h3>No visitor data yet</h3><p>Uptime works without any code. For visitors, page speed and JavaScript errors, paste the tiny beacon (under 1 KB) into your pages.</p>' +
          (s.can_edit ? '<a class="ui-btn primary" href="#site/' + esc(s.id) + '/install">' + UI.icon('code') + 'Install the beacon</a>' : '') + '</div>';
      }
      var hourNow = new Date().getUTCHours();
      return '<div class="st-kpis">' + kpi('Page views, 7 days', VR.num(t.views7), VR.num(t.today.views) + ' today') +
        kpi('Visitors, 7 days', VR.num(t.visitors7), VR.num(t.today.visitors) + ' today (unique per day)') +
        kpi('Avg page load', VR.ms(t.load_ms), 'real visitors, until the load event') +
        kpi('Avg server response', VR.ms(t.ttfb_ms), 'time to first byte, real visitors') + '</div>' +
        '<div class="st-card"><h3>Page views per day, 30 days <b>' + VR.num(t.days.reduce(function (a, d) { return a + d.views; }, 0)) + '</b></h3>' +
        VR.colbars(t.days.map(function (d, i) { return { v: d.views, tip: VR.day(d.day) + '\n' + VR.num(d.views) + ' views · ' + VR.num(d.visitors) + ' visitors', cls: i === t.days.length - 1 ? 'now' : '' }; }), 130) +
        '<div class="vr-axis"><span>' + VR.day(t.days[0].day) + '</span><span>today</span></div></div>' +
        '<div class="st-card"><h3>Today by hour (UTC) <b>' + VR.num(t.today.views) + '</b></h3>' +
        VR.colbars(t.today.hours.map(function (n, h) { return { v: h > hourNow ? null : n, tip: (h < 10 ? '0' : '') + h + ':00 UTC\n' + (h > hourNow ? 'later today' : VR.num(n) + ' views'), cls: h === hourNow ? 'now' : '' }; }), 90) +
        '<div class="vr-axis"><span>00:00</span><span>12:00</span><span>23:00</span></div></div>' +
        '<div class="st-grid3"><div class="st-card"><h3>Top pages, 7 days</h3>' + VR.blist(t.pages) + '</div>' +
        '<div class="st-card"><h3>Where visitors come from</h3>' + VR.blist(t.refs) + '</div>' +
        '<div class="st-card"><h3>Devices</h3>' + VR.blist(t.devices) + '<p class="small faint" style="margin:12px 0 0">From screen width: phone &lt; 700 px, tablet &lt; 1100 px.</p></div></div>';
    }

    function checks() {
      return '<div class="st-card" style="padding:0;overflow:auto"><table class="st-table"><thead><tr><th>Time (UTC)</th><th>Result</th><th>HTTP</th><th>Time</th><th class="hide-sm">Robot</th><th>Problem</th></tr></thead><tbody>' +
        (s.checks.length ? s.checks.map(function (c) {
          var st = !c.ok ? 'down' : c.slow ? 'slow' : 'up';
          return '<tr><td>' + VR.stamp(c.at) + '</td><td>' + VR.badge(st) + '</td><td>' + (c.code || '—') + '</td><td>' + VR.ms(c.ms) + '</td><td class="hide-sm">' + esc(c.source || 'robot') + '</td><td class="err">' + esc(c.error || '') + '</td></tr>';
        }).join('') : '<tr><td colspan="6" class="muted">No checks yet.</td></tr>') + '</tbody></table></div>' +
        '<p class="small muted">The last 80 robot visits. A failed check is retried after 2 minutes before an incident opens; raw checks are kept for 30 days, daily totals for good.</p>';
    }

    function errors() {
      return '<div class="ui-row between" style="margin-bottom:12px"><p class="muted small" style="margin:0">JavaScript errors real visitors hit, grouped by message (at most 3 per page view, from the beacon).</p>' +
        (s.can_edit && s.jserrors.length ? '<button class="ui-btn sm danger" data-clear-errors>' + UI.icon('trash') + 'Clear all</button>' : '') + '</div>' +
        (s.jserrors.length ? s.jserrors.map(function (e) {
          return '<div class="st-err"><span class="cnt">' + VR.num(e.count) + '×</span><code>' + esc(e.message) + '</code>' +
            '<small>' + esc(e.source || 'unknown source') + ' · on ' + esc(e.path || '/') + ' · first ' + VR.stamp(e.first) + ' · last ' + UI.ago(e.last) + '</small></div>';
        }).join('') : '<div class="ui-empty">' + UI.icon('check') + '<h3>No JavaScript errors</h3><p>' + (s.beacon === 'none' ? 'Install the beacon to catch errors your visitors see.' : 'Visitors haven\'t hit any. Nice.') + '</p></div>');
    }

    function install() {
      var code = snippet(s.site_key, s.endpoint);
      var bytes = new Blob([code]).size;
      return '<div class="st-card"><h3>' + UI.icon('robot') + ' Already working, no code needed</h3><p style="margin:0">The robots load <b>' + esc(s.host) + '</b> every ' + VR.every(s.interval) +
        ' (' + VR.perDay(s.interval) + ' times a day) and check the status code, response time, keyword, certificate, domain and security headers. Nothing to install for that.</p></div>' +
        '<div class="st-card"><h3>' + UI.icon('code') + ' Optional: the visitor beacon <b>' + bytes + ' bytes</b></h3>' +
        '<p>Paste this just before <code>&lt;/body&gt;</code> on every page (your theme\'s footer is usually the one place). It adds visitors, real page-load times and JavaScript errors.</p>' +
        '<div class="vr-copybox"><pre data-code>' + esc(code) + '</pre><button class="ui-btn sm" data-copy>' + UI.icon('copy') + 'Copy</button></div>' +
        '<ul class="st-facts"><li>' + UI.icon('zap') + '<span>Inline, nothing extra to download, and it waits until your page has finished loading.</span></li>' +
        '<li>' + UI.icon('send') + '<span>Sends one tiny background ping per page view (<code>sendBeacon</code>): it can\'t slow the page or block it.</span></li>' +
        '<li>' + UI.icon('lock') + '<span>No cookies, no local storage, respects Do Not Track. Unique visitors are counted with a daily-changing fingerprint; IP addresses are never stored.</span></li>' +
        '<li>' + UI.icon('info') + '<span>What it sends: the page path, the referring site, screen width, load time, server response time, and up to 3 JavaScript errors per page.</span></li></ul></div>' +
        '<div class="st-card"><h3>' + UI.icon('check') + ' Is it working?</h3><div class="st-verify" data-verify>' + verifyText(s.beacon, s.last_beat) + '</div>' +
        '<div class="ui-row" style="margin-top:12px"><button class="ui-btn" data-verify-now>' + UI.icon('refresh') + 'Check for beacons</button>' +
        (s.can_edit ? '<button class="ui-btn" data-test-beacon>' + UI.icon('send') + 'Send a test beacon from this browser</button>' : '') + '</div></div>' +
        '<div class="st-card"><h3>Where to paste it</h3><div class="st-plat">' +
        '<div><b>WordPress</b>Appearance → Theme file editor → footer.php before &lt;/body&gt;, or any "header &amp; footer scripts" plugin.</div>' +
        '<div><b>Shopify</b>Online Store → Themes → Edit code → theme.liquid, just before &lt;/body&gt;.</div>' +
        '<div><b>Wix, Squarespace, Webflow</b>Settings → Custom code → "Body end" / "Footer", on all pages.</div>' +
        '<div><b>Google Tag Manager</b>New tag → Custom HTML → paste → trigger "All pages".</div>' +
        '<div><b>Single-page apps</b>After each route change, call <code>vrpa({t:"v"})</code> to count the new page.</div>' +
        '<div><b>Several sites</b>Each site has its own key. Watching another site? Add it in the console and copy its snippet.</div></div></div>';
    }
    function verifyText(state, last) {
      if (state === 'none' || !last) return UI.icon('clock') + '<span>No beacon received yet. Paste the snippet, open your site in a browser, then check again.</span>';
      return VR.led(state === 'quiet' ? 'down' : 'up') + '<span>Last beacon <b>' + UI.ago(last) + '</b> (' + VR.stamp(last) + ' UTC)' + (state === 'quiet' ? ': quieter than your silence alarm.' : '. It\'s working.') + '</span>';
    }

    function settings() {
      var st = s.settings;
      return '<form class="st-card" data-settings><h3>' + UI.icon('cog') + ' What the robots check</h3><div class="st-settings">' +
        '<label class="ui-field"><span>Name</span><input type="text" name="name" value="' + esc(st.name) + '" maxlength="60" required></label>' +
        '<label class="ui-field"><span>Address</span><input type="text" name="url" value="' + esc(st.url) + '" required></label>' +
        '<label class="ui-field"><span>Check every</span><select name="interval_min">' + s.intervals.map(function (o) {
          return '<option value="' + o + '"' + (o === st.interval_min ? ' selected' : '') + '>' + VR.every(o) + ' (' + VR.perDay(o) + '× a day)</option>';
        }).join('') + '</select></label>' +
        '<label class="ui-field"><span>Slow above (ms)</span><input type="number" name="slow_ms" min="300" max="30000" step="100" value="' + st.slow_ms + '"></label>' +
        '<label class="ui-field"><span>Text that must be on the page</span><input type="text" name="keyword" value="' + esc(st.keyword) + '" maxlength="80" placeholder="optional"></label>' +
        '<label class="ui-field"><span>Expected HTTP status <em>(blank = any 2xx/3xx)</em></span><input type="number" name="expect_status" min="100" max="599" value="' + (st.expect_status || '') + '"></label>' +
        '<label class="ui-field"><span>Silence alarm <em>(hours without visitors, 0 = off)</em></span><input type="number" name="quiet_hours" min="0" max="168" value="' + st.quiet_hours + '"></label>' +
        '<label class="ui-field"><span>Tags <em>(comma separated)</em></span><input type="text" name="tags" value="' + esc(st.tags.join(', ')) + '"></label>' +
        '</div><div class="ui-row end" style="margin-top:14px"><button class="ui-btn primary" type="submit">' + UI.icon('check') + 'Save</button></div></form>' +
        '<div class="st-card st-danger"><h3>' + UI.icon('alert') + ' Careful</h3>' +
        '<div class="ui-row between"><div><b>New beacon key</b><p class="small muted" style="margin:2px 0 0">The old snippet stops counting. Use it if the key leaked.</p></div><button class="ui-btn" data-rotate>' + UI.icon('key') + 'Rotate key</button></div>' +
        '<div class="ui-row between" style="margin-top:14px"><div><b>Stop watching this site</b><p class="small muted" style="margin:2px 0 0">Deletes its checks, traffic, errors and incidents.</p></div><button class="ui-btn danger" data-delete>' + UI.icon('trash') + 'Delete site</button></div></div>';
    }

    var DRAW = { overview: overview, traffic: traffic, checks: checks, errors: errors, install: install, settings: settings };
    function draw() {
      if (tab === 'settings' && !s.can_edit) tab = 'overview';
      document.title = s.name + ' · VitalRPA';
      view.innerHTML = '<div class="ui-wrap">' + head() + '<div data-body>' + DRAW[tab]() + '</div></div>';
    }
    function load() {
      return UI.api('get_site', id).then(function (r) { s = r.site; draw(); });
    }

    view.addEventListener('click', function (e) {
      var b;
      if ((b = e.target.closest('[data-range]'))) { range = b.getAttribute('data-range'); draw(); return; }
      if ((b = e.target.closest('[data-check]'))) {
        UI.busy(b, UI.api('check_now', s.id)).then(function (r) {
          var x = r.result;
          UI.toast(x.state === 'fail' ? 'Check failed: ' + x.problem : 'HTTP ' + x.code + ' in ' + VR.ms(x.ms) + (x.state === 'slow' ? ' (slow)' : ''), x.state === 'fail' ? 'error' : 'ok');
          s = r.site; draw();
        });
        return;
      }
      if ((b = e.target.closest('[data-inspect]'))) {
        UI.busy(b, UI.api('inspect_now', s.id)).then(function (r) {
          var x = r.result;
          UI.toast(x.ssl_error || ('Certificate: ' + (x.ssl_days == null ? 'n/a' : x.ssl_days + ' days') + ' · domain: ' + (x.domain_days == null ? 'unknown' : x.domain_days + ' days')), x.ssl_error ? 'error' : 'ok');
          s = r.site; draw();
        });
        return;
      }
      if ((b = e.target.closest('[data-pause]'))) {
        var flag = !s.paused;
        UI.busy(b, UI.api('set_site_paused', s.id, flag)).then(function () { UI.toast(flag ? 'Paused: the robots leave it alone' : 'Resumed: checking now', 'ok'); return load(); });
        return;
      }
      if (e.target.closest('[data-copy]')) { VR.copy(view.querySelector('[data-code]').textContent, 'Snippet copied'); return; }
      if ((b = e.target.closest('[data-verify-now]'))) {
        UI.busy(b, UI.api('beacon_status', s.id)).then(function (r) { view.querySelector('[data-verify]').innerHTML = verifyText(r.state, r.last_beat); });
        return;
      }
      if ((b = e.target.closest('[data-test-beacon]'))) {
        var url = s.endpoint + '?' + new URLSearchParams({ k: s.site_key, t: 'v', p: '/vitalrpa-test', w: String(innerWidth), x: '1' });
        UI.busy(b, fetch(url, { mode: 'no-cors', cache: 'no-store' }).then(function () { return UI.api('beacon_status', s.id); })).then(function (r) {
          view.querySelector('[data-verify]').innerHTML = verifyText(r.state, r.last_beat);
          UI.toast('Test beacon received', 'ok');
        }, function () { UI.toast('The test beacon couldn\'t be sent from this browser (an ad blocker?)', 'error'); });
        return;
      }
      if ((b = e.target.closest('[data-clear-errors]'))) {
        UI.confirm({ title: 'Clear all JavaScript errors?', text: 'They come back if visitors hit them again.', ok: 'Clear', danger: true }).then(function (yes) {
          if (yes) UI.api('clear_js_errors', s.id).then(load);
        });
        return;
      }
      if ((b = e.target.closest('[data-rotate]'))) {
        UI.confirm({ title: 'Rotate the beacon key?', text: 'Pages with the old snippet stop counting until you paste the new one.', ok: 'Rotate', danger: true }).then(function (yes) {
          if (yes) UI.api('rotate_site_key', s.id).then(function () { UI.toast('New key ready: copy the new snippet', 'ok'); tab = 'install'; return load(); });
        });
        return;
      }
      if ((b = e.target.closest('[data-delete]'))) {
        UI.confirm({ title: 'Delete ' + s.name + '?', text: 'Its checks, traffic, errors and incidents are deleted too. This can\'t be undone.', ok: 'Delete', danger: true }).then(function (yes) {
          if (yes) UI.api('delete_site', s.id).then(function () { UI.toast('Deleted', 'ok'); UI.go('home'); });
        });
      }
    });
    view.addEventListener('submit', function (e) {
      if (!e.target.matches('[data-settings]')) return;
      e.preventDefault();
      UI.busy(e.target.querySelector('[type=submit]'), UI.api('update_site', s.id, UI.formData(e.target))).then(function (r) {
        s = r.site; UI.toast('Saved', 'ok'); draw();
      });
    });
    return load();
  });
})();

/* ===== status.html ===== */
(function () {
  var esc = UI.esc;
  var TEXT = { operational: 'All systems operational', degraded: 'Some systems are slow', maintenance: 'Scheduled maintenance', outage: 'Part of the service is down' };
  var LED = { operational: 'up', degraded: 'slow', maintenance: 'paused', outage: 'down' };
  UI.page('status', { title: 'Status' }, function (view, ctx) {
    var slug = ctx.args[0] || '';
    view.innerHTML = '<div class="ui-wrap sp-wrap"><div class="ui-skel" style="height:320px"></div></div>';
    return UI.api('get_status_page', slug).then(function (r) {
      var p = r.page;
      document.title = p.title + ' status';
      view.innerHTML = '<div class="ui-wrap ui-narrow sp-wrap"><div class="sp-top"><div><div class="eyebrow">Status page' + (p.demo ? ' · sample' : '') + '</div><h1>' + esc(p.title) + '</h1>' +
        (p.intro ? '<p class="muted" style="margin:6px 0 0">' + esc(p.intro) + '</p>' : '') + '</div>' +
        (p.mine ? '<a class="ui-btn sm" href="#statuspage" data-go="statuspage">' + UI.icon('edit') + 'Edit</a>' : '') + '</div>' +
        (!p.public ? '<p class="ui-note">' + UI.icon('lock') + ' Only you can see this page until you make it public.</p>' : '') +
        '<div class="sp-banner ' + p.overall + '">' + VR.led(LED[p.overall]) + TEXT[p.overall] + '</div>' +
        (p.sites.length ? '<div class="sp-sites">' + p.sites.map(function (s) {
          return '<div class="sp-site"><header><h3>' + VR.led(LED[s.state]) + esc(s.name) + '</h3><span class="ui-row" style="gap:12px"><span class="mono small muted">' + VR.pct(s.uptime) + ' uptime</span>' +
            '<span class="sp-state ' + s.state + '">' + s.state + '</span></span></header>' + VR.uptimeBars(s.bars) + '</div>';
        }).join('') + '</div>' : '<div class="ui-empty"><p>No services on this page yet.</p></div>') +
        '<section class="sp-inc"><h2>Past 14 days</h2>' + (p.incidents.length ? p.incidents.map(function (i) {
          return '<article class="' + (i.resolved ? '' : 'open') + '"><b>' + esc(i.title) + '</b><br><time>' + VR.stamp(i.started) + ' UTC' +
            (i.resolved ? ' → resolved ' + VR.stamp(i.resolved) + ' UTC' : ' · ongoing') + '</time>' + (i.resolution ? '<p class="small muted" style="margin:4px 0 0">' + esc(i.resolution) + '</p>' : '') + '</article>';
        }).join('') : '<p class="muted">No incidents in the past 14 days.</p>') + '</section>' +
        '<p class="sp-power">Updated ' + VR.stamp(p.updated) + ' UTC · checked around the clock by <a href="#landing" data-go="landing">VitalRPA</a> robots</p></div>';
    }, function (err) {
      view.innerHTML = '<div class="ui-wrap"><div class="ui-empty">' + UI.icon('status') + '<h3>No status page here</h3><p>' + esc(err.message) + '</p>' +
        '<a class="ui-btn" href="#status/northwind" data-go="status/northwind">See a sample status page</a></div></div>';
    });
  });
})();

/* ===== statuspage.html ===== */
(function () {
  var esc = UI.esc;
  UI.page('statuspage', { title: 'Status page', nav: 'Status page', icon: 'status', auth: 'user', order: 40 }, function (view) {
    view.innerHTML = '<div class="ui-wrap"><div class="ui-skel" style="height:320px"></div></div>';
    return UI.api('get_my_status_page').then(function (d) {
      var p = d.page || { slug: d.suggest.slug, title: d.suggest.title, intro: '', site_ids: d.sites.map(function (s) { return s.id; }), public: false };
      var base = location.origin + location.pathname.replace(/[^/]*$/, '') + '#status/';
      view.innerHTML = '<div class="ui-wrap"><div class="ui-page-head"><div><div class="eyebrow">Tell your customers first</div><h1>Status page</h1>' +
        '<p class="muted">A public page with the state of your sites and 90 days of uptime. Share it before people start emailing you.</p></div>' +
        (d.page ? '<a class="ui-btn" href="#status/' + esc(d.page.slug) + '" data-go="status/' + esc(d.page.slug) + '">' + UI.icon('external') + 'Open my page</a>' : '') + '</div>' +
        '<div class="sp-ed"><form class="ui-card ui-stack" data-sp>' +
        '<label class="ui-field"><span>Address</span><div class="sp-addr"><span>…#status/</span><input type="text" name="slug" value="' + esc(p.slug) + '" required pattern="[a-z0-9][a-z0-9-]{2,39}" maxlength="40"></div>' +
        '<p class="ui-hint">Lowercase letters, digits and dashes.</p></label>' +
        '<label class="ui-field"><span>Title</span><input type="text" name="title" value="' + esc(p.title) + '" maxlength="80" required></label>' +
        '<label class="ui-field"><span>A line for your visitors <em>(optional)</em></span><textarea name="intro" maxlength="400" rows="3" placeholder="We check our services every few minutes. Subscribe to our newsletter for maintenance notices.">' + esc(p.intro) + '</textarea></label>' +
        '<div class="ui-field"><span>Sites on the page</span>' + (d.sites.length ? '<div class="sp-pick">' + d.sites.map(function (s) {
          return '<label><input type="checkbox" name="site_' + esc(s.id) + '"' + (p.site_ids.indexOf(s.id) >= 0 ? ' checked' : '') + '><span>' + esc(s.name) + '<small>' + esc(s.host) + '</small></span></label>';
        }).join('') + '</div>' : '<p class="muted small">Add a site in the console first.</p>') + '<p class="ui-hint">Visitors see the names you gave the sites, never their addresses.</p></div>' +
        '<label class="ui-check"><input type="checkbox" name="public"' + (p.public ? ' checked' : '') + '><span><b>Public</b>: anyone with the link can see it</span></label>' +
        '<div class="ui-row end"><button class="ui-btn primary" type="submit">' + UI.icon('check') + 'Save</button></div></form>' +
        '<div class="ui-card"><h3>What visitors see</h3><ul class="sp-why muted"><li>One line: all good, slow, maintenance or down.</li><li>Each site with 90 days of daily uptime.</li>' +
        '<li>Outages from the last 14 days and how they ended.</li><li>Nothing else: no addresses, no notes, no traffic.</li></ul>' +
        (d.sample_slug ? '<a class="ui-btn sm" href="#status/' + esc(d.sample_slug) + '" data-go="status/' + esc(d.sample_slug) + '">' + UI.icon('eye') + 'See a sample page</a>' : '') +
        '<p class="small faint" style="margin:14px 0 0">Your link: <span class="mono">' + esc(base) + '<b data-slug>' + esc(p.slug) + '</b></span></p></div></div></div>';
      var f = view.querySelector('[data-sp]');
      f.slug.addEventListener('input', function () { view.querySelector('[data-slug]').textContent = f.slug.value; });
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        var v = UI.formData(f);
        var ids = Object.keys(v).filter(function (k) { return k.indexOf('site_') === 0 && v[k]; }).map(function (k) { return k.slice(5); });
        UI.busy(f.querySelector('[type=submit]'), UI.api('save_status_page', { slug: v.slug.trim().toLowerCase(), title: v.title, intro: v.intro, site_ids: ids, public: v.public }))
          .then(function (r) { UI.toast('Saved', 'ok'); UI.go('status', r.slug); });
      });
    });
  });
})();
