import os
import re
import glob
import html
import subprocess
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import yt_dlp
from faster_whisper import WhisperModel


def _report(callback, message, progress=None):
    if callback:
        callback(message, progress)


def _select_clips(segments, number_of_shorts):
    candidates = []
    strong_phrases = [
        "you won't believe", "the truth is", "this is why",
        "here's what happened", "nobody talks about",
        "the biggest mistake", "what happens next",
        "listen carefully", "i was shocked", "the secret to"
    ]
    strong_words = [
        "secret", "shocking", "mistake", "amazing", "incredible",
        "unbelievable", "dangerous", "truth", "insane", "crazy",
        "surprising"
    ]
    curiosity_words = [
        "why", "how", "what", "never", "actually",
        "imagine", "discover", "finally", "because"
    ]

    for segment in segments:
        start = float(segment.start)
        end_limit = start + 45
        selected = [s for s in segments if s.start >= start and s.end <= end_limit]
        if not selected:
            continue
        actual_end = float(selected[-1].end)
        duration = actual_end - start
        if duration < 25 or duration > 60:
            continue

        text = " ".join(s.text for s in selected).lower()
        score = sum(3 for phrase in strong_phrases if phrase in text)
        score += sum(
            len(re.findall(r"\b" + re.escape(word) + r"\b", text)) * 2
            for word in strong_words
        )
        score += sum(
            len(re.findall(r"\b" + re.escape(word) + r"\b", text))
            for word in curiosity_words
        )
        score += min(text.count("?"), 3) * 2
        score += min(text.count("!"), 3) * 2
        word_count = len(re.findall(r"\b\w+\b", text))
        if 80 <= word_count <= 180:
            score += 3
        candidates.append((score, start, actual_end, text))

    candidates.sort(reverse=True, key=lambda item: item[0])
    best = []
    for score, start, end, text in candidates:
        if all(end <= old_start or start >= old_end for old_start, old_end in best):
            best.append((start, end))
        if len(best) >= int(number_of_shorts):
            break
    return best


def _ass_time(seconds):
    total = round(seconds * 100)
    hours = total // 360000
    minutes = (total % 360000) // 6000
    secs = (total % 6000) // 100
    centiseconds = total % 100
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"


def _srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours = milliseconds // 3600000
    minutes = (milliseconds % 3600000) // 60000
    seconds_part = (milliseconds % 60000) // 1000
    ms = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{seconds_part:02},{ms:03}"


def _make_captions(words, index):
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
            start, end = active_word["start"], active_word["end"]
            if end <= start:
                continue
            parts = []
            for j, item in enumerate(group):
                safe_word = re.sub(r"[{}\\]", "", item["text"])
                if j == active_index:
                    parts.append(
                        r"{\c&H0000FFFF&\fscx115\fscy115"
                        r"\t(0,120,\fscx100\fscy100)}"
                        + safe_word + r"{\c&H00FFFFFF&}"
                    )
                else:
                    parts.append(safe_word)
            caption = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
                f"Pop,,0,0,0,,{{\\an5\\pos(540,960)}}{caption}"
            )

    ass_path = Path(f"subtitles/clip_{index}.ass")
    ass_path.write_text(header + "\n".join(events), encoding="utf-8-sig")

    srt_lines = []
    for number, word in enumerate(words, 1):
        srt_lines.append(
            f"{number}\n{_srt_time(word['start'])} --> "
            f"{_srt_time(word['end'])}\n{word['text']}\n"
        )
    Path(f"subtitles/clip_{index}.srt").write_text(
        "\n".join(srt_lines), encoding="utf-8"
    )
    return str(ass_path)


def _render_vertical(input_video, output_video, subtitle_file):
    """
    Preserve the complete original video frame, including streamer facecam,
    and create a vertical 9:16 Short with a blurred background.
    """
    font_folder = os.path.abspath("fonts").replace("\\", "/").replace(":", r"\:")
    subtitle_path = os.path.abspath(subtitle_file).replace("\\", "/").replace(":", r"\:")

    filter_complex = (
        "[0:v]split=2[background][foreground];"
        "[background]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=24:12[blurred];"
        "[foreground]scale=1080:1920:force_original_aspect_ratio=decrease[fit];"
        "[blurred][fit]overlay=(W-w)/2:(H-h)/2,"
        f"ass='{subtitle_path}':fontsdir='{font_folder}'[final]"
    )

    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_video),
        "-filter_complex", filter_complex,
        "-map", "[final]", "-map", "0:a?",
        "-c:v", "libx264", "-c:a", "aac",
        "-preset", "fast", "-pix_fmt", "yuv420p",
        "-shortest", str(output_video)
    ], check=True)


def _prepare_folders():
    for folder in ["downloads", "clips", "subtitles", "fonts"]:
        Path(folder).mkdir(exist_ok=True)
    for pattern in [
        "clips/clip_*.mp4", "clips/vertical_clip_*.mp4",
        "subtitles/clip_*.ass", "subtitles/clip_*.srt"
    ]:
        for old_file in glob.glob(pattern):
            os.remove(old_file)


def _transcribe(audio_or_video, callback):
    _report(callback, "Loading Whisper Tiny speech-recognition model...", 0.03)
    model = WhisperModel(
        "tiny", device="cpu", compute_type="int8",
        cpu_threads=2, num_workers=1
    )
    _report(callback, "Transcribing the complete audio. This may take several minutes...", 0.08)
    segments, info = model.transcribe(
        str(audio_or_video), word_timestamps=True, beam_size=1,
        vad_filter=True, condition_on_previous_text=True
    )
    segments = list(segments)
    _report(callback, f"Transcription completed. Detected language: {info.language}", 0.55)

    with open("transcript.txt", "w", encoding="utf-8") as file:
        for segment in segments:
            file.write(f"{segment.start:.2f} - {segment.end:.2f}: {segment.text}\n")

    words = []
    for segment in segments:
        for word in (segment.words or []):
            text = word.word.strip()
            if text:
                words.append({
                    "start": float(word.start),
                    "end": float(word.end),
                    "text": text
                })
    if not words:
        raise RuntimeError("No spoken words were detected in the audio.")
    return segments, words


def _parse_vtt(vtt_text):
    """Convert WebVTT caption cues into timestamped transcript segments."""
    segments = []
    lines = vtt_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    timestamp_pattern = re.compile(
        r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+"
        r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})"
    )

    i = 0
    while i < len(lines):
        match = timestamp_pattern.search(lines[i])
        if not match:
            i += 1
            continue

        groups = match.groups()
        start_hours = int(groups[0] or 0)
        start = start_hours * 3600 + int(groups[1]) * 60 + int(groups[2]) + int(groups[3]) / 1000
        end_hours = int(groups[4] or 0)
        end = end_hours * 3600 + int(groups[5]) * 60 + int(groups[6]) + int(groups[7]) / 1000

        i += 1
        cue_lines = []
        while i < len(lines) and lines[i].strip():
            line = lines[i].strip()
            if not line.startswith(("NOTE", "STYLE", "REGION")):
                cue_lines.append(line)
            i += 1

        text = " ".join(cue_lines)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text).replace("&lrm;", "").replace("&rlm;", "")
        text = re.sub(r"\s+", " ", text).strip()
        if text and end > start:
            if segments and text == segments[-1].text:
                segments[-1].end = max(segments[-1].end, end)
            else:
                segments.append(SimpleNamespace(start=start, end=end, text=text))
        i += 1

    return segments


def _caption_words(segments):
    """Create approximate word timings from caption cue timings for subtitle display."""
    words = []
    for segment in segments:
        cue_words = segment.text.split()
        if not cue_words:
            continue
        duration = max(0.15, float(segment.end) - float(segment.start))
        step = duration / len(cue_words)
        for index, word in enumerate(cue_words):
            start = float(segment.start) + index * step
            end = float(segment.start) + (index + 1) * step
            words.append({
                "start": start,
                "end": max(start + 0.08, end),
                "text": word
            })
    return words


def _fetch_youtube_captions(url, callback):
    """Retrieve YouTube captions, trying yt-dlp subtitle download and direct caption URLs."""
    _report(callback, "Checking YouTube captions...", 0.03)

    download_dir = Path("downloads")
    download_dir.mkdir(parents=True, exist_ok=True)

    for old_file in download_dir.glob("youtube_caption*"):
        if old_file.is_file():
            old_file.unlink()

    common_options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }

    with yt_dlp.YoutubeDL(common_options) as ydl:
        info = ydl.extract_info(url, download=False)

    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}

    # Prefer English, including YouTube's newer en-orig/en-US variants.
    all_languages = list(dict.fromkeys(list(manual.keys()) + list(automatic.keys())))
    if not all_languages:
        return None

    def language_rank(code):
        code = code.lower()
        if code in ("en", "en-us", "en-gb", "en-orig"):
            return 0
        if code.startswith("en-"):
            return 1
        return 2

    all_languages.sort(key=language_rank)
    preferred_languages = all_languages

    # Try manual captions first, then automatic captions for each matching language.
    track_attempts = []
    for language in preferred_languages:
        if manual.get(language):
            track_attempts.append((language, True, manual[language]))
        if automatic.get(language):
            track_attempts.append((language, False, automatic[language]))

    errors = []
    for language, is_manual, tracks in track_attempts:
        _report(callback, f"Trying YouTube captions ({language})...", 0.06)

        # First use yt-dlp's built-in subtitle downloader.
        subtitle_options = {
            **common_options,
            "writesubtitles": is_manual,
            "writeautomaticsubtitles": not is_manual,
            "subtitleslangs": [language],
            "subtitlesformat": "vtt",
            "outtmpl": str(download_dir / "youtube_caption.%(ext)s"),
            "overwrites": True,
        }

        try:
            with yt_dlp.YoutubeDL(subtitle_options) as ydl:
                ydl.download([url])
        except Exception as error:
            errors.append(f"{language} yt-dlp: {str(error)[:250]}")

        caption_files = [
            p for p in download_dir.glob("youtube_caption*")
            if p.is_file() and p.suffix.lower() == ".vtt"
        ]

        if caption_files:
            vtt_text = sorted(caption_files)[0].read_text(
                encoding="utf-8", errors="replace"
            )
            segments = _parse_vtt(vtt_text)
            if segments:
                return _save_caption_result(segments, callback)

        # Fallback: fetch the caption URL exposed by YouTube's player metadata.
        for track in tracks:
            caption_url = track.get("url")
            if not caption_url:
                continue
            try:
                request = urllib.request.Request(
                    caption_url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://www.youtube.com/",
                    },
                )
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw_caption = response.read().decode("utf-8", errors="replace")

                # Some YouTube caption URLs return JSON3 rather than WebVTT.
                if raw_caption.lstrip().startswith("{"):
                    data = __import__("json").loads(raw_caption)
                    caption_lines = []
                    for event in data.get("events", []):
                        text = "".join(
                            item.get("utf8", "")
                            for item in event.get("segs", [])
                        ).strip()
                        if text:
                            start = float(event.get("tStartMs", 0)) / 1000
                            duration = float(event.get("dDurationMs", 1000)) / 1000
                            caption_lines.append(
                                f"{_srt_time(start).replace(',', '.')} --> "
                                f"{_srt_time(start + duration).replace(',', '.')}\n{text}"
                            )
                    raw_caption = "WEBVTT\n\n" + "\n\n".join(caption_lines)

                segments = _parse_vtt(raw_caption)
                if segments:
                    (download_dir / "youtube_caption_direct.vtt").write_text(
                        raw_caption, encoding="utf-8"
                    )
                    return _save_caption_result(segments, callback)
            except Exception as error:
                errors.append(f"{language} direct URL: {str(error)[:250]}")

    raise RuntimeError(
        "YouTube listed caption tracks, but none could be downloaded or parsed. "
        "This can happen when YouTube blocks caption requests from the cloud server. "
        + " | ".join(errors[-4:])
    )


def _save_caption_result(segments, callback):
    words = _caption_words(segments)
    if not words:
        raise RuntimeError("Caption segments were found, but word timings could not be generated.")

    with open("transcript.txt", "w", encoding="utf-8") as file:
        for segment in segments:
            file.write(f"{segment.start:.2f} - {segment.end:.2f}: {segment.text}\n")

    _report(callback, "Transcript extracted successfully!", 0.15)
    return segments, words


def _finish_clips(best_clips, all_words, get_clip, number_of_shorts, callback):
    total = len(best_clips)
    finished = []
    for i, (start, end) in enumerate(best_clips, 1):
        _report(callback, f"Getting selected video segment {i} of {total}...", 0.62 + (i - 1) / total * 0.12)
        clip_path = Path(f"clips/clip_{i}.mp4")
        get_clip(start, end, clip_path)

        clip_words = [
            {
                "start": word["start"] - start,
                "end": word["end"] - start,
                "text": word["text"]
            }
            for word in all_words
            if word["start"] >= start and word["end"] <= end
        ]
        subtitle_path = _make_captions(clip_words, i)

        _report(callback, f"Rendering vertical Short {i} of {total}...", 0.78 + (i - 1) / total * 0.20)
        output_path = Path(f"clips/vertical_clip_{i}.mp4")
        _render_vertical(clip_path, output_path, subtitle_path)
        finished.append(str(output_path.resolve()))

    _report(callback, "All Shorts have been created!", 1.0)
    return finished


def process_video(video, number_of_shorts=5, progress_callback=None):
    """Process an uploaded local video file into vertical Shorts."""
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    _prepare_folders()

    video = Path(video).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Video file not found: {video}")

    segments, words = _transcribe(video, progress_callback)
    _report(progress_callback, "Finding potential highlights...", 0.58)
    best_clips = _select_clips(segments, number_of_shorts)
    if not best_clips:
        raise RuntimeError("No suitable 25–60 second clips were found. Try a longer video with more speech.")

    def local_clip(start, end, output):
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(start), "-i", str(video),
            "-t", str(end - start), "-c:v", "libx264", "-c:a", "aac",
            "-preset", "fast", str(output)
        ], check=True)

    return _finish_clips(best_clips, words, local_clip, number_of_shorts, progress_callback)


def process_youtube_video(url, number_of_shorts=5, progress_callback=None):
    """Use YouTube captions for analysis, then download source video once and cut clips locally."""
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    _prepare_folders()

    url = (url or "").strip()
    if not url:
        raise ValueError("Please enter a YouTube URL.")

    try:
        caption_result = _fetch_youtube_captions(url, progress_callback)
    except Exception as error:
        raise RuntimeError(
            f"YouTube caption retrieval failed: {error}. No audio was downloaded."
        ) from error

    if not caption_result:
        raise RuntimeError(
            "No usable YouTube captions were found. Full audio downloading is disabled."
        )

    segments, words = caption_result
    _report(callback=progress_callback, message="Captions loaded! Finding the strongest moments...", progress=0.58)

    best_clips = _select_clips(segments, number_of_shorts)
    if not best_clips:
        raise RuntimeError("No suitable clips found. Try another video.")

    def download_selected_range(start, end, output):
        output.parent.mkdir(parents=True, exist_ok=True)

        source_files = [
            p for p in output.parent.glob("source_video.*")
            if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm"}
        ]

        if not source_files:
            options = {
                "format": "bestvideo*+bestaudio/best",
                "js_runtimes": {"deno": {}},
                "remote_components": ["ejs:github"],
                "outtmpl": str(output.parent / "source_video.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])

            source_files = [
                p for p in output.parent.glob("source_video.*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm"}
            ]

        if not source_files:
            raise RuntimeError("Source video download failed.")

        source = source_files[0]
        command = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(source),
            "-t", str(end - start),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(output)
        ]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "FFmpeg clip creation failed: " + result.stderr[-2000:]
            )

        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("Generated clip is empty.")

    return _finish_clips(
        best_clips,
        words,
        download_selected_range,
        number_of_shorts,
        progress_callback
    )
