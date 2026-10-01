# -*- coding: utf-8 -*-
"""Map tools to add or remove manual points."""

from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapToolEmitPoint, QgsMapTool
from qgis.core import QgsPointXY, QgsRectangle


class ManualPointTool(QgsMapToolEmitPoint):
    """Emit a canvas point and delegate feature creation/deletion to the dialog."""

    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self.canvas = canvas
        self.callback = callback
        self.canvasClicked.connect(self._clicked)

    def _clicked(self, point, button):
        self.callback(point, button)


class ManualRectangleTool(QgsMapTool):
    """Emit a rectangle in canvas coordinates after the user drags an area.

    This intentionally avoids persistent rubber-band drawing to keep compatibility
    with QGIS 3 and QGIS 4. The start and end points are enough to construct a
    selection rectangle for deleting user-added points.
    """

    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self.canvas = canvas
        self.callback = callback
        self.start_point = None

    def canvasPressEvent(self, event):
        self.start_point = self.toMapCoordinates(event.pos())

    def canvasReleaseEvent(self, event):
        if self.start_point is None:
            return
        end_point = self.toMapCoordinates(event.pos())
        rect = QgsRectangle(QgsPointXY(self.start_point), QgsPointXY(end_point))
        self.start_point = None
        self.callback(rect)
