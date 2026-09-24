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
