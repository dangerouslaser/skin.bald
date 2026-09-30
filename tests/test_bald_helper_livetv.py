"""Bald Helper's Live TV search (resources/lib/livetv.py and the plugin's livetv routes), for Bald's Search window."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from support import helper

livetv = helper("livetv", "livetv")
plugin = helper("plugin", "livetv")

NOW = datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)
CHANNELS = [
    {"channelid": 1, "label": "NBC Boston", "channelnumber": 510, "thumbnail": "nbc.png",
     "broadcastnow": {"title": "News at Noon"}, "hidden": False},
    {"channelid": 2, "label": "Boston 25 News", "channelnumber": 507, "thumbnail": "fox.png", "hidden": False},
    {"channelid": 3, "label": "ESPN", "channelnumber": 25, "thumbnail": "", "hidden": False},
    {"channelid": 4, "label": "Hidden News", "channelnumber": 900, "hidden": True},
]
BROADCASTS = {
    1: [{"broadcastid": 11, "title": "NBC News Daily", "starttime": "2026-09-30 18:00:00", "endtime": "2026-09-30 19:00:00", "plot": "p"},
        {"broadcastid": 12, "title": "Morning News", "starttime": "2026-09-30 10:00:00", "endtime": "2026-09-30 11:00:00"}],
    2: [{"broadcastid": 21, "title": "Boston 25 News at 5", "starttime": "2026-09-30 21:00:00", "endtime": "2026-09-30 21:30:00"},
        {"broadcastid": 22, "title": "Late News", "starttime": "2026-10-01 03:00:00", "endtime": "2026-10-01 03:30:00"}],
    3: [{"broadcastid": 31, "title": "SportsCenter", "starttime": "2026-09-30 18:00:00", "endtime": "2026-09-30 19:00:00"}],
}


class FakeMonitor:
    def waitForAbort(self, seconds):
        return False


class FakeXbmc:
    Monitor = FakeMonitor

    def __init__(self, visible=()):
        self.calls = []
        self.builtins = []
        self.visible = set(visible)

    def executebuiltin(self, command):
        self.builtins.append(command)
        if command == "Dialog.Close(yesnodialog)":
            self.visible.discard("search")

    def getCondVisibility(self, condition):
        if condition == plugin.SEARCH_OPEN:
            return "search" in self.visible
        return "62" in self.visible

    def getInfoLabel(self, label):
        return self.labels.get(label, "") if hasattr(self, "labels") else ""

    def executeJSONRPC(self, request):
        request = json.loads(request)
        method, params = request["method"], request["params"]
        self.calls.append(method)
        if method == "PVR.GetChannels":
            channels = CHANNELS if params["channelgroupid"] == "alltv" else []
            return json.dumps({"result": {"channels": channels}})
        if method == "PVR.GetBroadcasts":
            return json.dumps({"result": {"broadcasts": BROADCASTS.get(params["channelid"], [])}})
        return json.dumps({"result": "OK"})

    def getRegion(self, key):
        return "%I:%M:%S %p"

    def getLocalizedString(self, number):
        return {19030: "Now", 41: "Mon", 42: "Tue", 43: "Wed", 44: "Thu", 45: "Fri", 46: "Sat", 47: "Sun",
                264: "Record", 19000: "Switch to channel"}.get(number, str(number))


class ChannelTests(unittest.TestCase):
    def test_hidden_channels_are_left_out(self):
        found = livetv.channels(FakeXbmc())
        self.assertEqual([c["name"] for c in found], ["NBC Boston", "Boston 25 News", "ESPN"])
        self.assertEqual(found[0]["now"], "News at Noon")

    def test_the_number_first_then_names_that_start_then_names_that_have_it(self):
        found = livetv.channels(FakeXbmc())
        self.assertEqual([c["name"] for c in livetv.match_channels(found, "25")], ["ESPN", "Boston 25 News"])
        self.assertEqual([c["name"] for c in livetv.match_channels(found, "boston")], ["Boston 25 News", "NBC Boston"])
        self.assertEqual([c["name"] for c in livetv.match_channels(found, "NEWS")], ["Boston 25 News"])
        self.assertEqual(livetv.match_channels(found, "  "), [])


class ProgrammeTests(unittest.TestCase):
    def test_on_now_or_later_soonest_first(self):
        _, programmes = livetv.guide(FakeXbmc())
        titles = [p["title"] for p in livetv.match_programmes(programmes, "news", NOW)]
        # Morning News has ended; NBC News Daily is on now, so it leads.
        self.assertEqual(titles, ["NBC News Daily", "Boston 25 News at 5", "Late News"])

    def test_the_guide_is_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            first = FakeXbmc()
            found, programmes = livetv.guide(first, folder, clock=lambda: 1000)
            self.assertEqual(first.calls.count("PVR.GetBroadcasts"), 3)
            again = FakeXbmc()
            self.assertEqual(livetv.guide(again, folder, clock=lambda: 1000 + livetv.CACHE_SECONDS - 1),
                             (found, programmes))
            self.assertEqual(again.calls, [])
            stale = FakeXbmc()
            livetv.guide(stale, folder, clock=lambda: 1000 + livetv.CACHE_SECONDS + 1)
            self.assertEqual(stale.calls.count("PVR.GetBroadcasts"), 3)

    def test_when(self):
        days = FakeXbmc().getLocalizedString
        day = lambda weekday: days(41 + weekday)  # noqa: E731
        start = NOW - timedelta(minutes=30)
        self.assertEqual(livetv.when(start, NOW + timedelta(minutes=30), NOW, "%I:%M:%S %p", "Now", day), "Now")
        later = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
        label = livetv.when(later, later + timedelta(minutes=30), NOW, "%I:%M:%S %p", "Now", day)
        self.assertEqual(label, later.astimezone().strftime("%I:%M %p").lstrip("0") if later.astimezone().date() ==
                         NOW.astimezone().date() else f"{day(later.astimezone().weekday())} "
                                                      f"{later.astimezone().strftime('%I:%M %p').lstrip('0')}")
        tomorrow = NOW + timedelta(days=1, hours=2)
        self.assertTrue(livetv.when(tomorrow, tomorrow + timedelta(hours=1), NOW, "%H:%M:%S", "Now", day)
                        .startswith(day(tomorrow.astimezone().weekday()) + " "))


class FakeItem:
    def __init__(self, label, label2="", offscreen=True):
        self.label, self.label2, self.props, self.art = label, label2, {}, {}

    def setArt(self, art):
        self.art = art

    def setProperty(self, key, value):
        self.props[key] = value


class FakeWindow:
    props = {}

    def __init__(self, window_id):
        pass

    def setProperty(self, key, value):
        FakeWindow.props[key] = value


class FakeGui:
    ListItem = FakeItem
    Window = FakeWindow

    class Dialog:
        choice = 0

        def contextmenu(self, labels):
            return FakeGui.Dialog.choice


class FakePlugin:
    def __init__(self):
        self.items = []

    def addDirectoryItems(self, handle, items, count):
        self.items = items

    def endOfDirectory(self, handle, **kwargs):
        pass


class PluginTests(unittest.TestCase):
    def test_channels_list(self):
        listing = FakePlugin()
        count = plugin.list_livetv(FakeXbmc(), FakeGui, listing, None, 1, "plugin://script.bald.helper/",
                                   {"info": "livetv_channels", "query": "boston"})
        self.assertEqual(count, 2)
        first = listing.items[0][1]
        self.assertEqual((first.label, first.props["channelid"], first.props["number"]), ("Boston 25 News", "2", "507"))
        # For Global Search's "No results found" dialog (DialogConfirm.xml).
        self.assertEqual((FakeWindow.props["Bald.SearchLive.Query"], FakeWindow.props["Bald.SearchLive.Channels"]),
                         ("boston", "2"))

    def test_programmes_list(self):
        listing = FakePlugin()
        plugin.list_livetv(FakeXbmc(), FakeGui, listing, None, 1, "plugin://script.bald.helper/",
                           {"info": "livetv_programmes", "query": "news"}, clock=lambda: NOW)
        first = listing.items[0][1]
        self.assertEqual((first.label, first.label2, first.props["when"], first.props["now"]),
                         ("NBC News Daily", "NBC Boston", "Now", "true"))
        self.assertEqual((first.props["channelid"], first.props["broadcastid"], first.props["plot"]), ("1", "11", "p"))

    def test_select_on_a_programme(self):
        xbmc = FakeXbmc()
        self.assertEqual(plugin.programme(xbmc, FakeGui, {"channelid": "1", "broadcastid": "11", "now": "true"}), "play")
        FakeGui.Dialog.choice = 0
        self.assertEqual(plugin.programme(xbmc, FakeGui, {"channelid": "2", "broadcastid": "21"}), "record")
        FakeGui.Dialog.choice = 1
        self.assertEqual(plugin.programme(xbmc, FakeGui, {"channelid": "2", "broadcastid": "21"}), "play")
        FakeGui.Dialog.choice = -1
        self.assertEqual(plugin.programme(xbmc, FakeGui, {"channelid": "2", "broadcastid": "21"}), "none")
        self.assertEqual(xbmc.calls.count("Player.Open"), 2)
        self.assertEqual(xbmc.calls.count("PVR.AddTimer"), 1)


class LiveSearchTests(unittest.TestCase):
    def test_closes_the_question_then_opens_bald_live_search(self):
        xbmc = FakeXbmc(visible={"search"})
        xbmc.labels = {"Window(home).Property(Bald.SearchLive.Channels)": "3"}
        self.assertTrue(plugin.live_search(xbmc))
        self.assertEqual(xbmc.builtins[1:], ["Dialog.Close(yesnodialog)", "ActivateWindow(1130)"])
        self.assertTrue(xbmc.builtins[0].startswith("SetProperty(Bald.LiveSearch.Query,"))

    def test_starts_on_the_programmes_without_channel_matches(self):
        xbmc = FakeXbmc(visible={"search", "62"})
        xbmc.labels = {"Window(home).Property(Bald.SearchLive.Channels)": "0"}
        plugin.live_search(xbmc)
        self.assertEqual(xbmc.builtins[-1], "SetFocus(62)")


if __name__ == "__main__":
    unittest.main()
