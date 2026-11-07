from anvil import *

from ._anvil_designer import StatusIncidentTemplate
from ... import vr


class StatusIncident(StatusIncidentTemplate):
    """Public status page: one outage from the last 14 days and how it ended."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["box"].className = "sp-inc-item" + ("" if i.get("resolved") else " open")
        n["title"].textContent = i.get("title") or ""
        n["when"].textContent = vr.stamp(i.get("started")) + " UTC" + (
            (" \u2192 resolved %s UTC" % vr.stamp(i["resolved"])) if i.get("resolved") else " \u00b7 ongoing")
        n["res"].textContent = i.get("resolution") or ""
        n["res"].hidden = not i.get("resolution")
