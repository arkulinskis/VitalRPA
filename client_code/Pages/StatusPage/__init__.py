from anvil import *
from anvil.js import window

from ._anvil_designer import StatusPageTemplate
from ... import router, state


class StatusPage(StatusPageTemplate):
    """#statuspage: set up your public status page (address, title, intro, which sites, public or not). The page
    itself is #status/<slug>."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        d: dict = state.call("get_my_status_page") or {}
        p: dict = d.get("page") or {"slug": d["suggest"]["slug"], "title": d["suggest"]["title"], "intro": "",
                              "site_ids": [s["id"] for s in d.get("sites", [])], "public": False}
        self.open_link.visible = bool(d.get("page"))
        if d.get("page"):
            state.set_attr(self.open_link, "href", router.href("status", d["page"]["slug"]))
        self.slug_box.text = p["slug"]
        self.title_box.text = p["title"]
        self.intro_box.text = p.get("intro") or ""
        self.public_box.checked = bool(p.get("public"))
        self.picks_panel.items = [dict(s, on=s["id"] in (p.get("site_ids") or [])) for s in d.get("sites", [])]
        self.no_sites.visible = not d.get("sites")
        self.sample_link.visible = bool(d.get("sample_slug"))
        if d.get("sample_slug"):
            state.set_attr(self.sample_link, "href", router.href("status", d["sample_slug"]))
        loc = window.location
        self.dom_nodes["base"].textContent = loc.origin + str(loc.pathname).rsplit("/", 1)[0] + "/#status/"
        self._slug()
        state.set_control_attr(self.slug_box, "aria-label", "Address")

    def _slug(self):
        self.dom_nodes["slug"].textContent = self.slug_box.text or ""

    @handle("slug_box", "change")
    def slug_box_change(self, **event_args):
        self._slug()

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        ids = [getattr(c, "item")["id"] for c in self.picks_panel.get_components() if getattr(c, "picked")()]
        data = {"slug": (self.slug_box.text or "").strip().lower(), "title": self.title_box.text or "",
                "intro": self.intro_box.text or "", "site_ids": ids, "public": bool(self.public_box.checked)}
        r = state.call("save_status_page", data)
        if r:
            state.toast("Saved", "ok")
            router.go("status", r["slug"])
