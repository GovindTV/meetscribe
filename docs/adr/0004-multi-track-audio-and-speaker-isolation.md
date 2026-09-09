# Multi-Track Audio Extraction and Speaker Channel Isolation

Standard video meeting recordings mix local microphone input (the host) and remote conference audio (external participants) into a single audio track. This single mixed channel obscures speaker identity, making speaker attribution ambiguous and vulnerable to transcription inaccuracies caused by local acoustic noise, keyboard typing, or mic level discrepancies. We decided to configure and support OBS multi-track recording (Track 1: Master Mix, Track 2: Remote Attendees, Track 3: Local Host Mic), demuxing audio tracks with FFmpeg and running VAD-filtered Faster-Whisper transcription on each channel independently prior to chronological merging.

## Considered Options

- **Single-Track Mixed Audio Transcription**: Audio from all participants and local room noise is recorded into a single stream. The agent must guess who spoke solely based on conversational cues or visual video tiles. Rejected because it produces speaker misattributions and confuses host commitments with client requests.
- **Post-Hoc Neural Diarization (e.g. PyAnnote)**: Running heavy neural speaker diarization on a mixed mono track. Rejected due to significant CPU/GPU compute overhead, non-deterministic clustering errors, and failure on simultaneous cross-talk.
- **Physical Multi-Track Demuxing & Channel Isolation**: Recording desktop conference audio and host microphone onto dedicated OBS tracks. FFmpeg extracts clean channels (`audio_remote.wav` and `audio_host.wav`), Faster-Whisper transcribes each with Silero VAD suppression, and utterances are merged chronologically with `[Host]` and `[Remote Attendee]` tags.

## Consequences

- The pipeline deterministically distinguishes between the host and remote attendees without relying on heuristic speaker guessing.
- Silero VAD prevents Whisper hallucinations during long silent periods on isolated channels (e.g., when the host is listening to a presentation).
- Lossless split-recording concatenation must preserve all streams using FFmpeg `-map 0`.
- Videos with only a single audio track remain fully supported via automatic fallback.
