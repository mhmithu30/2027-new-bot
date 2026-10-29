import os
import re
import json
import time
import hashlib
import threading
import requests
from collections import deque
from datetime import datetime, timezone, timedelta

# ---------- CONFIG ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL_SECONDS = 60
MIN_COINS = float(os.environ.get("MIN_COINS", "150"))  # সব সাইটের সর্বনিম্ন coin সীমা

APUCASH_URL = "https://apucash.com"
SEEN_IDS_FILE = "seen_ids.json"

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
DOLLARPULL_URL = "https://api.dollarpull.com/tracker/activity/recent?limit=50"
DOLLARPULL_TOKEN = os.environ.get("DOLLARPULL_TOKEN")
DOLLARPULL_SEEN_FILE = "dollarpull_seen_ids.json"

LOOTEARN_URL = "https://lootearn.com/api/getWithdrawAndCompletedOffers"
LOOTEARN_COOKIE = os.environ.get("LOOTEARN_COOKIE")
LOOTEARN_SEEN_FILE = "lootearn_seen_ids.json"

ZXAPI_URL = "https://zxearn.com/api/v1/public/live-activity"
ZXAPI_TOKEN = os.environ.get("ZXEARN_TOKEN")
ZXAPI_SEEN_FILE = "zxearn_api_seen_ids.json"

MISTCASH_URL = "https://mistcash.co/api/getWithdrawAndCompletedOffers"
MISTCASH_COOKIE = os.environ.get("MISTCASH_COOKIE")
MISTCASH_SEEN_FILE = "mistcash_seen_ids.json"
MISTCASH_MIN = float(os.environ.get("MISTCASH_MIN", str(MIN_COINS)))
LOOTEARN_MIN = float(os.environ.get("LOOTEARN_MIN", str(MIN_COINS)))

CLICKERAN_URL = "https://clickeran.com/get-red-data"
CLICKERAN_COOKIE = os.environ.get("CLICKERAN_COOKIE")
CLICKERAN_SEEN_FILE = "clickeran_seen_ids.json"
CLICKERAN_MIN = float(os.environ.get("CLICKERAN_MIN", str(MIN_COINS)))

BOUNTYCASH_URL = "https://bountycash.co/earn"
BOUNTYCASH_SEEN_FILE = "bountycash_seen_ids.json"
BOUNTYCASH_MIN = float(os.environ.get("BOUNTYCASH_MIN", str(MIN_COINS)))

CRAZYCASH_URL = "https://crazycash.co/get-red-data"
CRAZYCASH_COOKIE = os.environ.get("CRAZYCASH_COOKIE")  # ঐচ্ছিক
CRAZYCASH_SEEN_FILE = "crazycash_seen_ids.json"
CRAZYCASH_MIN = float(os.environ.get("CRAZYCASH_MIN", str(MIN_COINS)))
# cookie/টোকেনে ভুল করে ঢোকা নতুন লাইন বা বাড়তি স্পেস পরিষ্কার করা
for _name in (
    "JJREWARD_COOKIE", "SPEADEARN_COOKIE", "EARNFLAYER_COOKIE", "GOLDTASKER_COOKIE",
    "LOOTEARN_COOKIE", "MISTCASH_COOKIE", "CLICKERAN_COOKIE", "CRAZYCASH_COOKIE",
    "ZXAPI_TOKEN", "DOLLARPULL_TOKEN",
):
    _v = globals().get(_name)
    if _v:
        globals()[_name] = " ".join(_v.split())
# -----------------------------


send_lock = threading.Lock()
last_send_time = 0.0
MIN_SEND_GAP = 3.2  # Telegram গ্রুপে মিনিটে ~20 মেসেজের লিমিট
WARMUP_UNTIL = time.time() + 120  # রিস্টার্টের পর প্রথম ২ মিনিট পুরনো অফার পাঠাবে না


def send_telegram_message(text):
    global last_send_time
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    with send_lock:
        for _ in range(4):
            wait = MIN_SEND_GAP - (time.time() - last_send_time)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.post(url, data=payload, timeout=15)
            except Exception as e:
                print("Telegram request error:", e)
                last_send_time = time.time()
                return None
            last_send_time = time.time()
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                try:
                    retry = r.json().get("parameters", {}).get("retry_after", 5)
                except Exception:
                    retry = 5
                time.sleep(retry + 1)
                continue
            print("Telegram error:", r.text)
            return None
    return None


# প্রতি সাইটের শেষ ১০টা অফার (বাটনে চাপ দিলে দেখাবে)
site_history = {}
history_lock = threading.Lock()


def record_history(text):
    m = re.search(r"Website:</b>\s*([^\n]+)", text)
    if not m:
        return
    site = m.group(1).strip()
    with history_lock:
        dq = site_history.setdefault(site, deque(maxlen=10))
        dq.append((time.time(), text))


def send_lead(text):
    """নতুন লিড পাঠায়, তবে রিস্টার্টের পর warmup চলাকালীন চুপ থাকে।"""
    record_history(text)
    if time.time() < WARMUP_UNTIL:
        return None
    return send_telegram_message(text)


def pin_telegram_message(message_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "message_id": message_id, "disable_notification": False}
    r = requests.post(url, data=payload, timeout=15)
    if r.status_code != 200:
        print("Pin error:", r.text)


# সব সাইটের অফার এখানে জমা হবে, ঘণ্টায় একবার চেক হবে
hourly_offers_lock = threading.Lock()
hourly_offers = []


def track_offer(website, offer_name, reward):
    with hourly_offers_lock:
        hourly_offers.append({
            "website": website,
            "offer_name": offer_name,
            "reward": reward,
        })


def run_hourly_top_offer():
    while True:
        time.sleep(3600)  # ১ ঘণ্টা
        with hourly_offers_lock:
            offers_copy = hourly_offers.copy()
            hourly_offers.clear()

        if not offers_copy:
            continue

        top = max(offers_copy, key=lambda x: x["reward"])
        msg = (
            f"🏆 <b>HOURLY TOP OFFER</b>\n"
            f"🌐 <b>Website:</b> {top['website']}\n"
            f"🎯 <b>Offer:</b> {top['offer_name']}\n"
            f"💰 <b>Reward:</b> {top['reward']} coins"
        )
        result = send_telegram_message(msg)
        if result and result.get("ok"):
            message_id = result["result"]["message_id"]
            pin_telegram_message(message_id)
            print("Hourly top offer pinned:", top["offer_name"])


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
        print("Apucash: data-page JSON block পাওয়া যায়নি (site structure বদলেছে?)")
        return []
    data = json.loads(match.group(1))
    winners = data.get("props", {}).get("recentWinners", [])
    newest = winners[0].get("id") if winners else None
    print(f"Apucash check: {len(winners)} items, newest id {newest}")
    return winners


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
                if coins < MIN_COINS:
                    continue

                track_offer("Apucash", winner.get("source"), coins)
                send_lead(format_apucash_message(winner))
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
                if reward < MIN_COINS:
                    continue

                track_offer("JJReward", offer.get("offer_name"), reward)
                send_lead(format_jjreward_message(offer))
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
                if offer["amount"] < MIN_COINS:
                    continue

                track_offer("ZxEarn", offer["offername"], offer["amount"])
                send_lead(format_zxearn_message(offer))
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
                if reward < MIN_COINS:
                    continue

                track_offer("SpeadEarn", offer.get("name"), reward)
                send_lead(format_speadearn_message(offer))
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
                if amount < MIN_COINS:
                    continue
                # নেগেটিভ (withdrawal) বাদ দেওয়া
                if amount < 0:
                    continue

                track_offer("SpeadEarn Activity", item.get("source") or item.get("provider") or item.get("network") or "N/A", amount)
                send_lead(format_speadearn_activity_message(item))
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
            unseen = [i for i in items if i.get("id") not in seen_ids]
            top_id = max((i.get("id") or 0) for i in items) if items else None
            print(f"MistCoins check: {len(items)} offers on page, {len(unseen)} unseen, newest id {top_id}")
            for item in items:
                iid = item.get("id")
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)

                source = (item.get("partners") or "").lower()
                points = item.get("points") or 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if points < MIN_COINS:
                    continue

                track_offer("MistCoins", item.get("offer_name"), points)
                send_lead(format_mistcoins_message(item))
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
                if reward < MIN_COINS:
                    continue

                track_offer("EarnFlayer", item.get("offer_name"), reward)
                send_lead(format_earnflayer_message(item))
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
                if offer["points"] < MIN_COINS:
                    continue

                track_offer("HuntSkin", offer["detail"], offer["points"])
                send_lead(format_huntskin_message(offer))
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
        "Referer": "https://goldtasker.com/earn",
        "Origin": "https://goldtasker.com",
    }
    resp = requests.get(GOLDTASKER_URL, headers=headers, timeout=15)
    if resp.status_code != 200:
        names = [c.split("=")[0].strip() for c in (GOLDTASKER_COOKIE or "").split(";")]
        print(
            "GoldTasker DEBUG:",
            resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "cookie_names=", names,
            "cookie_len=", len(GOLDTASKER_COOKIE or ""),
            "body=", resp.text[:200].replace("\n", " "),
        )
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
                if reward < MIN_COINS:
                    continue

                track_offer("GoldTasker", item.get("offerName"), reward)
                send_lead(format_goldtasker_message(item))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_goldtasker_seen(seen_ids)
                print(f"GoldTasker: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("GoldTasker Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- DOLLARPULL (api, bearer token) ----------------
def load_dollarpull_seen():
    try:
        with open(DOLLARPULL_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_dollarpull_seen(seen_ids):
    with open(DOLLARPULL_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_dollarpull_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Authorization": f"Bearer {DOLLARPULL_TOKEN}",
        "Accept": "application/json",
        "Origin": "https://www.dollarpull.com",
        "Referer": "https://www.dollarpull.com/dashboard",
    }
    resp = requests.get(DOLLARPULL_URL, headers=headers, timeout=20)
    if resp.status_code != 200:
        print(
            "DollarPull DEBUG:", resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "body=", resp.text[:600].replace("\n", " "),
        )
        resp.raise_for_status()
    data = resp.json()

    def find_items(node):
        # JSON এর যেকোনো গভীরতায় offerName সহ লিস্ট খোঁজা
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and "offerName" in node[0]:
                return node
            for x in node:
                r = find_items(x)
                if r:
                    return r
        elif isinstance(node, dict):
            for v in node.values():
                r = find_items(v)
                if r:
                    return r
        return []

    items = find_items(data)
    if not items:
        top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        print("DollarPull: অফার লিস্ট পাওয়া যায়নি, top-level =", top)
    return items


def format_dollarpull_message(item):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> DollarPull\n"
        f"🎯 <b>Offer:</b> {item.get('offerName')}\n"
        f"🧱 <b>Network:</b> {item.get('name')}\n"
        f"💰 <b>Reward:</b> {item.get('amount')} coins\n"
        f"👤 <b>User:</b> {item.get('userName')}"
    )


def run_dollarpull():
    print("DollarPull bot শুরু হয়েছে...")
    if not DOLLARPULL_TOKEN:
        print("DollarPull: DOLLARPULL_TOKEN সেট করা নেই, বন্ধ।")
        return
    seen_ids = load_dollarpull_seen()
    while True:
        try:
            items = fetch_dollarpull_offers()
            print(f"DollarPull check: {len(items)} items, newest id {items[0].get('id') if items else None}")
            new_count = 0
            for item in items:
                iid = str(item.get("id"))
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)

                if item.get("type") != "offer":
                    continue
                network = (item.get("name") or "").lower()
                offer = (item.get("offerName") or "").lower()
                try:
                    amount = float(item.get("amount") or 0)
                except (TypeError, ValueError):
                    amount = 0

                if "cpx" in network or "cpx research" in offer or "theoremreach" in network or "theoremreach" in offer:
                    continue
                if amount < MIN_COINS:
                    continue

                track_offer("DollarPull", item.get("offerName"), amount)
                send_lead(format_dollarpull_message(item))
                new_count += 1
            if new_count:
                save_dollarpull_seen(seen_ids)
                print(f"DollarPull: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("DollarPull Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- LOOTEARN (getWithdrawAndCompletedOffers, cookie-based) ----------------
def load_lootearn_seen():
    try:
        with open(LOOTEARN_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_lootearn_seen(seen_ids):
    with open(LOOTEARN_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_lootearn_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": LOOTEARN_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
        "Referer": "https://lootearn.com/earn",
    }
    resp = requests.get(LOOTEARN_URL, headers=headers, timeout=20)
    if resp.status_code != 200:
        print(
            "LootEarn DEBUG:", resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "body=", resp.text[:300].replace("\n", " "),
        )
        resp.raise_for_status()
    data = resp.json()

    def find_items(node):
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and "offer_name" in node[0]:
                return node
            for x in node:
                r = find_items(x)
                if r:
                    return r
        elif isinstance(node, dict):
            # একই ধরনের একাধিক লিস্ট থাকলে সবগুলো জোড়া দেওয়া
            found = []
            for v in node.values():
                r = find_items(v)
                if r:
                    found.extend(r)
            return found
        return []

    items = []
    if isinstance(data, dict) and isinstance(data.get("combinedData"), list):
        items = data["combinedData"]
    else:
        items = find_items(data)
    if items:
        first = items[0] if isinstance(items[0], dict) else {}
        offer_sample = next((i for i in items if isinstance(i, dict) and i.get("type") != "withdrawal"), None)
        print("LootEarn offer sample:", offer_sample)
    else:
        top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        print("LootEarn: লিস্ট খালি/পাওয়া যায়নি, top-level =", top)
    return items


def lootearn_fields(item):
    offer = item.get("offer_name") or item.get("offerName") or item.get("name")
    partner = item.get("partners") or item.get("partner") or item.get("offerwallName") or item.get("wall")
    reward = item.get("reward") or item.get("points") or item.get("amount") or item.get("coins") or 0
    return offer, partner, reward


def format_lootearn_message(item):
    offer, partner, reward = lootearn_fields(item)
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> LootEarn\n"
        f"🎯 <b>Offer:</b> {offer}\n"
        f"🧱 <b>Network:</b> {partner}\n"
        f"💰 <b>Reward:</b> {reward} coins"
    )


def _old_format_lootearn_message(item):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> LootEarn\n"
        f"🎯 <b>Offer:</b> {item.get('offer_name')}\n"
        f"🧱 <b>Network:</b> {item.get('partners')}\n"
        f"💰 <b>Reward:</b> {item.get('reward')} coins"
    )


def run_lootearn():
    print("LootEarn bot শুরু হয়েছে...")
    if not LOOTEARN_COOKIE:
        print("LootEarn: LOOTEARN_COOKIE সেট করা নেই, বন্ধ।")
        return
    seen_ids = load_lootearn_seen()
    while True:
        try:
            items = fetch_lootearn_offers()
            print(f"LootEarn check: {len(items)} items")
            new_count = 0
            for item in items:
                offer_raw, partner_raw, reward_raw = lootearn_fields(item)
                key = f"{item.get('type')}-{item.get('id')}-{offer_raw}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)

                if item.get("type") == "withdrawal" or not offer_raw:
                    continue
                network = (partner_raw or "").lower()
                offer = (offer_raw or "").lower()
                try:
                    reward = float(reward_raw or 0)
                except (TypeError, ValueError):
                    reward = 0

                if "cpx" in network or "theoremreach" in network or "cpx research" in offer or "theoremreach" in offer:
                    continue
                if reward < LOOTEARN_MIN:
                    continue

                track_offer("LootEarn", offer_raw, reward)
                send_lead(format_lootearn_message(item))
                new_count += 1
            if new_count:
                save_lootearn_seen(seen_ids)
                print(f"LootEarn: {new_count} টা নতুন অফার ধরা হয়েছে।")
        except Exception as e:
            print("LootEarn Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- ZXEARN API (live-activity, bearer token) ----------------
def load_zxapi_seen():
    try:
        with open(ZXAPI_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_zxapi_seen(seen_ids):
    with open(ZXAPI_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_zxapi_items():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://zxearn.com/earn",
    }
    if ZXAPI_TOKEN:
        headers["Authorization"] = f"Bearer {ZXAPI_TOKEN}"
    resp = requests.get(ZXAPI_URL, headers=headers, timeout=20)
    if resp.status_code != 200:
        print(
            "ZxEarn API DEBUG:", resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "body=", resp.text[:300].replace("\n", " "),
        )
        resp.raise_for_status()
    data = resp.json()

    def find_items(node):
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and "payout_points" in node[0]:
                return node
            for x in node:
                r = find_items(x)
                if r:
                    return r
        elif isinstance(node, dict):
            for v in node.values():
                r = find_items(v)
                if r:
                    return r
        return []

    items = find_items(data)
    if not items:
        top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        print("ZxEarn API: লিস্ট পাওয়া যায়নি, top-level =", top)
    return items


def format_zxapi_message(item):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> ZxEarn\n"
        f"🎯 <b>Offer:</b> {item.get('offer_title')}\n"
        f"🧱 <b>Source:</b> {item.get('source')}\n"
        f"💰 <b>Reward:</b> {item.get('payout_points')} coins\n"
        f"👤 <b>User:</b> {item.get('username')}"
    )


def run_zxearn_api():
    print("ZxEarn API bot শুরু হয়েছে...")
    seen_ids = load_zxapi_seen()
    while True:
        try:
            items = fetch_zxapi_items()
            print(f"ZxEarn API check: {len(items)} items, newest id {max((i.get('id') or 0) for i in items) if items else None}")
            new_count = 0
            for item in items:
                iid = str(item.get("id"))
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)

                kind = (item.get("kind") or "").lower()
                if "withdraw" in kind or "cash" in kind:
                    continue
                source = (item.get("source") or "").lower()
                title = (item.get("offer_title") or "").lower()
                try:
                    points = float(item.get("payout_points") or 0)
                except (TypeError, ValueError):
                    points = 0

                if "cpx" in source or "cpx" in title or "theoremreach" in source or "theoremreach" in title:
                    continue
                if points < MIN_COINS:
                    continue

                track_offer("ZxEarn", item.get("offer_title"), points)
                send_lead(format_zxapi_message(item))
                new_count += 1
            if new_count:
                save_zxapi_seen(seen_ids)
                print(f"ZxEarn API: {new_count} টা নতুন অফার ধরা হয়েছে।")
        except Exception as e:
            print("ZxEarn API Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- MISTCASH (getWithdrawAndCompletedOffers, cookie-based) ----------------
def load_mistcash_seen():
    try:
        with open(MISTCASH_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_mistcash_seen(seen_ids):
    with open(MISTCASH_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_mistcash_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": MISTCASH_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
        "Referer": "https://mistcash.co/earn",
    }
    resp = requests.get(MISTCASH_URL, headers=headers, timeout=20)
    if resp.status_code != 200:
        print(
            "MistCash DEBUG:", resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "body=", resp.text[:200].replace("\n", " "),
        )
        resp.raise_for_status()
    data = resp.json()
    items = data.get("combinedData", []) if isinstance(data, dict) else []
    if not items:
        top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        print("MistCash: লিস্ট খালি, top-level =", top)
    return items


def format_mistcash_message(item):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> MistCash\n"
        f"🎯 <b>Offer:</b> {item.get('offer_name')}\n"
        f"🧱 <b>Network:</b> {item.get('partners')}\n"
        f"💰 <b>Reward:</b> {item.get('reward')} coins"
    )


def run_mistcash():
    print("MistCash bot শুরু হয়েছে...")
    if not MISTCASH_COOKIE:
        print("MistCash: MISTCASH_COOKIE সেট করা নেই, বন্ধ।")
        return
    seen_ids = load_mistcash_seen()
    while True:
        try:
            items = fetch_mistcash_offers()
            print(f"MistCash check: {len(items)} items")
            new_count = 0
            for item in items:
                key = f"{item.get('type')}-{item.get('id')}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)

                if item.get("type") == "withdrawal" or not item.get("offer_name"):
                    continue
                network = (item.get("partners") or "").lower()
                offer = (item.get("offer_name") or "").lower()
                try:
                    reward = float(item.get("reward") or 0)
                except (TypeError, ValueError):
                    reward = 0

                if "cpx" in network or "theoremreach" in network or "cpx research" in offer or "theoremreach" in offer:
                    continue
                if reward < MISTCASH_MIN:
                    continue

                track_offer("MistCash", item.get("offer_name"), reward)
                send_lead(format_mistcash_message(item))
                new_count += 1
            if new_count:
                save_mistcash_seen(seen_ids)
                print(f"MistCash: {new_count} টা নতুন অফার ধরা হয়েছে।")
        except Exception as e:
            print("MistCash Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- CLICKERAN (get-red-data, cookie-based) ----------------
def load_clickeran_seen():
    try:
        with open(CLICKERAN_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_clickeran_seen(seen_ids):
    with open(CLICKERAN_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def _first(item, keys):
    for k in keys:
        v = item.get(k)
        if v not in (None, ""):
            return v
    return None


def clickeran_fields(item):
    # এই সাইটে অফারের নাম নেই, আছে নেটওয়ার্ক (name) আর offer_id
    offer = _first(item, ["offer_name", "offerName", "title", "task"])
    network = _first(item, ["partners", "partner", "network", "wall", "offerwall", "name", "source", "provider"])
    if not offer:
        oid = item.get("offer_id")
        offer = f"{network} #{oid}" if oid is not None and network else (f"Offer #{oid}" if oid is not None else None)
    reward = _first(item, ["request_amount", "reward", "points", "amount", "coins", "payout", "payout_points"]) or 0
    user = item.get("user")
    if isinstance(user, dict):
        user = user.get("name")
    user = user or _first(item, ["username", "user_name"])
    return offer, network, reward, user


def fetch_clickeran_items():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": CLICKERAN_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
        "Referer": "https://clickeran.com/",
    }
    resp = requests.get(CLICKERAN_URL, headers=headers, timeout=20)
    if resp.status_code != 200:
        print(
            "Clickeran DEBUG:", resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "body=", resp.text[:200].replace("\n", " "),
        )
        resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        print("Clickeran: JSON নয়, body =", resp.text[:200].replace("\n", " "))
        return []

    def find_items(node):
        if isinstance(node, list):
            if node and isinstance(node[0], dict):
                return node
            for x in node:
                r = find_items(x)
                if r:
                    return r
        elif isinstance(node, dict):
            found = []
            for v in node.values():
                r = find_items(v)
                if r:
                    found.extend(r)
            return found
        return []

    items = find_items(data)
    top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
    sample = json.dumps(items[0], ensure_ascii=False)[:400] if items else None
    print("Clickeran top-level:", top, "| items:", len(items), "| sample:", sample)
    return items


def format_clickeran_message(item):
    offer, network, reward, user = clickeran_fields(item)
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> Clickeran\n"
        f"🎯 <b>Offer:</b> {offer}\n"
        f"🧱 <b>Network:</b> {network}\n"
        f"💰 <b>Reward:</b> {reward} coins\n"
        f"👤 <b>User:</b> {user}"
    )


def run_clickeran():
    print("Clickeran bot শুরু হয়েছে...")
    if not CLICKERAN_COOKIE:
        print("Clickeran: CLICKERAN_COOKIE সেট করা নেই, বন্ধ।")
        return
    seen_ids = load_clickeran_seen()
    while True:
        try:
            items = fetch_clickeran_items()
            new_count = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_id = item.get("id")
                key = str(raw_id) if raw_id is not None else hashlib.md5(
                    json.dumps(item, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
                if key in seen_ids:
                    continue
                seen_ids.add(key)

                offer, network, reward_raw, user = clickeran_fields(item)
                if not offer:
                    continue
                kind = str(item.get("feed_type") or item.get("type") or item.get("kind") or "").lower()
                if "withdraw" in kind or "cash" in kind:
                    continue
                try:
                    reward = float(str(reward_raw).replace(",", ""))
                except (TypeError, ValueError):
                    reward = 0
                blob = f"{offer} {network}".lower()
                if "cpx" in blob or "theoremreach" in blob:
                    continue
                if reward < CLICKERAN_MIN:
                    continue

                track_offer("Clickeran", offer, reward)
                send_lead(format_clickeran_message(item))
                new_count += 1
            if new_count:
                save_clickeran_seen(seen_ids)
                print(f"Clickeran: {new_count} টা নতুন অফার ধরা হয়েছে।")
        except Exception as e:
            print("Clickeran Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- BOUNTYCASH (embedded Inertia JSON, no login needed) ----------------
def load_bountycash_seen():
    try:
        with open(BOUNTYCASH_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_bountycash_seen(seen_ids):
    with open(BOUNTYCASH_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_bountycash_winners():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(BOUNTYCASH_URL, headers=headers, timeout=20)
    if resp.status_code != 200:
        print(
            "BountyCash DEBUG:", resp.status_code,
            "server=", resp.headers.get("server"),
            "cf-mitigated=", resp.headers.get("cf-mitigated"),
            "body=", resp.text[:200].replace("\n", " "),
        )
        resp.raise_for_status()
    match = re.search(
        r'<script data-page="app" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        print("BountyCash: data-page JSON পাওয়া যায়নি")
        return []
    data = json.loads(match.group(1))
    return data.get("props", {}).get("recentWinners", [])


def split_bountycash_source(source):
    # "Adloot – [SOI-Sweeps] US ..." → (network, offer)
    for sep in (" \u2013 ", " - "):
        if sep in source:
            net, off = source.split(sep, 1)
            return net.strip(), off.strip()
    return "N/A", source.strip()


def format_bountycash_message(item):
    network, offer = split_bountycash_source(item.get("source") or "")
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> BountyCash\n"
        f"🎯 <b>Offer:</b> {offer}\n"
        f"🧱 <b>Network:</b> {network}\n"
        f"💰 <b>Reward:</b> {item.get('coins')} coins\n"
        f"👤 <b>User:</b> {item.get('name')}\n"
        f"⏰ <b>Time:</b> {(item.get('tooltip') or {}).get('time')}"
    )


def run_bountycash():
    print("BountyCash bot শুরু হয়েছে...")
    seen_ids = load_bountycash_seen()
    while True:
        try:
            winners = fetch_bountycash_winners()
            print(f"BountyCash check: {len(winners)} items, newest id {max((w.get('id') or 0) for w in winners) if winners else None}")
            new_count = 0
            for w in winners:
                wid = str(w.get("id"))
                if wid in seen_ids:
                    continue
                seen_ids.add(wid)

                if (w.get("source_label") or "").lower() != "offer":
                    continue  # streak/bonus ইত্যাদি বাদ
                source = (w.get("source") or "").lower()
                try:
                    coins = float(w.get("coins") or 0)
                except (TypeError, ValueError):
                    coins = 0
                if "cpx" in source or "theoremreach" in source:
                    continue
                if coins < BOUNTYCASH_MIN:
                    continue

                network, offer = split_bountycash_source(w.get("source") or "")
                track_offer("BountyCash", offer, coins)
                send_lead(format_bountycash_message(w))
                new_count += 1
            if new_count:
                save_bountycash_seen(seen_ids)
                print(f"BountyCash: {new_count} টা নতুন অফার ধরা হয়েছে।")
        except Exception as e:
            print("BountyCash Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- GET-RED-DATA টাইপ সাইট (CrazyCash) ----------------
def run_getred_site(site, url, referer, cookie, minimum, seen_file):
    print(f"{site} bot শুরু হয়েছে...")
    try:
        with open(seen_file, "r") as f:
            seen_ids = set(json.load(f))
    except FileNotFoundError:
        seen_ids = set()

    while True:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
                "Referer": referer,
            }
            if cookie:
                headers["Cookie"] = cookie
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                print(
                    f"{site} DEBUG:", resp.status_code,
                    "server=", resp.headers.get("server"),
                    "cf-mitigated=", resp.headers.get("cf-mitigated"),
                    "body=", resp.text[:200].replace("\n", " "),
                )
                resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else (data.get("data") or [])
            print(f"{site} check: {len(items)} items")

            new_count = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = f"{item.get('feed_type')}-{item.get('id')}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)

                if (item.get("feed_type") or "").lower() != "offer":
                    continue  # cashout ইত্যাদি বাদ
                offer, network, reward_raw, user = clickeran_fields(item)
                if not offer:
                    continue
                try:
                    reward = float(str(reward_raw).replace(",", ""))
                except (TypeError, ValueError):
                    reward = 0
                blob = f"{offer} {network}".lower()
                if "cpx" in blob or "theoremreach" in blob:
                    continue
                if reward < minimum:
                    continue

                track_offer(site, offer, reward)
                send_lead(
                    f"🚀 <b>NEW LIVE LEAD</b>\n"
                    f"🌐 <b>Website:</b> {site}\n"
                    f"🎯 <b>Offer:</b> {offer}\n"
                    f"🧱 <b>Network:</b> {network}\n"
                    f"💰 <b>Reward:</b> {reward_raw} coins\n"
                    f"👤 <b>User:</b> {user}"
                )
                new_count += 1
            if new_count:
                with open(seen_file, "w") as f:
                    json.dump(list(seen_ids), f)
                print(f"{site}: {new_count} টা নতুন অফার ধরা হয়েছে।")
        except Exception as e:
            print(f"{site} Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- MENU BUTTONS (শেষ ১০ অফার) ----------------
MENU_SITES = [
    "Apucash", "JJReward", "ZxEarn", "MistCoins", "EarnFlayer", "HuntSkin",
    "DollarPull", "LootEarn", "MistCash", "Clickeran", "BountyCash", "CrazyCash",
]
BD_TZ = timezone(timedelta(hours=6))


def tg_api(method, payload):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=40)
        return r.json()
    except Exception as e:
        print(f"Telegram {method} error:", e)
        return None


def menu_markup():
    rows = []
    for i in range(0, len(MENU_SITES), 2):
        rows.append([
            {"text": f"🌐 {name}", "callback_data": f"s:{i + j}"}
            for j, name in enumerate(MENU_SITES[i:i + 2])
        ])
    return {"inline_keyboard": rows}


MENU_TEXT = "📋 <b>কোন সাইটের শেষ ১০টা অফার দেখবে?</b>\nবাটনে চাপ দাও 👇"


def site_history_text(site):
    with history_lock:
        items = list(site_history.get(site, []))
    if not items:
        return f"🌐 <b>{site}</b>\n\nএখনো কোনো অফার জমা হয়নি।"
    parts = [f"📋 <b>{site} — শেষ {len(items)}টা অফার</b>"]
    for ts, text in reversed(items):  # নতুন আগে
        body = text.split("\n", 1)[1] if text.startswith("🚀") else text
        body = "\n".join(l for l in body.split("\n") if "Website:" not in l)
        t = datetime.fromtimestamp(ts, BD_TZ).strftime("%H:%M")
        parts.append(f"🕒 {t}\n{body}")
    out = "\n━━━━━━━━━━\n".join(parts)
    return out[:4000]


def run_menu_bot():
    """/start বা /menu লিখলে বাটন মেনু দেখায়; বাটনে চাপলে ওই সাইটের শেষ ১০ অফার দেখায়।"""
    tg_api("deleteWebhook", {"drop_pending_updates": False})
    offset = None
    print("Menu bot শুরু হয়েছে...")
    while True:
        try:
            payload = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                payload["offset"] = offset
            res = tg_api("getUpdates", payload)
            if not res or not res.get("ok"):
                time.sleep(5)
                continue
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message")
                if msg:
                    txt = (msg.get("text") or "").strip().lower()
                    if txt.startswith("/start") or txt.startswith("/menu"):
                        tg_api("sendMessage", {
                            "chat_id": msg["chat"]["id"],
                            "text": MENU_TEXT,
                            "parse_mode": "HTML",
                            "reply_markup": menu_markup(),
                        })
                    continue
                cb = upd.get("callback_query")
                if not cb:
                    continue
                tg_api("answerCallbackQuery", {"callback_query_id": cb["id"]})
                m = cb.get("message")
                if not m:
                    continue
                data = cb.get("data") or ""
                if data.startswith("s:") and data[2:].isdigit() and int(data[2:]) < len(MENU_SITES):
                    site = MENU_SITES[int(data[2:])]
                    text = site_history_text(site)
                    markup = {"inline_keyboard": [[
                        {"text": "🔄 Refresh", "callback_data": data},
                        {"text": "⬅️ Back", "callback_data": "menu"},
                    ]]}
                else:
                    text, markup = MENU_TEXT, menu_markup()
                tg_api("editMessageText", {
                    "chat_id": m["chat"]["id"],
                    "message_id": m["message_id"],
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "reply_markup": markup,
                })
        except Exception as e:
            print("Menu bot Error:", e)
            time.sleep(5)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    t17 = threading.Thread(target=run_menu_bot, daemon=True)
    t17.start()

    t1 = threading.Thread(target=run_apucash, daemon=True)
    t1.start()

    t2 = threading.Thread(target=run_jjreward, daemon=True)
    t2.start()

    t3 = threading.Thread(target=run_zxearn_api, daemon=True)
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

    t10 = threading.Thread(target=run_hourly_top_offer, daemon=True)
    t10.start()

    t11 = threading.Thread(target=run_dollarpull, daemon=True)
    t11.start()

    t12 = threading.Thread(target=run_lootearn, daemon=True)
    t12.start()

    t13 = threading.Thread(target=run_mistcash, daemon=True)
    t13.start()

    t14 = threading.Thread(target=run_clickeran, daemon=True)
    t14.start()

    t15 = threading.Thread(target=run_bountycash, daemon=True)
    t15.start()

    t16 = threading.Thread(
        target=run_getred_site,
        args=("CrazyCash", CRAZYCASH_URL, "https://crazycash.co/earn", CRAZYCASH_COOKIE, CRAZYCASH_MIN, CRAZYCASH_SEEN_FILE),
        daemon=True,
    )
    t16.start()

    while True:  # main thread জীবিত রাখা
        time.sleep(3600)
