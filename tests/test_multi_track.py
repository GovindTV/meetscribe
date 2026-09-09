"""
tests/test_multi_track.py - Validation of Multi-Track OBS Audio Pipeline
"""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
import win32com.client

from process_meeting import (
    get_audio_tracks_info,
    extract_audio,
    transcribe_audio,
    merge_split_recordings,
)


class TestMultiTrackPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("tests/temp_multi_track").resolve()
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.bundle_dir = cls.test_dir / "bundle"
        cls.bundle_dir.mkdir(parents=True, exist_ok=True)

        # Generate two speech WAV files using Windows SAPI TTS
        cls.host_wav = cls.test_dir / "host_speech.wav"
        cls.remote_wav = cls.test_dir / "remote_speech.wav"

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")

        # Host speaks
        stream.Open(str(cls.host_wav), 3, False)
        voice.AudioOutputStream = stream
        voice.Speak("Hello team, I am the meeting host reviewing the quarterly deliverables.")
        stream.Close()

        # Remote speaks
        stream.Open(str(cls.remote_wav), 3, False)
        voice.AudioOutputStream = stream
        voice.Speak("Thank you. I am the remote technical lead and the database migration is on schedule.")
        stream.Close()

        # Generate a 3-track video (Video + Master Mix + Remote + Host)
        # Track 1 (0:a:0): Master mix
        # Track 2 (0:a:1): Remote speech
        # Track 3 (0:a:2): Host speech
        cls.video_path = cls.test_dir / "synthetic_multi.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=navy:s=640x360:d=6",
            "-i", str(cls.host_wav),
            "-i", str(cls.remote_wav),
            "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=longest[mix]",
            "-map", "0:v",
            "-map", "[mix]",
            "-map", "2:a",
            "-map", "1:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            str(cls.video_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_probe_audio_tracks(self):
        tracks = get_audio_tracks_info(self.video_path)
        self.assertEqual(len(tracks), 3, f"Expected 3 audio tracks, found {len(tracks)}")

    def test_02_extract_multi_track_audio(self):
        tracks = get_audio_tracks_info(self.video_path)
        extracted = extract_audio(
            self.video_path,
            self.bundle_dir,
            tracks,
            remote_track=2,
            host_track=3,
            master_track=1
        )
        self.assertTrue(extracted["is_multi_track"])
        self.assertTrue(extracted["master_wav"].is_file())
        self.assertTrue(extracted["remote_wav"].is_file())
        self.assertTrue(extracted["host_wav"].is_file())
        self.assertGreater(extracted["remote_wav"].stat().st_size, 1000)
        self.assertGreater(extracted["host_wav"].stat().st_size, 1000)

    def test_03_transcribe_multi_track_audio(self):
        tracks = get_audio_tracks_info(self.video_path)
        extracted = extract_audio(
            self.video_path,
            self.bundle_dir,
            tracks,
            remote_track=2,
            host_track=3,
            master_track=1
        )
        turns = transcribe_audio(extracted, self.bundle_dir, model_size="tiny")
        self.assertGreater(len(turns), 0, "Expected at least 1 speech turn")

        channels = {t.get("channel") for t in turns}
        self.assertTrue("Host" in channels or "Remote Attendee" in channels)

        # Check transcript.txt contains channel tags
        txt_path = self.bundle_dir / "transcript.txt"
        self.assertTrue(txt_path.is_file())
        content = txt_path.read_text(encoding="utf-8")
        self.assertTrue("[" in content and "]" in content)

    def test_04_merge_multi_stream_preserves_tracks(self):
        # Merge two copies of the 3-track video to verify -map 0 preserves all 3 audio streams
        merged_video = merge_split_recordings([self.video_path, self.video_path], self.bundle_dir)
        tracks = get_audio_tracks_info(merged_video)
        self.assertEqual(len(tracks), 3, f"Expected 3 audio tracks in merged video, found {len(tracks)}")

    def test_05_single_track_fallback(self):
        existing_single = Path("recordings/synthetic_part1.mp4").resolve()
        if existing_single.is_file():
            tracks = get_audio_tracks_info(existing_single)
            self.assertEqual(len(tracks), 1)
            single_bundle = self.test_dir / "single_bundle"
            single_bundle.mkdir(parents=True, exist_ok=True)
            extracted = extract_audio(
                existing_single,
                single_bundle,
                tracks,
                remote_track=2,
                host_track=3,
                master_track=1
            )
            self.assertFalse(extracted["is_multi_track"])
            self.assertTrue(extracted["master_wav"].is_file())
            self.assertIsNone(extracted["remote_wav"])


if __name__ == "__main__":
    unittest.main()
