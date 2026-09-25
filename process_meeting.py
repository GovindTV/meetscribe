#!/usr/bin/env python3
"""
process_meeting.py - Video Recording to Minutes of Meeting (MoM) Pipeline

Steps:
1. Discover source video (explicit path or latest video in recordings/)
2. Clear temporary artifact bundle folder to prevent bloat
3. Extract 16kHz mono audio from video
4. Transcribe speech turns using faster-whisper (CPU int8)
5. Extract two tiers of visual context:
   - slides/ (presentation / screen-share transitions via scene detection)
   - speakers/ (utterance keyframes at speech turn onsets)
6. Invoke Antigravity (agy CLI) to synthesize full-fidelity MoM into docs/mom/
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def get_video_duration(video_path: Path) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def get_audio_tracks_info(video_path: Path) -> list[dict]:
    """Query audio stream metadata using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index,codec_name,channels",
            "-of", "json",
            str(video_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return [s for s in data.get("streams", []) if s.get("codec_type", "audio") == "audio" or "channels" in s]
    except Exception:
        return []


def get_hardware_profile(
    custom_whisper_threads: int | None = None,
    custom_ffmpeg_threads: int | None = None,
    custom_speaker_workers: int | None = None,
    custom_hwaccel: str | None = None
) -> dict:
    """Detect available CPU threads and hardware acceleration options.
    Budgets threads to avoid oversubscription and thermal/power throttling on 15W CPUs:
    - 8 logical threads (e.g. i3-1215U / 6 cores): 4 for Whisper (P-cores), 2 for FFmpeg (E-cores), 2 for OS.
    - 6 logical threads: 3 for Whisper, 2 for FFmpeg, 1 for OS.
    - <=4 logical threads: 2 for Whisper, 1 for FFmpeg, 1 for OS.
    """
    cpu_count = os.cpu_count() or 4

    if cpu_count >= 8:
        default_whisper = 4
        default_ffmpeg = 2
        default_speakers = 3
    elif cpu_count >= 6:
        default_whisper = 3
        default_ffmpeg = 2
        default_speakers = 2
    else:
        default_whisper = max(1, cpu_count - 1)
        default_ffmpeg = 1
        default_speakers = 2

    whisper_threads = custom_whisper_threads if (custom_whisper_threads and custom_whisper_threads > 0) else default_whisper
    ffmpeg_threads = custom_ffmpeg_threads if (custom_ffmpeg_threads and custom_ffmpeg_threads > 0) else default_ffmpeg
    speaker_workers = custom_speaker_workers if (custom_speaker_workers and custom_speaker_workers > 0) else default_speakers

    # Hardware acceleration detection for FFmpeg video decoding
    hwaccel = None
    if custom_hwaccel and custom_hwaccel.lower() != "auto":
        hwaccel = None if custom_hwaccel.lower() == "none" else custom_hwaccel
    else:
        try:
            res = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True)
            out = res.stdout.lower()
            for method in ["d3d11va", "dxva2", "qsv"]:
                if method in out:
                    hwaccel = method
                    break
        except Exception:
            hwaccel = None

    return {
        "cpu_count": cpu_count,
        "whisper_threads": whisper_threads,
        "ffmpeg_threads": ffmpeg_threads,
        "speaker_workers": speaker_workers,
        "hwaccel": hwaccel,
    }


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH-MM-SS format for filenames."""
    total_sec = max(0.0, seconds)
    hours = int(total_sec // 3600)
    minutes = int((total_sec % 3600) // 60)
    sec = int(total_sec % 60)
    return f"{hours:02d}-{minutes:02d}-{sec:02d}"


def format_timestamp_colons(seconds: float) -> str:
    """Format seconds into HH:MM:SS format for transcripts."""
    total_sec = max(0.0, seconds)
    hours = int(total_sec // 3600)
    minutes = int((total_sec % 3600) // 60)
    sec = int(total_sec % 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}"


def find_source_videos(explicit_paths: list[str] | None, recordings_dir: Path) -> list[Path]:
    """Resolve one or more video files, or auto-discover the latest recording and its split segments."""
    valid_extensions = {".mp4", ".mkv", ".mov", ".webm", ".avi"}

    if explicit_paths:
        resolved = []
        for p_str in explicit_paths:
            # Handle glob patterns if wildcard present
            if any(char in p_str for char in ["*", "?"]):
                matches = list(Path().glob(p_str)) or list(recordings_dir.glob(p_str))
                for m in matches:
                    if m.is_file() and m.suffix.lower() in valid_extensions:
                        resolved.append(m.resolve())
            else:
                p = Path(p_str).resolve()
                if not p.is_file():
                    p_alt = recordings_dir / p_str
                    if p_alt.is_file():
                        p = p_alt.resolve()
                    else:
                        raise FileNotFoundError(f"Specified video file does not exist: {p_str}")
                resolved.append(p)

        if not resolved:
            raise FileNotFoundError(f"No valid video files matched: {explicit_paths}")

        # Sort chronologically by mtime then name
        return sorted(list(set(resolved)), key=lambda p: (p.stat().st_mtime, p.name))

    recordings_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        p for p in recordings_dir.iterdir()
        if p.is_file() and p.suffix.lower() in valid_extensions
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No video files found in {recordings_dir}. Please specify a video path or place a recording in {recordings_dir}."
        )

    # Pick latest by modified time
    latest_video = max(candidates, key=lambda p: p.stat().st_mtime)
    latest_mtime = latest_video.stat().st_mtime
    latest_date = datetime.fromtimestamp(latest_mtime).date()

    # Auto-detect sibling split files: files recorded on the same date within 45 mins of latest
    cluster = []
    for c in candidates:
        c_time = c.stat().st_mtime
        c_date = datetime.fromtimestamp(c_time).date()
        if c_date == latest_date and abs(latest_mtime - c_time) <= 45 * 60:
            cluster.append(c)

    # Sort cluster in chronological order
    cluster.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return cluster


def merge_split_recordings(video_paths: list[Path], bundle_dir: Path) -> Path:
    """Concatenate multiple split recordings losslessly into a unified session timeline (ADR-0002)."""
    if len(video_paths) == 1:
        return video_paths[0]

    merged_file = bundle_dir / "merged_session.mp4"
    concat_file = bundle_dir / "concat_list.txt"

    print(f"[*] CONCATENATING {len(video_paths)} SPLIT RECORDINGS (LOSSLESS STREAM COPY)")
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in video_paths:
            safe_path = str(p.resolve()).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    t0 = time.time()
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-map", "0",
        "-c", "copy",
        str(merged_file)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # Fallback to standard stream copy without -map 0 for heterogeneous streams
        fallback_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(merged_file)
        ]
        res = subprocess.run(fallback_cmd, capture_output=True, text=True)
        if res.returncode != 0 or not merged_file.is_file():
            raise RuntimeError(f"FFmpeg split video concatenation failed:\n{res.stderr}")

    elapsed = time.time() - t0
    merged_size_mb = merged_file.stat().st_size / (1024 * 1024)
    print(f"      -> Unified session created in {elapsed:.2f}s ({merged_size_mb:.2f} MB): {merged_file.name}\n")
    return merged_file


def clean_bundle_directory(bundle_dir: Path) -> None:
    """Wipe any previous temporary artifacts to prevent bloat."""
    print("[1/5] CLEANING ARTIFACT BUNDLE")
    print(f"      -> Working Directory: {bundle_dir}")
    purged_count = 0
    if bundle_dir.exists():
        for item in bundle_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                purged_count += 1
            else:
                try:
                    item.unlink()
                    purged_count += 1
                except OSError:
                    pass
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "slides").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "speakers").mkdir(parents=True, exist_ok=True)
    print(f"      -> Purged {purged_count} previous items. Clean directories ready.\n")


def extract_audio(
    video_path: Path,
    bundle_dir: Path,
    audio_tracks: list[dict],
    remote_track: int = 2,
    host_track: int = 3,
    master_track: int = 1,
    disable_multi_track: bool = False
) -> dict:
    """Extract 16kHz mono audio streams from video.
    Supports multi-track OBS recordings (Master Mix, Remote Attendees, Host Mic)
    as well as standard single-track fallback.
    """
    print("[2/5] EXTRACTING AUDIO VIA FFMPEG")
    master_wav = bundle_dir / "audio.wav"
    remote_wav = bundle_dir / "audio_remote.wav"
    host_wav = bundle_dir / "audio_host.wav"

    track_count = len(audio_tracks)
    master_idx = master_track - 1
    remote_idx = remote_track - 1
    host_idx = host_track - 1

    has_valid_tracks = (
        track_count >= 3
        and 0 <= master_idx < track_count
        and 0 <= remote_idx < track_count
        and 0 <= host_idx < track_count
        and len({master_idx, remote_idx, host_idx}) == 3
    )

    is_multi = (has_valid_tracks and not disable_multi_track)
    t0 = time.time()

    if is_multi:
        print(f"      -> Audio Stream Count: {track_count} tracks detected in OBS recording!")
        print(f"      -> Mode: Multi-Track Isolated Audio Extraction (ADR-0004)")
        print(f"         * Track {master_track} (Master Mix)  -> {master_wav.name}")
        print(f"         * Track {remote_track} (Remote Call) -> {remote_wav.name}")
        print(f"         * Track {host_track} (Host Mic)    -> {host_wav.name}")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-map", f"0:a:{master_idx}", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(master_wav),
            "-map", f"0:a:{remote_idx}", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(remote_wav),
            "-map", f"0:a:{host_idx}", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(host_wav),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            elapsed = time.time() - t0
            print(f"      -> Multi-track audio extracted in {elapsed:.2f}s.\n")
            return {
                "is_multi_track": True,
                "master_wav": master_wav,
                "remote_wav": remote_wav,
                "host_wav": host_wav,
            }
        else:
            err_snippet = res.stderr.strip().splitlines()[-1] if res.stderr else "unknown error"
            print(f"      [!] Multi-track extraction failed ({err_snippet}).")
            print("      [!] Falling back to standard single-track audio extraction...")

    # Standard single-track fallback mode
    if disable_multi_track and track_count >= 3:
        print(f"      -> Multi-track disabled via --disable-multi-track. Using master track {master_track}.")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-map", f"0:a:{master_idx if 0 <= master_idx < track_count else 0}",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(master_wav)
        ]
    else:
        print(f"      -> Audio Stream Count: {track_count} track(s). Mode: Standard Single-Track (Fallback).")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(master_wav)
        ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed:\n{res.stderr}")

    elapsed = time.time() - t0
    size_mb = master_wav.stat().st_size / (1024 * 1024)
    print(f"      -> Audio extracted in {elapsed:.2f}s ({size_mb:.2f} MB).\n")
    return {
        "is_multi_track": False,
        "master_wav": master_wav,
        "remote_wav": None,
        "host_wav": None,
    }


def get_default_glossary_template(client_id: str = "default") -> dict:
    """Return starter template for client glossary profile."""
    return {
        "client_id": client_id,
        "display_name": "Default Client",
        "description": "Client domain terminology and proprietary acronyms.",
        "terms": [
            {
                "canonical": "ExampleTerm",
                "description": "Description of what this system, project, or domain term represents."
            }
        ],
        "hotwords": [
            "ExampleHotword"
        ]
    }


def load_client_glossary(client_name: str | None, clients_dir: Path) -> tuple[dict | None, Path | None]:
    """Load client glossary JSON file. If default profile is requested but missing,
    auto-scaffolds a starter template.
    """
    if not client_name:
        return None, None

    clients_dir.mkdir(parents=True, exist_ok=True)
    glossary_path = clients_dir / f"{client_name}.json"

    if not glossary_path.is_file():
        if client_name == "default":
            template = get_default_glossary_template("default")
            with open(glossary_path, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2)
            print(f"[*] CLIENT GLOSSARY: Auto-scaffolded starter profile at '{glossary_path.as_posix()}'.")
            print(f"    -> Add your client's proprietary terms to this file to bias Whisper and MoM synthesis.\n")
            return template, glossary_path
        else:
            print(f"[!] Warning: Client profile '{client_name}' not found at '{glossary_path}'. Proceeding without client glossary.\n")
            return None, None

    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            glossary = json.load(f)
        terms_count = len(glossary.get("terms", []))
        hotwords_count = len(glossary.get("hotwords", []))
        display_name = glossary.get("display_name", client_name)
        print(f"[*] CLIENT GLOSSARY: Loaded '{display_name}' ({glossary_path.name})")
        print(f"    -> {terms_count} canonical terms, {hotwords_count} hotwords loaded for decoder biasing & synthesis grounding.\n")
        return glossary, glossary_path
    except Exception as e:
        print(f"[!] Warning: Failed to parse client profile '{glossary_path}': {e}. Proceeding without client glossary.\n")
        return None, None


def build_whisper_biasing_params(glossary: dict | None) -> tuple[str | None, str | None]:
    """Compile canonical terms and hotwords into Whisper decoder biasing parameters."""
    if not glossary:
        return None, None

    terms = [t["canonical"].strip() for t in glossary.get("terms", []) if isinstance(t, dict) and t.get("canonical")]
    hotwords_list = [h.strip() for h in glossary.get("hotwords", []) if isinstance(h, str) and h.strip()]

    all_terms = list(dict.fromkeys(terms + hotwords_list))
    if not all_terms:
        return None, None

    # Format initial_prompt context sentence (keeping within Whisper's ~224 token limit)
    terms_sample = ", ".join(all_terms[:40])
    initial_prompt = f"Meeting discussion covering client domain terminology: {terms_sample}."

    # Native hotwords argument in faster-whisper (space-separated string)
    hotwords = " ".join(all_terms)

    return initial_prompt, hotwords


def transcribe_audio(
    audio_files: dict,
    bundle_dir: Path,
    model_size: str = "large-v3",
    cpu_threads: int | None = None,
    initial_prompt: str | None = None,
    hotwords: str | None = None
) -> list[dict]:
    """Transcribe audio using faster-whisper on CPU with int8 quantization.
    Supports multi-track transcription with isolated Host vs Remote channels, VAD filtering,
    and client domain decoder biasing (initial_prompt and hotwords).
    """
    if model_size == "large":
        model_size = "large-v3"
    print("[3/5] TRANSCRIBING SPEECH WITH FASTER-WHISPER")
    thread_info = f" | CPU Threads: {cpu_threads}" if cpu_threads else ""
    print(f"      -> Engine: faster-whisper | Model: '{model_size}' | Quantization: int8 (CPU){thread_info}")
    if initial_prompt or hotwords:
        prompt_snippet = f" (Context: '{initial_prompt[:50]}...')" if initial_prompt else ""
        print(f"      -> Decoder Biasing: Active{prompt_snippet}")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("faster-whisper is required. Install via: pip install faster-whisper")

    print(f"      -> Initializing Whisper '{model_size}' (downloads automatically on first run)...")
    sys.stdout.flush()
    t_load = time.time()
    whisper_kwargs = {"device": "cpu", "compute_type": "int8"}
    if cpu_threads and cpu_threads > 0:
        whisper_kwargs["cpu_threads"] = cpu_threads
    model = WhisperModel(model_size, **whisper_kwargs)
    print(f"      -> Model loaded in {time.time() - t_load:.2f}s.")

    transcribe_kwargs = {
        "beam_size": 5,
        "vad_filter": True,
        "vad_parameters": dict(min_silence_duration_ms=500),
    }
    if initial_prompt:
        transcribe_kwargs["initial_prompt"] = initial_prompt
    if hotwords:
        transcribe_kwargs["hotwords"] = hotwords

    t0 = time.time()
    all_turns = []
    text_lines = []

    if audio_files.get("is_multi_track"):
        # 1. Transcribe Remote Attendees
        remote_path = audio_files["remote_wav"]
        print(f"      -> [Channel 1/2: Remote Attendees] Transcribing {remote_path.name} with VAD filtering...")
        sys.stdout.flush()
        remote_segments, _ = model.transcribe(
            str(remote_path),
            **transcribe_kwargs
        )
        remote_turns = []
        for seg in remote_segments:
            text = seg.text.strip()
            if text:
                remote_turns.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "timestamp": format_timestamp_colons(seg.start),
                    "channel": "Remote Attendee",
                    "text": text,
                })
        print(f"         * Remote Speech: {len(remote_turns)} speech turns captured.")

        # 2. Transcribe Host Microphone
        host_path = audio_files["host_wav"]
        print(f"      -> [Channel 2/2: Host Microphone] Transcribing {host_path.name} with VAD filtering...")
        sys.stdout.flush()
        host_segments, _ = model.transcribe(
            str(host_path),
            **transcribe_kwargs
        )
        host_turns = []
        for seg in host_segments:
            text = seg.text.strip()
            if text:
                host_turns.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "timestamp": format_timestamp_colons(seg.start),
                    "channel": "Host",
                    "text": text,
                })
        print(f"         * Host Speech: {len(host_turns)} speech turns captured.")

        # 3. Merge chronologically
        merged_turns = sorted(remote_turns + host_turns, key=lambda t: t["start"])
        for idx, turn in enumerate(merged_turns):
            turn["id"] = idx
            start_str = turn["timestamp"]
            end_str = format_timestamp_colons(turn["end"])
            channel_tag = f"[{turn['channel']}]"
            all_turns.append(turn)
            text_lines.append(f"[{start_str} -> {end_str}] {channel_tag}: {turn['text']}")
    else:
        audio_path = audio_files["master_wav"]
        segments, info = model.transcribe(
            str(audio_path),
            **transcribe_kwargs
        )
        total_duration = max(1.0, info.duration)
        print(f"      -> Detected language: {info.language.upper()} (confidence: {info.language_probability:.2%})")
        print(f"      -> Audio duration: {format_timestamp_colons(total_duration)} ({total_duration:.1f}s)")
        print("      -> Streaming transcript progress:")

        for idx, seg in enumerate(segments):
            start_str = format_timestamp_colons(seg.start)
            end_str = format_timestamp_colons(seg.end)
            turn = {
                "id": idx,
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "timestamp": start_str,
                "channel": "Speaker",
                "text": seg.text.strip(),
            }
            all_turns.append(turn)
            text_lines.append(f"[{start_str} -> {end_str}] {seg.text.strip()}")

            pct = min(100.0, (seg.end / total_duration) * 100.0)
            bar_len = 22
            filled = int(bar_len * pct / 100.0)
            bar = "=" * filled + (">" if filled < bar_len else "") + "." * max(0, bar_len - filled - (1 if filled < bar_len else 0))
            text_snippet = seg.text.strip().replace("\n", " ")
            if len(text_snippet) > 42:
                text_snippet = text_snippet[:39] + "..."
            sys.stdout.write(f"\n      [{bar}] {pct:5.1f}% | #{idx+1:03d} [{start_str}] {text_snippet:<45}")
            sys.stdout.flush()

        sys.stdout.write("\n")

    elapsed = time.time() - t0

    # Save transcript.json
    json_path = bundle_dir / "transcript.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_turns, f, indent=2, ensure_ascii=False)

    # Save transcript.txt
    txt_path = bundle_dir / "transcript.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text_lines) + "\n")

    print(f"      -> Transcription complete in {elapsed:.1f}s: {len(all_turns)} speech turns captured.")
    if audio_files.get("is_multi_track"):
        print(f"         * Remote Speech Turns : {len(remote_turns)}")
        print(f"         * Host Speech Turns   : {len(host_turns)}")
    print(f"      -> Saved to transcript.json and transcript.txt\n")
    return all_turns


def extract_slide_frames(
    video_path: Path,
    slides_dir: Path,
    hwaccel: str | None = None,
    threads: int | None = None
) -> list[Path]:
    """Extract slide/screen change frames using scene detection (ADR-0001)."""
    print("      [Tier 1: Presentation Slides]")
    accel_str = f" | HWAccel: {hwaccel}" if hwaccel else ""
    thread_str = f" | Threads: {threads}" if threads else ""
    print(f"      -> Analyzing scene transitions with FFmpeg filter (gt(scene, 0.05)){accel_str}{thread_str}...")
    t0 = time.time()
    temp_pattern = slides_dir / "temp_slide_%04d.jpg"
    cmd = ["ffmpeg", "-y"]
    if hwaccel:
        cmd.extend(["-hwaccel", hwaccel])
    if threads and threads > 0:
        cmd.extend(["-threads", str(threads)])
    cmd.extend([
        "-i", str(video_path),
        "-vf", "select=eq(n\\,0)+gt(scene\\,0.05),showinfo",
        "-fps_mode", "vfr",
        str(temp_pattern)
    ])
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Graceful fallback: if hwaccel failed on unusual video encoding, retry with software
    if proc.returncode != 0 and hwaccel:
        print(f"      -> Note: HWAccel '{hwaccel}' encountered issue. Retrying with software decoder...")
        cmd_fallback = ["ffmpeg", "-y"]
        if threads and threads > 0:
            cmd_fallback.extend(["-threads", str(threads)])
        cmd_fallback.extend([
            "-i", str(video_path),
            "-vf", "select=eq(n\\,0)+gt(scene\\,0.05),showinfo",
            "-fps_mode", "vfr",
            str(temp_pattern)
        ])
        proc = subprocess.run(cmd_fallback, capture_output=True, text=True)

    pts_matches = re.findall(r"pts_time:([0-9\.]+)", proc.stderr)

    temp_files = sorted(slides_dir.glob("temp_slide_*.jpg"))
    renamed_files = []
    seen_timestamps = {}
    for idx, f in enumerate(temp_files):
        if idx < len(pts_matches):
            pts_float = float(pts_matches[idx])
            ts = format_timestamp(pts_float)
        else:
            ts = f"frame_{idx:04d}"

        count = seen_timestamps.get(ts, 0)
        seen_timestamps[ts] = count + 1
        suffix = f"_{count:02d}" if count > 0 else ""
        new_path = slides_dir / f"slide_{ts}{suffix}.jpg"

        if new_path.exists():
            try:
                new_path.unlink()
            except OSError:
                pass
        if f.exists():
            f.rename(new_path)
            renamed_files.append(new_path)

    # Clean up any leftover temporary files
    for leftover in slides_dir.glob("temp_slide_*.jpg"):
        try:
            leftover.unlink()
        except OSError:
            pass

    elapsed = time.time() - t0
    print(f"      -> Extracted {len(renamed_files)} slide transition frames in {elapsed:.1f}s.")
    return renamed_files


def extract_speaker_frames(
    video_path: Path,
    speakers_dir: Path,
    speech_turns: list[dict],
    max_workers: int = 3
) -> list[Path]:
    """Extract speaker snapshot at each speech turn onset to isolate active speaker indicators (ADR-0001)."""
    print("      [Tier 2: Speaker Keyframes]")
    candidates = []
    last_pts = None
    for turn in speech_turns:
        start_sec = turn["start"]
        # Deduplicate to sample approximately every 15+ seconds to prevent frame bloat
        if last_pts is None or (start_sec - last_pts >= 15.0):
            candidates.append(turn)
            last_pts = start_sec

    # Cap candidates to max 120 frames distributed across the session to scale to 4-hour meetings (ADR-0002)
    MAX_SPEAKER_FRAMES = 120
    if len(candidates) > MAX_SPEAKER_FRAMES:
        step = len(candidates) / MAX_SPEAKER_FRAMES
        candidates = [candidates[int(i * step)] for i in range(MAX_SPEAKER_FRAMES)]

    total_candidates = len(candidates)
    worker_info = f" | Concurrent Workers: {max_workers}" if max_workers > 1 else ""
    print(f"      -> Sampling speaker video tiles for {total_candidates} speech turn onsets{worker_info}...")
    t0 = time.time()
    extracted_frames = []

    def _extract_one(idx: int, turn: dict) -> tuple[int, Path | None]:
        start_sec = turn["start"]
        ts = format_timestamp(start_sec)
        frame_path = speakers_dir / f"speaker_{ts}.jpg"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(video_path),
            "-frames:v", "1",
            "-fps_mode", "vfr",
            str(frame_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and frame_path.is_file():
            return idx, frame_path
        return idx, None

    if max_workers > 1 and total_candidates > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_turn = {
                executor.submit(_extract_one, idx, turn): (idx, turn)
                for idx, turn in enumerate(candidates, 1)
            }
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_turn):
                completed_count += 1
                idx, frame_path = future.result()
                if frame_path:
                    extracted_frames.append(frame_path)
                pct = (completed_count / total_candidates) * 100.0
                sys.stdout.write(f"\n      -> Progress: [{completed_count}/{total_candidates}] ({pct:5.1f}%) | Workers Active: {max_workers}")
                sys.stdout.flush()
    else:
        for idx, turn in enumerate(candidates, 1):
            _, frame_path = _extract_one(idx, turn)
            if frame_path:
                extracted_frames.append(frame_path)
            pct = (idx / total_candidates) * 100.0
            sys.stdout.write(f"\n      -> Progress: [{idx}/{total_candidates}] ({pct:5.1f}%)")
            sys.stdout.flush()

    sys.stdout.write("\n")
    extracted_frames.sort(key=lambda p: p.name)
    elapsed = time.time() - t0
    print(f"      -> Extracted {len(extracted_frames)} speaker keyframes in {elapsed:.1f}s.\n")
    return extracted_frames


def extract_artifacts_parallel(
    session_video: Path,
    bundle_dir: Path,
    audio_files: dict,
    model_size: str,
    profile: dict,
    extract_1fps: bool = False,
    initial_prompt: str | None = None,
    hotwords: str | None = None
) -> list[dict]:
    """Execute Tier 1 visual extraction and audio transcription concurrently.
    Allocates distinct CPU cores and GPU media engines to prevent bottlenecks.
    """
    slides_dir = bundle_dir / "slides"
    speakers_dir = bundle_dir / "speakers"

    print("========================================================================")
    print("           CONCURRENT PIPELINE EXECUTION (HARDWARE-OPTIMIZED)")
    print("========================================================================")
    print(f" [*] CPU Logical Cores      : {profile['cpu_count']}")
    print(f" [*] Whisper CPU Threads    : {profile['whisper_threads']} (Allocated)")
    print(f" [*] FFmpeg Video Threads   : {profile['ffmpeg_threads']} (Allocated)")
    print(f" [*] Video HW Acceleration  : {profile['hwaccel'] or 'Software'}")
    print(f" [*] Speaker Worker Pool    : {profile['speaker_workers']} workers")
    print("========================================================================\n")

    t_parallel_start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # 1. Launch Tier 1 Slide Frame Extraction in background thread
        print("[Parallel Stage 1/2] Spawning Tier 1 Slide Extraction in background...")
        slide_future = executor.submit(
            extract_slide_frames,
            session_video,
            slides_dir,
            profile["hwaccel"],
            profile["ffmpeg_threads"]
        )

        # 2. Run Audio Transcription in parallel on allocated Whisper threads
        print("[Parallel Stage 1/2] Starting Speech Transcription on dedicated threads...")
        speech_turns = transcribe_audio(
            audio_files,
            bundle_dir,
            model_size=model_size,
            cpu_threads=profile["whisper_threads"],
            initial_prompt=initial_prompt,
            hotwords=hotwords
        )

    # 3. Transcription finished -> Start Tier 2 Speaker Keyframes concurrently
    print("[Parallel Stage 2/2] Transcription complete. Launching Tier 2 Speaker Keyframe extraction...")
    extract_speaker_frames(
        session_video,
        speakers_dir,
        speech_turns,
        max_workers=profile["speaker_workers"]
    )

    # 4. Wait for Tier 1 Slide Extraction future
    slide_frames = slide_future.result()
    print(f"      -> Tier 1 Slide Extraction confirmed ready ({len(slide_frames)} slides).")

    # 5. Optional 1fps extraction if requested
    if extract_1fps:
        extract_all_1fps_frames(session_video, bundle_dir)

    total_parallel_time = time.time() - t_parallel_start
    print(f"\n[+] Concurrent preprocessing completed in {total_parallel_time:.1f}s.\n")
    return speech_turns


def extract_all_1fps_frames(video_path: Path, bundle_dir: Path) -> None:
    """Optional: Extract all frames at 1 frame per second if explicitly requested."""
    all_dir = bundle_dir / "all_1fps"
    all_dir.mkdir(parents=True, exist_ok=True)
    print("[*] Extracting 1 fps frames into all_1fps/...")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", "fps=1",
        "-fps_mode", "vfr",
        str(all_dir / "frame_%04d.jpg")
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    print(f"[+] 1 fps extraction complete: {len(list(all_dir.glob('*.jpg')))} frames generated.")


def sanitize_mom_content(content: str) -> str:
    """Ensure strict silent omission by programmatically stripping any meta-commentary disclaimers or leakages."""
    if content.startswith("```markdown"):
        content = content[len("```markdown"):].strip()
    elif content.startswith("```"):
        content = content[len("```"):].strip()
    if content.endswith("```"):
        content = content[:-3].strip()

    cleaned_lines = []
    for line in content.splitlines():
        lower = line.lower().strip()
        # Check for meta-commentary exclusion notes or disclaimers
        if "note:" in lower and any(w in lower for w in ["excluded", "omitted", "standards", "pleasantries", "social", "non-technical", "unshared"]):
            continue
        if any(lower.startswith(prefix) for prefix in ["*(note:", "(note:", "- *(note:", "- (note:"]):
            continue
        # Check for internal slide frame audit lines
        if "slide_" in lower and any(w in lower for w in ["omitted", "excluded", "incidental", "unshared", "workstation"]):
            continue
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def invoke_antigravity(
    video_path: Path,
    bundle_dir: Path,
    output_dir: Path,
    speech_turns: list[dict] | None = None,
    client_glossary: dict | None = None,
    glossary_path: Path | None = None
) -> Path:
    """Invoke Antigravity CLI (agy) to synthesize the full Minutes of Meeting."""
    print("[5/5] SYNTHESIZING MINUTES OF MEETING (ANTIGRAVITY AGENT)")
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    clean_title = re.sub(r"[^\w\-]", "_", video_path.stem)
    mom_file = output_dir / f"{date_str}_{clean_title}.md"

    # Read transcript text
    txt_path = bundle_dir / "transcript.txt"
    transcript_content = txt_path.read_text(encoding="utf-8") if txt_path.is_file() else "No transcript available."
    word_count = len(transcript_content.split())

    # Detect multi-track channels if available
    if speech_turns is None and (bundle_dir / "transcript.json").is_file():
        try:
            with open(bundle_dir / "transcript.json", "r", encoding="utf-8") as f:
                speech_turns = json.load(f)
        except Exception:
            speech_turns = []

    is_multi_track = any(t.get("channel") in ("Host", "Remote Attendee") for t in (speech_turns or []))

    multi_track_instructions = ""
    if is_multi_track:
        multi_track_instructions = """
CRITICAL PRINCIPLE 3 - DETERMINISTIC MULTI-TRACK SPEAKER ATTRIBUTION:
- Isolated Physical Channels: The transcript contains deterministic physical audio channels:
  * `[Host]`: Utterances spoken into the local workstation microphone by the host/organizer.
  * `[Remote Attendee]`: Utterances spoken by remote participants over the video conference call.
- Speaker Disambiguation:
  * Deterministically attribute host commitments, remarks, and moderation to the host.
  * For `[Remote Attendee]` turns, correlate the turn timestamp with the corresponding images in "speakers/" (which capture the meeting window and active speaker tile at that exact second) to attribute each statement to specific attendees by name.
"""
        instruction_2 = "2. Cross-reference speaker keyframes in \"speakers/\" (especially the opening frames) to identify attendee names, roles, and match spoken statements to specific individuals. Use the [Host] vs [Remote Attendee] channel tags in the transcript for deterministic separation of host vs remote attendees."
    else:
        instruction_2 = "2. Cross-reference speaker keyframes in \"speakers/\" (especially the opening frames) to identify attendee names, roles, and match spoken statements to specific individuals."

    # Build client domain glossary prompt section if available
    glossary_prompt_section = ""
    if client_glossary and (client_glossary.get("terms") or client_glossary.get("hotwords")):
        display_name = client_glossary.get("display_name", "Client Domain")
        terms_lines = []
        for t in client_glossary.get("terms", []):
            if isinstance(t, dict) and t.get("canonical"):
                desc = f": {t['description']}" if t.get("description") else ""
                terms_lines.append(f"  * `{t['canonical']}`{desc}")
        terms_text = "\n".join(terms_lines) if terms_lines else "  * None listed"
        hotwords_list = client_glossary.get("hotwords", [])
        hotwords_text = f"\n  * Additional hotwords: {', '.join(hotwords_list)}" if hotwords_list else ""

        glossary_prompt_section = f"""
CLIENT DOMAIN GLOSSARY ({display_name}):
The following domain terms, acronyms, and product names are canonical for this meeting:
{terms_text}{hotwords_text}

CRITICAL TERMINOLOGY INSTRUCTIONS:
- Ground truth terminology: The raw audio transcript may contain acoustic variations, informal spellings, or phonetic mishearings (e.g. mishearing proprietary names or acronyms). Always resolve and standardize these spoken terms to the exact canonical terminology in this glossary.
- Never invent alternative spellings or acronym casings for canonical terms.
"""

    suggested_json_path = (bundle_dir / "suggested_terms.json").resolve().as_posix()
    instruction_8 = f"""8. DISCOVERY OF CANDIDATE CLIENT TERMINOLOGY:
   Identify any recurring client-specific acronyms, project names, or proprietary technical terms mentioned in the dialogue that are NOT listed in the CLIENT DOMAIN GLOSSARY.
   Write these candidate terms as a JSON array to the artifact bundle path:
   "{suggested_json_path}"
   Format:
   [
     {{"term": "NovelAcronym", "context": "Brief explanation of how it was used in context"}}
   ]
   (If none detected, write [] to that file).
   NEVER mention candidate terms, glossary files, or internal pipeline suggestions in the Minutes of Meeting document itself.
"""

    # List visual frames
    slides = [f.name for f in sorted((bundle_dir / "slides").glob("*.jpg"))]
    speakers = [f.name for f in sorted((bundle_dir / "speakers").glob("*.jpg"))]

    print("      -> Feeding Context Bundle:")
    print(f"         * Transcript: {len(transcript_content)} chars (~{word_count} words)")
    if is_multi_track:
        print("         * Speaker Channels: Deterministic Multi-Track (Host vs. Remote Attendees)")
    if client_glossary:
        display_name = client_glossary.get("display_name", "Client")
        print(f"         * Client Glossary: Active ({display_name})")
    print(f"         * Slide Frames: {len(slides)} transition images")
    print(f"         * Speaker Keyframes: {len(speakers)} utterance onset images")
    print(f"      -> Target MoM Document: {mom_file.name}")

    slides_summary = f"{len(slides)} transitions captured in {bundle_dir / 'slides'} (Sample: {', '.join(slides[:8])})" if slides else "None captured."
    speakers_summary = f"{len(speakers)} keyframes captured in {bundle_dir / 'speakers'} (Sample: {', '.join(speakers[:8])})" if speakers else "None captured."

    # Check transcript size to prevent exceeding OS command line limits
    if len(transcript_content) > 12000:
        transcript_prompt_section = (
            f"The complete audio transcript is saved at: \"{txt_path.resolve()}\"\n"
            "Please read this file using your file reading tools to ingest the full dialogue."
        )
    else:
        transcript_prompt_section = f"FULL AUDIO TRANSCRIPTION:\n{transcript_content}"

    prompt = f"""You are an executive scribe synthesizing the definitive Minutes of Meeting (MoM) from a recorded video session.

CRITICAL PRINCIPLE 1 - STRICT SILENT OMISSION & ZERO META-COMMENTARY:
- ABSOLUTE BAN ON EXCLUSION NOTES: NEVER write disclaimers, notes, parentheticals, or footnotes stating what was excluded or omitted.
  * FORBIDDEN: "*(Note: Per executive MoM standards, non-technical social pleasantries regarding regional weather in Jaipur/Noida and personal commute/motorcycle experiences have been excluded.)*"
  * FORBIDDEN: "*(Note: Non-shared local attendee workstation windows have been excluded.)*"
  * FORBIDDEN: Any sentence containing "excluded", "omitted", "social pleasantries", or "incidental".
  If something is not part of the meeting, it must be 100% INVISIBLE. Do not mention that it was excluded. Do not mention the topic or details of the excluded talk (weather, traffic, commute, motorcycles, weekends, personal life, room cabins, coffee, lunch, or background applications).
- NO PSEUDO-AGENDA CHAPTERS FOR CHAT OR SILENCE: NEVER create a section header or timestamp block (e.g. "Workspace Context & Team Operational Sync") for periods of casual chatter, personal talk, silence, or room logistics. Jump directly to the next substantive business/technical agenda discussion.
- NO FAKE ACTION ITEMS: Action items must strictly be business, product, or engineering deliverables agreed upon for the project. NEVER convert casual statements (e.g. "I'll go back to my desk", "I'll talk to folks in the bay", "heading to my cabin") into action items.

CRITICAL PRINCIPLE 2 - IN-MEETING SCREENSHARE VS. LOCAL WORKSTATION RECORDING:
- In Section 2 ("In-Meeting Screenshare & Presentation Highlights"):
  * If genuine slides, spreadsheets, or dashboards were presented and verbally discussed in the meeting call: document their content and data structure.
  * If NO screenshare or slide deck was presented in the meeting: simply write:
    "None. No application windows, slides, spreadsheets, or architectural diagrams were shared or presented during this session. The meeting was conducted via audio and attendee tiles."
  * NEVER describe the recording host's unshared local desktop (e.g. IDEs, background browser tabs, AI assistants, query tools).
  * NEVER list internal image filenames (e.g. `slide_00-24-24.jpg`) or explain why an image was ignored.
{multi_track_instructions}
{glossary_prompt_section}
MEETING RECORDING: "{video_path.name}"
DATE: {date_str}

AVAILABLE ARTIFACTS IN BUNDLE ({bundle_dir.resolve()}):
- Slide Transitions: {slides_summary}
- Speaker Keyframes: {speakers_summary}

{transcript_prompt_section}

YOUR INSTRUCTIONS:
1. Ground truth is the verbal meeting dialogue: Examine the transcript to understand all discussion points, debates, and decisions.
{instruction_2}
3. Cross-reference slide frames in "slides/" ONLY for materials that were shared and discussed in the meeting (e.g. presentation slides, reviewed spreadsheets). Silently ignore any incidental background windows or local desktop activity.
4. Capture FULL DISCUSSION CONTEXT without missing technical decisions, architectural debates, or project updates.
5. Apply STRICT SILENT OMISSION: Exclude all informal banter, pleasantries, weather talk, commute stories, personal plans, and unshared desktop activity with ZERO meta-commentary or disclaimers.
6. For lengthy or multi-hour sessions (up to 4+ hours): Organize the Comprehensive Discussion into thematic chapters or chronological session phases with timestamp markers (e.g. `[01:15:00]`), ensuring exhaustive technical capture across all topics without skipping any agenda sections.
7. Structure the document as follows:
   # Minutes of Meeting: {video_path.stem.replace('_', ' ').title()}
   - **Date**: {date_str}
   - **Recording File**: `{video_path.name}`
   - **Identified Attendees & Roles**: (List each person identified from speaker tiles/dialogue)

   ## 1. Executive Summary
   Concise summary of the meeting purpose, key milestones, and high-level outcomes.

   ## 2. In-Meeting Screenshare & Presentation Highlights
   Chronological breakdown of ONLY materials actively shared and discussed in the meeting, summarizing diagrams, metrics, or documents shown. (If none, write: "None. No application windows, slides, spreadsheets, or architectural diagrams were shared or presented during this session. The meeting was conducted via audio and attendee tiles.")

   ## 3. Comprehensive Discussion & Decisions
   Detailed topic-by-topic discussion breakdown preserving all technical, design, and operational details with speaker attributions. (Do NOT include sections for casual chatter or conversational wind-down).

   ## 4. Action Items
   | # | Action Item | Owner | Target Due Date | Context |
   |---|-------------|-------|-----------------|---------|

   ## 5. Open Questions & Parked Topics
   Any unresolved items or questions deferred to future sessions.

{instruction_8}
Return ONLY the complete Markdown document, without conversational filler before or after.
"""

    agy_cmd = [
        "agy",
        "--dangerously-skip-permissions",
        "--print-timeout", "30m0s",
        "--print",
        prompt
    ]

    print("      -> Invoking agy CLI (autonomous agent synthesis, up to 30m timeout)...")
    sys.stdout.flush()
    t0 = time.time()
    res = subprocess.run(agy_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0

    raw_content = res.stdout.strip()
    content = sanitize_mom_content(raw_content)

    if content:
        mom_file.write_text(content + "\n", encoding="utf-8")
        file_size_kb = mom_file.stat().st_size / 1024
        print(f"      -> Agent synthesis completed in {elapsed:.1f}s ({file_size_kb:.1f} KB written).")
        print(f"\n========================================================================")
        print(f"[SUCCESS] Minutes of Meeting generated successfully!")
        print(f"Location: {mom_file.resolve()}")
        print(f"========================================================================\n")

        # Check for suggested candidate terms in bundle
        suggested_file = bundle_dir / "suggested_terms.json"
        if suggested_file.is_file():
            try:
                with open(suggested_file, "r", encoding="utf-8") as f:
                    suggestions = json.load(f)
                if isinstance(suggestions, list) and len(suggestions) > 0:
                    print("========================================================================")
                    print("[*] Suggested Glossary Additions (Detected from meeting dialogue):")
                    for item in suggestions:
                        term = item.get("term", "")
                        ctx = item.get("context", "")
                        print(f"    - {term}: {ctx}")
                    target_hint = f"'{glossary_path.as_posix()}'" if glossary_path else "docs/clients/default.json"
                    print(f"\n    -> Easily add these to {target_hint} to improve future transcriptions.")
                    print("========================================================================\n")
            except Exception:
                pass
    else:
        print(f"[!] Warning: No output returned from agy. Stderr: {res.stderr}")

    return mom_file


def main():
    parser = argparse.ArgumentParser(description="Video Recording to Minutes of Meeting (MoM) Pipeline")
    parser.add_argument("video_paths", nargs="*", default=None, help=r"Paths or glob pattern to meeting video recordings (default: latest session in D:\OBS Captures)")
    parser.add_argument("--model", default="large-v3", choices=["tiny", "base", "small", "medium", "large", "large-v3"], help="Whisper model size (default: large-v3)")
    parser.add_argument("--recordings-dir", default=r"D:\OBS Captures", help=r"Directory containing recordings (default: D:\OBS Captures)")
    parser.add_argument("--bundle-dir", default=".bundle", help="Temporary working directory for artifacts (default: .bundle)")
    parser.add_argument("--output-dir", default="docs/mom", help="Output directory for final MoM (default: docs/mom)")
    parser.add_argument("--extract-1fps", action="store_true", help="Also extract all frames at 1 fps into all_1fps/")
    parser.add_argument("--reuse-transcript", action="store_true", help="Reuse existing transcript.json in bundle if available")
    parser.add_argument("--synthesis-only", action="store_true", help="Skip all extraction and only run Antigravity synthesis on current bundle")
    parser.add_argument("--skip-agent", action="store_true", help="Stop after preprocessing without invoking agy agent")
    parser.add_argument("--remote-track", type=int, default=2, help="OBS audio track number for remote attendees (default: 2, 1-indexed)")
    parser.add_argument("--host-track", type=int, default=3, help="OBS audio track number for local host mic (default: 3, 1-indexed)")
    parser.add_argument("--master-track", type=int, default=1, help="OBS audio track number for master mix (default: 1, 1-indexed)")
    parser.add_argument("--disable-multi-track", action="store_true", help="Force single-track audio extraction even if multiple tracks exist")
    parser.add_argument("--sequential", action="store_true", help="Force sequential extraction instead of parallel execution")
    parser.add_argument("--whisper-threads", type=int, default=None, help="Explicit CPU threads for faster-whisper (default: auto-budgeted)")
    parser.add_argument("--ffmpeg-threads", type=int, default=None, help="Explicit CPU threads for FFmpeg scene detection (default: auto-budgeted)")
    parser.add_argument("--speaker-workers", type=int, default=None, help="Concurrent worker threads for speaker frame extraction (default: auto-budgeted)")
    parser.add_argument("--hwaccel", default="auto", choices=["auto", "d3d11va", "dxva2", "qsv", "none"], help="FFmpeg video decode hardware acceleration (default: auto)")
    parser.add_argument("--client", default="default", help="Client glossary profile name in docs/clients/ (default: 'default')")
    parser.add_argument("--no-client", action="store_true", help="Disable client glossary loading and proceed with general vocabulary")
    parser.add_argument("--clients-dir", default="docs/clients", help="Directory containing client profiles (default: docs/clients)")

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    recordings_dir = Path(args.recordings_dir).resolve()
    bundle_dir = (project_root / args.bundle_dir).resolve()
    output_dir = (project_root / args.output_dir).resolve()
    clients_dir = (project_root / args.clients_dir).resolve()

    client_name = None if args.no_client else args.client
    client_glossary, glossary_path = load_client_glossary(client_name, clients_dir)
    whisper_initial_prompt, whisper_hotwords = build_whisper_biasing_params(client_glossary)

    profile = get_hardware_profile(
        custom_whisper_threads=args.whisper_threads,
        custom_ffmpeg_threads=args.ffmpeg_threads,
        custom_speaker_workers=args.speaker_workers,
        custom_hwaccel=args.hwaccel
    )

    video_paths = find_source_videos(args.video_paths, recordings_dir)
    total_size_mb = sum(p.stat().st_size for p in video_paths) / (1024 * 1024)
    total_duration_sec = sum(get_video_duration(p) for p in video_paths)

    print("\n========================================================================")
    print("                    MoM VIDEO PROCESSING PIPELINE")
    print("========================================================================")
    if len(video_paths) == 1:
        print(f" [SOURCE] Video File   : {video_paths[0]}")
    else:
        print(f" [SOURCE] Split Recording Session ({len(video_paths)} parts detected):")
        for idx, p in enumerate(video_paths, 1):
            dur = get_video_duration(p)
            sz = p.stat().st_size / (1024 * 1024)
            print(f"   {idx}. {p.name} ({sz:.1f} MB, {format_timestamp_colons(dur)})")
    print(f" [SIZE]   Total Size   : {total_size_mb:.2f} MB")
    print(f" [TIME]   Total Length : {format_timestamp_colons(total_duration_sec)} ({total_duration_sec:.1f}s)")
    print(f" [DIR]    Artifacts    : {bundle_dir}")
    print(f" [DEST]   MoM Output   : {output_dir}")
    print(f" [CLIENT] Glossary     : {glossary_path.name if glossary_path else 'None (Disabled)'}")
    print(f" [MODE]   Execution    : {'Sequential' if args.sequential else 'Parallel (Hardware-Optimized)'}")
    print("========================================================================\n")

    if args.synthesis_only:
        session_video = bundle_dir / "merged_session.mp4" if (bundle_dir / "merged_session.mp4").is_file() else video_paths[0]
        print("[*] --synthesis-only passed. Skipping all extraction and synthesizing MoM immediately...\n")
        invoke_antigravity(
            session_video,
            bundle_dir,
            output_dir,
            client_glossary=client_glossary,
            glossary_path=glossary_path
        )
        return

    slides_dir = bundle_dir / "slides"
    speakers_dir = bundle_dir / "speakers"

    # 1-4. Bundle, Audio, Transcription & Visual Extraction
    cached_transcript = bundle_dir / "transcript.json"
    if args.reuse_transcript and cached_transcript.is_file():
        print("[1/5] ARTIFACT BUNDLE: Reusing cached transcript and media (--reuse-transcript).\n")
        slides_dir.mkdir(parents=True, exist_ok=True)
        speakers_dir.mkdir(parents=True, exist_ok=True)
        session_video = bundle_dir / "merged_session.mp4" if (bundle_dir / "merged_session.mp4").is_file() else video_paths[0]
        print("[2/5] AUDIO EXTRACTION: Cached audio found.\n")
        print("[3/5] TRANSCRIPTION: Loading cached transcript.json...")
        with open(cached_transcript, "r", encoding="utf-8") as f:
            speech_turns = json.load(f)
        print(f"      -> Loaded {len(speech_turns)} speech turns from cache.\n")

        print("[4/5] EXTRACTING VISUAL ARTIFACTS (TWO-TIER)")
        if not args.sequential:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                slide_future = executor.submit(extract_slide_frames, session_video, slides_dir, profile["hwaccel"], profile["ffmpeg_threads"])
                extract_speaker_frames(session_video, speakers_dir, speech_turns, max_workers=profile["speaker_workers"])
                slide_future.result()
        else:
            extract_slide_frames(session_video, slides_dir, hwaccel=profile["hwaccel"], threads=profile["ffmpeg_threads"])
            extract_speaker_frames(session_video, speakers_dir, speech_turns, max_workers=1)

        if args.extract_1fps:
            extract_all_1fps_frames(session_video, bundle_dir)
    else:
        clean_bundle_directory(bundle_dir)
        session_video = merge_split_recordings(video_paths, bundle_dir)
        audio_tracks = get_audio_tracks_info(session_video)
        audio_files = extract_audio(
            session_video,
            bundle_dir,
            audio_tracks,
            remote_track=args.remote_track,
            host_track=args.host_track,
            master_track=args.master_track,
            disable_multi_track=args.disable_multi_track
        )

        if args.sequential:
            print("[*] Mode: Sequential Execution (--sequential passed).\n")
            speech_turns = transcribe_audio(
                audio_files,
                bundle_dir,
                model_size=args.model,
                cpu_threads=profile["whisper_threads"],
                initial_prompt=whisper_initial_prompt,
                hotwords=whisper_hotwords
            )
            print("[4/5] EXTRACTING VISUAL ARTIFACTS (TWO-TIER)")
            extract_slide_frames(session_video, slides_dir, hwaccel=profile["hwaccel"], threads=profile["ffmpeg_threads"])
            extract_speaker_frames(session_video, speakers_dir, speech_turns, max_workers=1)
            if args.extract_1fps:
                extract_all_1fps_frames(session_video, bundle_dir)
        else:
            speech_turns = extract_artifacts_parallel(
                session_video,
                bundle_dir,
                audio_files,
                model_size=args.model,
                profile=profile,
                extract_1fps=args.extract_1fps,
                initial_prompt=whisper_initial_prompt,
                hotwords=whisper_hotwords
            )

    print("----------------------- Preprocessing Summary -----------------------")
    print(f"Artifacts ready in: {bundle_dir}")
    print(f"  - Audio file        : audio.wav")
    print(f"  - Transcript files  : transcript.json, transcript.txt ({len(speech_turns)} speech turns)")
    print(f"  - Slide frames      : {len(list(slides_dir.glob('*.jpg')))} transition images")
    print(f"  - Speaker keyframes : {len(list(speakers_dir.glob('*.jpg')))} onset images")
    print("---------------------------------------------------------------------\n")

    # 5. Antigravity Agent Synthesis
    if args.skip_agent:
        print("[*] --skip-agent passed. Preprocessing complete. Skipping agent synthesis.")
    else:
        invoke_antigravity(
            session_video,
            bundle_dir,
            output_dir,
            speech_turns=speech_turns,
            client_glossary=client_glossary,
            glossary_path=glossary_path
        )


if __name__ == "__main__":
    main()
