import os
import json
import base64
import urllib.request
import urllib.error

# Default plan pricing
SUBSCRIPTION_PLANS = {
    "pro_monthly": {
        "name": "Shorts Maker Pro",
        "price_inr": 499,
        "price_usd": 9.99,
        "period": "monthly",
        "features": [
            "Unlimited Short & Reel Generations",
            "Smart Face Tracking (Full 9:16 Auto-Crop)",
            "Dual-Speaker Split Screen Layout",
            "All Subtitle Presets (Hormozi, MrBeast, Neon)",
            "Dynamic Animated Emojis & Word Bounces",
            "Full 1080x1920 HD Export Quality",
            "No Watermarks & Priority Processing"
        ]
    }
}


def create_razorpay_payment_link(email, key_id=None, key_secret=None, amount_inr=499):
    """
    Creates a Razorpay Payment Link for Indian creators supporting UPI, GPay, PhonePe, Paytm, and Cards.
    Falls back to a standard checkout representation if live keys are not provided.
    """
    key_id = key_id or os.environ.get("RAZORPAY_KEY_ID")
    key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        return {
            "status": "simulation",
            "payment_url": None,
            "message": "Razorpay API keys not configured. Use Simulation/Test mode to activate Pro."
        }

    url = "https://api.razorpay.com/v1/payment_links"
    payload = {
        "amount": int(amount_inr * 100),  # amount in paise
        "currency": "INR",
        "accept_partial": False,
        "description": "Shorts Maker AI - Pro Monthly Subscription",
        "customer": {
            "email": email,
            "name": email.split("@")[0]
        },
        "notify": {
            "email": True
        },
        "reminder_enable": True,
        "notes": {
            "plan": "pro_monthly",
            "user_email": email
        }
    }

    auth_str = f"{key_id}:{key_secret}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {b64_auth}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "status": "success",
                "payment_url": data.get("short_url"),
                "payment_id": data.get("id")
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {
            "status": "error",
            "message": f"Razorpay error: {err_body}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
