from anvil import *

from ._anvil_designer import SiteRowTemplate
from ... import router, vr

BEACON = {"live": "\u25cf live", "idle": "idle", "quiet": "silent", "none": "none"}


class SiteRow(SiteRowTemplate):
    """Console: one site (a link to its page): light, name + host, 24-hour strip, 30-day uptime, response + sparkline,
    visitors today, certificate days, beacon state."""

    def __init__(self, **properties):
        super().__init__(**properties)
        s, n = self.item, self.dom_nodes
        down = s["status"] in ("down", "retrying")
        n["row"].setAttribute("href", router.href("site", s["id"]))
        n["row"].classList.toggle("cn-paused", bool(s["paused"]))
        n["led"].className = "vr-led s-" + (s["status"] or "pending")
        n["name"].textContent = s["name"]
        n["host"].textContent = s["host"] + ((" \u00b7 " + (s.get("last_error") or "down")) if down else " \u00b7 paused" if s["paused"] else "")
        n["up30"].textContent = vr.pct(s.get("up30"))
        n["resp"].textContent = str(s.get("last_code") or "ERR") if down else vr.ms(s.get("avg_ms"))
        n["resp"].classList.toggle("bad", down)
        n["visitors"].textContent = vr.DASH if s["beacon"] == "none" else vr.num(s.get("visitors"))
        n["visitors"].classList.toggle("faint", s["beacon"] == "none")
        if s.get("ssl_error"):
            text, cls = "ERR", "bad"
        else:
            text, cls = vr.days_tag(s.get("ssl_days"))
        n["ssl"].textContent = text
        n["ssl"].className = ("faint" if cls == "faint" else "ui-badge " + cls)
        n["beacon"].textContent = BEACON.get(s["beacon"], s["beacon"])
        n["beacon"].className = "cn-beacon " + s["beacon"]
        self.strip.show("cells", s.get("cells") or [])
        self.spark.show("spark", s.get("spark") or [])
