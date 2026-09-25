# Skin spec: alpha 0.1 (Kodi 22)

Working name: `skin.gallery` (rename freely). This document is the source of truth for the first buildable version. It captures every decision made in the design prototypes so the build does not have to re-derive them.

Reference prototypes (interactive, placeholder art): the "Home v2 with movie and TV info screens" board on the design canvas. Real-data prototype: `kodi-skin-gallery-home-tmdb.html` (opens locally in a browser with a TMDB key).

---

## 1. Targets and constraints

| Item | Decision |
| --- | --- |
| Kodi | 22 only. No Kodi 21 support. |
| Skin API | Use the `xbmc.gui` version from Kodi 22's bundled Estuary: `/Applications/Kodi.app/Contents/Resources/Kodi/addons/skin.estuary/addon.xml`. Do not guess it. |
| Resolution | `1080i` folder, 1920 by 1080 coordinates. |
| Safe margin | 96 px on all sides for content. Artwork may bleed. |
| Hardware | Develop on macOS Kodi 22. Validate performance on CoreELEC (Ugoos AM6B+ and AM9 Pro) at a 1080 GUI. |
| Display | 77" OLED. Dark UI, true black where possible, burn-in mitigation required (see section 7). |
| License | GPL-2.0-or-later. The alpha forks Kodi 22 Estuary for every window this spec does not redesign, then replaces them over time. |

### Starting point

Fork Kodi 22's Estuary into the new skin id so every required window exists from day one. Then replace, in this order: fonts and colors, `Home.xml`, `DialogVideoInfo.xml`, shared includes. Everything else stays Estuary until it is redesigned.

---

## 2. Dev loop (macOS)

| Task | How |
| --- | --- |
| Repo | Git repo for the skin. Symlink the skin folder into `~/Library/Application Support/Kodi/addons/`. |
| Enable | Restart Kodi once. Enable under Add-ons, My add-ons, Look and feel, Skin, then select it. |
| Reload | Keymap entry in `~/Library/Application Support/Kodi/userdata/keymaps/` binding a key to `ReloadSkin()`. Also callable remotely through Kodi's event server. |
| Debug | `Skin.ToggleDebug` shows control ids and window names. Watch `~/Library/Logs/kodi.log` for XML errors. |
| Screen | Run fullscreen or in a 1920 by 1080 window. |
| CoreELEC | Sync the repo to `/storage/.kodi/addons/<skin id>` over SSH for hardware checks. |

---

## 3. Design tokens

### Type

One UI family: **Instrument Sans** (SIL OFL, ship the TTFs in `fonts/`). Clearlogos provide all title personality; the UI never uses a display face.

| Role | Size | Weight | Notes |
| --- | --- | --- | --- |
| Clock | 132 | 300 | Letter spacing -0.045em, line height 1 |
| Date | 22 | 400 | 66% ink |
| Caption title | 40 | 600 | -0.02em |
| Caption meta (year, runtime) | 20 | 400 | 80% ink |
| Accent line (rating, genres) | 18 | 600 | Accent color |
| Caption plot | 20 | 400 | Line height 30, 4 lines max, 76% ink |
| Media flag | 14 | 600 | Outlined chip, +0.04em |
| Menu item (open) | 46 | 600 | -0.02em |
| Menu note | 19 | 500 | 60% ink |
| Section line | 22 | 600 | Plus 17 px hint at 55% |
| Row label | 20 | 600 | Count at 17 px, 55% |
| Info title fallback (no logo) | 76 | 600 | -0.03em |
| Info meta | 24 | 500 | |
| Info tagline | 30 | 500 | |
| Info plot | 22 | 400 | Line height 34, 4 lines |
| Action button | 22 | 600 | Pill, 14 px vertical padding |
| Section heading (Cast, Details) | 22 | 600 | |

### Color

**Changed 2026-09-24 (tried in Kodi).** The fanart-tinted palette below is replaced for alpha by a blurred-fanart background and fixed tokens. A tinted `field` at 7% lightness read as near-black even at high saturation, and the user preferred the blurred art.

| Element | Rule |
| --- | --- |
| Background | The focused item's fanart, blurred (Gaussian radius 40 on a 480 px copy, from TMDb Helper), darkened to 30% brightness, over `field`. Crossfades 800 FADE between titles once the new image has loaded. |
| `field` | Constant `#0B0C10`. Base under the background, and the color of scrims and dimming layers. |
| `accent` | Constant `#9FB0C6`. |
| `ink` | Constant `#ECEEF2`. |

The original tinted palette, kept for a later release (it needs a small service add-on to compute three tokens with the k-means rule):

| Token | Rule |
| --- | --- |
| `field` | Dominant dark cluster of the fanart, lightness forced to 7%, saturation clamped 25 to 60% |
| `accent` | Most saturated mid-tone cluster (lightness 30 to 80%), lightness 68%, saturation clamped 45 to 80% |
| `ink` | Accent hue, lightness 93%, saturation 35% |

Monochrome art (accent saturation under 12%): keep everything neutral. Use accent at lightness 74% and its own saturation, and ink at 2% saturation, so black-and-white films never pick up a false tint.

Clustering: k-means, k = 6, on a 96 by 54 downsample. The JavaScript implementation in the real-data prototype is the reference.

Static values: scrims are black at the alphas given per component below. Focus ring is 3 px of `ink`.

---

## 4. Motion

### Curves

| Name | CSS | Kodi |
| --- | --- | --- |
| MOVE | cubic-bezier(0.215, 0.61, 0.355, 1) | `tween="cubic" easing="out"` |
| FADE | cubic-bezier(0.445, 0.05, 0.55, 0.95) | `tween="sine" easing="inout"` |
| POP | cubic-bezier(0.175, 0.885, 0.32, 1.275) | `tween="back" easing="out"` |

### Timings (ms)

| Event | Timing |
| --- | --- |
| Focus change settle before info swaps | 180 (hold info hidden while `Container.Scrolling`) |
| Caption text out | 130 fade and slide 14 px left |
| Caption text in | fade 380, move 540, stagger: title 0, meta 70, flags 95, accent 120, plot 170 |
| Fanart crossfade | 700 fade, plus settle zoom 1.05 to 1.0 over 1500 |
| Clearlogo on art | fade 520 and rise 10 px over 760, delay 380 after the art starts |
| Row scroll | 440 MOVE |
| Tile focus pop | 280 POP, scale 1.05 |
| Row edge nudge | 14 px over 110, then back |
| Row swap (Up or Down between rows) | out 140 fade and drop 18 px, in 360 fade and 440 rise |
| Menu open | caption out 180, menu in fade 380 and slide 40 px over 480, delay 120 |
| Menu close | menu out 160, caption back fade 380 and slide over 480, delay 140 |
| Background change | 800 FADE crossfade of the blurred fanart (was: palette change, 800 FADE on every tinted element) |
| Info open | home chrome out 200; art frame zoom to full screen 640 MOVE, delay 40; info content base delay 380 then stagger 0, 60, 100, 140, 180, 220, 270, 310 |
| Info close | content out 130; art frame back 540 MOVE, delay 160; home chrome back 380, delay 440 |
| Info section scroll | 560 MOVE; art dims to 60% field over 460 |
| Season change | episode row out 140, swap, in 340 |

---

## 5. Screens

### 5.1 Home (`Home.xml`)

Layout, all absolute at 1080:

| Element | Position and size | Notes |
| --- | --- | --- |
| Art frame | 96, 120, 1248 by 702 | Fanart, aspect scale to fill. Contains the logo overlay. |
| Logo scrim | inside frame | Linear gradient at 32 degrees: black 60% at 0, 26% at 30%, 0 at 54%. Only when a logo is shown. |
| Clearlogo | inside frame, left 52, bottom 46 | Max 560 by 170, keep aspect, bottom-left aligned, soft drop shadow. Original colors. |
| Clock and date | 1440, 104, width 384 | |
| ~~Callout~~ | Removed 2026-09-24 after a trial in Kodi: the Home screen reads better without the dot and hairline. | Was: dot 10 px at 1339, 505; hairline to 1440 at y 510, ink 50%; dot pops, line grows from the left |
| Caption | 1440, 420, width 384 | Title, meta, flags (movies only), accent line, plot |
| Menu (open) | 1440, 392, width 420 | Vertical list, 6 px gap; note paragraph below |
| Section line | left 1440, bottom 88 | Accent dot 8 px, current screen name, "Back for menu" hint |
| Row label line | 96, 856 | Label, row dots (6 px, active 95%, others 28%), count |
| Row | 96, 894, clip width 1248 | Landscape tiles 176 by 99, gap 16. Poster tiles 66 by 99, gap 12. |

Row behavior: `fixedlist` with the focus allowed to travel to slot 2 (landscape) or slot 5 (poster), then the list scrolls. Unfocused tiles 55% opacity, 40% while the menu is open.

Media flags: movies only (series-level items never show them). Source labels: `ListItem.VideoResolution`, `ListItem.HdrType`, `ListItem.AudioCodec`, `ListItem.AudioChannels`. Map to display strings: 4K, 1080p, Dolby Vision, HDR10, HDR10+, HLG, Dolby Atmos, 7.1, 5.1.

Title handling: caption title is always text. The clearlogo only ever appears on the art, controlled by the Appearance setting. No logo: show nothing on the art.

#### Focus map

| From | Key | Result |
| --- | --- | --- |
| Row | Left or Right | Move within row; nudge at ends |
| Row | Up | Previous row; from the first row, open the menu |
| Row | Down | Next row, if any |
| Row | Back | Open the menu |
| Row | Select | Open info (movie or TV) |
| Row | Context (C) | Kodi's context menu for the item (Play, Information, Mark as watched, add-on entries), drawn as the Home menu: caption slides out, items slide in at the menu position. Changed 2026-09-24 at the user's request; this replaces "Customize home, jumped to this row (0.2)", which stays reachable from the menu's last item. |
| Menu | Up or Down | Move; the row and art preview that screen live |
| Menu | Left or Select | Enter the screen (screens without rows stay in the menu) |
| Menu | Back | Close without switching |
| Menu | Settings | Open Kodi's native Settings hub (alpha maintenance access) |
| Menu | Last item | Customize home (0.2) |

Menu state lives in a window property (for example `Window(Home).Property(MenuOpen)`), set in `onup`, `onback` and `onleft` handlers. Caption, menu and section line animate on that property with conditional animations.

#### Idle

| Idle threshold | Behavior |
| --- | --- |
| 60 s untouched (prototype used 8 s) | Menu closes, row dims to 40%, row dots, count and hint fade out |
| While idle | Advance the row every 8 s if Ambient is on |
| While idle | Drift the whole screen 2 px on a slow cycle (burn-in guard) |
| First key press after idle | Wakes only; performs no action |

Kodi: `System.IdleTime(60)` conditions; drift as a slow slide animation with `pulse="true"`.

The "Back for menu" hint hides after the menu has been opened three times (skin setting counter).

### 5.2 Movie info (`DialogVideoInfo.xml`)

Open info as a dialog over Home. Home stays rendered underneath, so the art frame can zoom to full screen in Home itself with a conditional animation on the info dialog being visible, while the dialog fades its content in. This avoids a two-window handoff and gives true continuity. If that proves impossible, fall back to a zoom animation with a start rectangle of 96,120,1248,702 on the dialog's own full-screen fanart.

Alpha robustness update (2026-09-25): Home keeps this handoff and follows the current info item's artwork when a related title replaces it. When opened outside Home (library/search/add-ons), info draws its own full-screen artwork over `field`, fading in over 380 FADE and out over 130 FADE. Missing artwork leaves the field, never an unrelated title's art.

Layout (content column starts at x 96):

| Group | Top | Contents |
| --- | --- | --- |
| A | 150 | Logo box 170 tall (or 76 px title), meta, genres (accent), flags, tagline, plot (4 lines), actions, progress (in-progress only) |
| B | 880 | Cast: 112 px circles, name, role |
| C | 1130 | Details: Directed by, Written by, Video, Audio, Subtitles, Added |
| D | 1360 | More like this: 256 by 144 tiles |

Scrims: horizontal field 92% at 0, 72% at 32%, 0 at 64%; plus bottom field 85% at 0, 0 at 42%.

Scroll sections: offset 0, 560, 1000. Group opacity per section: A 1, 0, 0. B 0.85, 1, 0.3. C 0, 0.85, 0.5. D 0, 0.5, 1.

Actions: in progress gives Resume, Start over, Trailer, Mark watched. Otherwise Play, Trailer, Mark watched. Focused action is filled with `ink` and the label in `field`.

| From | Key | Result |
| --- | --- | --- |
| Actions | Left or Right | Move between actions |
| Actions | Down | Cast; if empty, focus Details at section offset 560 |
| Cast | Down | More like this; if empty, focus Details |
| Details | Down | More like this if available; otherwise stay |
| Details | Up | Cast if available; otherwise actions |
| Any | Up | Previous section |
| More like this | Select | Replace this info with that title |
| Any | Back | Close; return to the originating tile |

### 5.3 TV info (`DialogVideoInfo.xml`, TV show items)

| Element | Notes |
| --- | --- |
| Header | Logo, "years, N seasons, rating", genres, 2-line show plot |
| Actions | Resume or Play the next episode (for example "Resume S3 E2"), Trailer |
| Seasons | Horizontal tabs with an accent underline on focus. Content: `videodb://tvshows/titles/<dbid>/` |
| Episodes | 320 by 180 cards, gap 24, focus travels to slot 2 then scrolls. Content path depends on the focused season. Watched check, progress bar. |
| Episode detail | Code and title, runtime, air date, per-episode flags, one-line synopsis |

Opening from an episode (Next up, Continue watching) focuses that episode in its season. Opening from a show focuses the primary action.

Art dims to 70% field at rest on this screen because content runs the full height.

### 5.4 Customize home (0.2, not in alpha 0.1)

Three columns, fully D-pad driven: Screens (plus Add screen, Appearance), the screen's settings and rows, and the row's settings (Content, Style, Items, move, remove). Select cycles values. Build on script.skinvariables, as Arctic Fuse does, so menus and widgets are stored as JSON and rendered into includes.

Appearance settings: Clearlogo on artwork (default on), Media flags (default on), Ambient when idle (default on).

---

## 6. Default rows (alpha uses a fixed configuration)

| Screen | Rows |
| --- | --- |
| Home | Recently added movies, Continue watching (movies and episodes), Next up |
| Movies | In progress, In 4K (poster), Unwatched (poster) |
| TV shows | Next up, All shows (poster) |
| Live TV | None (select opens the guide) |
| Search | None |

Content sources to confirm for Kodi 22: recently added (`videodb://recentlyaddedmovies/`), smart playlists in `special://skin/playlists/` for in progress, unwatched and 4K. Next up and a mixed movies-plus-episodes Continue watching need either TMDb Helper or script.skinvariables; confirm which Kodi 22 compatible option provides them.

---

## 7. Open items and risks

| Item | Plan |
| --- | --- |
| Palette extraction | Deferred. Alpha uses the blurred-fanart background and fixed tokens (section 3). A tinted accent and ink need a helper that exposes three k-means tokens; TMDb Helper's color feature gives one mean color at one forced lightness. |
| Dynamic colors | Confirmed: `colordiffuse` accepts `$INFO` / `$VAR` values in Kodi 22 (used while trialling the tinted field). |
| Dark clearlogos | Prototype turns near-black logos white by measuring brightness. Kodi cannot read pixels natively, so the alpha relies on the drop shadow. |
| Atmos flag | Confirm how Kodi 22 exposes Atmos in stream details. |
| Fanart performance | Measure on AM6B+ and AM9 Pro: crossfade plus settle zoom plus tinted fades. Reduce the settle zoom first if frames drop. |
| Burn-in | Idle drift, dimming, and ambient advance are required, not optional. |

---

## 8. Milestones

1. Fork Estuary into the new id, swap fonts, confirm it loads on macOS Kodi 22.
2. Home layout, static: art frame, caption, clock, row, flags, logo on art.
3. Home motion: settle, crossfade, staggered caption, row swap, summoned menu, idle.
4. Movie info with the art-frame handoff and Back returning to the tile.
5. TV info with seasons and episodes.
6. CoreELEC performance pass.
7. Then 0.2: Customize home and Appearance via script.skinvariables. Then 0.3: Live TV.
