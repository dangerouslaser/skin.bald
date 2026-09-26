# Detail pages — design proposal

Review prototype only. No live Kodi XML, settings or library records are changed.
The self-contained fragment embeds downscaled, cached library artwork; no server
addresses or credentials are included. Sample recommendations demonstrate layout
and selection, not Kodi's live recommendation ordering. Play/Trailer only change
focus in this prototype and never start playback.

## Proposed flow

1. Overview: retain the sharp full-screen hero and playback actions, with a Down
   hint instead of a clipped cast row.
2. Cast & details: showcase the originating movie's poster at x96, y156,
   432 × 648 in the default 1920 × 1080 composition. Place its title, cast row
   and six detail fields to the right. User-requested change: crossfade from
   sharp hero art to Home's blurred treatment (radius 40 at 480 px, brightness
   approximately 30%) over 460 ms. The browser approximates that blur at display
   size; Kodi implementation must use the existing cached TMDb Helper output.
3. More like this: Home-style framed art, right-hand summary, recommendation
   strip below. Highlight changes the preview only; activation replaces the
   originating movie and returns to Overview.

Up/Down changes pages. Left/Right changes cast/recommendation focus. Native
buttons provide mouse and keyboard access. Click another recommendation to
preview it; click the selected recommendation (or press Enter on it) to open.
Design controls offer poster prominence and four/five visible cast members.

## Motion finding

`DialogVideoInfo.xml` currently puts two independently reversible conditional
slides on the same content group: 0 → -560 for section 1 and 0 → -1000 for
section 2, both 560 ms cubic-out. The simultaneous reversal/start is a likely
source of the reported bounce, not a confirmed frame-by-frame diagnosis. The
proposal avoids compounded offsets by transitioning fixed pages one at a time.

## Verification

- JavaScript syntax checked; fragment below 1 MB.
- Inspected Cast & details and recommendation layouts in Safari.
- Switching the highlighted recommendation updated its title, artwork, year,
  runtime, genres and synopsis. Up returned to the original movie's cast page.
- Main subject, cast selection, recommendation selection and design choices are
  locally held; no Kodi calls occur from the prototype.
- Secondary sample titles use initials where cast photos were not embedded;
  unavailable technical metadata is explicitly labelled rather than invented.

Pending design approval before updating `docs/SPEC.md` or implementing in Kodi.
