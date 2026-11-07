"""Bots: the scheduled robots, cron heartbeats, and the Bots page.

Anvil Scheduled Tasks (SCHEDULED_TASKS in tools/sync_to_anvil.py) call:
  bot_tick   every 5 minutes: uptime sweep (sites whose turn has come), heartbeat watchdog, silence detector
  bot_daily  06:00 UTC: certificate + domain inspector, janitor (old raw data), morning digest
Each robot run is logged in bot_runs. Admin -> Robots can pause them all (setting "bots_paused") or run one now.
"""
import datetime as dt
import time

import anvil.email
import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables
import anvil.tables.query as q

from . import common as C
from . import Monitor, Incidents, Alerts, Beacon

TICK_BUDGET_S = 240   # a sweep stops before the next one starts
CHECKS_PER_TICK = 120

BOTS = [
    {"key": "uptime", "name": "Uptime sweeper", "icon": "pulse", "cron": "*/5 * * * *", "every": "every 5 min",
     "does": "Loads each site when its turn comes (every hour by default, so 24 check-ins a day). A failure is retried "
             "2 minutes later before anyone is alarmed, and a site that's down is checked every 5 minutes until it's back."},
    {"key": "beacon", "name": "Beacon listener", "icon": "radar", "cron": "always on", "every": "always on",
     "does": "Receives page views and JavaScript errors from the snippet on your pages: no cookies, after the page has loaded."},
    {"key": "silence", "name": "Silence detector", "icon": "bell", "cron": "*/5 * * * *", "every": "every 5 min",
     "does": "Notices when a site with the snippet stops receiving visitors (the snippet was removed, or the site is broken for real people)."},
    {"key": "heartbeat", "name": "Heartbeat watchdog", "icon": "heart", "cron": "*/5 * * * *", "every": "every 5 min",
     "does": "Notices when a backup, cron job or script misses its check-in."},
    {"key": "certs", "name": "Certificate & domain inspector", "icon": "lock", "cron": "0 6 * * *", "every": "daily 06:00 UTC",
     "does": "Reads every HTTPS certificate and the domain registration, and warns 14 and 30 days before they expire."},
    {"key": "janitor", "name": "Janitor", "icon": "database", "cron": "0 6 * * *", "every": "daily 06:00 UTC",
     "does": "Deletes raw checks after 30 days and visitor fingerprints after 2 days. Daily totals stay."},
    {"key": "digest", "name": "Morning digest", "icon": "mail", "cron": "0 6 * * *", "every": "daily 06:00 UTC",
     "does": "Emails a one-screen summary of the last 24 hours to everyone who switched it on."},
]
BOT_KEYS = {b["key"] for b in BOTS}


def paused():
    return bool(C.get_setting("bots_paused", False))


def run_bot(key, fn, demo=False):
    t0 = time.monotonic()
    try:
        handled, summary = fn()
        ok = True
    except Exception as e:  # noqa: BLE001 - log it, the next run tries again
        handled, summary, ok = 0, "Error: %s" % str(e)[:200], False
        print("bot %s failed: %r" % (key, e))
    app_tables.bot_runs.add_row(bot=key, at=C.now(), ms=int((time.monotonic() - t0) * 1000), handled=handled,
                                summary=C.text(summary, 300), ok=ok, is_demo=demo)
    return {"bot": key, "handled": handled, "summary": summary, "ok": ok}


# ----------------------------------------------------------------------------------------------- the sweeps
def sweep_uptime(budget_s=TICK_BUDGET_S):
    start, now = time.monotonic(), C.now()
    due = [s for s in app_tables.sites.search(paused=q.not_(True))
           if s["next_check"] is None or C.utc(s["next_check"]) <= now]
    due.sort(key=lambda s: C.utc(s["next_check"]) or now)
    n, problems = 0, 0
    for s in due[:CHECKS_PER_TICK]:
        if time.monotonic() - start > budget_s:
            break
        r = Monitor.run_check(s)
        n += 1
        problems += 1 if r["state"] != "up" else 0
    return n, "Checked %d site%s, %d with a problem" % (n, "" if n == 1 else "s", problems) if n else "Nothing was due"


def sweep_heartbeats():
    now, late = C.now(), 0
    for hb in app_tables.heartbeats.search(status=q.any_of("up", "waiting")):
        since = C.utc(hb["last_ping"]) or C.utc(hb["created"])
        deadline = since + dt.timedelta(minutes=(hb["period_min"] or 60) + (hb["grace_min"] or 0))
        if now > deadline:
            hb["status"] = "late"
            late += 1
            ago = "never checked in" if hb["last_ping"] is None else "last checked in %s UTC" % C.utc(hb["last_ping"]).strftime("%b %d %H:%M")
            Incidents.open_incident(hb["owner"], "heartbeat", "%s missed its check-in" % hb["name"],
                                    "Expected every %s; %s." % (_every(hb["period_min"]), ago), heartbeat=hb)
    return late, "%d heartbeat%s late" % (late, "" if late == 1 else "s")


def sweep_silence():
    now, n = C.now(), 0
    for s in app_tables.sites.search(paused=q.not_(True), last_beat=q.not_(None)):
        hours = s["quiet_hours"]
        if not hours:
            continue
        if (now - C.utc(s["last_beat"])).total_seconds() > hours * 3600:
            n += 1
            Incidents.open_incident(s["owner"], "silence", "%s: no visitors for %d hours" % (s["name"], hours),
                                    "The beacon last heard from a visitor at %s UTC. Was the snippet removed, or is the site "
                                    "broken for real visitors?" % C.utc(s["last_beat"]).strftime("%b %d %H:%M"), site=s)
    return n, "%d site%s gone quiet" % (n, "" if n == 1 else "s")


def sweep_certs(budget_s=600):
    start, n = time.monotonic(), 0
    for s in app_tables.sites.search(paused=q.not_(True)):
        if time.monotonic() - start > budget_s:
            break
        Monitor.inspect(s)
        n += 1
    return n, "Inspected %d certificate%s and domain%s" % (n, "" if n == 1 else "s", "" if n == 1 else "s")


def janitor():
    now = C.now()
    old_checks = app_tables.checks.search(at=q.less_than(now - dt.timedelta(days=30)))
    old_visits = app_tables.visits.search(day=q.less_than(now.date() - dt.timedelta(days=1)))
    old_log = app_tables.actions_log.search(at=q.less_than(now - dt.timedelta(days=90)))
    old_runs = app_tables.bot_runs.search(at=q.less_than(now - dt.timedelta(days=14)))
    n = 0
    for rows in (old_checks, old_visits, old_log, old_runs):
        for r in rows:
            r.delete()
            n += 1
    calm = 0
    for inc in app_tables.incidents.search(kind="jserrors", resolved=None):
        d = Monitor.daily_row(inc["site"]) if inc["site"] is not None else None
        if d is not None and (d["errors"] or 0) < Beacon.SPIKE_ERRORS_PER_DAY:
            Incidents.resolve(site=inc["site"], kind="jserrors", how="A calmer day: %d errors so far" % (d["errors"] or 0))
            calm += 1
    return n, "Deleted %d old raw row%s, closed %d calm error incident%s" % (n, "" if n == 1 else "s", calm, "" if calm == 1 else "s")


def digest():
    sent = 0
    for u in app_tables.users.search(digest_on=True, is_demo=q.not_(True)):
        sites = list(app_tables.sites.search(owner=u))
        if not sites:
            continue
        lines = ["Good morning! Your fleet in the last 24 hours:", ""]
        since = C.now() - dt.timedelta(hours=24)
        for s in sites:
            checks = list(app_tables.checks.search(site=s, at=q.greater_than(since)))
            up = sum(1 for c in checks if c["ok"])
            pct = "%.2f%%" % (100.0 * up / len(checks)) if checks else "no checks"
            d = Monitor.daily_row(s, (C.now() - dt.timedelta(days=1)).date())
            lines.append("- %s: %s up, %s, %d views yesterday" % (s["name"], pct, (s["status"] or "?").upper(), d["views"] or 0))
        opened = [i for i in app_tables.incidents.search(owner=u, resolved=None)]
        lines += ["", "%d open incident%s." % (len(opened), "" if len(opened) == 1 else "s")]
        lines += ["%s %s" % ("!" if i["severity"] == "critical" else "-", i["title"]) for i in opened[:10]]
        if C.origin():
            lines += ["", "Console: %s/#home" % C.origin()]
        lines += ["", "(Turn this email off in VitalRPA -> your profile.)"]
        try:
            anvil.email.send(to=u["alert_email"] or u["email"], subject="[VitalRPA] Morning digest", text="\n".join(lines),
                             from_name="VitalRPA robots")
            sent += 1
        except Exception as e:  # noqa: BLE001
            print("digest to %s failed: %r" % (u.get_id(), e))
    return sent, "Sent %d digest%s" % (sent, "" if sent == 1 else "s")


SWEEPS = {"uptime": sweep_uptime, "heartbeat": sweep_heartbeats, "silence": sweep_silence, "certs": sweep_certs,
          "janitor": janitor, "digest": digest}


# ----------------------------------------------------------------------------------------------- scheduled entry points
@anvil.server.background_task
def bot_tick():
    if paused():
        return "paused"
    return [run_bot(k, SWEEPS[k]) for k in ("uptime", "heartbeat", "silence")]


@anvil.server.background_task
def bot_daily():
    if paused():
        return "paused"
    return [run_bot(k, SWEEPS[k]) for k in ("certs", "janitor", "digest")]


@anvil.server.background_task
def bot_run_one(key):
    return run_bot(key, SWEEPS[key])


# ----------------------------------------------------------------------------------------------- heartbeats (people)
def _every(minutes):
    m = int(minutes or 0)
    if m and m % 1440 == 0:
        return "%d day%s" % (m // 1440, "" if m == 1440 else "s")
    if m and m % 60 == 0:
        return "%d hour%s" % (m // 60, "" if m == 60 else "s")
    return "%d min" % m


def hb_dict(hb, me=None):
    since = C.utc(hb["last_ping"])
    due = (since or C.utc(hb["created"])) + dt.timedelta(minutes=hb["period_min"] or 60)
    return {"id": hb.get_id(), "name": hb["name"], "token": hb["token"] if C.can_edit(hb, me) else None,
            "period_min": hb["period_min"], "grace_min": hb["grace_min"], "every": _every(hb["period_min"]),
            "last_ping": C.iso(since), "next_due": C.iso(due), "status": hb["status"], "pings": hb["pings"] or 0,
            "demo": bool(hb["is_demo"]), "can_edit": C.can_edit(hb, me)}


PERIODS = [5, 15, 30, 60, 180, 360, 720, 1440, 10080]


@anvil.server.callable(require_user=True)
def save_heartbeat(data):
    me = C.require_user()
    data = data if isinstance(data, dict) else {}
    hb = None
    if data.get("id"):
        hb = C.row_by_id(app_tables.heartbeats, data["id"])
        err = C.edit_error(hb, me)
        if err:
            return C.fail(err)
    name = C.text(data.get("name"), 60)
    if len(name) < 2:
        return C.fail("Name it (e.g. “Nightly database backup”).")
    try:
        period, grace = int(data.get("period_min") or 0), int(data.get("grace_min") or 0)
    except (TypeError, ValueError):
        return C.fail("The schedule needs numbers.")
    if period not in PERIODS:
        return C.fail("Pick how often it should check in.")
    if not 0 <= grace <= 1440:
        return C.fail("Grace time is between 0 and 1440 minutes.")
    if hb is None:
        if len(app_tables.heartbeats.search(owner=me)) >= 50:
            return C.fail("You have 50 heartbeats already.")
        hb = app_tables.heartbeats.add_row(owner=me, name=name, token=C.token(16, "hb_"), period_min=period, grace_min=grace,
                                           last_ping=None, status="waiting", pings=0, created=C.now(), is_demo=False)
        Alerts.default_playbook(me)
    else:
        hb.update(name=name, period_min=period, grace_min=grace)
    return C.ok(heartbeat=hb_dict(hb, me))


@anvil.server.callable(require_user=True)
def set_heartbeat_paused(heartbeat_id, flag):
    me = C.require_user()
    hb = C.row_by_id(app_tables.heartbeats, heartbeat_id)
    err = C.edit_error(hb, me)
    if err:
        return C.fail(err)
    hb["status"] = "paused" if flag else ("up" if hb["last_ping"] else "waiting")
    if flag:
        Incidents.resolve(heartbeat=hb, kind="heartbeat", how="Paused by %s" % C.name_of(me), by_robot=False)
    elif hb["status"] == "up":
        hb["last_ping"] = C.now()  # resuming starts a fresh period
    return C.ok(heartbeat=hb_dict(hb, me))


@anvil.server.callable(require_user=True)
def delete_heartbeat(heartbeat_id):
    me = C.require_user()
    hb = C.row_by_id(app_tables.heartbeats, heartbeat_id)
    if hb is None:
        return C.ok()
    err = C.edit_error(hb, me)
    if err:
        return C.fail(err)
    for inc in app_tables.incidents.search(heartbeat=hb):
        inc.delete()
    hb.delete()
    return C.ok()


@anvil.server.callable(require_user=True)
def ping_heartbeat_now(heartbeat_id):
    """The "Send a test ping" button: the same as the cron job calling the URL."""
    me = C.require_user()
    hb = C.row_by_id(app_tables.heartbeats, heartbeat_id)
    err = C.edit_error(hb, me)
    if err:
        return C.fail(err)
    Beacon.ping(hb)
    return C.ok(heartbeat=hb_dict(hb, me))


# ----------------------------------------------------------------------------------------------- the Bots page
def _n(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _last_runs(include_demo):
    out = {}
    for r in app_tables.bot_runs.search(tables.order_by("at", ascending=False)):
        if r["is_demo"] and not include_demo:
            continue
        if r["bot"] not in out:
            out[r["bot"]] = {"at": C.iso(r["at"]), "ms": r["ms"], "ok": bool(r["ok"])}
        if len(out) == len(BOT_KEYS):
            break
    return out


@anvil.server.callable(require_user=True)
def get_bots(sample=None):
    me = C.require_user()
    from . import DemoData
    DemoData.ensure_loaded()
    owners, mode = C.scope(me, sample)
    if mode == "sample":
        DemoData.keep_alive()
    sites, playbooks, hbs = [], [], []
    for o in owners:
        sites += list(app_tables.sites.search(owner=o))
        playbooks += list(app_tables.playbooks.search(tables.order_by("created"), owner=o))
        hbs += list(app_tables.heartbeats.search(tables.order_by("created"), owner=o))
    runs = _last_runs(mode == "sample")
    beats = [C.utc(s["last_beat"]) for s in sites if s["last_beat"] is not None]
    nexts = [C.utc(s["next_check"]) for s in sites if s["next_check"] is not None and not s["paused"]]
    fleet = {"uptime": _n(len(nexts), "site") + " on the rota",
             "beacon": "",
             "silence": _n(sum(1 for s in sites if s["quiet_hours"] and s["last_beat"]), "site") + " with an alarm",
             "heartbeat": _n(len(hbs), "heartbeat"),
             "certs": _n(sum(1 for s in sites if (s["url"] or "").startswith("https")), "HTTPS site"),
             "janitor": "keeps 30 days of raw checks", "digest": "on" if me["digest_on"] else "off for you"}
    bots = []
    for b in BOTS:
        d: dict = dict(b)
        d["last"] = runs.get(b["key"])
        d["fleet"] = fleet.get(b["key"], "")
        if b["key"] == "beacon":
            d["last_beat"] = C.iso(max(beats)) if beats else None
        if b["key"] == "uptime" and nexts:
            d["next"] = C.iso(min(nexts))
        bots.append(d)
    return {"mode": mode, "paused": paused(), "bots": bots,
            "playbooks": [Alerts.to_dict(p, me) for p in playbooks],
            "heartbeats": [hb_dict(h, me) for h in hbs],
            "log": Alerts.log_for(owners),
            "triggers": [{"key": k, "label": v} for k, v in Alerts.TRIGGERS],
            "sites": [{"id": s.get_id(), "name": s["name"]} for s in sites if s["owner"] == me],
            "ping_base": C.origin() + "/_/api/hb?t="}


# ----------------------------------------------------------------------------------------------- admin
@anvil.server.callable(require_user=True)
def admin_bots():
    C.require_admin()
    runs = [{"bot": r["bot"], "at": C.iso(r["at"]), "ms": r["ms"], "handled": r["handled"], "summary": r["summary"], "ok": bool(r["ok"])}
            for r in app_tables.bot_runs.search(tables.order_by("at", ascending=False))[:60]]
    day = C.today()
    days = list(app_tables.daily.search(day=day))
    return {"paused": paused(), "runs": runs, "bots": [{"key": b["key"], "name": b["name"], "runnable": b["key"] in SWEEPS} for b in BOTS],
            "stats": {"sites": len(app_tables.sites.search()), "heartbeats": len(app_tables.heartbeats.search()),
                      "checks_today": sum(d["checks"] or 0 for d in days), "views_today": sum(d["views"] or 0 for d in days),
                      "open_incidents": len(app_tables.incidents.search(resolved=None))}}


@anvil.server.callable(require_user=True)
def admin_set_bots_paused(flag):
    C.require_admin()
    C.set_setting("bots_paused", bool(flag))
    return C.ok(paused=bool(flag))


@anvil.server.callable(require_user=True)
def admin_run_bot(key):
    C.require_admin()
    if key not in SWEEPS:
        return C.fail("There's no robot called %s." % key)
    task = anvil.server.launch_background_task("bot_run_one", key)
    return C.ok(started=True, done=task.is_completed())
