import os
import re
import glob
import subprocess
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

def process_video(video, number_of_shorts=5, progress_callback=None):

def report(message, progress=None):
    if progress_callback:
        progress_callback(message, progress)

project_dir = Path(__file__).resolve().parent
os.chdir(project_dir)

for folder in ["downloads", "clips", "subtitles", "fonts"]:
    Path(folder).mkdir(exist_ok=True)

video = str(Path(video).resolve())

if not os.path.isfile(video):
    raise FileNotFoundError(f"Video file not found: {video}")

# Load Whisper model
report("Loading Whisper AI model...", 0.03)

model = WhisperModel(
    "tiny",
    device="cpu",
    compute_type="int8",
    cpu_threads=2,
    num_workers=1,
)

# Transcription
report("Transcribing video...", 0.08)

segments, info = model.transcribe(
    video,
    word_timestamps=True,
    beam_size=1,
    vad_filter=True,
    condition_on_previous_text=True
)

segments = list(segments)

report(
    f"Transcription completed. Language: {info.language}",
    0.55
)

with open("transcript.txt", "w", encoding="utf-8") as file:
    for segment in segments:
        file.write(
            f"{segment.start:.2f} - {segment.end:.2f}: "
            f"{segment.text}\n"
        )

all_words = []

for segment in segments:
    if not segment.words:
        continue

    for word in segment.words:
        word_text = word.word.strip()

        if word_text:
            all_words.append({
                "start": word.start,
                "end": word.end,
                "text": word_text
            })

if not all_words:
    raise RuntimeError("No words detected in video.")

# AI Viral Moment Detection
report("AI analyzing viral moments...", 0.58)

hook_words = [
    "secret", "amazing", "shocking", "surprising",
    "mistake", "important", "incredible", "unbelievable",
    "never", "always", "truth", "why", "how",
    "best", "worst", "dangerous", "finally",
    "actually", "imagine", "remember", "discover",
    "love", "hate", "crazy", "impossible",
    "money", "free", "powerful", "because",
    "problem", "solution", "learn", "success",
    "believe", "wrong", "right", "secretly",
    "amazing", "real", "honestly", "mistakes"
]

candidates = []

# Generate candidate clips
for segment in segments:

    start = segment.start
    window_end = start + 45

    selected = [
        s for s in segments
        if s.start < window_end and s.end > start
    ]

    if not selected:
        continue

    actual_end = min(
        window_end,
        max(s.end for s in selected)
    )

    duration = actual_end - start

    if duration < 20 or duration > 60:
        continue

    text = " ".join(
        s.text for s in selected
    ).lower()

    words = text.split()

    if len(words) < 25:
        continue

    score = 0

    # Hook detection
    for hook in hook_words:
        count = len(
            re.findall(
                r"\b" + re.escape(hook) + r"\b",
                text
            )
        )

        score += min(count, 3) * 3

    # Questions and excitement
    score += text.count("?") * 3
    score += text.count("!") * 3

    # Speech density
    speech_density = len(words) / max(duration, 1)

    score += min(speech_density * 2, 10)

    # Clip length bonus
    if duration >= 30:
        score += 5

    # Storytelling indicators
    if any(
        phrase in text
        for phrase in [
            "the reason",
            "what happened",
            "let me explain",
            "you know what",
            "the truth is",
            "here is why",
            "the problem is"
        ]
    ):
        score += 8

    candidates.append({
        "score": min(round(score), 100),
        "start": start,
        "end": actual_end,
        "text": text
    })

# Rank clips by engagement score
candidates.sort(
    key=lambda x: x["score"],
    reverse=True
)

best_clips = []

for candidate in candidates:

    start = candidate["start"]
    end = candidate["end"]

    # Avoid overlapping clips
    overlap = any(
        start < old_end and end > old_start
        for old_start, old_end in best_clips
    )

    if not overlap:
        best_clips.append((start, end))

    if len(best_clips) >= int(number_of_shorts):
        break

if not best_clips:
    raise RuntimeError(
        "No suitable highlights found. "
        "Try a longer video containing more speech."
    )

report(
    f"Selected {len(best_clips)} AI-ranked highlights.",
    0.62
)

# Subtitle timestamp
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

# Animated captions
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
                f"Dialogue: 0,{ass_time(start)},"
                f"{ass_time(end)},Pop,,0,0,0,,"
                f"{{\\an5\\pos(540,960)}}{caption}"
            )

    with open(
        output_file,
        "w",
        encoding="utf-8-sig"
    ) as file:

        file.write(header)
        file.write("\n".join(events))

# Clean previous clips
for pattern in [
    "clips/clip_*.mp4",
    "clips/vertical_clip_*.mp4",
    "subtitles/clip_*.ass",
    "subtitles/clip_*.srt"
]:

    for old_file in glob.glob(pattern):
        os.remove(old_file)

# Create horizontal clips and subtitles
total = len(best_clips)

for i, (start, end) in enumerate(best_clips, 1):

    report(
        f"Creating clip {i} of {total}...",
        0.64 + (i - 1) / total * 0.12
    )

    clip_path = f"clips/clip_{i}.mp4"

    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video,
        "-t", str(end - start),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        clip_path
    ], check=True)

    clip_words = [
        {
            "start": word["start"] - start,
            "end": word["end"] - start,
            "text": word["text"]
        }
        for word in all_words
        if word["start"] >= start
        and word["end"] <= end
    ]

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

    create_animated_captions(
        clip_words,
        f"subtitles/clip_{i}.ass"
    )

# Convert clips to vertical 9:16
def make_vertical_video(
    input_video,
    output_video,
    subtitle_file
):

    font_folder = os.path.abspath("fonts").replace("\\", "/")
    subtitle_path = os.path.abspath(subtitle_file).replace("\\", "/")

    font_folder = font_folder.replace(":", r"\:")
    subtitle_path = subtitle_path.replace(":", r"\:")

    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"ass='{subtitle_path}':fontsdir='{font_folder}'"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", video_filter,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        output_video
    ], check=True)

# Final rendering
finished = []

for i in range(1, total + 1):

    report(
        f"Rendering vertical Short {i} of {total}...",
        0.78 + (i - 1) / total * 0.20
    )

    input_path = f"clips/clip_{i}.mp4"
    output_path = f"clips/vertical_clip_{i}.mp4"
    subtitle_path = f"subtitles/clip_{i}.ass"

    make_vertical_video(
        input_path,
        output_path,
        subtitle_path
    )

    finished.append(
        str((project_dir / output_path).resolve())
    )

report("All Shorts have been created!", 1.0)

return finished