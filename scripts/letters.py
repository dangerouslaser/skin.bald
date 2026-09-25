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


def publish(xbmc, xbmcgui):
    container = next((c for c in (513, 512, 511, 510)
                      if xbmc.getCondVisibility(f'Control.IsVisible({c})')), None)
    if container is None:
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
