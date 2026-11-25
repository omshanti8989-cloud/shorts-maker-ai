# 🎬 Shorts Maker AI - Automated Viral Video to Shorts SaaS

Transform long YouTube videos and local video recordings into high-converting 9:16 vertical Shorts, Reels, and TikToks with automated speech recognition, Smart Face Tracking, viral highlight scoring, bouncing animated subtitles, and integrated **Razorpay** subscription payments.

---

## ✨ Features

- **🎯 Smart Face Tracking & 9:16 Auto-Crop**: Uses OpenCV to track active speakers smoothly, keeping faces centered in vertical format. Also supports blurred background and dual-speaker split screen.
- **🔥 Bouncing ASS Captions**: Synchronized multi-word animated captions with keyword color pop effects (Hormozi, MrBeast, Neon presets in Hindi, Hinglish, and English).
- **🤖 Gemini AI Viral Moment Detection**: Scans transcripts for curiosity hooks, question prompts, and emotional triggers to automatically extract high-retention clips.
- **💳 Razorpay Payment & Subscription Gateway**: Integrated with Razorpay Checkout for instant plan upgrades (UPI, Google Pay, PhonePe, Cards, NetBanking). Funds settle directly into your linked merchant bank account.
- **⚡ Faster-Whisper Powered**: CPU and GPU-optimized transcription pipeline with zero unnecessary audio re-encodes.
- **☁️ Cloud & Docker Ready**: Pre-configured with `Dockerfile`, `packages.txt`, and `.env.example` for instant deployment on Streamlit Cloud, Render, Railway, or AWS.

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- **Python 3.10+**
- **FFmpeg**: Ensure FFmpeg is installed and added to your system `PATH`.
  - Windows: `winget install Gyan.FFmpeg`
  - Linux: `sudo apt-get install -y ffmpeg`

### 2. Clone and Install
```bash
git clone https://github.com/omshanti8989-cloud/shorts-maker-ai.git
cd shorts-maker-ai

# Create virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Launch App
```bash
streamlit run app.py
```

---

## 💳 Razorpay Payment Setup (How Money Reaches Your Bank)

1. Sign up on [Razorpay](https://razorpay.com) and complete KYC verification.
2. Go to **Account & Settings > API Keys** and generate:
   - `RAZORPAY_KEY_ID` (starts with `rzp_live_...` or `rzp_test_...`)
   - `RAZORPAY_KEY_SECRET`
3. Enter your linked bank account in the Razorpay Dashboard (where payouts are deposited via standard T+2 settlement).
4. Configure your keys:
   - Locally: Create a `.env` file (copy from `.env.example`) or configure in `.streamlit/secrets.toml`.
   - In Cloud: Add them as Environment Variables in your hosting dashboard.

---

## ☁️ Cloud Deployment Options

### Option A: Streamlit Community Cloud (Recommended & Free)
1. Push this repository to GitHub.
2. Visit [share.streamlit.io](https://share.streamlit.io/) and select your repository.
3. Set the main file path to `app.py`.
4. Under **Advanced Settings > Secrets**, paste the keys from `.streamlit/secrets.toml.example`.
5. Streamlit Cloud automatically installs FFmpeg from `packages.txt`!

### Option B: Docker Container (Render, Railway, DigitalOcean, AWS EC2)
Build and run using Docker:
```bash
docker build -t shorts-maker-ai .
docker run -p 8501:8501 --env-file .env shorts-maker-ai
```
Or using Docker Compose:
```bash
docker-compose up -d
```

---

## 🔒 Security Notice

**Never commit private keys, credentials, or downloaded videos to GitHub.**
The repository includes a comprehensive `.gitignore` that automatically excludes:
- `client_secret.json`, `token.json`, `api key.txt`
- `.streamlit/secrets.toml`, `.env`
- `downloads/`, `clips/`, `subtitles/`, and temporary video files
- `users.db` and SQLite databases

---

## 📄 License
MIT License. Built for creators and developers.
