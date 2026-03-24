import httpx, time, asyncio, os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask
from threading import Thread

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КОНФИГУРАЦИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_ID    = 26616230
API_HASH  = "895c0f50a04747d3342b0b9ee83e19cd"
GROQ_KEY  = "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"
SESSION   = "1ApWapzMBu7ewG6tsX055ejFjJC5mhuQVAmOwBgavHdWHFIuKdOE7_evf0_o9RrLaOFuYXyYefc8pYPotY2eSeypMldV_ab6Mr3ZeSKH285IXgFUOoChXdrzBNFJzgQc-OmhNmrEiSYTMcXB3vJrH9ofWx1pyungUtAJ2OxajJWMd6eh9h42B0B73GBWQ6nTV8FwyV8NP5ux7LdV5gV0Fgp8JE7x_FoS7m03hIR_e8ISbWkQM9DaBByUaCc7GTORLOyBgf3RjuhA30aa9k97izyMqM59RprerrKbpsFz2A4sprUUVStqqLtvtgYs0tugNoxOVbr7cr9S0_EiDXV87Uz_SMV-cRvs="

MODEL     = "llama-3.3-70b-versatile"
# Промпт для личного использования
JARVIS_PROMPT = "Ты JARVIS — ИИ-ассистент. Отвечай кратко, саркастично, называй владельца 'сэр'."
# Промпт для тех, кто пишет вам (Мимикрия/Автоответчик)
ASSISTANT_PROMPT = (
    "Ты JARVIS, электронный ассистент владельца этого аккаунта. "
    "Владелец сейчас занят разработкой кода и не может ответить. "
    "Сразу скажи, что отвечает ИИ-ассистент Джарвис. "
    "Будь вежлив, но краток. Отвечай на вопросы по боту или по делу. "
    "Пиши как продвинутый ИИ."
)

tg = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
msg_cache = {} # Для удаленок
ai_memory = {} # Для контекста диалогов
mimic_mode = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KEEP-ALIVE (Render)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask('')
@app.route('/')
def home(): return "SYSTEM ONLINE"
def run_web(): app.run(host='0.0.0.0', port=8080)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  УМНЫЙ ИИ С ПАМЯТЬЮ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(chat_id, text, system_role):
    global ai_memory
    if chat_id not in ai_memory: ai_memory[chat_id] = []
    
    # Добавляем сообщение в историю
    ai_memory[chat_id].append({"role": "user", "content": text})
    if len(ai_memory[chat_id]) > 10: ai_memory[chat_id] = ai_memory[chat_id][-10:]

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system_role}] + ai_memory[chat_id],
        "temperature": 0.6
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
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
    raw = event.text.strip().lower()

    if raw == "ping":
        start = time.time(); await event.edit("🚀"); ms = round((time.time() - start) * 1000)
        return await event.edit(f"🛰 **Latency:** `{ms}ms`")

    if raw == "мимикрия вкл":
        mimic_mode = True; return await event.edit("🤖 **Режим Ассистента:** Активирован.")
    
    if raw == "мимикрия выкл":
        mimic_mode = False; return await event.edit("🤖 **Режим Ассистента:** Выключен.")
    
    if raw == "очистить кэш":
        ai_memory = {}; msg_cache = {}
        return await event.edit("🧹 **Вся память JARVIS очищена.**")

    if raw.startswith(("ai ", "джарвис ")):
        query = event.text.split(maxsplit=1)[1] if " " in event.text else None
        if not query: return
        await event.edit("⚡ **Считываю данные...**")
        ans = await ai_call(event.chat_id, query, JARVIS_PROMPT)
        await event.edit(f"🤖 **JARVIS:**\n{ans}" if ans else "❌ Сбой связи.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  АВТОПИЛОТ И ПРИЗРАК (Входящие)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(incoming=True))
async def monitor(event):
    global mimic_mode
    # Сохраняем для Anti-Delete
    if event.chat_id and event.text:
        msg_cache[event.id] = {'text': event.text, 'sender': event.sender_id}

    # Автоответчик "Ассистент Кодера"
    if mimic_mode and event.is_private and not (await event.get_sender()).bot:
        async with tg.action(event.chat_id, 'typing'):
            await asyncio.sleep(2) # Имитация задержки
            ans = await ai_call(event.chat_id, event.text, ASSISTANT_PROMPT)
            if ans: await event.reply(ans)

    # Media Sniper (исчезающие фото)
    if event.media and hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds:
        file = await event.download_media()
        await tg.send_file("me", file, caption=f"📸 **Sniper:** Файл от `{event.sender_id}` сохранен.")
        os.remove(file)

@tg.on(events.MessageDeleted())
async def del_log(event):
    for mid in event.deleted_ids:
        if mid in msg_cache:
            d = msg_cache[mid]
            await tg.send_message("me", f"🕵️ **Удалено:**\n👤 `{d['sender']}`\n📝 {d['text']}")

@tg.on(events.MessageEdited())
async def edit_log(event):
    if event.id in msg_cache:
        old = msg_cache[event.id]['text']
        if old != event.text:
            await tg.send_message("me", f"📝 **Изменено:**\n❌ Было: {old}\n✅ Стало: {event.text}")
            msg_cache[event.id]['text'] = event.text

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЗАПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start():
    await tg.start(); print("✅ JARVIS READY"); await tg.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(start())
