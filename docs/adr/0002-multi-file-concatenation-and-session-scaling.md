# Multi-File Concatenation and Long-Session Scaling

Meeting recordings can be split across multiple sequential files by recording software like OBS (due to file size limits, auto-split rules, or connection pauses) and may extend up to 4+ hours. We decided to concatenate multi-part recordings losslessly via FFmpeg stream-copying (`-c copy`) into a unified `Session Timeline` prior to media extraction, and bound speaker keyframe sampling to an adaptive maximum of 120 frames with an extended 30-minute agent synthesis timeout.

## Considered Options

- **Independent Per-File Processing with MoM Stitching**: Transcribing each part separately and attempting to merge sub-summaries. Rejected because it fragments discussion continuity, duplicates attendee introductions, and makes cross-segment topic tracking inaccurate.
- **Transcode Re-Encoding at Merge**: Re-encoding video parts when merging. Rejected because stream-copy demuxing (`-c copy`) achieves lossless concatenation in seconds without quality loss or heavy CPU overhead.
- **Unbounded 1 fps or Frequent Speaker Extraction**: Naive frame sampling over 4 hours yields 4,000–14,400 images, causing disk exhaustion and context window overflow. Rejected in favor of adaptive 15s+ sampling capped at 120 frames.

## Consequences

- All downstream stages (audio extraction, Whisper transcription, scene changes, speaker keyframes) operate on a single, continuous timeline.
- Timestamps across the transcript, slides, and MoM remain chronological and accurate across all split parts.
- Multi-hour meetings can be processed reliably within memory and context limits.
