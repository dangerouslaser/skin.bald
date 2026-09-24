# Build notes

Things from docs/SPEC.md that did not map directly onto Kodi 22, with what was tried and what was done instead.

## Milestone 1

- **Clock weight 300.** Instrument Sans ships static TTFs from 400 (Regular) to 700 (Bold); there is no Light. `Bald_Clock` uses Regular for now. Options later: generate a 300 instance from the variable font with fontTools (`varLib.instancer`; the wght axis starts at 400, so this needs a different face or accepting 400).
- **Letter spacing.** Kodi's Font.xml has no tracking or letter-spacing property, so the spec's -0.045em, -0.02em, -0.03em and +0.04em values are not applied.
- **Line height.** `<linespacing>` multiplies the font's own line height, not the point size. Caption plot (1.5) and info plot (1.55) are first guesses at 30 px and 34 px lines; measure and tune in milestone 2.
- **Variable fonts.** Kodi's FreeType path renders only the default instance of a variable TTF, so the repo ships the static Regular, Medium, SemiBold and Bold files from github.com/Instrument/instrument-sans.
- **Estuary font names.** The Default fontset keeps every Estuary font name and size so the copied utility windows render; `<style>bold</style>` entries now use the SemiBold file, and the synthetic `lighten` and `bold` styles are dropped. The Arial fontset (for non-Latin languages) is unchanged apart from the added Bald_* names.
- **Switching skins remotely.** Setting `lookandfeel.skin` over JSON-RPC loads the skin, but Kodi's "keep this skin?" confirmation closes immediately and reverts. Workaround: quit Kodi, set `lookandfeel.skin` to `skin.bald` in `userdata/guisettings.xml`, and relaunch. `kodi-send` is not installed on this Mac; the event server is enabled if it is added later.
- **Resolution folder.** One `<res>` entry, 1920 x 1080, folder `1080i`, as the spec says. Estuary's extra aspect-ratio entries were dropped.

## Milestone 2

- **Plot ellipsis.** Kodi cannot end a multi-line block with "...". `CGUITextLayout::WrapText` draws `ceil(height / line height)` lines and stops; a `textbox` clips. Only single-line labels truncate with an ellipsis (by width). The caption plot is a `wrapmultiline` label 116 px tall with 30 px lines, so it stops cleanly at 4 lines. A real ellipsis would need a service to pre-trim the text into a window property; revisit alongside the palette service (section 7).
- **Line spacing measured.** Instrument Sans' natural line is about 1.2 x size. Caption plot uses 1.25 (20 px -> 30 px lines), info plot 1.29 (22 px -> 34 px).
- **Fixedlist focus.** Kodi's `movement` lets the cursor travel *below* `focusposition`, not above it. `focusposition 2, movement 2` gives the prototype's behavior: focus travels right to slot 2, then the row scrolls, and it stays at slot 2 going back left. But `SelectItem` always places the selection at `focusposition`, so a freshly loaded row starts on its third item, and `SetFocus(id,0,absolute)` in `onload` does not help (content loads asynchronously and selecting item 0 still lands on slot 2). Fix in milestone 3 with the row motion work, likely a one-shot skin timer that moves each row back two items once its content has loaded.
- **Row sources.** Kodi library only. Continue watching is two skin playlists (`inprogress_movies.xsp`, `inprogress_episodes.xsp`) as two `<content>` elements in one list; Kodi concatenates them, so movies come first rather than interleaving by last played. Next up is `videodb://inprogresstvshows/` (shows, not the next episode). Rows become user-configurable widgets in 0.2.
- **Clearlogo drop shadow.** Not implemented; Kodi images have no blur or shadow. Options later: a pre-blurred shadow texture behind the logo, or leave it (logo scrim already provides contrast).
- **Genres.** `ListItem.Genre` joins with " / " (Kodi's separator), not the prototype's ", ".
- **Dev window.** The macOS Kodi window must be 16:9 or the GUI is stretched. Set to 1600 x 900 content (1600 x 928 with title bar) via System Events.
- **Callout gap.** The hairline ends at x 1416, leaving 24 px before the caption at 1440 (prototype ran it to 1440; it read as touching the text). Changed at the user's request.
