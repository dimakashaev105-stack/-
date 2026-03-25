import httpx, asyncio, os, time, sqlite3
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask
from threading import Thread

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КОНФИГУРАЦИЯ (MULTI-CORE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_ID    = int(os.getenv("API_ID", 0))
API_HASH  = os.getenv("API_HASH")
GROQ_KEY  = os.getenv("GROQ_KEY")
WEATHER_KEY = os.getenv("WEATHER_KEY")
# Список сессий (основная и вторая)
SESSIONS  = [os.getenv("SESSION"), os.getenv("SESSION_2")]

MODEL = "llama-3.3-70b-versatile"
JARVIS_PROMPT = "Ты JARVIS — ИИ Тони Старка. Отвечай кратко, саркастично, называй владельца 'сэр'."
ASSISTANT_PROMPT = "Ты JARVIS, ассистент. Сразу скажи, что отвечает ИИ. Будь вежлив."

clients = []
for sess in SESSIONS:
    if sess: clients.append(TelegramClient(StringSession(sess), API_ID, API_HASH))

msg_cache = {}
mimic_mode = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ИНТЕЛЛЕКТ И ПОГОДА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(text, system_role):
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    payload = {"model": MODEL, "messages": [{"role": "system", "content": system_role}, {"role": "user", "content": text}], "temperature": 0.6}
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            return resp.json()['choices'][0]['message']['content']
        except: return "Сэр, нейросеть временно недоступна."

async def get_weather(city):
    if not WEATHER_KEY: return "❌ Ключ погоды не задан."
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_KEY}&units=metric&lang=ru"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url); d = r.json()
            return f"🌡 {d['main']['temp']}°C, {d['weather'][0]['description']}"
        except: return "❌ Город не найден."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЛОГИКА ДЛЯ КАЖДОГО АККАУНТА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def setup_handlers(client):
    @client.on(events.NewMessage(outgoing=True))
    async def cmd_handler(event):
        global mimic_mode
        text = event.text; raw = text.lower()

        if raw == "ping":
            await event.edit("🚀 **Системы Multi-Core стабильны.**")
        
        elif raw == "мимикрия вкл":
            mimic_mode = True; await event.edit("🤖 **Ассистент активен на всех ядрах.**")
        
        elif raw == "мимикрия выкл":
            mimic_mode = False; await event.edit("🤖 **Ассистент отключен.**")

        elif raw.startswith("погода "):
            res = await get_weather(text.split(maxsplit=1)[1])
            await event.edit(res)

        elif raw.startswith(("ai ", "джарвис ")):
            await event.edit("⚡ **Анализ...**")
            ans = await ai_call(text.split(maxsplit=1)[1], JARVIS_PROMPT)
            await event.edit(f"🤖 **JARVIS:**\n{ans}")

    @client.on(events.NewMessage(incoming=True))
    async def monitor(event):
        if event.is_private and event.text:
            msg_cache[event.id] = {'text': event.text, 'sender': event.sender_id}
            if mimic_mode and not (await event.get_sender()).bot:
                async with client.action(event.chat_id, 'typing'):
                    ans = await ai_call(event.text, ASSISTANT_PROMPT)
                    if ans: await event.reply(ans)

    @client.on(events.MessageDeleted())
    async def del_log(event):
        for mid in event.deleted_ids:
            if mid in msg_cache:
                d = msg_cache[mid]
                await client.send_message("me", f"🕵️ **Удалено в ЛС:**\n📝 {d['text']}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЗАПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask(__name__)
@app.route('/')
def index(): return f"JARVIS ACTIVE: {len(clients)} CORES"

async def main():
    for client in clients:
        await client.start()
        setup_handlers(client)
        me = await client.get_me()
        print(f"✅ Подключен: @{me.username}")
    
    await asyncio.gather(*(c.run_until_disconnected() for c in clients))

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    if clients: asyncio.run(main())
    else: print("❌ Ошибка: Сессии не найдены!")
