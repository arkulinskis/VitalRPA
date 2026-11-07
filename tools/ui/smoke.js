/* Smoke test: every page address opens without an error and isn't empty, signed out, as a new member (sample fleet,
   one sample site's tabs) and as the admin. ui_test.py fails the run on any Python/JS exception it sees.
   python -I tools/ui_test.py --only smoke.js. Resolves to {ok, log}. */
(async function () {
  const log = [], bad = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function until(fn, what, ms) {
    const end = Date.now() + (ms || 30000);
    while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (e) {} await sleep(150); }
    throw new Error('timed out waiting for: ' + what);
  }
  const $ = (s) => document.querySelector(s), $$ = (s) => Array.from(document.querySelectorAll(s));
  function type(input, value) {
    input.focus(); input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  async function visit(hash) {
    if (location.hash !== hash) window.UI_READY = false;
    location.hash = hash;
    await until(() => window.UI_READY && location.hash === hash, hash, 40000);
    await sleep(500);
    const n = (($('.ui-main') || document.body).innerText || '').trim().length;
    if (n < 40) bad.push(hash + ' is empty');
    log.push((n < 40 ? 'EMPTY ' : 'ok   ') + hash + ' (' + n + ' chars)');
  }
  const inputs = () => $$('.au-card input[type=text], .au-card input[type=email], .au-card input[type=password]').filter((i) => i.offsetParent);
  async function signOut() {
    $('.anvil-role-avatar button').click();
    await sleep(300);
    $$('.ui-menu button').find((b) => /Sign out/.test(b.textContent)).click();
    await until(() => location.hash === '#landing' && window.UI_READY, 'signed out');
  }
  try {
    for (const h of ['#landing', '#auth', '#auth/signup', '#status/northwind', '#status/nobody-here']) await visit(h);
    // a new member (sees the sample fleet)
    await visit('#auth/signup');
    let i = inputs();
    type(i[0], 'Smoke Tester'); type(i[1], 'smoke' + Date.now() + '@example.com'); type(i[2], 'Hb-' + Math.random().toString(36).slice(2) + '-Kq7');
    const tick = $('.au-card input[type=checkbox]'); if (tick && !tick.checked) tick.click();
    $$('.anvil-role-btn-block button').find((b) => /Create account/.test(b.textContent)).click();
    await until(() => location.hash === '#home' && window.UI_READY, 'signed up', 60000);
    for (const h of ['#home', '#home/sample', '#incidents', '#incidents/resolved', '#incidents/all', '#bots', '#statuspage', '#profile']) await visit(h);
    await visit('#home');
    const site = $('a.cn-row[href^="#site/"]').getAttribute('href');
    for (const t of ['', '/traffic', '/checks', '/errors', '/install']) await visit(site + t);
    await visit('#site/no-such-site');
    await signOut();
    // the admin (ADMIN_EMAILS address; made on first run in this local database)
    await visit('#auth');
    const pw = 'Hb-local-admin-Kq7-2026';
    i = inputs(); type(i[0], 'arkulinskis@gmail.com'); type(i[1], pw);
    $$('.anvil-role-btn-block button').find((b) => /Sign in/.test(b.textContent)).click();
    await sleep(3000);
    if (location.hash !== '#home') {
      $$('.ui-seg button').find((b) => /Create account/.test(b.textContent)).click();
      await sleep(500);
      i = inputs(); type(i[0], 'Local Admin'); type(i[1], 'arkulinskis@gmail.com'); type(i[2], pw);
      const t2 = $('.au-card input[type=checkbox]'); if (t2 && !t2.checked) t2.click();
      $$('.anvil-role-btn-block button').find((b) => /Create account/.test(b.textContent)).click();
    }
    await until(() => location.hash === '#home' && window.UI_READY, 'signed in as admin', 60000);
    for (const h of ['#admin/overview', '#admin/robots', '#admin/feedback', '#admin/users', '#admin/demo']) await visit(h);
    await signOut();
    log.push(bad.length ? 'PROBLEMS: ' + bad.join(' | ') : 'PASSED');
    return { ok: !bad.length, log };
  } catch (e) {
    log.push(String(e && e.message || e));
    return { ok: false, log };
  }
})();
