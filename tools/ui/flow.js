/* VitalRPA's user journeys, run inside the real app (Anvil App Server) by tools/ui_test.py through tools/live/drive.mjs:
   landing + Watch, a public status page, sign-up (sent back to the page asked for), the sample console (filter, tags),
   a sample site's tabs (snippet under 1 KB), incidents, robots, adding a site through the dialog, its settings, the
   status page editor, a heartbeat and a playbook through their dialogs, deleting the site, profile + alerts, theme,
   sign out. Resolves to {ok, log}. Keep log lines ASCII (the Windows console). */
(async function () {
  const log = [], t0 = Date.now();
  const say = (m) => log.push(((Date.now() - t0) / 1000).toFixed(1) + 's ' + m);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function until(fn, what, ms) {
    const end = Date.now() + (ms || 20000);
    while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (e) {} await sleep(150); }
    throw new Error('timed out waiting for: ' + what);
  }
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const vis = (e) => e && e.getBoundingClientRect().width > 0;
  const byText = (sel, text) => $$(sel).find((e) => vis(e) && e.textContent.trim().replace(/\s+/g, ' ') === text);
  async function click(sel, text) {
    const el = await until(() => (text ? byText(sel, text) : $$(sel).find(vis)), sel + (text ? ' "' + text + '"' : ''));
    el.scrollIntoView({ block: 'center' });
    el.click();
    return el;
  }
  function type(input, value) {
    input.focus();
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  async function page(hash, ready, what) {
    if (location.hash !== hash) window.UI_READY = false;  // the old page stays until the router runs
    location.hash = hash;
    await until(() => window.UI_READY && location.hash === hash && ready(), what || hash, 40000);
    await sleep(300);
  }
  async function yes(text) {  // confirm() dialogs
    await click('.anvil-modal-content button', text);
    await until(() => !byText('.anvil-modal-content button', text), 'dialog closed');
  }
  const ok = (cond, msg) => { if (!cond) throw new Error('FAILED: ' + msg); say('ok   ' + msg); };
  const rnd = Math.random().toString(36).slice(2, 8);

  try {
    // ---- landing (visitors)
    await page('#landing', () => $('.lp-hero'), 'landing');
    ok(vis($$('.lp-hero a[href="#auth/signup"]').find(vis)), 'landing: hero with a sign-up link');
    ok($$('.lp-row .vr-cells i').length === 5 * 24, 'landing: the console picture has 5 sites x 24 hours');
    ok($('#watch .ytf-cover'), 'landing: Watch section with the video cover');
    ok(byText('.ui-header a', 'Start monitoring'), 'landing: Start monitoring in the header');
    ok($('.ui-footer a[href="https://arkvital.com"]') && $('.ui-footer a[href="https://addanapp.com"]') && $('.ui-footer [data-prepsto-open]') && $('.ui-footer [data-lk-open]'),
      'footer: feedback, Privacy & Terms, arkvital.com, addanapp.com');

    // ---- a public status page, signed out
    await page('#status/northwind', () => vis($('.sp-banner')) || vis($$('.ui-empty').find(vis)), 'status page');
    ok($$('.sp-site').length >= 1 && $$('.sp-site .vr-bars i').length >= 90, 'status page: services with 90-day bars');
    await page('#status/nobody-here-' + rnd, () => vis($$('.ui-empty').find(vis)), 'missing status page');
    ok(/No status page here/.test(document.body.textContent), 'status page: unknown address shows a friendly message');

    // ---- members-only page sends visitors to sign in, then back
    await page('#bots', () => true);
    await until(() => window.UI_READY && $$('.au-card input').length >= 2, 'redirected to sign in');
    ok(true, 'a members-only page asks visitors to sign in');
    await click('.au-card .ui-seg button', 'Create account');
    await until(() => $$('.au-card input').filter(vis).length >= 3, 'sign-up form');
    const inputs = $$('.au-card input[type=text], .au-card input[type=email], .au-card input[type=password]').filter(vis);
    type(inputs[0], 'Flow Tester'); type(inputs[1], 'flow' + Date.now() + '@example.com'); type(inputs[2], 'Hb-' + rnd + '-Kq7z');
    const tick = $('.au-card input[type=checkbox]');
    if (tick && !tick.checked) tick.click();
    await click('.anvil-role-btn-block button', 'Create account');
    await until(() => location.hash === '#bots' && window.UI_READY && $('.bt-robot'), 'back on the page they wanted', 60000);
    ok(true, 'sign-up: signed in and sent on to the page they asked for');
    ok($('.anvil-role-avatar button') && /FT/.test($('.anvil-role-avatar button').textContent), 'header: account button with initials');
    ok(/UTC \d\d:\d\d:\d\d/.test(($('.vr-clock') || {}).textContent || ''), 'header: the UTC robot clock');

    // ---- robots page (sample fleet for a new account)
    ok($$('.bt-robot').length >= 6, 'robots: the built-in robots (' + $$('.bt-robot').length + ')');
    ok(vis($('.bt .vr-sample')), 'robots: sample-fleet banner for a new account');
    ok($$('.bt-pb').length >= 1 && $$('.bt-hb').length >= 1, 'robots: sample playbooks and heartbeats');

    // ---- console: the sample fleet
    await page('#home', () => $$('a.cn-row').length >= 3, 'console');
    const rows0 = $$('a.cn-row').length;
    ok(vis($('.cn .vr-sample')) && /Sample fleet/.test($('.anvil-role-cn-sub').textContent), 'console: sample fleet, said in the subtitle');
    ok($$('a.cn-row .vr-cells')[0].querySelectorAll('i').length === 24, 'console: 24-hour strip per site');
    ok($$('.cn-kpi b').every((b) => b.textContent.trim()), 'console: five KPI tiles filled');
    ok($$('.cn-line-host').length >= 3, 'console: the robot log');
    type($('.cn-tools input'), 'harbor');
    await until(() => $$('a.cn-row').length >= 1 && $$('a.cn-row').length < rows0, 'filter narrows');
    ok(/harbor/i.test($('a.cn-row').textContent), 'console: the filter box narrows the list');
    type($('.cn-tools input'), '');
    await until(() => $$('a.cn-row').length === rows0, 'filter cleared');
    const chips = $$('.anvil-role-cn-chip button');
    if (chips.length > 1) {
      chips[1].click();
      await until(() => $$('.anvil-role-cn-chip.anvil-role-on button')[0] && $$('.anvil-role-cn-chip.anvil-role-on button')[0].textContent !== 'all', 'tag picked');
      ok($$('a.cn-row').length <= rows0, 'console: a tag chip filters by tag');
      $$('.anvil-role-cn-chip button')[0].click();
      await until(() => $$('a.cn-row').length === rows0, 'all again');
    }

    // ---- a sample site: tabs
    const href = $('a.cn-row').getAttribute('href');
    await page(href, () => $('.st-kpis'), 'site overview');
    ok($$('.st .vr-bars i').length === 90 && ($('.st .vr-chart') || $('.st .st-card .ui-empty')), 'site: 90-day bars and the response chart');
    ok(!$$('.ui-tabs a').find((a) => vis(a) && /Settings/.test(a.textContent)), 'site: sample sites have no Settings tab');
    await click('.st-toggle button', '24 h');
    await until(() => $('.st-toggle button.on') && /24/.test($('.st-toggle button.on').textContent), '24 h range');
    ok(true, 'site: the 24 h / 7 days switch');
    await page(href + '/traffic', () => $('.vr-colbars') || vis($$('.st .ui-empty').find(vis)), 'traffic');
    ok($$('.vr-colbars').length === 2, 'site: traffic charts');
    await page(href + '/checks', () => $$('.st-trow-host').length >= 1, 'checks');
    ok(true, 'site: the robot visits (' + $$('.st-trow-host').length + ')');
    await page(href + '/install', () => $('.vr-copybox pre'), 'install');
    const bytes = new Blob([$('.vr-copybox pre').textContent]).size;
    ok(bytes < 1024 && /sendBeacon/.test($('.vr-copybox pre').textContent), 'site: the beacon snippet is under 1 KB (' + bytes + ' bytes)');

    // ---- incidents (sample)
    await page('#incidents/all', () => $$('.in-card').length >= 1 || vis($$('.ui-empty').find(vis)), 'incidents');
    ok($$('.in-card').length >= 1, 'incidents: sample incidents (' + $$('.in-card').length + ')');
    await click('.anvil-role-seg button', 'Resolved');
    await until(() => location.hash === '#incidents/resolved', 'resolved filter');
    ok(true, 'incidents: the Resolved filter changes the address');

    // ---- add a site through the dialog
    await page('#home', () => $('.ui-page-head .anvil-role-btn-primary button'), 'console');
    await click('.ui-page-head .anvil-role-btn-primary button', 'Add site');
    const url = await until(() => $$('.dlg input').find(vis), 'add-site dialog');
    type(url, 'https://example.com/flow-' + rnd);
    type($$('.dlg input')[1], 'Flow site ' + rnd);
    await click('.dlg .anvil-role-btn-primary button', 'Start watching');
    await until(() => /^#site\/.+\/install$/.test(location.hash) && window.UI_READY && $('.vr-copybox pre'), 'the new site, Install tab', 60000);
    ok(/vr_/.test($('.vr-copybox pre').textContent), 'add site: lands on Install with its own beacon key');
    const mine = location.hash.replace(/\/install$/, '');
    await page(mine + '/settings', () => $('.st-settings input'), 'settings');
    type($('.st-settings input'), 'Flow site renamed ' + rnd);
    await click('.st-save button', 'Save');
    await until(() => /Flow site renamed/.test($('.anvil-role-st-name').textContent), 'renamed');
    ok(true, 'settings: rename saved');
    await page('#home', () => $$('a.cn-row').length >= 1, 'console (mine)');
    ok(/Your fleet/.test($('.anvil-role-cn-sub').textContent) && /Flow site renamed/.test($('.cn-table').textContent), 'console: now your own fleet');

    // ---- status page editor -> the public page
    await page('#statuspage', () => $('.sp-addr input'), 'status page editor');
    const slug = 'flow-' + rnd;
    type($('.sp-addr input'), slug);
    ok(/flow-/.test($('.sp-link').textContent), 'status page editor: the link follows the address');
    const pub = $$('.sp-ed input[type=checkbox]').pop();
    if (!pub.checked) pub.click();
    await click('.sp-ed .anvil-role-btn-primary button', 'Save');
    await until(() => location.hash === '#status/' + slug && window.UI_READY && $('.sp-banner'), 'own status page', 30000);
    ok($$('.sp-site').length >= 1, 'status page: saved and opened, with the site on it');

    // ---- heartbeat + playbook through their dialogs
    await page('#bots', () => $('.bt-robot'), 'robots');
    await click('.bt-sec-head button', 'New heartbeat');
    const hbName = await until(() => $$('.dlg input').find(vis), 'heartbeat dialog');
    type(hbName, 'Flow backup ' + rnd);
    await click('.dlg .anvil-role-btn-primary button', 'Save');
    await until(() => !$('.dlg') && /Flow backup/.test(document.body.textContent), 'heartbeat added', 30000);
    ok(/curl -fsS/.test($$('.bt-hb').find((h) => /Flow backup/.test(h.textContent)).textContent), 'heartbeat: added with its curl line');
    await click('.bt-sec-head button', 'New playbook');
    const pbName = await until(() => $$('.dlg input').find(vis), 'playbook dialog');
    type(pbName, 'Flow playbook ' + rnd);
    await click('.dlg .anvil-role-btn-primary button', 'Save playbook');
    await until(() => !$('.dlg') && /Flow playbook/.test(document.body.textContent), 'playbook added', 30000);
    ok(true, 'playbook: saved through the dialog');
    const hb = $$('.bt-hb').find((h) => /Flow backup/.test(h.textContent));
    hb.querySelector('.anvil-role-ic-trash button').click();
    await yes('Delete');
    await until(() => !/Flow backup/.test(document.body.textContent), 'heartbeat deleted', 30000);
    ok(true, 'heartbeat: delete asks, then removes it');

    // ---- delete the site
    await page(mine + '/settings', () => $('.st-danger'), 'settings');
    await click('.st-danger button', 'Delete site');
    await yes('Delete');
    await until(() => location.hash === '#home' && window.UI_READY, 'back on the console', 30000);
    ok(true, 'settings: delete site asks, then goes back to the console');

    // ---- profile + alerts
    await page('#profile', () => $('.pf-grid'), 'profile');
    type($('.pf-grid input'), 'Flow Tester Two');
    await click('.pf-grid .anvil-role-btn-primary button', 'Save');
    await until(() => /Flow Tester Two/.test($('.pf-head').textContent), 'name saved');
    ok(true, 'profile: name saved');
    type($('.pf-alerts input'), 'oncall-' + rnd + '@example.com');
    await click('.pf-alerts .anvil-role-btn-primary button', 'Save alerts');
    await sleep(1500);
    await page('#landing', () => $('.lp-hero'));
    await page('#profile', () => $('.pf-alerts input') && $('.pf-alerts input').value, 'alerts reloaded');
    ok(/oncall-/.test($('.pf-alerts input').value), 'profile: alert email saved');

    // ---- light / dark switch in the account menu
    await click('.anvil-role-avatar button');
    await click('.ui-menu .ui-seg button', 'Dark');
    ok(document.documentElement.classList.contains('ui-dark'), 'menu: Dark switches the theme');
    await click('.ui-menu .ui-seg button', 'Auto');

    // ---- sign out
    await click('.ui-menu button', 'Sign out');
    await until(() => location.hash === '#landing' && window.UI_READY && byText('.ui-header a', 'Start monitoring'), 'signed out');
    ok(true, 'sign out: back to the landing page as a visitor');

    say('PASSED');
    return { ok: true, log: log };
  } catch (e) {
    say(String(e && e.message || e));
    return { ok: false, log: log };
  }
})();
