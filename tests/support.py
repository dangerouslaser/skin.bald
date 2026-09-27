"""Loaders the tests share: modules by file path, Bald Helper's modules as a package, the Home defaults builder and
the Kodi stand-ins more than one test file uses."""

import importlib
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "script.bald.helper"
LIB = ADDON / "resources" / "lib"


def load_file(name, path):
    """A fresh module from a file path, registered nowhere."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helper(name, tag="test"):
    """Bald Helper's resources/lib/<name>.py, imported as a module of a package named after `tag`, so its relative
    imports work; each tag is its own copy of the modules (one per test file keeps the files independent)."""
    package = f"bald_helper_{tag}"
    if package not in sys.modules:
        spec = importlib.util.spec_from_file_location(package, LIB / "__init__.py",
                                                      submodule_search_locations=[str(LIB)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{package}.{name}")


def load_builder():
    """A fresh tools/build_home_defaults.py."""
    return load_file("build_home_defaults", ROOT / "tools" / "build_home_defaults.py")


@contextmanager
def service(fakes):
    """Bald Helper's service.py loaded as Kodi runs it (the add-on folder on sys.path, `resources.lib` imported
    fresh), with `fakes` as the xbmc modules; sys.modules and sys.path are put back afterwards."""
    saved = {name: module for name, module in sys.modules.items()
             if name in fakes or name == "resources" or name.startswith("resources.")}
    for name in saved:
        sys.modules.pop(name)
    sys.modules.update(fakes)
    sys.path.insert(0, str(ADDON))
    try:
        yield load_file("bald_helper_service", ADDON / "service.py")
    finally:
        sys.path.remove(str(ADDON))
        for name in [name for name in sys.modules
                     if name in fakes or name == "resources" or name.startswith("resources.")]:
            sys.modules.pop(name)
        sys.modules.update(saved)


class FakeWindow:
    """A Kodi window's properties."""

    def __init__(self):
        self.properties = {}

    def getProperty(self, key):
        return self.properties.get(key, "")

    def setProperty(self, key, value):
        self.properties[key] = value

    def clearProperty(self, key):
        self.properties.pop(key, None)


class Clock:
    """A clock the test moves."""

    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
