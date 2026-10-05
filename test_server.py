"""Proves /analyze never leaves a recording behind, on any path.

Run with:  python -m unittest test_server -v
Needs only Flask: birdnetlib (and its model) is replaced by a stub, and
ffmpeg by a fake subprocess.run, so this runs anywhere.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

# Stub birdnetlib before server.py imports it (it loads a model at import).
_birdnetlib = types.ModuleType("birdnetlib")
_analyzer_mod = types.ModuleType("birdnetlib.analyzer")


class _FakeRecording:
    fail = False

    def __init__(self, **kwargs):
        self.path = kwargs["path"]
        self.detections = []

    def analyze(self):
        if _FakeRecording.fail:
            raise RuntimeError("analysis failed")
        self.detections = [{
            "common_name": "American Robin", "scientific_name": "Turdus migratorius",
            "confidence": 0.9, "start_time": 0.0, "end_time": 3.0,
        }]


_birdnetlib.Recording = _FakeRecording
_analyzer_mod.Analyzer = lambda: object()
sys.modules["birdnetlib"] = _birdnetlib
sys.modules["birdnetlib.analyzer"] = _analyzer_mod

import server  # noqa: E402


class AnalyzeLeavesNoFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="birdnet-test-")
        self._old_tempdir = tempfile.tempdir
        tempfile.tempdir = self.dir
        _FakeRecording.fail = False
        self.client = server.app.test_client()

    def tearDown(self):
        tempfile.tempdir = self._old_tempdir
        shutil.rmtree(self.dir, ignore_errors=True)

    def post(self):
        return self.client.post(
            "/analyze",
            data={"audio": (io.BytesIO(b"not really audio"), "clip.m4a")},
            content_type="multipart/form-data",
        )

    def leftovers(self):
        return os.listdir(self.dir)

    def test_conversion_raises(self):
        # The path that used to return before the delete step.
        with mock.patch.object(server.subprocess, "run", side_effect=OSError("ffmpeg missing")):
            r = self.post()
        self.assertEqual(r.status_code, 500)
        self.assertIn("Audio conversion failed", r.get_json()["error"])
        self.assertEqual(self.leftovers(), [])

    def test_conversion_times_out(self):
        with mock.patch.object(server.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("ffmpeg", 30)):
            r = self.post()
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.leftovers(), [])

    def test_conversion_produces_nothing(self):
        with mock.patch.object(server.subprocess, "run", return_value=None):
            r = self.post()
        self.assertEqual(r.status_code, 500)
        self.assertIn("no output", r.get_json()["error"])
        self.assertEqual(self.leftovers(), [])

    def _fake_ffmpeg(self, cmd, **kwargs):
        with open(cmd[-1], "wb") as f:
            f.write(b"wav")

    def test_analysis_fails(self):
        _FakeRecording.fail = True
        with mock.patch.object(server.subprocess, "run", side_effect=self._fake_ffmpeg):
            r = self.post()
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.leftovers(), [])

    def test_success(self):
        with mock.patch.object(server.subprocess, "run", side_effect=self._fake_ffmpeg):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["detections"][0]["species"], "American Robin")
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
