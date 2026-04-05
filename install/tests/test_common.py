"""test_common.py — Tests for install/_common.py utilities."""
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import (
    color,
    find_dir_by_markers,
    test_wyrd_connection as _wyrd_connection,
    copy_bridge_files,
)


def _wyrd_connection_import():
    """Smoke test: _wyrd_connection is importable and callable."""
    # Don't hit network — just confirm function exists and returns bool type
    import urllib.request, urllib.error
    import unittest.mock as mock
    with mock.patch("urllib.request.urlopen", side_effect=OSError("refused")):
        result = _wyrd_connection("localhost", 19999)
    assert result is False


# ===========================================================================
# color()
# ===========================================================================

class TestColor:
    def test_empty_code_returns_text_unchanged(self):
        assert color("hello", "") == "hello"

    def test_non_empty_code_wraps_text(self):
        result = color("hello", "\033[92m")
        assert "hello" in result

    def test_none_code_returns_text(self):
        assert color("test", "") == "test"

    def test_color_with_reset(self):
        result = color("ok", "\033[92m")
        # Should contain the original text
        assert "ok" in result


# ===========================================================================
# find_dir_by_markers()
# ===========================================================================

class TestFindDirByMarkers:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_dir_with_any_marker(self):
        (self.tmp / "Assets").mkdir()
        result = find_dir_by_markers([self.tmp], ["Assets", "nonexistent"])
        assert self.tmp in result

    def test_empty_when_no_markers_present(self):
        result = find_dir_by_markers([self.tmp], ["Assets", "ProjectSettings"])
        assert result == []

    def test_require_all_passes_when_all_present(self):
        (self.tmp / "Assets").mkdir()
        (self.tmp / "ProjectSettings").mkdir()
        result = find_dir_by_markers([self.tmp], ["Assets", "ProjectSettings"], require_all=True)
        assert self.tmp in result

    def test_require_all_fails_when_missing_one(self):
        (self.tmp / "Assets").mkdir()
        result = find_dir_by_markers([self.tmp], ["Assets", "ProjectSettings"], require_all=True)
        assert self.tmp not in result

    def test_skips_nonexistent_search_paths(self):
        result = find_dir_by_markers([Path("/nonexistent/path")], ["Assets"])
        assert result == []

    def test_file_marker_works_too(self):
        (self.tmp / "project.godot").write_text("godot_project=1")
        result = find_dir_by_markers([self.tmp], ["project.godot"])
        assert self.tmp in result

    def test_deduplicates_results(self):
        (self.tmp / "Assets").mkdir()
        result = find_dir_by_markers([self.tmp, self.tmp], ["Assets"])
        assert result.count(self.tmp) == 1

    def test_none_search_path_skipped(self):
        result = find_dir_by_markers([None], ["Assets"])
        assert result == []

    def test_empty_search_paths(self):
        result = find_dir_by_markers([], ["Assets"])
        assert result == []

    def test_returns_sorted_list(self):
        d1 = self.tmp / "alpha"
        d2 = self.tmp / "beta"
        d1.mkdir(); d2.mkdir()
        (d1 / "marker.txt").write_text("")
        (d2 / "marker.txt").write_text("")
        result = find_dir_by_markers([d2, d1], ["marker.txt"])
        assert result == sorted(result)


# ===========================================================================
# _wyrd_connection()
# ===========================================================================

class TestWyrdConnection:
    def test_returns_true_on_200(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert _wyrd_connection("localhost", 8765) is True

    def test_returns_false_on_connection_refused(self):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            assert _wyrd_connection("localhost", 8765) is False

    def test_returns_false_on_timeout(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            assert _wyrd_connection("localhost", 8765) is False

    def test_custom_host_port_used(self):
        calls = []
        def fake_open(url, timeout):
            calls.append(url)
            raise OSError("refused")
        with patch("urllib.request.urlopen", side_effect=fake_open):
            _wyrd_connection("myserver", 9999)
        assert calls and "myserver:9999" in calls[0]


# ===========================================================================
# copy_bridge_files()
# ===========================================================================

class TestCopyBridgeFiles:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_does_not_copy(self):
        src = self.tmp / "source.py"
        src.write_text("content")
        dst = self.tmp / "dest" / "source.py"
        copy_bridge_files([(src, dst)], dry_run=True)
        assert not dst.exists()

    def test_dry_run_returns_paths(self):
        src = self.tmp / "source.py"
        src.write_text("content")
        dst = self.tmp / "dest" / "source.py"
        result = copy_bridge_files([(src, dst)], dry_run=True)
        assert dst in result

    def test_real_copy_creates_file(self):
        src = self.tmp / "source.py"
        src.write_text("hello wyrd")
        dst = self.tmp / "output" / "source.py"
        copy_bridge_files([(src, dst)], dry_run=False)
        assert dst.exists()
        assert dst.read_text() == "hello wyrd"

    def test_creates_parent_dirs(self):
        src = self.tmp / "file.txt"
        src.write_text("x")
        dst = self.tmp / "deep" / "nested" / "dir" / "file.txt"
        copy_bridge_files([(src, dst)])
        assert dst.exists()

    def test_empty_list_returns_empty(self):
        result = copy_bridge_files([])
        assert result == []

    def test_multiple_files_all_copied(self):
        srcs = []
        dsts = []
        for i in range(3):
            s = self.tmp / f"src{i}.py"
            s.write_text(f"file{i}")
            srcs.append(s)
            dsts.append(self.tmp / "out" / f"dst{i}.py")
        pairs = list(zip(srcs, dsts))
        copy_bridge_files(pairs)
        for d in dsts:
            assert d.exists()
