import os
import uuid
from pathlib import Path

import streamlit as st
import yt_dlp

from engine import process_video

PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

st.set_page_config(
    page_title="Shorts Maker AI",
    page_icon="🎬",
    layout="wide"
)
st.markdown(
    """
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#111827">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """,
    unsafe_allow_html=True
)
st.title("🎬 Shorts Maker AI")
st.subheader("Turn long videos into engaging Shorts automatically")
st.caption("Your videos are processed by your own Shorts Maker engine.")

st.divider()
st.header("1. Choose your video")

source = st.radio(
    "Video source",
    ["Upload video from device", "YouTube video link"],
    horizontal=True
)

video_path = None

if source == "Upload video from device":
    uploaded = st.file_uploader(
        "Choose a video",
        type=["mp4", "mkv", "mov", "avi", "webm", "m4v"]
    )
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".mp4"
        video_path = DOWNLOAD_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
        video_path.write_bytes(uploaded.getbuffer())
        st.success(f"Video uploaded: {uploaded.name}")
else:
    youtube_url = st.text_input(
        "Paste YouTube video URL",
        placeholder="https://www.youtube.com/watch?v=..."
    )

st.divider()
st.header("2. Customize your Shorts")
number_of_shorts = st.number_input(
    "How many Shorts do you want?",
    min_value=1,
    max_value=20,
    value=5,
    step=1
)

if st.button("🚀 Generate Shorts", type="primary", use_container_width=True):
    try:
        if source == "Upload video from device":
            if video_path is None:
                st.error("Please upload a video first.")
                st.stop()
            selected_video = str(video_path)
        else:
            if not youtube_url.strip():
                st.error("Please enter a YouTube link.")
                st.stop()

            st.info("Downloading YouTube video...")
            download_options = {
                "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
                "outtmpl": str(DOWNLOAD_DIR / "youtube_video.%(ext)s"),
                "merge_output_format": "mp4",
                "overwrites": True,
                "nopart": True,
                "js_runtimes": {"deno": {}},
                "remote_components": ["ejs:github"],
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(download_options) as ydl:
                ydl.download([youtube_url.strip()])

            candidates = [
                p for p in DOWNLOAD_DIR.glob("youtube_video.*")
                if not p.name.endswith((".part", ".ytdl"))
            ]
            if not candidates:
                st.error("The YouTube download did not produce a video file.")
                st.stop()
            selected_video = str(next(
                (p for p in candidates if p.suffix.lower() == ".mp4"),
                candidates[0]
            ))

        st.divider()
        st.header("3. Processing")
        status = st.empty()
        progress = st.progress(0)

        def update_progress(message, value=None):
            status.write(message)
            if value is not None:
                progress.progress(max(0.0, min(1.0, float(value))))

        results = process_video(
            selected_video,
            int(number_of_shorts),
            progress_callback=update_progress
        )

        st.success(f"Finished! Created {len(results)} Short(s).")
        st.header("4. Preview and download")
        for index, result in enumerate(results, 1):
            result_path = Path(result)
            st.subheader(f"Short {index}")
            st.video(str(result_path))
            with open(result_path, "rb") as file:
                st.download_button(
                    label=f"⬇️ Download Short {index}",
                    data=file,
                    file_name=result_path.name,
                    mime="video/mp4",
                    key=f"download_{index}"
                )

    except Exception as error:
        st.error(f"Processing failed: {error}")
        st.exception(error)

st.divider()
st.caption("Shorts Maker AI • Python • Whisper Tiny • FFmpeg")
st.components.v1.html(
    """
    <script>
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function() {
            navigator.serviceWorker.register(
                "/app/static/service-worker.js"
            ).then(function(registration) {
                console.log("PWA Service Worker registered!");
            }).catch(function(error) {
                console.log("Service Worker registration failed:", error);
            });
        });
    }
    </script>
    """,
    height=0
)