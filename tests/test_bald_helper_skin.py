"""The skin's side of Bald Helper's blurred backgrounds: the blur prefers Bald.Blur when the helper is enabled and falls
back to TMDb Helper's; every window names the container it follows through Bald_FollowContainer; TMDb Helper is told
only when it still needs to follow (its blur without the helper, its online ratings always); and the two never blur
at once."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from conditions import equivalent, implies
from kodi_includes import expand_call, expand_follow, expressions

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "1080i"
HELPER = "$EXP[Bald_HasHelper]"
TMDB = "$EXP[Bald_HasTMDbHelper]"
BLUR_WINDOWS = ("Home.xml", "MyVideoNav.xml", "script-globalsearch.xml")


def chosen(variable, scenario):
    """The value a <variable> takes whenever `scenario` holds: the first value whose condition it implies, every
    earlier condition being ruled out by it."""
    for value in variable.findall("value"):
        condition = value.get("condition")
        if condition is None or implies(scenario, condition):
            return value.text
        if not implies(scenario, f"![{condition}]"):
            raise AssertionError(f"{scenario!r} does not decide {condition!r}")
    return None


class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.bodies = expressions()

    def test_has_helper_means_installed_and_enabled(self):
        self.assertEqual(self.bodies["Bald_HasHelper"],
                         "[System.HasAddon(script.bald.helper) + System.AddonIsEnabled(script.bald.helper)]")

    def test_tmdb_helper_follows_without_the_helper_or_for_online_ratings(self):
        follows = "$EXP[Bald_TMDbHelperFollows]"
        self.assertTrue(equivalent(follows, f"!{HELPER} | $EXP[Bald_RatingsOnline]"))
        self.assertTrue(implies(f"!{HELPER}", follows))
        self.assertTrue(implies("$EXP[Bald_RatingsOnline]", follows))
        self.assertTrue(implies(f"{HELPER} + Skin.HasSetting(Bald.Ratings.NoOnline)", f"!{follows}"))


class BlurSourceTests(unittest.TestCase):
    def setUp(self):
        self.home = ET.parse(XML / "Includes_Bald_Home.xml").getroot()
        self.blur = self.home.find("variable[@name='Bald_BlurImage']")

    def test_prefers_the_helpers_blur(self):
        live = "Window.IsActive(home)"
        self.assertEqual(chosen(self.blur, f"{HELPER} + {live}"), "$INFO[Window(home).Property(Bald.Blur)]")
        self.assertEqual(chosen(self.blur, f"!{HELPER} + {live}"),
                         "$INFO[Window(home).Property(TMDbHelper.ListItem.BlurImage)]")

    def test_windows_without_an_item_show_the_last_blur(self):
        settings = ("!Window.IsActive(home) + !Window.IsActive(videos) + "
                    "String.IsEmpty(Window(home).Property(Bald.Blur)) + "
                    "String.IsEmpty(Window(home).Property(TMDbHelper.ListItem.BlurImage))")
        self.assertEqual(chosen(self.blur, f"{HELPER} + {settings}"), "$INFO[Window(home).Property(Bald.Blur.Last)]")
        self.assertEqual(chosen(self.blur, f"!{HELPER} + {settings}"), "$INFO[Window(home).Property(Bald.LastBlur)]")
        has_blur = "$EXP[Bald_HasBlur]"
        self.assertTrue(implies(f"{HELPER} + {settings} + !String.IsEmpty(Window(home).Property(Bald.Blur.Last))",
                                has_blur))
        # The helper's last blur, not the TMDb Helper copy, decides it with the helper.
        self.assertTrue(implies(f"{HELPER} + {settings} + String.IsEmpty(Window(home).Property(Bald.Blur.Last))",
                                f"!{has_blur}"))

    def test_home_and_library_keep_the_plain_field_for_an_item_without_art(self):
        for window in ("home", "videos"):
            empty = f"Window.IsActive({window}) + {HELPER} + String.IsEmpty(Window(home).Property(Bald.Blur))"
            self.assertTrue(implies(empty, "!$EXP[Bald_HasBlur]"), window)

    def test_blur_layers_need_either_helper_and_the_setting(self):
        layers = [c.findtext("visible") for c in self.home.find("include[@name='Bald_BackdropImage']")
                  .findall("control[@type='image']")]
        layers.append(ET.parse(XML / "Custom_1129_BaldCurtain.xml").getroot()
                      .find(".//control[@type='image'][texture='$VAR[Bald_CurtainBlur]']").findtext("visible"))
        self.assertEqual(len(layers), 3)
        for visible in layers:
            self.assertTrue(equivalent(visible, "$EXP[Bald_BlurOn] + $EXP[Bald_HasBlur]"), visible)
        on = "$EXP[Bald_BlurOn]"
        self.assertTrue(equivalent(on, f"!Skin.HasSetting(Bald.DisableBlur) + [{HELPER} | {TMDB}]"))
        self.assertTrue(implies(f"{HELPER} + !{TMDB} + !Skin.HasSetting(Bald.DisableBlur)", on))

    def test_the_curtain_and_the_tmdb_copy_on_unload(self):
        curtain = self.home.find("variable[@name='Bald_CurtainBlur']")
        self.assertEqual(curtain.findall("value")[-1].text, "$VAR[Bald_BlurImage]")
        handoff = ET.parse(XML / "Includes_Bald_Common.xml").getroot().find("include[@name='Bald_CurtainHandoff']")
        keep = next(n for n in handoff.findall("onunload") if n.text.startswith("SetProperty(Bald.LastBlur,"))
        self.assertTrue(implies(keep.get("condition"), f"!{HELPER}"))


class FollowTests(unittest.TestCase):
    def test_follow_include_sets_both_properties(self):
        for suffix, tag in (("", "onfocus"), ("OnUp", "onup"), ("OnDown", "ondown"), ("OnBack", "onback"),
                            ("OnLoad", "onload")):
            with self.subTest(tag=tag):
                nodes = expand_call(f"Bald_FollowContainer{suffix}", {"id": "9101", "window": "home"})
                self.assertEqual([n.tag for n in nodes], [tag, tag])
                ours, tmdb = nodes
                self.assertEqual(ours.text, "SetProperty(Bald.FocusContainer,9101,home)")
                self.assertTrue(equivalent(ours.get("condition"), "true"))
                self.assertEqual(tmdb.text, "SetProperty(TMDbHelper.WidgetContainer,9101,home)")
                self.assertTrue(equivalent(tmdb.get("condition"), "$EXP[Bald_TMDbHelperFollows]"))
        guarded = expand_call("Bald_FollowContainer", {"id": "1", "window": "home", "condition": "Control.HasFocus(2)"})
        self.assertTrue(equivalent(guarded[0].get("condition"), "Control.HasFocus(2)"))
        self.assertTrue(equivalent(guarded[1].get("condition"), "Control.HasFocus(2) + $EXP[Bald_TMDbHelperFollows]"))

    def test_unfollow_include_clears_both(self):
        for suffix, tag in (("", "onunfocus"), ("OnFocus", "onfocus"), ("OnUp", "onup"), ("OnDown", "ondown"),
                            ("OnLoad", "onload"), ("OnUnload", "onunload")):
            with self.subTest(tag=tag):
                nodes = expand_call(f"Bald_UnfollowContainer{suffix}", {"window": "videos"})
                self.assertEqual([(n.tag, n.text) for n in nodes],
                                 [(tag, "ClearProperty(Bald.FocusContainer,videos)"),
                                  (tag, "ClearProperty(TMDbHelper.WidgetContainer,videos)")])

    def test_no_window_sets_tmdb_helpers_container_directly(self):
        # Only the includes (and Global Search, which has no window name to pass) write TMDbHelper.WidgetContainer.
        for path in sorted(XML.glob("*.xml")):
            if path.name in ("Includes_Bald_Common.xml", "script-globalsearch.xml"):
                continue
            with self.subTest(file=path.name):
                self.assertNotIn("TMDbHelper.WidgetContainer", path.read_text(encoding="utf-8"))

    def test_every_followed_container_per_window(self):
        found = {}
        for path in sorted(XML.glob("*.xml")):
            for call in ET.parse(path).getroot().iter("include"):
                if (call.get("content") or "").startswith("Bald_FollowContainer"):
                    params = {p.get("name"): p.text for p in call.findall("param")}
                    found.setdefault(params["window"], set()).add(params["id"])
        self.assertEqual(set(found), {"home", "videos", "movieinformation"})
        self.assertEqual(found["movieinformation"], {"5100"})
        self.assertLessEqual({"9101", "$PARAM[id]"}, found["home"])
        self.assertLessEqual({"510", "511", "512", "513", "514", "515", "520", "530", "540", "521", "522", "523",
                              "531", "532", "541", "542", "5302"}, found["videos"])

    def test_windows_clear_what_they_follow(self):
        for name, window in (("MyVideoNav.xml", "videos"), ("DialogVideoInfo.xml", "movieinformation")):
            root = ET.parse(XML / name).getroot()
            actions = {(n.tag, n.text) for n in expand_follow(root)}
            for tag in ("onload", "onunload"):
                self.assertIn((tag, f"ClearProperty(Bald.FocusContainer,{window})"), actions)

    def test_global_search_follows_its_results(self):
        root = ET.parse(XML / "script-globalsearch.xml").getroot()
        loads = {n.text: n.get("condition") for n in root.findall("onload")}
        self.assertIn("SetProperty(Bald.FocusContainer,50)", loads)
        self.assertIsNone(loads["SetProperty(Bald.FocusContainer,50)"])
        self.assertTrue(implies(loads["SetProperty(TMDbHelper.WidgetContainer,50)"], "$EXP[Bald_TMDbHelperFollows]"))
        self.assertIn("ClearProperty(Bald.FocusContainer)", [n.text for n in root.findall("onunload")])
        image = next(c for c in root.iter("control") if c.findtext("texture") == "$VAR[Bald_SearchBlur]")
        variable = ET.parse(XML / "Includes_Bald_Home.xml").getroot().find("variable[@name='Bald_SearchBlur']")
        self.assertEqual(chosen(variable, HELPER), "$INFO[Window(home).Property(Bald.Blur)]")
        self.assertEqual(chosen(variable, f"!{HELPER}"), "$INFO[Window.Property(TMDbHelper.ListItem.BlurImage)]")
        visible = image.findtext("visible")
        self.assertTrue(implies(f"{HELPER} + !Skin.HasSetting(Bald.DisableBlur) + "
                                "!String.IsEmpty(Window(home).Property(Bald.Blur))", visible))
        self.assertTrue(implies(visible, "!Skin.HasSetting(Bald.DisableBlur)"))


class NoDoubleBlurTests(unittest.TestCase):
    def test_tmdb_blur_only_without_the_helper_and_reset_with_it(self):
        for name in BLUR_WINDOWS:
            with self.subTest(window=name):
                loads = [(n.get("condition"), n.text) for n in ET.parse(XML / name).getroot().findall("onload")]
                sets = [c for c, text in loads if text == "Skin.SetBool(TMDbHelper.EnableBlur)"]
                resets = [c for c, text in loads if text == "Skin.Reset(TMDbHelper.EnableBlur)"]
                self.assertEqual((len(sets), len(resets)), (1, 1))
                self.assertTrue(implies(sets[0], f"!{HELPER} + {TMDB}"))
                self.assertTrue(implies(f"{HELPER} + Skin.HasSetting(TMDbHelper.EnableBlur)", resets[0]))
                sources = [c for c, text in loads if (text or "").startswith("SetProperty(TMDbHelper.Blur.SourceImage")]
                for condition in sources:
                    self.assertTrue(implies(condition, f"!{HELPER}"))

    def test_no_dead_colour_reset(self):
        self.assertNotIn("TMDbHelper.EnableColors", (XML / "Home.xml").read_text(encoding="utf-8"))


class HelperPropertiesTests(unittest.TestCase):
    """The names the skin reads are the ones Bald Helper writes."""

    def test_property_names_match_the_helper(self):
        blur = (ROOT / "addons" / "script.bald.helper" / "resources" / "lib" / "blur.py").read_text(encoding="utf-8")
        for name in ("Bald.Blur", "Bald.Blur.Last", "Bald.Blur.For"):
            self.assertIn(f'"{name}"', blur)
        self.assertIn('"Window({}).Property(Bald.FocusContainer)"', blur)
        skin = (XML / "Includes_Bald_Home.xml").read_text(encoding="utf-8")
        self.assertTrue(re.search(r"Window\(home\)\.Property\(Bald\.Blur\.Last\)", skin))


if __name__ == "__main__":
    unittest.main()
