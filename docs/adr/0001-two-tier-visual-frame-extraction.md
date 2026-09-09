# Two-Tier Visual Frame Extraction for Meeting Artifacts

Meeting recordings require visual analysis for both shared slide comprehension and speaker attribution (webcam active-speaker indicators). Blind 1 fps extraction generates thousands of redundant images that overwhelm LLM context limits and disk storage, while pure slide scene-detection misses speaker shifts occurring during static slides. We decided to extract frames into two decoupled tiers: slide change frames via FFmpeg scene detection into `slides/`, and utterance keyframes sampled at the start timestamp of each transcript speech turn into `speakers/`. This bounds visual artifacts to ~80–150 relevant frames while preserving complete context.

## Considered Options

- **Blind 1 fps Extraction**: Produces 2,700–3,600 images per hour, overwhelming LLM context windows and wasting disk.
- **Slide Scene-Detection Only**: Fails to capture speaker webcam tile highlights when discussion continues over a static slide.
- **On-Demand FFmpeg Extraction via Agent**: Requires the agent to execute repeated video-slicing CLI commands during generation, slowing down the inference loop.

## Consequences

- The transcription stage must precede speaker frame extraction so utterance timestamps are known.
- Antigravity can reliably map speakers by cross-referencing speech turn timestamps against corresponding speaker frames.
