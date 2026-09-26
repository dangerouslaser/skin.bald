"""Remove Bald's retired TV Guide Left override from existing installs."""
import os


def remove(xbmc, xbmcvfs):
    keymap_dir = xbmcvfs.translatePath("special://profile/keymaps")
    destination = os.path.join(keymap_dir, "bald-pvr.xml")
    try:
        os.remove(destination)
    except FileNotFoundError:
        return False
    xbmc.executebuiltin("Action(reloadkeymaps)")
    return True


if __name__ == "__main__":
    try:
        import xbmc
        import xbmcvfs

        remove(xbmc, xbmcvfs)
    except Exception as error:
        import xbmc

        xbmc.log("Bald PVR keymap: {}".format(error), xbmc.LOGERROR)
