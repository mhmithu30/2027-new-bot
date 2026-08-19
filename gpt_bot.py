import os
import re
import json
import time
import hashlib
import threading
import requests
import socketio

# ---------- CONFIG ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL_SECONDS = 60

APUCASH_URL = "https://apucash.com"
SEEN_IDS_FILE = "seen_ids.json"
PAIDCASH_SOCKET_URL = "https://servers.faucetify.io"

JJREWARD_URL = "https://www.jjreward.com/api/getWithdrawAndCompletedOffers"
JJREWARD_COOKIE = os.environ.get("JJREWARD_COOKIE")
JJREWARD_SEEN_FILE = "jjreward_seen_ids.json"

ZXEARN_URL = "https://zxearn.com"
ZXEARN_SEEN_FILE = "zxearn_seen_ids.json"

SPEADEARN_URL = "https://speadearn.online/gemiad-offers"
SPEADEARN_SEEN_FILE = "speadearn_seen_ids.json"

SPEADEARN_ACTIVITY_URL = "https://speadearn.online/recent-activity"
SPEADEARN_COOKIE = os.environ.get("SPEADEARN_COOKIE")
SPEADEARN_ACTIVITY_SEEN_FILE = "speadearn_activity_seen_ids.json"

MISTCOINS_URL = "https://mistcoins.com"
MISTCOINS_SEEN_FILE = "mistcoins_seen_ids.json"

EARNFLAYER_URL = "https://earnflayer.com/api/getWithdrawAndCompletedOffers"
EARNFLAYER_COOKIE = os.environ.get("EARNFLAYER_COOKIE")
EARNFLAYER_SEEN_FILE = "earnflayer_seen_ids.json"

HUNTSKIN_URL = "https://huntskin.com/Liveoffersfinal/Live.php"
HUNTSKIN_SEEN_FILE = "huntskin_seen_ids.json"

GOLDTASKER_URL = "https://goldtasker.com/api/live-offers"
GOLDTASKER_COOKIE = os.environ.get("GOLDTASKER_COOKIE")
GOLDTASKER_SEEN_FILE = "goldtasker_seen_ids.json"
# -----------------------------


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    r = requests.post(url, data=payload, timeout=15)
    if r.status_code != 200:
        print("Telegram error:", r.text)


# ---------------- APUCASH (polling) ----------------
def load_seen_ids():
    try:
        with open(SEEN_IDS_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_recent_winners():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(APUCASH_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    match = re.search(
        r'<script data-page="app" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        return []
    data = json.loads(match.group(1))
    return data.get("props", {}).get("recentWinners", [])


def format_apucash_message(winner):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> Apucash\n"
        f"🎯 <b>Offer:</b> {winner.get('source')}\n"
        f"💰 <b>Reward:</b> {winner.get('coins')} coins\n"
        f"👤 <b>User:</b> {winner.get('name')}\n"
        f"⏰ <b>Time:</b> {winner.get('tooltip', {}).get('time')}"
    )


def run_apucash():
    print("Apucash bot শুরু হয়েছে...")
    seen_ids = load_seen_ids()
    while True:
        try:
            winners = fetch_recent_winners()
            new_count = 0
            for winner in winners:
                wid = winner.get("id")
                if wid in seen_ids:
                    continue

                seen_ids.add(wid)  # আগে চেক করা হয়ে গেছে, দ্বিতীয়বার আর দেখাবে না

                source = (winner.get("source") or "").lower()
                coins = winner.get("coins") or 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if coins < 500:
                    continue

                send_telegram_message(format_apucash_message(winner))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_seen_ids(seen_ids)
                print(f"Apucash: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("Apucash Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- JJREWARD (polling with cookie) ----------------
def load_jjreward_seen():
    try:
        with open(JJREWARD_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_jjreward_seen(seen_ids):
    with open(JJREWARD_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_jjreward_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": JJREWARD_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = requests.get(JJREWARD_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("completedOffers", [])


def format_jjreward_message(offer):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> JJReward\n"
        f"🎯 <b>Offer:</b> {offer.get('offer_name')}\n"
        f"🧱 <b>Network:</b> {offer.get('partners')}\n"
        f"💰 <b>Reward:</b> {offer.get('reward')} JJ"
    )


def run_jjreward():
    print("JJReward bot শুরু হয়েছে...")
    seen_ids = load_jjreward_seen()
    while True:
        try:
            offers = fetch_jjreward_offers()
            new_count = 0
            for offer in offers:
                oid = offer.get("id")
                if oid in seen_ids:
                    continue
                seen_ids.add(oid)

                source = (offer.get("partners") or "").lower()
                try:
                    reward = float(offer.get("reward") or 0)
                except (TypeError, ValueError):
                    reward = 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if reward < 500:
                    continue

                send_telegram_message(format_jjreward_message(offer))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_jjreward_seen(seen_ids)
                print(f"JJReward: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("JJReward Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- ZXEARN (polling, no login needed) ----------------
def load_zxearn_seen():
    try:
        with open(ZXEARN_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_zxearn_seen(seen_ids):
    with open(ZXEARN_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_zxearn_offers():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(ZXEARN_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # প্রতিটা offer card বের করা
    cards = re.findall(
        r'data-id="(id-\d+)"[^>]*data-feed-type="offer"[^>]*data-bs-original-title="([^"]*)"',
        html,
    )

    offers = []
    for card_id, tooltip in cards:
        offername = re.search(r"Offername:\s*([^<]*)</p>", tooltip)
        network = re.search(r"Name:\s*([^<]*)</p>", tooltip)
        amount = re.search(r"Amount:\s*([\d.]+)\s*Coins", tooltip)
        offers.append({
            "id": card_id,
            "offername": offername.group(1).strip() if offername else "N/A",
            "network": network.group(1).strip() if network else "N/A",
            "amount": float(amount.group(1)) if amount else 0,
        })
    return offers


def format_zxearn_message(offer):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> ZxEarn\n"
        f"🎯 <b>Offer:</b> {offer['offername']}\n"
        f"🧱 <b>Network:</b> {offer['network']}\n"
        f"💰 <b>Reward:</b> {offer['amount']} coins"
    )


def run_zxearn():
    print("ZxEarn bot শুরু হয়েছে...")
    seen_ids = load_zxearn_seen()
    while True:
        try:
            offers = fetch_zxearn_offers()
            new_count = 0
            for offer in offers:
                oid = offer["id"]
                if oid in seen_ids:
                    continue
                seen_ids.add(oid)

                source = offer["network"].lower()
                if "cpx research" in source or "theoremreach" in source:
                    continue
                if offer["amount"] < 500:
                    continue

                send_telegram_message(format_zxearn_message(offer))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_zxearn_seen(seen_ids)
                print(f"ZxEarn: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("ZxEarn Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- SPEADEARN (gemiad-offers API polling) ----------------
def load_speadearn_seen():
    try:
        with open(SPEADEARN_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_speadearn_seen(seen_ids):
    with open(SPEADEARN_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_speadearn_offers():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(SPEADEARN_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        return []
    return data.get("offers", [])


def format_speadearn_message(offer):
    return (
        f"🚀 <b>NEW OFFER ADDED</b>\n"
        f"🌐 <b>Website:</b> SpeadEarn\n"
        f"🎯 <b>Offer:</b> {offer.get('name')}\n"
        f"🧱 <b>Category:</b> {offer.get('category')}\n"
        f"💰 <b>Reward:</b> {offer.get('reward')} coins"
    )


def run_speadearn():
    print("SpeadEarn bot শুরু হয়েছে...")
    seen_ids = load_speadearn_seen()
    while True:
        try:
            offers = fetch_speadearn_offers()
            new_count = 0
            for offer in offers:
                oid = offer.get("id")
                if oid in seen_ids:
                    continue
                seen_ids.add(oid)

                try:
                    reward = float(offer.get("reward") or 0)
                except (TypeError, ValueError):
                    reward = 0
                if reward < 500:
                    continue

                send_telegram_message(format_speadearn_message(offer))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_speadearn_seen(seen_ids)
                print(f"SpeadEarn: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("SpeadEarn Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- SPEADEARN ACTIVITY (recent-activity, cookie-based) ----------------
def load_speadearn_activity_seen():
    try:
        with open(SPEADEARN_ACTIVITY_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_speadearn_activity_seen(seen_ids):
    with open(SPEADEARN_ACTIVITY_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_speadearn_activity():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": SPEADEARN_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    resp = requests.get(SPEADEARN_ACTIVITY_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # রেসপন্স স্ট্রাকচার নিশ্চিত না হওয়ায় সম্ভাব্য key গুলো চেক করা হচ্ছে
    if isinstance(data, list):
        return data
    return data.get("data") or data.get("activities") or data.get("recent") or []


def format_speadearn_activity_message(item):
    name = item.get("name") or item.get("user") or item.get("username") or "Unknown"
    source = item.get("source") or item.get("provider") or item.get("network") or "N/A"
    amount = item.get("amount") or item.get("coins") or item.get("reward") or 0
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> SpeadEarn\n"
        f"🎯 <b>Network:</b> {source}\n"
        f"💰 <b>Reward:</b> {amount} coins\n"
        f"👤 <b>User:</b> {name}"
    )


def run_speadearn_activity():
    print("SpeadEarn Activity bot শুরু হয়েছে...")
    seen_ids = load_speadearn_activity_seen()
    while True:
        try:
            items = fetch_speadearn_activity()
            new_count = 0
            for item in items:
                iid = item.get("id") or json.dumps(item, sort_keys=True)
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)

                try:
                    amount = float(item.get("amount") or item.get("coins") or item.get("reward") or 0)
                except (TypeError, ValueError):
                    amount = 0
                if amount < 500:
                    continue
                # নেগেটিভ (withdrawal) বাদ দেওয়া
                if amount < 0:
                    continue

                send_telegram_message(format_speadearn_activity_message(item))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_speadearn_activity_seen(seen_ids)
                print(f"SpeadEarn Activity: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("SpeadEarn Activity Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- MISTCOINS (embedded JSON in HTML, no login needed) ----------------
def load_mistcoins_seen():
    try:
        with open(MISTCOINS_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_mistcoins_seen(seen_ids):
    with open(MISTCOINS_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_mistcoins_activity():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(MISTCOINS_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # @click="openDetail({...})" এর ভেতরের JSON অবজেক্টগুলো বের করা
    matches = re.findall(r'openDetail\((\{.*?\})\)"', html)

    items = []
    seen_local = set()
    for raw in matches:
        try:
            unescaped = raw.replace("&quot;", '"')
            data = json.loads(unescaped)
        except json.JSONDecodeError:
            continue
        if data.get("type") != "offer":
            continue
        if data["id"] in seen_local:
            continue
        seen_local.add(data["id"])
        items.append(data)
    return items


def format_mistcoins_message(item):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> MistCoins\n"
        f"🎯 <b>Offer:</b> {item.get('offer_name')}\n"
        f"🧱 <b>Network:</b> {item.get('partners')}\n"
        f"💰 <b>Reward:</b> {item.get('points')} coins\n"
        f"👤 <b>User:</b> {item.get('user_name')}"
    )


def run_mistcoins():
    print("MistCoins bot শুরু হয়েছে...")
    seen_ids = load_mistcoins_seen()
    while True:
        try:
            items = fetch_mistcoins_activity()
            new_count = 0
            for item in items:
                iid = item.get("id")
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)

                source = (item.get("partners") or "").lower()
                points = item.get("points") or 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if points < 500:
                    continue

                send_telegram_message(format_mistcoins_message(item))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_mistcoins_seen(seen_ids)
                print(f"MistCoins: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("MistCoins Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- EARNFLAYER (getWithdrawAndCompletedOffers, cookie-based) ----------------
def load_earnflayer_seen():
    try:
        with open(EARNFLAYER_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_earnflayer_seen(seen_ids):
    with open(EARNFLAYER_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_earnflayer_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": EARNFLAYER_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    resp = requests.get(EARNFLAYER_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("combinedData", [])


def format_earnflayer_message(item):
    if item.get("type") == "withdrawal":
        return None  # cashout, skip
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> EarnFlayer\n"
        f"🎯 <b>Offer:</b> {item.get('offer_name')}\n"
        f"🧱 <b>Network:</b> {item.get('partners')}\n"
        f"💰 <b>Reward:</b> {item.get('reward')} coins"
    )


def run_earnflayer():
    print("EarnFlayer bot শুরু হয়েছে...")
    seen_ids = load_earnflayer_seen()
    while True:
        try:
            items = fetch_earnflayer_offers()
            new_count = 0
            for item in items:
                key = f"{item.get('type')}-{item.get('id')}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)

                if item.get("type") == "withdrawal":
                    continue

                source = (item.get("partners") or "").lower()
                try:
                    reward = float(item.get("reward") or 0)
                except (TypeError, ValueError):
                    reward = 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if reward < 500:
                    continue

                send_telegram_message(format_earnflayer_message(item))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_earnflayer_seen(seen_ids)
                print(f"EarnFlayer: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("EarnFlayer Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- HUNTSKIN (plain HTML table, no login needed) ----------------
def load_huntskin_seen():
    try:
        with open(HUNTSKIN_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_huntskin_seen(seen_ids):
    with open(HUNTSKIN_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_huntskin_offers():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(HUNTSKIN_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    html = resp.text

    rows = re.findall(
        r"<tr><td data-label='username'>(.*?)</td><td data-label='Points'>(.*?)</td><td data-label='type'>(.*?)</td>",
        html,
    )

    offers = []
    for username, points, type_text in rows:
        try:
            points_val = float(points)
        except ValueError:
            points_val = 0
        row_id = hashlib.md5(f"{username}-{points}-{type_text}".encode()).hexdigest()
        offers.append({
            "id": row_id,
            "username": username.strip(),
            "points": points_val,
            "detail": type_text.strip(),
        })
    return offers


def format_huntskin_message(offer):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> HuntSkin\n"
        f"🎯 <b>Detail:</b> {offer['detail']}\n"
        f"💰 <b>Reward:</b> {offer['points']} coins\n"
        f"👤 <b>User:</b> {offer['username']}"
    )


def run_huntskin():
    print("HuntSkin bot শুরু হয়েছে...")
    seen_ids = load_huntskin_seen()
    while True:
        try:
            offers = fetch_huntskin_offers()
            new_count = 0
            for offer in offers:
                oid = offer["id"]
                if oid in seen_ids:
                    continue
                seen_ids.add(oid)

                source = offer["detail"].lower()
                if "cpx research" in source or "theoremreach" in source:
                    continue
                if offer["points"] < 500:
                    continue

                send_telegram_message(format_huntskin_message(offer))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_huntskin_seen(seen_ids)
                print(f"HuntSkin: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("HuntSkin Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- GOLDTASKER (live-offers API, cookie-based) ----------------
def load_goldtasker_seen():
    try:
        with open(GOLDTASKER_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_goldtasker_seen(seen_ids):
    with open(GOLDTASKER_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_goldtasker_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": GOLDTASKER_COOKIE,
        "Accept": "application/json",
    }
    resp = requests.get(GOLDTASKER_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("data") or data.get("offers") or []


def format_goldtasker_message(item):
    user = item.get("user", {})
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> GoldTasker\n"
        f"🎯 <b>Offer:</b> {item.get('offerName')}\n"
        f"🧱 <b>Network:</b> {item.get('offerwallName')}\n"
        f"💰 <b>Reward:</b> {item.get('reward')} coins\n"
        f"👤 <b>User:</b> {user.get('name')}"
    )


def run_goldtasker():
    print("GoldTasker bot শুরু হয়েছে...")
    seen_ids = load_goldtasker_seen()
    while True:
        try:
            items = fetch_goldtasker_offers()
            new_count = 0
            for item in items:
                key = f"{item.get('offerName')}-{item.get('createdAt')}-{item.get('user', {}).get('name')}"
                iid = hashlib.md5(key.encode()).hexdigest()
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)

                source = (item.get("offerwallName") or "").lower()
                try:
                    reward = float(item.get("reward") or 0)
                except (TypeError, ValueError):
                    reward = 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if reward < 500:
                    continue

                send_telegram_message(format_goldtasker_message(item))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_goldtasker_seen(seen_ids)
                print(f"GoldTasker: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("GoldTasker Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- PAIDCASH (socket.io live) ----------------
sio = socketio.Client()


@sio.event
def connect():
    print("PaidCash socket connected")


@sio.event
def disconnect():
    print("PaidCash disconnected, reconnecting...")


@sio.on("activityFeed")
def on_activity(data):
    if data.get("feedType") != "earn":
        return

    wall = (data.get("wall") or "").lower()
    coins = data.get("coins") or 0

    if "cpx research" in wall or "theoremreach" in wall:
        return
    if coins < 500:
        return

    if True:
        msg = (
            f"🚀 <b>NEW LIVE LEAD</b>\n"
            f"🌐 <b>Website:</b> PaidCash\n"
            f"🎯 <b>Offer:</b> {data.get('offername')}\n"
            f"🧱 <b>Network:</b> {data.get('wall')}\n"
            f"💰 <b>Reward:</b> {data.get('coins')} coins\n"
            f"👤 <b>User:</b> {data.get('username')}"
        )
        send_telegram_message(msg)
        print("PaidCash: Sent -", data.get("offername"))


def run_paidcash():
    while True:
        try:
            sio.connect(PAIDCASH_SOCKET_URL, transports=["websocket"])
            sio.wait()
        except Exception as e:
            print("PaidCash Error:", e)
            time.sleep(5)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    t1 = threading.Thread(target=run_apucash, daemon=True)
    t1.start()

    t2 = threading.Thread(target=run_jjreward, daemon=True)
    t2.start()

    t3 = threading.Thread(target=run_zxearn, daemon=True)
    t3.start()

    t4 = threading.Thread(target=run_speadearn, daemon=True)
    t4.start()

    t5 = threading.Thread(target=run_speadearn_activity, daemon=True)
    t5.start()

    t6 = threading.Thread(target=run_mistcoins, daemon=True)
    t6.start()

    t7 = threading.Thread(target=run_earnflayer, daemon=True)
    t7.start()

    t8 = threading.Thread(target=run_huntskin, daemon=True)
    t8.start()

    t9 = threading.Thread(target=run_goldtasker, daemon=True)
    t9.start()

    run_paidcash()  # main thread এ চলবে
