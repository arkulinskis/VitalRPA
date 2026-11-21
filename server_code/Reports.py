"""Client reports: one private link per client (a client = a tag), with a month of uptime, downtime, response time,
certificates, domains, header grades, visitors and "what the robots handled". Printable to PDF from the browser.

Owners manage them on #reports (list_reports / report_for_tag / save_report / rotate_report_link / delete_report).
Anyone with the link reads #report/<token> (get_report): only the report owner's sites with that tag (or the
chosen site ids), never notes, emails, beacon keys or another owner's sites. A new link kills the old one.
The sample fleet has one report, token "sample" (DemoData.SAMPLE_REPORT).
"""
import datetime as dt

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables
import anvil.tables.query as q

from . import common as C
from . import DemoData, Incidents, Monitor, Probe

MAX_REPORTS = 40
MONTHS_BACK = 6
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


# ----------------------------------------------------------------------------------------------- helpers
def _sites_for(r):
    owner = r["owner"]
    rows = list(app_tables.sites.search(tables.order_by("name"), owner=owner))
    ids = list(r["site_ids"] or [])
    if ids:
        return [s for s in rows if s.get_id() in ids]
    tag = r["tag"] or ""
    return [s for s in rows if not tag or tag in (s["tags"] or [])]


def _to_dict(r):
    sites = _sites_for(r)
    return {"id": r.get_id(), "token": r["token"], "title": r["title"], "tag": r["tag"] or "", "note": r["note"] or "",
            "created": C.iso(r["created"]), "views": r["views"] or 0, "sites": len(sites), "demo": bool(r["is_demo"])}


def _month_start(d):
    return dt.date(d.year, d.month, 1)


def _add_months(d, n):
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def _months(today):
    """The current month (so far) and the 6 full months before it, newest first."""
    first = _month_start(today)
    out = []
    for back in range(0, MONTHS_BACK + 1):
        d = _add_months(first, -back)
        out.append({"key": "%04d-%02d" % (d.year, d.month),
                    "label": "%s %d%s" % (MONTH_NAMES[d.month - 1], d.year, " (so far)" if back == 0 else "")})
    return out


def _parse_month(key, today):
    try:
        y, m = [int(x) for x in str(key).split("-")]
        d = dt.date(y, m, 1)
    except (TypeError, ValueError):
        return None
    allowed = {x["key"] for x in _months(today)}
    return d if "%04d-%02d" % (d.year, d.month) in allowed else None


def _clip_minutes(start, end, lo, hi):
    a, b = max(start, lo), min(end, hi)
    return max(0, int((b - a).total_seconds() // 60))


def _tags(me):
    counts = {}
    for s in app_tables.sites.search(owner=me):
        for t in s["tags"] or []:
            counts[t] = counts.get(t, 0) + 1
    return [{"tag": t, "sites": n} for t, n in sorted(counts.items())]


# ----------------------------------------------------------------------------------------------- the report itself
def build(r, month_key=None):
    today = C.today()
    first = _parse_month(month_key, today) if month_key else None
    if first is None:
        first = _add_months(_month_start(today), -1)  # the last full month
    nxt = _add_months(first, 1)
    lo = dt.datetime(first.year, first.month, first.day, tzinfo=dt.timezone.utc)
    hi = min(dt.datetime(nxt.year, nxt.month, nxt.day, tzinfo=dt.timezone.utc), C.now())
    sites = _sites_for(r)
    rows, handled = [], []
    tot_checks = tot_fails = tot_ms = tot_down = tot_views = tot_visitors = 0
    beacon_any = False
    for s in sites:
        days = list(app_tables.daily.search(site=s, day=q.all_of(q.greater_than_or_equal_to(first), q.less_than(nxt))))
        checks = sum(d["checks"] or 0 for d in days)
        fails = sum(d["fails"] or 0 for d in days)
        ms_sum = sum(d["ms_sum"] or 0 for d in days)
        views = sum(d["views"] or 0 for d in days)
        visitors = sum(d["visitors"] or 0 for d in days)
        incs = [i for i in app_tables.incidents.search(site=s, started=q.less_than(hi))
                if C.utc(i["resolved"]) is None or C.utc(i["resolved"]) > lo]
        down = sum(_clip_minutes(C.utc(i["started"]), C.utc(i["resolved"]) or C.now(), lo, hi) for i in incs if i["kind"] == "down")
        for i in incs:
            started, resolved = C.utc(i["started"]), C.utc(i["resolved"])
            handled.append({"at": C.iso(started), "site": s["name"], "kind": i["kind"],
                            "kind_label": Incidents.KINDS.get(i["kind"], (i["kind"], ""))[0], "title": i["title"],
                            "minutes": int(((resolved or C.now()) - started).total_seconds() // 60),
                            "open": resolved is None, "ended": i["resolution"] or ("Still being handled" if resolved is None else "Resolved")})
        sec = Probe.sec_grade(s["sec_headers"], s["url"] or "")
        rows.append({"name": s["name"], "host": Probe.host_of(s["url"]), "uptime": None if not checks else round(100.0 * (checks - fails) / checks, 3),
                     "checks": checks, "down_min": down, "avg_ms": int(ms_sum / checks) if checks else None,
                     "ssl_days": Monitor.days_left(s["ssl_expires"]), "ssl_issuer": s["ssl_issuer"] or "",
                     "https": (s["url"] or "").startswith("https://"), "domain_expires": C.iso(s["domain_expires"]),
                     "domain_days": Monitor.days_left(s["domain_expires"]), "grade": sec["grade"],
                     "views": views, "visitors": visitors, "beacon": views > 0, "paused": bool(s["paused"])})
        tot_checks += checks
        tot_fails += fails
        tot_ms += ms_sum
        tot_down += down
        tot_views += views
        tot_visitors += visitors
        beacon_any = beacon_any or views > 0
    handled.sort(key=lambda x: x["at"], reverse=True)
    head = {"uptime": None if not tot_checks else round(100.0 * (tot_checks - tot_fails) / tot_checks, 3),
            "incidents": len(handled), "down_min": tot_down, "checks": tot_checks,
            "avg_ms": int(tot_ms / tot_checks) if tot_checks else None, "views": tot_views, "visitors": tot_visitors,
            "beacon": beacon_any}
    return {"title": r["title"], "note": r["note"] or "", "tag": r["tag"] or "", "month": "%04d-%02d" % (first.year, first.month),
            "month_label": "%s %d" % (MONTH_NAMES[first.month - 1], first.year), "months": _months(today),
            "partial": first == _month_start(today), "head": head, "sites": rows, "handled": handled[:60],
            "demo": bool(r["is_demo"]), "generated": C.iso(C.now())}


@anvil.server.callable
def get_report(token, month=None):
    """Public: the report behind a private link. A turned-off (rotated or deleted) link gets a friendly message."""
    token = C.text(token, 40)
    if token == DemoData.SAMPLE_REPORT["token"]:
        DemoData.ensure_loaded()
        DemoData.ensure_extras()
        DemoData.keep_alive()
    r = app_tables.reports.get(token=token) if token else None
    if r is None:
        return C.fail("This report link was turned off, or it never existed. Ask whoever sent it for a new one.")
    if month is None:
        r["views"] = (r["views"] or 0) + 1
    return C.ok(report=build(r, month))


# ----------------------------------------------------------------------------------------------- the owner's side
@anvil.server.callable(require_user=True)
def list_reports():
    me = C.require_user()
    DemoData.ensure_extras()
    rows = list(app_tables.reports.search(tables.order_by("created", ascending=False), owner=me))
    return {"reports": [_to_dict(r) for r in rows], "tags": _tags(me), "has_fleet": C.has_fleet(me),
            "sample": app_tables.reports.get(token=DemoData.SAMPLE_REPORT["token"]) is not None}


def _clean(data, me):
    data = data if isinstance(data, dict) else {}
    title = C.text(data.get("title"), 80)
    if len(title) < 2:
        return None, "Give the report a name your client recognises (e.g. “Harbor Dental: website care”)."
    tag = C.text(data.get("tag"), 20).lower().lstrip("#")
    if tag and tag not in {t["tag"] for t in _tags(me)}:
        return None, "None of your sites has the tag #%s yet." % tag
    return {"title": title, "tag": tag, "note": C.text(data.get("note"), 300, multiline=True)}, None


@anvil.server.callable(require_user=True)
def save_report(data):
    me = C.require_user()
    fields, err = _clean(data, me)
    if err:
        return C.fail(err)
    rid = (data or {}).get("id") if isinstance(data, dict) else None
    if rid:
        r = C.row_by_id(app_tables.reports, rid)
        err = C.edit_error(r, me)
        if err:
            return C.fail(err)
        r.update(**fields)
    else:
        if not C.has_fleet(me):
            return C.fail("Add your own sites first: a report shows your sites to your client.")
        if len(app_tables.reports.search(owner=me)) >= MAX_REPORTS:
            return C.fail("You have %d reports already, the most for now." % MAX_REPORTS)
        r = app_tables.reports.add_row(owner=me, token=C.token(16), site_ids=[], created=C.now(), views=0, is_demo=False, **fields)
    return C.ok(report=_to_dict(r))


@anvil.server.callable(require_user=True)
def report_for_tag(tag):
    """The Console's "Client report for #tag": the existing report for that tag, or a new one named after it."""
    me = C.require_user()
    tag = C.text(tag, 20).lower().lstrip("#")
    for r in app_tables.reports.search(owner=me, tag=tag):
        return C.ok(report=_to_dict(r), created=False)
    title = ("#%s: website care" % tag) if tag else "Website care"
    res = save_report({"title": title, "tag": tag, "note": ""})
    if res.get("ok"):
        res["created"] = True
    return res


@anvil.server.callable(require_user=True)
def rotate_report_link(report_id):
    me = C.require_user()
    r = C.row_by_id(app_tables.reports, report_id)
    err = C.edit_error(r, me)
    if err:
        return C.fail(err)
    r.update(token=C.token(16), views=0)
    return C.ok(report=_to_dict(r))


@anvil.server.callable(require_user=True)
def delete_report(report_id):
    me = C.require_user()
    r = C.row_by_id(app_tables.reports, report_id)
    if r is None:
        return C.ok()
    err = C.edit_error(r, me)
    if err:
        return C.fail(err)
    r.delete()
    return C.ok()
