"""VitalRPA helpers every page uses: the number and time formats of the old window.VR (Python now), and the bridge to
the chart engine theme/assets/vr-charts.js (24-hour strips, uptime bars, sparklines, column bars, bar lists, the
response-time chart). Times are UTC everywhere ("robot time"): stamp() and hhmm() read the ISO text as it is.

    vr.draw(dom_node, kind, data, opts)    draw a chart into a node (Components/Chart does it for templates)
    vr.copy(text)                          copy to the clipboard -> True / False
"""
import json

from anvil.js import window

STATUS = {"up": "Up", "slow": "Slow", "retrying": "Retrying", "down": "Down", "paused": "Paused", "pending": "Pending"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DASH = "—"


def _trim(x):
    return str(int(x)) if float(x) == int(x) else ("%.1f" % x)


def num(n):
    if n is None:
        return DASH
    s, neg = str(int(round(abs(n)))), n < 0
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ("-" if neg else "") + ",".join(parts)


def ms(n):
    if n is None:
        return DASH
    if n >= 1000:
        return ("%.1f s" if n >= 10000 else "%.2f s") % (n / 1000.0)
    return "%d ms" % int(round(n))


def pct(p):
    if p is None:
        return DASH
    if p >= 99.995:
        return "100%"
    return ("%.2f%%" if p >= 99 else "%.1f%%") % p


def size(n):
    if n is None:
        return DASH
    if n >= 1048576:
        return "%.1f MB" % (n / 1048576.0)
    if n >= 1024:
        return "%d KB" % int(round(n / 1024.0))
    return "%d B" % n


def every(m):
    if m >= 1440:
        return _trim(m / 1440.0) + " day"
    if m >= 60:
        return _trim(m / 60.0) + " h"
    return "%d min" % m


def per_day(m):
    return int(round(1440.0 / m))


def check_ins(m):
    n = per_day(m)
    return "1 check-in a day" if n == 1 else "%d check-ins a day" % n


def dur(minutes):
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return "%d min" % minutes
    if minutes < 1440:
        rest = minutes % 60
        return "%d h %s" % (minutes // 60, ("%d min" % rest) if rest else "")
    return "%d d %d h" % (minutes // 1440, (minutes % 1440) // 60)


def hhmm(iso):
    return iso[11:16] if iso else DASH


def stamp(iso):
    """'Nov 6 14:05' in UTC (the ISO text from the server is already UTC)."""
    if not iso:
        return DASH
    return "%s %d %s" % (MONTHS[int(iso[5:7]) - 1], int(iso[8:10]), iso[11:16])


def day(iso_day):
    return "%s %d" % (MONTHS[int(iso_day[5:7]) - 1], int(iso_day[8:10]))


def date(iso):
    """'6 Nov 2026'."""
    if not iso:
        return DASH
    return "%d %s %s" % (int(iso[8:10]), MONTHS[int(iso[5:7]) - 1], iso[:4])


def until(iso):
    if not iso:
        return ""
    m = int(round((window.Date.parse(iso) - window.Date.now()) / 60000.0))
    if m <= 0:
        return "due now"
    return "in %d min" % m if m < 60 else "in %d h %d min" % (m // 60, m % 60)


def days_tag(n, warn=14):
    """(text, badge class) for days left on a certificate or domain."""
    if n is None:
        return DASH, "faint"
    return "%dd" % n, "bad" if n <= 3 else "warn" if n <= warn else ""


def utc_hour():
    return int((window.Date.now() // 3600000) % 24)


def clock_text():
    secs = int(window.Date.now() // 1000) % 86400
    return "UTC %02d:%02d:%02d" % (secs // 3600, (secs // 60) % 60, secs % 60)


def draw(node, kind, data, opts=None):
    window.VR.render(node, kind, json.dumps(data), json.dumps(opts or {}))


def snippet(key, endpoint):
    return window.VR.snippet(key, endpoint)


def byte_size(text):
    return int(window.VR.bytes(text))


def copy(text):
    return bool(window.VR.copy(text))
