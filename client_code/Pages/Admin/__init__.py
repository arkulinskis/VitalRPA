from anvil import *
from anvil.js import window
import anvil.js

from ._anvil_designer import AdminTemplate
from ... import state, vr

TABS = ["overview", "robots", "feedback", "users", "demo"]


class Admin(AdminTemplate):
    """#admin/<tab>: overview numbers, Robots (pause all, run one, recent runs), the old feedback inbox, users
    (admin / active switches) and the demo data. Each tab is its own address, so the browser's back button works."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        self.tab = args[0] if args and args[0] in TABS else "overview"
        self._filter = "new"
        self._paused = False
        parts = {"overview": self.overview_part, "robots": self.robots_part, "feedback": self.feedback_part,
                 "users": self.users_part, "demo": self.demo_part}
        tabs = {"overview": self.tab_overview, "robots": self.tab_robots, "feedback": self.tab_feedback,
                "users": self.tab_users, "demo": self.tab_demo}
        for name in TABS:
            parts[name].visible = name == self.tab
            tabs[name].classes["on"] = name == self.tab
            if name == self.tab:
                state.set_attr(tabs[name], "aria-current", "page")
        self.feedback_panel.add_event_handler("x-changed", self._feedback_changed)
        self.run_panel.add_event_handler("x-ran", self._ran)
        getattr(self, "_" + self.tab)()

    # ---- overview
    def _overview(self):
        d = state.call("admin_overview")
        self.s_users.text, self.s_admins.text = str(d["users"]), str(d["admins"])
        self.s_admins_label.text = "admin" if d["admins"] == 1 else "admins"
        self.s_feedback.text, self.s_sites.text = str(d["feedback_new"]), str(d["sites"])
        self.s_open.text = str(d["open_incidents"])
        self.demo_line.text = "Demo data is %s (%d demo people). Manage it in the Demo data tab." % (
            d["demo"]["state"], d["demo"]["counts"].get("users", 0))

    # ---- robots
    def _robots(self):
        d = state.call("admin_bots")
        st = d["stats"]
        self.r_sites.text, self.r_hbs.text = str(st["sites"]), str(st["heartbeats"])
        self.r_checks.text, self.r_views.text = vr.num(st["checks_today"]), vr.num(st["views_today"])
        self.r_open.text = str(st["open_incidents"])
        self._paused = bool(d["paused"])
        self.bots_title.text = "All robots are paused" if self._paused else "Robots are running"
        self.pause_button.text = "Resume robots" if self._paused else "Pause all robots"
        self.pause_button.role = ["btn", "btn-primary", "ic-play"] if self._paused else ["btn", "btn-danger", "ic-pause"]
        self.run_panel.items = [b for b in d["bots"] if b["runnable"]]
        self.runs_panel.items = d["runs"]
        self.runs_head.visible = bool(d["runs"])
        self.no_runs.visible = not d["runs"]

    @handle("pause_button", "click")
    def pause_button_click(self, **event_args):
        if state.call("admin_set_bots_paused", not self._paused):
            state.toast("Saved", "ok")
            self._robots()

    def _ran(self, **event_args):
        window.setTimeout(anvil.js.report_exceptions(lambda: self._robots()), 1500)

    # ---- feedback
    def _feedback(self):
        d = state.call("list_feedback", None)
        items = [i for i in d["items"] if self._filter == "all" or i["status"] == self._filter]
        self.feedback_panel.items = items
        self.no_feedback.visible = not items
        labels = {"new": "New", "read": "Read", "done": "Done", "all": "All"}
        for key, el in (("new", self.f_new), ("read", self.f_read), ("done", self.f_done), ("all", self.f_all)):
            n = len(d["items"]) if key == "all" else d["counts"].get(key, 0)
            el.text = "%s (%d)" % (labels[key], n)
            el.role = ["seg", "on"] if key == self._filter else ["seg"]
            state.set_control_attr(el, "aria-pressed", "true" if key == self._filter else "false")

    def _set_filter(self, value):
        self._filter = value
        self._feedback()

    @handle("f_new", "click")
    def f_new_click(self, **event_args):
        self._set_filter("new")

    @handle("f_read", "click")
    def f_read_click(self, **event_args):
        self._set_filter("read")

    @handle("f_done", "click")
    def f_done_click(self, **event_args):
        self._set_filter("done")

    @handle("f_all", "click")
    def f_all_click(self, **event_args):
        self._set_filter("all")

    def _feedback_changed(self, **event_args):
        self._feedback()

    # ---- users
    def _users(self, query=None):
        d = state.call("list_users", query or None)
        self.users_panel.items = d["users"]
        self.users_count.text = state.plural(d["total"], "person", "people")

    @handle("search_box", "pressed_enter")
    def search_box_pressed_enter(self, **event_args):
        self._users(self.search_box.text)

    @handle("search_button", "click")
    def search_button_click(self, **event_args):
        self._users(self.search_box.text)

    # ---- demo data
    def _demo(self):
        d = state.call("admin_overview")["demo"]
        counts = ", ".join("%s %s" % (v, k) for k, v in d["counts"].items())
        self.demo_status.text = "Status: %s \u00b7 %s" % (d["state"], counts)
        self.demo_load_button.text = "Reload demo data" if d["state"] == "loaded" else "Load demo data"

    @handle("demo_load_button", "click")
    def demo_load_button_click(self, **event_args):
        if confirm("Demo people and content are added (any old demo rows are replaced).", title="Load the demo data?",
                   buttons=[("Cancel", False), ("Load", True)], role="app-dialog"):
            if state.call("demo_load"):
                state.toast("Done", "ok")
                self._demo()

    @handle("demo_remove_button", "click")
    def demo_remove_button_click(self, **event_args):
        if confirm("Every demo row is deleted. Real data stays.", title="Remove the demo data?",
                   buttons=[("Cancel", False), ("Remove", True)], role="app-dialog"):
            if state.call("demo_remove"):
                state.toast("Done", "ok")
                self._demo()
