# Meeting Minutes (MoM) Pipeline 🎙️ ➡️ 📄

> **Turn your video meeting recordings into professional, executive-ready Minutes of Meeting automatically.**

This tool takes a recorded meeting video (from Zoom, Microsoft Teams, Google Meet, OBS, etc.), listens to the discussion, transcribes who said what, captures relevant presentation slides, and uses AI to write clean, structured meeting minutes with decisions and action items.

---

## 📑 Table of Contents
1. [Overview in Plain English](#-overview-in-plain-english)
2. [Prerequisites Checklist](#-prerequisites-checklist)
3. [Initial Setup (Do this once on a new PC)](#-initial-setup-do-this-once-on-a-new-pc)
   - [Step 1: Install Python](#step-1-install-python)
   - [Step 2: Install FFmpeg](#step-2-install-ffmpeg)
   - [Step 3: Install Antigravity (agy)](#step-3-install-antigravity-agy)
   - [Step 4: Install Required Packages](#step-4-install-required-packages)
   - [Quick Health Check](#quick-health-check)
4. [Everyday Use: Running Meetings](#-everyday-use-running-meetings)
   - [Method 1: The One-Click Way (Easiest)](#method-1-the-one-click-way-easiest)
   - [Method 2: Drag-and-Drop Any Video](#method-2-drag-and-drop-any-video)
   - [Method 3: Using the Command Prompt](#method-3-using-the-command-prompt)
5. [Where Are My Meeting Notes?](#-where-are-my-meeting-notes)
6. [Smart Features You Should Know About](#-smart-features-you-should-know-about)
7. [Choosing the Right Whisper Voice Model](#️-choosing-the-right-whisper-voice-model)
8. [Getting the Best Output Quality (OBS Guide)](#-getting-the-best-output-quality-obs-setup-guide)
9. [Helpful Everyday Tips](#-helpful-everyday-tips)
10. [Troubleshooting & Frequently Asked Questions](#-troubleshooting--frequently-asked-questions)

---

## 💡 Overview in Plain English

Instead of manually typing notes during meetings or spending an hour reviewing video recordings, this tool does the heavy lifting for you in 5 simple stages:

```
[ Your Video Recording ]
           │
           ▼
1. Extract clear audio
2. Transcribe voice to text (with timestamps)
3. Snapshot slides and active speakers
4. AI synthesis (Antigravity executive scribe)
           │
           ▼
[ Clean Minutes of Meeting (.md) in docs/mom/ ]
```

### What makes it special?
- **Zero Small Talk**: Social pleasantries (e.g. weather, traffic, coffee talk) are automatically excluded. Only genuine business, product, and technical discussions are included.
- **Privacy Protection**: If you recorded your whole screen, background windows (such as personal emails, browser tabs, or code editors) are ignored. Only slides and screenshares that participants verbally discussed are included.
- **Handles Split Recordings**: If OBS or your recorder split your meeting into two or more parts, it automatically stitches them together into one unified timeline.

---

## 📋 Prerequisites Checklist

Before you start, make sure you have:
- [x] A computer running **Windows 10** or **Windows 11**.
- [x] An active **Internet connection** (needed for the one-time installation).
- [x] Your **meeting video file** (e.g. `.mp4`, `.mkv`, `.mov`, `.webm`, or `.avi`).

---

## 🛠️ Initial Setup (Do this once on a new PC)

Follow these 4 simple steps to prepare your Windows computer. You only ever need to do this once!

### Step 1: Install Python

Python is the programming language that powers this tool.

1. Open your web browser and go to: **[https://www.python.org/downloads/](https://www.python.org/downloads/)**
2. Click the yellow **Download Python** button.
3. Open the downloaded installer file (e.g., `python-3.x.x-amd64.exe`).
4. ⚠️ **VERY IMPORTANT**: On the first screen of the installer, check the box at the very bottom that says:
   > ☑️ **Add python.exe to PATH**
   *(If you miss this checkbox, Windows will not be able to find Python!)*
5. Click **Install Now**.
6. When the setup completes, click **Close**.

---

### Step 2: Install FFmpeg

FFmpeg is a helper tool used to extract audio and take snapshots of slides from videos.

The easiest way to install it on Windows:
1. Press the **Windows Key** on your keyboard, type `PowerShell`, and click **Windows PowerShell** to open it.
2. Copy and paste the following command into the window, then press **Enter**:
   ```powershell
   winget install Gyan.FFmpeg
   ```
3. Type `Y` (Yes) if it asks for permission.
4. Wait for the installer to finish. Once done, close the PowerShell window.

---

### Step 3: Install Antigravity (`agy`)

Antigravity is the AI agent that reads the transcript and visual slides to write the executive Minutes of Meeting.

1. If you haven't already installed Antigravity, install the **Antigravity Desktop App / CLI**.
2. Open PowerShell or Command Prompt, type:
   ```powershell
   agy
   ```
   and press **Enter**.
3. If this is your first time, follow the on-screen prompt to log in and authorize your account.
4. Once logged in, you can close the window.

---

### Step 4: Install faster-whisper & the Voice Model

**faster-whisper** is the local AI engine that listens to your meeting audio and converts speech into accurate, timestamped text. It runs directly on your computer without sending your confidential audio to any external cloud service.

#### 1. Install the Python Package
1. Open File Explorer and navigate to this folder (`MoM`).
2. Click on the address bar at the top of the File Explorer window, type `cmd`, and press **Enter**. (This opens a black Command Prompt directly inside this folder).
3. Type or paste the following command and press **Enter**:
   ```cmd
   pip install -r requirements.txt
   ```
4. This installs `faster-whisper` and its helper libraries onto your system.

#### 2. How the AI Model is Downloaded
You don't need to manually hunt for AI files or copy models anywhere:
- **Automatic First-Run Download**: The first time you process a meeting, the tool automatically downloads the high-accuracy **`large-v3`** voice model (~1.5 GB).
- **Saved Locally for Offline Use**: The model is saved to your computer (`C:\Users\<YourUsername>\.cache\huggingface\hub\`). Future meeting runs start in 1–2 seconds and do **not** re-download it.
- **Works 100% Offline**: Once downloaded, speech transcription runs entirely on your own PC without needing an internet connection.

*(Optional)* **Want to pre-download the model now so your first meeting is instant?**
In your Command Prompt, simply run:
```cmd
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3')"
```
You will see a progress bar while it saves the model to your hard drive. Once it finishes, it's ready forever!

---

### ✅ Quick Health Check

Want to make sure everything is installed properly? Open a Command Prompt and type:

```cmd
python --version
ffmpeg -version
agy --version
```

If each command prints a version number without any error, **you are completely set up and ready to go!** 🎉

---

## 🚀 Everyday Use: Running Meetings

Once setup is complete, processing meetings is quick and simple. Pick whichever method you find easiest:

### Method 1: The One-Click Way (Easiest)

If you record meetings using OBS Studio and save them to `D:\OBS Captures` (the default setting):

1. Finish your meeting recording.
2. Open this `MoM` folder in File Explorer.
3. **Double-click `run_meeting.bat`**.

That's it! The tool will automatically locate your newest recording, process the audio and slides, and generate your meeting minutes.

---

### Method 2: Drag-and-Drop Any Video

If you have a video recording saved anywhere else (such as your Desktop, Downloads, or a Zoom folder):

1. Find your video file (e.g. `Client_Sync.mp4`).
2. **Drag the video file with your mouse and drop it directly on top of `run_meeting.bat`**.
3. The window will open and immediately start processing your file.

*(You can even select and drag multiple split video files together!)*

---

### Method 3: Using the Command Prompt

If you prefer typing commands or want to customize options:

1. Open Command Prompt in the `MoM` folder.
2. Run the script with your video path:
   ```cmd
   python process_meeting.py "C:\Users\YourName\Videos\Meeting.mp4"
   ```

3. To process multiple split files from the same session:
   ```cmd
   python process_meeting.py "recordings\part1.mp4" "recordings\part2.mp4"
   ```

---

### ⏳ What You Will See While It Runs

When the tool runs, you will see a progress monitor:

1. **[1/5] CLEANING ARTIFACT BUNDLE**: Cleans up previous temporary files.
2. **[2/5] EXTRACTING AUDIO**: Converts video audio into 16kHz crystal-clear sound.
3. **[3/5] TRANSCRIBING SPEECH**: Transcribes speech with a live progress bar showing spoken sentences:
   ```
   [==========>...........] 48.2% | #042 [00:12:15] Let's finalize the database schema...
   ```
4. **[4/5] EXTRACTING VISUAL ARTIFACTS**: Captures slides when the screen changes and snapshots active speaker video tiles.
5. **[5/5] SYNTHESIZING MINUTES OF MEETING**: Antigravity writes the complete document.

When finished, it displays:
```
========================================================================
[SUCCESS] Minutes of Meeting generated successfully!
Location: D:\MoM\docs\mom\2026-09-09_MyMeeting.md
========================================================================
```

---

## 📂 Where Are My Meeting Notes?

All finished meeting minutes are saved in the **`docs/mom/`** folder:

```
MoM/
 └── docs/
      └── mom/
           ├── 2026-09-08_Team_Sync.md
           └── 2026-09-09_Project_Kickoff.md
```

### How to use your generated document:
- **Double-click** the file to view it in your favorite Markdown editor, VS Code, or Notepad.
- **Copy and Paste**: Open the file in Notepad, press `Ctrl+A` to select all, `Ctrl+C` to copy, and paste it directly into an email, Slack channel, Google Doc, or Microsoft Word.
- **What's inside each document**:
  - **Date & Recording Details**: Source file and date.
  - **Attendees & Roles**: Automatically identified participants.
  - **Executive Summary**: High-level overview of the meeting outcomes.
  - **Screenshare & Presentation Highlights**: Summary of slides or documents presented.
  - **Comprehensive Discussion & Decisions**: Chronological breakdown with timestamps and speaker attributions.
  - **Action Items Table**: A clear table of tasks, owners, and due dates.
  - **Open Questions & Parked Topics**: Items left open for future discussions.

---

## 🧠 Smart Features You Should Know About

- **Automatic Split File Merging**:
  If a recording software breaks your recording into multiple files (e.g. `recording_01.mp4`, `recording_02.mp4`) because of file size or pausing, you do not need to stitch them manually with video editing software. The pipeline merges them seamlessly without quality loss.

- **Strict Silent Omission**:
  Personal conversations, chit-chat about lunch, weekends, commute, or weather are completely left out. The document contains **zero disclaimers** (it won't say "social chatter was excluded"—it simply focuses 100% on work).

- **Dialogue-Grounded Visuals**:
  If you were multitasking during the call (e.g. checking an email or browser window), that private activity will **never** be documented. Only screens that were actively shared and talked about during the call are captured.

---

## 🎙️ Choosing the Right Whisper Voice Model

By default, the pipeline uses the **`large-v3`** model, which provides state-of-the-art accuracy, handles diverse accents, technical jargon, and overlapping speakers exceptionally well. Depending on your PC and needs, you can choose a different model using the `--model` setting:

| Model Size | Download Size | RAM Needed | Speed | Best Used For | Command Example |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`large-v3`** *(Default)* | ~1.5 GB | ~4.0 GB | 🚀 Balanced | Maximum accuracy, technical discussions, multi-speaker syncs | `python process_meeting.py` *(or `run_meeting.bat`)* |
| **`medium`** | ~1.5 GB | ~3.5 GB | 🏎️ Moderate | High accuracy alternative | `python process_meeting.py --model medium` |
| **`small`** | ~480 MB | ~2.0 GB | ⚡ Fast | Good accuracy on moderate hardware | `python process_meeting.py --model small` |
| **`base`** | ~145 MB | ~1.0 GB | ⚡ Very Fast | Faster processing on older laptops or budget machines | `python process_meeting.py --model base` |
| **`tiny`** | ~75 MB | ~0.5 GB | ⚡⚡ Fastest | Ultra-fast drafts and quick tests | `python process_meeting.py --model tiny` |

> 💡 **Note**: The model downloads **once** automatically the first time you run it, and remains saved on your PC for offline use forever.

---

## 🎬 Getting the Best Output Quality (OBS Setup Guide)

> **Good News**: You do not need to change any settings if you don't want to! The pipeline works **100% out of the box** with standard, single-track video recordings (`.mp4`, `.mkv`, Zoom/Teams recordings, etc.).

If you record your meetings using **OBS Studio**, you can optionally configure a few recommended settings to unlock **studio-grade accuracy**:

1. **Multi-Track Audio (Speaker Isolation)**: Captures your microphone and the meeting call on separate audio tracks. The pipeline deterministically knows who spoke (Host vs. Remote Attendees) with zero guesswork.
2. **Window Capture**: Records just the Teams/Zoom/Meet window instead of your entire desktop. This completely protects your workstation privacy and eliminates 80%+ of false slide detections.
3. **Keyframe Interval (1s or 2s)**: Makes speaker video tile seeking virtually instantaneous.
4. **CQP / CRF Rate Control & 30 FPS**: Shrinks multi-hour video files by 60–80% while keeping presentation slides razor-sharp.
5. **RNNoise Mic Filter**: Removes background noise and fan hum so Whisper produces clean transcripts without hallucinations during pauses.

👉 **For step-by-step instructions with exact screenshots and settings, read the [OBS Recording Configuration Guide](docs/obs_recording_guide.md).**

---

## 💡 Helpful Everyday Tips

| Goal | How to do it |
| :--- | :--- |
| **Make transcription run faster on older PCs** | Add `--model base` or `--model tiny`:<br>`python process_meeting.py --model base` |
| **Force sequential mode (if debugging)** | Add `--sequential`:<br>`python process_meeting.py --sequential` |
| **Custom CPU thread allocation** | Customize Whisper or FFmpeg threads:<br>`python process_meeting.py --whisper-threads 4 --ffmpeg-threads 2` |
| **Change the recordings folder** | If your videos are in a different folder:<br>`python process_meeting.py --recordings-dir "C:\MyRecordings"` |
| **Re-run AI summary without waiting to transcribe again** | If you already transcribed a video and just want to re-generate the notes:<br>`python process_meeting.py --reuse-transcript` |
| **Only run the AI step** | Skip all media cutting and jump straight to writing:<br>`python process_meeting.py --synthesis-only` |

---

## ❓ Troubleshooting & Frequently Asked Questions

### 1. "python is not recognized as an internal or external command"
- **Why**: Python was installed without checking the "Add to PATH" box.
- **Fix**: Re-download the Python installer from [python.org](https://www.python.org/downloads/). Run the installer, select **Modify**, and make sure **Add Python to PATH** is checked. Then restart your command prompt.

### 2. "ffmpeg is not recognized"
- **Why**: FFmpeg is not installed or the terminal has not refreshed its environment paths.
- **Fix**: Open PowerShell as Administrator and run:
  ```powershell
  winget install Gyan.FFmpeg
  ```
  Close all open command prompts and reopen them.

### 3. "agy is not recognized"
- **Why**: The Antigravity CLI has not been added to your system path.
- **Fix**: Check that Antigravity is installed. Ensure `C:\Users\<YourUsername>\AppData\Local\agy\bin` is in your Windows User PATH, or launch the Antigravity desktop app.

### 4. "The batch window opens and closes in one second"
- **Fix**: Always run via `run_meeting.bat`—it includes a pause at the end so error messages remain visible. If it closes instantly, open Command Prompt (`cmd`) and run `run_meeting.bat` manually to see the exact error.

### 5. "Why did the first meeting run pause on 'Initializing Whisper'?"
- **Why**: On your very first run, `faster-whisper` automatically downloads the high-accuracy `large-v3` voice model (~1.5 GB).
- **Fix**: No action needed! It only downloads once. Future meetings will load the model in 1–2 seconds.

### 6. "DLL load failed while importing _ext or ctranslate2"
- **Why**: A brand-new Windows installation might lack the Microsoft Visual C++ runtime.
- **Fix**: Open PowerShell and run:
  ```powershell
  winget install Microsoft.VCRedist.2015+.x64
  ```
  Or download it directly from Microsoft: [Visual C++ 2015-2022 Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).

### 7. "How long does a 1-hour meeting take to process?"
- On an average laptop or desktop, transcribing a 1-hour meeting and generating the full minutes takes approximately **2 to 5 minutes**.

### 8. "Where does all the temporary storage go?"
- The pipeline stores temporary audio and pictures in the `.bundle` folder. Every time you run a new meeting, this folder is automatically cleaned out, so it will never clutter or fill up your hard drive.

---

*Need more technical architecture details? Check out [CONTEXT.md](file:///d:/MoM/CONTEXT.md) and the decision records in [docs/adr/](file:///d:/MoM/docs/adr/).*
