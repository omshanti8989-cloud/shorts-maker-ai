import os
import re


def create_animated_captions(words, output_file):
    """
    Create 3-5 word ASS captions.
    Active word: yellow.
    Other words: white.
    Position: lower middle.
    Animation: pop / bounce.
    """

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    header = """[Script Info]
Title: Shorts Maker Animated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Noto Sans Devanagari,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,1,4,2,2,70,70,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def ass_time(seconds):
        total = round(seconds * 100)
        hours = total // 360000
        minutes = (total % 360000) // 6000
        secs = (total % 6000) // 100
        centiseconds = total % 100
        return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"

    events = []
    group_size = 4

    for i in range(0, len(words), group_size):
        group = words[i:i + group_size]

        if not group:
            continue

        for active_index, active_word in enumerate(group):
            start = active_word["start"]
            end = active_word["end"]

            if end <= start:
                continue

            caption_parts = []

            for j, item in enumerate(group):
                safe_word = re.sub(r"[{}]", "", item["text"])

                if j == active_index:
                    caption_parts.append(
                        r"{\c&H0000FFFF&\fscx115\fscy115\t(0,120,\fscx100\fscy100)}"
                        + safe_word
                        + r"{\c&H00FFFFFF&}"
                    )
                else:
                    caption_parts.append(safe_word)

            caption = " ".join(caption_parts)

            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},"
                f"Pop,,0,0,0,,{{\\an2\\pos(540,1450)}}{caption}"
            )

    with open(output_file, "w", encoding="utf-8-sig") as file:
        file.write(header)
        file.write("\n".join(events))

    print("Animated captions created:", output_file)