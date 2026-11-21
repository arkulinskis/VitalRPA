from anvil import *

from ._anvil_designer import RenewalRowTemplate
from ... import state, vr


class RenewalRow(RenewalRowTemplate):
    """#renewals: one certificate or domain (site, kind, date, days-left badge with a label, issuer or registrable
    domain, when the robots last read it, Inspect now for owners). Raises x-inspected on the panel."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["site"].textContent = i.get("site") or ""
        n["host"].textContent = i.get("host") or ""
        n["kind"].textContent = i.get("label") or ""
        n["kind"].className = "ui-badge rn-kind " + ("brand" if i.get("kind") == "cert" else "")
        n["date"].textContent = vr.date(i.get("date")) if i.get("date") else "no date"
        d = i.get("days")
        if d is None:
            text, cls = ("problem" if i.get("error") else "unknown"), ("bad" if i.get("error") else "")
        elif d < 0:
            text, cls = "expired %d day%s ago" % (-d, "" if d == -1 else "s"), "bad"
        else:
            text = "today" if d == 0 else "%d day%s left" % (d, "" if d == 1 else "s")
            cls = "bad" if d <= 7 else "warn" if d <= 30 else "good"
        n["days"].textContent = text
        n["days"].className = "ui-badge rn-days " + cls
        n["detail"].textContent = i.get("error") or i.get("detail") or ""
        n["read"].textContent = (" \u00b7 read " + state.ago(i["inspected"])) if i.get("inspected") else " \u00b7 not read yet"
        self.inspect_button.visible = bool(i.get("can_edit"))
        state.set_control_attr(self.inspect_button, "aria-label", "Inspect %s now" % (i.get("site") or "this site"))

    @handle("inspect_button", "click")
    def inspect_button_click(self, **event_args):
        self.inspect_button.enabled = False
        try:
            r = state.call("inspect_now", self.item["site_id"])
        finally:
            self.inspect_button.enabled = True
        if r:
            state.toast("Read again just now", "ok")
            self.parent.raise_event("x-inspected")
