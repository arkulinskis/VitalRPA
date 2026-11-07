import datetime

from anvil import *
import anvil.js
from anvil.js import window

from ._anvil_designer import ShellTemplate
from ... import auth, router, state, vr

THEMES = ["auto", "light", "dark"]


class Shell(ShellTemplate):
    """The frame around every page: header (menu with the open-incident count, the UTC robot clock and the account
    menu for members; Sign in / Start monitoring for visitors), the footer and the phone tab bar.

    Anvil keeps ONE Shell while pages come and go (open_form only swaps the "content" slot when the layout matches),
    so everything that depends on who is signed in or which page is open is drawn in refresh(), which router.show()
    calls after every page change. Never only in __init__."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.copyright_label.text = "\u00a9 %d VitalRPA \u00b7 robot time is UTC" % datetime.date.today().year
        self._outside = anvil.js.report_exceptions(self._close_menu_outside)
        self._keys = anvil.js.report_exceptions(self._key)
        self._tick = anvil.js.report_exceptions(self._clock)
        self._timer = None
        self._page = ""
        state.set_shell(self)
        self.refresh("")

    def refresh(self, page):
        me = state.me()
        self._page = page
        self.classes.update({"signed-in": bool(me), "signed-out": not me})
        self.member_actions.visible = bool(me)
        self.guest_actions.visible = not me and page != "auth"
        self.tabbar.visible = bool(me)
        self.menu.visible = False
        state.set_attr(self.brand, "href", "#home" if me else "#landing")
        self.show_counts()
        self.tab_profile.classes["on"] = page == "profile"
        if me:
            self.avatar_button.text = state.initials(me.get("name"))
            self.menu_name.text = me.get("name") or ""
            self.menu_email.text = me.get("email") or ""
            self.admin_link.visible = bool(me.get("is_admin"))
        self._show_theme()
        self._clock(None)

    def show_counts(self):
        """The menus (header + phone tab bar), with the open-incident count on Incidents."""
        me, page, n = state.me(), self._page, state.open_count()
        links = [{"page": p, "label": label, "icon": icon, "on": p == page, "count": n if p == "incidents" else 0}
                 for p, label, icon in router.NAV] if me else []
        self.nav_panel.items = links
        self.tab_panel.items = links

    def _clock(self, *args):
        self.dom_nodes["clock"].textContent = vr.clock_text()

    # ---- account menu
    @handle("avatar_button", "click")
    def avatar_button_click(self, **event_args):
        self.menu.visible = not self.menu.visible
        state.set_control_attr(self.avatar_button, "aria-expanded", "true" if self.menu.visible else "false")

    def _close_menu_outside(self, event):
        if self.menu.visible and not event.target.closest(".anvil-role-avatar, .ui-menu .ui-seg"):
            self.menu.visible = False

    def _key(self, event):
        if event.key == "Escape":
            self.menu.visible = False

    @handle("", "show")
    def form_show(self, **event_args):
        window.document.addEventListener("click", self._outside, True)
        window.document.addEventListener("keydown", self._keys)
        if self._timer is None:
            self._timer = window.setInterval(self._tick, 1000)

    @handle("", "hide")
    def form_hide(self, **event_args):
        window.document.removeEventListener("click", self._outside, True)
        window.document.removeEventListener("keydown", self._keys)
        if self._timer is not None:
            window.clearInterval(self._timer)
            self._timer = None

    def theme_click(self, event):
        state.set_theme(event.currentTarget.getAttribute("data-theme-set"))
        self._show_theme()

    def _show_theme(self):
        t = state.theme()
        for name, el in zip(THEMES, [self.theme_auto, self.theme_light, self.theme_dark]):
            el.classes["on"] = name == t

    def feedback_click(self, event):
        self.menu.visible = False
        state.feedback()

    def sign_out_click(self, event):
        auth.sign_out()
        state.set_open(0)
        state.toast("Signed out. The robots keep watching.")
        router.go("landing")
