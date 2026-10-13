"""
tests/test_post_execution_actions.py - Unit tests for post-execution interactive menu, key reading, and file opening
"""

import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from process_meeting import (
    open_path,
    reveal_in_file_manager,
    read_single_key,
    post_execution_menu,
)


class TestPostExecutionActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("tests/temp_actions_test").resolve()
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.bundle_dir = cls.test_dir / "bundle"
        cls.bundle_dir.mkdir(parents=True, exist_ok=True)
        cls.output_dir = cls.test_dir / "docs_mom"
        cls.output_dir.mkdir(parents=True, exist_ok=True)
        cls.clients_dir = cls.test_dir / "clients"
        cls.clients_dir.mkdir(parents=True, exist_ok=True)

        cls.dummy_mom = cls.output_dir / "test_mom.md"
        cls.dummy_mom.write_text("# Test MoM", encoding="utf-8")

        cls.dummy_glossary = cls.clients_dir / "default.json"
        cls.dummy_glossary.write_text(json.dumps({"client_id": "default", "terms": []}), encoding="utf-8")

        cls.dummy_transcript_txt = cls.bundle_dir / "transcript.txt"
        cls.dummy_transcript_txt.write_text("[00:00:01] Hello", encoding="utf-8")

        cls.dummy_video = cls.test_dir / "test_video.mp4"
        cls.dummy_video.write_bytes(b"\x00" * 100)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_open_path_existing_windows(self):
        with patch("sys.platform", "win32"), patch("os.startfile", create=True) as mock_startfile:
            res = open_path(self.dummy_mom)
            self.assertTrue(res)
            mock_startfile.assert_called_once_with(str(self.dummy_mom.resolve()))

    def test_02_open_path_nonexistent(self):
        non_existent = self.test_dir / "does_not_exist_xyz.txt"
        res = open_path(non_existent)
        self.assertFalse(res)

    def test_03_open_path_fallback_to_notepad(self):
        with patch("sys.platform", "win32"), \
             patch("os.startfile", side_effect=OSError("No association"), create=True), \
             patch("subprocess.Popen") as mock_popen:
            res = open_path(self.dummy_mom)
            self.assertTrue(res)
            mock_popen.assert_called_once_with(["notepad.exe", str(self.dummy_mom.resolve())])

    def test_04_reveal_in_file_manager_file(self):
        with patch("sys.platform", "win32"), patch("subprocess.Popen") as mock_popen:
            res = reveal_in_file_manager(self.dummy_mom)
            self.assertTrue(res)
            mock_popen.assert_called_once_with(["explorer", f"/select,{self.dummy_mom.resolve()}"])

    def test_05_reveal_in_file_manager_folder(self):
        with patch("sys.platform", "win32"), patch("os.startfile", create=True) as mock_startfile:
            res = reveal_in_file_manager(self.output_dir)
            self.assertTrue(res)
            mock_startfile.assert_called_once_with(str(self.output_dir.resolve()))

    def test_06_read_single_key_msvcrt_char(self):
        mock_msvcrt = MagicMock()
        mock_msvcrt.getwch.side_effect = ["1"]
        with patch("sys.platform", "win32"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch.dict("sys.modules", {"msvcrt": mock_msvcrt}):
            key = read_single_key()
            self.assertEqual(key, "1")

    def test_07_read_single_key_msvcrt_special_keys(self):
        mock_msvcrt = MagicMock()
        # Arrow key produces '\xe0' followed by code 'H'
        mock_msvcrt.getwch.side_effect = ["\xe0", "H"]
        with patch("sys.platform", "win32"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch.dict("sys.modules", {"msvcrt": mock_msvcrt}):
            key = read_single_key()
            self.assertEqual(key, "")

    def test_08_read_single_key_msvcrt_enter_and_esc(self):
        mock_msvcrt = MagicMock()
        mock_msvcrt.getwch.side_effect = ["\r"]
        with patch("sys.platform", "win32"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch.dict("sys.modules", {"msvcrt": mock_msvcrt}):
            key = read_single_key()
            self.assertEqual(key, "ENTER")

        mock_msvcrt.getwch.side_effect = ["\x1b"]
        with patch("sys.platform", "win32"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch.dict("sys.modules", {"msvcrt": mock_msvcrt}):
            key = read_single_key()
            self.assertEqual(key, "ESC")

    def test_09_read_single_key_line_input_fallback(self):
        with patch("sys.stdin.isatty", return_value=False), \
             patch("sys.stdin.readline", side_effect=["o\n", "\n", ""]):
            k1 = read_single_key()
            self.assertEqual(k1, "o")
            k2 = read_single_key()
            self.assertEqual(k2, "ENTER")
            k3 = read_single_key()
            self.assertEqual(k3, "EOF")

    @patch("process_meeting.open_path")
    @patch("process_meeting.read_single_key")
    def test_10_post_execution_menu_open_mom_then_exit(self, mock_read_key, mock_open_path):
        mock_read_key.side_effect = ["1", "c"]
        post_execution_menu(
            mom_file=self.dummy_mom,
            glossary_path=self.dummy_glossary,
            bundle_dir=self.bundle_dir,
            output_dir=self.output_dir,
            session_video=self.dummy_video,
            client_name="default",
            clients_dir=self.clients_dir,
        )
        mock_open_path.assert_called_once_with(self.dummy_mom)

    @patch("process_meeting.open_path")
    @patch("process_meeting.read_single_key")
    def test_11_post_execution_menu_open_glossary_then_exit(self, mock_read_key, mock_open_path):
        mock_read_key.side_effect = ["2", "q"]
        post_execution_menu(
            mom_file=self.dummy_mom,
            glossary_path=self.dummy_glossary,
            bundle_dir=self.bundle_dir,
            output_dir=self.output_dir,
            session_video=self.dummy_video,
            client_name="default",
            clients_dir=self.clients_dir,
        )
        mock_open_path.assert_called_once_with(self.dummy_glossary)

    @patch("process_meeting.open_path")
    @patch("process_meeting.read_single_key")
    def test_12_post_execution_menu_open_transcript(self, mock_read_key, mock_open_path):
        mock_read_key.side_effect = ["3", "close"]
        post_execution_menu(
            mom_file=self.dummy_mom,
            glossary_path=self.dummy_glossary,
            bundle_dir=self.bundle_dir,
            output_dir=self.output_dir,
            session_video=self.dummy_video,
            client_name="default",
            clients_dir=self.clients_dir,
        )
        mock_open_path.assert_called_once_with(self.dummy_transcript_txt)

    @patch("process_meeting.reveal_in_file_manager")
    @patch("process_meeting.read_single_key")
    def test_13_post_execution_menu_reveal_folder(self, mock_read_key, mock_reveal):
        mock_read_key.side_effect = ["4", "ENTER"]
        post_execution_menu(
            mom_file=self.dummy_mom,
            glossary_path=self.dummy_glossary,
            bundle_dir=self.bundle_dir,
            output_dir=self.output_dir,
            session_video=self.dummy_video,
            client_name="default",
            clients_dir=self.clients_dir,
        )
        mock_reveal.assert_called_once_with(self.dummy_mom)

    @patch("process_meeting.invoke_antigravity")
    @patch("process_meeting.read_single_key")
    def test_14_post_execution_menu_resynthesize(self, mock_read_key, mock_invoke):
        mock_invoke.return_value = self.dummy_mom
        mock_read_key.side_effect = ["5", "ESC"]
        post_execution_menu(
            mom_file=self.dummy_mom,
            glossary_path=self.dummy_glossary,
            bundle_dir=self.bundle_dir,
            output_dir=self.output_dir,
            session_video=self.dummy_video,
            client_name="default",
            clients_dir=self.clients_dir,
        )
        mock_invoke.assert_called_once()

    @patch("process_meeting.reveal_in_file_manager")
    @patch("process_meeting.read_single_key")
    def test_15_post_execution_menu_open_bundle(self, mock_read_key, mock_reveal):
        mock_read_key.side_effect = ["6", "c"]
        post_execution_menu(
            mom_file=self.dummy_mom,
            glossary_path=self.dummy_glossary,
            bundle_dir=self.bundle_dir,
            output_dir=self.output_dir,
            session_video=self.dummy_video,
            client_name="default",
            clients_dir=self.clients_dir,
        )
        mock_reveal.assert_called_once_with(self.bundle_dir)


if __name__ == "__main__":
    unittest.main()
