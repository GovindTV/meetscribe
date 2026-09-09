"""
tests/test_parallel_extraction.py - Validation of Parallel Hardware-Optimized Extraction Pipeline
"""

import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
import win32com.client

from process_meeting import (
    get_hardware_profile,
    get_audio_tracks_info,
    extract_audio,
    transcribe_audio,
    extract_slide_frames,
    extract_speaker_frames,
    extract_artifacts_parallel,
    clean_bundle_directory,
)


class TestParallelExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("tests/temp_parallel_test").resolve()
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.seq_bundle = cls.test_dir / "seq_bundle"
        cls.par_bundle = cls.test_dir / "par_bundle"

        # Generate audio using SAPI TTS
        cls.host_wav = cls.test_dir / "host.wav"
        cls.remote_wav = cls.test_dir / "remote.wav"

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")

        stream.Open(str(cls.host_wav), 3, False)
        voice.AudioOutputStream = stream
        voice.Speak("Welcome everyone. Today we are presenting the new Q3 roadmap and milestones.")
        stream.Close()

        stream.Open(str(cls.remote_wav), 3, False)
        voice.AudioOutputStream = stream
        voice.Speak("Understood. The front end team has released the updated architecture diagrams.")
        stream.Close()

        # Generate synthetic video with 2 distinct slide visual scenes (navy and teal)
        # to test FFmpeg scene detection and multi-track audio simultaneously
        cls.video_path = cls.test_dir / "synthetic_session.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=navy:s=640x360:d=4",
            "-f", "lavfi", "-i", "color=c=teal:s=640x360:d=4",
            "-i", str(cls.host_wav),
            "-i", str(cls.remote_wav),
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[vcat];[2:a][3:a]amix=inputs=2:duration=longest[mix]",
            "-map", "[vcat]",
            "-map", "[mix]",
            "-map", "3:a",
            "-map", "2:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            str(cls.video_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_hardware_profile_detection(self):
        profile = get_hardware_profile()
        self.assertIn("cpu_count", profile)
        self.assertIn("whisper_threads", profile)
        self.assertIn("ffmpeg_threads", profile)
        self.assertIn("hwaccel", profile)
        self.assertGreater(profile["cpu_count"], 0)
        self.assertGreater(profile["whisper_threads"], 0)
        self.assertGreater(profile["ffmpeg_threads"], 0)

        # Confirm thread budget prevents CPU oversubscription
        allocated_worker_threads = profile["whisper_threads"] + profile["ffmpeg_threads"]
        self.assertLessEqual(
            allocated_worker_threads,
            profile["cpu_count"],
            f"Allocated threads ({allocated_worker_threads}) exceeds CPU count ({profile['cpu_count']})"
        )

    def test_02_custom_thread_allocation(self):
        profile = get_hardware_profile(
            custom_whisper_threads=2,
            custom_ffmpeg_threads=1,
            custom_speaker_workers=2,
            custom_hwaccel="none"
        )
        self.assertEqual(profile["whisper_threads"], 2)
        self.assertEqual(profile["ffmpeg_threads"], 1)
        self.assertEqual(profile["speaker_workers"], 2)
        self.assertIsNone(profile["hwaccel"])

    def test_03_parallel_vs_sequential_parity(self):
        profile = get_hardware_profile()
        tracks = get_audio_tracks_info(self.video_path)

        # 1. Run Sequential Extraction
        clean_bundle_directory(self.seq_bundle)
        audio_files_seq = extract_audio(
            self.video_path, self.seq_bundle, tracks,
            remote_track=2, host_track=3, master_track=1
        )
        t0_seq = time.time()
        turns_seq = transcribe_audio(
            audio_files_seq, self.seq_bundle, model_size="tiny",
            cpu_threads=profile["whisper_threads"]
        )
        slides_seq = extract_slide_frames(
            self.video_path, self.seq_bundle / "slides",
            hwaccel=profile["hwaccel"], threads=profile["ffmpeg_threads"]
        )
        speakers_seq = extract_speaker_frames(
            self.video_path, self.seq_bundle / "speakers",
            turns_seq, max_workers=1
        )
        t_seq = time.time() - t0_seq

        # 2. Run Parallel Extraction
        clean_bundle_directory(self.par_bundle)
        audio_files_par = extract_audio(
            self.video_path, self.par_bundle, tracks,
            remote_track=2, host_track=3, master_track=1
        )
        t0_par = time.time()
        turns_par = extract_artifacts_parallel(
            self.video_path, self.par_bundle, audio_files_par,
            model_size="tiny", profile=profile
        )
        t_par = time.time() - t0_par

        # Verify Artifact Parity
        self.assertGreater(len(turns_seq), 0)
        self.assertEqual(len(turns_seq), len(turns_par), "Speech turn counts differ between sequential and parallel")

        # Verify Speaker Channel Tags exist in both
        channels_seq = {t["channel"] for t in turns_seq}
        channels_par = {t["channel"] for t in turns_par}
        self.assertEqual(channels_seq, channels_par)
        self.assertTrue("Host" in channels_par or "Remote Attendee" in channels_par)

        # Verify Slide extraction captured frames in both
        slides_par = list((self.par_bundle / "slides").glob("*.jpg"))
        self.assertGreater(len(slides_par), 0, "No slides extracted in parallel mode")
        self.assertEqual(len(slides_seq), len(slides_par), "Slide frame counts differ")

        # Verify Speaker extraction captured frames in both
        speakers_par = list((self.par_bundle / "speakers").glob("*.jpg"))
        self.assertGreater(len(speakers_par), 0, "No speaker keyframes extracted in parallel mode")
        self.assertEqual(len(speakers_seq), len(speakers_par), "Speaker frame counts differ")

        print(f"\n========================================================")
        print(f"  BENCHMARK: Sequential: {t_seq:.2f}s | Parallel: {t_par:.2f}s")
        print(f"========================================================\n")


if __name__ == "__main__":
    unittest.main()
