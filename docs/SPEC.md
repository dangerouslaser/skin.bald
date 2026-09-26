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

One UI family at a time: **Instrument Sans** by default, or **DM Sans** as an optional skin-wide alternative, selected in Bald Settings › Appearance › Typography (both SIL OFL, static TTFs shipped in `fonts/`). Each is a `Font.xml` fontset with the same font names and sizes. DM Sans' fontset adjusts line spacing so multi-line text keeps Instrument Sans' pixel line heights. The scale below is specified in Instrument Sans. Clearlogos provide all title personality; the UI never uses a display face.

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
| Info page change | Incoming 360 FADE + 18 px rise over 560 MOVE; outgoing 130 FADE; sharp/blur crossfade 460 FADE |
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
| Row | 96, 894, clip width 1248 | Landscape tiles 176 by 99, gap 16. ~~Poster tiles 66 by 99, gap 12.~~ Poster rows: see Row styles below. |

Row behavior: `fixedlist` with the focus allowed to travel to slot 2 (landscape) or slot 5 (poster), then the list scrolls. Unfocused tiles 55% opacity, 40% while the menu is open.

Row styles (2026-09-26): each configured row has a style, chosen in the widget editor: **Fanart** (default; the landscape tile above), **Thumbnail** (same tile; episode stills, else landscape art, else fanart), **Fanart with logo** (the fanart tile with the item's clearlogo at its bottom left, max 100 by 34, 8 px in, over the logo scrim; hidden without a logo or with clearlogos off) and **Poster**. A poster row reuses the Poster-low composition (5.10) and replaces the "66 by 99" poster tile above: rail at 96, 738, 1248 by 234, eight 156 px slots with 140 by 210 posters (2.5% focus pop and ring), focus to slot 5; row label line at 96, 712 (12 px above the posters, as on landscape rows); episodes use the season poster, then the show's. The art frame shrinks to 1248 by 576 (96, 120) while a poster row is shown or previewed: the bottom edge (frame mask, logo scrim, clearlogo) moves up 126 px and the art up 63 px so the crop stays centred, both 540 MOVE after 30 (the info close's frame timing), and back the same way for a landscape row; a fixed mask over the new bottom edge fades in 200 FADE after 370 and out 150 FADE. This runs alongside the row swap (out 140, in after 170). With info open from a poster row the art's 63 px returns in step with the frame zoom (640 MOVE after 40), so the zoom about 274,343 is the same as from a landscape row; it moves up again with the zoom back (540 MOVE after 30).

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
| Menu | Up or Down | Move; preview that screen at its last active widget row and item |
| Menu | Left or Select | Enter the screen (screens without rows stay in the menu) |
| Menu | Right | Open the selected screen's full native library when a disclosure chevron is shown |
| Menu | Back | Close without switching |
| Menu | Settings | Open Kodi's native Settings hub (alpha maintenance access) |
| Menu | Last item | Customize home (0.2) |

Menu state lives in a window property (for example `Window(Home).Property(MenuOpen)`), set in `onup`, `onback` and `onleft` handlers. Caption, menu and section line animate on that property with conditional animations.

Settings separates Kodi's native categories from a dedicated **Bald Settings** tile and customization view. Customization uses Arctic Fuse 3's screen-first behavior as a reference: Home is mandatory and enabled by default; Movies and TV Shows are optional screens, each with its own independent widget node. Live TV is an optional menu destination, enabled by default, which opens the guide and has no widget editor. Enabling an optional screen adds it to the Home main menu; disabling it removes the menu entry rather than falling back to a different native-library action. Each widget screen supports up to 20 ordered rows. The editor regenerates the three Home-screen includes when it closes. CoreELEC and LibreELEC use their native service launch actions (`RunAddon(service.coreelec.settings)` and `RunAddon(service.libreelec.settings)`) and appear only when the corresponding service is enabled; unsupported platforms therefore show no dead entry.

Context menu update (2026-09-25): show at most five actions, scrolling as focus moves beyond the visible entries, with no wrapping at either end. Keep the main menu's instant scroll and 56 px buttons / 6 px gaps. The selected action's tooltip uses the same note position (1466,714), 394 px width, font and opacity as Home. Native and known add-on actions have descriptions; unknown actions use a generic label-based hint.

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

Approved paged revision (2026-09-25): three fixed pages replace the long scrolling column. No cast peek on Overview and no additive section offsets.

| Page | Layout | Contents |
| --- | --- | --- |
| Overview | Content x96, y150 | Existing logo/title, meta, genres, flags, tagline, plot, actions and progress |
| Cast & details | Poster 96,156,432,648; right column x624, width1200 | Title/meta above five 240 px cast slots at y378; 112 px portraits with name/role; Details heading y650, three 380 px columns at y696 and y796 |
| More like this | Home-sized frame 96,120,1248,702; shared Home caption x1440, title ending at y464, width384; row y884 | Highlighted recommendation's fanart, title, year/runtime, movie media flags, genres and plot; Home's staggered caption transitions and landscape tiles, 440 MOVE scrolling |

Scrims: horizontal field 92% at 0, 72% at 32%, 0 at 64%; plus bottom field 85% at 0, 0 at 42%.

Overview retains sharp fullscreen fanart. Moving down crossfades over 460 FADE to Home's shared blurred backdrop (TMDb Helper cached blur: 480 px, radius40, brightness30%). Cast uses the original movie's art; recommendations follow the highlighted item. Up restores sharp fanart. Without blur support/art, use the opaque field. Each page fades in over 360 FADE and rises 18 px over 560 MOVE; the outgoing page fades out over 130 FADE. Preserve each list's selection when changing pages.

Recommendation previews explicitly read container5100; they must not replace the native dialog item until Select. The highlighted title's clearlogo uses Home's artwork overlay (52 px from the frame's left, 46 px from its bottom, max560×170), logo scrim and fade/rise transition. Fall back to `tvshow.clearlogo`; if neither exists, show no logo or scrim. Loading/empty recommendations have an escapable focus target. The page trail sits at y954 on the first two pages; the recommendation page uses Home-style right-hand hints.

Actions: in progress gives Resume, Start over, Trailer, Mark watched. Otherwise Play, Trailer, Mark watched. Focused action is filled with `ink` and the label in `field`.

| From | Key | Result |
| --- | --- | --- |
| Actions | Left or Right | Move between actions |
| Actions | Down | Cast & details; focus cast, or Details if cast is empty |
| Cast / Details | Down | More like this; focus its list, or the loading/empty state |
| Cast / Details | Up | Overview; restore previous action |
| More like this | Up | Cast & details; restore cast selection, or Details if empty |
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

Appearance settings: Clearlogo on artwork (default on), blurred fanart backgrounds (default on), media flags (default on), Ambient when idle (default on), and an optional auto-hide for the Home navigation hint. Bald Settings follows Arctic Fuse 3's launcher pattern: its Customization entry opens the screen-first widget editor, while Appearance opens a focused Bald-owned settings window instead of the inherited Estuary skin settings.

---

### 5.5 Movie library — approved first native view

The first redesigned library view replaces Estuary for movie browsing only; other content types retain their existing views. Use three large posters on the left and the selected movie's artwork preview and details on the right.

- Heading at (96,108); sort summary right-aligned at (1296,120), width 528.
- Horizontal native list 510 at (84,210), 1152 × 648, with three 384 px slots. Posters are 360 × 540 at slot offset (12,12), with title labels beneath. Preserve artwork proportions and center-crop to fill the 2:3 frame, rather than letterboxing nonstandard posters. Focus pop: 100 → 102.5%, 280 ms POP; scrolling: 440 ms MOVE.
- Artwork at (1296,222), 528 × 297. Reuse Home's 700 ms crossfade and 1500 ms settle zoom, with backdrop masks preventing frame overflow.
- Caption width 528; title area y548–636, metadata starts y636. Reuse Home's staggered title, metadata, **media flags**, genres and plot. The background uses the same optional blurred-fanart treatment as Home.
- No separate Open details button. Footer at y954; item count left, navigation hints right.
- Left/Right browses; Up opens native view/sort/filter options; Down enters letter browsing; Info opens the existing paged detail dialog. Select follows Kodi's global default-select action (approved as Show information on the development installation). Back from details restores the selected movie.
- Letter mode shows a full 0–9, A–Z strip beneath the posters at (96,888), width1134, with a quiet label at y856. The active group uses the accent color and a 6 px dot; available letters use 70% ink and absent letters 34%. The first cell is 68 px wide; the 26 letter cells are 41 px each. Numbers, symbols and non-Latin initials share the first indicator. Left/Right uses Kodi's native previous/next-letter groups, skipping absent groups and updating the posters and preview without filtering or reloading the library. Up, Select or Back returns to the selected poster (Select does not open details until back in normal browsing). Native title sorting/article handling and filtered results are respected. If another sort is selected, prompt for Title sort instead of changing the user's sorting preference. Mode-specific footer hints use the shared 20 px dot spacing.
- Audio flags show the reported codec through Kodi's shared codec-name map (including Atmos/DTS:X profiles when reported), followed by the channel flag. Missing codec data produces no chip. This applies consistently to Home, recommendations and the info overview as well.
- Home's Movies menu opens the native movie library. Existing alternative view choices remain available.
- Library options replace the right-hand artwork and caption, retaining the posters at 72% of their normal opacity. The menu exactly reuses Home's geometry and row components: (1440,392), width420, five 62 px rows (56 px text height plus 6 px gap), instant scrolling with no wrapping. Home's menu type, accent dot and fade/slide timings apply. Heading and tooltip align to x1466 at width394. Left/Back returns to the posters; Up or Kodi's Menu action opens options. The footer switches immediately to the return/select hints with the same 20 px dot separator.
- Options retain native View, Sort by, Order, Filter, Watched status and Update library behavior. Search launches the themed Global Search window, scoped initially to the current library type: Movies for movie views, TV Shows for series and season views, and Episodes for episode views. Current view/sort/order/watched values appear in the tooltip. Untouched views retain the Estuary sidebar; secondary sort/filter dialogs remain native.

---

### 5.6 Movie poster wall — full-width variant

- Native movie panel511, selectable alongside Bald posters. Eight columns × two rows: panel at (84,210), 1728 × 624, slots216 × 312. Posters are192 × 288, center-cropped, with the existing 2.5% focus pop and outline. No per-poster text; the selected title appears in the header.
- Selected title at (96,108), width1100, metadata at y168. Media flags right-aligned at (1296,168), width528, including audio codec. Shared staggered caption motion and blurred selected-fanart background apply.
- Direction keys traverse the grid and scroll rows. Up at the top or Left at the left edge opens options; Menu also opens options. Right at the right edge enters letter mode; Down at the end of the library also enters it. Letter navigation and return behavior match section5.5.
- Shared Home-width options menu replaces the rightmost two poster columns; the remaining posters dim to35%. Frame masks stay opaque. Other view choices remain available.
- The full alphabet strip, footer alignment, native Select/Info actions and 20px hint separators remain consistent with the first library view. The right-side artwork-preview variant is described in section5.7.

---

### 5.7 Movie poster wall — artwork-preview variant

- Native movie panel512, labeled Bald wall with preview, follows the full-width wall in the view cycle. Five columns × two rows at (84,210), 1080 × 624; shared 216 × 312 slots and 192 × 288 cropped posters.
- Reuses section5.5's right-hand 528 × 297 artwork, staggered title/metadata/media flags/genres/plot, menu transitions and opaque overflow masks. The selected title lives in the preview rather than repeating above the grid; the header reads Movies.
- The blurred background follows container512. Grid navigation, full alphabet, footer and native information actions match section5.6. Options replace only the preview; posters dim to72% while the menu is open.
- All three Bald movie layouts remain available. Shared preview controls are parameterized so fixes apply to both the three-poster view and this wall.

---

### 5.8 Movie compact list

- Native vertical list513 at (96,222), 1140 × 624; thirteen 48px rows. Title, year and runtime columns, with quiet Resume/Watched text at the right. Resume takes precedence when a watched movie is partly replayed. Unwatched items have no status label.
- Selected row uses full ink and an 8px accent dot; other rows use70% ink. Instrument Sans section text for titles, caption metadata for year/runtime. No posters or extra Open details button.
- Reuses the existing 528px right-hand preview, media flags including audio codec, blurred backdrop and options transitions. Shared alphabet and 20px footer separators remain unchanged.
- Up/Down browse and scroll; Left or Menu opens options. Right enters letter mode; Down at the end also enters it. Up at the start opens options. Select follows the native default action, Info opens details, and Back from details restores the selected row.
- The artwork-focused alternative is described in section5.9.

---

### 5.9 Movie artwork-focused list

- Native vertical list514 at (96,222), 624 × 616; seven 88px rows. Larger title text with year/runtime and quiet Resume/Watched status beneath. The selected title can scroll when too long; no poster thumbnails.
- Fanart at (816,180), 1008 × 567. Shared Home700ms crossfade and1500ms settle zoom, bounded by fixed opaque backdrop masks. Clearlogo at frame offset(40,378), maximum504 × 153, with Home fade/rise and logo scrim. Missing logo leaves the artwork unobstructed.
- Metadata at y774, codec-inclusive media flags at y806, and a two-line synopsis at y848. Caption motion reuses Home's staggered fades/slides. Synopsis hides in letter mode so the shared full alphabet at y888 remains legible.
- Native navigation, alphabet, footer and information actions match the compact list. Options replace the artwork/details region at the existing right-hand menu position; list dims to72%. Blurred background follows container514. Other layouts remain available.

---

### 5.10 Movie poster-low view

- Native horizontal list515 at (96,738), 1248 × 234, exactly matching the fanart width; eight 156px slots. Posters are140 × 210 at slot offset(12,12), center-cropped, with the shared2.5% focus pop and outline. The focused artwork and ring remain inside the list clip.
- Cinematic fanart at (96,120), 1248 × 576 with the shared700ms crossfade and1500ms settle zoom. A clearlogo sits at frame offset(52,392), maximum560 × 138, over the Home logo scrim. Fixed backdrop masks contain the zoom without the black-box transition seen in earlier preview work.
- Shared Home caption at x1440, title y270 and body y402 provides title, year/runtime, codec-inclusive flags, genres and plot. Sort summary remains at the upper right. The blurred background follows container515.
- The poster rail sits beneath the artwork with its item count at y704; navigation hints use the skin-wide bottom baseline at y954 in the open space to the rail's right. Left/Right browses; Up or Menu opens options; Down enters the shared alphabet. Alphabet mode covers the poster rail with the aligned blurred backdrop before drawing its strip at y888, retaining the native selection underneath. Options hide the caption and dim artwork/posters to72%; the shared Home-width menu sits wholly to the right of the artwork and poster rail, so it needs no additional backdrop panel. The open-menu footer ends at the shared x1824 safe edge from (1404,954), matching the other library hints.
- Select follows Kodi's native default action; Info opens details and Back restores the selected poster. Other library layouts remain available.

### 5.11 TV library — primary Series, Seasons and Episodes path

- Kodi retains independent native view modes for each content level: Series520, Seasons530 and Episodes540. The first implementation completes this full drill-down before adding alternative layouts.
- Series520 reuses the three-poster movie geometry and shared artwork preview. Its caption shows series years, season count, watched progress, genres and plot; series-level media flags remain hidden. Alphabet browsing remains available. Select enters the show's seasons and Info opens TV details.
- Seasons530 keeps three large season posters with `season.poster`, `tvshow.poster` and container TV-show poster fallbacks. The right preview retains show artwork/clearlogo where season art is absent and shows watched/total episode progress. Specials remain native list items. Seasons do not expose alphabet mode.
- Episodes540 uses a seven-row artwork-focused list at x96 and a1008×567 16:9 preview at x816. Rows show S/E code, title, air date, runtime and Resume/Watched state. The preview shows episode thumb, then episode/show fanart fallback, followed by episode metadata, codec-inclusive media flags and plot. Episodes do not expose alphabet mode.
- All three levels share the Home-width library options menu, x1824 footer alignment, blurred selected-art background, native sorting/filtering/context actions and 440 MOVE scrolling. Missing artwork falls back through Kodi's native TV artwork inheritance and then the field/placeholder—never unrelated art.

### 5.12 TV library — alternative layouts

- Series adds three alternatives to the primary three-poster shelf: a five-column/two-row wall with the shared right preview (521), a thirteen-row compact list with the same preview (522), and a cinematic poster-low view (523). All retain alphabet browsing, Series metadata, native Select/Info behavior and the shared options/footer geometry.
- Seasons adds a thirteen-row compact list (531) with episode totals and watched progress. It retains the selected season/show artwork preview and clearlogo fallback; Seasons never enters alphabet mode.
- Episodes adds a thirteen-row compact list with a 528×297 selected thumbnail and caption (541), plus a five-column/two-row 16:9 thumbnail wall using 192×108 cards (542). Both retain episode code, title, air date/runtime, watch state, media flags and plot; Episodes never enters alphabet mode.
- The View option cycles only within layouts valid for the current content level and keeps the options menu open after every switch: Series 520→521→522→523, Seasons 530→531 and Episodes 540→541→542. Legacy Estuary video views remain unavailable for all three redesigned TV levels.

### 5.13 Search surfaces

- Home Search launches Global Search directly. If the optional add-on is missing or disabled, Kodi's normal install/enable path remains available; there is no intermediate destination chooser.
- `script-globalsearch.xml` is supplied as an active-skin override while the add-on retains ownership of queries, result population, selection, playback and information actions. Its Bald contract uses the add-on's default result view50, categories9000, new-search990, category991 and empty-state999.
- The results window mirrors the library compact list: Bald field and shared cached blurred-fanart backdrop, title and query at the safe left margin, compact rows, a sharp selected-art preview and a Home-width options menu at x1440. Up/Left replaces the preview with New search followed by the available result categories and counts. Focus, nested category navigation, new search, context actions and Back remain Global Search contracts. Home keeps its Search menu focused underneath the modal so closing results returns to Search rather than the content row.
- Kodi's native keyboard retains every required control ID and navigation route while replacing Estuary's dialog tint, input outline, type and character-key focus treatment with Bald field, ink, outline and pill tokens. Keyboard input, autocomplete, password/numeric variants, confirmation and cancellation remain native contracts.
- Result windows owned by external add-ons are outside the skin's XML contract; native video results continue into Bald library/detail views where their content type supports them.

### 5.14 Live TV guide

- Home Live TV opens Kodi's native TV Guide directly. The first PVR milestone provides one primary vertical timeline view and disables Estuary's alternate guide orientations until Bald variants exist.
- The Guide retains Kodi 22's native EPG grid50, channel-group binding11, wrapper63, scrollbar60, channel-number input, menu9000, programme information and timer/recording actions. Control11 remains available to Kodi but is not rendered as a wide carousel.
- Layout uses the 96px safe margin: heading/clock at the top, a lightweight selected channel/programme summary above the grid, date strip at y354 and timeline from y420. The guide deliberately avoids per-programme fanart so focus changes remain responsive on CoreELEC-class hardware. Channel rows use logos, number/name and 68px spacing; programme blocks use quiet ink surfaces with an accent focus marker and progress/timer marks.
- Left moves backward through programmes and earlier guide time. At the grid's left boundary, Left opens the 480px right-side Guide tools drawer matching Home. For HDMI-CEC remotes, Back opens the drawer from anywhere in the grid; Back or Return to guide closes it, and an explicit Exit Live TV action returns Home. The drawer provides Jump to now, Choose channel group, Choose date and Search through Kodi's native `PVR.EpgGridControl` actions. Right never transfers remote focus to the thin scrollbar; the scrollbar remains the grid's page control. Programme focus uses a narrow accent marker so it cannot be confused with Kodi's current-time progress shading.
- This milestone does not replace Channels, Recordings, Timers or programme dialogs. Those remain native Estuary contracts until their dedicated Bald passes.

### 5.14 Native popups

- Shared confirmation, selection, settings and file/add-on popup surfaces use the fixed `field` panel, a quiet 10% `ink` header, Instrument Sans typography and Bald pill actions. Preserve every native control ID and dispatch action.
- Dialog action buttons are 72 px high with an 8 px gap, retaining Estuary's 80 px stacking rhythm without intersecting outlines. Focus fills the pill with `ink`; unfocused actions use the 45% `ink` outline.
- Standard popup lists use 70% `ink` labels and a 10% `ink` focus row. The native backdrop dims behind the panel and uses the standard dialog fade rather than introducing a separate motion language.

### 5.15 Shared foundations (2026-09-26, for review)

Decisions the spec does not cover, made while moving Kodi's control defaults, the select dialog layouts and the shared Estuary buttons onto Bald tokens. Nothing here is seen in Kodi yet.

- **Control defaults.** A control that sets nothing reads as Bald: labels and fadelabels in `Bald_InfoPlot` at full `ink`, textboxes in `Bald_InfoPlot` at 70% `ink`, disabled text 28%, selected and invalid text in `accent`.
- **Default button focus is a quiet pill, not the action pill.** Kodi draws focused text in the text colour when a control has no focused colour, and many buttons bring their own focus texture and rely on that. A default focused colour of `field` (needed on an `ink`-filled pill) would put dark text on those buttons, so the default button is a pill filled with 28% `ink` when focused and a 45% `ink` outline otherwise, with full `ink` `Bald_Section` text. Real actions keep using `DefaultDialogButton` (the `ink`-filled pill).
- **Default setting rows** (radio button, spinner, slider, edit, colour button) use the TV guide tool row's surface: 10% `ink` on focus, 60% `ink` text turning full `ink`, no dot (the dot texture only stays round at the scaffold's 56 px row height). Their state marks are the settings scaffold's: `accent` and dim dots for radios, chevrons for spinners, the 4 px track and 16 px nib for sliders, a 20 px dot for colours. Progress bars are a full `ink` bar on a 10% track; scrollbars are 10% / 34% / full `ink`.
- **Select dialogs.** The stream pickers (video, audio, subtitles) mark the stream in use with the `accent` check the profile list uses, and the default stream with Estuary's star tinted with the row's secondary ink. The list and the action column are separated by a 10% `ink` hairline instead of Estuary's inset panel; the page indicator is 4 px. The item count is `Bald_Hint` at 60% `ink`.
- **Game pickers.** The filter, stretch, rotation and in-game save pickers are bottom sheets of opaque `field` with a 10% `ink` hairline on top (fade 300 FADE), tiles on a `placeholder` well, and the Home tile focus ring on the focused preview. Game saves tiles use the 10% `ink` focus surface.
- **Colour themes.** Kodi's "Skin colours" setting now offers only Bald's palette (`colors/defaults.xml`); Estuary's 14 themes are gone.

### 5.16 Playback (proposed, 2026-09-26)

Not in the prototype; proposed for review in Kodi. Shared pieces live in `Includes_Bald_Playback.xml`. Kodi's and Estuary's control ids, actions and visibility rules are unchanged; only the drawing is new.

- **Seek bar** (`DialogSeekBar.xml`, shown with the OSD, the info overlay and the time display). Bottom scrim: the info dialog's `scrim_info_b` in `field`, reaching up to y 542. Left at x 96: clearlogo box 480 x 120 (bottom at y 676), else the title (Caption title 40, y 628); meta line y 688 (Caption meta 20, 80% ink: "S1 E2 · Title", "2019 · Drama", channel and times for live TV, artist and album for music, then the chapter); media flag chips y 728 (the caption chip, from the player's own labels). Right column (x 1296 to 1824, right-aligned): recording mark (accent dot and "Currently recording") y 568, seek state (Accent 18, accent: "Paused", "Seeking +30s", "Fast forward 4x") y 604, elapsed / total (Info tagline 30, ink) y 640, "Ends at 21:43" or the timeshift position (60% ink) y 688.
- **Track.** A 4 px rounded line at y 768 from x 96 to 1824 in 28% `ink`; the cached part in 45%, the played part in full `ink`; the playhead a 16 px dot in `accent`. Chapters and scene markers are 8 px `field` gaps in the line, cut points 60% dashes, bookmarks accent dashes, edit-list ranges a 60% band. Live TV draws the timeshift buffer in 45% and the programme so far in `ink`, with the programme's start and end times (Hint 17, 60%) under the ends.
- **Info overlay** (Info while playing): the same block plus the tagline and plot (Caption plot, 5 lines, 80% ink) at y 386 to 536 and a taller scrim; what plays next sits on the hint line at the left ("Up next · …").
- **OSD** (`VideoOSD.xml`, `MusicOSD.xml`): one row of icon buttons at y 818 under the track, transport from x 96 and tools ending at x 1824. Each button is 64 x 84: Estuary's icon at 56 px in 60% `ink`, full `ink` when focused with an 8 px `accent` dot under it (the Home menu's dot, turned to sit under an icon) and the tile pop (1.05, 280 POP). Selected states keep their icons (play/pause, random); record turns `accent` while recording. Up from the row focuses the track; an 8 px accent dot left of the track marks it, and Left/Right skip. Hints on y 954, right-aligned: the focused button's name, then "Up to seek" (or "Left and right to skip · Down for controls" on the track). The OSD opens with 380 FADE and a 40 px rise over 480 MOVE and closes in 160.
- **Pause and seek header** (`Custom_1109_TopBarOverlay.xml`, seeking or paused without the OSD): top scrim (the same texture flipped); the state (Info meta 24) at 96,108, the time and chapter (Caption meta, 70%) at y 146 and a 1200 px track at y 206; Home's clock (132) at 1440,104 with the finish time where Home has the date. In the OSD and info states only the clock shows at the top. After 5 s paused the header fades out (480), as Estuary's top bar left the screen.
- **OSD settings** (`Custom_1101_SettingsDialog.xml`): a right-hand drawer rather than a centred popup. The player dims to 60% `field` with the info dialog's horizontal scrim mirrored; the heading (Caption meta, 60%) at 1178,292 and the settings scaffold's rows (56 px, 6 px gap, Section 22 at 45%, accent dot and 6 px slide on focus, value right-aligned, toggles as state dots) in a 672 px column ending at x 1824. Opens like the Home menu (fade 380, 40 px slide over 480 after 120), closes in 160.
- **Small player popups** (`DialogSlider.xml`, `Custom_1110_TempoControl.xml`): an opaque `field` panel, 840 wide, centred at y 96; the name in Section 22 at 60%, the value in Info meta 24; the settings slider (4 px track, 16 px nib, accent when focused) or the settings chevrons (45%, full ink focused).
- **Bookmarks** (`VideoOSDBookmarks.xml`): over the dimmed player and the bottom scrim, the heading at y 560, the pill actions at y 632 and a row of 288 x 162 rounded thumbnails at y 736, unfocused at the poster dim, focused full with the tile focus ring; time and chapter under each.
- **Player controls** (`PlayerControls.xml`, outside full screen): the Bald popup surface with the art at the right, title, artist and meta, the track and the OSD buttons, and the focused button's name under them.
- **Subtitle search** (`DialogSubtitles.xml`): services as a standard popup list; results with the language code in a flag chip, the release name over the language, and the rating, hearing-impaired and sync marks in 60% ink; 10% ink focus row; a 4 px scrollbar.
- **Buffering** (`VideoFullScreen.xml`): a 110 px `field` disc at 60% with Estuary's cache ring in `accent` and the percentage. The view-mode lines sit at the top left over the top scrim.
- **Icons.** Bald has no icon set: the OSD uses Estuary's `osd/fullscreen/buttons` icons, tinted with Bald tokens.

### 5.17 Global overlays (added 2026-09-26, for review)

- Busy, toasts, background progress, volume and the text viewer are quiet chrome over any window: an opaque `field` surface with a 10% `ink` wash (a pill capsule for the busy and volume indicators, a plain panel for toasts, the volume slider and the text viewer), Instrument Sans at caption sizes, `ink` text, and the `accent` only for progress fills and the focused slider nib.
- Placement: an overlay band at y 48 (half the safe margin) holds the long-lived indicators so they never cover titles or the Home clock. Background progress ends on the right safe edge: one line of dots, title at 80% and step at 45% joined by the 20 px dot separator, with a 360 px, 4 px accent bar beneath. The volume capsule (420 x 54) is centred in the band. Toasts are a 560 x 104 card at the safe top (y 96) on the right safe edge. The busy capsule (108 x 54) is centred over a 60% `field` scrim, with no scrim over fullscreen video or games. The volume slider is a 640 x 96 panel centred above the hint baseline (y 834). The text viewer is a 1440 x 770 centred popup with the page count ("2 / 5") at the right of its header.
- Background progress shows one status line: the step is dropped when empty or already part of the title, and the percentage is shown by the bar alone. It fades out over fullscreen video and games.
- Busy is three 12 px dots that brighten in turn (28% to full `ink`, 360 each way, 180 apart, 1200 ms cycle) instead of a spinner, since Bald's motion is fade, slide and zoom only.
- Motion: overlays fade in over 240 and out over 160 (FADE) with a 14 px slide (24 px from the right for toasts) over 360 in and 200 out (MOVE). The text viewer keeps the shared popup open and close.

### 5.18 Live TV windows and dialogs (2026-09-26, for review)

Design decisions the spec did not cover, taken in the Live TV restyle (docs/NOTES.md, "Live TV windows restyle"). The guide (5.14) is unchanged.

- Channels, Recordings, Timers, Search and Providers reuse the Library/Search layout: title at 96,108, accent section line at y 174 (TV or Radio, then group, provider or search), list at 96,222 (1140 wide, eight 84 px rows), preview column at 1296,222 (528 wide) and hints on y 954. Channel rows: number, logo, name, programme line and a 4 px progress bar in `accent`; other rows: optional state icon tinted `ink`, title with a right-hand value, and a second line. Focus is full `ink` plus the accent dot; unfocused text is 70% / 45% `ink`.
- The options column replaces Estuary's sidebar at the Home menu's x 1440 in Bald Settings' row style (accent dot, state dot at the right for Kodi's toggles). Left opens it, the preview gives way with the menu-open motion, and Left, Right or Back return to the list. Channels keep one view.
- Over live video, the channel switcher and mini guide are left-column overlays on the field scrims (no panel), entering with the menu-open move from the left (fade 380, slide 40 px over 480). The switcher's Left and Right change channel group.
- Programme and recording information: channel line, 76 px title, accent line (premiere, finale, live or new, then genre), when, episode, progress, 22 px plot and Kodi's actions as the info dialog's pills; art and details at the preview position. Content enters with the info stagger (0-180 ms). The dialog lays `field` at 60% plus the scrims over whatever is behind, and the programme's fanart at backdrop brightness when there is one.
- Guide controls are text pills (48 px, `Bald_RowLabel`) grouped Programme / Channel / Group on a `field` bar with a 10% `ink` top rule; the 12-hour steps read "−12 h" and "+12 h".
- Channel and group managers keep the shared popup surface; lists use the popup list rule (70% `ink`, 10% `ink` focus row), settings rows use Bald Settings' rows, and boxed Estuary panels are removed.


### 5.19 Browsing outside the Bald movie and TV views (2026-09-26, proposed; not yet run in Kodi)

Design decisions the spec did not cover, for review. They restyle Estuary's library views (50-55, 500-504) and the windows that browse with them (video add-ons and plugins, files and sources, sets, genres, actors, playlists, music videos, the add-on browser and information, favourites, programs, the file manager, the event log and the smart playlist editor), keeping every Kodi-bound id and action.

- **Page.** The Bald library page: field background, title at (96,108) in caption-title type with the folder trail after it at 60% ink, the sort summary right-aligned on the x 1824 safe edge at y 120, the item count at (96,954) and hints on the y 954 line. Windows still laid out for Estuary's content top (y 100) keep their header at y 24 until they are redesigned (TopBar `top` param).
- **Background.** No blur outside the Bald views: TMDb Helper's blurred image is only kept current for the video library's Bald views, so browse windows would risk showing unrelated art. Instead the focused item's fanart sits at the backdrop brightness under a 60% field layer (about 12% visible), over the opaque field.
- **Preview column.** Lists and walls with room for it show section 5.5's preview column: 528 x 297 art at (1296,222) and the staggered caption beneath (title, one meta line, codec flags for videos, genre in the accent, four to five lines of plot or add-on description). Items without landscape art show their poster, thumb or icon whole inside the frame. The art crossfades in place (fadetime) without the settle zoom, so it needs no backdrop masks over the non-blurred background. It hides for the parent-folder item and while the options menu is open.
- **Lists.** 50 (and the lists inside 502 and 503): 48 px rows as the compact list (5.8). 55, the main add-on and plugin list: 56 px rows with a 40 px icon for add-ons, plugin folders, playlists and favourites (add-on rows also show author and version, and Estuary's status and origin marks tinted to accent and 45% ink), text rows for videos and songs. 504 (versions and extras): 88 px rows with a 112 x 63 still. Focused rows use full ink and the 8 px accent dot; other rows 70% ink.
- **Walls.** One tile language (Bald_LibraryPosterItem's placeholder, 3 px ink ring and 2.5% pop) in three shapes chosen by content: 2:3 posters (216 x 312 slots), 16:9 stills with a label (288 x 216) and square covers and icons kept whole with a two-line label (216 x 276). 500 is full width with the focused title and meta line at y 858; 54 is five posters wide beside the preview; 52 is the full-width icon wall for files, sources, genres and similar; 501 shows banners three across. 51 is the three-poster view of 5.5 with the preview; 53 is a poster rail at y 534 under a large title, meta, genre and plot, with the preview art at the right.
- **Options menu.** Estuary's side blade becomes the Bald library options column: at x 1440 from y 292, 440 wide, settings-style rows (Bald_ConfigureButton: accent dot, full ink focused, 45% otherwise, radio state as an accent dot), section headings in caption-meta type at 60% ink, the Home menu's show and hide motion, the view dimmed to 72%. Because the column is on the right, Left and Back return to the view (Right stays in the menu), and Filter's "move back to the list" action is Left. The footer switches to "Left / Back to browse · Select to change". Now-playing transport sits under the rows as 72 px round buttons with Estuary's icons tinted.
- **Add-on information.** The info dialog's language: fanart at the backdrop brightness under the info scrims; icon (168) and name in info-title type at the safe margin, version and author in info meta, the repository's deprecated / broken warning in the accent; screenshots as a rail of three 360 x 203 tiles; the summary and description as a focusable block (a 45% ink focus ring; Select opens the changelog when there is one); details (type, origin, size, binary, status) in the right column; Kodi's actions as pills at y 870; the disclaimer on the hint line.
- **File manager and event log.** Two 816-wide compact lists at the safe margins, each under its path, with their counts on the hint line. The event log uses 100 px rows (icon, title, date, two lines of description) and keeps its actions as a fixed options column at x 1440 (Right from the list).
- **Smart playlists.** The shared popup surface with settings-style rows, the rules list on a 10% ink field and the existing pill actions.

### 5.20 Media utility windows (2026-09-26, proposed; not yet seen in Kodi)

Decisions the spec did not cover, made while restyling the music, pictures, games, weather and profile windows (`Includes_Bald_Media.xml`). Please review.

- **Music information** follows the movie Overview's language on one page, not three: sharp fanart under the two info scrims, a 400 px square cover at the safe margin, a 76 px title (albums and songs have no clearlogo), a meta line ("Artist · 1997 · 48:12"), the genre as the accent line and the description as four 22 px lines. Kodi's actions (Play, Your rating, Artist information, Show fanart, Refresh, Choose art) are the info pills in one row at y 590. Below, songs or albums fill a two-column row list and artists reuse the cast circles; a details list (label over value, as `Bald_Detail`) sits in the preview column. The description is focusable and opens Kodi's text viewer, shown by a 10% `ink` row. No hints: the actions change with the item type.
- **Now playing (visualisation)**: the bottom info scrim, a 320 px cover, the caption type scale (title 40, artist as info meta, album as the accent line, "year · genre · n/10" as caption meta) and the info dialog's 4 px progress bar with times; "Next: title · artist" on the footer line. The block rises 180 px (MOVE, 440) while the music OSD's bottom bar is up. Background fanart dims to 30% behind a running visualisation (800 FADE) and only drifts 100→105% when Estuary's animate-fanart setting is on.
- **Picture information**: from the pictures window, the picture sits sharp on the field in the left 1136 px; over a running slideshow only the right column draws, on the horizontal info scrim flipped to the right. Filename and date head the preview column; Kodi's details list uses the label-over-value detail rows.
- **Login screen**: a page title (Kodi's own "User login" heading), the Estuary prompt as plot text, and profiles as 200 px round avatars on a centred fixed list. Unfocused avatars dim to the tile level; the focused one pops to 1.06 in an `ink` ring. Power options is a pill; the profile counter Kodi writes sits on the footer line, hints at the right.
- **Weather**: the page title with the location, the temperature at the clock size (132), condition as the tagline and feels-like as info meta, then five tinted stat figures. Forecast rows are captioned like Home rows; cards are 240 × 300 with a 10% `ink` tile and the 1.05 tile pop on focus. Low temperatures are 60% `ink` instead of Estuary's blue and red. Maps fill the safe area with a 3 px `ink` focus ring. Updating dims the page with `field` at 60% and breathes an accent dot.
- **Game dialogs and OSD** stay popups on the shared surface. Menu rows are the popup list rows with Estuary's OSD icons tinted to the row's ink; controller pictures are tinted with the accent. Disc manager items that need an open tray read at 34% `ink` while it is closed (Estuary: 38% white).
- **Small popups** (colour picker, media source, video versions): Estuary's inner panel frames are gone; lists use the popup list row, section captions are the row-label style at 60% `ink`, text fields are the keyboard's outline pill, counters and paths sit in the hint style at the panel's foot, and colour swatches are rounded tiles that pop to 1.12 inside an `ink` ring.
- **Icons**: Estuary's icon textures stay (Bald has no icon set), always tinted with an `ink` step and sized 40-48 px.

### 5.21 Restyle review follow-ups (2026-09-26, proposed; not yet seen in Kodi)

Small decisions made while fixing the merged restyles' review findings. Please review.

- **Music playlist editor footer.** Two item counters on the y 954 hint line in hint type at 60% `ink`, "n / total": the files list's at the left safe margin, the playlist's flush with the right one. They replace Estuary's badge counters; the window's single `BottomBar` count is left empty so the two do not overlap.
- **PVR timer icons in popup lists.** Estuary's recording icon is tinted `accent`, its reminder bell the row's `ink` step (70% unfocused, full on the focused row), in both the select dialog's detailed rows and the simple list.
- **Popup list focus row.** Every popup list's 10% `ink` focus row halves while its list is not focused; the PVR managers' row now does the same (it dimmed to 40%).
- **OSD help with a state.** Where Estuary's OSD help named a control and its state in one label ("Random · On", "Rewind · Fast forward"), the state is a separate hint part after the hint line's own 20 px dot. The PlayerControls caption under its row uses the same dot. The hints still name the focused control rather than "<key> for <action>", as Estuary's help did.
- **Rating circle setting dropped.** Appearance no longer offers Estuary's "Choose rating to display for media items": nothing drew the circle after the library views and music information became Bald. If a rating mark is wanted, it belongs in the Bald preview caption as a new design.

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
