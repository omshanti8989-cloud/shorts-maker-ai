import os
import cv2
import numpy as np
from pathlib import Path


class SmartCropper:
    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def analyze_video_faces(self, video_path, sample_interval_sec=0.5):
        """
        Samples video frames to detect face positions and identify dominant speakers.
        Returns:
            video_info: dict(width, height, fps, duration)
            primary_x: median center-X coordinate of the primary face
            dual_speakers: tuple (left_x, right_x) if two distinct speakers are found, else None
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0

        frame_step = max(1, int(fps * sample_interval_sec))

        face_centers_x = []
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_step == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Downscale for faster detection
                scale = 0.5
                small_gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale)

                faces = self.face_cascade.detectMultiScale(
                    small_gray,
                    scaleFactor=1.15,
                    minNeighbors=4,
                    minSize=(30, 30)
                )

                for (x, y, w, h) in faces:
                    # Convert back to original scale
                    orig_center_x = (x + w / 2) / scale
                    orig_w = w / scale
                    # Ignore tiny false positives (less than 6% of video width)
                    if orig_w > width * 0.06:
                        face_centers_x.append(orig_center_x)

            frame_idx += 1

        cap.release()

        video_info = {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration
        }

        if not face_centers_x:
            # Default to center
            return video_info, width // 2, None

        # Check for two distinct speakers (e.g. podcast / interview)
        left_faces = [x for x in face_centers_x if x < width * 0.45]
        right_faces = [x for x in face_centers_x if x > width * 0.55]

        dual_speakers = None
        if len(left_faces) >= 5 and len(right_faces) >= 5:
            # Both speakers are prominent
            left_median = int(np.median(left_faces))
            right_median = int(np.median(right_faces))
            dual_speakers = (left_median, right_median)

        # Primary speaker is the overall median
        primary_x = int(np.median(face_centers_x))

        return video_info, primary_x, dual_speakers

    def get_crop_filter(self, video_info, primary_x, layout="smart_crop", dual_speakers=None, subtitle_path=None, fonts_dir=None):
        """
        Generates FFmpeg filter string for rendering 1080x1920 vertical shorts.

        Supported layouts:
        1. 'smart_crop': 9:16 full-screen crop tracking the speaker's face.
        2. 'blurred_background': 16:9 fitted in center with blurred ambient background.
        3. 'split_screen': Stacked dual-speaker layout (Top: Speaker 1, Bottom: Speaker 2).
        """
        w = video_info["width"]
        h = video_info["height"]

        # Prepare subtitle filter component
        sub_filter = ""
        if subtitle_path:
            clean_sub = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", r"\:")
            clean_font = os.path.abspath(fonts_dir or "fonts").replace("\\", "/").replace(":", r"\:")
            sub_filter = f",ass='{clean_sub}':fontsdir='{clean_font}'"

        if layout == "blurred_background":
            filter_str = (
                "[0:v]split=2[bg][fg];"
                "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=25:12[blurred];"
                "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fit];"
                f"[blurred][fit]overlay=(W-w)/2:(H-h)/2{sub_filter}[final]"
            )
            return filter_str, "[final]"

        elif layout == "split_screen" and dual_speakers:
            left_x, right_x = dual_speakers
            # Each crop is 1080x960 (half of 1920)
            # Crop width from source for 1080x960 aspect ratio:
            # Aspect ratio is 1080 / 960 = 9 / 8 = 1.125
            crop_w = int(h * (9 / 8))
            if crop_w > w:
                crop_w = w

            x1 = max(0, min(w - crop_w, int(left_x - crop_w / 2)))
            x2 = max(0, min(w - crop_w, int(right_x - crop_w / 2)))

            filter_str = (
                f"[0:v]split=2[spk1][spk2];"
                f"[spk1]crop={crop_w}:{h}:{x1}:0,scale=1080:960[top];"
                f"[spk2]crop={crop_w}:{h}:{x2}:0,scale=1080:960[bottom];"
                f"[top][bottom]vstack{sub_filter}[final]"
            )
            return filter_str, "[final]"

        else:
            # Default: 'smart_crop' (Full screen 9:16 face-tracked)
            # 9:16 width for height h
            crop_w = int(h * 9 / 16)
            if crop_w % 2 != 0:
                crop_w += 1

            if crop_w > w:
                # Video is already narrower than 9:16 or portrait
                crop_w = w

            # Center crop window around speaker's face X
            crop_x = int(primary_x - crop_w / 2)
            # Clamp so crop doesn't exceed video boundaries
            crop_x = max(0, min(w - crop_w, crop_x))

            filter_str = (
                f"[0:v]crop={crop_w}:{h}:{crop_x}:0,"
                f"scale=1080:1920:flags=lanczos{sub_filter}[final]"
            )
            return filter_str, "[final]"
