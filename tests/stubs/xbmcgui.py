"""Minimal stand-in for Kodi's xbmcgui module, for the tests."""


class Window:
    def __init__(self, *args):
        self._props = {}

    def getProperty(self, key):
        return self._props.get(key, "")

    def setProperty(self, key, value):
        self._props[key] = value
