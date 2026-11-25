import os
import io
import uuid
import zipfile
from pathlib import Path

import streamlit as st
from googleapiclient.discovery import build

from engine import process_video, process_youtube_video
import database
import payments

PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

st.set_page_config(
    page_title="Shorts Maker AI - Viral Short & Reel Creator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling, cards, and badges
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FF0055, #7928CA, #4A00E0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .viral-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        background: linear-gradient(135deg, #FF416C, #FF4B2B);
        color: white;
        font-weight: 700;
        font-size: 0.85rem;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    .clip-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 20px;
    }
    .pricing-card {
        background: linear-gradient(145deg, rgba(30, 27, 75, 0.8), rgba(49, 46, 129, 0.5));
        border: 2px solid #818CF8;
        border-radius: 16px;
        padding: 24px;
        margin: 15px 0;
        box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.3);
    }
    .pricing-price {
        font-size: 2.2rem;
        font-weight: 800;
        color: #38BDF8;
    }
    .pro-badge {
        display: inline-block;
        background: linear-gradient(135deg, #10B981, #059669);
        color: white;
        padding: 4px 12px;
        border-radius: 16px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .free-badge {
        display: inline-block;
        background: linear-gradient(135deg, #F59E0B, #D97706);
        color: white;
        padding: 4px 12px;
        border-radius: 16px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    </style>
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#111827">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """,
    unsafe_allow_html=True
)


def get_secret(key, default=""):
    try:
        return st.secrets.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)


# ---------------------------------
# SIDEBAR SETTINGS & CONFIGURATION
# ---------------------------------

with st.sidebar:
    st.image("static/logo.png" if Path("static/logo.png").exists() else "🎬", width=64)
    st.title("⚙️ AI Customization")

    st.subheader("👤 User Account")
    user_email = st.session_state.get("user_email", "")

    if not user_email:
        with st.form("sidebar_email_form"):
            in_email = st.text_input("Enter Email to claim 1 Free Video", placeholder="creator@gmail.com")
            btn_login = st.form_submit_button("Claim 1 Free Video ➔", use_container_width=True)
            if btn_login and in_email.strip():
                st.session_state["user_email"] = in_email.strip().lower()
                st.rerun()
    else:
        user_info = database.get_or_create_user(user_email)
        st.markdown(f"**Logged in:** `{user_email}`")
        if user_info["is_subscribed"]:
            st.markdown('<span class="pro-badge">💎 PRO (Unlimited)</span>', unsafe_allow_html=True)
        elif user_info["free_credits"] > 0:
            st.markdown('<span class="free-badge">🎁 1 Free Video Credit</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="viral-badge">🔒 0 Credits (Upgrade Needed)</span>', unsafe_allow_html=True)

        col_acc1, col_acc2 = st.columns(2)
        with col_acc1:
            if st.button("Log out", use_container_width=True):
                st.session_state["user_email"] = ""
                st.rerun()
        with col_acc2:
            if st.button("Reset (1 Free)", use_container_width=True, help="Reset to 1 free credit for testing"):
                database.reset_user(user_email)
                st.rerun()

    st.divider()

    st.subheader("🤖 AI Brain & Keys")
    gemini_key_default = get_secret("GEMINI_API_KEY", "")
    gemini_api_key = st.text_input(
        "Gemini API Key",
        value=gemini_key_default,
        type="password",
        help="Enables LLM-powered viral moment selection, punchline detection, and viral scoring."
    )

    youtube_key_default = get_secret("YOUTUBE_API_KEY", "")
    youtube_api_key = st.text_input(
        "YouTube API Key",
        value=youtube_key_default,
        type="password",
        help="Optional: Used for trending video search and channel discovery."
    )

    st.divider()

    st.subheader("🎨 Subtitle Appearance")
    color_names = {
        "yellow": "🟡 Vibrant Yellow",
        "green": "🟢 Neon Green",
        "cyan": "🔵 Electric Cyan",
        "orange": "🟠 Hot Orange",
        "magenta": "🟣 Neon Magenta"
    }
    selected_color = st.selectbox(
        "Active Word Highlight Color",
        list(color_names.keys()),
        format_func=lambda k: color_names[k],
        index=0
    )

    enable_emojis = st.checkbox(
        "✨ Context-Aware Emojis (🔥, 💰, 😱)",
        value=True,
        help="Automatically injects animated emojis on matching keywords like money, win, shock, etc."
    )


# ---------------------------------
# YOUTUBE API HELPER FUNCTIONS
# ---------------------------------

def get_youtube_api():
    key = youtube_api_key.strip()
    if not key:
        raise ValueError("YouTube API key is required for video discovery. Add it in the sidebar.")
    return build("youtube", "v3", developerKey=key, cache_discovery=False)


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


# ---------------------------------
# MAIN PAGE INTERFACE
# ---------------------------------

st.markdown('<div class="main-header">🎬 Shorts Maker AI</div>', unsafe_allow_html=True)
st.write("Convert long YouTube videos and local files into high-retention 9:16 Shorts & Reels with AI face-tracking and dynamic captions.")

st.divider()

st.header("1. Choose Your Video Source")

source = st.radio(
    "Select video source",
    [
        "Upload video from device",
        "YouTube video link",
        "Discover YouTube videos"
    ],
    horizontal=True
)

selected_video = None
selected_url = None

if source == "Upload video from device":
    uploaded = st.file_uploader(
        "Upload a video file (MP4, MKV, MOV, WEBM)",
        type=["mp4", "mkv", "mov", "avi", "webm", "m4v"]
    )
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".mp4"
        video_path = DOWNLOAD_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
        video_path.write_bytes(uploaded.getbuffer())
        selected_video = str(video_path)
        st.success(f"✅ Video ready for processing: {uploaded.name}")

elif source == "YouTube video link":
    selected_url = st.text_input(
        "Paste YouTube video URL",
        placeholder="https://www.youtube.com/watch?v=..."
    )

elif source == "Discover YouTube videos":
    discovery_type = st.radio(
        "Discovery method",
        ["Popular videos in India", "Videos from selected channels"]
    )

    if discovery_type == "Popular videos in India":
        if st.button("🔍 Find Popular Videos"):
            try:
                with st.spinner("Finding popular YouTube videos..."):
                    st.session_state["discovered_videos"] = get_popular_videos()
            except Exception as error:
                st.error(f"YouTube discovery failed: {error}")
    else:
        channel_text = st.text_area(
            "Enter YouTube Channel IDs (one per line)",
            placeholder="e.g. UC_x5XG1OV2P6uZZ5FSM9Ttw"
        )
        if st.button("🔍 Find Channel Videos"):
            channel_ids = [c.strip() for c in channel_text.splitlines() if c.strip()]
            if not channel_ids:
                st.warning("Please enter at least one channel ID.")
            else:
                try:
                    with st.spinner("Finding channel videos..."):
                        st.session_state["discovered_videos"] = get_channel_videos(channel_ids)
                except Exception as error:
                    st.error(f"Channel discovery failed: {error}")

    discovered = st.session_state.get("discovered_videos", [])
    if discovered:
        options = [f"{video['title']} — {video['channel']}" for video in discovered]
        selected_index = st.selectbox(
            "Select a video to convert",
            range(len(options)),
            format_func=lambda idx: options[idx]
        )
        chosen_video = discovered[selected_index]
        selected_url = chosen_video["url"]
        st.video(selected_url)


# ---------------------------------
# 2. CUSTOMIZE YOUR SHORTS
# ---------------------------------

st.divider()
st.header("2. Customize Your Shorts")

col_num, col_layout = st.columns(2)

with col_num:
    number_of_shorts = st.number_input(
        "How many Shorts do you want?",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        help="Select the number of non-overlapping viral shorts you want to generate."
    )

layout_options = {
    "smart_crop": "🎯 Smart Face Tracking (Full 9:16)",
    "blurred_background": "🔲 Blurred Ambient Fit (16:9)",
    "split_screen": "👥 Dual Speaker Split (Top/Bottom)"
}
with col_layout:
    selected_layout_key = st.selectbox(
        "9:16 Video Layout",
        list(layout_options.keys()),
        format_func=lambda k: layout_options[k],
        index=0,
        help="Smart Face Tracking automatically tracks the active speaker."
    )

col_lang, col_style = st.columns(2)

language_options = {
    "hinglish": "🔥 Hinglish (Natural Roman Hindi + English - Recommended)",
    "en": "🇬🇧 English (Full English Translation)",
    "original": "🌐 Original Audio Language",
    "hi": "🇮🇳 Pure Hindi (हिन्दी - देवनागरी)"
}
with col_lang:
    selected_language = st.selectbox(
        "🗣️ Subtitle Language",
        list(language_options.keys()),
        format_func=lambda k: language_options[k],
        index=0,
        help="Hinglish: English speech stays in English, Hindi speech is converted to Roman Hinglish (no pure Devanagari)."
    )

style_names = {
    "hormozi": "Hormozi (Bold & Contrast)",
    "mrbeast": "MrBeast (Dynamic Pop)",
    "minimal": "Clean Minimalist",
    "neon": "Cyber Neon"
}
with col_style:
    selected_style = st.selectbox(
        "Subtitle Preset",
        list(style_names.keys()),
        format_func=lambda k: style_names[k],
        index=0
    )


# ---------------------------------
# 3. GENERATION ACTION & PIPELINE
# ---------------------------------

st.divider()

user_email = st.session_state.get("user_email", "").strip().lower()

# Check user authentication and credits
if not user_email:
    st.info("🎁 **Get 1 Free Video Conversion!** Enter your email address to claim your free video credit:")
    c_em1, c_em2 = st.columns([3, 1])
    with c_em1:
        quick_email = st.text_input("Your Email", placeholder="creator@example.com", label_visibility="collapsed")
    with c_em2:
        if st.button("Claim 1 Free Video ➔", type="primary", use_container_width=True):
            if quick_email.strip() and "@" in quick_email:
                st.session_state["user_email"] = quick_email.strip().lower()
                st.rerun()
            else:
                st.warning("Please enter a valid email address.")
    st.stop()

can_generate, reason, user_info = database.can_generate_video(user_email)

if not can_generate:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 20px;">
        <span class="viral-badge">🔒 FREE CREDIT USED</span>
        <h2 style="color: white; margin-top: 5px;">Choose Your Plan to Continue Generating</h2>
        <p style="color: #94A3B8;">Payments are securely processed via Razorpay (UPI, GPay, PhonePe, Cards, NetBanking). Funds settle directly into your bank account.</p>
    </div>
    """, unsafe_allow_html=True)

    plan_cols = st.columns(len(payments.SUBSCRIPTION_PLANS))
    for idx, (p_key, p_data) in enumerate(payments.SUBSCRIPTION_PLANS.items()):
        with plan_cols[idx]:
            st.markdown(f"""
            <div class="pricing-card" style="min-height: 380px;">
                <h3 style="color: #F8FAFC; margin-bottom: 5px;">{p_data['name']}</h3>
                <div class="pricing-price">₹{p_data['price_inr']}</div>
                <div style="color: #94A3B8; font-size: 0.85rem; margin-bottom: 15px;">billed {p_data['period']}</div>
                <hr style="border-color: rgba(255,255,255,0.1); margin-bottom: 15px;" />
                <ul style="padding-left: 20px; font-size: 0.9rem; color: #E2E8F0; text-align: left;">
                    {''.join(f'<li>{f}</li>' for f in p_data['features'])}
                </ul>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"Choose {p_data['name']}", key=f"sel_plan_{p_key}", use_container_width=True, type="primary" if p_key == "pro" else "secondary"):
                st.session_state["active_checkout_plan"] = p_key
                try:
                    order = payments.create_razorpay_order(p_key, user_email)
                    st.session_state["active_order"] = order
                except Exception as ex:
                    st.error(f"Order creation failed: {ex}")

    # Active Checkout Box
    if "active_order" in st.session_state and "active_checkout_plan" in st.session_state:
        st.divider()
        st.markdown("### 🔒 Secure Razorpay Checkout")
        active_plan_info = payments.SUBSCRIPTION_PLANS[st.session_state["active_checkout_plan"]]
        order_info = st.session_state["active_order"]

        k_id, _ = payments.get_razorpay_credentials()

        checkout_html = payments.generate_checkout_html(
            order_id=order_info["order_id"],
            amount_paise=active_plan_info["amount_paise"],
            plan_name=active_plan_info["name"],
            key_id=k_id or "rzp_test_simulation",
            user_email=user_email
        )

        st.components.v1.html(checkout_html, height=200)

        st.markdown("#### Confirm Payment / Instant Credit")
        with st.form("verify_payment_form"):
            c_v1, c_v2 = st.columns(2)
            with c_v1:
                payment_id_in = st.text_input(
                    "Razorpay Payment ID",
                    placeholder="e.g. pay_NxZ89f92..." if not order_info.get("is_simulation") else "simulated_payment",
                    value="simulated_payment" if order_info.get("is_simulation") else ""
                )
            with c_v2:
                sig_in = st.text_input(
                    "Payment Signature (Optional in simulation)",
                    placeholder="Signature hash from Razorpay",
                    value="simulated_signature" if order_info.get("is_simulation") else ""
                )

            submit_btn = st.form_submit_button("✅ Verify & Activate Subscription", use_container_width=True)
            if submit_btn:
                is_valid = payments.verify_payment_signature(
                    order_info["order_id"],
                    payment_id_in.strip(),
                    sig_in.strip()
                )
                if is_valid:
                    database.activate_subscription(user_email, plan=st.session_state["active_checkout_plan"])
                    st.balloons()
                    st.success(f"🎉 Payment verified! {active_plan_info['name']} subscription activated.")
                    del st.session_state["active_order"]
                    st.rerun()
                else:
                    st.error("❌ Verification failed. Please ensure the Payment ID matches your transaction.")

    st.stop()

# User is allowed to generate!
col_btn, col_info = st.columns([1, 2])
with col_btn:
    start_btn = st.button("🚀 Generate Viral Shorts", type="primary", use_container_width=True)

with col_info:
    if user_info["is_subscribed"]:
        status_badge = '<span class="pro-badge">💎 PRO (Unlimited)</span>'
    else:
        status_badge = '<span class="free-badge">🎁 1 Free Video Credit</span>'
    st.markdown(
        f"{status_badge} &nbsp; <strong>Config:</strong> {layout_options[selected_layout_key]} • "
        f"<strong>Style:</strong> {style_names[selected_style]}",
        unsafe_allow_html=True
    )

if start_btn:
    if source == "Upload video from device" and not selected_video:
        st.error("Please upload a video file first.")
        st.stop()
    elif source != "Upload video from device" and (not selected_url or not selected_url.strip()):
        st.error("Please enter or select a YouTube video URL.")
        st.stop()

    st.divider()
    st.subheader("⚡ Processing Pipeline")
    status_text = st.empty()
    progress_bar = st.progress(0)

    def update_progress(message, value=None):
        status_text.markdown(f"**Status:** {message}")
        if value is not None:
            progress_bar.progress(max(0.0, min(1.0, float(value))))

    try:
        if source == "Upload video from device":
            results = process_video(
                selected_video,
                number_of_shorts=int(number_of_shorts),
                progress_callback=update_progress,
                gemini_api_key=gemini_api_key.strip() or None,
                layout=selected_layout_key,
                caption_style=selected_style,
                highlight_color=selected_color,
                enable_emojis=enable_emojis,
                subtitle_language=selected_language
            )
        else:
            results = process_youtube_video(
                selected_url.strip(),
                number_of_shorts=int(number_of_shorts),
                progress_callback=update_progress,
                youtube_api_key=youtube_api_key.strip() or None,
                gemini_api_key=gemini_api_key.strip() or None,
                layout=selected_layout_key,
                caption_style=selected_style,
                highlight_color=selected_color,
                enable_emojis=enable_emojis,
                subtitle_language=selected_language
            )

        # Deduct credit after successful generation
        database.use_credit(user_email, video_type=source, shorts_count=len(results))

        if not user_info["is_subscribed"]:
            st.balloons()
            st.toast("🎉 Video created! Your 1 free credit has been used.", icon="🎬")

        st.success(f"🎉 Success! Generated {len(results)} high-retention Short(s).")

        # ---------------------------------
        # RESULTS GALLERY & PREVIEWS
        # ---------------------------------
        st.header("✨ Your AI Shorts Are Ready")

        # Display in a responsive grid
        cols = st.columns(min(len(results), 2))
        for index, result in enumerate(results):
            col = cols[index % len(cols)]
            with col:
                result_path = Path(str(result))
                title = result.get("title", f"Short {index + 1}") if hasattr(result, "get") else f"Short {index + 1}"
                score = result.get("viral_score", 85) if hasattr(result, "get") else 85
                hook = result.get("hook", "") if hasattr(result, "get") else ""
                reason = result.get("reason", "") if hasattr(result, "get") else ""
                duration = result.get("duration", "") if hasattr(result, "get") else ""

                st.markdown(
                    f"""
                    <div class="clip-card">
                        <span class="viral-badge">🔥 {score}/100 VIRAL SCORE</span>
                        <h4 style="margin-top: 5px; margin-bottom: 5px;">{title}</h4>
                        <p style="color: #9CA3AF; font-size: 0.85rem; margin-bottom: 10px;">
                            <strong>Hook:</strong> "{hook}"<br>
                            <em>{reason}</em>
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                st.video(str(result_path))

                with open(result_path, "rb") as file_data:
                    st.download_button(
                        label=f"⬇️ Download Short {index + 1} (MP4)",
                        data=file_data,
                        file_name=f"short_{index + 1}_{result_path.name}",
                        mime="video/mp4",
                        key=f"download_{index}",
                        use_container_width=True
                    )
                st.write("")

        if len(results) > 1:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for idx, r_file in enumerate(results, 1):
                    p = Path(str(r_file))
                    zf.write(p, arcname=f"short_{idx}_{p.name}")
            zip_buffer.seek(0)
            st.download_button(
                label="📦 Download All Generated Shorts as ZIP",
                data=zip_buffer,
                file_name="shorts_maker_all_clips.zip",
                mime="application/zip",
                use_container_width=True
            )

    except Exception as error:
        st.error(f"Processing failed: {error}")
        st.exception(error)


st.divider()
st.caption(
    "Shorts Maker AI • Powered by Whisper • Gemini API • OpenCV Face Tracking • FFmpeg 9.0"
)
