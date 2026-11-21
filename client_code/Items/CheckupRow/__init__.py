from anvil import *

from ._anvil_designer import CheckupRowTemplate

WORD = {"good": "OK", "warn": "Watch", "bad": "Fix", "info": "Note"}


class CheckupRow(CheckupRowTemplate):
    """Check-up report card: one check (status colour + word, label, what the robot saw, what to do)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        r, n = self.item, self.dom_nodes
        st = r.get("status") or "info"
        n["row"].className = "ck-row " + st
        n["label"].textContent = r.get("label") or ""
        n["st"].textContent = WORD.get(st, "")
        n["value"].textContent = r.get("value") or ""
        n["todo"].textContent = r.get("todo") or ""
