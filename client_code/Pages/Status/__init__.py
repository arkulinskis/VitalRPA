import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import StatusTemplate
from ... import router, state, vr

TEXT = {"operational": "All systems operational", "degraded": "Some systems are slow", "maintenance": "Scheduled maintenance",
        "outage": "Part of the service is down"}
LED = {"operational": "up", "degraded": "slow", "maintenance": "paused", "outage": "down"}


class Status(StatusTemplate):
    """#status/<slug>: a public status page anyone can open, signed in or not. Overall state, each chosen site with 90
    days of uptime, and the last 14 days of outages. Nothing private. Edited on #statuspage."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        r = anvil.server.call("get_status_page", args[0] if args else "")
        ok = bool(r.get("ok"))
        self.missing.visible, self.main.visible = not ok, ok
        if not ok:
            self.missing_text.text = r.get("error") or "There's no public status page at this address."
            return
        p = r["page"]
        window.document.title = p["title"] + " status"
        n = self.dom_nodes
        self.title.text = p["title"]
        self.meta_line.text = "Status page" + (" \u00b7 sample" if p.get("demo") else "")
        self.intro.text = p.get("intro") or ""
        self.intro.visible = bool(p.get("intro"))
        self.edit_link.visible = bool(p.get("mine"))
        self.private_note.visible = not p.get("public")
        overall = p.get("overall") or "operational"
        n["banner"].className = "sp-banner " + overall
        n["banner_led"].className = "vr-led s-" + LED.get(overall, "up")
        n["banner_text"].textContent = TEXT.get(overall, overall)
        self.sites_panel.items = p["sites"]
        self.sites_part.visible = bool(p["sites"])
        self.no_sites.visible = not p["sites"]
        self.inc_panel.items = p["incidents"]
        self.no_inc.visible = not p["incidents"]
        n["updated"].textContent = vr.stamp(p.get("updated"))
