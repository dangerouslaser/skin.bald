"""Read available sort-letter groups from the visible native movie container."""
import string
import uuid


def bucket(letter):
    letter = letter.upper()
    return letter if letter in string.ascii_uppercase and len(letter) == 1 else '0'


def available_letters(count, read):
    found = set()
    for index in range(count):
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


def publish(xbmc, xbmcgui, container=''):
    # Each view passes its own id: RunScript(skin.bald,letters,<id>).
    container = view_container(container)
    if container is None or not xbmc.getCondVisibility(f'Control.IsVisible({container})'):
        return
    window = xbmcgui.Window(10025)
    token = uuid.uuid4().hex
    window.setProperty('Bald.LetterScan', token)
    window.clearProperty('Bald.AvailableLetters')
    count_label = f'Container({container}).NumAllItems'
    count = int(xbmc.getInfoLabel(count_label) or 0)
    path = xbmc.getInfoLabel('Container.FolderPath')
    result = available_letters(count, lambda index: xbmc.getInfoLabel(
        f'Container({container}).ListItemAbsolute({index}).SortLetter'))
    if (window.getProperty('Bald.LetterScan') == token
            and xbmc.getCondVisibility(f'Window.IsActive(videos) + Control.IsVisible({container}) + Control.HasFocus(9160)')
            and xbmc.getInfoLabel('Container.FolderPath') == path
            and int(xbmc.getInfoLabel(count_label) or 0) == count):
        window.setProperty('Bald.AvailableLetters', result)
