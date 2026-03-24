import httpx, asyncio, os, time
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask
from threading import Thread

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КОНФИГУРАЦИЯ (SECURE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_ID    = int(os.getenv("API_ID", 0))
API_HASH  = os.getenv("API_HASH")
GROQ_KEY  = os.getenv("GROQ_KEY")
SESSION   = os.getenv("SESSION")

MODEL     = "llama-3.3-70b-versatile"
JARVIS_PROMPT = "Ты JARVIS — ИИ Тони Старка. Отвечай кратко, саркастично, называй владельца 'сэр'."
ASSISTANT_PROMPT = "Ты JARVIS, ассистент владельца этого аккаунта. Сразу скажи, что отвечает ИИ, так как владелец занят кодом. Будь вежлив и краток."

if not all([API_ID, API_HASH, GROQ_KEY, SESSION]):
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Ключи не найдены в Environment Variables Render!")

tg = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
msg_cache = {}
ai_memory = {}
mimic_mode = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KEEP-ALIVE (Render)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask(__name__)
@app.route('/')
def index(): return "JARVIS SYSTEM SECURE"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЛОГИКА ИИ С ПАМЯТЬЮ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(chat_id, text, system_role):
    if chat_id not in ai_memory: ai_memory[chat_id] = []
    ai_memory[chat_id].append({"role": "user", "content": text})
    if len(ai_memory[chat_id]) > 10: ai_memory[chat_id] = ai_memory[chat_id][-10:]

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system_role}] + ai_memory[chat_id],
        "temperature": 0.6
    }
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            ans = resp.json()['choices'][0]['message']['content']
            ai_memory[chat_id].append({"role": "assistant", "content": ans})
            return ans
        except: return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КОМАНДЫ (Исходящие)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(outgoing=True))
async def cmd_handler(event):
    global mimic_mode, ai_memory, msg_cache
    text = event.text.strip()
    raw = text.lower()

    if raw == "ping":
        start = time.time(); await event.edit("🚀"); ms = round((time.time() - start) * 1000)
        return await event.edit(f"🛰 **Latency:** `{ms}ms` | **Status:** SECURE")

    if raw == "мимикрия вкл":
        mimic_mode = True; return await event.edit("🤖 **Ассистент:** ВКЛ")
    if raw == "мимикрия выкл":
        mimic_mode = False; return await event.edit("🤖 **Ассистент:** ВЫКЛ")
    if raw == "очистить кэш":
        ai_memory.clear(); msg_cache.clear(); return await event.edit("🧹 **Память стерта.**")

    if raw.startswith((".send ", "отправить ", "напиши ")):
        parts = text.split(maxsplit=2)
        if len(parts) < 3: return await event.edit("❌ **Формат: `.send @user текст`**")
        target, content = parts[1], parts[2]
        await event.edit(f"🔍 **Поиск {target}...**")
        try:
            entity = await tg.get_input_entity(target)
            await tg.send_message(entity, content)
            await event.edit(f"🚀 **Отправлено для {target}:**\n{content}")
        except Exception as e:
            await event.edit(f"⚠️ **Ошибка:** `{str(e)}`")
        return

    if raw.startswith(("ai ", "джарвис ")):
        query = text.split(maxsplit=1)[1] if " " in text else None
        if not query: return
        await event.edit("⚡ **Анализ...**")
        ans = await ai_call(event.chat_id, query, JARVIS_PROMPT)
        await event.edit(f"🤖 **JARVIS:**\n{ans}" if ans else "❌ Ошибка Groq.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  МОНИТОРИНГ (Входящие)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(incoming=True))
async def monitor(event):
    if event.chat_id and event.text:
        msg_cache[event.id] = {'text': event.text, 'sender': event.sender_id}

    if mimic_mode and event.is_private and not (await event.get_sender()).bot:
        async with tg.action(event.chat_id, 'typing'):
            await asyncio.sleep(2)
            ans = await ai_call(event.chat_id, event.text, ASSISTANT_PROMPT)
            if ans: await event.reply(ans)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start_bot():
    await tg.start()
    print("✅ JARVIS ONLINE (SECURE MODE)")
    await tg.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_flask).start()
    asyncio.run(start_bot())
