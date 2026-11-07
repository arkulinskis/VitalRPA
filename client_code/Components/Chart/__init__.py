from anvil import *

from ._anvil_designer import ChartTemplate
from ... import vr


class Chart(ChartTemplate):
    """One chart from the engine (theme/assets/vr-charts.js): kind = cells (24-hour strip), uptimeBars (90 days),
    spark, colbars, blist or lineChart; data = what that kind draws; opts = its options (lineChart: limit; colbars:
    height, label; blist: empty). Redraws whenever a property changes; show(kind, data, opts) sets all three at once."""

    def __init__(self, **properties):
        self._kind, self._data, self._opts, self._ready = "cells", None, None, False
        super().__init__(**properties)
        self._ready = True
        self._draw()

    def _draw(self):
        if self._ready and self._data is not None:
            vr.draw(self.dom_nodes["box"], self._kind, self._data, self._opts)

    def show(self, kind, data, opts=None):
        self._kind, self._data, self._opts = kind, data, opts
        self._draw()

    @property
    def kind(self):
        return self._kind

    @kind.setter
    def kind(self, value):
        self._kind = value or "cells"
        self._draw()

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self._draw()

    @property
    def opts(self):
        return self._opts

    @opts.setter
    def opts(self, value):
        self._opts = value
        self._draw()
