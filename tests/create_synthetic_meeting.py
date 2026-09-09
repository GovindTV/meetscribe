import subprocess
import win32com.client
from pathlib import Path
from PIL import Image, ImageDraw

def create_single_part(output_video: Path, slides_data, speech_text):
    temp_dir = output_video.parent / f"temp_{output_video.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    slide_paths = []
    for i, (title, body, bg_color, speaker) in enumerate(slides_data, start=1):
        img = Image.new("RGB", (1280, 720), color=bg_color)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (1280, 100)], fill=(20, 20, 25))
        draw.text((40, 35), title, fill=(255, 255, 255))
        draw.text((60, 160), body, fill=(240, 240, 240))
        draw.rectangle([(980, 30), (1240, 190)], fill=(40, 40, 40), outline=(0, 255, 0), width=3)
        draw.text((1000, 100), f"Speaking:\n{speaker}", fill=(255, 255, 255))
        p = temp_dir / f"slide_{i}.png"
        img.save(p)
        slide_paths.append(p)

    wav_path = temp_dir / "speech.wav"
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(str(wav_path), 3, False)
    voice.AudioOutputStream = stream
    voice.Speak(speech_text)
    stream.Close()

    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)
    ]
    res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    duration = float(res.stdout.strip())
    slide_duration = duration / len(slide_paths)

    concat_file = temp_dir / "slides.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in slide_paths:
            f.write(f"file '{p.name}'\n")
            f.write(f"duration {slide_duration:.2f}\n")
        f.write(f"file '{slide_paths[-1].name}'\n")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(wav_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(output_video)
    ]
    subprocess.run(ffmpeg_cmd, cwd=str(temp_dir), check=True)
    print(f"[+] Created {output_video.name} ({duration:.1f}s)")

if __name__ == "__main__":
    recordings_dir = Path(r"d:\MoM\recordings")
    recordings_dir.mkdir(parents=True, exist_ok=True)

    part1 = recordings_dir / "synthetic_part1.mp4"
    slides1 = [
        ("Architecture Kickoff: Part 1", "Session 1:\n- Scalability review\n- Multi-hour handling\n- Lossless concatenation", (25, 45, 80), "Alice (Host)"),
        ("Technical Deep Dive", "Presenter: Alice\n- Microservice seam contracts\n- FFmpeg stream-copying pipeline", (30, 75, 45), "Alice (Host)")
    ]
    speech1 = "Hello team, welcome to part one of the architecture discussion. Alice is presenting the microservice roadmap."
    create_single_part(part1, slides1, speech1)

    part2 = recordings_dir / "synthetic_part2.mp4"
    slides2 = [
        ("Database & Operations: Part 2", "Session 2:\n- Migration timeline\n- Cutover plan", (75, 35, 35), "Bob (Data Lead)"),
        ("Final Action Items & Summary", "Action Items:\n- Bob: Complete DB migration by Friday\n- Charlie: Review code", (40, 40, 70), "Bob (Data Lead)")
    ]
    speech2 = "Welcome back to part two of our session. Bob will handle the database migration by Friday. Charlie will review pull requests."
    create_single_part(part2, slides2, speech2)
