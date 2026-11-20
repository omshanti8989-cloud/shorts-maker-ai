import uuid
from pathlib import Path

import streamlit as st
from googleapiclient.discovery import build

from engine import process_video, process_youtube_video


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


def get_youtube_api():
    api_key = st.secrets.get("YOUTUBE_API_KEY")

    if not api_key:
        raise ValueError("YouTube API key is missing from Streamlit Secrets.")

    return build(
        "youtube",
        "v3",
        developerKey=api_key,
        cache_discovery=False
    )


def get_popular_videos():
    youtube = get_youtube_api()

    response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        chart="mostPopular",
        regionCode="IN",
        maxResults=20
    ).execute()

    videos = []

    for item in response.get("items", []):
        videos.append({
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "video_id": item["id"],
            "url": f"https://www.youtube.com/watch?v={item['id']}",
            "views": item.get("statistics", {}).get("viewCount", "N/A")
        })

    return videos


def get_channel_videos(channel_ids):
    youtube = get_youtube_api()
    videos = []

    for channel_id in channel_ids:

        channel_response = youtube.channels().list(
            part="contentDetails,snippet",
            id=channel_id
        ).execute()

        for channel in channel_response.get("items", []):

            playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

            response = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=20
            ).execute()

            for item in response.get("items", []):

                video_id = item["snippet"]["resourceId"]["videoId"]

                videos.append({
                    "title": item["snippet"]["title"],
                    "channel": channel["snippet"]["title"],
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "views": "Check YouTube"
                })

    return videos


st.title("🎬 Shorts Maker AI")
st.subheader("Turn long videos into engaging Shorts automatically")

st.caption(
    "Discover YouTube videos and generate Shorts using your AI engine."
)

st.divider()

st.header("1. Choose your video source")

source = st.radio(
    "Select source",
    [
        "Upload video from device",
        "YouTube video link",
        "Discover YouTube videos"
    ],
    horizontal=False
)

selected_video = None
selected_url = None


# ---------------------------------
# UPLOAD VIDEO
# ---------------------------------

if source == "Upload video from device":

    uploaded = st.file_uploader(
        "Choose a video",
        type=["mp4", "mkv", "mov", "avi", "webm", "m4v"]
    )

    if uploaded is not None:

        suffix = Path(uploaded.name).suffix or ".mp4"

        video_path = DOWNLOAD_DIR / (
            f"upload_{uuid.uuid4().hex}{suffix}"
        )

        video_path.write_bytes(uploaded.getbuffer())

        selected_video = str(video_path)

        st.success(f"Video uploaded: {uploaded.name}")


# ---------------------------------
# MANUAL YOUTUBE LINK
# ---------------------------------

elif source == "YouTube video link":

    selected_url = st.text_input(
        "Paste YouTube video URL",
        placeholder="https://www.youtube.com/watch?v=..."
    )


# ---------------------------------
# AUTOMATIC YOUTUBE DISCOVERY
# ---------------------------------

elif source == "Discover YouTube videos":

    discovery_type = st.radio(
        "Discovery method",
        [
            "Popular videos in India",
            "Videos from selected channels"
        ]
    )

    if discovery_type == "Popular videos in India":

        if st.button("🔍 Find Popular Videos"):

            try:
                with st.spinner("Finding popular YouTube videos..."):

                    videos = get_popular_videos()

                    st.session_state["discovered_videos"] = videos

            except Exception as error:
                st.error(f"YouTube discovery failed: {error}")


    else:

        channel_text = st.text_area(
            "Enter YouTube Channel IDs",
            placeholder="Enter channel IDs, one per line"
        )

        if st.button("🔍 Find Channel Videos"):

            channel_ids = [
                channel.strip()
                for channel in channel_text.splitlines()
                if channel.strip()
            ]

            if not channel_ids:

                st.warning("Please enter at least one channel ID.")

            else:

                try:
                    with st.spinner("Finding channel videos..."):

                        videos = get_channel_videos(channel_ids)

                        st.session_state["discovered_videos"] = videos

                except Exception as error:
                    st.error(f"Channel discovery failed: {error}")


    discovered = st.session_state.get("discovered_videos", [])

    if discovered:

        st.success(f"Found {len(discovered)} videos.")

        options = [
            f"{video['title']} — {video['channel']}"
            for video in discovered
        ]

        selected_index = st.selectbox(
            "Select a video",
            range(len(options)),
            format_func=lambda index: options[index]
        )

        chosen_video = discovered[selected_index]

        selected_url = chosen_video["url"]

        st.video(selected_url)

        st.caption(f"Channel: {chosen_video['channel']}")

        st.info(
            "Selected video will be processed using your Shorts Maker engine."
        )


# ---------------------------------
# SHORTS SETTINGS
# ---------------------------------

st.divider()

st.header("2. Customize your Shorts")

number_of_shorts = st.number_input(
    "How many Shorts do you want?",
    min_value=1,
    max_value=20,
    value=5,
    step=1
)


# ---------------------------------
# GENERATE SHORTS
# ---------------------------------

if st.button(
    "🚀 Generate Shorts",
    type="primary",
    use_container_width=True
):

    try:

        if source == "Upload video from device":

            if selected_video is None:
                st.error("Please upload a video first.")
                st.stop()

        else:

            if not selected_url or not selected_url.strip():

                st.error("Please select or enter a YouTube video.")
                st.stop()


        st.divider()

        st.header("3. Processing")

        status = st.empty()
        progress = st.progress(0)


        def update_progress(message, value=None):

            status.write(message)

            if value is not None:

                progress.progress(
                    max(0.0, min(1.0, float(value)))
                )


        if source == "Upload video from device":

            results = process_video(
                selected_video,
                int(number_of_shorts),
                progress_callback=update_progress
            )

        else:

            results = process_youtube_video(
                selected_url.strip(),
                int(number_of_shorts),
                progress_callback=update_progress
            )


        st.success(
            f"Finished! Created {len(results)} Short(s)."
        )

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

st.caption(
    "Shorts Maker AI • Python • Whisper • FFmpeg • YouTube Data API"
)


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
