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


def _report(callback, message, progress=None):
    if callback:
        callback(message, progress)



def _select_clips(segments, number_of_shorts, chat_signals=None):
    """Rank 25-60 second transcript windows, optionally boosted by live-chat bursts."""
    candidates = []
    strong_phrases = [
        "you won't believe", "the truth is", "this is why",
        "here's what happened", "nobody talks about",
        "the biggest mistake", "what happens next",
        "listen carefully", "i was shocked", "the secret to",
        "बहुत बढ़िया", "क्या बात है", "भाई साहब", "मार दिया",
        "हेडशॉट", "क्लच", "ओपी", "जबरदस्त"
    ]
    strong_words = [
        "secret", "shocking", "mistake", "amazing", "incredible",
        "unbelievable", "dangerous", "truth", "insane", "crazy",
        "surprising", "clutch", "headshot", "knock", "kill", "op",
        "वाह", "गजब", "भाई", "मार", "जीत", "नॉक"
    ]
    curiosity_words = [
        "why", "how", "what", "never", "actually",
        "imagine", "discover", "finally", "because"
    ]
    chat_signals = chat_signals or []

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
            len(re.findall(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text)) * 2
            for word in strong_words
        )
        score += sum(
            len(re.findall(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text))
            for word in curiosity_words
        )
        score += min(text.count("?"), 3) * 2
        score += min(text.count("!"), 3) * 2
        word_count = len(re.findall(r"\b\w+\b", text))
        if 80 <= word_count <= 180:
            score += 3

        # A chat burst near the transcript window is a useful secondary signal.
        for signal_start, signal_score in chat_signals:
            if start - 12 <= signal_start <= actual_end + 12:
                score += min(int(signal_score), 12)

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
    """
    Fast caption path: inspect metadata once, prefer Hindi/Hinglish tracks,
    and fetch only one usable track with a short network timeout.
    """
    _report(callback, "Fast Mode: checking Hindi/English captions...", 0.03)
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

    # Prefer manual Hindi, then automatic Hindi, then English.
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
                    _report(callback, f"Loaded {language} captions.", 0.18)
                    return _save_caption_result(segments, callback)
            except Exception as error:
                errors.append(f"{language}: {str(error)[:180]}")

    if errors:
        _report(
            callback,
            "Fast caption retrieval did not work; checking whether another source is available...",
            0.12,
        )
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



def _youtube_api_get(endpoint, params, timeout=8):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/{endpoint}?{query}",
        headers={"User-Agent": "ShortsMakerAI/2.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _fetch_live_chat_signals(url, api_key, callback):
    """
    Read one recent batch from an active livestream chat.
    This API cannot provide archived chat for an ended stream.
    """
    if not api_key:
        _report(callback, "Live-chat scan skipped: YOUTUBE_API_KEY is not configured.", 0.10)
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
            _report(callback, "No active live chat found; using captions only.", 0.12)
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
        _report(
            callback,
            f"Scanned {len(chat.get('items', []))} recent live-chat messages.",
            0.16,
        )
        return signals
    except Exception as error:
        _report(callback, f"Live-chat scan unavailable; continuing with captions: {str(error)[:160]}", 0.12)
        return []


def _chat_only_clip_candidates(chat_signals, number_of_shorts, duration=40):
    """Build candidate windows from active-live-chat reaction bursts when captions are absent."""
    ranked = sorted(chat_signals, key=lambda item: item[1], reverse=True)
    chosen = []
    for timestamp, score in ranked:
        start = max(0.0, float(timestamp) - 10.0)
        end = start + float(duration)
        if all(end <= old_start or start >= old_end for old_start, old_end in chosen):
            chosen.append((start, end))
        if len(chosen) >= int(number_of_shorts):
            break
    return chosen

def process_youtube_video(url, number_of_shorts=5, progress_callback=None, youtube_api_key=None):
    """Analyze YouTube captions, then retrieve only the selected video ranges."""
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    _prepare_folders()

    url = (url or "").strip()
    if not url:
        raise ValueError("Please enter a YouTube URL.")

    chat_signals = _fetch_live_chat_signals(url, youtube_api_key, progress_callback)

    caption_error = None
    try:
        caption_result = _fetch_youtube_captions(url, progress_callback)
    except Exception as error:
        caption_result = None
        caption_error = error

    if caption_result:
        segments, words = caption_result
        _report(
            callback=progress_callback,
            message="Captions loaded! Ranking Hindi/English highlights with chat signals...",
            progress=0.58,
        )
        best_clips = _select_clips(
            segments, number_of_shorts, chat_signals=chat_signals
        )
    elif chat_signals:
        words = []
        _report(
            progress_callback,
            "Captions unavailable. Creating candidate timestamps from active live-chat reactions.",
            0.58,
        )
        best_clips = _chat_only_clip_candidates(chat_signals, number_of_shorts)
    else:
        detail = f" Caption error: {caption_error}" if caption_error else ""
        raise RuntimeError(
            "No usable YouTube captions or active live-chat signals were available. "
            "Full video/audio downloading remains disabled." + detail
        )

    if not best_clips:
        raise RuntimeError("No suitable clips found. Try another video.")

    def download_selected_range(start, end, output):
        """Download only one selected YouTube time range, not the full source."""
        output.parent.mkdir(parents=True, exist_ok=True)

        # Each clip gets its own yt-dlp download. web_safari commonly exposes
        # HLS formats, which currently avoid some GVS PO-token requirements.
        # If that client is unavailable for a video, retry with yt-dlp defaults.
        attempts = [
            ("web_safari", {"youtube": {"player_client": ["web_safari"]}}),
            ("default", None),
        ]
        errors = []

        for client_name, extractor_args in attempts:
            # Remove leftovers from a failed previous attempt for this clip.
            for stale in output.parent.glob(f"{output.stem}.*"):
                if stale.is_file():
                    try:
                        stale.unlink()
                    except OSError:
                        pass

            options = {
                "format": "best",
                "download_ranges": download_range_func(None, [(float(start), float(end))]),
                "force_keyframes_at_cuts": True,
                "outtmpl": str(output.with_suffix("")) + ".%(ext)s",
                "merge_output_format": "mp4",
                "js_runtimes": {"deno": {}},
                "remote_components": ["ejs:github"],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "overwrites": True,
                "retries": 2,
                "fragment_retries": 2,
                "socket_timeout": 30,
            }
            if extractor_args:
                options["extractor_args"] = extractor_args

            try:
                _report(
                    progress_callback,
                    f"Downloading only {int(end - start)} seconds of selected footage ({client_name} client)...",
                    0.62,
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
                    # Normalize the result to the MP4 filename expected by the renderer.
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
                errors.append(f"{client_name}: {str(error)[:700]}")

        combined = " | ".join(errors)
        if "403" in combined or "Forbidden" in combined:
            raise RuntimeError(
                "YouTube returned HTTP 403 for the selected video segment with both "
                "the web_safari and default clients. This update avoids downloading "
                "the entire source video, but it cannot override a YouTube block on "
                "the Streamlit Cloud server IP. A PO-token provider may help with "
                "token-related 403s; it will not fix an IP-level block. Details: "
                + combined
            )
        raise RuntimeError("Could not download the selected YouTube segment. " + combined)

    return _finish_clips(
        best_clips,
        words,
        download_selected_range,
        number_of_shorts,
        progress_callback
    )
