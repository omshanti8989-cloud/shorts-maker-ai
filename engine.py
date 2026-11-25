import os
import re
import glob
import html
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import yt_dlp
from yt_dlp.utils import download_range_func
from faster_whisper import WhisperModel

from ai_highlight import detect_viral_highlights
from cropper import SmartCropper
from caption_maker import create_animated_captions
from translator import translate_words_to_language


class ShortResult(str):
    """String subclass that holds rich viral clip metadata for full backward compatibility."""
    def __new__(cls, path, **meta):
        instance = super().__new__(cls, path)
        instance.path = str(path)
        instance.meta = meta
        for k, v in meta.items():
            setattr(instance, k, v)
        return instance

    def __getitem__(self, item):
        if isinstance(item, str):
            return self.meta.get(item)
        return super().__getitem__(item)

    def get(self, item, default=None):
        return self.meta.get(item, default)


def _report(callback, message, progress=None):
    if callback:
        callback(message, progress)


def _ass_time(seconds):
    total = round(max(0.0, float(seconds)) * 100)
    hours = total // 360000
    minutes = (total % 360000) // 6000
    secs = (total % 6000) // 100
    centiseconds = total % 100
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"


def _srt_time(seconds):
    milliseconds = round(max(0.0, float(seconds)) * 1000)
    hours = milliseconds // 3600000
    minutes = (milliseconds % 3600000) // 60000
    seconds_part = (milliseconds % 60000) // 1000
    ms = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{seconds_part:02},{ms:03}"


def _make_captions(words, index, style_name="hormozi", highlight_color="yellow", enable_emojis=True):
    ass_path = Path(f"subtitles/clip_{index}.ass")
    create_animated_captions(
        words,
        str(ass_path),
        style_name=style_name,
        highlight_color=highlight_color,
        enable_emojis=enable_emojis
    )

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


def _render_vertical(input_video, output_video, subtitle_file, layout="smart_crop"):
    """
    Renders 9:16 vertical short using SmartCropper with face tracking,
    blurred ambient background, or split screen layout.
    """
    cropper = SmartCropper()
    font_folder = os.path.abspath("fonts").replace("\\", "/").replace(":", r"\:")
    subtitle_path = os.path.abspath(subtitle_file).replace("\\", "/").replace(":", r"\:")

    try:
        video_info, primary_x, dual_speakers = cropper.analyze_video_faces(input_video)
        filter_complex, map_out = cropper.get_crop_filter(
            video_info,
            primary_x=primary_x,
            layout=layout,
            dual_speakers=dual_speakers,
            subtitle_path=subtitle_path,
            fonts_dir="fonts"
        )

        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_video),
            "-filter_complex", filter_complex,
            "-map", map_out, "-map", "0:a?",
            "-c:v", "libx264", "-c:a", "aac",
            "-preset", "fast", "-pix_fmt", "yuv420p",
            "-shortest", str(output_video)
        ], check=True)

    except Exception as e:
        print(f"Smart crop failed ({e}), falling back to blurred background...")
        fallback_filter = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=24:12[blurred];"
            "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fit];"
            f"[blurred][fit]overlay=(W-w)/2:(H-h)/2,"
            f"ass='{subtitle_path}':fontsdir='{font_folder}'[final]"
        )
        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_video),
            "-filter_complex", fallback_filter,
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
            try:
                os.remove(old_file)
            except OSError:
                pass


def _transcribe(audio_or_video, callback):
    _report(callback, "Loading Whisper speech recognition model...", 0.03)
    model = WhisperModel(
        "tiny", device="cpu", compute_type="int8",
        cpu_threads=2, num_workers=1
    )
    _report(callback, "Transcribing video audio. This may take a few moments...", 0.08)
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
    """Convert WebVTT caption cues into strictly sequential, non-overlapping transcript segments."""
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
            segments.append(SimpleNamespace(start=start, end=end, text=text))
        i += 1

    # Clean and resolve overlapping cues (common in YouTube rolling WebVTT captions)
    segments.sort(key=lambda s: (s.start, s.end))
    cleaned = []
    for s in segments:
        text = s.text.strip()
        if not text or s.end <= s.start:
            continue
        if cleaned:
            prev = cleaned[-1]
            if s.start < prev.end:
                # If nearly identical start time (<=0.25s), merge lines to avoid collision
                if s.start <= prev.start + 0.25:
                    if text not in prev.text:
                        prev.text = f"{prev.text} {text}"
                    prev.end = max(prev.end, s.end)
                    continue
                else:
                    # Previous cue finishes right when new cue begins
                    prev.end = s.start
        cleaned.append(SimpleNamespace(start=s.start, end=s.end, text=text))

    return cleaned


def _caption_words(segments):
    """Create approximate word timings from caption cue timings for subtitle display."""
    words = []
    for segment in segments:
        cue_words = segment.text.split()
        if not cue_words:
            continue
        duration = max(0.2, float(segment.end) - float(segment.start))
        step = duration / len(cue_words)
        for index, word in enumerate(cue_words):
            start = float(segment.start) + index * step
            end = float(segment.start) + (index + 1) * step
            words.append({
                "start": start,
                "end": end,
                "text": word
            })
    return words


def _fetch_youtube_captions(url, callback):
    """Fast caption path: inspect metadata and fetch WebVTT track directly."""
    _report(callback, "Fast Mode: checking for existing YouTube captions...", 0.03)
    download_dir = Path("downloads")
    download_dir.mkdir(parents=True, exist_ok=True)
    for old_file in download_dir.glob("youtube_caption*"):
        if old_file.is_file():
            try:
                old_file.unlink()
            except OSError:
                pass

    common_options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 12,
        "retries": 0,
        "extractor_retries": 0,
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }
    with yt_dlp.YoutubeDL(common_options) as ydl:
        info = ydl.extract_info(url, download=False)

    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    all_languages = list(dict.fromkeys(list(manual) + list(automatic)))
    if not all_languages:
        return None

    def language_rank(code):
        code = code.lower()
        if code in ("hi", "hi-in", "hi-orig"):
            return 0
        if code.startswith("hi-"):
            return 1
        if code in ("en", "en-us", "en-gb", "en-orig"):
            return 2
        if code.startswith("en-"):
            return 3
        return 9

    all_languages.sort(key=language_rank)
    preferred = [code for code in all_languages if language_rank(code) < 9][:2]
    if not preferred:
        preferred = all_languages[:1]

    attempts = []
    for language in preferred:
        if manual.get(language):
            attempts.append((language, manual[language]))
        if automatic.get(language):
            attempts.append((language, automatic[language]))

    errors = []
    for language, tracks in attempts[:3]:
        _report(callback, f"Fast Mode: fetching {language} captions...", 0.08)
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
                with urllib.request.urlopen(request, timeout=8) as response:
                    raw_caption = response.read(8 * 1024 * 1024).decode(
                        "utf-8", errors="replace"
                    )

                if raw_caption.lstrip().startswith("{"):
                    data = json.loads(raw_caption)
                    caption_lines = []
                    for event in data.get("events", []):
                        text = "".join(
                            item.get("utf8", "")
                            for item in event.get("segs", [])
                        ).strip()
                        if text:
                            cue_start = float(event.get("tStartMs", 0)) / 1000
                            cue_duration = float(event.get("dDurationMs", 1000)) / 1000
                            caption_lines.append(
                                f"{_srt_time(cue_start).replace(',', '.')} --> "
                                f"{_srt_time(cue_start + cue_duration).replace(',', '.')}\n{text}"
                            )
                    raw_caption = "WEBVTT\n\n" + "\n\n".join(caption_lines)

                segments = _parse_vtt(raw_caption)
                if segments:
                    (download_dir / "youtube_caption_fast.vtt").write_text(
                        raw_caption, encoding="utf-8"
                    )
                    _report(callback, f"Loaded {language} captions successfully.", 0.18)
                    return _save_caption_result(segments, callback)
            except Exception as error:
                errors.append(f"{language}: {str(error)[:180]}")

    return None


def _save_caption_result(segments, callback):
    words = _caption_words(segments)
    if not words:
        raise RuntimeError("Caption segments were found, but word timings could not be generated.")

    with open("transcript.txt", "w", encoding="utf-8") as file:
        for segment in segments:
            file.write(f"{segment.start:.2f} - {segment.end:.2f}: {segment.text}\n")

    _report(callback, "Transcript extracted successfully!", 0.15)
    return segments, words


def _finish_clips(
    best_clips,
    all_words,
    get_clip,
    number_of_shorts,
    callback,
    layout="smart_crop",
    caption_style="hormozi",
    highlight_color="yellow",
    enable_emojis=True,
    subtitle_language="hinglish",
    gemini_api_key=None
):
    total = len(best_clips)
    finished = []
    for i, clip in enumerate(best_clips, 1):
        if isinstance(clip, dict):
            start, end = clip["start"], clip["end"]
            title = clip.get("title", f"Short {i}")
            viral_score = clip.get("viral_score", 85)
            hook = clip.get("hook", "")
            reason = clip.get("reason", "")
        else:
            start, end = clip[0], clip[1]
            title = f"Viral Short {i}"
            viral_score = 80
            hook = ""
            reason = "Selected moment"

        _report(callback, f"Processing selected viral segment {i} of {total}: '{title}'...", 0.60 + (i - 1) / total * 0.15)
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

        # Handle Subtitle Translation (Hinglish: Roman Hindi + English; English: English; Hindi: Devanagari)
        sub_lang = subtitle_language or "hinglish"
        if sub_lang == "original":
            sub_lang = "hinglish"

        lang_label = "Hinglish (Roman)" if sub_lang == "hinglish" else ("English" if sub_lang == "en" else "Hindi")
        _report(callback, f"Generating {lang_label} captions...", 0.68 + (i - 1) / total * 0.08)
        clip_words = translate_words_to_language(
            clip_words,
            target_language=sub_lang,
            api_key=gemini_api_key
        )

        subtitle_path = _make_captions(
            clip_words,
            i,
            style_name=caption_style,
            highlight_color=highlight_color,
            enable_emojis=enable_emojis
        )

        _report(callback, f"Rendering 9:16 Short {i} of {total} ({layout} layout)...", 0.75 + (i - 1) / total * 0.22)
        output_path = Path(f"clips/vertical_clip_{i}.mp4")
        _render_vertical(clip_path, output_path, subtitle_path, layout=layout)

        result_obj = ShortResult(
            str(output_path.resolve()),
            title=title,
            viral_score=viral_score,
            hook=hook,
            reason=reason,
            start=start,
            end=end,
            duration=round(end - start, 1)
        )
        finished.append(result_obj)

    _report(callback, "All Shorts have been created successfully!", 1.0)
    return finished


def process_video(
    video,
    number_of_shorts=5,
    progress_callback=None,
    gemini_api_key=None,
    layout="smart_crop",
    caption_style="hormozi",
    highlight_color="yellow",
    enable_emojis=True,
    subtitle_language="hinglish"
):
    """Process an uploaded local video file into vertical Shorts."""
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    _prepare_folders()

    video = Path(video).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Video file not found: {video}")

    segments, words = _transcribe(video, progress_callback)
    _report(progress_callback, "Detecting viral highlights with AI...", 0.58)

    best_clips = detect_viral_highlights(
        segments,
        number_of_shorts=number_of_shorts,
        api_key=gemini_api_key
    )
    if not best_clips:
        raise RuntimeError("No suitable 25–60 second clips were found. Try a video with more spoken dialogue.")

    def local_clip(start, end, output):
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(start), "-i", str(video),
            "-t", str(end - start), "-c:v", "libx264", "-c:a", "aac",
            "-preset", "fast", str(output)
        ], check=True)

    return _finish_clips(
        best_clips,
        words,
        local_clip,
        number_of_shorts,
        progress_callback,
        layout=layout,
        caption_style=caption_style,
        highlight_color=highlight_color,
        enable_emojis=enable_emojis,
        subtitle_language=subtitle_language,
        gemini_api_key=gemini_api_key
    )


def _youtube_api_get(endpoint, params, timeout=8):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/{endpoint}?{query}",
        headers={"User-Agent": "ShortsMakerAI/2.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _fetch_live_chat_signals(url, api_key, callback):
    if not api_key:
        return []

    match = re.search(r"(?:v=|youtu\.be/|live/)([A-Za-z0-9_-]{11})", url)
    if not match:
        return []

    video_id = match.group(1)
    try:
        details = _youtube_api_get(
            "videos",
            {
                "part": "liveStreamingDetails",
                "id": video_id,
                "key": api_key,
            },
        )
        items = details.get("items", [])
        if not items:
            return []
        live = items[0].get("liveStreamingDetails", {})
        chat_id = live.get("activeLiveChatId")
        actual_start = live.get("actualStartTime")
        if not chat_id or not actual_start:
            return []

        from datetime import datetime
        start_dt = datetime.fromisoformat(actual_start.replace("Z", "+00:00"))
        chat = _youtube_api_get(
            "liveChat/messages",
            {
                "part": "snippet",
                "liveChatId": chat_id,
                "maxResults": 200,
                "key": api_key,
            },
        )
        buckets = {}
        reaction_terms = (
            "op", "clutch", "headshot", "1v", "knock", "kill",
            "वाह", "गजब", "जबरदस्त", "भाई", "मार दिया", "क्लच",
            "हेडशॉट", "ओपी", "🔥", "😂", "😱", "💀"
        )
        for item in chat.get("items", []):
            snippet = item.get("snippet", {})
            published = snippet.get("publishedAt")
            message = snippet.get("displayMessage", "").lower()
            if not published or not message:
                continue
            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
            elapsed = max(0, int((timestamp - start_dt).total_seconds()))
            bucket = (elapsed // 15) * 15
            score = 1
            score += sum(2 for term in reaction_terms if term in message)
            buckets[bucket] = buckets.get(bucket, 0) + score

        signals = [(float(bucket), score) for bucket, score in buckets.items() if score >= 3]
        return signals
    except Exception:
        return []


def process_youtube_video(
    url,
    number_of_shorts=5,
    progress_callback=None,
    youtube_api_key=None,
    gemini_api_key=None,
    layout="smart_crop",
    caption_style="hormozi",
    highlight_color="yellow",
    enable_emojis=True,
    subtitle_language="hinglish"
):
    """Analyze YouTube captions with AI, then retrieve and render selected 9:16 ranges."""
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    _prepare_folders()

    url = (url or "").strip()
    if not url:
        raise ValueError("Please enter a YouTube URL.")

    chat_signals = _fetch_live_chat_signals(url, youtube_api_key, progress_callback)

    caption_result = None
    try:
        caption_result = _fetch_youtube_captions(url, progress_callback)
    except Exception as error:
        caption_result = None

    if caption_result:
        segments, words = caption_result
        _report(
            callback=progress_callback,
            message="Captions loaded! Detecting viral highlights using AI...",
            progress=0.55,
        )
        best_clips = detect_viral_highlights(
            segments,
            number_of_shorts=number_of_shorts,
            api_key=gemini_api_key,
            chat_signals=chat_signals
        )
    else:
        raise RuntimeError(
            "No usable YouTube captions or transcript could be retrieved automatically for this video. "
            "Please try another video or upload the video file directly."
        )

    if not best_clips:
        raise RuntimeError("No suitable clips found. Try another video.")

    def download_selected_range(start, end, output):
        """Download only one selected YouTube time range, not the full source."""
        output.parent.mkdir(parents=True, exist_ok=True)

        attempts = [
            ("default", None),
            ("web_safari", {"youtube": {"player_client": ["web_safari"]}}),
        ]
        errors = []

        for client_name, extractor_args in attempts:
            for stale in output.parent.glob(f"{output.stem}.*"):
                if stale.is_file():
                    try:
                        stale.unlink()
                    except OSError:
                        pass

            options = {
                "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "download_ranges": download_range_func(None, [(float(start), float(end))]),
                "outtmpl": str(output.with_suffix("")) + ".%(ext)s",
                "merge_output_format": "mp4",
                "js_runtimes": {"deno": {}},
                "remote_components": ["ejs:github"],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "overwrites": True,
                "retries": 3,
                "fragment_retries": 3,
                "socket_timeout": 30,
            }
            if extractor_args:
                options["extractor_args"] = extractor_args

            try:
                _report(
                    progress_callback,
                    f"Downloading {int(end - start)}s clip segment ({client_name})...",
                    0.65,
                )
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([url])

                generated = [
                    p for p in output.parent.glob(f"{output.stem}.*")
                    if p.is_file() and p.suffix.lower() in {
                        ".mp4", ".mkv", ".webm", ".mov"
                    }
                ]
                if not generated:
                    raise RuntimeError("yt-dlp completed but no clip file was created.")

                downloaded = generated[0]
                if downloaded != output:
                    command = [
                        "ffmpeg", "-y", "-i", str(downloaded),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-c:a", "aac", "-movflags", "+faststart", str(output)
                    ]
                    result = subprocess.run(command, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise RuntimeError("FFmpeg could not normalize the selected segment: " + result.stderr[-1200:])
                    if downloaded.exists():
                        downloaded.unlink()

                if not output.exists() or output.stat().st_size == 0:
                    raise RuntimeError("The downloaded clip is empty.")
                return

            except Exception as error:
                errors.append(f"{client_name}: {str(error)[:400]}")

        combined = " | ".join(errors)
        raise RuntimeError("Could not download the selected YouTube segment. Details: " + combined)

    return _finish_clips(
        best_clips,
        words,
        download_selected_range,
        number_of_shorts,
        progress_callback,
        layout=layout,
        caption_style=caption_style,
        highlight_color=highlight_color,
        enable_emojis=enable_emojis,
        subtitle_language=subtitle_language,
        gemini_api_key=gemini_api_key
    )
