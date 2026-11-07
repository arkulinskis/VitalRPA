from anvil import *

from ._anvil_designer import HeartbeatRowTemplate
from ... import state, vr


class HeartbeatRow(HeartbeatRowTemplate):
    """Robots: one cron heartbeat (light, schedule, last ping, LATE; Test ping, Pause, Delete; the curl line to copy)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        h, n = self.item, self.dom_nodes
        stt = h.get("status")
        led = "down" if stt == "late" else "up" if stt == "up" else "paused" if stt == "paused" else "pending"
        n["led"].className = "vr-led s-" + led
        n["name"].textContent = h.get("name") or ""
        n["sample"].hidden = not h.get("demo")
        n["meta"].textContent = "every %s (+%s min grace) \u00b7 %s" % (
            h.get("every") or "", h.get("grace_min"), ("last ping " + state.ago(h["last_ping"])) if h.get("last_ping") else "never pinged")
        n["late"].hidden = stt != "late"
        n["due"].textContent = (" \u00b7 next due " + vr.until(h.get("next_due"))) if stt == "up" else ""
        n["pings"].textContent = " \u00b7 %s pings" % vr.num(h.get("pings") or 0)
        self.buttons.visible = bool(h.get("can_edit"))
        self.pause_button.text = "Resume" if stt == "paused" else "Pause"
        self.pause_button.role = ["btn", "btn-sm", "ic-play" if stt == "paused" else "ic-pause"]
        state.set_control_attr(self.delete_button, "aria-label", "Delete " + (h.get("name") or "heartbeat"))
        self.url = (h.get("ping_base") or "") + h["token"] if h.get("token") else None
        self.url_row.visible = bool(self.url)
        if self.url:
            n["code"].textContent = "curl -fsS " + self.url
            n["code"].setAttribute("title", self.url)

    @handle("ping_button", "click")
    def ping_button_click(self, **event_args):
        if state.call("ping_heartbeat_now", self.item["id"]):
            state.toast("Ping received", "ok")
            self.parent.raise_event("x-changed")

    @handle("pause_button", "click")
    def pause_button_click(self, **event_args):
        if state.call("set_heartbeat_paused", self.item["id"], self.item.get("status") != "paused"):
            self.parent.raise_event("x-changed")

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        if confirm("Jobs still calling its URL will get \"unknown token\".", title="Delete \u201c%s\u201d?" % self.item["name"],
                   buttons=[("Cancel", False), ("Delete", True)], role="app-dialog"):
            if state.call("delete_heartbeat", self.item["id"]):
                self.parent.raise_event("x-changed")

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        if vr.copy("curl -fsS " + str(self.url)):
            state.toast("Command copied to the clipboard", "ok")
        else:
            state.toast("Select the text and copy it by hand", "error")
