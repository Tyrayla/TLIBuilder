"""engine-data.zip must be byte-identical when the data is identical, whenever and wherever it's built. Before,
each entry carried the source file's mtime (and OS-specific attributes), so every rebuild produced a "changed" zip:
data deploys re-uploaded it and verify-web-deploy.mjs flagged a current CDN as stale (found 2026-10-02).
"""
import os
import zipfile

from tools.export_engine_bundle import _write_zip


def _files(root, contents):
    paths = []
    for name, data in contents.items():
        p = os.path.join(root, name)
        with open(p, "wb") as f:
            f.write(data)
        paths.append((p, f"seasons/SS13/{name}"))
    return paths


CONTENTS = {"a.json": b'{"a":1}', "b.json": b'{"b":[1,2,3]}'}


def test_same_data_different_mtimes_gives_identical_bytes(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    one = _files(str(tmp_path / "one"), CONTENTS)
    two = _files(str(tmp_path / "two"), CONTENTS)
    for p, _ in one:
        os.utime(p, (1_600_000_000, 1_600_000_000))   # 2020
    for p, _ in two:
        os.utime(p, (1_800_000_000, 1_800_000_000))   # 2027

    _write_zip(one, str(tmp_path / "one.zip"))
    _write_zip(two, str(tmp_path / "two.zip"))

    assert (tmp_path / "one.zip").read_bytes() == (tmp_path / "two.zip").read_bytes()


def test_zip_contents_and_order_are_preserved(tmp_path):
    entries = _files(str(tmp_path), CONTENTS)
    _write_zip(entries, str(tmp_path / "out.zip"))

    with zipfile.ZipFile(tmp_path / "out.zip") as z:
        assert z.namelist() == ["seasons/SS13/a.json", "seasons/SS13/b.json"]
        assert z.read("seasons/SS13/a.json") == b'{"a":1}'
        assert z.read("seasons/SS13/b.json") == b'{"b":[1,2,3]}'
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist())


def test_changed_data_changes_the_bytes(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    _write_zip(_files(str(tmp_path / "one"), CONTENTS), str(tmp_path / "one.zip"))
    _write_zip(_files(str(tmp_path / "two"), {**CONTENTS, "b.json": b'{"b":[1,2,4]}'}), str(tmp_path / "two.zip"))

    assert (tmp_path / "one.zip").read_bytes() != (tmp_path / "two.zip").read_bytes()
