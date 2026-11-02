# VitalRPA

Website robots for people and teams who run many websites. Robots check every site around the clock (24 check-ins a
day by default, every 5 minutes if it matters): status code, response time, a keyword that must be on the page, the TLS
certificate, the domain's expiry and the security headers. None of that needs any code on the site. An optional
inline beacon (under 1 KB, no cookies, runs after the page has loaded) adds real visitors, page-load times and the
JavaScript errors visitors hit. When something breaks, **playbooks** (the RPA part) act: email, webhooks for
Slack/Teams/Discord/Zapier, or a second-robot recheck. Built on [Anvil](https://anvil.works).

- **App repo:** github.com/arkulinskis/VitalRPA (branch `master`). Anvil pulls `master`.
- **Live:** https://vitalrpa.com (DNS pointed at Anvil on 2026-10-29). Listed in the Addanapp portfolio (Working businesses).

## What it does

**For visitors (signed out):** a landing page (promise, how it works, what the robots check, "lighter than your favicon",
FAQ), public status pages (`#status/<slug>`, e.g. the sample `#status/northwind`), sign-up, feedback, Privacy & Terms.

**For members:**
- **Console** (`#home`): every site with a status light, a 24-hour strip (one cell per hour), 30-day uptime, average
  response + sparkline, visitors today, certificate days left, beacon state; KPI tiles (sites up, open incidents,
  visitors, average response, certificates expiring); tag filter + search; the **robot log** (latest checks and
  incidents, terminal style); refreshes every minute. A UTC clock sits in the header and the open-incident count on the nav.
- **Sample fleet:** people with no sites of their own see a read-only demo fleet (Mara Lindqvist's agency: 8 fictional
  `.example` sites with an outage, a slow site, an expiring certificate, a silent beacon, a late cron job). `#home/sample`
  opens it any time.
- **Add a site** (dialog): address, name, check interval (shows check-ins per day), keyword, expected status, slow limit,
  tags. The first check runs immediately, then the install tab opens.
- **Site page** (`#site/<id>/<tab>`): overview (uptime KPIs, 90-day uptime bars, response-time chart with hover
  crosshair and failed-check marks, TLS certificate, domain, security-header grade A-F, page weight/server, incidents),
  traffic (views/visitors per day and per hour, top pages, referrers, devices, real load time and TTFB), checks (last 80
  robot visits), JS errors (grouped, clear all), install (the snippet with copy, test beacon, "is it working?",
  where-to-paste tips), settings (all check settings, rotate beacon key, delete). Buttons: run check now, inspect TLS &
  domain, pause/resume (maintenance).
- **Incidents** (`#incidents[/resolved|/all]`): opened/closed by the robots, severity, timeline of notes, "I'm on it"
  (acknowledge), notes, mark resolved.
- **Robots** (`#bots`): the built-in robots (uptime sweeper, beacon listener, silence detector, heartbeat watchdog,
  certificate & domain inspector, janitor, morning digest) with schedule and last run; **playbooks** (if trigger [on site]
  → email / webhook / recheck; on/off, test run, edit, delete); **cron heartbeats** (a ping URL + curl command for
  backups/cron jobs; late = incident; test ping, pause); the log of everything the robots did.
- **Status page** (`#statuspage`): address, title, intro, which sites, public or private.
- **Profile:** name, theme, password reset, alert email, morning digest.
- New accounts get two playbooks: "email me when something breaks" and "...when it's fixed".

**For admins** (`#admin`; arkulinskis@gmail.com becomes an admin on first sign-in):
- **Robots:** totals (sites, heartbeats, checks and page views today, open incidents), pause/resume all robots, run any
  robot now, recent runs.
- **Feedback inbox, Users, Demo data** (load/remove the sample fleet), as in every template app.

## The robots (Anvil Scheduled Tasks)

`SCHEDULED_TASKS` in `tools/sync_to_anvil.py` writes them into anvil.yaml:
- `bot_tick` every 5 minutes: uptime sweep (sites whose `next_check` is due), heartbeat watchdog, silence detector.
- `bot_daily` at 06:00 UTC: certificate + domain inspector, janitor (checks > 30 days, fingerprints > 2 days), digest.

Rules: a failed check is retried after 2 minutes (status `retrying`); the 2nd failure in a row = `down` + incident;
while down, checks every 5 minutes; 3 slow checks in a row = `slow` incident; certificate ≤ 14 days, domain ≤ 30 days
= incident; a site with the beacon and a silence alarm (`quiet_hours`) that hears no visitor for that long = incident;
50 JS errors in a day = incident. Every incident open/close runs the owner's playbooks.

## The beacon

`/_/api/b` (Beacon.py) receives `sendBeacon` pings: `k` site key, `t` v (view) or e (error), `p` path, `r` referrer
host, `w` width, `l` load ms, `f` TTFB ms, `m`/`s` error message/source. Bots are ignored by user agent. Unique visitors
= sha256(daily secret + IP + user agent), stored 2 days in `visits`; everything else is added to the site's `daily` row.
Heartbeats ping `/_/api/hb?t=<token>`.

## Setting it up in Anvil (once)

1. In the Anvil editor: **Create app → Clone from GitHub**, and paste `https://github.com/arkulinskis/VitalRPA`.
2. **Users** service: email + password and "Continue with Google", sign-up allowed (already set in `anvil.yaml`; check it). **Email** service: on.
3. If it shows a **Schema Mismatch** alert, choose **"The schema of the source code is correct"** so Anvil creates the tables.
4. **Scheduled Tasks**: check that `bot_tick` (every 5 minutes) and `bot_daily` (daily 06:00) are listed; add them there if not.
5. **Run** it and sign up with **arkulinskis@gmail.com** straight away (that account becomes the admin).
6. **Publish** (Publish → public URL, or your own domain).

<!-- libraries:start -->
## Libraries and outside services

What this project uses besides its own code. Generated by `APP_MAKER/tools/libraries.py`; to change it, edit `APP_MAKER/libraries/catalog.py` and re-run the script.

| Name | How it gets in | Used here for |
|---|---|---|
| [Google Fonts](https://fonts.google.com) | Loaded from a CDN | IBM Plex Mono, IBM Plex Sans |

**Built into the browser:** localStorage, Clipboard.

**Anvil platform:** Anvil, Anvil Data Tables, Anvil JS bridge (anvil.js), Anvil Users, Anvil HTTP, Anvil Email.

**Build and test tools (not shipped):** Node.js, PyYAML, Headless Chrome (DevTools Protocol).

<!-- libraries:end -->

## Working on it

See `.claude/skills/vitalrpa/SKILL.md`. In short:

```
python -I tools/check.py --ui                    # syntax, server tests, headless UI tests → ALL CHECKS PASSED
python -I tools/preview/devserver.py 8765        # the app on in-memory data: http://localhost:8765/  (?as=ana#home, ?as=admin#admin)
python tools/deploy.py                           # dry run (needs PyYAML, so no -I)
python tools/deploy.py --push "Message"          # deploy: commit + push to GitHub, Anvil pulls it
```

## Project layout

```
web/            core.js/core.css (engine + design tokens), app.js (header with UTC clock, footer, extra icons),
                pages/_shared.html (window.VR: status lights, charts, tooltips), pages/*.html
client_code/    Main.py (the only Anvil form: bridge to the server, sign-in), legal.py
server_code/    common.py (+ fleet scope helpers), Accounts.py, Feedback.py, Admin.py, DemoData.py (sample fleet),
                Probe.py (HTTP/TLS/RDAP, simulation), Monitor.py (one check + incidents), Incidents.py, Alerts.py (playbooks),
                Beacon.py (HTTP endpoints), Bots.py (scheduled robots, heartbeats, Robots page), Sites.py (console, site page),
                StatusPage.py, legal_server.py
assets/         icon.svg (pulse line on a dark tile) + generated PNG icons
tools/          sync_to_anvil.py (settings, tables, scheduled tasks), deploy.py, check.py, preview/ (dev server, UI tests, screenshots), testing/
```
