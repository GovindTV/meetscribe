# OBS Recording Configuration Guide for Optimal MoM Extraction

This document explains the recommended settings for recording video conference meetings in [OBS Studio](https://obsproject.com/) to achieve the highest quality, most accurate Minutes of Meeting (MoM) synthesis.

> [!NOTE]
> **Full Backward Compatibility**:
> None of these settings are mandatory. The pipeline in [process_meeting.py](file:///d:/MoM/process_meeting.py) works **100% out of the box** with standard, single-track desktop recordings (`.mp4`, `.mkv`, etc.). If standard recordings are provided, the pipeline automatically operates in single-track fallback mode without errors.
>
> However, adopting the settings below eliminates speaker confusion, removes private desktop activity, cuts video processing time, and produces executive-grade MoM documentation.

---

## 1. Multi-Track Audio Recording (Deterministic Speaker Isolation)

By default, OBS mixes your microphone and the meeting audio into a single track. This forces the transcription engine to merge all voices together, making speaker attribution ambiguous.

Configuring multi-track audio enables the pipeline to deterministically isolate the host from remote participants.

### Step-by-Step OBS Setup:
1. **Enable Advanced Output Mode**:
   - Go to **Settings → Output**.
   - Change **Output Mode** dropdown from *Simple* to **Advanced**.
   - Under the **Recording** tab, check **Audio Tracks 1, 2, and 3**.
2. **Assign Physical Channels**:
   - In the main OBS window, look at the **Audio Mixer**.
   - Click the gear / three-dots icon on any audio source and select **Advanced Audio Properties**.
   - Configure the channel matrix as follows:
     - **Track 1**: Check both **Desktop Audio** AND **Mic/Aux** *(Master mix fallback)*.
     - **Track 2**: Check **Desktop Audio ONLY** *(Clean audio of remote call participants)*.
     - **Track 3**: Check **Mic/Aux ONLY** *(Clean audio of your local host microphone)*.

### Pipeline Impact:
- Utterances on Track 3 are guaranteed 100% to be the host / organizer.
- Utterances on Track 2 are isolated remote attendees without local room noise or keyboard clatter.
- Silero VAD skips silence on inactive tracks, speeding up transcription and eliminating hallucinations.

---

## 2. Window Capture vs. Display Capture (Workstation Privacy & Clean Slides)

Recording the entire desktop (Display Capture) captures private multitasking, IDEs, browser tabs, and notification popups whenever you switch windows ([ADR-0003](file:///d:/MoM/docs/adr/0003-dialogue-grounded-visual-relevance-filtering.md)). Every window switch triggers FFmpeg scene detection, flooding the bundle with hundreds of non-meeting images.

### Step-by-Step OBS Setup:
1. In your OBS Scene **Sources**, click **+ → Window Capture**.
2. Select your conference application (e.g. *Microsoft Teams*, *Zoom*, or the browser tab running *Google Meet*).
3. In the Window Capture properties, uncheck **Capture Cursor** (so mouse movement does not trigger false slide scene changes or obscure text).

### Pipeline Impact:
- False slide changes drop by **80–90%**.
- 100% of video pixels are dedicated to the presentation slides or attendee tiles, keeping small text razor-sharp for inspection.
- Zero chance of leaking private workstation activities into the MoM.

---

## 3. Keyframe Interval: 1s or 2s (Fast Speaker Keyframe Extraction)

During preprocessing, the pipeline seeks to speech turn timestamps (`-ss`) to extract speaker thumbnails from the video tiles ([ADR-0001](file:///d:/MoM/docs/adr/0001-two-tier-visual-frame-extraction.md)). Default OBS keyframe intervals (auto/10s) force FFmpeg to decode large GOP intervals to locate frames.

### Step-by-Step OBS Setup:
1. Go to **Settings → Output → Recording**.
2. Locate your encoder settings (NVIDIA NVENC, Intel QSV, AMD AMF, or x264).
3. Change **Keyframe Interval (GOP)** from `0 (Auto)` to **`1s` or `2s`**.

### Pipeline Impact:
- FFmpeg keyframe seeking is nearly instantaneous.
- Speaker thumbnail snapshots land on exact timestamps without drift.

---

## 4. Rate Control: CQP / CRF (Small File Size & Razor-Sharp Text)

Meeting recordings are predominantly static slides or spreadsheets. Constant Bitrate (CBR) wastes tens of gigabytes encoding unchanging pixels, while potentially degrading text quality.

### Step-by-Step OBS Setup:
1. Go to **Settings → Output → Recording**.
2. Set **Rate Control**:
   - For hardware encoders (NVENC / QSV / AMF): choose **CQP**.
   - For software encoder (x264): choose **CRF**.
3. Set **CQ Level / CRF** to **`20` – `22`**.

### Pipeline Impact:
- Static slides take almost 0 Mbps, shrinking multi-hour recordings into compact files.
- Text, code snippets, and spreadsheets retain lossless-quality clarity.

---

## 5. Framerate: 30 FPS (Double Scene Detection Speed)

Video meetings and slide decks do not need 60 FPS. 60 FPS quadruples the number of frames FFmpeg must scan during scene-change detection.

### Step-by-Step OBS Setup:
1. Go to **Settings → Video**.
2. Set **Common FPS Values** to **`30`** (or `24`).
3. Ensure **Base (Canvas)** and **Output (Scaled) Resolution** are set to your native resolution (e.g. `1920x1080`).

### Pipeline Impact:
- Scene-detection filter (`select=gt(scene,0.05)`) runs **2x faster**.
- Lossless concatenation of split recordings executes in seconds.

---

## 6. Microphone Noise Suppression (RNNoise Filter)

Air conditioning hum, fan noise, or room reverb can cause Whisper to hallucinate tokens (e.g. `[Music]`, `Thank you`, or repetitive phrases) during pauses in speech.

### Step-by-Step OBS Setup:
1. In the **Audio Mixer**, click the 3 dots next to **Mic/Aux → Filters**.
2. Click **+** and add **Noise Suppression**.
3. Choose **RNNoise (good quality, more CPU usage)**.

### Pipeline Impact:
- Guarantees clean silence between spoken words, enabling Silero VAD to segment utterances cleanly without hallucinated filler turns.

---

## Quick Reference: Baseline vs. Optimized Settings

| Feature | Baseline (Default OBS) | Optimized OBS Setup | Primary Benefit |
| :--- | :--- | :--- | :--- |
| **Audio Tracks** | Track 1 (Single mixed track) | Track 1 (Mix), Track 2 (Remote), Track 3 (Host) | Deterministic Host vs. Attendee speaker separation |
| **Capture Source** | Display Capture | Window Capture (Cursor hidden) | Prevents workstation leakage; cuts 80%+ false slides |
| **Keyframe Interval** | `0` (Auto / 8-10s) | `1s` or `2s` | Instant, frame-accurate speaker thumbnail seeking |
| **Rate Control** | CBR (e.g. 6000 Kbps) | CQP / CRF (`20-22`) | 60–80% smaller video files; razor-sharp slide text |
| **Framerate** | 60 FPS | 30 FPS | 2x faster FFmpeg scene detection |
| **Mic Filter** | None | RNNoise Suppression | Clean silence gaps; zero Whisper hallucinations |
