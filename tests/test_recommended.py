"""scripts/recommended.py: Kodi settings Bald recommends, applied only after a yes."""

import json
import unittest
from unittest.mock import Mock

from scripts import recommended


def kodi(values, yes=True):
    """A mock xbmc whose settings hold `values`, and a dialog that answers `yes`."""
    xbmc = Mock()
    xbmc.getLocalizedString = lambda num: f"#{num}"
    calls = []

    def execute(payload):
        request = json.loads(payload)
        calls.append(request)
        params = request["params"]
        if request["method"] == "Settings.GetSettingValue":
            return json.dumps({"id": 1, "result": {"value": values[params["setting"]]}})
        values[params["setting"]] = params["value"]
        return json.dumps({"id": 1, "result": True})

    xbmc.executeJSONRPC.side_effect = execute
    xbmcgui = Mock()
    xbmcgui.Dialog.return_value.yesno.return_value = yes
    return xbmc, xbmcgui, calls


class RecommendedTests(unittest.TestCase):
    DEFAULTS = {"filelists.showparentdiritems": True, "myvideos.selectaction": 8, "videolibrary.flattentvshows": 1}
    RECOMMENDED = {"filelists.showparentdiritems": False, "myvideos.selectaction": 3, "videolibrary.flattentvshows": 0}

    def test_applies_after_yes(self):
        values = dict(self.DEFAULTS)
        xbmc, xbmcgui, _ = kodi(values)
        self.assertTrue(recommended.apply(xbmc, xbmcgui))
        self.assertEqual(values, self.RECOMMENDED)

    def test_no_changes_after_no(self):
        values = dict(self.DEFAULTS)
        xbmc, xbmcgui, calls = kodi(values, yes=False)
        self.assertFalse(recommended.apply(xbmc, xbmcgui))
        self.assertEqual(values, self.DEFAULTS)
        self.assertFalse([c for c in calls if c["method"] == "Settings.SetSettingValue"])

    def test_prompt_mode_is_silent_when_already_set(self):
        values = dict(self.RECOMMENDED)
        xbmc, xbmcgui, _ = kodi(values)
        self.assertFalse(recommended.apply(xbmc, xbmcgui, "prompt"))
        xbmcgui.Dialog.return_value.yesno.assert_not_called()
        xbmcgui.Dialog.return_value.notification.assert_not_called()

    def test_button_says_when_already_set(self):
        values = dict(self.RECOMMENDED)
        xbmc, xbmcgui, _ = kodi(values)
        recommended.apply(xbmc, xbmcgui)
        xbmcgui.Dialog.return_value.notification.assert_called_once()


    def test_an_answer_without_a_result_counts_as_not_set(self):
        xbmc = Mock()
        xbmc.executeJSONRPC.return_value = json.dumps({"id": 1})
        self.assertEqual(recommended.pending(xbmc), list(recommended.RECOMMENDED))

    def test_uses_the_skins_one_json_rpc_helper(self):
        from scripts import info
        self.assertIs(recommended.rpc, info.rpc)

if __name__ == "__main__":
    unittest.main()
