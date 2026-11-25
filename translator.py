import os
import re
import json

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# =====================================================================
# EXTENSIVE SPOKEN HINDI TO HINGLISH DICTIONARY (Viral Creator Style)
# =====================================================================
COMMON_HINDI_TO_HINGLISH = {
    # Greetings & Common openers
    "नमस्ते": "Namaste", "नमस्कार": "Namaskar", "हेलो": "Hello", "हाय": "Hey",
    "दोस्तों": "dosto", "दोस्त": "dost", "यार": "yaar", "भाई": "bhai",
    "आज": "aaj", "कल": "kal", "परसों": "parso", "रोज": "roz",

    # Pronouns
    "हम": "hum", "मैं": "main", "मुझे": "mujhe", "मुझको": "mujhko",
    "आप": "aap", "आपको": "aapko", "आपसे": "aapse", "आपका": "aapka", "आपकी": "aapki", "आपके": "aapke",
    "तुम": "tum", "तुम्हें": "tumhe", "तुम्हारा": "tumhara", "तुम्हारी": "tumhari", "तुम्हारे": "tumhare",
    "यह": "yeh", "ये": "ye", "वह": "woh", "वो": "woh", "वे": "ve",
    "इस": "iss", "इसे": "isse", "इसका": "iska", "इसकी": "iski", "इसके": "iske",
    "उस": "uss", "उसे": "usse", "उसका": "uska", "उसकी": "uski", "उसके": "uske",
    "इन": "in", "इन्हें": "inhe", "इनका": "inka", "इनकी": "inki", "इनके": "inke",
    "उन": "un", "उन्हें": "unhe", "उनका": "unka", "उनकी": "unki", "उनके": "unke",
    "खुद": "khud", "अपना": "apna", "अपनी": "apni", "अपने": "apne",

    # Helping verbs & Tenses
    "है": "hai", "हैं": "hain", "था": "tha", "थी": "thi", "थे": "the",
    "हो": "ho", "हूँ": "hoon", "हुए": "huye", "हुई": "huyi", "हुआ": "hua",
    "होगा": "hoga", "होगी": "hogi", "होंगे": "honge", "होता": "hota", "होती": "hoti", "होते": "hote",
    "रहना": "rahna", "रहा": "raha", "रही": "rahi", "रहे": "rahe",

    # Core action verbs
    "बात": "baat", "करना": "karna", "करते": "karte", "करती": "karti", "करता": "karta",
    "करने": "karne", "करेंगे": "karenge", "करूंगा": "karunga", "करूंगी": "karungi",
    "किया": "kiya", "किए": "kiye", "की": "ki", "कर": "kar", "करो": "karo",
    "वाले": "wale", "वाला": "wala", "वाली": "wali",
    "सकते": "sakte", "सकता": "sakta", "सकती": "sakti", "सके": "sake",
    "चाहिए": "chahiye", "चाहता": "chahta", "चाहती": "chahti", "चाहते": "chahte",
    "जानते": "jaante", "जानता": "jaanta", "जानती": "jaanti", "जानना": "jaanna",
    "पता": "pata", "मालूम": "maloom",
    "देख": "dekh", "देखो": "dekho", "देखना": "dekhna", "देखा": "dekha", "देखते": "dekhte",
    "सुन": "sun", "सुनो": "suno", "सुनना": "sunna", "सुना": "suna", "सुनते": "sunte",
    "बोल": "bol", "बोलो": "bolo", "बोलना": "bolna", "बोला": "bola", "बोलते": "bolte",
    "कहना": "kahna", "कहा": "kaha", "कहो": "kaho",
    "जाना": "jaana", "जाओ": "jao", "जाते": "jaate", "जाता": "jaata", "जाती": "jaati",
    "गया": "gaya", "गई": "gayi", "गए": "gaye",
    "आना": "aana", "आओ": "aao", "आया": "aaya", "आई": "aayi", "आए": "aaye", "आते": "aate",
    "लेना": "lena", "लो": "lo", "लिया": "liya", "लिए": "liye",
    "देना": "dena", "दो": "do", "दिया": "diya", "दिए": "diye",
    "रखना": "rakhna", "रखो": "rakho", "रखा": "rakha",
    "सोचना": "sochna", "सोचो": "socho", "सोचा": "socha", "सोच": "soch",

    # Prepositions & Connectors
    "के": "ke", "का": "ka", "की": "ki", "में": "mein", "पर": "par", "से": "se", "को": "ko",
    "ने": "ne", "तक": "tak", "साथ": "saath", "बिना": "bina", "बारे": "baare",
    "अगर": "agar", "यदि": "yadi", "लेकिन": "lekin", "परंतु": "parantu", "मगर": "magar",
    "क्योंकि": "kyunki", "इसलिए": "isliye", "ताकि": "taaki", "और": "aur", "तथा": "tatha",
    "भी": "bhi", "तो": "toh", "या": "ya", "अथवा": "athwa",

    # Question words
    "क्या": "kya", "क्यों": "kyun", "कैसे": "kaise", "कब": "kab", "कहाँ": "kahan", "कौन": "kaun",
    "कितना": "kitna", "कितनी": "kitni", "कितने": "kitne",

    # Quantity & Modifiers
    "नहीं": "nahi", "हाँ": "haan", "ना": "na", "मत": "mat",
    "बहुत": "bohot", "ज्यादा": "zyada", "कम": "kam", "थोड़ा": "thoda", "थोड़ी": "thodi",
    "काफी": "kaafi", "सिर्फ": "sirf", "केवल": "kewal", "बस": "bas",
    "सब": "sab", "सभी": "sabhi", "सारा": "saara", "सारी": "saari", "सारे": "saare",
    "पूरा": "poora", "पूरी": "poori", "पूरे": "poore",
    "कुछ": "kuch", "कोई": "koi", "हर": "har",

    # Common nouns & Viral descriptors
    "लोग": "log", "लोगों": "logo", "इंसान": "insan", "व्यक्ति": "vyakti",
    "समय": "samay", "वक्त": "waqt", "साल": "saal", "महीना": "mahina", "दिन": "din", "रात": "raat",
    "पैसा": "paisa", "पैसे": "paise", "रुपया": "rupya", "रुपये": "rupaye", "करोड़": "crore", "लाख": "lakh",
    "काम": "kaam", "नाम": "naam", "चीज": "cheez", "बातें": "baatein",
    "सच": "sach", "झूठ": "jhooth", "सच्चाई": "sacchai", "हकीकत": "haqeeqat",
    "रहस्य": "rahasya", "सीक्रेट": "secret", "ट्रिक": "trick", "तरीका": "tareeka", "तरीके": "tareeke",
    "गलती": "galti", "गलतियां": "galtiyan", "खतरा": "khatra", "खतरनाक": "khatarnak",
    "हैरान": "hairan", "चौंक": "chaunk", "धमाका": "dhamaka", "बवाल": "bawal",
    "अच्छा": "accha", "अच्छी": "acchi", "अच्छे": "acche", "बढ़िया": "badhiya", "शानदार": "shandar",
    "बुरा": "bura", "बुरी": "buri", "गलत": "galat", "सही": "sahi",
    "बड़ा": "bada", "बड़ी": "badi", "बड़े": "bade", "छोटा": "chhota", "छोटी": "chhoti", "छोटे": "chhote",
    "शुरू": "shuru", "शुरुआत": "shuruat", "खत्म": "khatam", "अंत": "ant",
    "सबूत": "saboot", "फायदा": "fayda", "नुकसान": "nuksan", "सवाल": "sawal", "जवाब": "jawab",
    "दुनिया": "duniya", "देश": "desh", "जिंदगी": "zindagi", "जीवन": "jeevan",
    "दिमाग": "dimag", "दिल": "dil", "सोच": "soch",

    # Social & Tech terms often transcribed in Devanagari by Whisper
    "वीडियो": "video", "चैनल": "channel", "सब्सक्राइब": "subscribe", "लाइक": "like",
    "शेयर": "share", "फॉलो": "follow", "कमेंट": "comment", "व्यूज": "views",
    "फॉलोअर्स": "followers", "यूट्यूब": "YouTube", "गूगल": "Google", "इंटरनेट": "Internet",
    "मोबाइल": "mobile", "फोन": "phone", "कंप्यूटर": "computer", "लैपटॉप": "laptop"
}

# Phonetic character maps for words not in the dictionary
DEVANAGARI_CONSONANTS = {
    '\u0915': 'k', '\u0916': 'kh', '\u0917': 'g', '\u0918': 'gh', '\u0919': 'ng',
    '\u091a': 'ch', '\u091b': 'chh', '\u091c': 'j', '\u091d': 'jh', '\u091e': 'ny',
    '\u091f': 't', '\u0920': 'th', '\u0921': 'd', '\u0922': 'dh', '\u0923': 'n',
    '\u0924': 't', '\u0925': 'th', '\u0926': 'd', '\u0927': 'dh', '\u0928': 'n',
    '\u092a': 'p', '\u092b': 'f', '\u092c': 'b', '\u092d': 'bh', '\u092e': 'm',
    '\u092f': 'y', '\u0930': 'r', '\u0932': 'l', '\u0935': 'v',
    '\u0936': 'sh', '\u0937': 'sh', '\u0938': 's', '\u0939': 'h',
    '\u0958': 'q', '\u0959': 'kh', '\u095a': 'gh', '\u095b': 'z',
    '\u095c': 'd', '\u095d': 'dh', '\u095e': 'f', '\u095f': 'y'
}

DEVANAGARI_VOWELS = {
    '\u0905': 'a', '\u0906': 'aa', '\u0907': 'i', '\u0908': 'ee',
    '\u0909': 'u', '\u090a': 'oo', '\u090b': 'ri', '\u090f': 'e',
    '\u0910': 'ai', '\u0913': 'o', '\u0914': 'au'
}

DEVANAGARI_MATRAS = {
    '\u093e': 'a', '\u093f': 'i', '\u0940': 'ee', '\u0941': 'u',
    '\u0942': 'oo', '\u0943': 'ri', '\u0947': 'e', '\u0948': 'ai',
    '\u094b': 'o', '\u094c': 'au', '\u0902': 'n', '\u0901': 'n',
    '\u0903': 'h'
}


def devanagari_to_hinglish(word_str):
    """
    Converts a single Devanagari word into natural, readable Roman Hinglish.
    If the word is already English or Latin, returns it untouched.
    """
    if not word_str:
        return word_str

    # If the word contains no Devanagari characters, it is already English/Latin
    if not re.search(r'[\u0900-\u097F]', word_str):
        return word_str

    # Extract leading/trailing punctuation
    prefix_match = re.match(r'^[^\w\u0900-\u097F]+', word_str)
    prefix = prefix_match.group(0) if prefix_match else ""
    suffix_match = re.search(r'[^\w\u0900-\u097F]+$', word_str)
    suffix = suffix_match.group(0) if suffix_match else ""

    clean_devanagari = word_str[len(prefix):len(word_str) - len(suffix) if suffix else len(word_str)].strip()

    # 1. Check common spoken Hindi dictionary
    if clean_devanagari in COMMON_HINDI_TO_HINGLISH:
        return f"{prefix}{COMMON_HINDI_TO_HINGLISH[clean_devanagari]}{suffix}"

    # 2. Algorithmic phonetic transliteration
    result = []
    i = 0
    n = len(clean_devanagari)

    while i < n:
        char = clean_devanagari[i]

        if char in DEVANAGARI_CONSONANTS:
            # Check if followed by halant (virama)
            if i + 1 < n and clean_devanagari[i + 1] == '\u094d':
                result.append(DEVANAGARI_CONSONANTS[char])
                i += 2
                continue
            # Check if followed by matra
            elif i + 1 < n and clean_devanagari[i + 1] in DEVANAGARI_MATRAS:
                result.append(DEVANAGARI_CONSONANTS[char] + DEVANAGARI_MATRAS[clean_devanagari[i + 1]])
                i += 2
                continue
            else:
                # Schwa deletion rule in modern Hindi: terminal consonant has no trailing 'a'
                if i + 1 == n and len(clean_devanagari) > 1:
                    result.append(DEVANAGARI_CONSONANTS[char])
                else:
                    result.append(DEVANAGARI_CONSONANTS[char] + 'a')
                i += 1
                continue

        elif char in DEVANAGARI_VOWELS:
            result.append(DEVANAGARI_VOWELS[char])
            i += 1
            continue

        elif char in DEVANAGARI_MATRAS:
            result.append(DEVANAGARI_MATRAS[char])
            i += 1
            continue

        elif char == '\u094d':  # Stray halant
            i += 1
            continue

        else:
            result.append(char)
            i += 1

    transliterated = "".join(result)
    return f"{prefix}{transliterated}{suffix}"


def convert_words_to_hinglish_offline(words):
    """
    Offline transliteration pipeline:
    - Leaves English words 100% in English
    - Converts any Devanagari Hindi words into natural Hinglish (Roman script)
    """
    processed = []
    for w in words:
        raw_text = str(w.get("text", "")).strip()
        if not raw_text:
            continue
        hinglish_text = devanagari_to_hinglish(raw_text)
        processed.append({
            "start": w["start"],
            "end": w["end"],
            "text": hinglish_text
        })
    return processed


def translate_words_to_language(words, target_language="hinglish", api_key=None):
    """
    Translates/Transliterates timestamped words:
    - 'hinglish': (DEFAULT) Spoken English remains in English; spoken Hindi is converted to Hinglish.
                  NO pure Devanagari characters appear in captions.
    - 'en': Translates into clear, high-energy English.
    - 'hi': Translates into pure Devanagari Hindi (if explicitly requested).
    - 'original': Keeps original text.
    """
    if not words:
        return words

    # If target is original, but user never wants pure Devanagari, convert any Devanagari to Hinglish!
    if target_language in ("original", None, ""):
        target_language = "hinglish"

    # Check if there are any Devanagari characters present
    original_text = " ".join(str(w.get("text", "")).strip() for w in words).strip()
    has_devanagari = bool(re.search(r'[\u0900-\u097F]', original_text))

    # If the text is already 100% English and target is Hinglish or original, no conversion needed!
    if not has_devanagari and target_language == "hinglish":
        return words

    api_key = api_key or os.environ.get("GEMINI_API_KEY")

    # If Gemini API is available, use LLM for viral creator-grade Hinglish
    if api_key and HAS_GENAI:
        try:
            start_time = float(words[0]["start"])
            end_time = float(words[-1]["end"])
            duration = max(0.5, end_time - start_time)

            client = genai.Client(api_key=api_key)

            if target_language == "hinglish":
                instruction = (
                    "You are an expert subtitle editor for viral Indian YouTube Shorts & Reels "
                    "(like Ranveer Allahbadia, Dhruv Rathee, Raj Shamani). "
                    "Convert any Hindi speech written in Devanagari into conversational, natural Hinglish "
                    "written strictly in the English/Roman alphabet (e.g. 'Yeh baat jaan kar aap hairan ho jaenge'). "
                    "CRITICAL RULES: "
                    "1. Any English words spoken (e.g. 'marketing', 'channel', 'business', 'mindset', 'AI', 'video', 'subscribe') "
                    "MUST remain in standard English! "
                    "2. Do NOT output ANY Devanagari script characters (क, ख, ग, etc.). "
                    "3. If a sentence has both Hindi and English words, output seamless Hinglish (e.g. 'Agar aap apna business scale karna chahte hain')."
                )
            elif target_language == "en":
                instruction = "Translate into clear, high-energy English for viral Shorts. Keep creator tone."
            else:
                instruction = "Translate into natural Hindi written in Devanagari script."

            prompt = f"""{instruction}

Sentence to convert:
"{original_text}"

Return ONLY a JSON array of individual words in sequential order, matching the timing of the sentence:
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
            if translated_words and isinstance(translated_words, list):
                # Ensure no rogue Devanagari remained in Gemini's response
                clean_list = []
                for tw in translated_words:
                    word_str = str(tw).strip()
                    if word_str:
                        if target_language == "hinglish" and re.search(r'[\u0900-\u097F]', word_str):
                            word_str = devanagari_to_hinglish(word_str)
                        clean_list.append(word_str)

                if clean_list:
                    step = duration / len(clean_list)
                    new_words = []
                    for idx, tw in enumerate(clean_list):
                        w_start = start_time + idx * step
                        w_end = start_time + (idx + 1) * step
                        new_words.append({
                            "start": round(w_start, 2),
                            "end": round(w_end, 2),
                            "text": tw
                        })
                    return new_words

        except Exception as e:
            print(f"Gemini Hinglish conversion error: {e}. Falling back to offline transliterator.")

    # Offline high-accuracy fallback (100% offline, guaranteed no pure Hindi Devanagari characters)
    if target_language == "hinglish":
        return convert_words_to_hinglish_offline(words)

    return words
