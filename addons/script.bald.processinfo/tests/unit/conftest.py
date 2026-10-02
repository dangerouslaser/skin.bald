# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fork (Bald Process Info): upstream's unit tests describe an Amlogic box.

The fork keeps VS10 to Amlogic (core.platform.is_amlogic), and the test runner
is not one, so these tests run as on Amlogic.  The fork's own LibreELEC tests
(tests/test_libreelec.py) set the platform themselves.
"""

import pytest

from core import platform


@pytest.fixture(autouse=True)
def on_amlogic(monkeypatch):
    monkeypatch.setattr(platform, "_amlogic", True)
