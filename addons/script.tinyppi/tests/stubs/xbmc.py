"""Minimal stand-in for Kodi's xbmc module, for the tests."""
LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3
LABELS = {}


def log(msg, level=LOGINFO):
    pass


def getInfoLabel(label):
    return LABELS.get(label, "")


def getCondVisibility(condition):
    return False


def sleep(ms):
    pass
