"""Sites: the console (every site at a glance), one site in detail, and adding / changing / removing sites.

People see their own sites; people with none yet see the sample fleet read-only (common.scope).
"""
import datetime as dt

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables
import anvil.tables.query as q

from . import common as C
from . import Probe, Monitor, Incidents, Alerts, DemoData

MAX_SITES = 50
MAX_TAGS = 6


# ----------------------------------------------------------------------------------------------- helpers
def _host(url):
    h = Probe.host_of(url)
    return h[4:] if h.startswith("www.") else h


def _beacon_state(site):
    mins = C.minutes_since(site["last_beat"])
    if mins is None:
        return "none"
    if mins <= 60:
        return "live"
    if site["quiet_hours"] and mins > site["quiet_hours"] * 60:
        return "quiet"
    return "idle"


def _cells(checks, now):
    """24 hourly cells (oldest first) for the last 24 hours: up | slow | down | none."""
    cells = ["none"] * 24
    start = now - dt.timedelta(hours=24)
    for c in checks:
        i = int((C.utc(c["at"]) - start).total_seconds() // 3600)
        if 0 <= i < 24:
            st = "down" if not c["ok"] else "slow" if c["slow"] else "up"
            rank = {"none": 0, "up": 1, "slow": 2, "down": 3}
            if rank[st] > rank[cells[i]]:
                cells[i] = st
    return cells


def _pct(ok, total):
    return None if not total else round(100.0 * ok / total, 2)


def _sec(site):
    h = site["sec_headers"] or {}
    items = [{"key": k, "name": n, "why": why, "ok": bool(h.get(k))} for k, n, why in Probe.SEC_HEADERS]
    score = sum(1 for i in items if i["ok"])
    https = bool(h.get("https", (site["url"] or "").startswith("https://")))
    grade = "A" if score >= 5 and https else "B" if score >= 4 and https else "C" if score >= 3 and https else "D" if score >= 2 else "F"
    return {"items": items, "score": score, "grade": grade if h else None, "https": https}


def summary(s, checks, dailies, me, now):
    """One site for the console."""
    checks = sorted(checks, key=lambda c: C.utc(c["at"]))
    ok24 = sum(1 for c in checks if c["ok"])
    tot30 = sum(d["checks"] or 0 for d in dailies)
    fail30 = sum(d["fails"] or 0 for d in dailies)
    today = [d for d in dailies if d["day"] == now.date()]
    t = today[0] if today else None
    ms = [c["ms"] for c in checks if c["ok"] and c["ms"]]
    return {"id": s.get_id(), "name": s["name"], "url": s["url"], "host": _host(s["url"]), "status": s["status"] or "pending",
            "since": C.iso(s["status_since"]), "last_check": C.iso(s["last_check"]), "next_check": C.iso(s["next_check"]),
            "last_ms": s["last_ms"], "last_code": s["last_code"], "last_error": s["last_error"], "interval": s["interval_min"],
            "cells": _cells(checks, now), "up24": _pct(ok24, len(checks)), "up30": _pct(tot30 - fail30, tot30),
            "spark": [c["ms"] for c in checks if c["ms"]][-48:], "avg_ms": int(sum(ms) / len(ms)) if ms else None,
            "views": (t["views"] or 0) if t else 0, "visitors": (t["visitors"] or 0) if t else 0, "errors": (t["errors"] or 0) if t else 0,
            "ssl_days": Monitor.days_left(s["ssl_expires"]), "ssl_error": s["ssl_error"], "domain_days": Monitor.days_left(s["domain_expires"]),
            "beacon": _beacon_state(s), "last_beat": C.iso(s["last_beat"]), "tags": list(s["tags"] or []), "paused": bool(s["paused"]),
            "grade": _sec(s)["grade"], "demo": bool(s["is_demo"]), "can_edit": C.can_edit(s, me)}


def _group(rows, key="site"):
    out = {}
    for r in rows:
        if r[key] is not None:
            out.setdefault(r[key].get_id(), []).append(r)
    return out


def _feed(sites, checks, owners, now, limit=36):
    """The robot log: recent checks and incidents, newest first."""
    names = {s.get_id(): _host(s["url"]) for s in sites}
    lines = []
    for c in sorted(checks, key=lambda c: C.utc(c["at"]), reverse=True)[:limit]:
        sid = c["site"].get_id()
        lvl = "bad" if not c["ok"] else "warn" if c["slow"] else "ok"
        res = ("%s %s ms" % (c["code"], c["ms"])) if c["code"] else (c["error"] or "no answer")
        lines.append({"at": C.iso(c["at"]), "bot": "uptime" if c["source"] == "robot" else c["source"] or "robot", "level": lvl,
                      "text": "GET %s → %s" % (names.get(sid, "?"), res) + ("  (%s)" % c["error"] if c["error"] and c["code"] else "")})
    since = now - dt.timedelta(hours=48)
    for o in owners:
        for i in app_tables.incidents.search(owner=o, started=q.greater_than(since)):
            lines.append({"at": C.iso(i["started"]), "bot": "incident", "level": "bad" if i["severity"] == "critical" else "warn",
                          "text": "OPEN " + i["title"]})
        for i in app_tables.incidents.search(owner=o, resolved=q.greater_than(since)):
            lines.append({"at": C.iso(i["resolved"]), "bot": "incident", "level": "ok", "text": "RESOLVED %s: %s" % (i["title"], i["resolution"] or "")})
    lines.sort(key=lambda x: x["at"], reverse=True)
    return lines[:limit]


def _fleet_rows(owners):
    sites = []
    for o in owners:
        sites += list(app_tables.sites.search(tables.order_by("name"), owner=o))
    return sites


# ----------------------------------------------------------------------------------------------- the console
@anvil.server.callable(require_user=True)
def get_console(sample=None):
    me = C.require_user()
    DemoData.ensure_loaded()
    owners, mode = C.scope(me, sample)
    if mode == "sample":
        DemoData.keep_alive()
    now = C.now()
    sites = _fleet_rows(owners)
    checks, dailies = [], []
    if sites:
        checks = list(app_tables.checks.search(site=q.any_of(*sites), at=q.greater_than(now - dt.timedelta(hours=24))))
        dailies = list(app_tables.daily.search(site=q.any_of(*sites), day=q.greater_than_or_equal_to(now.date() - dt.timedelta(days=29))))
    by_c, by_d = _group(checks), _group(dailies)
    out = [summary(s, by_c.get(s.get_id(), []), by_d.get(s.get_id(), []), me, now) for s in sites]
    order = {"down": 0, "retrying": 1, "slow": 2, "pending": 3, "up": 4, "paused": 5}
    out.sort(key=lambda x: (order.get(x["status"], 3), x["name"].lower()))
    open_inc = []
    for o in owners:
        open_inc += list(app_tables.incidents.search(owner=o, resolved=None))
    ms = [c["ms"] for c in checks if c["ok"] and c["ms"]]
    totals = {"sites": len(out), "up": sum(1 for s in out if s["status"] == "up"),
              "slow": sum(1 for s in out if s["status"] == "slow"),
              "down": sum(1 for s in out if s["status"] in ("down", "retrying")),
              "paused": sum(1 for s in out if s["paused"]), "pending": sum(1 for s in out if s["status"] == "pending"),
              "incidents": len(open_inc), "critical": sum(1 for i in open_inc if i["severity"] == "critical"),
              "views": sum(s["views"] for s in out), "visitors": sum(s["visitors"] for s in out),
              "avg_ms": int(sum(ms) / len(ms)) if ms else None, "checks24": len(checks),
              "up24": _pct(sum(1 for c in checks if c["ok"]), len(checks)),
              "certs_soon": sum(1 for s in out if (s["ssl_days"] is not None and s["ssl_days"] <= 14) or s["ssl_error"])}
    tags = sorted({t for s in out for t in s["tags"]})
    demo_owner = owners[0] if mode == "sample" else None
    return {"mode": mode, "has_own": C.has_fleet(me), "sample_owner": C.name_of(demo_owner) if demo_owner else None,
            "sites": out, "totals": totals, "tags": tags, "feed": _feed(sites, checks, owners, now), "now": C.iso(now),
            "can_sample": DemoData.state() == "loaded"}


# ----------------------------------------------------------------------------------------------- one site
def _site_or_fail(site_id, me):
    s = C.row_by_id(app_tables.sites, site_id)
    if not C.can_view(s, me):
        return None
    return s


def _traffic(dailies, today):
    last7 = [d for d in dailies if d["day"] > today - dt.timedelta(days=7)]
    pages, refs, devices = {}, {}, {}
    for d in last7:
        for src, dst in ((d["pages"], pages), (d["refs"], refs), (d["devices"], devices)):
            for k, v in (src or {}).items():
                dst[k] = dst.get(k, 0) + (v or 0)
    load_n = sum(d["load_n"] or 0 for d in last7)

    def top(m, n=10):
        total = float(sum(m.values())) or 1.0
        return [{"name": k, "n": v, "pct": round(100 * v / total, 1)} for k, v in sorted(m.items(), key=lambda kv: -kv[1])[:n]]
    by_day = {d["day"]: d for d in dailies}
    days = []
    for back in range(29, -1, -1):
        day = today - dt.timedelta(days=back)
        d = by_day.get(day)
        days.append({"day": day.isoformat(), "views": (d["views"] or 0) if d else 0, "visitors": (d["visitors"] or 0) if d else 0})
    t = by_day.get(today)
    return {"views7": sum(d["views"] or 0 for d in last7), "visitors7": sum(d["visitors"] or 0 for d in last7),
            "errors7": sum(d["errors"] or 0 for d in last7),
            "load_ms": int(sum(d["load_sum"] or 0 for d in last7) / load_n) if load_n else None,
            "ttfb_ms": int(sum(d["ttfb_sum"] or 0 for d in last7) / load_n) if load_n else None,
            "today": {"views": (t["views"] or 0) if t else 0, "visitors": (t["visitors"] or 0) if t else 0,
                      "hours": [h if h is not None else None for h in ((t["hours"] if t else None) or [0] * 24)]},
            "pages": top(pages), "refs": top(refs), "devices": top(devices, 4), "days": days}


def detail(s, me):
    now = C.now()
    today = now.date()
    checks = sorted(app_tables.checks.search(site=s, at=q.greater_than(now - dt.timedelta(days=7))), key=lambda c: C.utc(c["at"]))
    dailies = list(app_tables.daily.search(site=s, day=q.greater_than_or_equal_to(today - dt.timedelta(days=89))))
    by_day = {d["day"]: d for d in dailies}
    bars = []
    for back in range(89, -1, -1):
        day = today - dt.timedelta(days=back)
        d = by_day.get(day)
        n, f = ((d["checks"] or 0), (d["fails"] or 0)) if d else (0, 0)
        bars.append({"day": day.isoformat(), "checks": n, "fails": f, "pct": _pct(n - f, n)})
    tot = sum(b["checks"] for b in bars)
    fails = sum(b["fails"] for b in bars)
    step = max(1, len(checks) // 300)
    series = [[C.iso(c["at"]), c["ms"], bool(c["ok"]), bool(c["slow"])] for c in checks[::step]]
    recent = [{"at": C.iso(c["at"]), "ok": bool(c["ok"]), "slow": bool(c["slow"]), "code": c["code"], "ms": c["ms"],
               "error": c["error"], "source": c["source"]} for c in reversed(checks[-80:])]
    errs = sorted(app_tables.jserrors.search(site=s), key=lambda r: C.utc(r["last"]), reverse=True)
    incs = sorted(app_tables.incidents.search(site=s), key=lambda r: C.utc(r["started"]), reverse=True)[:25]
    base = summary(s, [c for c in checks if C.utc(c["at"]) > now - dt.timedelta(hours=24)],
                   [d for d in dailies if d["day"] > today - dt.timedelta(days=30)], me, now)
    editable = C.can_edit(s, me)
    base.update({
        "uptime90": bars, "up90": _pct(tot - fails, tot), "series": series, "checks": recent,
        "traffic": _traffic(dailies, today), "security": _sec(s), "page_bytes": s["page_bytes"], "server": s["server"],
        "ssl_expires": C.iso(s["ssl_expires"]), "ssl_issuer": s["ssl_issuer"], "domain_expires": C.iso(s["domain_expires"]),
        "domain_error": s["domain_error"], "domain": Probe.registrable_domain(Probe.host_of(s["url"])), "inspected": C.iso(s["inspected"]),
        "jserrors": [{"id": r.get_id(), "message": r["message"], "source": r["source"], "path": r["path"], "count": r["count"],
                      "first": C.iso(r["first"]), "last": C.iso(r["last"])} for r in errs[:60]],
        "incidents": [Incidents.to_dict(r, me) for r in incs],
        "site_key": s["site_key"] if editable else "vr_xxxxxxxxxx", "endpoint": C.origin() + "/_/api/b",
        "settings": {"name": s["name"], "url": s["url"], "interval_min": s["interval_min"], "keyword": s["keyword"] or "",
                     "expect_status": s["expect_status"], "slow_ms": s["slow_ms"] or 3000, "quiet_hours": s["quiet_hours"] or 0,
                     "tags": list(s["tags"] or []), "paused": bool(s["paused"])},
        "intervals": Monitor.INTERVALS,
    })
    return base


@anvil.server.callable(require_user=True)
def get_site(site_id):
    me = C.require_user()
    s = _site_or_fail(site_id, me)
    if s is None:
        return C.fail("That site doesn't exist, or it isn't yours.")
    if s["is_demo"]:
        DemoData.keep_alive()
    return C.ok(site=detail(s, me))


# ----------------------------------------------------------------------------------------------- changing sites
def _clean(data, current=None):
    """(fields, error) from the add / settings form."""
    data = data if isinstance(data, dict) else {}
    url = Probe.normalize_url(data.get("url") if "url" in data else (current["url"] if current else ""))
    if not url:
        return None, "That address doesn't look like a public website (e.g. https://example.com)."
    name = C.text(data.get("name"), 60) or _host(url)
    try:
        interval = int(data.get("interval_min") or 60)
        slow_ms = int(data.get("slow_ms") or 3000)
        quiet = int(data.get("quiet_hours") or 0)
        expect = int(data["expect_status"]) if str(data.get("expect_status") or "").strip() else None
    except (TypeError, ValueError):
        return None, "Some of the numbers aren't numbers."
    if interval not in Monitor.INTERVALS:
        return None, "Pick how often the robots should check."
    if not 300 <= slow_ms <= 30000:
        return None, "The slow limit is between 300 and 30000 ms."
    if not 0 <= quiet <= 168:
        return None, "The silence alarm is between 0 (off) and 168 hours."
    if expect is not None and not 100 <= expect <= 599:
        return None, "An HTTP status is a number between 100 and 599."
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split(",")
    tags = []
    for t in raw_tags:
        t = C.text(t, 20).lower().replace(" ", "-")
        if t and t not in tags:
            tags.append(t)
    return {"name": name, "url": url, "interval_min": interval, "keyword": C.text(data.get("keyword"), 80) or None,
            "expect_status": expect, "slow_ms": slow_ms, "quiet_hours": quiet, "tags": tags[:MAX_TAGS]}, None


@anvil.server.callable(require_user=True)
def add_site(data):
    me = C.require_user()
    fields, err = _clean(data)
    if err:
        return C.fail(err)
    mine = list(app_tables.sites.search(owner=me))
    if len(mine) >= MAX_SITES:
        return C.fail("You're watching %d sites already, the most for now." % MAX_SITES)
    if any(s["url"] == fields["url"] for s in mine):
        return C.fail("You're already watching that address.")
    if C.rate_limited("add_site", 30, 3600):
        return C.fail("That's a lot of new sites in one hour. Try again a bit later.")
    s = app_tables.sites.add_row(owner=me, site_key=C.token(10, "vr_"), paused=False, status="pending", status_since=C.now(),
                                 next_check=C.now(), fails=0, slow_streak=0, created=C.now(), is_demo=False, **fields)
    Alerts.default_playbook(me)
    return C.ok(site_id=s.get_id())


@anvil.server.callable(require_user=True)
def update_site(site_id, data):
    me = C.require_user()
    s = C.row_by_id(app_tables.sites, site_id)
    err = C.edit_error(s, me)
    if err:
        return C.fail(err)
    fields, err = _clean(data, s)
    if err:
        return C.fail(err)
    if fields["url"] != s["url"] or fields["interval_min"] != s["interval_min"]:
        fields["next_check"] = C.now()
    s.update(**fields)
    return C.ok(site=detail(s, me))


@anvil.server.callable(require_user=True)
def set_site_paused(site_id, flag):
    me = C.require_user()
    s = C.row_by_id(app_tables.sites, site_id)
    err = C.edit_error(s, me)
    if err:
        return C.fail(err)
    if flag:
        s.update(paused=True, status="paused", status_since=C.now())
        for kind in ("down", "slow", "silence"):
            Incidents.resolve(site=s, kind=kind, how="Paused for maintenance by %s" % C.name_of(me), by_robot=False)
    else:
        s.update(paused=False, status="pending", status_since=C.now(), next_check=C.now(), fails=0, slow_streak=0)
    return C.ok(paused=bool(flag))


@anvil.server.callable(require_user=True)
def delete_site(site_id):
    me = C.require_user()
    s = C.row_by_id(app_tables.sites, site_id)
    if s is None:
        return C.ok()
    err = C.edit_error(s, me)
    if err:
        return C.fail(err)
    for table in (app_tables.checks, app_tables.daily, app_tables.visits, app_tables.jserrors, app_tables.incidents, app_tables.playbooks):
        for r in table.search(site=s):
            r.delete()
    sid = s.get_id()
    for p in app_tables.status_pages.search(owner=s["owner"]):
        if sid in (p["site_ids"] or []):
            p["site_ids"] = [x for x in p["site_ids"] if x != sid]
    s.delete()
    return C.ok()


@anvil.server.callable(require_user=True)
def check_now(site_id):
    """"Run check now": one robot visit right away (sample sites too: they're simulated)."""
    me = C.require_user()
    s = _site_or_fail(site_id, me)
    if s is None:
        return C.fail("That site doesn't exist, or it isn't yours.")
    if C.rate_limited("check_now", 20, 600):
        return C.fail("Easy on the button: the robots are already checking. Try again in a few minutes.")
    r = Monitor.run_check(s, source="manual")
    return C.ok(result=r, site=detail(s, me))


@anvil.server.callable(require_user=True)
def inspect_now(site_id):
    me = C.require_user()
    s = C.row_by_id(app_tables.sites, site_id)
    err = C.edit_error(s, me)
    if err:
        return C.fail(err)
    if C.rate_limited("inspect_now", 10, 3600):
        return C.fail("The inspector needs a break. Try again later.")
    r = Monitor.inspect(s)
    return C.ok(result=r, site=detail(s, me))


@anvil.server.callable(require_user=True)
def rotate_site_key(site_id):
    me = C.require_user()
    s = C.row_by_id(app_tables.sites, site_id)
    err = C.edit_error(s, me)
    if err:
        return C.fail(err)
    s["site_key"] = C.token(10, "vr_")
    return C.ok(site_key=s["site_key"])


@anvil.server.callable(require_user=True)
def clear_js_errors(site_id):
    me = C.require_user()
    s = C.row_by_id(app_tables.sites, site_id)
    err = C.edit_error(s, me)
    if err:
        return C.fail(err)
    for r in app_tables.jserrors.search(site=s):
        r.delete()
    Incidents.resolve(site=s, kind="jserrors", how="Errors cleared by %s" % C.name_of(me), by_robot=False)
    return C.ok()


@anvil.server.callable(require_user=True)
def beacon_status(site_id):
    """The install tab's "Is it working?" button: when the beacon last heard from the site."""
    me = C.require_user()
    s = _site_or_fail(site_id, me)
    if s is None:
        return C.fail("That site doesn't exist, or it isn't yours.")
    d = Monitor.daily_row(s) if C.can_edit(s, me) else None
    return C.ok(last_beat=C.iso(s["last_beat"]), state=_beacon_state(s), views_today=(d["views"] or 0) if d else 0)
