#!/usr/bin/env python3
"""Build the static Kodi repository feed from a clean, tagged skin checkout.

Everything published comes from --revision (the skin, the bundled add-ons, the repository add-on and every icon,
fanart and screenshot), never from the working tree. --output is deleted and rebuilt, and the landing page and the
repository zip go into its parent, so it must be a new or empty directory, or one this script built before, and
neither it nor its parent may be the checkout, the home folder or a folder that holds either."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from fnmatch import fnmatch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_SOURCE = "packaging/repository.bald"  # the repository add-on, in the checkout
BUNDLED_ADDONS = ("addons/script.bald.xcsetup", "addons/script.bald.helper")
# Skin Variables writes the Home rows per install; releases ship 1080i/Includes_Bald_HomeDefaults.xml instead.
PER_INSTALL_FILES = ("1080i/script-skinvariables-generator-includes",)


def addon_identity(root: ET.Element) -> tuple[str, str]:
    return root.attrib["id"], root.attrib["version"]


def tracked_files(revision: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True
    )
    files = {"addon.xml", "LICENSE.txt", "LICENSE-Estuary.txt"}
    directories = (
        "1080i/",
        "colors/",
        "extras/",
        "fonts/",
        "language/",
        "media/",
        "playlists/",
        "resources/",
        "scripts/",
        "shortcuts/",
    )
    return [
        line
        for line in output.splitlines()
        if (line in files or line.startswith(directories)) and not line.startswith(PER_INSTALL_FILES)
    ]


def git_file(revision: str, relative_path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{revision}:{relative_path}"], cwd=ROOT)


def git_tree_files(revision: str, directory: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", directory],
        cwd=ROOT,
        text=True,
    )
    return output.splitlines()


def zip_skin(output: Path, revision: str, version: str) -> Path:
    destination = output / "skin.bald" / f"skin.bald-{version}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in tracked_files(revision):
            archive.writestr(f"skin.bald/{relative_path}", git_file(revision, relative_path))
    return destination


def zip_repository(output: Path, revision: str, version: str) -> Path:
    destination = output / "repository.bald" / f"repository.bald-{version}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in ("addon.xml", "icon.png", "fanart.jpg"):
            archive.writestr(f"repository.bald/{name}", git_file(revision, f"{REPOSITORY_SOURCE}/{name}"))
    return destination


def zip_bundled_addon(output: Path, revision: str, source: str) -> ET.Element:
    addon_xml_path = f"{source}/addon.xml"
    addon_xml = git_file(revision, addon_xml_path)
    root = ET.fromstring(addon_xml)
    addon_id = root.attrib["id"]
    version = root.attrib["version"]
    destination = output / addon_id / f"{addon_id}-{version}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{source}/"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in git_tree_files(revision, source):
            archive_path = f"{addon_id}/{relative_path.removeprefix(prefix)}"
            archive.writestr(archive_path, git_file(revision, relative_path))
    # Declared assets (icon, fanart, screenshots) beside the zip too, where Kodi's add-on browser reads them.
    assets = root.find("./extension[@point='xbmc.addon.metadata']/assets")
    for asset in [] if assets is None else assets:
        if asset.text:
            target = output / addon_id / asset.text.strip()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git_file(revision, f"{source}/{asset.text.strip()}"))
    return root


def copy_metadata(output: Path, revision: str, addon_id: str, source: str, asset_dir: str = "") -> None:
    """Icon, fanart and any screenshot-NN.jpg of `source` at the revision next to the add-on's zip, where Kodi's
    add-on browser reads them."""
    target = output / addon_id / asset_dir
    target.mkdir(parents=True, exist_ok=True)
    names = [path.removeprefix(f"{source}/") for path in git_tree_files(revision, source)]
    screenshots = sorted(name for name in names if "/" not in name and fnmatch(name, "screenshot-*.jpg"))
    for name in ("icon.png", "fanart.jpg", *screenshots):
        (target / name).write_bytes(git_file(revision, f"{source}/{name}"))


def check_output(output: Path) -> None:
    """Refuse an output directory whose deletion, or whose parent's new index.html and zip, could harm anything:
    the checkout, the home folder, a folder holding either, or a directory this script did not build."""
    output = output.resolve()
    home = Path.home().resolve()
    for guarded in (ROOT, home):
        if guarded.is_relative_to(output) or output.parent == guarded:
            raise SystemExit(f"refusing unsafe output directory: {output}")
    if output.exists():
        if not output.is_dir():
            raise SystemExit(f"refusing output that is not a directory: {output}")
        if any(output.iterdir()) and not (output / "addons.xml.md5").is_file():
            raise SystemExit(f"refusing to delete {output}: not empty, and not a feed this script built")


# Captions for the skin's screenshots (resources/screenshot-NN.jpg, in order) on the landing page.
SCREENSHOT_CAPTIONS = (
    "Home: artwork first, with ratings, media flags and rows you arrange",
    "Hubs you add, rename and reorder, each with its own rows",
    "Movie information",
    "Cast and details",
    "More like this",
    "Library views with a live preview",
    "Live TV rows and channel groups",
    "TV guide",
    "Series page: seasons as tabs, episodes in a row",
)
# The movie library's views (the screenshots after SCREENSHOT_CAPTIONS's), a section of their own.
LIBRARY_CAPTIONS = (
    "Posters with a preview",
    "Poster wall with a preview",
    "Full-width poster wall",
    "Poster-low rail under the artwork",
    "Compact list",
    "Artwork list",
)


def landing_page(repository_zip: str, repository_version: str, skin_version: str) -> str:
    """The site's index.html. Links use double quotes and the files are listed plainly, so Kodi can also browse the
    site as a file source (its HTTP directory parser only reads href="...")."""
    shots = "".join(
        f'<figure><a class="shot" href="kodi/skin.bald/resources/screenshot-{i:02d}.jpg">'
        f'<img src="kodi/skin.bald/resources/screenshot-{i:02d}.jpg" alt="{caption}" loading="lazy" '
        f'width="1920" height="1080"></a><figcaption>{caption}</figcaption></figure>'
        for i, caption in enumerate(SCREENSHOT_CAPTIONS[1:], start=2)
    )
    views = "".join(
        f'<figure><a class="shot" href="kodi/skin.bald/resources/screenshot-{i:02d}.jpg">'
        f'<img src="kodi/skin.bald/resources/screenshot-{i:02d}.jpg" alt="{caption}" loading="lazy" '
        f'width="1920" height="1080"></a><figcaption>{caption}</figcaption></figure>'
        for i, caption in enumerate(LIBRARY_CAPTIONS, start=len(SCREENSHOT_CAPTIONS) + 1)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bald for Kodi 22</title>
<meta name="description" content="Bald: a minimal, artwork-first skin for Kodi 22.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet">
<style>
:root {{ --field: #0b0c10; --ink: #eceef2; --ink60: rgba(236,238,242,.6); --ink34: rgba(236,238,242,.34);
  --ink10: rgba(236,238,242,.1); --accent: #ffffff; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--field); color: var(--ink); font: 400 17px/1.55 "DM Sans", system-ui, sans-serif; }}
main {{ max-width: 1200px; margin: 0 auto; padding: 72px 24px 96px; }}
header {{ display: grid; gap: 40px; grid-template-columns: minmax(0, 1fr) 360px; align-items: end; }}
h1 {{ margin: 0; font-weight: 600; font-size: clamp(56px, 9vw, 104px); line-height: .95; letter-spacing: -.02em; }}
/* The full stop drops in from above the page and bounces to rest: falls ease-in, rises ease-out, each bounce lower. */
h1 .dot {{ display: inline-block; animation: bald-drop 1.6s .25s both; }}
@keyframes bald-drop {{
  0%   {{ transform: translateY(-120vh); animation-timing-function: cubic-bezier(.55, 0, 1, .45); }}
  46%  {{ transform: translateY(0);      animation-timing-function: cubic-bezier(0, .55, .45, 1); }}
  62%  {{ transform: translateY(-.28em); animation-timing-function: cubic-bezier(.55, 0, 1, .45); }}
  76%  {{ transform: translateY(0);      animation-timing-function: cubic-bezier(0, .55, .45, 1); }}
  85%  {{ transform: translateY(-.1em);  animation-timing-function: cubic-bezier(.55, 0, 1, .45); }}
  92%  {{ transform: translateY(0);      animation-timing-function: cubic-bezier(0, .55, .45, 1); }}
  96%  {{ transform: translateY(-.03em); animation-timing-function: cubic-bezier(.55, 0, 1, .45); }}
  100% {{ transform: translateY(0); }}
}}
@media (prefers-reduced-motion: reduce) {{ h1 .dot {{ animation: none; }} }}
.lede {{ margin: 18px 0 0; color: var(--ink60); font-size: 20px; max-width: 34ch; }}
.install {{ border-left: 1px solid var(--ink10); padding-left: 28px; }}
.install h2 {{ margin: 0 0 12px; font-size: 13px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: var(--accent); }}
.install ol {{ margin: 0 0 20px; padding-left: 20px; color: var(--ink60); font-size: 15px; }}
.install li {{ margin: 6px 0; }}
.install strong {{ color: var(--ink); font-weight: 500; }}
.button {{ display: inline-block; padding: 12px 20px; border-radius: 999px; background: var(--ink); color: var(--field);
  font-weight: 600; text-decoration: none; }}
.button:hover {{ background: var(--accent); }}
.version {{ display: block; margin-top: 10px; color: var(--ink34); font-size: 13px; }}
.hero {{ margin: 56px 0 0; }}
img {{ display: block; width: 100%; height: auto; border-radius: 6px; background: var(--ink10); }}
.hero img {{ box-shadow: 0 30px 80px rgba(0,0,0,.5); }}
.gallery {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 40px 28px; margin-top: 64px; }}
figure {{ margin: 0; }}
figcaption {{ margin-top: 12px; color: var(--ink60); font-size: 15px; }}
figcaption::before {{ content: ""; display: inline-block; width: 7px; height: 7px; margin: 0 10px 2px 0;
  border-radius: 50%; background: var(--accent); }}
.views h2 {{ margin: 96px 0 8px; font-size: 13px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: var(--accent); }}
.views p {{ margin: 0; color: var(--ink60); }}
.views .gallery {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 32px 24px; margin-top: 32px; }}
.shot {{ display: block; border-radius: 6px; cursor: zoom-in; }}
.shot img {{ transition: transform .32s cubic-bezier(.22,1,.36,1), opacity .2s; }}
.shot:hover img, .shot:focus-visible img {{ transform: scale(1.012); }}
.shot:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 4px; }}
dialog {{ width: 100vw; height: 100vh; max-width: none; max-height: none; margin: 0; padding: 0; border: 0;
  background: transparent; color: var(--ink); }}
dialog::backdrop {{ background: rgba(6,7,10,.94); }}
dialog[open] {{ display: grid; place-items: center; animation: fade .24s ease-out; }}
@keyframes fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
.lightbox {{ margin: 0; width: min(calc(100vw - 176px), calc((100vh - 120px) * 16 / 9)); }}
.lightbox img {{ border-radius: 8px; box-shadow: 0 30px 90px rgba(0,0,0,.6); }}
.lightbox figcaption {{ display: flex; justify-content: space-between; gap: 16px; }}
.lightbox figcaption::before {{ display: none; }}
dialog:focus {{ outline: none; }}
.count {{ color: var(--ink34); font-variant-numeric: tabular-nums; }}
.nav, .close {{ position: fixed; border: 0; background: rgba(236,238,242,.08); color: var(--ink); cursor: pointer;
  width: 48px; height: 48px; border-radius: 50%; font: 400 22px/48px "DM Sans", system-ui, sans-serif; }}
.nav:hover, .close:hover {{ background: rgba(236,238,242,.18); }}
.nav {{ top: 50%; margin-top: -24px; }}
.prev {{ left: 24px; }} .next {{ right: 24px; }} .close {{ top: 20px; right: 24px; }}
@media (max-width: 820px) {{ .nav {{ top: auto; bottom: 20px; margin: 0; }} .lightbox {{ width: 94vw; }} }}
.files {{ margin-top: 80px; padding-top: 24px; border-top: 1px solid var(--ink10); color: var(--ink34); font-size: 13px; }}
.files a {{ color: var(--ink60); }}
@media (max-width: 820px) {{ header {{ grid-template-columns: 1fr; }} .install {{ border-left: 0; padding-left: 0; }}
  .gallery, .views .gallery {{ grid-template-columns: 1fr; }} main {{ padding: 48px 16px 64px; }} }}
</style>
</head>
<body>
<main>
<header>
<div>
<h1>Bald<span class="dot">.</span></h1>
<p class="lede">A minimal, artwork-first skin for Kodi 22, with fluid motion and nothing in the way of your library.</p>
</div>
<div class="install">
<h2>Install</h2>
<ol>
<li>Download the repository and choose <strong>Add-ons › Install from zip file</strong> in Kodi.</li>
<li>Then <strong>Install from repository › Bald Add-on Repository › Look and feel › Skin › Bald</strong>.</li>
</ol>
<a class="button" href="{repository_zip}">Download repository</a>
<span class="version">Bald {skin_version} · repository {repository_version} · Kodi 22 only</span>
</div>
</header>
<figure class="hero"><a class="shot" href="kodi/skin.bald/resources/screenshot-01.jpg"><img src="kodi/skin.bald/resources/screenshot-01.jpg" alt="{SCREENSHOT_CAPTIONS[0]}" width="1920" height="1080"></a><figcaption>{SCREENSHOT_CAPTIONS[0]}</figcaption></figure>
<section class="gallery">{shots}</section>
<section class="views"><h2>Library views</h2><p>Six ways to browse a library, switched from the options menu.</p>
<div class="gallery">{views}</div></section>
<p class="files"><a href="https://github.com/dangerouslaser/skin.bald">Source on GitHub</a> · <a href="https://forum.kodi.tv/showthread.php?tid=388804">Kodi forum thread</a> · Files: <a href="{repository_zip}">{repository_zip}</a> · <a href="kodi/">kodi/</a></p>
</main>
<dialog id="viewer" aria-label="Screenshot" tabindex="-1">
<figure class="lightbox"><img id="viewer-img" alt=""><figcaption><span id="viewer-caption"></span><span class="count" id="viewer-count"></span></figcaption></figure>
<button class="nav prev" type="button" aria-label="Previous screenshot">&#8249;</button>
<button class="nav next" type="button" aria-label="Next screenshot">&#8250;</button>
<button class="close" type="button" aria-label="Close">&#215;</button>
</dialog>
<script>
(() => {{
  const shots = [...document.querySelectorAll("a.shot")];
  const viewer = document.getElementById("viewer");
  const img = document.getElementById("viewer-img");
  const caption = document.getElementById("viewer-caption");
  const count = document.getElementById("viewer-count");
  if (!viewer.showModal) return;  // No <dialog> support: the links open the image itself.
  let index = 0;
  const show = (i) => {{
    index = (i + shots.length) % shots.length;
    const shot = shots[index];
    const alt = shot.querySelector("img").alt;
    img.src = shot.href; img.alt = alt;
    caption.textContent = alt;
    count.textContent = `${{index + 1}} / ${{shots.length}}`;
    new Image().src = shots[(index + 1) % shots.length].href;  // Preload the next one.
  }};
  shots.forEach((shot, i) => shot.addEventListener("click", (event) => {{
    event.preventDefault(); show(i); viewer.showModal(); viewer.focus();
  }}));
  viewer.querySelector(".prev").addEventListener("click", () => show(index - 1));
  viewer.querySelector(".next").addEventListener("click", () => show(index + 1));
  viewer.querySelector(".close").addEventListener("click", () => viewer.close());
  viewer.addEventListener("click", (event) => {{ if (event.target === viewer) viewer.close(); }});
  viewer.addEventListener("keydown", (event) => {{
    if (event.key === "ArrowLeft") show(index - 1);
    if (event.key === "ArrowRight") show(index + 1);
  }});
}})();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--expected-version")
    args = parser.parse_args()

    skin_root = ET.fromstring(git_file(args.revision, "addon.xml"))
    repository_root = ET.fromstring(git_file(args.revision, f"{REPOSITORY_SOURCE}/addon.xml"))
    skin_id, skin_version = addon_identity(skin_root)
    repository_id, repository_version = addon_identity(repository_root)
    if skin_id != "skin.bald":
        raise SystemExit(f"unexpected skin id: {skin_id}")
    if args.expected_version and skin_version != args.expected_version:
        raise SystemExit(
            f"tag version {args.expected_version} does not match addon.xml {skin_version}"
        )

    output = args.output.resolve()
    check_output(output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    zip_skin(output, args.revision, skin_version)
    repository_zip = zip_repository(output, args.revision, repository_version)
    copy_metadata(output, args.revision, skin_id, "resources", "resources")
    copy_metadata(output, args.revision, repository_id, REPOSITORY_SOURCE)

    addons = ET.Element("addons")
    addons.append(skin_root)
    for source in BUNDLED_ADDONS:
        addons.append(zip_bundled_addon(output, args.revision, source))
    addons.append(repository_root)
    ET.indent(addons, space="  ")
    index = ET.tostring(addons, encoding="utf-8", xml_declaration=True)
    (output / "addons.xml").write_bytes(index + b"\n")
    (output / "addons.xml.md5").write_text(hashlib.md5(index + b"\n").hexdigest())
    shutil.copy2(repository_zip, output.parent / repository_zip.name)
    (output.parent / "index.html").write_text(
        landing_page(repository_zip.name, repository_version, skin_version), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
