"""Read available sort-letter groups from the visible native library container (the video or music library).

RunScript(skin.bald,letters,<view id>) scans on every call. Bald Helper's service calls publish() with a `cache`
(get/put by key(), cleared when the video library changes) and a `cancelled` check (a newer request stops a scan)."""
import string
import uuid


def bucket(letter):
    letter = letter.upper()
    return letter if letter in string.ascii_uppercase and len(letter) == 1 else '0'


def available_letters(count, read, cancelled=None):
    """';A;B;' for the groups present, or None when `cancelled` stopped the scan."""
    found = set()
    for index in range(count):
        if cancelled is not None and index % 50 == 0 and cancelled():
            return None
        letter = read(index)
        if letter:
            found.add(bucket(letter))
        if len(found) == 27:
            break
    return ';' + ';'.join(sorted(found)) + ';'


# Library view containers live in 500-599 (see 1080i/IDs); anything else is a bad call site.
VIEW_IDS = range(500, 600)


def view_container(value):
    """Return the call site's container id as an int, or None when it is not a view id."""
    value = str(value or '').strip()
    if not value.isdecimal() or int(value) not in VIEW_IDS:
        return None
    return int(value)


# The library windows with Bald views, by name (for conditions) and id (for xbmcgui.Window): the letter bar reads
# Window(<name>).Property(Bald.AvailableLetters).
LIBRARY_WINDOWS = (('videos', 10025), ('music', 10502))


def library_window(xbmc):
    """(name, id) of the active library window, or None when neither is active."""
    for name, window_id in LIBRARY_WINDOWS:
        if xbmc.getCondVisibility(f'Window.IsActive({name})'):
            return name, window_id
    return None


def cache_key(xbmc, container, count, path):
    """What a scan's result depends on: the listing (folder, size) and how it is sorted."""
    return (container, path, count, xbmc.getInfoLabel('Container.SortMethod'),
            xbmc.getInfoLabel('Container.SortOrder'))


def publish(xbmc, xbmcgui, container='', cache=None, cancelled=None):
    # Each view passes its own id: RunScript(skin.bald,letters,<id>).
    container = view_container(container)
    if container is None or not xbmc.getCondVisibility(f'Control.IsVisible({container})'):
        return
    active = library_window(xbmc)
    if active is None:
        return
    name, window_id = active
    window = xbmcgui.Window(window_id)
    token = uuid.uuid4().hex
    window.setProperty('Bald.LetterScan', token)
    window.clearProperty('Bald.AvailableLetters')
    count_label = f'Container({container}).NumAllItems'
    count = int(xbmc.getInfoLabel(count_label) or 0)
    path = xbmc.getInfoLabel('Container.FolderPath')
    key = cache_key(xbmc, container, count, path) if cache is not None else None
    result = cache.get(key) if cache is not None else None
    if result is None:
        result = available_letters(count, lambda index: xbmc.getInfoLabel(
            f'Container({container}).ListItemAbsolute({index}).SortLetter'), cancelled)
        if result is None:
            return
        if (cache is not None and xbmc.getInfoLabel('Container.FolderPath') == path
                and int(xbmc.getInfoLabel(count_label) or 0) == count):
            cache.put(key, result)
    if (window.getProperty('Bald.LetterScan') == token
            and xbmc.getCondVisibility(f'Window.IsActive({name}) + Control.IsVisible({container}) + Control.HasFocus(9160)')
            and xbmc.getInfoLabel('Container.FolderPath') == path
            and int(xbmc.getInfoLabel(count_label) or 0) == count):
        window.setProperty('Bald.AvailableLetters', result)
