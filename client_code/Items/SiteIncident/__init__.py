from anvil import *

from ._anvil_designer import SiteIncidentTemplate
from ... import vr

SEV = {"critical": ("bad", "alert", "Critical"), "warning": ("warn", "info", "Warning")}


class SiteIncident(SiteIncidentTemplate):
    """Site -> Overview: one recent incident (links to the Incidents page)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        cls, icon, text = ("good", "check", "Resolved") if i.get("resolved") else SEV.get(i.get("severity"), SEV["warning"])
        n["sev"].className = "ui-badge " + cls
        n["sev_ic"].className = "ic ic-" + icon
        n["sev_t"].textContent = text
        n["title"].textContent = i.get("title") or ""
        n["when"].textContent = "%s \u00b7 %s" % (vr.stamp(i.get("started")), vr.dur(i.get("minutes") or 0))
        n["link"].setAttribute("href", "#incidents/all" if i.get("resolved") else "#incidents")
