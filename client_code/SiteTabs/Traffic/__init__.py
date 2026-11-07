from anvil import *

from ._anvil_designer import TrafficTemplate
from ... import router, vr


class Traffic(TrafficTemplate):
    """Site -> Traffic (from the beacon): views, visitors, load and server times; views per day (30 days) and by hour
    today; top pages, referrers, devices."""

    def __init__(self, site, page, **properties):
        super().__init__(**properties)
        s, t = site, site["traffic"]
        none = s["beacon"] == "none" and not t["views7"]
        self.empty.visible = none
        self.data_part.visible = not none
        self.install_link.visible = bool(s["can_edit"])
        state_href = router.href("site", s["id"], "install")
        self.dom_nodes["install_a"].setAttribute("href", state_href)
        if none:
            return
        n = self.dom_nodes
        for key, value, sub in (("k1", vr.num(t["views7"]), vr.num(t["today"]["views"]) + " today"),
                                ("k2", vr.num(t["visitors7"]), vr.num(t["today"]["visitors"]) + " today (unique per day)"),
                                ("k3", vr.ms(t.get("load_ms")), "real visitors, until the load event"),
                                ("k4", vr.ms(t.get("ttfb_ms")), "time to first byte, real visitors")):
            n[key].textContent = value
            n[key + "_sub"].textContent = sub
        days = t["days"]
        n["views30"].textContent = vr.num(sum(d["views"] for d in days))
        self.days_chart.show("colbars", [{"v": d["views"], "tip": "%s\n%s views \u00b7 %s visitors" % (vr.day(d["day"]), vr.num(d["views"]), vr.num(d["visitors"])),
                                          "cls": "now" if k == len(days) - 1 else ""} for k, d in enumerate(days)],
                             {"height": 130, "label": "Page views per day, last 30 days"})
        n["first_day"].textContent = vr.day(days[0]["day"])
        hour = vr.utc_hour()
        n["today"].textContent = vr.num(t["today"]["views"])
        self.hours_chart.show("colbars", [{"v": None if h > hour else v,
                                           "tip": "%02d:00 UTC\n%s" % (h, "later today" if h > hour else vr.num(v) + " views"),
                                           "cls": "now" if h == hour else ""} for h, v in enumerate(t["today"]["hours"])],
                              {"height": 90, "label": "Page views today by hour"})
        self.pages_chart.show("blist", t["pages"])
        self.refs_chart.show("blist", t["refs"])
        self.devices_chart.show("blist", t["devices"])
