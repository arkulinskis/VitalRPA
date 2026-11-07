from anvil import *

from ._anvil_designer import SettingsTemplate
from ... import router, state, vr


class Settings(SettingsTemplate):
    """Site -> Settings (owners only): what the robots check; rotate the beacon key; delete the site."""

    def __init__(self, site, page, **properties):
        super().__init__(**properties)
        self.s, self.page = site, page
        st = site["settings"]
        self.name_box.text = st["name"]
        self.url_box.text = st["url"]
        self.interval_box.items = [("%s (%d\u00d7 a day)" % (vr.every(m), vr.per_day(m)), m) for m in site["intervals"]]
        self.interval_box.selected_value = st["interval_min"]
        self.slow_box.text = str(st["slow_ms"])
        self.keyword_box.text = st.get("keyword") or ""
        self.status_box.text = str(st["expect_status"]) if st.get("expect_status") else ""
        self.quiet_box.text = str(st.get("quiet_hours") or 0)
        self.tags_box.text = ", ".join(st["tags"])
        state.set_control_attr(self.interval_box, "aria-label", "Check every")

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        data = {"name": self.name_box.text or "", "url": self.url_box.text or "", "interval_min": self.interval_box.selected_value,
                "slow_ms": self.slow_box.text or 3000, "keyword": self.keyword_box.text or "", "expect_status": self.status_box.text or "",
                "quiet_hours": self.quiet_box.text or 0, "tags": self.tags_box.text or ""}
        r = state.call("update_site", self.s["id"], data)
        if r:
            state.toast("Saved", "ok")
            self.page.set_site(r["site"])

    @handle("rotate_button", "click")
    def rotate_button_click(self, **event_args):
        if confirm("Pages with the old snippet stop counting until you paste the new one.", title="Rotate the beacon key?",
                   buttons=[("Cancel", False), ("Rotate", True)], role="app-dialog"):
            if state.call("rotate_site_key", self.s["id"]):
                state.toast("New key ready: copy the new snippet", "ok")
                self.page.reload("install")
                router.replace("site", self.s["id"], "install")

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        if confirm("Its checks, traffic, errors and incidents are deleted too. This can't be undone.",
                   title="Delete %s?" % self.s["name"], buttons=[("Cancel", False), ("Delete", True)], role="app-dialog"):
            if state.call("delete_site", self.s["id"]):
                state.toast("Deleted", "ok")
                router.go("home")
