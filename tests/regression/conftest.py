"""Configuration for regression and smoke test suites."""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "regression: PRR acceptance criteria regression tests")
    config.addinivalue_line("markers", "smoke: post-deploy smoke tests")
