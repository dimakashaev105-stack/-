import httpx
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
import time
import asyncio
from flask import Flask
from threading import Thread

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КОНФИГУРАЦИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_ID    = 26616230
API_HASH  = "895c0f50a04747d3342b0b9ee83e19cd"
GROQ_KEY  = "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"
SESSION   = "1ApWapzMBu7ewG6tsX055ejFjJC5mhuQVAmOwBgavHdWHFIuKdOE7_evf0_o9RrLaOFuYXyYefc8pYPotY2eSeypMldV_ab6Mr3ZeSKH285IXgFUOoChXdrzBNFJzgQc-OmhNmrEiSYTMcXB3vJrH9ofWx1pyungUtAJ2OxajJWMd6eh9h42B0B73GBWQ6nTV8FwyV8NP5ux7LdV5gV0Fgp8JE7x_FoS7m03hIR_e8ISbWkQM9DaBByUaCc7GTORLOyBgf3RjuhA30aa9k97izyMqM59RprerrKbpsFz2A4sprUUVStqqLtvtgYs0tugNoxOVbr7cr9S0_EiDXV87Uz_SMV-cRvs="

MODEL = "llama-3.3-70b-versatile"
SYSTEM_PROMPT = "Ты JARVIS — ИИ Тони Старка. Отвечай кратко, саркастично, называй владельца 'сэр'."

# Состояние системы
afk_mode = False
afk_reason = "не в сети"
afk_replied = set()
ai_history = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WEB-СЕРВЕР (Keep-Alive)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask('')
@app.route('/')
def home(): return "SYSTEM ONLINE"

def run_web(): app.run(host='0.0.0.0', port=8080)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЯДРО ИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(chat_id, text):
    if chat_id not in ai_history: ai_history[chat_id] = []
    ai_history[chat_id].append({"role": "user", "content": text})
    
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + ai_history[chat_id][-10:],
        "temperature": 0.6
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            ans = resp.json()['choices'][0]['message']['content']
            ai_history[chat_id].append({"role": "assistant", "content": ans})
            return ans
        except: return "❌ Ошибка связи с Groq."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ОБРАБОТЧИК СОБЫТИЙ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
tg = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

@tg.on(events.NewMessage(outgoing=True))
async def main_handler(event):
    global afk_mode, afk_reason, afk_replied
    raw = event.text.strip()
    low = raw.lower()
    
    # 1. СИСТЕМНЫЕ КОМАНДЫ
    if low == "ping":
        start = time.time()
        await event.edit("🚀")
        ms = round((time.time() - start) * 1000)
        return await event.edit(f"🛰 **JARVIS:** Отклик `{ms}ms` | Engine: Groq")

    if low == "cls":
        ai_history[event.chat_id] = []
        return await event.edit("🧠 **JARVIS:** Память чата стерта.")

    if low.startswith("del"):
        await event.delete()
        if event.is_reply:
            reply = await event.get_reply_message()
            await reply.delete()
        return

    # 2. ИНФОРМАЦИЯ И ОТПРАВКА
    if low.startswith("id"):
        uid = event.chat_id
        res = f"🆔 **Chat ID:** `{uid}`"
        if event.is_reply:
            rep = await event.get_reply_message()
            res += f"\n👤 **User ID:** `{rep.sender_id}`"
        return await event.edit(res)

    if low.startswith("отправь ") or low.startswith("send "):
        parts = raw.split(maxsplit=2)
        if len(parts) < 3: return await event.edit("❌ Формат: `отправь @user текст`")
        try:
            await tg.send_message(parts[1], parts[2])
            await event.edit(f"✅ **Отправлено для {parts[1]}**")
        except Exception as e: await event.edit(f"❌ Ошибка: {e}")
        return

    # 3. AFK РЕЖИМ
    if low.startswith("afk"):
        afk_mode = True
        afk_reason = raw[4:].strip() or "отдыхает"
        afk_replied = set()
        return await event.edit(f"💤 **Режим AFK активирован:** {afk_reason}")

    if low == "back" or low == "я тут":
        afk_mode = False
        return await event.edit("🌞 **С возвращением, сэр!** Режим AFK выключен.")

    # 4. ИНТЕЛЛЕКТ (AI)
    me = await tg.get_me()
    is_saved = event.is_private and event.chat_id == me.id
    
    if low.startswith("ai ") or low.startswith("джарвис ") or is_saved:
        query = raw
        for p in ["ai ", "ai", "джарвис ", "джарвис"]:
            if low.startswith(p): query = raw[len(p):].strip(); break
        if not query: return
        
        await event.edit("⚡ **Обработка...**")
        ans = await ai_call(event.chat_id, query)
        await event.edit(f"🤖 **JARVIS:**\n{ans}")

# Автоответчик AFK
@tg.on(events.NewMessage(incoming=True))
async def afk_listener(event):
    if afk_mode and not event.is_channel and event.sender_id not in afk_replied:
        afk_replied.add(event.sender_id)
        await event.reply(f"🛰 **JARVIS:** Сэр сейчас отсутствует ({afk_reason}). Я передам ему, что вы писали.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЗАПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start_system():
    await tg.start()
    print("✅ JARVIS ПОЛНОСТЬЮ УКОМПЛЕКТОВАН")
    await tg.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start() # Запуск веб-сервера
    asyncio.run(start_system())
