import os
import sqlite3
import datetime
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "soliq_portal.db")
SECRET_API_TOKEN = os.environ.get("SITE_API_TOKEN", "soliq_portal_secret_token_2026")

CATEGORIES = {
    "portal": {
        "id": "portal",
        "name": "Portaldagi yangiliklar",
        "icon": "🌐",
        "badge_class": "bg-blue-100 text-blue-800 border-blue-200",
        "color": "#1e40af"
    },
    "yuridik": {
        "id": "yuridik",
        "name": "Yuridik shaxslar uchun",
        "icon": "🏢",
        "badge_class": "bg-indigo-100 text-indigo-800 border-indigo-200",
        "color": "#4338ca"
    },
    "jismoniy": {
        "id": "jismoniy",
        "name": "Jismoniy shaxslar uchun",
        "icon": "👤",
        "badge_class": "bg-emerald-100 text-emerald-800 border-emerald-200",
        "color": "#065f46"
    },
    "yatt": {
        "id": "yatt",
        "name": "YaTT va o‘z-o‘zini band qilganlar",
        "icon": "💼",
        "badge_class": "bg-amber-100 text-amber-800 border-amber-200",
        "color": "#92400e"
    }
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT,
        content TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'portal',
        category_name TEXT NOT NULL DEFAULT 'Portaldagi yangiliklar',
        image_url TEXT,
        source TEXT DEFAULT 'Telegram Soliq Yangiliklari',
        source_url TEXT,
        views INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    # Check if empty, then seed sample news
    cursor.execute("SELECT COUNT(*) FROM news")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_sample_news(cursor)
        conn.commit()
    conn.close()

def auto_detect_category(text: str) -> str:
    """
    Matn mazmuniga qarab avtomatik toifani aniqlash (AI qoidalari)
    """
    lower = text.lower()
    
    # 1. YaTT va o'zini o'zi band qilganlar
    if any(k in lower for k in ["yatt", "yakka tartibdagi", "o'zini o'zi band", "o‘zini o‘zi band", "frilanser", "hunarmand", "qat'iy belgilangan soliq"]):
        return "yatt"
    
    # 2. Yuridik shaxslar (MChJ, QQS, Foyda solig'i, E-faktura, korxona)
    if any(k in lower for k in ["mchj", "aj", "korxona", "yuridik shaxs", "qqs", "qo'shilgan qiymat", "foyda solig'i", "aylanmadan olinadigan", "buxgalter", "e-faktura", "hisob-faktura", "ttn"]):
        return "yuridik"
    
    # 3. Jismoniy shaxslar (Daromad solig'i, mol-mulk, yer solig'i, keshbek, soliq uz ilovasi)
    if any(k in lower for k in ["jshods", "jismoniy shaxs", "mol-mulk", "yer solig'i", "keshbek", "fuqaro", "daromad solig'i", "ijara solig'i", "soliq uz ilova"]):
        return "jismoniy"
    
    # Umumiy portal yangiliklari
    return "portal"

def seed_sample_news(cursor):
    sample_data = [
        (
            "Yuridik shaxslar uchun 2026-yil QQS va aylanmadan olinadigan soliq hisobotlari topshirish muddati e'lon qilindi",
            "Davlat soliq qo‘mitasi korxona va tashkilotlar buxgalterlariga muhim hisobot muddatlarini eslatib o‘tdi. Xususan, QQS hisobotini topshirish va to‘lash tartibi soddalashtirildi.",
            """Davlat soliq qo‘mitasi yuridik shaxslar, xususan MChJ va aksiyadorlik jamiyatlari buxgalterlariga 2026-yilning navbatdagi soliq hisobotlari muddatlarini eslatadi.

Asosiy talablar:
1. Qo‘shilgan qiymat solig‘i (QQS) bo‘yicha hisobotlar elektron soliq xizmatlari portali (my.soliq.uz) orqali to‘liq avtomatlashtirilgan tarzda qabul qilinadi.
2. Aylanmadan olinadigan soliq to‘lovchilari uchun yangi qulaylik: E-faktura tizimidagi ma'lumotlar avtomatik tarzda hisobotga yuklanadi.
3. Kechiktirilgan hisobotlar uchun jarimalar miqdori va to‘lov intizomini saqlash tavsiya etiladi.

Buxgalterlardan o‘z vaqtida hisob-kitoblarni yakunlab, tizim orqali tasdiqlashlari so‘raladi.""",
            "yuridik",
            "Yuridik shaxslar uchun",
            "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=800&q=80",
            "@soliqnews",
            "https://t.me/soliqnews"
        ),
        (
            "Jismoniy shaxslar diqqatiga: Mol-mulk va yer solig‘ini to‘lashda keshbek va yangi imtiyozlar joriy etildi",
            "Fuqarolar o‘zlariga tegishli uy-joy va yer uchastkalari uchun soliqlarni 'Soliq' mobil ilovasi orqali to‘laganlarida 1% keshbek hamda yengilliklardan foydalanishlari mumkin.",
            """O‘zbekiston Respublikasi fuqarolari uchun mol-mulk va yer solig‘ini to‘lash jarayoni yanada qulaylashtirildi. 

Yangiliklar va qulayliklar:
• 'Soliq' mobil ilovasi orqali to‘langan to‘lovlar uchun 1 foiz kafolatlangan keshbek to‘lab beriladi.
• Qarz mavjudligini JShShIR (PINFL) orqali hech qanday E-IMZO talab qilinmagan holda bir zumda bilish imkoni yaratildi.
• Ijtimoiy himoyaga muhtoj oilalar va pensiya yoshidagi fuqarolar uchun qonun bilan belgilangan imtiyozlar avtomatik tarzda hisoblanadi.

Soliqlarni o‘z vaqtida to‘lash orqali penya hisoblanishining oldini oling!""",
            "jismoniy",
            "Jismoniy shaxslar uchun",
            "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=800&q=80",
            "@soliq_press",
            "https://t.me/soliq_press"
        ),
        (
            "YaTT va o‘zini o‘zi band qilgan fuqarolar uchun elektron chek berish va qat'iy soliq stavkalari bo‘yicha eslatma",
            "Yakka tartibdagi tadbirkorlar va frilanserlar uchun soliq ma'murchiligida yaratilgan yengilliklar hamda onlayn savdo tartibi tushuntirildi.",
            """Yakka tartibdagi tadbirkorlik bilan shug‘ullanuvchi yoki o‘z-o‘zini band qilgan shaxslar uchun soliq tartibi bo‘yicha muhim eslatmalar:

1. O‘zini o‘zi band qilgan fuqarolar faoliyat turlari bo‘yicha daromad solig‘idan to‘liq ozod etilgan, faqat ixtiyoriy ravishda pensiya staji uchun ijtimoiy soliq to‘lashlari kifoya.
2. YaTTlar uchun savdo va xizmat ko‘rsatishda onlayn nazorat-kassa mashinalari yoki mobil chek berish majburiyati to‘liq integratsiya qilindi.
3. Soliq mobil ilovasida 'Mening YaTTim' bo‘limi orqali hisobotlarni 1 daqiqada topshirish mumkin.

Barcha frilanser va hunarmandlarga faoliyatlarini qonuniy ro‘yxatdan o‘tkazib, bank xizmatlaridan to‘siqsiz foydalanish tavsiya etiladi.""",
            "yatt",
            "YaTT va o‘z-o‘zini band qilganlar",
            "https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=800&q=80",
            "@soliq_yangiliklari_n1",
            "https://t.me/soliq_yangiliklari_n1"
        ),
        (
            "Elektron soliq xizmatlari portalida (my.soliq.uz) yangilangan intellektual xizmatlar ishga tushirildi",
            "Soliq to‘lovchilar uchun barcha davlat xizmatlarini yagona darcha tamoyili asosida olish imkoniyati kengaytirildi va qidiruv tizimi optimallashtirildi.",
            """Davlat soliq qo‘mitasi axborot texnologiyalari markazi tomonidan my.soliq.uz portalining yangilangan funksionalligi taqdim etildi.

Asosiy qulayliklar:
- Sun'iy intellektga asoslangan aqlli qidiruv orqali kerakli hujjat va nizomlarni darhol topish.
- Barcha toifadagi soliq to‘lovchilar uchun shaxsiy kabinetga kirish jarayonini yengillashtirish.
- Yangiliklar lentasi va soliq taqvimining yangilangan formati.
- Telegram xabarnoma xizmati orqali hisobot muddatlarini doimiy eslatib turish imkoniyati.

Platforma uzluksiz 24/7 rejimida xizmat ko‘rsatadi.""",
            "portal",
            "Portaldagi yangiliklar",
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=80",
            "@soliqnews",
            "https://t.me/soliqnews"
        )
    ]
    cursor.executemany("""
    INSERT INTO news (title, summary, content, category, category_name, image_url, source, source_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, sample_data)

# ==============================================================================
# MARSHRUTLAR (WEB ROUTES)
# ==============================================================================

@app.route("/")
def index():
    category = request.args.get("category", "all")
    search_query = request.args.get("q", "").strip()

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM news WHERE 1=1"
    params = []

    if category in CATEGORIES:
        query += " AND category = ?"
        params.append(category)

    if search_query:
        query += " AND (title LIKE ? OR content LIKE ? OR summary LIKE ?)"
        wildcard = f"%{search_query}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    news_items = cursor.fetchall()

    # Get count stats
    cursor.execute("SELECT category, COUNT(*) as cnt FROM news GROUP BY category")
    counts_raw = dict(cursor.fetchall())
    cursor.execute("SELECT COUNT(*) FROM news")
    total_count = cursor.fetchone()[0]

    counts = {
        "all": total_count,
        "portal": counts_raw.get("portal", 0),
        "yuridik": counts_raw.get("yuridik", 0),
        "jismoniy": counts_raw.get("jismoniy", 0),
        "yatt": counts_raw.get("yatt", 0)
    }

    conn.close()

    now_uz = datetime.datetime.now().strftime("%d.%m.%Y | %H:%M")

    return render_template(
        "index.html",
        news_items=news_items,
        current_category=category,
        search_query=search_query,
        categories=CATEGORIES,
        counts=counts,
        now_uz=now_uz
    )

@app.route("/news/<int:news_id>")
def news_detail(news_id):
    conn = get_db()
    cursor = conn.cursor()
    
    # Increment views
    cursor.execute("UPDATE news SET views = views + 1 WHERE id = ?", (news_id,))
    conn.commit()

    cursor.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    item = cursor.fetchone()
    
    if not item:
        conn.close()
        return redirect(url_for("index"))

    # Similar news
    cursor.execute("SELECT * FROM news WHERE category = ? AND id != ? ORDER BY id DESC LIMIT 3", (item["category"], news_id))
    related_items = cursor.fetchall()
    conn.close()

    return render_template(
        "detail.html",
        item=item,
        related_items=related_items,
        categories=CATEGORIES
    )

# ==============================================================================
# REST API (BOT BILAN ULASH UCHUN)
# ==============================================================================

@app.route("/api/news", methods=["POST"])
def api_add_news():
    """
    Telegram Bot ushbu API ga yangilik yuboradi:
    POST /api/news
    Headers: { "Authorization": "Bearer soliq_portal_secret_token_2026" }
    Body JSON:
    {
        "title": "Yangilik sarlavhasi",
        "content": "To'liq xabar matni",
        "category": "auto" (yoki 'yuridik', 'jismoniy', 'yatt', 'portal'),
        "image_url": "https://...",
        "source": "@soliq_yangiliklari_n1",
        "source_url": "https://t.me/..."
    }
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    
    # Oddiy token tekshiruvi (agar SECRET_API_TOKEN bo'sh bo'lmasa)
    if SECRET_API_TOKEN and token != SECRET_API_TOKEN:
        # Xavfsizlik uchun, agar token noto'g'ri bo'lsa rad etish
        return jsonify({"status": "error", "message": "Noto'g'ri API Token"}), 401

    data = request.get_json(force=True, silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"status": "error", "message": "Xabar matni (content) bo'sh bo'lmasligi kerak"}), 400

    raw_title = data.get("title", "").strip()
    if not raw_title:
        # Birinchi qatorni sarlavha qilish
        first_line = content.split("\n")[0]
        raw_title = first_line[:120].strip("#* ")

    # Qisqacha xulosa (summary)
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    summary = lines[1][:220] if len(lines) > 1 else lines[0][:220]

    # Toifani aniqlash
    req_cat = data.get("category", "auto").lower()
    if req_cat in CATEGORIES:
        category = req_cat
    else:
        # Avtomatik AI/qoidaviy toifalash
        category = auto_detect_category(f"{raw_title} {content}")

    cat_info = CATEGORIES.get(category, CATEGORIES["portal"])
    category_name = cat_info["name"]

    image_url = data.get("image_url") or None
    source = data.get("source", "Telegram Soliq Yangiliklari")
    source_url = data.get("source_url") or None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO news (title, summary, content, category, category_name, image_url, source, source_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (raw_title, summary, content, category, category_name, image_url, source, source_url))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "Yangilik muvaffaqiyatli chop etildi",
        "news_id": new_id,
        "category": category,
        "category_name": category_name,
        "title": raw_title
    }), 201

@app.route("/api/news", methods=["GET"])
def api_get_news():
    category = request.args.get("category")
    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    cursor = conn.cursor()
    if category and category in CATEGORIES:
        cursor.execute("SELECT * FROM news WHERE category = ? ORDER BY id DESC LIMIT ? OFFSET ?", (category, limit, offset))
    else:
        cursor.execute("SELECT * FROM news ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    
    rows = cursor.fetchall()
    news_list = [dict(r) for r in rows]
    conn.close()

    return jsonify({"count": len(news_list), "news": news_list})

# ==============================================================================
# ADMIN PANELI (BOSHQARUV VA TEST QILISH)
# ==============================================================================

@app.route("/admin")
def admin_panel():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news ORDER BY id DESC")
    all_news = cursor.fetchall()
    conn.close()
    return render_template(
        "admin.html",
        news_list=all_news,
        categories=CATEGORIES,
        api_token=SECRET_API_TOKEN
    )

@app.route("/admin/add", methods=["POST"])
def admin_add_news():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    category = request.form.get("category", "auto")
    image_url = request.form.get("image_url", "").strip() or None
    source = request.form.get("source", "@soliq_yangiliklari_n1").strip()

    if not title:
        first_line = content.split("\n")[0]
        title = first_line[:120].strip("#* ")

    if category not in CATEGORIES:
        category = auto_detect_category(f"{title} {content}")

    cat_name = CATEGORIES[category]["name"]
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    summary = lines[1][:220] if len(lines) > 1 else lines[0][:220]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO news (title, summary, content, category, category_name, image_url, source)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (title, summary, content, category, cat_name, image_url, source))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

@app.route("/admin/delete/<int:news_id>", methods=["POST"])
def admin_delete_news(news_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

# ==============================================================================
# SOHIBA VA ISHGA TUSHIRISH
# ==============================================================================

# Har qanday serverda (Gunicorn, Render yoki mahalliy) baza jadvallarini tayyorlash
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("================================================================")
    print("🏛  SOLIQ YANGILIKLARI PORTALI ISHGA TUSHMOQDA")
    print(f"🌐  Manzil: http://0.0.0.0:{port}")
    print(f"🔑  API Token: {SECRET_API_TOKEN}")
    print("================================================================")
    app.run(host="0.0.0.0", port=port, debug=True)
