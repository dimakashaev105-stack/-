import httpx, asyncio, os, time, sqlite3, json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask
from threading import Thread

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КОНФИГУРАЦИЯ (SECURE MODE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_ID    = int(os.getenv("API_ID", 0))
API_HASH  = os.getenv("API_HASH")
GROQ_KEY  = os.getenv("GROQ_KEY")
SESSION   = os.getenv("SESSION")
WEATHER_KEY = os.getenv("WEATHER_KEY")  # OpenWeatherMap API key

MODEL     = "llama-3.3-70b-versatile"
JARVIS_PROMPT = "Ты JARVIS — ИИ Тони Старка. Отвечай кратко, саркастично, называй владельца 'сэр'."
ASSISTANT_PROMPT = "Ты JARVIS, ассистент владельца этого аккаунта. Сразу скажи, что отвечает ИИ, так как владелец занят кодом. Будь вежлив и краток."

# Ключевые слова для уведомлений (можно менять)
KEYWORDS = os.getenv("KEYWORDS", "важно,срочно,помоги,позвони").split(",")

if not all([API_ID, API_HASH, GROQ_KEY, SESSION]):
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Ключи не найдены в Environment Variables Render!")

tg = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
msg_cache = {}
ai_memory = {}
mimic_mode = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  БАЗА ДАННЫХ (SQLite)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def init_db():
    conn = sqlite3.connect("jarvis.db")
    c = conn.cursor()
    # Статистика активности чатов
    c.execute("""CREATE TABLE IF NOT EXISTS chat_stats (
        chat_id INTEGER, chat_name TEXT, msg_count INTEGER DEFAULT 0,
        last_seen TEXT, PRIMARY KEY (chat_id)
    )""")
    # История сообщений для HTML-отчёта
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER, chat_name TEXT, sender_id INTEGER,
        sender_name TEXT, text TEXT, date TEXT
    )""")
    conn.commit(); conn.close()

def db_log_message(chat_id, chat_name, sender_id, sender_name, text):
    conn = sqlite3.connect("jarvis.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Лог сообщения
    c.execute("INSERT INTO messages (chat_id, chat_name, sender_id, sender_name, text, date) VALUES (?,?,?,?,?,?)",
              (chat_id, chat_name, sender_id, sender_name, text, now))
    # Обновляем статистику
    c.execute("""INSERT INTO chat_stats (chat_id, chat_name, msg_count, last_seen)
                 VALUES (?,?,1,?) ON CONFLICT(chat_id) DO UPDATE SET
                 msg_count=msg_count+1, last_seen=?, chat_name=?""",
              (chat_id, chat_name, now, now, chat_name))
    conn.commit(); conn.close()

init_db()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KEEP-ALIVE (Веб-сервер)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask(__name__)
@app.route('/')
def index(): return "JARVIS SYSTEM SECURE & ACTIVE"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЛОГИКА ИИ С ПАМЯТЬЮ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(chat_id, text, system_role):
    if chat_id not in ai_memory: ai_memory[chat_id] = []
    ai_memory[chat_id].append({"role": "user", "content": text})
    if len(ai_memory[chat_id]) > 12: ai_memory[chat_id] = ai_memory[chat_id][-12:]

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system_role}] + ai_memory[chat_id],
        "temperature": 0.6
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            ans = resp.json()['choices'][0]['message']['content']
            ai_memory[chat_id].append({"role": "assistant", "content": ans})
            return ans
        except Exception as e:
            print(f"Ошибка ИИ: {e}")
            return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  [НОВОЕ] ПОГОДА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_weather(city: str) -> str:
    if not WEATHER_KEY:
        return "❌ **WEATHER_KEY** не задан в переменных окружения."
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_KEY}&units=metric&lang=ru"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url)
            d = r.json()
            if d.get("cod") != 200:
                return f"❌ Город **{city}** не найден."
            name    = d["name"]
            temp    = d["main"]["temp"]
            feels   = d["main"]["feels_like"]
            desc    = d["weather"][0]["description"].capitalize()
            humidity= d["main"]["humidity"]
            wind    = d["wind"]["speed"]
            return (f"🌍 **{name}**\n"
                    f"🌡 Температура: `{temp}°C` (ощущается `{feels}°C`)\n"
                    f"☁️ {desc}\n"
                    f"💧 Влажность: `{humidity}%`\n"
                    f"💨 Ветер: `{wind} м/с`")
        except Exception as e:
            return f"❌ Ошибка погоды: {e}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  [НОВОЕ] HTML-ОТЧЁТ ПЕРЕПИСКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_html_report(chat_id=None, limit=200) -> str:
    conn = sqlite3.connect("jarvis.db")
    c = conn.cursor()
    if chat_id:
        c.execute("SELECT chat_name, sender_name, text, date FROM messages WHERE chat_id=? ORDER BY date DESC LIMIT ?", (chat_id, limit))
    else:
        c.execute("SELECT chat_name, sender_name, text, date FROM messages ORDER BY date DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()

    rows_html = ""
    for chat_name, sender, text, date in rows:
        safe_text = (text or "").replace("<", "&lt;").replace(">", "&gt;")
        rows_html += f"<tr><td>{date}</td><td>{chat_name or '—'}</td><td>{sender or '—'}</td><td>{safe_text}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<title>JARVIS — История переписки</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }}
  h1 {{ color: #58a6ff; }} table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
  th {{ background: #161b22; color: #58a6ff; padding: 10px; text-align: left; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #21262d; font-size: 13px; }}
  tr:hover {{ background: #161b22; }}
</style></head><body>
<h1>🤖 JARVIS — История переписки</h1>
<p>Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Записей: {len(rows)}</p>
<table><tr><th>Дата</th><th>Чат</th><th>Отправитель</th><th>Сообщение</th></tr>
{rows_html}
</table></body></html>"""

    path = "/tmp/jarvis_report.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  [НОВОЕ] СТАТИСТИКА ЧАТОВ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_chat_stats(top_n=10) -> str:
    conn = sqlite3.connect("jarvis.db")
    c = conn.cursor()
    c.execute("SELECT chat_name, msg_count, last_seen FROM chat_stats ORDER BY msg_count DESC LIMIT ?", (top_n,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return "📊 Статистика пуста — нет данных."
    lines = [f"📊 **Топ-{top_n} активных чатов:**\n"]
    for i, (name, count, last) in enumerate(rows, 1):
        lines.append(f"`{i}.` **{name or 'Личка'}** — {count} сообщ. | последнее: `{last}`")
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ОБРАБОТЧИК КОМАНД (Исходящие)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(outgoing=True))
async def cmd_handler(event):
    global mimic_mode, ai_memory, msg_cache
    text = event.text.strip()
    raw = text.lower()

    # 1. Пинг системы
    if raw == "ping":
        start = time.time(); await event.edit("🚀"); ms = round((time.time() - start) * 1000)
        return await event.edit(f"🛰 **Latency:** `{ms}ms` | **Status:** SECURE")

    # 2. Управление ассистентом
    if raw == "мимикрия вкл":
        mimic_mode = True; return await event.edit("🤖 **Ассистент:** ВКЛ (Отвечаю в ЛС)")
    if raw == "мимикрия выкл":
        mimic_mode = False; return await event.edit("🤖 **Ассистент:** ВЫКЛ")

    # 3. Очистка кэша и памяти
    if raw == "очистить кэш":
        ai_memory.clear(); msg_cache.clear()
        return await event.edit("🧹 **Вся локальная память стерта.**")

    # 4. Поиск по юзернейму и отправка
    if raw.startswith((".send ", "отправить ", "напиши ")):
        parts = text.split(maxsplit=2)
        if len(parts) < 3: return await event.edit("❌ **Формат: `.send @user текст`**")
        target, content = parts[1], parts[2]
        await event.edit(f"🔍 **Поиск {target}...**")
        try:
            entity = await tg.get_input_entity(target)
            await tg.send_message(entity, content)
            await event.edit(f"🚀 **Доставлено для {target}:**\n{content}")
        except Exception as e:
            await event.edit(f"⚠️ **Ошибка поиска:** `{str(e)}`")
        return

    # 5. ИИ Команды
    if raw.startswith(("ai ", "джарвис ")):
        query = text.split(maxsplit=1)[1] if " " in text else None
        if not query: return
        await event.edit("⚡ **Анализ...**")
        ans = await ai_call(event.chat_id, query, JARVIS_PROMPT)
        return await event.edit(f"🤖 **JARVIS:**\n{ans}" if ans else "❌ Ошибка Groq API.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [НОВОЕ] ПОГОДА
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Использование: погода Москва
    if raw.startswith("погода "):
        city = text.split(maxsplit=1)[1]
        await event.edit(f"🌐 **Запрос погоды для {city}...**")
        result = await get_weather(city)
        return await event.edit(result)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [НОВОЕ] СТАТИСТИКА ЧАТОВ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Использование: статистика
    if raw == "статистика":
        return await event.edit(get_chat_stats())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [НОВОЕ] HTML-ОТЧЁТ ПЕРЕПИСКИ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Использование: отчёт  или  отчёт 500
    if raw.startswith("отчёт") or raw.startswith("отчет"):
        parts = raw.split()
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 200
        await event.edit(f"📄 **Генерирую отчёт ({limit} сообщений)...**")
        path = generate_html_report(limit=limit)
        await tg.send_file("me", path, caption=f"📊 **JARVIS — HTML отчёт переписки**\nСообщений: {limit}")
        return await event.edit(f"✅ **Отчёт отправлен в Избранное!**")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [НОВОЕ] УПРАВЛЕНИЕ КЛЮЧЕВЫМИ СЛОВАМИ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Использование: слова вкл слово1,слово2  или  слова список
    if raw.startswith("слова "):
        args = text.split(maxsplit=1)[1]
        if args.lower() == "список":
            return await event.edit(f"🔍 **Отслеживаемые слова:**\n`{'`, `'.join(KEYWORDS)}`")
        if args.lower().startswith("вкл "):
            new_words = args[4:].split(",")
            KEYWORDS.extend([w.strip() for w in new_words if w.strip()])
            return await event.edit(f"✅ **Добавлены слова:** `{'`, `'.join(new_words)}`")
        if args.lower().startswith("выкл "):
            remove = args[5:].strip().lower()
            if remove in KEYWORDS:
                KEYWORDS.remove(remove)
                return await event.edit(f"🗑 **Удалено слово:** `{remove}`")
            return await event.edit(f"❌ Слово `{remove}` не найдено в списке.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  МОНИТОРИНГ (Входящие)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(incoming=True))
async def monitor(event):
    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'title', '') or str(event.sender_id)
    chat = await event.get_chat()
    chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or str(event.chat_id)

    # Сохраняем все входящие в кэш (Anti-Delete) и БД
    if event.text:
        msg_cache[event.id] = {'text': event.text, 'sender': event.sender_id}
        db_log_message(event.chat_id, chat_name, event.sender_id, sender_name, event.text)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [НОВОЕ] УВЕДОМЛЕНИЕ ПРИ УПОМИНАНИИ КЛЮЧЕВЫХ СЛОВ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if event.text:
        msg_lower = event.text.lower()
        found = [kw for kw in KEYWORDS if kw.strip() and kw.strip() in msg_lower]
        if found:
            await tg.send_message("me",
                f"🔔 **Ключевое слово обнаружено!**\n"
                f"💬 Чат: **{chat_name}**\n"
                f"👤 От: `{sender_name}` (`{event.sender_id}`)\n"
                f"🔑 Слово: `{'`, `'.join(found)}`\n"
                f"📝 Сообщение: {event.text}"
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [НОВОЕ] УМНЫЙ АВТООТВЕТ С ТОНОМ СОБЕСЕДНИКА
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Анализирует тон входящего и генерирует ответ в похожем стиле
    if mimic_mode and event.is_private and not getattr(sender, 'bot', False):
        async with tg.action(event.chat_id, 'typing'):
            await asyncio.sleep(2)
            tone_prompt = (
                "Ты JARVIS, ассистент владельца аккаунта. Сразу предупреди, что отвечает ИИ. "
                "Внимательно прочитай стиль и тон входящего сообщения (формальный/неформальный, "
                "весёлый/серьёзный, краткий/развёрнутый) и отвечай в похожем стиле. "
                "Будь вежлив и адаптируйся под собеседника."
            )
            ans = await ai_call(event.chat_id, event.text, tone_prompt)
            if ans: await event.reply(ans)

    # Media Sniper (фото-однодневки)
    if event.is_private and event.media and hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds:
        file = await event.download_media()
        await tg.send_file("me", file, caption=f"📸 **Снайпер:** Перехват от `{event.sender_id}`")
        os.remove(file)

@tg.on(events.MessageDeleted())
async def del_log(event):
    for mid in event.deleted_ids:
        if mid in msg_cache:
            d = msg_cache[mid]
            await tg.send_message("me", f"🕵️ **Удалено:**\n👤 `{d['sender']}`\n📝 {d['text']}")
            del msg_cache[mid]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЗАПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start_bot():
    await tg.start()
    print("✅ JARVIS ONLINE & SECURE")
    await tg.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_flask, daemon=True).start()
    asyncio.run(start_bot())
