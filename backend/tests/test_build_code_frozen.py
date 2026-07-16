"""The tli1 build-code codec is FROZEN. This test is the backstop.

`build_code.py` defines the wire format for shareable build codes: the `tli1_`
prefix, the zlib+base64url pipeline, and the `SCHEMA_VERSION` migration
semantics. Changing any of that silently breaks every build code already shared
in the wild. The rule (see CLAUDE.md) is that the wire format does not change.

Other layers discourage editing the file — settings.json deny rules, the
path-guard hook — but each has a gap: deny rules don't reach a Bash subprocess,
and the hook fails open and scans Bash with a regex. This test has no gap. It
pins the SHA-256 of the file's bytes, so a modification made by ANY route —
Edit, Write, a redirect, a helper script, or a bug in the guard itself — trips
it. It is the one check that cannot be evaded.

The codec exists in TWO repos: the full encode/decode here, and a validation-only
port in the separate `tlibuilder-code-share` service. Both are frozen. The share
copy lives outside this repo, so it is verified only when that repo is checked
out alongside this one (the owner's machine); it is skipped, not failed, in a
backend-only checkout.

── If you INTEND to change the codec ────────────────────────────────────────────
"Frozen" means the wire format, not that the file is untouchable forever. A
narrowly-scoped validation or hardening patch is allowed WITH OWNER SIGN-OFF.
The unlock ritual is deliberate, so the change shows up as a change:

  1. Make the edit.
  2. Run this test; it fails and prints the new hash.
  3. Paste the new hash into EXPECTED below, in the same commit.

If you are updating this hash without having meant to touch the codec, stop —
something modified `build_code.py` that shouldn't have.
"""
import hashlib
import os

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.dirname(_HERE)
_UMBRELLA = os.path.dirname(os.path.dirname(_BACKEND))  # .../TLI/

# path (relative to this file) -> expected SHA-256 of its bytes
EXPECTED = {
    os.path.join(_BACKEND, "build_code.py"):
        "2d8b33c93c3b7a0a4bfde81975858eb744d8dc65161181c1e1924ae973c5aa0f",
    os.path.join(_UMBRELLA, "tlibuilder-code-share", "build_code.py"):
        "3414670932ad486afb77c0d15a28fbfb2e58c579fa5745795f54a771129782d4",
}


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest.mark.parametrize("path, expected", sorted(EXPECTED.items()))
def test_codec_is_frozen(path, expected):
    if not os.path.exists(path):
        pytest.skip(f"{path} not present (sibling repo not checked out)")
    actual = _sha256(path)
    assert actual == expected, (
        f"\n\nFROZEN CODEC CHANGED: {path}\n"
        f"  expected SHA-256: {expected}\n"
        f"  actual   SHA-256: {actual}\n\n"
        f"The tli1 wire format is frozen. If you did NOT mean to change this file, "
        f"revert it. If you DID (owner sign-off, a narrow validation patch), paste "
        f"the actual hash above into EXPECTED in this test, in the same commit.\n"
    )


def test_desktop_codec_is_always_checked():
    """The in-repo copy must never be skip-only — guard against a refactor that
    accidentally removes it from EXPECTED and makes the whole test vacuous."""
    desktop = os.path.join(_BACKEND, "build_code.py")
    assert desktop in EXPECTED, "the desktop codec must be pinned in EXPECTED"
    assert os.path.exists(desktop), "backend/build_code.py must exist"
