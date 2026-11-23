import os
import re
import json
from types import SimpleNamespace

# Check for google-genai library
try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def _heuristic_select_clips(segments, number_of_shorts=5, chat_signals=None):
    """
    Fallback highlight detection using lexical heuristics, punctuation, and chat signals.
    Returns structured list of candidate dictionaries.
    """
    strong_phrases = [
        "you won't believe", "the truth is", "this is why",
        "here's what happened", "nobody talks about",
        "the biggest mistake", "what happens next",
        "listen carefully", "i was shocked", "the secret to",
        "the real reason", "stop doing this", "never do this",
        "बहुत बढ़िया", "क्या बात है", "भाई साहब", "मार दिया",
        "हेडशॉट", "क्लच", "ओपी", "जबरदस्त"
    ]
    strong_words = [
        "secret", "shocking", "mistake", "amazing", "incredible",
        "unbelievable", "dangerous", "truth", "insane", "crazy",
        "surprising", "clutch", "headshot", "knock", "kill", "op",
        "वाह", "गजब", "भाई", "मार", "जीत", "नॉक", "money", "rich",
        "hack", "trick", "fail", "win", "rule", "proof"
    ]
    curiosity_words = [
        "why", "how", "what", "never", "actually",
        "imagine", "discover", "finally", "because"
    ]
    chat_signals = chat_signals or []

    candidates = []
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

        text = " ".join(s.text for s in selected).strip()
        lower_text = text.lower()

        score = 60  # Base viral score
        score += sum(6 for phrase in strong_phrases if phrase in lower_text)
        score += sum(
            len(re.findall(r"(?<!\w)" + re.escape(word) + r"(?!\w)", lower_text)) * 3
            for word in strong_words
        )
        score += sum(
            len(re.findall(r"(?<!\w)" + re.escape(word) + r"(?!\w)", lower_text))
            for word in curiosity_words
        )
        score += min(lower_text.count("?"), 3) * 3
        score += min(lower_text.count("!"), 3) * 2

        word_count = len(re.findall(r"\b\w+\b", text))
        if 80 <= word_count <= 180:
            score += 5

        for signal_start, signal_score in chat_signals:
            if start - 12 <= signal_start <= actual_end + 12:
                score += min(int(signal_score), 15)

        score = min(99, max(50, score))

        # Generate a punchy title from the first sentence or text
        first_sentence = re.split(r"[.!?]", text)[0].strip()
        title = first_sentence[:50] + ("..." if len(first_sentence) > 50 else "")
        if not title:
            title = f"Viral Moment ({int(start)}s - {int(actual_end)}s)"

        candidates.append({
            "title": title,
            "start": round(start, 2),
            "end": round(actual_end, 2),
            "duration": round(duration, 1),
            "viral_score": score,
            "hook": first_sentence[:80],
            "reason": "Strong keyword signals and high audience engagement pattern",
            "text": text
        })

    candidates.sort(reverse=True, key=lambda item: item["viral_score"])

    # Non-overlapping selection
    best = []
    for cand in candidates:
        if all(cand["end"] <= old["start"] or cand["start"] >= old["end"] for old in best):
            best.append(cand)
        if len(best) >= int(number_of_shorts):
            break

    return best


def detect_viral_highlights(segments, number_of_shorts=5, api_key=None, chat_signals=None):
    """
    Detect viral clips using Gemini API LLM if available; otherwise falls back to heuristics.
    Returns a list of dicts with keys: title, start, end, viral_score, hook, reason, text.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")

    if not api_key or not HAS_GENAI:
        return _heuristic_select_clips(segments, number_of_shorts, chat_signals)

    try:
        client = genai.Client(api_key=api_key)

        # Build transcript excerpt representation with timestamps
        transcript_lines = []
        for s in segments:
            transcript_lines.append(f"[{s.start:.1f} - {s.end:.1f}] {s.text}")
        full_transcript = "\n".join(transcript_lines)

        # Truncate if exceptionally long to avoid huge prompt overhead
        if len(full_transcript) > 60000:
            full_transcript = full_transcript[:60000] + "\n...[truncated]"

        prompt = f"""You are a world-class viral short-form video editor specializing in YouTube Shorts, Instagram Reels, and TikTok.
Analyze the following timestamped video transcript and identify the TOP {number_of_shorts} most engaging, high-retention clips.

Rules for viral shorts:
1. Duration: Each clip MUST be between 25 and 60 seconds (end - start).
2. Hook: Must start with a powerful hook (curiosity, controversy, surprising fact, emotional trigger, or question).
3. Value/Punchline: Must deliver a complete payoff or insight. Never cut off mid-thought or mid-sentence!
4. Accuracy: Start and End timestamps MUST strictly match the timestamps provided in the transcript.
5. Non-overlapping: Clips must not overlap with each other.

Return ONLY a JSON array with this exact structure:
[
  {{
    "title": "Punchy Click-Worthy Title (under 45 chars)",
    "start": 12.5,
    "end": 48.0,
    "viral_score": 94,
    "hook": "First sentence or opening statement",
    "reason": "Brief explanation of why this will hook the audience and retain viewers"
  }}
]

Transcript:
{full_transcript}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
            )
        )

        raw_json = response.text.strip()
        data = json.loads(raw_json)

        clips = []
        for item in data:
            start = float(item["start"])
            end = float(item["end"])
            duration = end - start
            if duration < 15 or duration > 75:
                continue

            # Find matching text from segments
            clip_segments = [s for s in segments if s.start >= start and s.end <= end]
            text = " ".join(s.text for s in clip_segments).strip() if clip_segments else item.get("hook", "")

            clips.append({
                "title": item.get("title", f"Clip ({int(start)}s - {int(end)}s)"),
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(duration, 1),
                "viral_score": int(item.get("viral_score", 85)),
                "hook": item.get("hook", ""),
                "reason": item.get("reason", "Selected by AI for high retention"),
                "text": text
            })

        if clips:
            clips.sort(reverse=True, key=lambda x: x["viral_score"])
            # Ensure non-overlapping
            best = []
            for cand in clips:
                if all(cand["end"] <= old["start"] or cand["start"] >= old["end"] for old in best):
                    best.append(cand)
                if len(best) >= int(number_of_shorts):
                    break
            return best

    except Exception as e:
        print(f"Gemini highlight detection error: {e}. Falling back to heuristics.")

    return _heuristic_select_clips(segments, number_of_shorts, chat_signals)
