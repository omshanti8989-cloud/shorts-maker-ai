import os
import uuid
from pathlib import Path

import streamlit as st
from googleapiclient.discovery import build

from engine import process_video, process_youtube_video


# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Shorts Maker AI",
    page_icon="🎬",
    layout="wide"
)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# API KEY
# --------------------------------------------------

def get_youtube_api_key():
    try:
        return (
            st.secrets.get("YOUTUBE_API_KEY")
            or os.getenv("YOUTUBE_API_KEY")
        )
    except Exception:
        return os.getenv("YOUTUBE_API_KEY")


def get_youtube_api():
    api_key = get_youtube_api_key()

    if not api_key:
        raise ValueError(
            "YouTube API key is missing. "
            "Add YOUTUBE_API_KEY in Streamlit Secrets."
        )

    return build(
        "youtube",
        "v3",
        developerKey=api_key,
        cache_discovery=False
    )


# --------------------------------------------------
# YOUTUBE VIDEO DISCOVERY
# --------------------------------------------------

def get_popular_videos(max_results=10):
    youtube = get_youtube_api()

    response = youtube.videos().list(
        part="snippet,statistics",
        chart="mostPopular",
        regionCode="IN",
        maxResults=max_results
    ).execute()

    videos = []

    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})

        videos.append({
            "id": item["id"],
            "title": snippet.get("title", "Untitled"),
            "channel": snippet.get("channelTitle", "Unknown"),
            "thumbnail": snippet.get("thumbnails", {})
                .get("medium",
