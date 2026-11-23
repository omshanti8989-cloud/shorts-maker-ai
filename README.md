# 🎬 Shorts Maker AI

An AI-powered web application that turns long YouTube videos and downloaded files into viral, high-retention vertical Shorts & Instagram Reels (9:16).

---

## ✨ Features

- 🎁 **1 Free Video + Pro Subscription Engine:**
  - Built-in SQLite user and credit management (`users.db`).
  - Users enter their email to claim **1 Free Video Conversion**.
  - Subsequent videos trigger the high-converting **Pro Subscription Paywall**.
  - **Razorpay Integration:** Supports UPI (PhonePe, Google Pay, Paytm), Cards, and Netbanking (₹499/month).
  - Built-in Simulation/Test mode for instant testing without paying.

- 🎯 **Smart Face Tracking & Auto-Reframing:**
  - Uses OpenCV computer vision to automatically detect and follow active speakers.
  - Crops 16:9 widescreen footage into full-screen 9:16 vertical video with smooth framing.
  - Supports **Dual-Speaker Split Screen** (Top/Bottom) for interviews and podcasts.
  - Optional **Ambient Blurred Background** mode.

- 🤖 **Gemini AI Viral Moment Selection:**
  - Ingests word-level transcripts and prompts Google Gemini to identify the highest retention 25–60s segments.
  - Rates clips with a **Viral Score (1-100)**, generates engaging titles, hooks, and punchline rationale.
  - Automatic fallback to lexical heuristic & live-chat reaction burst scoring if no API key is provided.

- 🔥 **Dynamic Animated Captions (Hormozi & MrBeast Style):**
  - Word-by-word karaoke highlighting with pop/bounce scaling.
  - Preset styles: **Hormozi**, **MrBeast**, **Clean Minimalist**, and **Cyber Neon**.
  - Customizable active word highlight colors (Yellow, Green, Cyan, Orange, Magenta).
  - **Contextual Emojis:** Automatically adds dynamic emojis (💰 for money, 🔥 for hype, 😱 for shock, 🏆 for win).
  - Strictly sequential, non-overlapping subtitle events with Devanagari font support for Hindi, Hinglish, and English.

- ⚡ **Optimized Ingestion & Processing:**
  - YouTube WebVTT caption fast-path avoiding full video downloads just to transcribe.
  - Selective time-range downloading via `yt-dlp` (`download_ranges`) to fetch only the chosen clip seconds.
  - Asynchronous background rendering with FFmpeg.

---

## 🚀 Quick Start

### 1. Install Dependencies
Ensure you have [FFmpeg](https://ffmpeg.org/) installed and available in your system `PATH`.

```bash
pip install -r requirements.txt
```

### 2. Run the Web Application
```bash
streamlit run app.py
```

### 3. (Optional) Configuration & API Keys
You can input your keys in the web sidebar, or define them in `.streamlit/secrets.toml`:
- `GEMINI_API_KEY`: For LLM viral moment selection and scoring.
- `YOUTUBE_API_KEY`: For searching trending YouTube videos and channel uploads.
- `RAZORPAY_KEY_ID` & `RAZORPAY_KEY_SECRET`: For accepting payments in INR via UPI/cards.
