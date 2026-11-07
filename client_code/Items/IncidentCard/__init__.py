from anvil import *

from ._anvil_designer import IncidentCardTemplate
from ... import router, state, vr

KIND_ICON = {"down": "server", "slow": "gauge", "ssl": "lock", "domain": "globe", "silence": "eye", "jserrors": "bug", "heartbeat": "heart"}
SEV = {"critical": ("bad", "alert", "Critical"), "warning": ("warn", "info", "Warning")}


class IncidentCard(IncidentCardTemplate):
    """Incidents: one incident with its badges, timeline and (for its owner, while open) I'm on it / Mark resolved /
    a note. Changes raise x-changed so the page reloads the list."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["card"].className = "in-card " + (i.get("severity") or "") + (" resolved" if i.get("resolved") else "")
        cls, icon, text = ("good", "check", "Resolved") if i.get("resolved") else SEV.get(i.get("severity"), SEV["warning"])
        n["sev"].className = "ui-badge " + cls
        n["sev_ic"].className = "ic ic-" + icon
        n["sev_t"].textContent = text
        n["kind_ic"].className = "ic ic-" + KIND_ICON.get(i.get("kind"), "info")
        n["kind_t"].textContent = i.get("kind_label") or ""
        n["acked"].hidden = not (i.get("acked") and not i.get("resolved"))
        n["sample"].hidden = not i.get("demo")
        n["title"].textContent = i.get("title") or ""
        n["opened"].textContent = " opened %s UTC" % vr.stamp(i.get("started"))
        n["lasted"].textContent = ("lasted " if i.get("resolved") else "open for ") + vr.dur(i.get("minutes") or 0)
        n["subject"].textContent = i.get("subject") or ""
        n["subject"].setAttribute("href", router.href("site", i["site_id"]) if i.get("site_id") else "#bots")
        n["detail"].textContent = i.get("detail") or ""
        n["detail"].hidden = not i.get("detail")
        n["res"].hidden = not i.get("resolved")
        n["res_t"].textContent = " %s \u00b7 %s UTC" % (i.get("resolution") or "", vr.stamp(i.get("resolved")))
        notes = i.get("notes") or []
        self.notes_panel.items = notes
        self.notes_panel.visible = bool(notes)
        active = bool(i.get("can_edit")) and not i.get("resolved")
        self.actions.visible = self.note_row.visible = active
        self.ack_button.visible = not i.get("acked")
        state.set_control_attr(self.note_box, "aria-label", "Note for the timeline")

    @handle("ack_button", "click")
    def ack_button_click(self, **event_args):
        if state.call("ack_incident", self.item["id"]):
            state.toast("Acknowledged", "ok")
            self.parent.raise_event("x-changed")

    @handle("resolve_button", "click")
    def resolve_button_click(self, **event_args):
        if confirm("If the problem is still there, the robots will open a new incident on their next check.",
                   title="Mark as resolved?", buttons=[("Cancel", False), ("Resolve", True)], role="app-dialog"):
            if state.call("resolve_incident", self.item["id"], ""):
                state.toast("Resolved", "ok")
                self.parent.raise_event("x-changed")

    @handle("note_box", "pressed_enter")
    def note_box_pressed_enter(self, **event_args):
        self.note_button_click()

    @handle("note_button", "click")
    def note_button_click(self, **event_args):
        if state.call("add_incident_note", self.item["id"], self.note_box.text or ""):
            self.parent.raise_event("x-changed")
