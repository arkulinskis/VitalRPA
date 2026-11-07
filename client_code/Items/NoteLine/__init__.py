from anvil import *

from ._anvil_designer import NoteLineTemplate
from ... import vr


class NoteLine(NoteLineTemplate):
    """Incidents: one note on the timeline (who, when, what)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["by"].textContent = i.get("by") or ""
        n["at"].textContent = vr.stamp(i.get("at"))
        n["text"].textContent = i.get("text") or ""
