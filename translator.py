import os
import re
import json

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def translate_words_to_language(words, target_language="hi", api_key=None):
    """
    Translates or transliterates timestamped words into the desired subtitle language:
    - 'hi': Hindi in Devanagari script (e.g. 'यह सच जानकर आप हैरान रह जाएंगे')
    - 'hinglish': Conversational Hindi in Roman/English alphabet (e.g. 'Yeh sach jaan kar aap heran ho jaoge')
    - 'en': English
    - 'original': Preserves original video language
    """
    if not words or target_language in ("original", None, ""):
        return words

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key or not HAS_GENAI:
        return words

    try:
        start_time = float(words[0]["start"])
        end_time = float(words[-1]["end"])
        duration = max(0.5, end_time - start_time)
        original_text = " ".join(str(w["text"]).strip() for w in words).strip()

        if not original_text:
            return words

        client = genai.Client(api_key=api_key)

        lang_instructions = {
            "hi": "Translate into natural, punchy Hindi written in Devanagari script (e.g. 'यह बात जानकर आप हैरान रह जाएंगे'). Return ONLY Devanagari Hindi words.",
            "hinglish": "Translate into conversational Hinglish written in English/Latin letters (e.g. 'Yeh baat jaan kar aap heran ho jaoge'). Keep viral creator tone.",
            "en": "Translate into clear, high-energy English."
        }
        instruction = lang_instructions.get(target_language, lang_instructions["hi"])

        prompt = f"""You are a professional subtitle translator for viral Instagram Reels and YouTube Shorts.
{instruction}

Sentence to translate:
"{original_text}"

Return ONLY a JSON array of individual words in sequential order, matching the translation:
["word1", "word2", "word3", ...]
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )

        translated_words = json.loads(response.text.strip())
        if not translated_words or not isinstance(translated_words, list):
            return words

        # Distribute timestamps evenly across translated words
        step = duration / len(translated_words)
        new_words = []
        for idx, tw in enumerate(translated_words):
            clean_tw = str(tw).strip()
            if not clean_tw:
                continue
            w_start = start_time + idx * step
            w_end = start_time + (idx + 1) * step
            new_words.append({
                "start": round(w_start, 2),
                "end": round(w_end, 2),
                "text": clean_tw
            })

        return new_words

    except Exception as e:
        print(f"Translation to {target_language} skipped ({e}); using original captions.")
        return words
