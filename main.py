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
PROMPT    = "Ты JARVIS — ИИ Тони Старка. Отвечай кратко, саркастично, называй владельца 'сэр'."
MIMIC_PROMPT = "Ты обычный парень. Пиши кратко, без заглавных букв, используй сленг, делай опечатки. Не пались, что ты ИИ."

tg = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
msg_cache = {}
mimic_mode = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ВЕБ-СЕРВЕР (Keep-Alive)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask('')
@app.route('/')
def home(): return "SYSTEM ONLINE"
def run_web(): app.run(host='0.0.0.0', port=8080)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЯДРО ИИ (Groq)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def ai_call(text, custom_prompt=PROMPT):
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "system", "content": custom_prompt}, {"role": "user", "content": text}]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            return resp.json()['choices'][0]['message']['content']
        except: return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ОБРАБОТЧИК КОМАНД (Outgoing)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(outgoing=True))
async def cmd_handler(event):
    global mimic_mode
    raw = event.text.strip().lower()

    if raw == "ping":
        start = time.time(); await event.edit("🚀"); ms = round((time.time() - start) * 1000)
        return await event.edit(f"🛰 **Latency:** `{ms}ms` | **Engine:** Groq")

    if raw == "мимикрия вкл":
        mimic_mode = True; return await event.edit("🎭 **Mimicry:** ON")
    
    if raw == "мимикрия выкл":
        mimic_mode = False; return await event.edit("🎭 **Mimicry:** OFF")

    if raw.startswith("del"):
        await event.delete()
        if event.is_reply: (await event.get_reply_message()).delete()
        return

    if raw.startswith(("ai ", "джарвис ")):
        query = event.text.split(maxsplit=1)[1] if " " in event.text else None
        if not query: return
        await event.edit("⚡ **Processing...**")
        ans = await ai_call(query)
        await event.edit(f"🤖 **JARVIS:**\n{ans}" if ans else "❌ Error")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  МОНИТОРИНГ (Incoming & Ghost)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@tg.on(events.NewMessage(incoming=True))
async def monitor(event):
    global mimic_mode
    # Кэшируем сообщения для Anti-Delete
    if event.chat_id and event.text:
        msg_cache[event.id] = {'text': event.text, 'sender': event.sender_id}
        if len(msg_cache) > 500: msg_cache.pop(next(iter(msg_cache)))

    # Социальная мимикрия (только ЛС)
    if mimic_mode and event.is_private and not (await event.get_sender()).bot:
        async with tg.action(event.chat_id, 'typing'):
            await asyncio.sleep(len(event.text) * 0.1 + 1)
            ans = await ai_call(event.text, MIMIC_PROMPT)
            if ans: await event.reply(ans.lower())

    # Media Sniper (исчезающие фото)
    if event.media and hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds:
        file = await event.download_media()
        await tg.send_file("me", file, caption=f"📸 **Sniper:** Saved self-destructing media from `{event.sender_id}`")
        os.remove(file)

@tg.on(events.MessageDeleted())
async def del_log(event):
    for mid in event.deleted_ids:
        if mid in msg_cache:
            d = msg_cache[mid]
            await tg.send_message("me", f"🕵️ **Deleted:**\n👤 `{d['sender']}`\n📝 {d['text']}")

@tg.on(events.MessageEdited())
async def edit_log(event):
    if event.id in msg_cache:
        old = msg_cache[event.id]['text']
        if old != event.text:
            await tg.send_message("me", f"📝 **Edited:**\n❌ Old: {old}\n✅ New: {event.text}")
            msg_cache[event.id]['text'] = event.text

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RUN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start():
    await tg.start(); print("✅ JARVIS ULTIMATE ONLINE"); await tg.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(start())
