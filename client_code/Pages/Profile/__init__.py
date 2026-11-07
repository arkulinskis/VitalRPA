from anvil import *

from ._anvil_designer import ProfileTemplate
from ... import auth, router, state


class Profile(ProfileTemplate):
    """#profile: your name, light/dark, a password reset link, the alert email + morning digest (playbooks with an
    empty address send there), Privacy & Terms, feedback, sign out."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.name_title, 1)
        state.set_control_attr(self.name_box, "autocomplete", "name")
        state.set_control_attr(self.alert_box, "autocomplete", "email")
        self._show_me()
        self._show_theme()
        a = state.call("get_alerts") or {}
        self.alert_box.text = a.get("alert_email") or ""
        self.digest_box.checked = bool(a.get("digest_on"))

    def _show_me(self):
        me = state.me()
        self.initials.text = state.initials(me.get("name"))
        self.name_title.text = me.get("name") or ""
        joined = state.month_year(me.get("joined"))
        self.email_line.text = (me.get("email") or "") + (" \u00b7 member since " + joined if joined else "")
        self.name_box.text = me.get("name") or ""
        self.alert_box.placeholder = me.get("email") or ""
        self.admin_link.visible = bool(me.get("is_admin"))

    def _show_theme(self):
        t = state.theme()
        for name, el in (("auto", self.theme_auto), ("light", self.theme_light), ("dark", self.theme_dark)):
            el.classes["on"] = name == t

    def theme_click(self, event):
        state.set_theme(event.currentTarget.getAttribute("data-theme-pick"))
        self._show_theme()

    @handle("name_box", "pressed_enter")
    def name_box_pressed_enter(self, **event_args):
        self.save_button_click()

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        name = (self.name_box.text or "").strip()
        if len(name) < 2:
            state.toast("Please tell us your name.", "error")
            return
        r = state.call("update_profile", name)
        if r:
            state.set_me(r["me"])
            self._show_me()
            layout = getattr(self, "layout", None)
            if layout is not None:
                layout.refresh("profile")
            state.toast("Saved", "ok")

    @handle("alert_box", "pressed_enter")
    def alert_box_pressed_enter(self, **event_args):
        self.alerts_button_click()

    @handle("alerts_button", "click")
    def alerts_button_click(self, **event_args):
        if state.call("save_alerts", (self.alert_box.text or "").strip(), bool(self.digest_box.checked)):
            state.toast("Alert settings saved", "ok")

    @handle("reset_button", "click")
    def reset_button_click(self, **event_args):
        r = auth.reset(state.me()["email"])
        state.toast(r["message"], "ok")

    def feedback_click(self, event):
        state.feedback()

    def sign_out_click(self, event):
        auth.sign_out()
        state.set_open(0)
        state.toast("Signed out. The robots keep watching.")
        router.go("landing")
