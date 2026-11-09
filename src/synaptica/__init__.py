"""SYNAPTICA: a bilingual (ES/EN) neuroscience website that updates itself every day.

Adapted from paleo-atlas ``src/paleo/__init__.py``.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("synaptica")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"
