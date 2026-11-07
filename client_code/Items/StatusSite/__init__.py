from anvil import *

from ._anvil_designer import StatusSiteTemplate
from ... import vr

LED = {"operational": "up", "degraded": "slow", "maintenance": "paused", "outage": "down"}


class StatusSite(StatusSiteTemplate):
    """Public status page: one service (light, name, uptime, state, 90 daily bars)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        s, n = self.item, self.dom_nodes
        n["led"].className = "vr-led s-" + LED.get(s.get("state"), "up")
        n["name"].textContent = s.get("name") or ""
        n["uptime"].textContent = vr.pct(s.get("uptime")) + " uptime"
        n["state"].textContent = s.get("state") or ""
        n["state"].className = "sp-state " + (s.get("state") or "")
        self.bars.show("uptimeBars", s.get("bars") or [])
