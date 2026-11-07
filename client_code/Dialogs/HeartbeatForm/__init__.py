import anvil.server
from anvil import *

from ._anvil_designer import HeartbeatFormTemplate
from ... import state

PERIODS = [(5, "5 min"), (15, "15 min"), (30, "30 min"), (60, "1 hour"), (180, "3 hours"), (360, "6 hours"), (720, "12 hours"),
           (1440, "1 day"), (10080, "1 week")]


class HeartbeatForm(HeartbeatFormTemplate):
    """New heartbeat: name, how often the job checks in, grace time. Closes with True when saved."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.period_box.items = [(label, m) for m, label in PERIODS]
        self.period_box.selected_value = 1440
        self.grace_box.text = "30"
        state.set_control_attr(self.period_box, "aria-label", "Checks in every")

    @handle("", "show")
    def form_show(self, **event_args):
        self.name_box.focus()

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        try:
            grace = int(self.grace_box.text or 0)
        except ValueError:
            grace = 30
        data = {"id": None, "name": self.name_box.text or "", "period_min": self.period_box.selected_value, "grace_min": grace}
        self.save_button.enabled = False
        try:
            r = anvil.server.call("save_heartbeat", data)
        finally:
            self.save_button.enabled = True
        if not r.get("ok"):
            self.message.text, self.message.visible = r.get("error") or "That didn't work.", True
            return
        self.raise_event("x-close-alert", value=True)
