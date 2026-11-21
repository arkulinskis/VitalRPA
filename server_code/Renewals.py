"""Renewals: every certificate and domain in the fleet, sorted by days left (#renewals), and a private calendar feed
(/_/api/renewals.ics?t=<token>) with an all-day event per expiry and reminders 14 and 3 days before. The feed is
read again by Google/Apple/Outlook calendars on their own schedule, so new dates the robots read show up by themselves.
Tokens live in `feeds` (owner, kind "renewals", token); a new link kills the old URL (404).
"""
import datetime as dt

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C
from . import DemoData, Monitor, Probe

GROUPS = [("week", "This week"), ("month", "Within 30 days"), ("quarter", "Within 90 days"), ("later", "Later"), ("none", "No data yet")]


def _group(days, error):
    if days is None:
        return "week" if error else "none"
    if days <= 7:
        return "week"
    if days <= 30:
        return "month"
    if days <= 90:
        return "quarter"
    return "later"


def items_for(sites, me=None):
    out = []
    for s in sites:
        host = Probe.host_of(s["url"])
        base = {"site_id": s.get_id(), "site": s["name"], "host": host[4:] if host.startswith("www.") else host,
                "inspected": C.iso(s["inspected"]), "can_edit": C.can_edit(s, me), "paused": bool(s["paused"])}
        if (s["url"] or "").startswith("https://"):
            days = Monitor.days_left(s["ssl_expires"])
            out.append(dict(base, kind="cert", label="Certificate", date=C.iso(s["ssl_expires"]), days=days,
                            detail=("Issued by %s" % s["ssl_issuer"]) if s["ssl_issuer"] else "", error=s["ssl_error"] or "",
                            group=_group(days, s["ssl_error"])))
        days = Monitor.days_left(s["domain_expires"])
        out.append(dict(base, kind="domain", label="Domain", date=C.iso(s["domain_expires"]), days=days,
                        detail=Probe.registrable_domain(host), error=s["domain_error"] or "",
                        group="none" if days is None else _group(days, None)))
    out.sort(key=lambda i: (i["days"] is None, i["days"] if i["days"] is not None else 0, i["site"].lower()))
    return out


@anvil.server.callable(require_user=True)
def get_renewals(sample=None):
    me = C.require_user()
    DemoData.ensure_loaded()
    owners, mode = C.scope(me, sample)
    sites = []
    for o in owners:
        sites += list(app_tables.sites.search(tables.order_by("name"), owner=o))
    items = items_for(sites, me)
    groups = [{"key": k, "label": label, "items": [i for i in items if i["group"] == k]} for k, label in GROUPS]
    return {"mode": mode, "has_own": C.has_fleet(me), "groups": groups, "total": len(items),
            "soon": sum(1 for i in items if i["group"] in ("week", "month"))}


# ----------------------------------------------------------------------------------------------- the calendar feed
def _feed_row(me, create=True):
    row = app_tables.feeds.get(owner=me, kind="renewals")
    if row is None and create:
        row = app_tables.feeds.add_row(owner=me, kind="renewals", token=C.token(24), created=C.now())
    return row


def _links(row):
    base = C.origin()
    https = "%s/_/api/renewals.ics?t=%s" % (base, row["token"])
    webcal = "webcal://" + https.split("://", 1)[-1]
    return {"https": https, "webcal": webcal}


@anvil.server.callable(require_user=True)
def get_calendar_link():
    me = C.require_user()
    if not C.has_fleet(me):
        return C.fail("Add your own sites first: the calendar shows your certificates and domains.")
    return C.ok(**_links(_feed_row(me)))


@anvil.server.callable(require_user=True)
def rotate_calendar_link():
    me = C.require_user()
    row = _feed_row(me, create=False)
    if row is None:
        return get_calendar_link()
    row.update(token=C.token(24), created=C.now())
    return C.ok(**_links(row))


def _esc(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line):
    """RFC 5545: lines longer than 75 octets continue on the next line after CRLF + one space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def ics_for(sites, origin="", now=None):
    now = now or C.now()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//VitalRPA//Renewals//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:VitalRPA renewals", "X-WR-CALDESC:Certificates and domains your VitalRPA robots watch",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for i in items_for(sites):
        if not i["date"]:
            continue
        day = dt.date.fromisoformat(i["date"][:10])
        sid = "".join(ch if ch.isalnum() else "-" for ch in i["site_id"]).strip("-")
        what = "Certificate" if i["kind"] == "cert" else "Domain"
        summary = "%s expires: %s" % (what, i["host"] if i["kind"] == "cert" else i["detail"])
        todo = ("Renew it, or check that auto-renewal still works." if i["kind"] == "cert"
                else "Renew it at the registrar and check the card on file.")
        desc = "%s (%s). %s%s" % (i["site"], i["detail"] or i["host"], todo,
                                  ("\n%s/#site/%s" % (origin, i["site_id"])) if origin else "")
        lines += ["BEGIN:VEVENT", "UID:%s-%s-%s@vitalrpa" % (sid, i["kind"], day.strftime("%Y%m%d")), "DTSTAMP:" + stamp,
                  "DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d"), "DTEND;VALUE=DATE:" + (day + dt.timedelta(days=1)).strftime("%Y%m%d"),
                  "SUMMARY:" + _esc(summary), "DESCRIPTION:" + _esc(desc), "TRANSP:TRANSPARENT"]
        if origin:
            lines.append("URL:%s/#renewals" % origin)
        for before in (14, 3):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-P%dD" % before,
                      "DESCRIPTION:" + _esc("%s in %d days" % (summary, before)), "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


@anvil.server.http_endpoint("/renewals.ics")
def renewals_ics(t=None, **kw):
    """The private calendar feed. Unknown or rotated token -> 404."""
    row = app_tables.feeds.get(token=str(t), kind="renewals") if t else None
    if row is None or row["owner"] is None:
        return anvil.server.HttpResponse(404, "This calendar link was turned off.")
    sites = list(app_tables.sites.search(owner=row["owner"]))
    body = ics_for(sites, C.origin())
    return anvil.server.HttpResponse(200, body, headers={"Content-Type": "text/calendar; charset=utf-8",
                                                         "Cache-Control": "private, max-age=3600",
                                                         "Content-Disposition": 'inline; filename="vitalrpa-renewals.ics"'})
