import anvil.server
from anvil import *

from ._anvil_designer import PlaybookFormTemplate
from ... import state


class PlaybookForm(PlaybookFormTemplate):
    """New / edit playbook: name, when (trigger), on (a site or any), and what the robot does (email, webhook,
    recheck). Closes with True when saved."""

    def __init__(self, bots=None, playbook=None, **properties):
        super().__init__(**properties)
        d: dict = bots or {}
        pb: dict = playbook or {"name": "", "trigger": "down", "site_id": None, "actions": [{"type": "email", "to": ""}]}
        self.pb_id = pb.get("id")
        self.heading.text = "Edit playbook" if self.pb_id else "New playbook"
        self.name_box.text = pb.get("name") or ""
        self.trigger_box.items = [(t["label"], t["key"]) for t in d.get("triggers", [])]
        self.trigger_box.selected_value = pb.get("trigger") or "down"
        self.site_box.items = [("Any site", "")] + [(s["name"], s["id"]) for s in d.get("sites", [])]
        self.site_box.selected_value = pb.get("site_id") or ""
        acts = {a.get("type"): a for a in pb.get("actions") or []}
        self.email_on.checked = "email" in acts
        self.email_box.text = (acts.get("email") or {}).get("to") or ""
        self.hook_on.checked = "webhook" in acts
        self.hook_box.text = (acts.get("webhook") or {}).get("url") or ""
        self.recheck_on.checked = "recheck" in acts
        state.set_control_attr(self.trigger_box, "aria-label", "When")
        state.set_control_attr(self.site_box, "aria-label", "On")
        state.set_control_attr(self.email_box, "aria-label", "Email to")
        state.set_control_attr(self.hook_box, "aria-label", "Webhook address")

    @handle("", "show")
    def form_show(self, **event_args):
        self.name_box.focus()

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        actions = []
        if self.email_on.checked:
            actions.append({"type": "email", "to": self.email_box.text or ""})
        if self.hook_on.checked:
            actions.append({"type": "webhook", "url": self.hook_box.text or ""})
        if self.recheck_on.checked:
            actions.append({"type": "recheck"})
        data = {"id": self.pb_id, "name": self.name_box.text or "", "trigger": self.trigger_box.selected_value,
                "site_id": self.site_box.selected_value or None, "actions": actions}
        self.save_button.enabled = False
        try:
            r = anvil.server.call("save_playbook", data)
        finally:
            self.save_button.enabled = True
        if not r.get("ok"):
            self.message.text, self.message.visible = r.get("error") or "That didn't work.", True
            return
        self.raise_event("x-close-alert", value=True)
