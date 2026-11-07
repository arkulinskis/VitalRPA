from anvil import *

from ._anvil_designer import JsErrorTemplate
from ... import state, vr


class JsError(JsErrorTemplate):
    """Site -> JS errors: one grouped error (count, message, where, first and last seen)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        e, n = self.item, self.dom_nodes
        n["cnt"].textContent = vr.num(e.get("count")) + "\u00d7"
        n["msg"].textContent = e.get("message") or ""
        n["meta"].textContent = "%s \u00b7 on %s \u00b7 first %s \u00b7 last %s" % (
            e.get("source") or "unknown source", e.get("path") or "/", vr.stamp(e.get("first")), state.ago(e.get("last")))
