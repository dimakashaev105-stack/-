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
WEATHER_KEY = os.getenv("WEATHER_KEY")

MODEL     = "llama-3.3-70b-versatile"
JARVIS_PROMPT = "Ты JARVIS — ИИ Тони Старка. Отвечай кратко, саркастично, называй владельца 'сэр'."
ASSISTANT_PROMPT = "Ты JARVIS, ассистент владельца этого аккаунта. Сразу скажи, что отвечает ИИ. Будь вежлив и краток."

# Ключевые слова для уведомлений
KEYWORDS = os.getenv("KEYWORDS", "важно,срочно,помоги,позвони").split(",")

tg = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
msg_cache = {}
ai_memory = {}
mimic_mode = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  БАЗА ДАННЫХ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def init_db():
    conn = sqlite3.connect("jarvis.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS chat_stats (chat_id INTEGER PRIMARY KEY, chat_name TEXT, msg_count INTEGER DEFAULT 0, last_seen TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, chat_name TEXT, sender_id INTEGER, sender_name TEXT, text TEXT, date TEXT)")
    conn.commit()
    conn.close()

def db_log_message(chat_id, chat_name, sender_id, sender_name, text):
    try:
        conn = sqlite3.connect("jarvis.db")
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO messages (chat_id, chat_name, sender_id, sender_name, text, date) VALUES (?,?,?,?,?,?)", (chat_id, chat_name, sender_id, sender_name, text, now))
        c.execute("INSERT INTO chat_stats (chat_id, chat_name, msg_count, last_seen) VALUES (?,?,1,?) ON CONFLICT(chat_id) DO UPDATE SET msg_count=msg_count+1, last_seen=?, chat_name=?", (chat_id, chat_name, now, now, chat_name))
        conn.commit()
        conn.close()
    except: pass

init_db()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ВЕБ-СЕРВЕР
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask(__name__)
@app.route('/')
def index(): return "JARVIS CORE ONLINE"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(chat_id, text, system_role):
    if chat_id not in ai_memory: ai_memory[chat_id] = []
    ai_memory[chat_id].append({"role": "user", "content": text})
    payload = {"model": MODEL, "messages": [{"role": "system", "content": system_role}] + ai_memory[chat_id][-10:], "temperature": 0.6}
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            ans = resp.json()['choices'][0]['message']['content']
            ai_memory[chat_id].append({"role": "assistant", "content": ans})
            return ans
        except: return None

async def get_weather(city: str) -> str:
    if not WEATHER_KEY: return "❌ WEATHER_KEY не задан."
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_KEY}&units=metric&lang=ru"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url); d = r.json()
            if d.get("cod") != 200: return f"❌ Город {city} не найден."
            return f"🌍 **{d['name']}**\n🌡 Температура: `{d['main']['temp']}°C`\n☁️ {d['weather'][0]['description'].capitalize()}"
        except: return "❌ Ошибка погоды."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ОБРАБОТЧИКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(outgoing=True))
async def cmd_handler(event):
    global mimic_mode, ai_memory
    text = event.text.strip(); raw = text.lower()

    if raw == "ping":
        await event.edit("🚀 Pong!"); return

    if raw == "мимикрия вкл":
        mimic_mode = True; await event.edit("🤖 Ассистент: ВКЛ"); return

    if raw == "мимикрия выкл":
        mimic_mode = False; await event.edit("🤖 Ассистент: ВЫКЛ"); return

    if raw == "статистика":
        conn = sqlite3.connect("jarvis.db"); c = conn.cursor()
        c.execute("SELECT chat_name, msg_count FROM chat_stats ORDER BY msg_count DESC LIMIT 5")
        res = c.fetchall(); conn.close()
        out = "📊 **Топ чатов:**\n" + "\n".join([f"• {n}: {c}" for n, c in res])
        await event.edit(out); return

    if raw.startswith("погода "):
        city = text.split(maxsplit=1)[1]
        res = await get_weather(city)
        await event.edit(res); return

    if raw.startswith(("ai ", "джарвис ")):
        query = text.split(maxsplit=1)[1]
        await event.edit("⚡ Анализ..."); ans = await ai_call(event.chat_id, query, JARVIS_PROMPT)
        await event.edit(f"🤖 **JARVIS:**\n{ans}" if ans else "❌ Ошибка ИИ."); return

@tg.on(events.NewMessage(incoming=True))
async def monitor(event):
    chat = await event.get_chat()
    chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Личка')
    sender = await event.get_sender()
    sender_name = getattr(sender, 'first_name', 'Аноним')

    if event.text:
        # Лог в БД для статистики и отчетов
        db_log_message(event.chat_id, chat_name, event.sender_id, sender_name, event.text)
        # Кэш для Anti-Delete (только в ЛС)
        if event.is_private:
            msg_cache[event.id] = {'text': event.text, 'sender': sender_name}

    # Автоответчик
    if mimic_mode and event.is_private and not getattr(sender, 'bot', False):
        async with tg.action(event.chat_id, 'typing'):
            await asyncio.sleep(2)
            ans = await ai_call(event.chat_id, event.text, ASSISTANT_PROMPT)
            if ans: await event.reply(ans)

@tg.on(events.MessageDeleted())
async def del_log(event):
    for mid in event.deleted_ids:
        if mid in msg_cache:
            d = msg_cache[mid]
            await tg.send_message("me", f"🕵️ **Удалено в ЛС:**\n👤 `{d['sender']}`\n📝 {d['text']}")
            del msg_cache[mid]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЗАПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    await tg.start()
    print("✅ JARVIS ONLINE")
    await tg.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
