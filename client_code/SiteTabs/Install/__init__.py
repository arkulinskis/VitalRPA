import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import InstallTemplate
from ... import state, vr


class Install(InstallTemplate):
    """Site -> Install beacon: what already works with no code, the snippet (copy), "Is it working?" (ask the server,
    or send a test beacon from this browser), where to paste it."""

    def __init__(self, site, page, **properties):
        super().__init__(**properties)
        s = self.s = site
        n = self.dom_nodes
        n["host"].textContent = s["host"]
        n["every"].textContent = "%s (%d times a day)" % (vr.every(s["interval"]), vr.per_day(s["interval"]))
        self.code = vr.snippet(s["site_key"], s["endpoint"])
        n["code"].textContent = self.code
        n["bytes"].textContent = "%d bytes" % vr.byte_size(self.code)
        self.test_button.visible = bool(s["can_edit"])
        self._verify(s["beacon"], s.get("last_beat"))

    def _verify(self, st, last):
        n = self.dom_nodes
        if st == "none" or not last:
            n["v_led"].className = "ic ic-clock"
            n["v_text"].textContent = "No beacon received yet. Paste the snippet, open your site in a browser, then check again."
            return
        n["v_led"].className = "vr-led s-" + ("down" if st == "quiet" else "up")
        n["v_text"].textContent = "Last beacon %s (%s UTC)%s" % (state.ago(last), vr.stamp(last),
                                                                ": quieter than your silence alarm." if st == "quiet" else ". It's working.")

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        if vr.copy(self.code):
            state.toast("Snippet copied to the clipboard", "ok")
        else:
            state.toast("Select the text and copy it by hand", "error")

    @handle("verify_button", "click")
    def verify_button_click(self, **event_args):
        r = state.call("beacon_status", self.s["id"])
        if r:
            self._verify(r["state"], r.get("last_beat"))

    @handle("test_button", "click")
    def test_button_click(self, **event_args):
        s = self.s
        url = "%s?k=%s&t=v&p=%%2Fvitalrpa-test&w=%d&x=1" % (s["endpoint"], window.encodeURIComponent(s["site_key"]), int(window.innerWidth))
        self.test_button.enabled = False
        try:
            try:
                window.fetch(url, {"mode": "no-cors", "cache": "no-store"})
            except Exception:
                state.toast("The test beacon couldn't be sent from this browser (an ad blocker?)", "error")
                return
            r = state.call("beacon_status", s["id"])
        finally:
            self.test_button.enabled = True
        if r:
            self._verify(r["state"], r.get("last_beat"))
            state.toast("Test beacon received", "ok")
