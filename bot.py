import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import random
import hashlib
import logging
import threading
import os

# === НАСТРОЙКИ ===
BOT_TOKEN = "8287060486:AAH0tRlAnM2s4rYXKQRDlIB-XMZOhTcMuyI"  # Ваш токен
ADMIN_IDS = [8139807344, 5255608302]

# ВАШ ДОМЕН С HTTPS (ЗАМЕНИТЕ!)
YOUR_DOMAIN = "xxx.bothost.ru"  # ⬅️ ЗАМЕНИТЕ НА ВАШ
MINI_APP_URL = f"https://{YOUR_DOMAIN}/basketball"

# Секретный ключ для токенов
SECRET_KEY = "basketball_bot_secret_key_2024_change_this"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

bot = telebot.TeleBot(BOT_TOKEN)

# === БАЗА ДАННЫХ ===
def get_db():
    conn = sqlite3.connect('game.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Пользователи
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Статистика баскетбола
    c.execute('''
    CREATE TABLE IF NOT EXISTS basketball_stats (
        user_id INTEGER PRIMARY KEY,
        total_hits INTEGER DEFAULT 0,
        total_misses INTEGER DEFAULT 0,
        best_streak INTEGER DEFAULT 0,
        current_streak INTEGER DEFAULT 0,
        total_earned INTEGER DEFAULT 0,
        last_played TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Дневные рекорды
    c.execute('''
    CREATE TABLE IF NOT EXISTS basketball_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date DATE DEFAULT CURRENT_DATE,
        score INTEGER DEFAULT 0,
        earned INTEGER DEFAULT 0
    )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База готова")

# === ПОМОЩНИКИ ===
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(user_id, username, first_name):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
        (user_id, username, first_name)
    )
    conn.commit()
    conn.close()

def add_money(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result['balance'] if result else 0

def format_money(amount):
    return f"{amount:,}".replace(",", " ")

# === ТОКЕН ДЛЯ МИНИ-ПРИЛОЖЕНИЯ ===
def make_token(user_id, username):
    timestamp = int(time.time())
    data = f"{user_id}:{username}:{timestamp}:{SECRET_KEY}"
    return hashlib.sha256(data.encode()).hexdigest()[:20]

# === ГЛАВНОЕ МЕНЮ ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    create_user(user_id, username, first_name)
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("🏀 Мини-Баскетбол"),
        KeyboardButton("💰 Баланс"),
        KeyboardButton("📊 Статистика"),
        KeyboardButton("🏆 Топ"),
        KeyboardButton("🎰 Казино"),
        KeyboardButton("💼 Работа")
    )
    
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {first_name}!\n\n"
        f"🏀 *Новое мини-приложение: БАСКЕТБОЛ!*\n"
        f"Зарабатывай ❄️, бросая мяч в корзину!\n\n"
        f"Нажми '🏀 Мини-Баскетбол' чтобы начать!",
        parse_mode='Markdown',
        reply_markup=markup
    )

# === ЗАПУСК МИНИ-ПРИЛОЖЕНИЯ ===
@bot.message_handler(func=lambda m: m.text == "🏀 Мини-Баскетбол")
def launch_mini_app(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        
        # Создаем токен
        token = make_token(user_id, username)
        
        # URL мини-приложения
        game_url = f"{MINI_APP_URL}?user_id={user_id}&token={token}"
        
        # Кнопка для запуска
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "🎮 ЗАПУСТИТЬ МИНИ-ПРИЛОЖЕНИЕ",
                web_app=telebot.types.WebAppInfo(url=game_url)
            )
        )
        
        bot.send_message(
            message.chat.id,
            f"🏀 *МИНИ-ПРИЛОЖЕНИЕ: БАСКЕТБОЛ*\n\n"
            f"🔗 Ссылка: `{YOUR_DOMAIN}`\n"
            f"👤 Игрок: {username}\n\n"
            f"*Правила:*\n"
            f"• Брось мяч в корзину\n"
            f"• За попадание: +25❄️\n"
            f"• Серия попаданий: бонус\n"
            f"• Рекорд дня: 10.000❄️\n\n"
            f"Нажми кнопку ниже чтобы начать играть! 🎯",
            parse_mode='Markdown',
            reply_markup=markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

# === ОСТАЛЬНЫЕ КОМАНДЫ ===
@bot.message_handler(func=lambda m: m.text == "💰 Баланс")
def balance_cmd(message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {format_money(balance)}❄️")

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats_cmd(message):
    user_id = message.from_user.id
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        SELECT total_hits, total_misses, best_streak, total_earned 
        FROM basketball_stats 
        WHERE user_id = ?
    ''', (user_id,))
    
    stats = c.fetchone()
    conn.close()
    
    if stats:
        accuracy = (stats['total_hits'] / (stats['total_hits'] + stats['total_misses'] * 1.0)) * 100 if (stats['total_hits'] + stats['total_misses']) > 0 else 0
        
        text = (
            f"📊 *Ваша статистика баскетбола:*\n\n"
            f"🎯 Попаданий: {stats['total_hits']}\n"
            f"❌ Промахов: {stats['total_misses']}\n"
            f"📈 Точность: {accuracy:.1f}%\n"
            f"🔥 Лучшая серия: {stats['best_streak']}\n"
            f"💰 Заработано: {format_money(stats['total_earned'])}❄️"
        )
    else:
        text = "📭 У вас еще нет статистики. Сыграйте в баскетбол!"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# === ЗАПУСК БОТА ===
if __name__ == "__main__":
    print("🔧 Инициализация базы данных...")
    init_db()
    
    print(f"🌐 Домен мини-приложения: {MINI_APP_URL}")
    print("🤖 Бот запускается...")
    
    bot.polling(none_stop=True)
