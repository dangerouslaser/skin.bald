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
    window = xbmcgui.Window(10025)
    token = uuid.uuid4().hex
    window.setProperty('Bald.LetterScan', token)
    window.clearProperty('Bald.AvailableLetters')
    count = int(xbmc.getInfoLabel('Container(510).NumAllItems') or 0)
    path = xbmc.getInfoLabel('Container.FolderPath')
    result = available_letters(count, lambda index: xbmc.getInfoLabel(
        f'Container(510).ListItemAbsolute({index}).SortLetter'))
    if (window.getProperty('Bald.LetterScan') == token
            and xbmc.getCondVisibility('Window.IsActive(videos) + Control.IsVisible(510) + Control.HasFocus(9160)')
            and xbmc.getInfoLabel('Container.FolderPath') == path
            and int(xbmc.getInfoLabel('Container(510).NumAllItems') or 0) == count):
        window.setProperty('Bald.AvailableLetters', result)
