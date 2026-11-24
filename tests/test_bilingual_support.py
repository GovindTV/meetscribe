"""
tests/test_bilingual_support.py - Unit tests for Hindi/English (Hinglish) bilingual support
"""

import argparse
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from process_meeting import (
    build_whisper_biasing_params,
    clean_repetitive_text,
    invoke_antigravity,
    transcribe_audio,
)


class TestBilingualSupport(unittest.TestCase):
    def test_01_clean_repetitive_text_hindi_purna_viram(self):
        # Repetitive sentences ending in Hindi Purna Viram (।)
        text_with_repetition = "हम इस एपीआई को डिप्लॉय करेंगे। हम इस एपीआई को डिप्लॉय करेंगे।"
        cleaned = clean_repetitive_text(text_with_repetition)
        self.assertEqual(cleaned, "हम इस एपीआई को डिप्लॉय करेंगे।")

    def test_02_clean_repetitive_text_hindi_double_purna_viram(self):
        # Repetitive sentences ending in double Purna Viram (॥)
        text_with_double_viram = "यह काम पूरा हो चुका है॥ यह काम पूरा हो चुका है॥"
        cleaned = clean_repetitive_text(text_with_double_viram)
        self.assertEqual(cleaned, "यह काम पूरा हो चुका है॥")

    def test_03_clean_repetitive_text_hinglish_mixed_punctuation(self):
        # Mixed Hinglish sentences with English punctuation
        text = "Schema freeze kar chuke hain. Schema freeze kar chuke hain."
        cleaned = clean_repetitive_text(text)
        self.assertEqual(cleaned, "Schema freeze kar chuke hain.")

    def test_04_build_whisper_biasing_params_hindi_with_glossary(self):
        glossary = {
            "team": [
                {"name": "Rohit Sharma", "aliases": ["Rohit", "रोहित"]},
                {"name": "Shraddha Tambe", "aliases": ["Shraddha", "श्रद्धा"]},
            ],
            "terms": [
                {"canonical": "CHANGE_REGISTER", "description": "Table for ARR changes"},
                {"canonical": "Snowflake", "description": "Data warehouse"},
            ],
            "hotwords": ["API", "Schema"],
        }
        initial_prompt, hotwords = build_whisper_biasing_params(glossary, language="hi")
        self.assertIsNotNone(initial_prompt)
        self.assertIn("यह मीटिंग हिंदी और अंग्रेज़ी में है", initial_prompt)
        self.assertIn("Rohit Sharma", initial_prompt)
        self.assertIn("रोहित", initial_prompt)
        self.assertIn("CHANGE_REGISTER", initial_prompt)
        self.assertIn("Snowflake", initial_prompt)
        self.assertEqual(hotwords, "Rohit Sharma Rohit रोहित Shraddha Tambe Shraddha श्रद्धा CHANGE_REGISTER Snowflake API Schema")

    def test_05_build_whisper_biasing_params_hindi_without_glossary(self):
        initial_prompt, hotwords = build_whisper_biasing_params(None, language="hi")
        self.assertIsNotNone(initial_prompt)
        self.assertIn("यह मीटिंग हिंदी और अंग्रेज़ी में है", initial_prompt)
        self.assertIsNone(hotwords)

    def test_06_build_whisper_biasing_params_default_english_backward_compatible(self):
        glossary = {
            "terms": [
                {"canonical": "Snowflake", "description": "Data warehouse"}
            ]
        }
        initial_prompt, hotwords = build_whisper_biasing_params(glossary)
        self.assertIsNotNone(initial_prompt)
        self.assertTrue(initial_prompt.startswith("Meeting discussion covering team members and domain terms:"))
        self.assertNotIn("हिंदी", initial_prompt)

    @patch("subprocess.run")
    def test_07_invoke_antigravity_contains_bilingual_instructions(self, mock_run):
        mock_run.return_value = MagicMock(return_value=0, stdout="# Minutes of Meeting: Test\n", stderr="")
        video_path = Path("recordings/test_meeting.mp4")
        bundle_dir = Path("tests/temp_test_bundle")
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "transcript.txt").write_text("[00:00:00 -> 00:00:10] [Host]: Rohit, schema freeze kar diya?", encoding="utf-8")
        (bundle_dir / "slides").mkdir(parents=True, exist_ok=True)
        (bundle_dir / "speakers").mkdir(parents=True, exist_ok=True)
        output_dir = Path("tests/temp_test_output")

        try:
            invoke_antigravity(
                video_path=video_path,
                bundle_dir=bundle_dir,
                output_dir=output_dir,
                language="hi",
            )
            self.assertTrue(mock_run.called)
            cmd_args = mock_run.call_args[0][0]
            # Prompt is the last argument to agy
            prompt = cmd_args[-1]
            self.assertIn("CRITICAL PRINCIPLE 5 - BILINGUAL & CODE-SWITCHED SPEECH", prompt)
            self.assertIn("Synthesize the entire Minutes of Meeting strictly in professional, executive-standard English", prompt)
            self.assertIn("Preserve exact technical terminology", prompt)
            self.assertIn("kya haal hai", prompt)
        finally:
            import shutil
            shutil.rmtree(bundle_dir, ignore_errors=True)
            shutil.rmtree(output_dir, ignore_errors=True)

    @patch("faster_whisper.WhisperModel")
    def test_08_transcribe_audio_forwards_language_and_task(self, mock_model_cls):
        mock_instance = MagicMock()
        mock_info = MagicMock(duration=10.0, language="hi", language_probability=0.98)
        mock_instance.transcribe.return_value = ([], mock_info)
        mock_model_cls.return_value = mock_instance

        audio_files = {
            "is_multi_track": False,
            "master_wav": Path("audio.wav"),
        }
        bundle_dir = Path("tests/temp_transcribe_test")
        bundle_dir.mkdir(parents=True, exist_ok=True)

        try:
            transcribe_audio(
                audio_files=audio_files,
                bundle_dir=bundle_dir,
                model_size="turbo",
                language="hi",
                task="translate",
            )
            self.assertTrue(mock_instance.transcribe.called)
            _, kwargs = mock_instance.transcribe.call_args
            self.assertEqual(kwargs.get("language"), "hi")
            self.assertEqual(kwargs.get("task"), "translate")
        finally:
            import shutil
            shutil.rmtree(bundle_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
