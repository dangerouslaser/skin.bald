"""Minimal stand-in for Kodi's xbmcaddon module, for the tests."""


class Addon:
    def __init__(self, *args):
        pass

    def getLocalizedString(self, string_id):
        return "N/A"

    def getSetting(self, key):
        return ""

    def getSettingBool(self, key):
        return False

    def getAddonInfo(self, key):
        return ""
