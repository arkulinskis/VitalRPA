from anvil import *

from ._anvil_designer import PlaybookRowTemplate
from ... import state


class PlaybookRow(PlaybookRowTemplate):
    """Robots: one playbook (on/off switch, IF trigger ON site -> actions, how often it fired; Test, Edit, Delete)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        p, n = self.item, self.dom_nodes
        n["row"].classList.toggle("off", not p.get("enabled"))
        self.on_box.checked = bool(p.get("enabled"))
        self.on_box.enabled = bool(p.get("can_edit"))
        state.set_control_attr(self.on_box, "aria-label", "Playbook on: " + (p.get("name") or ""))
        n["name"].textContent = p.get("name") or ""
        n["sample"].hidden = not p.get("demo")
        n["trigger"].textContent = p.get("trigger_label") or ""
        n["site"].textContent = p.get("site_name") or ""
        self.acts_panel.items = p.get("actions") or []
        n["meta"].textContent = "fired %d\u00d7%s" % (p.get("fired") or 0, (" \u00b7 last " + state.ago(p["last_fired"])) if p.get("last_fired") else "")
        self.buttons.visible = bool(p.get("can_edit"))
        state.set_control_attr(self.delete_button, "aria-label", "Delete " + (p.get("name") or "playbook"))

    @handle("on_box", "change")
    def on_box_change(self, **event_args):
        flag = bool(self.on_box.checked)
        if state.call("set_playbook_enabled", self.item["id"], flag):
            state.toast("Playbook on" if flag else "Playbook off", "ok")
            self.parent.raise_event("x-changed")
        else:
            self.on_box.checked = not flag

    @handle("test_button", "click")
    def test_button_click(self, **event_args):
        self.test_button.enabled = False
        try:
            r = state.call("test_playbook", self.item["id"])
        finally:
            self.test_button.enabled = True
        if not r:
            return
        bad = [x for x in r["results"] if not x.get("ok")]
        if bad:
            state.toast(bad[0].get("result") or "The test failed", "error")
        else:
            state.toast("Test sent: " + ", ".join(x.get("result") or "" for x in r["results"]), "ok")
        self.parent.raise_event("x-changed")

    @handle("edit_button", "click")
    def edit_button_click(self, **event_args):
        self.parent.raise_event("x-edit", playbook=self.item)

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        if confirm("Delete \u201c%s\u201d?" % self.item["name"], buttons=[("Cancel", False), ("Delete", True)], role="app-dialog"):
            if state.call("delete_playbook", self.item["id"]):
                self.parent.raise_event("x-changed")
