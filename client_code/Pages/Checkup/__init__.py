import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import CheckupTemplate
from ... import router, state, vr
from ...Dialogs.AddSite import add_site

VERDICT = {"good": "good", "warn": "warn", "bad": "bad"}


def clean_host(text):
    """What people type ('https://www.Shop.com/cart?x') -> 'www.shop.com' (the server checks it properly)."""
    s = (text or "").strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/")[0].split("?")[0].split("#")[0].strip().lower()
    return s


class Checkup(CheckupTemplate):
    """#checkup/<host> (anyone, also signed out): the free website check-up. The page types out the robot log while two
    server calls run (checkup_http, then checkup_tls), then shows a report card: one row per check with a status colour
    and what to do, Copy link, Run again (results older than 30 min) and "Watch it around the clock" (sign up, then the
    console opens Add site with the address filled in; members add it straight away). #checkup alone = the form."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        state.set_control_attr(self.address_box, "aria-label", "Website address")
        state.set_control_attr(self.address_box, "inputmode", "url")
        state.set_control_attr(self.address_box, "autocomplete", "off")
        self.host = clean_host(args[0]) if args else ""
        self.address_box.text = self.host
        self.run: dict = {}
        self._started = False
        self.body.visible = bool(self.host)
        self.start.visible = not self.host
        self.card.visible = False
        self.watch_button.text = "Add to my console" if state.me() else "Watch it around the clock, free"

    @handle("", "show")
    def form_show(self, **event_args):
        if self.host and not self._started:
            self._started = True
            self._go(False)
        elif not self.host:
            self.address_box.focus()

    # ---- running
    def _go(self, fresh):
        self.refusal.visible = False
        self.card.visible = False
        self.body.visible = True
        self.start.visible = False
        self.dom_nodes["term_host"].textContent = self.host
        self.log_panel.items = [{"at": None, "bot": "uptime", "level": "ok", "text": "GET https://%s/ …" % self.host}]
        self.busy_line.visible = True
        self.dom_nodes["busy_text"].textContent = "loading the page like a visitor"
        r = self._call("checkup_http", self.host, fresh)
        if r is None:
            return
        self._show_log(r)
        if not r.get("done"):
            self.dom_nodes["busy_text"].textContent = "reading the certificate and the domain"
            r = self._call("checkup_tls", r["run_id"])
            if r is None:
                return
            self._show_log(r)
        self._show_card(r)

    def _call(self, name, *args):
        try:
            r = anvil.server.call_s(name, *args)
        except Exception as e:  # noqa: BLE001 - a timeout or a dropped line: say so, keep the page
            if type(e).__name__ == "SessionExpiredError":
                raise
            r = {"ok": False, "error": "The robots couldn't finish this time (%s). Try again in a minute." % (type(e).__name__)}
        if not r.get("ok"):
            self.busy_line.visible = False
            self.body.visible = False
            self.start.visible = True
            self.refusal.text = r.get("error") or "That didn't work."
            self.refusal.visible = True
            return None
        return r

    def _show_log(self, r):
        at = r.get("at")
        lines = [dict(line, at=at, delay=i * 160) for i, line in enumerate(r.get("log") or [])]
        if r.get("cached"):
            lines.append({"at": at, "bot": "cache", "level": "ok", "text": "from the robots' notes, checked %s" % self._age(r)})
        self.log_panel.items = lines

    def _age(self, r):
        m = int(r.get("age_min") or 0)
        if m < 1:
            return "just now"
        if m < 60:
            return "%d min ago" % m
        if m < 1440:
            return "%d h ago" % (m // 60)
        return "on %s UTC" % vr.stamp(r.get("at"))

    def _show_card(self, r):
        self.run = r
        self.busy_line.visible = False
        n = self.dom_nodes
        n["card_host"].textContent = r["host"]
        n["card_when"].textContent = "Checked %s · %s" % (self._age(r), r.get("url") or "")
        v = r.get("verdict") or {}
        n["verdict"].textContent = v.get("text") or ""
        n["verdict"].className = "ck-verdict " + VERDICT.get(v.get("level"), "")
        self.rows_panel.items = r.get("rows") or []
        self.again_button.visible = int(r.get("age_min") or 0) >= int(r.get("fresh_after_min") or 30)
        self.card.visible = True
        router.replace("checkup", r["host"])
        window.document.title = r["host"] + " check-up · VitalRPA"

    # ---- buttons
    def _start_from_box(self):
        host = clean_host(self.address_box.text)
        if not host:
            self.refusal.text = "Type the address of a website first, like example.com."
            self.refusal.visible = True
            return
        if host == self.host and self.run:
            self._go(False)
            return
        self.host = host
        router.go("checkup", host)

    @handle("run_button", "click")
    def run_button_click(self, **event_args):
        self._start_from_box()

    @handle("address_box", "pressed_enter")
    def address_box_pressed_enter(self, **event_args):
        self._start_from_box()

    @handle("again_button", "click")
    def again_button_click(self, **event_args):
        self._go(True)

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        link = window.location.origin + window.location.pathname + "#checkup/" + self.host
        state.toast("Link copied" if vr.copy(link) else link, "ok")

    @handle("watch_button", "click")
    def watch_button_click(self, **event_args):
        url = (self.run.get("url") or ("https://%s/" % self.host))
        if state.me():
            add_site(url)
        else:
            router.remember_after(router.href("home", "watch", self.host))
            router.go("auth", "signup")
