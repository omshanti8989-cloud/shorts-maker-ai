import os
import re
from pathlib import Path

# ASS color format is &HAABBGGRR& (Alpha, Blue, Green, Red)
COLOR_PALETTES = {
    "yellow": "&H0000FFFF&",    # Vibrant Yellow
    "green": "&H0000FF00&",     # Neon Lime Green
    "cyan": "&H00FFFF00&",      # Electric Cyan
    "orange": "&H000080FF&",    # Hot Orange
    "magenta": "&H00FF00FF&",   # Neon Magenta
    "white": "&H00FFFFFF&"      # Pure White
}

# Contextual keyword-to-emoji dictionary (English, Hindi & Hinglish)
KEYWORD_EMOJIS = {
    r"\b(money|rich|dollar|cash|profit|earn|wealth|income|पैसे|पैसा|रुपये|रुपया|धन|कमाई|अमीर|paise|paisa|kamai|dhan|crore|lakh)\b": "💰",
    r"\b(fire|hot|lit|insane|crazy|आग|खतरनाक|कहर|बवाल|कातिल|aag|bawal|shandar|toofan)\b": "🔥",
    r"\b(shock|shocking|unbelievable|surprising|secret|truth|सच|रहस्य|हैरान|चौंक|धमाका|चमत्कार|sach|hairan|rahasya|shock)\b": "😱",
    r"\b(win|winner|victory|champion|clutch|जीत|विजेता|शान|टॉप|jeet|vijay)\b": "🏆",
    r"\b(danger|warning|mistake|risk|trap|fail|खतरा|गलती|सावधान|धोखा|khatra|galti|savdhan|dhokha)\b": "⚠️",
    r"\b(rocket|grow|growth|fast|scale|boost|boom|रॉकेट|तरक्की|उड़ान|rocket|growth)\b": "🚀",
    r"\b(dead|kill|headshot|knock|die|death|मार|मौत|खत्म|डेड|mar|maut|khatam)\b": "💀",
    r"\b(love|heart|passion|प्यार|दिल|मोहब्बत|pyar|dil|mohabbat)\b": "❤️",
    r"\b(think|why|how|mind|idea|brain|solution|सोच|आइडिया|दिमाग|उपाय|soch|dimag)\b": "💡",
    r"\b(laugh|funny|joke|meme|lol|हंसी|मजाक|जोक|hasi|majak)\b": "😂",
    r"\b(time|clock|wait|hurry|delay|समय|वक्त|देर|samay|waqt)\b": "⏳",
    r"\b(power|strong|gym|muscle|ताकत|दम|हिम्मत|taakat|dum|himmat)\b": "💪",
    r"\b(stop|never|don't|no|रुक|मत|नहीं|rok|ruk|mat|nahi)\b": "🛑"
}


def _get_emoji_for_word(word_clean):
    lower = word_clean.lower()
    for pattern, emoji in KEYWORD_EMOJIS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            return emoji
    return ""


def _ass_time(seconds):
    total = round(max(0.0, float(seconds)) * 100)
    hours = total // 360000
    minutes = (total % 360000) // 6000
    secs = (total % 6000) // 100
    centiseconds = total % 100
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"


def create_animated_captions(
    words,
    output_file,
    style_name="hormozi",
    highlight_color="yellow",
    enable_emojis=True,
    group_size=4
):
    """
    Generates high-energy, animated ASS captions with word-level highlights.
    Guarantees strictly sequential, non-overlapping subtitle events.
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not words:
        output_path.write_text("", encoding="utf-8-sig")
        return str(output_path)

    # 1. Strictly sort and eliminate any timestamp overlaps
    sorted_words = sorted(words, key=lambda w: float(w["start"]))
    clean_words = []

    for w in sorted_words:
        start = max(0.0, float(w["start"]))
        end = max(start + 0.05, float(w["end"]))
        raw_text = str(w.get("text", "")).strip()
        safe_text = re.sub(r"[{}\\\r\n]", "", raw_text)

        if not safe_text:
            continue

        if clean_words:
            prev = clean_words[-1]
            # If current word starts before previous ended, clamp previous end
            if start < prev["end"]:
                prev["end"] = start

            # Avoid tiny or negative duration
            if prev["end"] <= prev["start"]:
                prev["end"] = prev["start"] + 0.08
                if start < prev["end"]:
                    start = prev["end"]
                    end = max(start + 0.1, end)

        clean_words.append({
            "start": start,
            "end": end,
            "text": safe_text
        })

    if not clean_words:
        output_path.write_text("", encoding="utf-8-sig")
        return str(output_path)

    active_color = COLOR_PALETTES.get(highlight_color.lower(), COLOR_PALETTES["yellow"])
    white_color = "&H00FFFFFF&"
    black_color = "&H00000000&"
    dark_shadow = "&H80000000&"

    # Define style-specific parameters
    if style_name == "mrbeast":
        font_name = "Noto Sans Devanagari"
        font_size = 84
        outline = 5
        shadow = 3
        pos_y = 1250
        bounce_tag = r"{\c" + active_color + r"\fscx130\fscy130\t(0,100,\fscx100\fscy100)}"
    elif style_name == "minimal":
        font_name = "Noto Sans Devanagari"
        font_size = 68
        outline = 2
        shadow = 1
        pos_y = 1450
        bounce_tag = r"{\c" + active_color + r"\fscx108\fscy108\t(0,80,\fscx100\fscy100)}"
    elif style_name == "neon":
        font_name = "Noto Sans Devanagari"
        font_size = 78
        outline = 4
        shadow = 4
        pos_y = 1350
        active_color = COLOR_PALETTES.get(highlight_color.lower(), "&H00FFFF00&")
        bounce_tag = r"{\c" + active_color + r"\3c&H00FF00FF&\fscx120\fscy120\t(0,120,\fscx100\fscy100)}"
    else:  # 'hormozi' default
        font_name = "Noto Sans Devanagari"
        font_size = 76
        outline = 4
        shadow = 2
        pos_y = 1400
        bounce_tag = r"{\c" + active_color + r"\fscx118\fscy118\t(0,110,\fscx100\fscy100)}"

    header = f"""[Script Info]
Title: Shorts Maker Animated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,{font_name},{font_size},{white_color},{active_color},{black_color},{dark_shadow},-1,0,1,{outline},{shadow},2,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for i in range(0, len(clean_words), group_size):
        group = clean_words[i:i + group_size]
        if not group:
            continue

        next_group_start = clean_words[i + group_size]["start"] if (i + group_size) < len(clean_words) else None

        for active_index, active_word in enumerate(group):
            start = active_word["start"]

            # CRITICAL: Next dialogue starts exactly when this dialogue ends.
            # This completely eliminates dual overlapping subtitles!
            if active_index + 1 < len(group):
                end = group[active_index + 1]["start"]
            else:
                end = active_word["end"]
                if next_group_start is not None and end > next_group_start:
                    end = next_group_start

            if end <= start:
                end = start + 0.1

            caption_parts = []
            for j, item in enumerate(group):
                safe_word = item["text"]

                if j == active_index:
                    emoji = _get_emoji_for_word(safe_word) if enable_emojis else ""
                    emoji_str = f" {emoji}" if emoji else ""

                    caption_parts.append(
                        f"{bounce_tag}{safe_word.upper()}{emoji_str}{{\\c{white_color}\\fscx100\\fscy100}}"
                    )
                else:
                    caption_parts.append(safe_word.upper())

            caption = " ".join(caption_parts)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
                f"Pop,,0,0,0,,{{\\an2\\pos(540,{pos_y})}}{caption}"
            )

    output_path.write_text(header + "\n".join(events), encoding="utf-8-sig")
    return str(output_path)
