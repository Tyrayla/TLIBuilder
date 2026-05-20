"""
Shared fixtures for the TLIBuilder test suite.
Run from the backend/ directory: py -m pytest tests/
"""
import os
import sys

# Ensure the backend package root is on sys.path so all imports resolve.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
