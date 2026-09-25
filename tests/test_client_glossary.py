"""
tests/test_client_glossary.py - Validation of Client Terminology Grounding and Decoder Biasing
"""

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from process_meeting import (
    get_default_glossary_template,
    load_client_glossary,
    build_whisper_biasing_params,
    transcribe_audio,
    invoke_antigravity,
)


class TestClientGlossary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("tests/temp_glossary_test").resolve()
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.clients_dir = cls.test_dir / "clients"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def tearDown(self):
        if self.clients_dir.exists():
            shutil.rmtree(self.clients_dir, ignore_errors=True)

    def test_01_template_schema(self):
        template = get_default_glossary_template("custom_client")
        self.assertEqual(template["client_id"], "custom_client")
        self.assertIn("display_name", template)
        self.assertIn("terms", template)
        self.assertIn("hotwords", template)
        self.assertIsInstance(template["terms"], list)
        self.assertIsInstance(template["hotwords"], list)
        self.assertGreater(len(template["terms"]), 0)
        self.assertIn("canonical", template["terms"][0])

    def test_02_load_glossary_autoscaffold_default(self):
        # When default profile does not exist, it should be auto-scaffolded
        glossary, path = load_client_glossary("default", self.clients_dir)
        self.assertIsNotNone(glossary)
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "default.json")
        self.assertEqual(glossary["client_id"], "default")

    def test_03_load_existing_glossary(self):
        self.clients_dir.mkdir(parents=True, exist_ok=True)
        custom_path = self.clients_dir / "acme.json"
        data = {
            "client_id": "acme",
            "display_name": "Acme Corp",
            "terms": [
                {"canonical": "AcmeNexus", "description": "Core API gateway"}
            ],
            "hotwords": ["K8s", "GraphQL"]
        }
        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        glossary, path = load_client_glossary("acme", self.clients_dir)
        self.assertEqual(glossary["display_name"], "Acme Corp")
        self.assertEqual(path, custom_path)

    def test_04_load_missing_custom_profile_graceful(self):
        # Non-default missing profile returns None without raising
        glossary, path = load_client_glossary("nonexistent", self.clients_dir)
        self.assertIsNone(glossary)
        self.assertIsNone(path)

    def test_05_load_disabled_client(self):
        glossary, path = load_client_glossary(None, self.clients_dir)
        self.assertIsNone(glossary)
        self.assertIsNone(path)

    def test_06_build_whisper_biasing_params(self):
        glossary = {
            "terms": [
                {"canonical": "AcmeNexus", "description": "API Gateway"},
                {"canonical": "ApolloSync", "description": "State sync"}
            ],
            "hotwords": ["K8s", "OAuth2"]
        }
        initial_prompt, hotwords = build_whisper_biasing_params(glossary)
        self.assertIsNotNone(initial_prompt)
        self.assertIn("AcmeNexus", initial_prompt)
        self.assertIn("ApolloSync", initial_prompt)
        self.assertIn("K8s", initial_prompt)
        self.assertIn("OAuth2", initial_prompt)

        self.assertEqual(hotwords, "AcmeNexus ApolloSync K8s OAuth2")

    def test_07_build_whisper_biasing_params_empty(self):
        prompt, hotwords = build_whisper_biasing_params(None)
        self.assertIsNone(prompt)
        self.assertIsNone(hotwords)

        prompt, hotwords = build_whisper_biasing_params({"terms": [], "hotwords": []})
        self.assertIsNone(prompt)
        self.assertIsNone(hotwords)

    @patch("faster_whisper.WhisperModel")
    def test_08_transcribe_audio_passes_biasing_params(self, mock_whisper_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 2.0
        mock_seg.text = "Hello AcmeNexus"
        mock_info = MagicMock()
        mock_info.duration = 2.0
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_model.transcribe.return_value = ([mock_seg], mock_info)

        dummy_audio = self.test_dir / "test.wav"
        dummy_audio.write_bytes(b"RIFF" + b"\x00" * 40)
        bundle_dir = self.test_dir / "bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)

        audio_files = {
            "is_multi_track": False,
            "master_wav": dummy_audio
        }

        turns = transcribe_audio(
            audio_files,
            bundle_dir,
            model_size="tiny",
            initial_prompt="Meeting discussion covering: AcmeNexus.",
            hotwords="AcmeNexus"
        )

        self.assertEqual(len(turns), 1)
        mock_model.transcribe.assert_called_once()
        _, kwargs = mock_model.transcribe.call_args
        self.assertEqual(kwargs.get("initial_prompt"), "Meeting discussion covering: AcmeNexus.")
        self.assertEqual(kwargs.get("hotwords"), "AcmeNexus")

    @patch("subprocess.run")
    def test_09_invoke_antigravity_injects_glossary_and_suggestions(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.stdout = "# Minutes of Meeting: Test\n\nExecutive Summary content."
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        video_path = self.test_dir / "test_session.mp4"
        bundle_dir = self.test_dir / "bundle"
        output_dir = self.test_dir / "out"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "transcript.txt").write_text("Hello team", encoding="utf-8")

        glossary = {
            "display_name": "TestCorp",
            "terms": [{"canonical": "OmegaGateway", "description": "Reverse proxy"}],
            "hotwords": ["Envoy"]
        }

        # Pre-seed a suggested_terms.json in bundle
        suggested_path = bundle_dir / "suggested_terms.json"
        with open(suggested_path, "w", encoding="utf-8") as f:
            json.dump([{"term": "ProtoBufX", "context": "New serialization format"}], f)

        mom_path = invoke_antigravity(
            video_path,
            bundle_dir,
            output_dir,
            client_glossary=glossary
        )

        self.assertTrue(mom_path.is_file())
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        prompt = call_args[-1]

        self.assertIn("CLIENT DOMAIN GLOSSARY (TestCorp):", prompt)
        self.assertIn("OmegaGateway", prompt)
        self.assertIn("Reverse proxy", prompt)
        self.assertIn("DISCOVERY OF CANDIDATE CLIENT TERMINOLOGY:", prompt)


if __name__ == "__main__":
    unittest.main()
