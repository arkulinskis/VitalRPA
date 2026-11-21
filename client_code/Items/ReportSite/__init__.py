from anvil import *

from ._anvil_designer import ReportSiteTemplate
from ... import vr


class ReportSite(ReportSiteTemplate):
    """Client report: one site's month (uptime, downtime, average response, certificate, domain, header grade, and
    views/visitors when the beacon is on)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        s, n = self.item, self.dom_nodes
        n["name"].textContent = s.get("name") or ""
        n["host"].textContent = s.get("host") or ""
        n["uptime"].textContent = vr.pct(s.get("uptime")) if s.get("checks") else "no checks"
        n["uptime"].className = "bad" if (s.get("uptime") is not None and s["uptime"] < 99) else ""
        n["down"].textContent = vr.dur(s.get("down_min") or 0) if s.get("down_min") else "none"
        n["ms"].textContent = vr.ms(s.get("avg_ms"))
        if not s.get("https"):
            n["cert"].textContent = "no HTTPS"
        elif s.get("ssl_days") is None:
            n["cert"].textContent = vr.DASH
        else:
            d = s["ssl_days"]
            n["cert"].textContent = "%d days left%s" % (d, (" \u00b7 " + s["ssl_issuer"]) if s.get("ssl_issuer") else "")
            n["cert"].className = "bad" if d <= 7 else "warn" if d <= 21 else ""
        n["domain"].textContent = vr.date(s.get("domain_expires")) if s.get("domain_expires") else vr.DASH
        n["domain"].className = "warn" if (s.get("domain_days") is not None and s["domain_days"] <= 30) else ""
        n["grade"].textContent = s.get("grade") or vr.DASH
        n["traffic_box"].hidden = not s.get("beacon")
        n["traffic"].textContent = "%s / %s" % (vr.num(s.get("views")), vr.num(s.get("visitors")))
