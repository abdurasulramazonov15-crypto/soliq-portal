import re
import time
import requests
import logging
import asyncio
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ==============================================================================
# 1. SOZLAMALAR
# ==============================================================================
BOT_TOKEN = "8519083655:AAF5vXmAeWiW2qRDuOJjbU8roNVww2xDMso"
ADMIN_ID = 1766334490  # @ABDURASUL_N1

# Yangilik yuboriladigan kanal
TARGET_CHANNEL = "@soliq_news_yangiliklari"

# Sayt API sozlamalari (news.ramazonov.uz bilan integratsiya)
SITE_API_URL = "https://news.ramazonov.uz/api/news"
SITE_API_TOKEN = "soliq_portal_secret_token_2026"

# Kuzatiladigan rasmiy kanallar
OFFICIAL_CHANNELS = [
    "soliqnews",
    "soliq_yangiliklar_n1",
    "soliq_yangiliklari_uzbekistan",
    "huquqiyaxborot"
]

# Google Gemini API kaliti
GEMINI_API_KEY = "AQ.Ab8RN6JxLiV9_jSlTAPV8BsvM3_NAv5wdnRDU0T3tbWNrq6WhQ"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SoliqNewsBot")

last_seen_posts = {channel: None for channel in OFFICIAL_CHANNELS}
pending_posts = {}
users_waiting_ai = set()

# Soliq kalit so'zlari (Zaxira filtr)
TAX_KEYWORDS = [
    "soliq", "buxgalter", "imtiyoz", "deklaratsiya", "hisobot", "qqs",
    "daromad", "foyda", "jarima", "stavka", "fiskal", "cheki", "keshbek",
    "ehf", "hisobvaraq", "jshshir", "tadbirkor", "yatt", "mchj", "patent",
    "ijara", "tushum", "bojxona", "penya", "my.soliq.uz", "soliq.uz",
    "mol-mulk", "yer solig", "ijtimoiy soliq", "aksiz", "льгот", "налог"
]


# ==============================================================================
# 2. KERAKSIZ IJTIMOIY TARMOQLARNI VA BELGILARNI TOZALASH
# ==============================================================================
def clean_social_and_junk_links(text: str) -> str:
    """Ijtimoiy tarmoqlar havolalari va markdown belgilarini tozalash"""
    if not text:
        return ""

    social_keywords = [
        "telegram", "facebook", "youtube", "instagram", "threads",
        "twitter", "|x|", "fb.com", "youtu.be", "t.me", "vk.com"
    ]

    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line_clean = line.strip().lower().replace("т", "t")
        if not line_clean:
            cleaned_lines.append("")
            continue

        count = sum(1 for w in social_keywords if w in line_clean)
        if count >= 1 and ("|" in line or count >= 2 or any(u in line_clean for u in ["fb.com", "instagram.com", "youtube.com", "threads.net", "t.me"])):
            continue

        if any(line_clean == w for w in ["telegram", "facebook", "instagram", "threads", "youtube", "|x|", "x"]):
            continue

        cleaned_lines.append(line)

    res = "\n".join(cleaned_lines)
    res = res.replace("**", "").replace("__", "").replace("```", "")
    res = re.sub(r'\n{3,}', '\n\n', res)
    return res.strip()


# ==============================================================================
# 3. GEMINI AI: KANAL YANGILIKLARINI TOIFALASH VA SODDALASHTIRISH
# ==============================================================================
def process_and_simplify_text(text: str) -> dict:
    """
    Xabarni soliqqa oidligini tekshiradi, 4 ta toifadan biriga ajratadi
    va o'zbek tilida sodda qilib qayta yozadi.
    """
    cleaned_source = clean_social_and_junk_links(text)

    prompt = (
        "Siz Telegram kanallar va rasmiy veb-portal uchun professional kopiraytersiz.\n\n"
        "Quyidagi yangilikni tahlil qiling:\n"
        "1. Agar xabarda umuman soliq, buxgalteriya, imtiyoz (льгота), tadbirkorlik yoki qonunga aloqasi bo'lmasa "
        "(masalan: sport musobaqasi, stol tennisi, ob-havo, bayram tabrigi), FAQAT 'NO_TAX' deb javob bering.\n\n"
        "2. Agar soliq yoki imtiyozga oid bo'lsa:\n"
        "Eng birinchi qatorda toifani yozing:\n"
        "TOIFA: [yuridik | jismoniy | yatt | portal]\n"
        "(Qoidasi: MCHJ, korxona, QQS, buxgalteriya bo'lsa: yuridik; "
        "oddiy fuqarolar, mol-mulk, yer solig'i, keshbek bo'lsa: jismoniy; "
        "yakka tartibdagi tadbirkor, patent, frilans bo'lsa: yatt; "
        "barchaga umumiy bo'lsa: portal deb yozing).\n\n"
        "Keyingi qatorlarda tayyor o'zbekcha postni yozing:\n"
        "- Asl matn rus tilida bo'lsa ham, uni TO'LIQ O'ZBEK TILIDA yozing!\n"
        "- Ijtimoiy tarmoqlar nomlarini ASLO qo'shmang!\n"
        "- Matnda ikkita yulduzcha (**) kabi belgilarni ISHLATMANG!\n"
        "- Post to'g'ridan-to'g'ri 📢 belgisi bilan boshlansin:\n\n"
        "  📢 KATTA HARFLARDA SARLAVHA\n\n"
        "  💡 Nima haqida?\n\n"
        "  ⏰ Qachongacha yoki muddati?\n\n"
        "  🎯 Kimlar uchun?\n\n"
        "  👉 Muhim eslatma\n\n"
        "  #SoliqYangiliklari #Imtiyoz\n\n"
        f"Asl matn:\n{cleaned_source}"
    )

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    models = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                raw_result = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "NO_TAX" in raw_result:
                    logger.info("🚫 AI xabarni soliqqa oid emas deb baholadi.")
                    return {"is_tax": False, "text": cleaned_source, "category": "portal"}

                # Toifani ajratib olish
                category = "portal"
                post_text = raw_result
                if "TOIFA:" in raw_result:
                    lines = raw_result.splitlines()
                    for line in lines:
                        if "TOIFA:" in line:
                            cat_candidate = line.split("TOIFA:")[1].strip().lower()
                            for valid_cat in ["yuridik", "jismoniy", "yatt", "portal"]:
                                if valid_cat in cat_candidate:
                                    category = valid_cat
                                    break
                            break
                    # TOIFA qatorini Telegram postidan olib tashlash
                    post_text = re.sub(r'TOIFA:\s*\w+\n*', '', raw_result).strip()

                clean_text = clean_social_and_junk_links(post_text)
                logger.info(f"✨ AI matnni soddalashtirdi va toifaladi: [{category}]")
                return {"is_tax": True, "text": clean_text, "category": category}
        except Exception as e:
            logger.warning(f"AI {model_name} xatosi: {e}")

    # Zaxira tekshiruv
    text_lower = cleaned_source.lower()
    is_tax = any(kw in text_lower for kw in TAX_KEYWORDS)
    cat = "portal"
    if "yatt" in text_lower or "yakka" in text_lower: cat = "yatt"
    elif "jismoniy" in text_lower or "fuqaro" in text_lower: cat = "jismoniy"
    elif "yuridik" in text_lower or "korxona" in text_lower or "mchj" in text_lower: cat = "yuridik"

    return {"is_tax": is_tax, "text": cleaned_source, "category": cat}


# ==============================================================================
# 4. SAYT REST API'SIGA YUBORISH
# ==============================================================================
def send_to_website(title: str, text: str, category: str, photo_urls: list, video_url: str, source: str):
    """Yangilikni news.ramazonov.uz sayti bazasiga kiritish"""
    try:
        first_photo = photo_urls[0] if photo_urls else None
        first_line = title.strip().split("\n")[0].replace("📢", "").strip()

        payload = {
            "title": first_line[:120] if first_line else "Soliq yangiligi",
            "content": text,
            "category": category,
            "image_url": first_photo,
            "video_url": video_url,
            "source": source
        }
        headers = {
            "Authorization": f"Bearer {SITE_API_TOKEN}",
            "Content-Type": "application/json"
        }
        resp = requests.post(SITE_API_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201):
            logger.info(f"🌐 Yangilik saytga joylandi ({category})!")
        else:
            logger.warning(f"Sayt javobi: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"Saytga yuborishda xatolik: {e}")


# ==============================================================================
# 5. FOYDALANUVCHILAR SAVOLLARIGA JAVOB BERISH (/ai)
# ==============================================================================
def answer_user_soliq_question(question: str) -> str:
    prompt = (
        "Siz O'zbekiston soliq va buxgalteriya qonunchiligi bo'yicha malakali, samimiy virtual yordamchisiz.\n\n"
        "Foydalanuvchi sizga soliq yoki tadbirkorlik bo'yicha savol bermoqda. "
        "Unga o'zbek tilida juda sodda, muloyim, aniq va tushunarli javob bering.\n\n"
        "QOIDALAR:\n"
        "1. Matnda ikkita yulduzcha (**) yoki boshqa keraksiz belgilarni ASLO ISHLATMANG.\n"
        "2. Emojilardan (📌, 💡, ⚖️, 👉, ✅) chiroyli va o'qishga qulay foydalaning.\n"
        "3. Agar savol soliqqa mutlaqo aloqador bo'lmasa, muloyimlik bilan faqat soliq va biznesda yordam bera olishingizni ayting.\n\n"
        f"Foydalanuvchi savoli: {question}"
    )

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            raw_answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return clean_social_and_junk_links(raw_answer)
    except Exception as e:
        logger.error(f"Foydalanuvchi savoliga javob berishda AI xatosi: {e}")

    return "Kechirasiz, hozirda tizimda texnik yuklama mavjud. Iltimos, birozdan so'ng qayta urinib ko'ring."


# ==============================================================================
# 6. KANALLARDAN POSTLARNI O'QISH
# ==============================================================================
def fetch_latest_post(channel_username: str):
    clean_name = channel_username.lstrip("@")
    url = f"https://t.me/s/{clean_name}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        messages = soup.find_all('div', class_='tgme_widget_message')
        if not messages:
            return None

        latest_msg = messages[-1]
        msg_id = latest_msg.get('data-post')

        text_div = latest_msg.find('div', class_='tgme_widget_message_text')
        text = text_div.get_text(separator="\n").strip() if text_div else ""

        photo_urls = []
        photo_wraps = latest_msg.find_all('a', class_='tgme_widget_message_photo_wrap')
        for wrap in photo_wraps:
            style = wrap.get('style', '')
            if "background-image:url('" in style:
                p_url = style.split("background-image:url('")[1].split("')")[0]
                if p_url and p_url not in photo_urls:
                    photo_urls.append(p_url)

        if not photo_urls:
            photo_single = latest_msg.find('a', class_='tgme_widget_message_photo_default')
            if photo_single:
                style = photo_single.get('style', '')
                if "background-image:url('" in style:
                    p_url = style.split("background-image:url('")[1].split("')")[0]
                    if p_url:
                        photo_urls.append(p_url)

        has_video = False
        video_url = None
        video_thumb = None

        video_player = latest_msg.find('a', class_='tgme_widget_message_video_player')
        if video_player:
            has_video = True
            v_tag = video_player.find('video')
            if v_tag and v_tag.get('src'):
                video_url = v_tag.get('src')

            thumb_tag = video_player.find('i', class_='tgme_widget_message_video_thumb')
            if thumb_tag:
                style = thumb_tag.get('style', '')
                if "background-image:url('" in style:
                    video_thumb = style.split("background-image:url('")[1].split("')")[0]

            if video_thumb and not photo_urls:
                photo_urls.append(video_thumb)

        if not text and not photo_urls and not has_video:
            return None

        return {
            "id": msg_id,
            "text": text,
            "photo_urls": photo_urls,
            "has_video": has_video,
            "video_url": video_url,
            "video_thumb": video_thumb,
            "post_link": f"https://t.me/{msg_id}",
            "channel": clean_name
        }
    except Exception as e:
        logger.error(f"Kanal tekshirishda xatolik ({channel_username}): {e}")
        return None


# ==============================================================================
# 7. CHOP ETISH (TELEGRAM KANAL + SAYT)
# ==============================================================================
async def send_post_to_target_channel(context: ContextTypes.DEFAULT_TYPE, post_data: dict, is_simplified: bool = True):
    text = post_data["simplified"] if is_simplified else post_data["original"]
    photo_urls = post_data.get("photo_urls", [])
    has_video = post_data.get("has_video", False)
    video_url = post_data.get("video_url")
    post_link = post_data.get("post_link", "")
    source_label = post_data.get("channel", "Rasmiy")
    category = post_data.get("category", "portal")

    # 1. Telegram kanal uchun matn
    footer = f"\n\n📢 Manba: @{source_label}\n👉 Kanalga obuna bo'ling: {TARGET_CHANNEL}"
    if has_video and post_link:
        footer = f"\n\n📹 Videoni tomosha qilish: {post_link}" + footer

    full_text = text + footer

    tg_success = False

    try:
        # Video fayli bo'lsa
        if video_url:
            try:
                resp = requests.get(video_url, timeout=20)
                if resp.status_code == 200:
                    await context.bot.send_video(chat_id=TARGET_CHANNEL, video=resp.content, caption=full_text[:1020])
                    tg_success = True
            except Exception:
                pass

        # Albom bo'lsa
        if not tg_success and len(photo_urls) > 1:
            media_group = []
            caption_used = False
            for p_url in photo_urls[:10]:
                try:
                    resp = requests.get(p_url, timeout=10)
                    if resp.status_code == 200:
                        cap = full_text[:1020] if not caption_used else None
                        media_group.append(InputMediaPhoto(media=resp.content, caption=cap))
                        caption_used = True
                except Exception:
                    pass

            if media_group:
                await context.bot.send_media_group(chat_id=TARGET_CHANNEL, media=media_group)
                if len(full_text) > 1020:
                    await context.bot.send_message(chat_id=TARGET_CHANNEL, text=full_text)
                tg_success = True

        # Bitta rasm bo'lsa
        if not tg_success and len(photo_urls) == 1:
            try:
                resp = requests.get(photo_urls[0], timeout=10)
                if resp.status_code == 200:
                    if len(full_text) <= 1020:
                        await context.bot.send_photo(chat_id=TARGET_CHANNEL, photo=resp.content, caption=full_text)
                    else:
                        await context.bot.send_photo(chat_id=TARGET_CHANNEL, photo=resp.content)
                        await context.bot.send_message(chat_id=TARGET_CHANNEL, text=full_text[:4090])
                    tg_success = True
            except Exception:
                pass

        # Faqat matn
        if not tg_success:
            await context.bot.send_message(chat_id=TARGET_CHANNEL, text=full_text[:4090])
            tg_success = True

        logger.info(f"✅ Xabar muvaffaqiyatli {TARGET_CHANNEL} ga joylandi!")

        # 2. Saytga ham bir vaqtda joylash
        send_to_website(
            title=text.split("\n")[0],
            text=text,
            category=category,
            photo_urls=photo_urls,
            video_url=post_link if has_video else None,
            source=source_label
        )

        return True

    except Exception as e:
        logger.error(f"Kanalga yuborishda xatolik: {e}")
        return False


# ==============================================================================
# 8. ADMINGA TASDIQLASH XABARI (INLINE TUGMALAR)
# ==============================================================================
async def ask_admin_approval(context: ContextTypes.DEFAULT_TYPE, post_uid: str, post_data: dict):
    channel = post_data["channel"]
    simplified = post_data["simplified"]
    category = post_data.get("category", "portal").upper()
    photo_urls = post_data.get("photo_urls", [])
    has_video = post_data.get("has_video", False)
    post_link = post_data.get("post_link", "")

    buttons = [
        [
            InlineKeyboardButton("✅ Soddalashtirilganni chop etish", callback_data=f"pub_{post_uid}")
        ],
        [
            InlineKeyboardButton("📄 Asl matnni chop etish", callback_data=f"orig_{post_uid}"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"rej_{post_uid}")
        ]
    ]

    if has_video and post_link:
        buttons.insert(1, [InlineKeyboardButton("📹 Asl videoni ochish", url=post_link)])

    keyboard = InlineKeyboardMarkup(buttons)

    media_type = "📹 Video bor" if has_video else (f"📸 Rasmlar: {len(photo_urls)} ta" if photo_urls else "📝 Faqat matn")

    preview_text = (
        f"🔔 YANGI SOLIQ YANGILIGI\n"
        f"📢 Manba: @{channel}\n"
        f"🏷 Bo'lim: [{category}]\n"
        f"📎 Turi: {media_type}\n\n"
        f"✨ AI TAYYORLAGAN POST:\n\n"
        f"{simplified}\n\n"
        f"Qaysi variantda kanal va saytga chiqaraylik?"
    )

    try:
        if photo_urls:
            try:
                resp = requests.get(photo_urls[0], timeout=10)
                if resp.status_code == 200:
                    caption_piece = preview_text[:1020]
                    await context.bot.send_photo(
                        chat_id=ADMIN_ID,
                        photo=resp.content,
                        caption=caption_piece,
                        reply_markup=keyboard
                    )
                    return
            except Exception:
                pass

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=preview_text[:4090],
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Adminga yuborishda xatolik: {e}")


# ==============================================================================
# 9. TUGMALARNI BOSGANDA ISHLASH
# ==============================================================================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.from_user or query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ Bu tugmani faqat admin bosa oladi!", show_alert=True)
        return

    data = query.data
    action, post_uid = data.split("_", 1)
    post_data = pending_posts.get(post_uid)

    if not post_data:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu xabar topilmadi yoki allaqachon ko'rib chiqilgan.")
        return

    if action == "pub":
        ok = await send_post_to_target_channel(context, post_data, is_simplified=True)
        if ok:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"✅ AI posti {TARGET_CHANNEL} kanaliga va Saytga chop etildi!")
            del pending_posts[post_uid]
        else:
            await query.message.reply_text("❌ Chop etishda xatolik yuz berdi.")

    elif action == "orig":
        ok = await send_post_to_target_channel(context, post_data, is_simplified=False)
        if ok:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"✅ Asl post {TARGET_CHANNEL} kanaliga va Saytga chop etildi!")
            del pending_posts[post_uid]
        else:
            await query.message.reply_text("❌ Chop etishda xatolik yuz berdi.")

    elif action == "rej":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Post bekor qilindi.")
        if post_uid in pending_posts:
            del pending_posts[post_uid]


# ==============================================================================
# 10. DAVRIY KANALLARNI TEKSHIRISH
# ==============================================================================
async def check_channels_job(context: ContextTypes.DEFAULT_TYPE):
    for channel in OFFICIAL_CHANNELS:
        post = await asyncio.to_thread(fetch_latest_post, channel)
        if not post or not post["id"]:
            continue

        if last_seen_posts[channel] is None:
            last_seen_posts[channel] = post["id"]
            logger.info(f"Kuzatuv faol: @{channel}")
            continue

        if post["id"] != last_seen_posts[channel]:
            last_seen_posts[channel] = post["id"]
            logger.info(f"📢 Yangi post aniqlandi: @{channel} -> {post['id']}")

            result = await asyncio.to_thread(process_and_simplify_text, post["text"])
            if not result["is_tax"]:
                logger.info(f"🚫 Soliqqa oid emas, o'tkazib yuborildi: {post['id']}")
                continue

            post_uid = f"{channel}_{int(time.time())}"
            cleaned_original = clean_social_and_junk_links(post["text"])
            pending_posts[post_uid] = {
                "simplified": result["text"],
                "original": cleaned_original,
                "category": result.get("category", "portal"),
                "photo_urls": post.get("photo_urls", []),
                "has_video": post.get("has_video", False),
                "video_url": post.get("video_url"),
                "post_link": post.get("post_link"),
                "channel": channel
            }

            await ask_admin_approval(context, post_uid, pending_posts[post_uid])


# ==============================================================================
# 11. BUYRUQLAR (/start, /ai, /test)
# ==============================================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    if user_id == ADMIN_ID:
        channels_list = "\n".join([f"• @{ch}" for ch in OFFICIAL_CHANNELS])
        await update.message.reply_text(
            f"👑 Assalomu alaykum, Admin (@{username})!\n\n"
            f"🎯 Telegram kanal: {TARGET_CHANNEL}\n"
            f"🌐 Veb-portal: news.ramazonov.uz (http://127.0.0.1:5000)\n\n"
            f"📡 Kuzatilayotgan kanallar:\n{channels_list}\n\n"
            "⚙️ Admin imkoniyatlari:\n"
            "/test — Oxirgi yangilikni AI bilan tayyorlab, tasdiqlash uchun chiqarish\n"
            "/ai — Sun'iy intellektga savol berib ko'rish"
        )
    else:
        await update.message.reply_text(
            f"👋 Assalomu alaykum, {username}!\n\n"
            "🏛 Soliq Yangiliklari Portali botiga xush kelibsiz.\n\n"
            "💡 Soliqlar yoki tadbirkorlik bo'yicha savolingiz bormi?\n"
            "Savolingizni berish uchun /ai buyrug'ini bosing!\n\n"
            f"📢 Yangiliklar kanali: {TARGET_CHANNEL}\n"
            "🌐 Rasmiy veb-portal: news.ramazonov.uz"
        )


async def ai_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    users_waiting_ai.add(user_id)

    await update.message.reply_text(
        "🤖 Soliq AI Maslahatchisi\n\n"
        "Soliqlar, buxgalteriya, imtiyozlar, deklaratsiya yoki tadbirkorlik bo'yicha tushunmagan savolingiz bormi?\n\n"
        "Marhamat, savolingizni yozib yuboring — sizga sodda va tushunarli tilda javob beraman! 👇"
    )


async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Ushbu buyruq faqat bot admini uchun mo'ljallangan.")
        return

    await update.message.reply_text("⏳ Kanaldan oxirgi xabar olinmoqda va toifalanmoqda...")

    post = await asyncio.to_thread(fetch_latest_post, "soliqnews")
    if not post:
        await update.message.reply_text("❌ Kanaldan xabar olib bo'lmadi.")
        return

    result = await asyncio.to_thread(process_and_simplify_text, post["text"])

    post_uid = f"test_{int(time.time())}"
    cleaned_original = clean_social_and_junk_links(post["text"])
    pending_posts[post_uid] = {
        "simplified": result["text"],
        "original": cleaned_original,
        "category": result.get("category", "portal"),
        "photo_urls": post.get("photo_urls", []),
        "has_video": post.get("has_video", False),
        "video_url": post.get("video_url"),
        "post_link": post.get("post_link"),
        "channel": "soliqnews"
    }

    await ask_admin_approval(context, post_uid, pending_posts[post_uid])


async def handle_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    user_text = update.message.text or ""

    if user_id in users_waiting_ai or len(user_text) > 5:
        if user_id in users_waiting_ai:
            users_waiting_ai.remove(user_id)

        wait_msg = await update.message.reply_text("⏳ Savolingiz tahlil qilinmoqda, bir oz kuting...")
        answer = await asyncio.to_thread(answer_user_soliq_question, user_text)
        await wait_msg.delete()
        await update.message.reply_text(
            f"{answer}\n\n"
            "💡 Yana savolingiz bo'lsa, /ai buyrug'ini bosing yoki to'g'ridan-to'g'ri yozishingiz mumkin."
        )


# ==============================================================================
# 12. ASOSIY ISHGA TUSHIRISH
# ==============================================================================
def main():
    logger.info("Bot ishga tushirilmoqda...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ai", ai_cmd))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CallbackQueryHandler(handle_buttons))

    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        handle_user_messages
    ))

    job_queue = app.job_queue
    job_queue.run_repeating(check_channels_job, interval=30, first=2)

    logger.info(">>> Bot muvaffaqiyatli ishga tushdi! <<<")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()