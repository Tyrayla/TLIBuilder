"""Bundle the backend Python the in-browser Pyodide worker imports (engine + orchestration).

This is APP code (versioned with the frontend), so the web build ships it as a static asset (`backend-py.zip`)
that the worker fetches from its own origin and unpacks into the Pyodide FS. Excludes tests, __pycache__, and
build artifacts.

tools/ ships an allowlist only (_WEB_TOOLS_KEEP): the importers/exporters/manual scripts are reachable solely
through /dev import endpoints the web client can never call (DevTools is desktop-gated on window.api), and some
carry the maintainer's absolute local paths — excluding them keeps those out of the public bundle. A dev import
endpoint invoked in-browser would raise ModuleNotFoundError, which is acceptable: it was already unreachable.

Output: <out>/backend-py.zip   (default <repo>/src/renderer/public/backend-py.zip so Vite serves it)
Usage:  python backend/tools/export_backend_bundle.py [--out DIR]
"""
import argparse
import os
import sys
import zipfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_BACKEND)
_SKIP_DIRS = {"__pycache__", "tests", "backend-build", ".pytest_cache"}

# tools/ modules the LIVE web paths import (lazily) — everything else in tools/ is dev/manual-only.
#   node_type_filter_builder — load_filter (server.py, engine compute/aggregator paths)
#   prism_catalog            — categorize_prism_catalog (/api/ethereal-prism)
#   destiny_catalog          — categorize_destiny (/api/destiny)
_WEB_TOOLS_KEEP = {"__init__.py", "node_type_filter_builder.py", "prism_catalog.py", "destiny_catalog.py"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(_REPO, "src", "renderer", "public"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    zpath = os.path.join(args.out, "backend-py.zip")

    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, files in os.walk(_BACKEND):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in files:
                if not f.endswith(".py"):
                    continue
                if os.path.relpath(root, _BACKEND) == "tools" and f not in _WEB_TOOLS_KEEP:
                    continue
                p = os.path.join(root, f)
                arc = os.path.relpath(p, _BACKEND).replace(os.sep, "/")  # importable layout (engine/..., server.py)
                z.write(p, arc); n += 1

    size = os.path.getsize(zpath)
    print(f"backend-py.zip  {n} files  {size / 1024:.0f} KB  -> {zpath}")


if __name__ == "__main__":
    main()
