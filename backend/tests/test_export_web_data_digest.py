"""The web-data manifest carries a content fingerprint of everything the CDN serves for the app (season
catalogs + icons), so the post-deploy check can tell a real production deploy from a stale one or a
preview-only one by comparing manifest.json alone (bug-301 follow-up: icons were otherwise unchecked).
"""
import os

from tools.export_web_data import content_digest


def _write(path, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _tree(root, files):
    for rel, data in files.items():
        _write(os.path.join(root, *rel.split("/")), data)
    return str(root)


BASE = {
    "SS13/skills.json": b'{"skills":[]}',
    "SS13/hero_traits.json": b'{"traits":[1]}',
    "icons/skills/a.webp": b"\x00\x01icon-a",
    "icons/gear/b.webp": b"\x00\x02icon-b",
}


def test_same_content_gives_the_same_digest_regardless_of_write_order(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", dict(reversed(list(BASE.items()))))
    assert content_digest(a, "SS13") == content_digest(b, "SS13")


def test_digest_is_a_sha256_hex_string(tmp_path):
    d = content_digest(_tree(tmp_path / "a", BASE), "SS13")
    assert len(d) == 64 and all(c in "0123456789abcdef" for c in d)


def test_changing_one_icon_changes_the_digest(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "icons/gear/b.webp": b"\x00\x02icon-B"})
    assert content_digest(a, "SS13") != content_digest(b, "SS13")


def test_changing_one_catalog_changes_the_digest(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "SS13/skills.json": b'{"skills":[1]}'})
    assert content_digest(a, "SS13") != content_digest(b, "SS13")


def test_renaming_a_file_changes_the_digest(tmp_path):
    renamed = {k if k != "icons/skills/a.webp" else "icons/skills/z.webp": v for k, v in BASE.items()}
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", renamed)
    assert content_digest(a, "SS13") != content_digest(b, "SS13")


def test_the_cdn_worker_and_headers_count(tmp_path):
    # _worker.js serves every request (and owns CORS); it can't be fetched to compare, so it rides in the digest.
    a = _tree(tmp_path / "a", {**BASE, "_worker.js": b"export default {}", "_headers": b"/*\n"})
    b = _tree(tmp_path / "b", {**BASE, "_worker.js": b"export default {x}", "_headers": b"/*\n"})
    c = _tree(tmp_path / "c", {**BASE, "_worker.js": b"export default {}", "_headers": b"/*\n  X: 1\n"})
    assert content_digest(a, "SS13") != content_digest(b, "SS13")
    assert content_digest(a, "SS13") != content_digest(c, "SS13")


def test_other_seasons_and_the_manifest_itself_do_not_count(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "SS12/skills.json": b"old season", "manifest.json": b'{"season":"SS13"}'})
    assert content_digest(a, "SS13") == content_digest(b, "SS13")
