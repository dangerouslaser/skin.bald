# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 U3knOwn

"""Fixtures shared by the unit tests.

Fork (Bald Process Info): upstream's unit tests describe an Amlogic box.
The fork keeps VS10 to Amlogic (core.platform.is_amlogic) and lets the overlay
open wherever DRM is (core.platform.has_drm); the test runner may be neither,
so these tests run as on Amlogic without DRM.  The fork's own LibreELEC tests
(tests/test_libreelec.py) set the platform themselves.
"""

import pytest

from core import platform
from dashboard_server import serve


@pytest.fixture(autouse=True)
def on_amlogic(monkeypatch):
    monkeypatch.setattr(platform, "_amlogic", True)
    monkeypatch.setattr(platform, "has_drm", lambda: False)


@pytest.fixture
def dashboard():
    """A running dashboard server with nothing playing."""
    srv, close = serve()
    yield srv
    close()
