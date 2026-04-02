"""
Stub out streamlit and plotly for pure-computation tests.

The system-level installs of streamlit and plotly have empty __init__.py
files, so their attributes (cache_resource, cache_data, go.Figure, etc.)
are missing.  We inject minimal stubs before any test module is collected
so that importing the dashboard scripts works without a real runtime.
"""

import sys
from unittest.mock import MagicMock

# --- streamlit stub: cache decorators act as identity functions ---
_st_stub = MagicMock()
_st_stub.cache_resource = lambda fn=None, **_kw: (fn if fn is not None else lambda f: f)
_st_stub.cache_data = lambda fn=None, **_kw: (fn if fn is not None else lambda f: f)
sys.modules["streamlit"] = _st_stub

# --- plotly stub: graph_objects needs Figure/Scatter for type annotations ---
_go_stub = MagicMock()
sys.modules["plotly"] = MagicMock()
sys.modules["plotly.graph_objects"] = _go_stub
