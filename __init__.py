# -*- coding: utf-8 -*-
"""QGIS plugin entry point."""


def classFactory(iface):  # pylint: disable=invalid-name
    from .aoo_eoo_gbif import AooEooGbifPlugin
    return AooEooGbifPlugin(iface)
