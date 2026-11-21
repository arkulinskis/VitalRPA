from anvil import *

from ._anvil_designer import ReportIncidentTemplate
from ... import vr


class ReportIncident(ReportIncidentTemplate):
    """Client report: one thing the robots handled this month (when, what, how long, how it ended)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["at"].textContent = vr.stamp(i.get("at"))
        n["title"].textContent = i.get("title") or ""
        n["ended"].textContent = "%s \u00b7 %s" % (i.get("ended") or "", vr.dur(i.get("minutes") or 0))
        n["badge"].textContent = "open" if i.get("open") else (i.get("kind_label") or "")
        n["badge"].className = "ui-badge " + ("bad" if i.get("open") else "good" if i.get("kind") == "down" else "")
