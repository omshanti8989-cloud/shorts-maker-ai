import os
import re
import glob
import subprocess
import yt_dlp

from tkinter import Tk, filedialog
from faster_whisper import WhisperModel


# ==================================================
# 1. CREATE PROJECT FOLDERS
# ==================================================

for folder in ["downloads", "clips", "subtitles", "fonts"]:
    os.makedirs(folder, exist_ok=True)


# ==================================================
# 2. SELECT VIDEO SOURCE
# ==================================================

print("\n========== SHORTS MAKER ==========")
print("1. YouTube video or livestream link")
print("2. Browse video from laptop")

choice = input("\nChoose option (1 or 2): ").strip()

if choice == "1":

    VIDEO_URL = input("\nPaste YouTube video link: ").strip()

    if not VIDEO_URL:
        raise SystemExit("No YouTube link entered.")

    print("\nDownloading video...")

    options = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "outtmpl": "downloads/video.%(ext)s",
        "merge_output_format": "mp4",
        "overwrites": True,
        "nopart": True,
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([VIDEO_URL])

    video_files = [
        f for f in glob.glob("downloads/video.*")
        if not f.endswith((".part", ".ytdl"))
    ]

    if not video_files:
        raise SystemExit("Downloaded video was not found.")

    video = next(
        (f for f in video_files if f.lower().endswith(".mp4")),
        video_files[0]
    )

elif choice == "2":

    print("\nOpening video browser...")

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    video = filedialog.askopenfilename(
        title="Select a video",
        filetypes=[
            ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),
            ("All files", "*.*")
        ]
    )

    root.destroy()

    if not video:
        raise SystemExit("No video selected.")

    video = os.path.abspath(video)

else:
    raise SystemExit("Invalid choice. Please select 1 or 2.")

print("\nSelected video:", video)


# ==================================================
# 3. LOAD WHISPER MEDIUM
# ==================================================

print("\nLoading AI speech recognition model...")

model = WhisperModel(
    "medium",
    device="cpu",
    compute_type="int8"
)

print("\nAnalyzing video...")

segments, info = model.transcribe(
    video,
    word_timestamps=True,
    beam_size=5,
    vad_filter=True,
    condition_on_previous_text=True
)

segments = list(segments)

print("\nTranscription completed!")
print("Detected language:", info.language)


# ==================================================
# 4. SAVE FULL TRANSCRIPT
# ==================================================

with open("transcript.txt", "w", encoding="utf-8") as file:
    for segment in segments:
        file.write(
            f"{segment.start:.2f} - {segment.end:.2f}: "
            f"{segment.text}\n"
        )

print("Transcript saved as transcript.txt")


# ==================================================
# 5. PREPARE WORD DATA
# ==================================================

all_words = []

for segment in segments:

    if not segment.words:
        continue

    for word in segment.words:

        word_text = word.word.strip()

        if not word_text:
            continue

        all_words.append({
            "start": word.start,
            "end": word.end,
            "text": word_text
        })

if not all_words:
    raise SystemExit("No words detected in the video.")


# ==================================================
# 6. AUTOMATIC HIGHLIGHT SELECTION
# ==================================================

print("\nFinding potential highlights...")

hook_words = [
    "secret", "amazing", "shocking", "surprising",
    "mistake", "important", "incredible", "unbelievable",
    "never", "always", "truth", "why", "how",
    "best", "worst", "dangerous", "finally",
    "actually", "imagine", "remember", "discover"
]

candidates = []

for segment in segments:

    start = segment.start
    end = start + 45

    selected = [
        s for s in segments
        if s.start >= start and s.end <= end
    ]

    if not selected:
        continue

    actual_end = selected[-1].end
    duration = actual_end - start

    if duration < 25 or duration > 60:
        continue

    text = " ".join(
        s.text for s in selected
    ).lower()

    score = sum(
        len(
            re.findall(
                r"\b" + re.escape(word) + r"\b",
                text
            )
        )
        for word in hook_words
    )

    score += text.count("?") * 2
    score += text.count("!") * 2

    candidates.append(
        (score, start, actual_end, text)
    )

candidates.sort(
    reverse=True,
    key=lambda x: x[0]
)


# ==================================================
# 7. ASK NUMBER OF SHORTS
# ==================================================

number_of_shorts = input(
    "\nHow many Shorts do you want? (Default 5): "
).strip()

try:
    number_of_shorts = (
        int(number_of_shorts)
        if number_of_shorts
        else 5
    )

    if number_of_shorts < 1:
        raise ValueError

except ValueError:
    raise SystemExit("Enter a valid number greater than zero.")


# ==================================================
# 8. SELECT NON-OVERLAPPING CLIPS
# ==================================================

best_clips = []

for score, start, end, text in candidates:

    if all(
        end <= old_start or start >= old_end
        for old_start, old_end in best_clips
    ):
        best_clips.append((start, end))

    if len(best_clips) >= number_of_shorts:
        break

if not best_clips:
    raise SystemExit("No suitable clips found.")

print("\nSelected potential highlights:")

for i, (start, end) in enumerate(best_clips, 1):
    print(f"Clip {i}: {start:.1f}s - {end:.1f}s")


# ==================================================
# 9. CREATE ANIMATED CAPTIONS
# ==================================================

def ass_time(seconds):

    total = round(seconds * 100)

    hours = total // 360000
    minutes = (total % 360000) // 6000
    secs = (total % 6000) // 100
    centiseconds = total % 100

    return (
        f"{hours}:{minutes:02}:"
        f"{secs:02}.{centiseconds:02}"
    )


def create_animated_captions(words, output_file):

    header = """[Script Info]
Title: Shorts Maker Animated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Noto Sans Devanagari,81,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,1,4,2,5,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    group_size = 4

    for i in range(0, len(words), group_size):

        group = words[i:i + group_size]

        for active_index, active_word in enumerate(group):

            start = active_word["start"]
            end = active_word["end"]

            if end <= start:
                continue

            caption_parts = []

            for j, item in enumerate(group):

                safe_word = re.sub(
                    r"[{}\\]",
                    "",
                    item["text"]
                )

                if j == active_index:

                    caption_parts.append(
                        r"{\c&H0000FFFF&\fscx115\fscy115"
                        r"\t(0,120,\fscx100\fscy100)}"
                        + safe_word
                        + r"{\c&H00FFFFFF&}"
                    )

                else:
                    caption_parts.append(safe_word)

            caption = " ".join(caption_parts)

            events.append(
                f"Dialogue: 0,"
                f"{ass_time(start)},"
                f"{ass_time(end)},"
                f"Pop,,0,0,0,,"
                f"{{\\an5\\pos(540,960)}}{caption}"
            )

    with open(
        output_file,
        "w",
        encoding="utf-8-sig"
    ) as file:

        file.write(header)
        file.write("\n".join(events))

    print("Animated captions created:", output_file)


# ==================================================
# 10. CLEAN OLD GENERATED OUTPUTS
# ==================================================

for pattern in [
    "clips/clip_*.mp4",
    "clips/vertical_clip_*.mp4",
    "subtitles/clip_*.ass",
    "subtitles/clip_*.srt"
]:

    for old_file in glob.glob(pattern):
        os.remove(old_file)


# ==================================================
# 11. CREATE CLIPS AND CAPTIONS
# ==================================================

def srt_time(seconds):

    milliseconds = round(seconds * 1000)

    hours = milliseconds // 3600000
    minutes = (milliseconds % 3600000) // 60000
    seconds_part = (milliseconds % 60000) // 1000
    ms = milliseconds % 1000

    return (
        f"{hours:02}:{minutes:02}:"
        f"{seconds_part:02},{ms:03}"
    )


for i, (start, end) in enumerate(best_clips, 1):

    print(f"\nCreating clip {i}...")

    clip_path = f"clips/clip_{i}.mp4"

    subprocess.run([
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", video,
        "-t", str(end - start),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        clip_path
    ], check=True)

    clip_words = []

    for word in all_words:

        if word["start"] >= start and word["end"] <= end:

            clip_words.append({
                "start": word["start"] - start,
                "end": word["end"] - start,
                "text": word["text"]
            })

    # Save normal SRT backup.

    with open(
        f"subtitles/clip_{i}.srt",
        "w",
        encoding="utf-8"
    ) as subtitle_file:

        for number, word in enumerate(clip_words, 1):

            subtitle_file.write(
                f"{number}\n"
                f"{srt_time(word['start'])} --> "
                f"{srt_time(word['end'])}\n"
                f"{word['text']}\n\n"
            )

    # Save animated ASS captions.

    create_animated_captions(
        clip_words,
        f"subtitles/clip_{i}.ass"
    )

    print(f"Clip {i} completed!")


# ==================================================
# 12. CREATE VERTICAL VIDEOS
# ==================================================

def make_vertical_video(
    input_video,
    output_video,
    subtitle_file
):

    font_folder = os.path.abspath(
        "fonts"
    ).replace("\\", "/")

    subtitle_path = os.path.abspath(
        subtitle_file
    ).replace("\\", "/")

    font_folder = font_folder.replace(":", r"\:")
    subtitle_path = subtitle_path.replace(":", r"\:")

    video_filter = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"ass='{subtitle_path}':"
        f"fontsdir='{font_folder}'"
    )

    subprocess.run([
        "ffmpeg",
        "-y",
        "-i", input_video,
        "-vf", video_filter,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        output_video
    ], check=True)


# ==================================================
# 13. PROCESS ALL VERTICAL VIDEOS
# ==================================================

print("\nCreating vertical Shorts...")

for i in range(1, len(best_clips) + 1):

    input_path = f"clips/clip_{i}.mp4"
    output_path = f"clips/vertical_clip_{i}.mp4"
    subtitle_path = f"subtitles/clip_{i}.ass"

    print("\nConverting:", input_path)

    make_vertical_video(
        input_path,
        output_path,
        subtitle_path
    )

    print("Vertical video completed:", output_path)


# ==================================================
# 14. FINISHED
# ==================================================

print("\n================================")
print("ALL SHORTS CREATED!")
print("================================")

print("\nFinished videos:")
print("C:\\shorts-maker\\clips")

print("\nAnimated captions:")
print("C:\\shorts-maker\\subtitles")