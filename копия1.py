import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import random
import os
import re
import shutil
from datetime import datetime, timedelta
import threading
import logging
import io
from PIL import Image
import base64
import zipfile
import json

BOT_TOKEN = "8287060486:AAH0tRlAnM2s4rYXKQRDlIB-XMZOhTcMuyI"

ADMIN_IDS = [8139807344, 5255608302]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

bot = telebot.TeleBot(BOT_TOKEN)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_last_action = {}
user_captcha_status = {}
user_bonus_cooldown = {}
bonus_processing = set()
pending_ref_codes = {}
SNOW_COOLDOWN = {}
SNOW_JOBS = {}
SNOW_LAST_MESSAGE = {}
COURIER_JOBS = {}
COURIER_STATS = {}
HOUSE_SHOP = {}
user_top_page = {}
user_top_mode = {}
ACTIVE_CONTESTS = {}
CONTEST_PARTICIPANTS = {}

# ========== НАСТРОЙКИ ==========
MINING_EXCHANGE_RATE = 70
REQUIRED_CHANNEL = "@FECTIZ"
MIN_BONUS = 100
MAX_BONUS = 2000

# ========== СИСТЕМА УРОВНЕЙ ==========
LEVEL_SYSTEM = {
    1: {"name": "Новичок", "exp_required": 0, "unlocks": ["Игры"]},
    3: {"name": "Ученик", "exp_required": 50000, "unlocks": ["Работа: Чистка снега"]},
    5: {"name": "Игрок", "exp_required": 200000, "unlocks": ["Банк (вклады)"]},
    7: {"name": "Опытный", "exp_required": 500000, "unlocks": ["Система домов"]},
    10: {"name": "Майнер", "exp_required": 1000000, "unlocks": ["Майнинг ферма"]},
    15: {"name": "Курьер", "exp_required": 2500000, "unlocks": ["Работа: Курьер"]},
    20: {"name": "Мастер", "exp_required": 5000000, "unlocks": ["Премиум бонусы"]},
    25: {"name": "Легенда", "exp_required": 10000000, "unlocks": ["Все функции"]}
}

COURIER_LEVELS = {
    1: {"name": "🛵 Начинающий", "deliveries": 3, "pay": 80, "xp_needed": 5, "cooldown": 180},
    2: {"name": "🚲 Курьер", "deliveries": 4, "pay": 110, "xp_needed": 10, "cooldown": 180},
    3: {"name": "🚗 Профи", "deliveries": 5, "pay": 150, "xp_needed": 15, "cooldown": 180},
    4: {"name": "🚚 Эксперт", "deliveries": 6, "pay": 200, "xp_needed": 20, "cooldown": 180},
    5: {"name": "✈️ Мастер", "deliveries": 7, "pay": 260, "xp_needed": 25, "cooldown": 180}
}

ADDRESSES = ["🏢 Центр", "🌳 Парк", "🏘️ Жилой", "🏬 ТЦ", "🏛️ Администрация", "🎓 Университет", "🏥 Больница"]
PACKAGES = ["📦 Посылка", "📮 Письмо", "🎁 Подарок", "📚 Документы", "💻 Техника", "🌿 Растение"]

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    conn = sqlite3.connect('game.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            nickname TEXT,
            balance INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            experience INTEGER DEFAULT 0,
            last_click INTEGER DEFAULT 0,
            click_power INTEGER DEFAULT 2,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            video_cards INTEGER DEFAULT 0,
            deposit INTEGER DEFAULT 0,
            last_mining_collect INTEGER DEFAULT 0,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            click_streak INTEGER DEFAULT 0,
            bank_deposit INTEGER DEFAULT 0,
            captcha_passed INTEGER DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            banned_at TIMESTAMP,
            last_interest_calc INTEGER DEFAULT 0,
            last_snow_work TIMESTAMP,
            snow_cooldown_end TIMESTAMP,
            current_snow_job TEXT,
            snow_job_progress INTEGER DEFAULT 0,
            snow_job_total INTEGER DEFAULT 0,
            snow_job_end_time TIMESTAMP,
            snow_territory TEXT,
            last_bonus INTEGER DEFAULT 0,
            mining_trees INTEGER DEFAULT 0,
            mining_balance INTEGER DEFAULT 0
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS checks (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            max_activations INTEGER,
            current_activations INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_activations (
            user_id INTEGER,
            check_code TEXT,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, check_code),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (check_code) REFERENCES checks(code) ON DELETE CASCADE
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_houses (
            user_id INTEGER,
            house_id TEXT,
            is_current INTEGER DEFAULT 0,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, house_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referral_wins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referee_id INTEGER,
            win_amount INTEGER,
            bonus_amount INTEGER,
            game_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (referee_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contests (
            contest_id TEXT PRIMARY KEY,
            channel_id INTEGER,
            channel_title TEXT,
            max_participants INTEGER,
            winners_count INTEGER,
            prizes_text TEXT,
            creator_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (creator_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contest_participants (
            contest_id TEXT,
            user_id INTEGER,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (contest_id, user_id),
            FOREIGN KEY (contest_id) REFERENCES contests(contest_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS mining_stats (
            user_id INTEGER PRIMARY KEY,
            total_mined INTEGER DEFAULT 0,
            total_exchanged INTEGER DEFAULT 0,
            last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Индексы
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_level ON users(level)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_total_earned ON users(total_earned)')
        
        # Проверяем и добавляем колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'level' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
        if 'total_earned' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN total_earned INTEGER DEFAULT 0")
        if 'experience' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN experience INTEGER DEFAULT 0")
        
        conn.commit()
        logging.info("База данных инициализирована")
        
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_banned(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned, ban_reason FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0] == 1:
        return True, result[1] if result[1] else "Причина не указана"
    return False, None

def is_spam(user_id):
    current_time = time.time()
    if user_id in user_last_action:
        time_passed = current_time - user_last_action[user_id]
        if time_passed < 1:
            return True
    user_last_action[user_id] = current_time
    return False

def format_balance(balance):
    return f"{balance:,}".replace(",", " ")

def parse_bet_amount(bet_text, user_balance):
    if bet_text.lower() in ['все', 'all']:
        return user_balance
    
    bet_text = bet_text.lower().replace(' ', '')
    
    pattern = r'^(\d*\.?\d+)([кk]|[кk]{2,}|[mb]?)$'
    match = re.match(pattern, bet_text)
    
    if match:
        number_part = match.group(1)
        multiplier_part = match.group(2)
        
        try:
            number = float(number_part)
            
            if multiplier_part.startswith('к') or multiplier_part.startswith('k'):
                k_count = multiplier_part.count('к') + multiplier_part.count('k')
                if k_count == 1:
                    multiplier = 1000
                elif k_count == 2:
                    multiplier = 1000000
                else:
                    multiplier = 1000000000
            elif multiplier_part == 'm':
                multiplier = 1000000
            elif multiplier_part == 'b':
                multiplier = 1000000000
            else:
                multiplier = 1
            
            return int(number * multiplier)
        except:
            return None
    
    try:
        return int(bet_text)
    except:
        return None

def get_or_create_user(user_id, username, first_name):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        referral_code = f"ref{user_id}"
        
        cursor.execute(
            '''INSERT INTO users (user_id, username, first_name, balance, referral_code, 
            video_cards, deposit, last_mining_collect, click_streak, bank_deposit, 
            captcha_passed, is_banned, last_interest_calc, mining_balance, level, total_earned, experience) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, 
             datetime.now().timestamp(), 0, 1, 0, 0)
        )
        conn.commit()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_balance(user_id, amount, source="игра"):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('UPDATE users SET balance = balance + ?, last_activity = CURRENT_TIMESTAMP WHERE user_id = ?', 
                  (amount, user_id))
    
    if amount > 0:
        cursor.execute('UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?', (amount, user_id))
        
        experience_gained = max(1, int(amount * 0.01))
        cursor.execute('UPDATE users SET experience = experience + ? WHERE user_id = ?', 
                      (experience_gained, user_id))
        
        cursor.execute('SELECT level, experience FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if user_data:
            current_level = user_data[0] or 1
            current_exp = user_data[1] or 0
            
            for level, data in LEVEL_SYSTEM.items():
                if level > current_level and current_exp >= data['exp_required']:
                    cursor.execute('UPDATE users SET level = ? WHERE user_id = ?', (level, user_id))
                    
                    try:
                        level_info = LEVEL_SYSTEM.get(level, {})
                        unlocks = level_info.get('unlocks', [])
                        unlocks_text = "\n".join([f"• {item}" for item in unlocks]) if unlocks else "• Новые бонусы!"
                        
                        bot.send_message(
                            user_id,
                            f"🎉 *НОВЫЙ УРОВЕНЬ!*\n\n"
                            f"⬆️ {level_info.get('name', f'Уровень {level}')}\n"
                            f"📊 Уровень: {level}\n"
                            f"💎 Опыт: {format_balance(current_exp)}\n\n"
                            f"🔓 *Открыто:*\n{unlocks_text}\n\n"
                            f"Продолжайте играть!",
                            parse_mode='Markdown'
                        )
                    except:
                        pass
    
    conn.commit()
    conn.close()
    return True

def get_balance(user_id):
    calculate_interest(user_id)
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def calculate_interest(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT bank_deposit, last_interest_calc FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] > 0:
        bank_deposit, last_calc = result
        
        if isinstance(last_calc, str):
            try:
                last_calc_time = datetime.strptime(last_calc, '%Y-%m-%d %H:%M:%S').timestamp()
            except:
                last_calc_time = time.time() - 3600
        elif isinstance(last_calc, float) or isinstance(last_calc, int):
            last_calc_time = last_calc
        else:
            last_calc_time = time.time() - 3600
        
        current_time = time.time()
        hours_passed = (current_time - last_calc_time) / 3600
        
        if hours_passed >= 1:
            interest_hours = int(hours_passed)
            interest = int(bank_deposit * 0.005 * interest_hours)
            
            if interest > 0:
                cursor.execute('UPDATE users SET balance = balance + ?, last_interest_calc = ? WHERE user_id = ?',
                             (interest, current_time, user_id))
                conn.commit()
                
                try:
                    bot.send_message(
                        user_id,
                        f"🏦 НАЧИСЛЕНЫ ПРОЦЕНТЫ ПО ВКЛАДУ!\n\n"
                        f"💰 На вкладе: ❄️{format_balance(bank_deposit)}\n"
                        f"📈 Начислено: +❄️{format_balance(interest)}\n"
                        f"⏰ Проценты начисляются каждый час",
                        parse_mode='Markdown'
                    )
                except:
                    pass
    
    conn.close()

def get_user_level(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT level FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result['level'] if result else 1
    except:
        return 1

def check_level_requirement(user_id, required_level):
    user_level = get_user_level(user_id)
    if user_level < required_level:
        next_level_data = LEVEL_SYSTEM.get(required_level, {})
        exp_required = next_level_data.get('exp_required', 0)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT experience FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        current_exp = result['experience'] if result else 0
        exp_needed = max(0, exp_required - current_exp)
        
        level_info = LEVEL_SYSTEM.get(required_level, {})
        level_name = level_info.get('name', f'Уровень {required_level}')
        unlocks = level_info.get('unlocks', ['Новые возможности'])
        
        unlocks_text = "\n".join([f"• {item}" for item in unlocks])
        
        return False, f"""
🚫 *ДОСТУП ЗАКРЫТ!*

Требуется уровень: {required_level} ({level_name})
Ваш уровень: {user_level}

📊 *До уровня осталось:* {format_balance(exp_needed)} опыта

🔓 *Откроется доступ к:*
{unlocks_text}

💡 *Как повысить уровень?*
• Играйте в игры (1% от выигрыша = опыт)
• Выполняйте работу
• Приглашайте друзей
• Получайте бонусы
"""
    
    return True, ""

# ========== СИСТЕМА УРОВНЕЙ (дополнительные функции) ==========
def add_experience(user_id, amount, source="игра"):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET experience = experience + ? WHERE user_id = ?', (amount, user_id))
        
        cursor.execute('SELECT level, experience FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            conn.close()
            return
        
        current_level = user_data['level'] or 1
        current_exp = user_data['experience'] or 0
        
        new_level = current_level
        for level, data in LEVEL_SYSTEM.items():
            if level > current_level and current_exp >= data['exp_required']:
                new_level = level
        
        if new_level > current_level:
            cursor.execute('UPDATE users SET level = ? WHERE user_id = ?', (new_level, user_id))
            
            level_info = LEVEL_SYSTEM.get(new_level, {})
            level_name = level_info.get('name', f'Уровень {new_level}')
            
            try:
                unlocks = level_info.get('unlocks', [])
                unlocks_text = "\n".join([f"• {item}" for item in unlocks]) if unlocks else "• Новые бонусы!"
                
                bot.send_message(
                    user_id,
                    f"🎉 *НОВЫЙ УРОВЕНЬ!*\n\n"
                    f"⬆️ {level_name}\n"
                    f"📊 Уровень: {new_level}\n"
                    f"💎 Опыт: {format_balance(current_exp)}\n\n"
                    f"🔓 *Открыто:*\n{unlocks_text}\n\n"
                    f"Продолжайте играть!",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка добавления опыта: {e}")

def get_level_progress(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT level, experience FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return 1, 0, 0, 0
        
        current_level = result['level'] or 1
        current_exp = result['experience'] or 0
        
        next_level = current_level + 1
        next_level_data = LEVEL_SYSTEM.get(next_level)
        
        if not next_level_data:
            return current_level, current_exp, 0, 100
        
        exp_required = next_level_data['exp_required']
        exp_needed = max(0, exp_required - current_exp)
        progress_percent = min(100, int((current_exp / exp_required) * 100)) if exp_required > 0 else 100
        
        return current_level, current_exp, exp_needed, progress_percent
        
    except:
        return 1, 0, 0, 0

# ========== КАПЧА ==========
def generate_captcha():
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    operation = random.choice(['+', '-', '*'])
    
    if operation == '+':
        answer = num1 + num2
    elif operation == '-':
        answer = num1 - num2
    else:
        answer = num1 * num2
    
    captcha_question = f"{num1} {operation} {num2} = ?"
    
    return captcha_question, str(answer)

# ========== МЕНЮ ==========
def create_main_menu(chat_id, user_level=1):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if chat_id > 0:
        buttons = [
            KeyboardButton("Я"),
            KeyboardButton("Топ снежков"),
            KeyboardButton("Бонус")
        ]
        
        if user_level >= 1:
            buttons.append(KeyboardButton("Игры"))
        
        if user_level >= 3:
            buttons.append(KeyboardButton("Работа"))
        
        if user_level >= 5:
            buttons.append(KeyboardButton("Банк"))
        
        if user_level >= 7:
            buttons.append(KeyboardButton("🏠 Дом"))
        
        if user_level >= 10:
            buttons.append(KeyboardButton("Майнинг"))
        
        markup.add(*buttons)
    else:
        markup.add(
            KeyboardButton("Баланс"),
            KeyboardButton("Топ снежков"),
            KeyboardButton("Бонус")
        )
    
    return markup

# ========== СТАРТ ==========
@bot.message_handler(commands=['start'])
def start(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        start_param = None
        if len(message.text.split()) > 1:
            start_param = message.text.split()[1].strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            is_new_user = True
            referral_code = f"ref{user_id}"
            
            cursor.execute(
                '''INSERT INTO users (user_id, username, first_name, balance, referral_code, 
                video_cards, deposit, last_mining_collect, click_streak, bank_deposit, 
                captcha_passed, is_banned, last_interest_calc, mining_balance, level, total_earned, experience) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, 
                 datetime.now().timestamp(), 0, 1, 0, 0)
            )
            conn.commit()
            
            if start_param and start_param.startswith('ref'):
                pending_ref_codes[user_id] = start_param
            
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для регистрации решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        captcha_passed = user_data[0]
        
        if captcha_passed == 0:
            if start_param and start_param.startswith('ref'):
                pending_ref_codes[user_id] = start_param
            
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для доступа к боту решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        conn.close()
        
        if start_param:
            process_ref_or_check(user_id, username, first_name, start_param)
        
        user_level = get_user_level(user_id)
        markup = create_main_menu(message.chat.id, user_level)
        
        if message.chat.id > 0:
            welcome_text = f"✨ Добро пожаловать! ✨\n\n📊 Ваш уровень: {user_level}\n\nВыберите действие из меню ниже:"
        else:
            welcome_text = f"👋 Привет, {first_name}!\n\n📊 Ваш уровень: {user_level}\n\nИспользуйте меню ниже для работы с ботом."
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')
    
    except Exception as e:
        logging.error(f"Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте снова позже.")

# ========== ПРОФИЛЬ ==========
@bot.message_handler(func=lambda message: message.text == "Я")
def handle_me(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT first_name, nickname, level, experience, total_earned, 
                   video_cards, bank_deposit, mining_balance, registered_at
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            first_name, nickname, level, experience, total_earned, video_cards, bank_deposit, mining_balance, registered_at = result
            
            _, _, exp_needed, progress_percent = get_level_progress(user_id)
            
            display_name = nickname if nickname and nickname.strip() else first_name
            
            level_info = LEVEL_SYSTEM.get(level, {})
            level_name = level_info.get('name', f'Уровень {level}')
            
            reg_date = "Неизвестно"
            if registered_at:
                try:
                    reg_date = registered_at[:10]
                except:
                    reg_date = str(registered_at)[:10]
            
            message_text = f"👤 *{display_name}*\n"
            message_text += f"🎮 Уровень {level} ({level_name})\n\n"
            
            progress_bars = 10
            filled_bars = int(progress_percent / 10)
            progress_bar = "🟦" * filled_bars + "⬜" * (progress_bars - filled_bars)
            
            message_text += f"{progress_bar} {progress_percent}%\n"
            if exp_needed > 0:
                message_text += f"📈 До {level+1} уровня: {format_balance(exp_needed)} опыта\n\n"
            
            message_text += f"💰 *Баланс:* ❄️{format_balance(balance)}\n"
            
            if mining_balance and mining_balance > 0:
                message_text += f"🎄 *Елки:* {mining_balance}🎄\n"
            
            if bank_deposit and bank_deposit > 0:
                message_text += f"🏦 *В банке:* ❄️{format_balance(bank_deposit)}\n"
            
            message_text += f"💎 *Всего заработано:* ❄️{format_balance(total_earned)}\n"
            message_text += f"📅 *Регистрация:* {reg_date}\n\n"
            
            message_text += "*🔓 Доступно:*\n"
            if level >= 1:
                message_text += "• Игры 🎮\n"
            if level >= 3:
                message_text += "• Работа 💼\n"
            if level >= 5:
                message_text += "• Банк 🏦\n"
            if level >= 7:
                message_text += "• Дома 🏠\n"
            if level >= 10:
                message_text += "• Майнинг ⛏️\n"
            if level >= 15:
                message_text += "• Курьер 🚚\n"
            
            next_level_to_unlock = None
            for lvl in sorted(LEVEL_SYSTEM.keys()):
                if lvl > level:
                    next_level_to_unlock = lvl
                    break
            
            if next_level_to_unlock:
                next_level_info = LEVEL_SYSTEM.get(next_level_to_unlock, {})
                next_unlocks = next_level_info.get('unlocks', [])
                if next_unlocks:
                    message_text += f"\n*🔜 На {next_level_to_unlock} уровне:*\n"
                    for unlock in next_unlocks[:2]:
                        message_text += f"• {unlock}\n"
            
            bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
            
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
        
        conn.close()
    
    except Exception as e:
        logging.error(f"Ошибка в handle_me: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# ========== ИГРЫ ==========
@bot.message_handler(func=lambda message: message.text == "Игры")
def handle_games_menu(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        
        has_access, access_message = check_level_requirement(message.from_user.id, 1)
        if not has_access:
            bot.send_message(message.chat.id, access_message, parse_mode='Markdown')
            return
        
        games_text = """
🎮 *ИГРЫ*

Выберите игру:

*🎰 Рулетка*
`рул [ставка] [тип]`
Типы: число(0-36), красный/черный, чет/нечет, большие/малые

*🎲 Кубик*
`куб [ставка] [тип]`
Типы: число(1-6), чет/нечет, большие/малые

*⚽ Футбол*
`фтб [ставка]`
Выигрыш x1.5

*🏀 Баскетбол*
`бск [ставка]`
Выигрыш x2.5

*🎯 Дартс*
`дартс [ставка]`
Победа: x5, Штраф: -2x

*🎳 Боулинг*
`боул [ставка]`
Победа: x2, Возврат при 1 кегле

*🎰 Слоты*
`слот [ставка]`
Джекпот: x64
"""
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🎰 Рулетка", callback_data="game_roulette_info"),
            InlineKeyboardButton("🎲 Кубик", callback_data="game_dice_info"),
            InlineKeyboardButton("⚽ Футбол", callback_data="game_football_info"),
            InlineKeyboardButton("🏀 Баскетбол", callback_data="game_basketball_info"),
            InlineKeyboardButton("🎯 Дартс", callback_data="game_darts_info"),
            InlineKeyboardButton("🎳 Боулинг", callback_data="game_bowling_info"),
            InlineKeyboardButton("🎰 Слоты", callback_data="game_slots_info")
        )
        
        bot.send_message(message.chat.id, games_text, parse_mode='Markdown', reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в меню игр: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# ========== РАБОТА ==========
@bot.message_handler(func=lambda message: message.text == "Работа")
def handle_work_menu(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        
        has_access, access_message = check_level_requirement(message.from_user.id, 3)
        if not has_access:
            bot.send_message(message.chat.id, access_message, parse_mode='Markdown')
            return
        
        work_text = """
💼 *РАБОТА*

Выберите работу:

*❄️ Чистка снега*
- 100 кликов
- Награда: от 1000❄️
- Штраф за ошибки
- Перезарядка: 3 минуты

*🚚 Курьер* (требуется 15 уровень)
- Доставка посылок
- Повышение уровня
- Заработок от 80❄️ за доставку
"""
        
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        buttons = [KeyboardButton("❄️ Чистка снега")]
        
        if user_level >= 15:
            buttons.append(KeyboardButton("🚚 Курьер"))
        
        buttons.append(KeyboardButton("◀️ Назад"))
        markup.add(*buttons)
        
        bot.send_message(message.chat.id, work_text, parse_mode='Markdown', reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в меню работы: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# ========== БАНК ==========
@bot.message_handler(func=lambda message: message.text == "Банк")
def handle_bank_menu(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        
        has_access, access_message = check_level_requirement(message.from_user.id, 5)
        if not has_access:
            bot.send_message(message.chat.id, access_message, parse_mode='Markdown')
            return
        
        user_id = message.from_user.id
        bank_deposit = get_bank_deposit(user_id)
        
        bank_text = f"""
🏦 *БАНК*

*Ваш вклад:* ❄️{format_balance(bank_deposit)}
*Проценты:* 0.5% каждый час
*Начисление:* автоматически

*Команды:*
`вклад [сумма]` - положить деньги под проценты
`снять [сумма]` - забрать деньги с вклада

*Примеры:*
`вклад 1000` - положить 1000❄️
`вклад все` - положить все деньги
`снять 500к` - снять 500,000❄️
"""
        
        bot.send_message(message.chat.id, bank_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в меню банка: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

def get_bank_deposit(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT bank_deposit FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_bank_deposit(user_id, amount):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET bank_deposit = bank_deposit + ?, last_interest_calc = ? WHERE user_id = ?',
                  (amount, datetime.now().timestamp(), user_id))
    conn.commit()
    conn.close()
    return True

@bot.message_handler(func=lambda message: message.text.lower().startswith('вклад '))
def handle_deposit(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        if user_level < 5:
            bot.send_message(message.chat.id, "🚫 Банк доступен с 5 уровня!")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        bank_deposit = get_bank_deposit(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: вклад 1000к")
            return
        
        deposit_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if deposit_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if deposit_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if deposit_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств на балансе")
            return
        
        update_balance(user_id, -deposit_amount)
        update_bank_deposit(user_id, deposit_amount)
        
        new_balance = get_balance(user_id)
        new_deposit = get_bank_deposit(user_id)
        
        bot.send_message(message.chat.id,
                       f"✅ Вы положили ❄️{format_balance(deposit_amount)} на вклад под 0.5% в час\n"
                       f"❄️ На вкладе: ❄️{format_balance(new_deposit)}\n"
                       f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_deposit: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в операции. Попробуйте снова.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('снять '))
def handle_withdraw(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        if user_level < 5:
            bot.send_message(message.chat.id, "🚫 Банк доступен с 5 уровня!")
            return
            
        user_id = message.from_user.id
        bank_deposit = get_bank_deposit(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: снять 1000к")
            return
        
        withdraw_amount = parse_bet_amount(' '.join(parts[1:]), bank_deposit)
        
        if withdraw_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if withdraw_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if withdraw_amount > bank_deposit:
            bot.send_message(message.chat.id, "❌ Недостаточно средств на вкладе")
            return
        
        update_balance(user_id, withdraw_amount)
        update_bank_deposit(user_id, -withdraw_amount)
        
        new_balance = get_balance(user_id)
        new_deposit = get_bank_deposit(user_id)
        
        bot.send_message(message.chat.id,
                       f"✅ Вы сняли ❄️{format_balance(withdraw_amount)} с вклада\n"
                       f"❄️ Осталось на вкладе: ❄️{format_balance(new_deposit)}\n"
                       f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_withdraw: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в операции. Попробуйте снова.")

# ========== МАЙНИНГ ==========
@bot.message_handler(func=lambda message: message.text == "Майнинг")
def handle_mining(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        
        has_access, access_message = check_level_requirement(message.from_user.id, 10)
        if not has_access:
            bot.send_message(message.chat.id, access_message, parse_mode='Markdown')
            return
            
        user_id = message.from_user.id
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT video_cards, last_mining_collect, mining_balance, mining_trees 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
            conn.close()
            return
        
        video_cards, last_collect, mining_balance, mining_trees = result
        
        video_cards = video_cards if video_cards is not None else 0
        last_collect = last_collect if last_collect is not None else 0
        mining_balance = mining_balance if mining_balance is not None else 0
        mining_trees = mining_trees if mining_trees is not None else 0
        
        if last_collect == 0:
            current_time = int(time.time())
            cursor.execute('UPDATE users SET last_mining_collect = ? WHERE user_id = ?', 
                          (current_time, user_id))
            last_collect = current_time
            conn.commit()
        
        accumulated_trees = 0
        if video_cards > 0 and last_collect > 0:
            try:
                current_time = int(time.time())
                time_passed = current_time - last_collect
                
                if time_passed > 0:
                    income_per_hour = video_cards
                    accumulated_trees = int(income_per_hour * (time_passed / 3600))
                    
                    max_accumulation = video_cards * 24
                    if accumulated_trees > max_accumulation:
                        accumulated_trees = max_accumulation
                        
            except Exception as e:
                logging.error(f"Ошибка расчета накоплений: {e}")
                accumulated_trees = 0
        
        income_per_hour = video_cards
        
        card_price = 5000 * (video_cards + 1)
        
        message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
        message_text += f"🎮 *Видеокарт:* {video_cards}\n"
        message_text += f"💰 *Доход:* {income_per_hour} 🎄/час\n"
        message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}❄️\n\n"
        message_text += f"📦 *В хранилище:* {mining_balance}🎄\n"
        message_text += f"🌲 *Всего добыто:* {mining_trees}🎄\n"
        
        if video_cards == 0:
            message_text += "\n💡 Купите первую видеокарту чтобы начать майнить елки!"
        elif accumulated_trees > 0:
            message_text += f"📈 *Доступно для сбора:* {accumulated_trees}🎄"
            
            if accumulated_trees < (video_cards * 24):
                trees_needed = (video_cards * 24) - accumulated_trees
                hours_needed = trees_needed / video_cards if video_cards > 0 else 0
                if hours_needed > 0:
                    if hours_needed >= 1:
                        message_text += f"\n⏰ *До полного:* {hours_needed:.1f} ч."
                    else:
                        minutes = int(hours_needed * 60)
                        message_text += f"\n⏰ *До полного:* {minutes} мин."
        else:
            message_text += "⏳ Доход еще не накоплен"
        
        bot.send_message(message.chat.id, message_text, 
                       reply_markup=create_mining_keyboard(video_cards, accumulated_trees, mining_balance, card_price),
                       parse_mode='Markdown')
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка в майнинге: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка загрузки майнинга: {str(e)[:100]}")

def create_mining_keyboard(video_cards, accumulated_trees, mining_balance, card_price):
    markup = InlineKeyboardMarkup(row_width=2)
    
    if accumulated_trees > 0:
        markup.add(
            InlineKeyboardButton(f"🔄 Собрать {accumulated_trees}🎄", callback_data="mining_collect")
        )
    
    markup.add(
        InlineKeyboardButton(f"💳 Купить карту {format_balance(card_price)}❄️", callback_data="mining_buy")
    )
    
    if mining_balance > 0:
        markup.add(
            InlineKeyboardButton(f"💱 Обменять {mining_balance}🎄", callback_data="mining_exchange")
        )
    
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('mining_'))
def mining_callback_handler(call):
    user_id = call.from_user.id
    
    try:
        if call.data == "mining_collect":
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT video_cards, last_mining_collect, mining_balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ Ошибка загрузки данных!")
                conn.close()
                return
                
            video_cards, last_collect, mining_balance = result
            
            video_cards = video_cards if video_cards is not None else 0
            last_collect = last_collect if last_collect is not None else 0
            mining_balance = mining_balance if mining_balance is not None else 0
            
            if video_cards == 0:
                bot.answer_callback_query(call.id, "❌ У вас нет видеокарт для сбора!")
                conn.close()
                return
            
            current_time = int(time.time())
            if last_collect == 0:
                cursor.execute('UPDATE users SET last_mining_collect = ? WHERE user_id = ?', 
                             (current_time, user_id))
                last_collect = current_time
            
            accumulated_trees = 0
            if last_collect > 0:
                time_passed = current_time - last_collect
                
                if time_passed > 0:
                    income_per_hour = video_cards
                    accumulated_trees = int(income_per_hour * (time_passed / 3600))
                    
                    max_accumulation = video_cards * 24
                    if accumulated_trees > max_accumulation:
                        accumulated_trees = max_accumulation
            
            if accumulated_trees > 0:
                new_mining_balance = mining_balance + accumulated_trees
                
                cursor.execute('''
                    UPDATE users 
                    SET mining_balance = ?, 
                        last_mining_collect = ?,
                        mining_trees = COALESCE(mining_trees, 0) + ?
                    WHERE user_id = ?
                ''', (new_mining_balance, current_time, accumulated_trees, user_id))
                conn.commit()
                
                bot.answer_callback_query(call.id, f"✅ Собрано {accumulated_trees}🎄 в хранилище!")
                
                new_income_per_hour = video_cards
                new_card_price = 2000 * (video_cards + 1)
                
                message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
                message_text += f"🎮 *Видеокарт:* {video_cards}\n"
                message_text += f"💰 *Доход:* {new_income_per_hour} 🎄/час\n"
                message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}❄️\n\n"
                message_text += f"📦 *В хранилище:* {new_mining_balance}🎄\n"
                message_text += f"🌲 *Всего добыто:* {accumulated_trees}🎄\n"
                message_text += f"✅ *Собрано:* {accumulated_trees}🎄"
                
                try:
                    bot.edit_message_text(
                        message_text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_mining_keyboard(video_cards, 0, new_mining_balance, new_card_price),
                        parse_mode='Markdown'
                    )
                except:
                    bot.answer_callback_query(call.id, "✅ Собрано!")
            else:
                bot.answer_callback_query(call.id, "⏳ Доход еще не накоплен!")
            
            conn.close()
        
        elif call.data == "mining_buy":
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT video_cards, balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ Ошибка загрузки данных!")
                conn.close()
                return
                
            video_cards, balance = result
            video_cards = video_cards if video_cards is not None else 0
            balance = balance if balance is not None else 0
            
            card_price = 2000 * (video_cards + 1)
            
            if balance >= card_price:
                cursor.execute(
                    'UPDATE users SET video_cards = video_cards + 1, balance = balance - ? WHERE user_id = ?',
                    (card_price, user_id)
                )
                conn.commit()
                
                new_video_cards = video_cards + 1
                new_income_per_hour = new_video_cards
                new_card_price = 2000 * (new_video_cards + 1)
                
                cursor.execute('SELECT mining_balance, mining_trees FROM users WHERE user_id = ?', (user_id,))
                mining_result = cursor.fetchone()
                mining_balance = mining_result[0] if mining_result else 0
                mining_trees = mining_result[1] if mining_result else 0
                
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                new_balance_result = cursor.fetchone()
                new_balance = new_balance_result[0] if new_balance_result else 0
                
                bot.answer_callback_query(call.id, f"✅ Куплена видеокарта {new_video_cards} уровня!")
                
                message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
                message_text += f"🎮 *Видеокарт:* {new_video_cards}\n"
                message_text += f"💰 *Доход:* {new_income_per_hour} 🎄/час\n"
                message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}❄️\n\n"
                message_text += f"📦 *В хранилище:* {mining_balance}🎄\n"
                message_text += f"🌲 *Всего добыто:* {mining_trees}🎄\n"
                message_text += f"💳 *Баланс снежков:* {format_balance(new_balance)}❄️"
                
                try:
                    bot.edit_message_text(
                        message_text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_mining_keyboard(new_video_cards, 0, mining_balance, new_card_price),
                        parse_mode='Markdown'
                    )
                except:
                    bot.answer_callback_query(call.id, "✅ Куплено!")
            else:
                bot.answer_callback_query(call.id, 
                    f"❌ Недостаточно снежков! Нужно: {format_balance(card_price)}❄️",
                    show_alert=True)
            
            conn.close()
        
        elif call.data == "mining_exchange":
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT mining_balance, balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ Ошибка загрузки данных!")
                conn.close()
                return
                
            mining_balance, current_balance = result
            
            mining_balance = mining_balance if mining_balance is not None else 0
            current_balance = current_balance if current_balance is not None else 0
            
            if mining_balance <= 0:
                bot.answer_callback_query(call.id, "❌ У вас нет елок для обмена!")
                conn.close()
                return
            
            snow_amount = mining_balance * MINING_EXCHANGE_RATE
            
            cursor.execute(
                'UPDATE users SET mining_balance = 0, balance = balance + ? WHERE user_id = ?',
                (snow_amount, user_id)
            )
            conn.commit()
            
            new_balance = current_balance + snow_amount
            
            cursor.execute('SELECT video_cards, mining_trees FROM users WHERE user_id = ?', (user_id,))
            video_result = cursor.fetchone()
            video_cards = video_result[0] if video_result else 0
            mining_trees = video_result[1] if video_result else 0
            card_price = 2000 * (video_cards + 1)
            
            bot.answer_callback_query(call.id, f"✅ Обменено {mining_balance}🎄 на {format_balance(snow_amount)}❄️!")
            
            message_text = f"🖥 *Ваша майнинг ферma:*\n\n"
            message_text += f"🎮 *Видеокарт:* {video_cards}\n"
            message_text += f"💰 *Доход:* {video_cards} 🎄/час\n"
            message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}❄️\n\n"
            message_text += f"📦 *В хранилище:* 0🎄\n"
            message_text += f"🌲 *Всего добыто:* {mining_trees}🎄\n"
            message_text += f"✅ *Обменено:* {mining_balance}🎄 → {format_balance(snow_amount)}❄️\n"
            message_text += f"💳 *Баланс снежков:* {format_balance(new_balance)}❄️"
            
            try:
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_mining_keyboard(video_cards, 0, 0, card_price),
                    parse_mode='Markdown'
                )
            except:
                bot.answer_callback_query(call.id, "✅ Обменено!")
            
            conn.close()
    
    except Exception as e:
        logging.error(f"Ошибка в mining_callback_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка базы данных")

# ========== РАБОТА: ЧИСТКА СНЕГА ==========
@bot.message_handler(func=lambda message: message.text == "❄️ Чистка снега")
def handle_snow_work(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        if user_level < 3:
            bot.send_message(message.chat.id, "🚫 Работа доступна с 3 уровня!")
            return
            
        user_id = message.from_user.id
        
        current_time = time.time()
        if user_id in SNOW_COOLDOWN:
            cooldown_end = SNOW_COOLDOWN[user_id]
            if current_time < cooldown_end:
                time_left = int(cooldown_end - current_time)
                minutes = time_left // 60
                seconds = time_left % 60
                
                cool_msg = f"⏳ Отдых: {minutes}м {seconds}с"
                bot.send_message(message.chat.id, cool_msg)
                return
        
        if user_id in SNOW_JOBS:
            job = SNOW_JOBS[user_id]
            
            if user_id in SNOW_LAST_MESSAGE:
                last_msg = SNOW_LAST_MESSAGE[user_id]
                if current_time - last_msg["timestamp"] > 60:
                    del SNOW_JOBS[user_id]
                    bot.send_message(message.chat.id, "❄️ Прошлая уборка устарела\nНачните заново")
                    return
            
            progress_msg = get_snow_progress_message(job)
            markup = create_snow_keyboard(job["clicks_left"], job["current_earnings"])
            
            bot.send_message(message.chat.id, progress_msg, reply_markup=markup)
            return
        
        completed_jobs = SNOW_JOBS.get(user_id, {}).get("completed", 0) if user_id in SNOW_JOBS else 0
        
        level_bonus = 1 + (user_level * 0.01)
        base_earnings = int(1000 * level_bonus)
        bonus_per_job = int(25 * level_bonus)
        earnings = base_earnings + (completed_jobs * bonus_per_job)
        
        SNOW_JOBS[user_id] = {
            "clicks_left": 100,
            "clicks_done": 0,
            "total_earnings": earnings,
            "current_earnings": earnings,
            "completed": completed_jobs,
            "start_time": current_time,
            "wrong_clicks": 0
        }
        
        stats_msg = (
            f"❄️ *УБОРКА СНЕГА*\n\n"
            f"🎯 100 кликов\n"
            f"💰 {format_balance(earnings)}❄️\n"
            f"📈 Надбавка: +50❄️\n"
            f"❗ Штраф: -100❄️ за ошибку\n"
            f"🏆 Выполнено: {completed_jobs}\n"
            f"🎮 Бонус уровня {user_level}: +{user_level}% к заработку"
        )
        
        markup = create_snow_keyboard(100, earnings)
        msg = bot.send_message(message.chat.id, stats_msg, reply_markup=markup, parse_mode='Markdown')
        
        SNOW_LAST_MESSAGE[user_id] = {
            "chat_id": msg.chat.id,
            "message_id": msg.message_id,
            "timestamp": current_time
        }
        
    except Exception as e:
        logging.error(f"Ошибка в уборке снега: {e}")
        bot.send_message(message.chat.id, "❄️ Ошибка")

def create_snow_keyboard(clicks_left, current_earnings):
    markup = InlineKeyboardMarkup(row_width=5)
    
    snow_position = random.randint(0, 4)
    
    buttons = []
    for i in range(5):
        if i == snow_position:
            buttons.append(InlineKeyboardButton("❄️", callback_data="snow_correct"))
        else:
            trap_symbols = ["•", "○", "●", "◌"]
            trap_symbol = random.choice(trap_symbols)
            buttons.append(InlineKeyboardButton(trap_symbol, callback_data="snow_wrong"))
    
    markup.row(*buttons)
    
    markup.row(InlineKeyboardButton(f"💰 {format_balance(current_earnings)}❄️", callback_data="snow_balance"))
    
    return markup

def get_snow_progress_message(job):
    clicks_done = job["clicks_done"]
    progress_percent = (clicks_done / 100) * 100
    
    filled = int(progress_percent / 6.67)
    progress_bar = "🟦" * filled + "⬜" * (15 - filled)
    
    message = (
        f"❄️ {clicks_done}/100\n"
        f"{progress_bar}\n"
        f"💰 {format_balance(job['current_earnings'])}❄️\n"
        f"❌ Ошибок: {job['wrong_clicks']}"
    )
    
    return message

@bot.callback_query_handler(func=lambda call: call.data in ["snow_correct", "snow_wrong", "snow_balance"])
def handle_snow_click(call):
    try:
        user_id = call.from_user.id
        current_time = time.time()
        
        if user_id not in SNOW_JOBS:
            bot.answer_callback_query(call.id, "❌ Работа не найдена")
            return
        
        if user_id in SNOW_LAST_MESSAGE:
            last_msg = SNOW_LAST_MESSAGE[user_id]
            if (last_msg["chat_id"] != call.message.chat.id or 
                last_msg["message_id"] != call.message.message_id):
                bot.answer_callback_query(call.id, "❌ Сообщение устарело")
                return
        
        job = SNOW_JOBS[user_id]
        
        if call.data == "snow_balance":
            bot.answer_callback_query(call.id, f"💰 {format_balance(job['current_earnings'])}❄️")
            return
        
        elif call.data == "snow_wrong":
            penalty = 50
            if job["current_earnings"] > penalty:
                job["current_earnings"] -= penalty
            else:
                job["current_earnings"] = 0
            
            job["wrong_clicks"] += 1
            
            markup = create_snow_keyboard(job["clicks_left"], job["current_earnings"])
            progress_msg = get_snow_progress_message(job)
            
            try:
                bot.edit_message_text(
                    progress_msg,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            except:
                bot.answer_callback_query(call.id, "❌ Сообщение устарело")
                del SNOW_JOBS[user_id]
                return
            
            bot.answer_callback_query(call.id, f"💸 -100❄️")
            return
        
        job["clicks_left"] -= 1
        job["clicks_done"] += 1
        
        if user_id in SNOW_LAST_MESSAGE:
            SNOW_LAST_MESSAGE[user_id]["timestamp"] = current_time
        
        if job["clicks_left"] <= 0:
            earnings = job["current_earnings"]
            
            if earnings > 0:
                experience_gained = max(10, int(earnings * 0.02))
                update_balance(user_id, earnings, "чистка снега")
                add_experience(user_id, experience_gained)
                new_balance = get_balance(user_id)
            else:
                earnings = 0
                new_balance = get_balance(user_id)
            
            job["completed"] += 1
            
            cooldown_duration = 180
            SNOW_COOLDOWN[user_id] = time.time() + cooldown_duration
            
            completed_count = job["completed"]
            wrong_clicks = job["wrong_clicks"]
            
            del SNOW_JOBS[user_id]
            
            if earnings > 0:
                result_msg = (
                    f"✅ *УБОРКА ЗАВЕРШЕНА!*\n\n"
                    f"🎯 Кликов: 100\n"
                    f"❌ Ошибок: {wrong_clicks}\n"
                    f"💰 Заработано: {format_balance(earnings)}❄️\n"
                    f"📊 Баланс: {format_balance(new_balance)}❄️\n"
                    f"🏆 Уборок: {completed_count}\n\n"
                    f"⏳ Следующая через 3 мин"
                )
                bot.answer_callback_query(call.id, f"✅ +{format_balance(earnings)}❄️")
            else:
                result_msg = (
                    f"⚠️ *УБОРКА ЗАВЕРШЕНА*\n\n"
                    f"🎯 Кликов: 100\n"
                    f"❌ Ошибок: {wrong_clicks}\n"
                    f"💸 Все деньги потеряны!\n"
                    f"📊 Баланс: {format_balance(new_balance)}❄️\n\n"
                    f"⏳ Следующая через 3 мин"
                )
                bot.answer_callback_query(call.id, "💸 0❄️")
            
            try:
                bot.edit_message_text(
                    result_msg,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(call.message.chat.id, result_msg, parse_mode='Markdown')
            
        else:
            markup = create_snow_keyboard(job["clicks_left"], job["current_earnings"])
            progress_msg = get_snow_progress_message(job)
            
            try:
                bot.edit_message_text(
                    progress_msg,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            except:
                bot.answer_callback_query(call.id, "❌ Сообщение устарело")
                return
            
            bot.answer_callback_query(call.id, "❄️")
            
    except Exception as e:
        logging.error(f"Ошибка в клике снега: {e}")
        bot.answer_callback_query(call.id, "❌")

# ========== РАБОТА: КУРЬЕР ==========
@bot.message_handler(func=lambda message: message.text == "🚚 Курьер")
def handle_courier(message):
    user_id = message.from_user.id
    
    banned, reason = is_banned(user_id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
        return
    
    user_level = get_user_level(user_id)
    if user_level < 15:
        bot.send_message(message.chat.id, "🚫 Работа курьером доступна с 15 уровня!")
        return
    
    stats = get_courier_stats(user_id)
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    
    current_time = time.time()
    
    if stats["cooldown"] > 0 and current_time < stats["cooldown"]:
        time_left = int(stats["cooldown"] - current_time)
        minutes = time_left // 60
        seconds = time_left % 60
        
        msg = f"⏳ Отдых: {minutes}м {seconds}с"
        bot.send_message(message.chat.id, msg)
        return
    
    if user_id in COURIER_JOBS:
        show_active_job(message, user_id, stats)
    else:
        show_courier_menu(message, user_id, stats)

def get_courier_stats(user_id):
    if user_id not in COURIER_STATS:
        COURIER_STATS[user_id] = {
            "level": 1,
            "xp": 0,
            "deliveries": 0,
            "earned": 0,
            "cooldown": 0
        }
    return COURIER_STATS[user_id]

def save_courier_stats(user_id, stats):
    COURIER_STATS[user_id] = stats

def show_courier_menu(message, user_id, stats):
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    next_level = stats["level"] + 1
    next_data = COURIER_LEVELS.get(next_level)
    
    xp_percent = (stats["xp"] / level_data["xp_needed"]) * 100 if level_data["xp_needed"] > 0 else 0
    progress_bar = "🟦" * int(xp_percent / 10) + "⬜" * (10 - int(xp_percent / 10))
    
    msg = f"""
🚚 *Курьер*

• Уровень: {level_data['name']}
• Доставок: {stats['deliveries']}
• Заработано: {format_balance(stats['earned'])}❄️

{progress_bar}
{stats['xp']}/{level_data['xp_needed']} опыта

💰 За доставку: {level_data['pay']}❄️
📦 За смену: {level_data['deliveries']} посылок
"""
    
    if next_data:
        xp_needed = level_data["xp_needed"] - stats["xp"]
        msg += f"""
        
⬆️ До {next_data['name']}:
• Нужно: {xp_needed} опыта
• Доставок: +{next_data['deliveries'] - level_data['deliveries']}
• Зарплата: +{next_data['pay'] - level_data['pay']}❄️
"""
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📦 Начать смену", callback_data="courier_start"),
        InlineKeyboardButton("🔄 Обновить", callback_data="courier_refresh")
    )
    
    bot.send_message(message.chat.id, msg.strip(), reply_markup=markup, parse_mode='Markdown')

def show_active_job(message, user_id, stats):
    job = COURIER_JOBS[user_id]
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    
    deliveries_left = level_data["deliveries"] - job["done"]
    progress_percent = (job["done"] / level_data["deliveries"]) * 10
    progress_bar = "🟩" * int(progress_percent) + "⬜" * (10 - int(progress_percent))
    
    msg = f"""
🚚 *Доставка*

📍 {job['address']}
📦 {job['package']}

{progress_bar}
{job['done']}/{level_data['deliveries']} доставок

💰 +{job['pay']}❄️ за доставку
⚡ Бонус: +{job['bonus']}❄️
"""
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("✅ Доставить", callback_data="courier_deliver"),
        InlineKeyboardButton("❌ Отменить", callback_data="courier_cancel")
    )
    
    bot.send_message(message.chat.id, msg.strip(), reply_markup=markup, parse_mode='Markdown')

def create_courier_job(user_id):
    stats = get_courier_stats(user_id)
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    
    base_pay = level_data["pay"]
    bonus = random.randint(5, 15)
    
    return {
        "done": 0,
        "total": level_data["deliveries"],
        "address": random.choice(ADDRESSES),
        "package": random.choice(PACKAGES),
        "pay": base_pay,
        "bonus": bonus,
        "earnings": 0,
        "start_time": time.time()
    }

@bot.callback_query_handler(func=lambda call: call.data.startswith('courier_'))
def handle_courier_callback(call):
    user_id = call.from_user.id
    
    if call.data == "courier_start":
        stats = get_courier_stats(user_id)
        
        current_time = time.time()
        if stats["cooldown"] > 0 and current_time < stats["cooldown"]:
            bot.answer_callback_query(call.id, "⏳ Подождите немного")
            return
        
        COURIER_JOBS[user_id] = create_courier_job(user_id)
        
        show_active_job(call.message, user_id, stats)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        bot.answer_callback_query(call.id, "🚚 Смена начата!")
    
    elif call.data == "courier_refresh":
        stats = get_courier_stats(user_id)
        
        if user_id in COURIER_JOBS:
            show_active_job(call.message, user_id, stats)
        else:
            show_courier_menu(call.message, user_id, stats)
        
        bot.answer_callback_query(call.id, "🔄 Обновлено")
    
    elif call.data == "courier_deliver":
        if user_id not in COURIER_JOBS:
            bot.answer_callback_query(call.id, "❌ Нет активной смены")
            return
        
        job = COURIER_JOBS[user_id]
        stats = get_courier_stats(user_id)
        level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
        
        total_pay = job["pay"] + job["bonus"]
        
        job["done"] += 1
        job["earnings"] += total_pay
        
        stats["deliveries"] += 1
        stats["earned"] += total_pay
        stats["xp"] += 1
        
        if stats["xp"] >= level_data["xp_needed"] and stats["level"] < 5:
            stats["level"] += 1
            stats["xp"] = 0
            level_up = True
        else:
            level_up = False
        
        save_courier_stats(user_id, stats)
        
        if job["done"] >= job["total"]:
            total_earnings = job["earnings"]
            update_balance(user_id, total_earnings)
            
            current_time = time.time()
            stats["cooldown"] = current_time + level_data["cooldown"]
            save_courier_stats(user_id, stats)
            
            del COURIER_JOBS[user_id]
            
            new_balance = get_balance(user_id)
            
            msg = f"✅ *СМЕНА ЗАВЕРШЕНА!*\n\n"
            msg += f"📦 Доставок: {job['total']}/{job['total']}\n"
            msg += f"💰 Заработано: {format_balance(total_earnings)}❄️\n"
            msg += f"💳 Баланс: {format_balance(new_balance)}❄️\n\n"
            
            if level_up:
                new_level_data = COURIER_LEVELS.get(stats["level"])
                msg += f"🎉 *НОВЫЙ УРОВЕНЬ!*\n"
                msg += f"⬆️ {new_level_data['name']}\n"
            
            msg += f"⏳ Следующая через 3 минуты"
            
            try:
                bot.edit_message_text(
                    msg,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass
            
            bot.answer_callback_query(call.id, f"✅ +{format_balance(total_earnings)}❄️")
        
        else:
            job["address"] = random.choice(ADDRESSES)
            job["package"] = random.choice(PACKAGES)
            job["bonus"] = random.randint(5, 15)
            
            show_active_job(call.message, user_id, stats)
            bot.answer_callback_query(call.id, f"✅ +{total_pay}❄️")
    
    elif call.data == "courier_cancel":
        if user_id in COURIER_JOBS:
            job = COURIER_JOBS[user_id]
            stats = get_courier_stats(user_id)
            
            if job["earnings"] > 0:
                update_balance(user_id, job["earnings"])
                stats["earned"] += job["earnings"]
                stats["deliveries"] += job["done"]
                stats["xp"] += job["done"]
                save_courier_stats(user_id, stats)
            
            del COURIER_JOBS[user_id]
            
            msg = "🚫 *СМЕНА ОТМЕНЕНА*\n\n"
            
            if job["earnings"] > 0:
                msg += f"💰 Сохранено: {format_balance(job['earnings'])}❄️\n"
                msg += f"📦 Доставок: {job['done']}\n"
            else:
                msg += "💸 Ничего не заработано\n"
            
            msg += "💡 Можно начать новую смену"
            
            try:
                bot.edit_message_text(
                    msg,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass
        
        bot.answer_callback_query(call.id, "❌ Отменено")

# ========== БОНУС ==========
@bot.message_handler(func=lambda message: message.text == "Бонус")
def handle_daily_bonus(message):
    try:
        user_id = message.from_user.id
        
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        try:
            channel_member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if channel_member.status not in ['member', 'administrator', 'creator']:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                
                bot.send_message(
                    message.chat.id,
                    "🎁 *Бонус*\n\n"
                    f"❄️ *{MIN_BONUS}-{MAX_BONUS}❄️*\n"
                    f"🕐 *каждые 30 мин*\n\n"
                    f"❌ *Для бонуса подпишитесь на канал:*\n"
                    f"📢 {REQUIRED_CHANNEL}\n\n"
                    "После подписки нажмите *'🔄 Проверить'*",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
            markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
            
            bot.send_message(
                message.chat.id,
                "🎁 *Бонус*\n\n"
                f"❄️ *{MIN_BONUS}-{MAX_BONUS}❄️*\n"
                f"🕐 *каждые 30 мин*\n\n"
                f"❌ *Ошибка проверки подписки.*\n"
                f"Подпишитесь на: {REQUIRED_CHANNEL}\n\n"
                "После подписки нажмите *'🔄 Проверить'*",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            return
        
        current_time = int(time.time())
        
        if user_id in bonus_processing:
            bot.send_message(message.chat.id, "⏳ Бонус уже обрабатывается...")
            return
        
        if user_id in user_bonus_cooldown:
            last_bonus_time = user_bonus_cooldown[user_id]
            time_passed = current_time - last_bonus_time
            
            if time_passed < 2:
                time_left = 2 - time_passed
                bot.send_message(message.chat.id, f"⏳ Подождите {time_left} секунд")
                return
        
        user_bonus_cooldown[user_id] = current_time
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_bonus = result[0]
                
                if isinstance(last_bonus, str):
                    try:
                        last_bonus_time = int(float(last_bonus))
                    except:
                        try:
                            last_bonus_time = int(last_bonus)
                        except:
                            last_bonus_time = 0
                else:
                    last_bonus_time = int(last_bonus) if last_bonus else 0
                
                if last_bonus_time > 0:
                    time_passed = current_time - last_bonus_time
                    
                    if time_passed < 1800:
                        time_left = 1800 - time_passed
                        minutes = time_left // 60
                        seconds = time_left % 60
                        
                        if user_id in user_bonus_cooldown:
                            del user_bonus_cooldown[user_id]
                            
                        bot.send_message(message.chat.id, f"⏳ Бонус будет доступен через {minutes} минут {seconds} секунд")
                        conn.close()
                        return
                        
        except Exception as e:
            logging.error(f"Ошибка проверки времени бонуса: {e}")
        finally:
            if conn:
                conn.close()
        
        user_level = get_user_level(user_id)
        level_multiplier = 1 + (user_level * 0.01)
        
        min_bonus_with_level = int(MIN_BONUS * level_multiplier)
        max_bonus_with_level = int(MAX_BONUS * level_multiplier)
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"claim_bonus_{current_time}"))
        
        bonus_text = f"🎁 *Бонус*\n\n"
        bonus_text += f"❄️ *{min_bonus_with_level}-{max_bonus_with_level}❄️*\n"
        bonus_text += f"🕐 *каждые 30 мин*\n"
        bonus_text += f"🎮 *Бонус уровня {user_level}: +{user_level}%*"
        
        bot.send_message(message.chat.id, bonus_text, parse_mode='Markdown', reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в бонусе: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_bonus_"))
def handle_claim_bonus(call):
    conn = None
    try:
        user_id = call.from_user.id
        current_time = int(time.time())
        
        callback_parts = call.data.split('_')
        if len(callback_parts) != 3:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
            
        callback_timestamp = int(callback_parts[2])
        
        if current_time - callback_timestamp > 60:
            bot.answer_callback_query(call.id, "❌ Время истекло, обновите страницу")
            return
        
        if user_id in bonus_processing:
            bot.answer_callback_query(call.id, "⏳ Уже получаете бонус...")
            return
        
        bonus_processing.add(user_id)
        
        try:
            try:
                channel_member = bot.get_chat_member("@FECTIZ", user_id)
                if channel_member.status not in ['member', 'administrator', 'creator']:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                    markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                    
                    bot.edit_message_text(
                        "❌ *Подписка не найдена!*\n"
                        f"📢 {REQUIRED_CHANNEL}",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
                    bot.answer_callback_query(call.id, "❌ Проверьте подписку")
                    return
            except:
                bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки")
                return
            
            user_level = get_user_level(user_id)
            level_multiplier = 1 + (user_level * 0.01)
            
            min_bonus_with_level = int(MIN_BONUS * level_multiplier)
            max_bonus_with_level = int(MAX_BONUS * level_multiplier)
            
            bonus_amount = random.randint(min_bonus_with_level, max_bonus_with_level)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('BEGIN IMMEDIATE TRANSACTION')
            
            cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_bonus = result[0]
                
                if isinstance(last_bonus, str):
                    try:
                        last_bonus_time = int(float(last_bonus))
                    except:
                        try:
                            last_bonus_time = int(last_bonus)
                        except:
                            last_bonus_time = 0
                else:
                    last_bonus_time = int(last_bonus) if last_bonus else 0
                
                if last_bonus_time > 0:
                    time_passed = current_time - last_bonus_time
                    
                    if time_passed < 1700:
                        cursor.execute('ROLLBACK')
                        conn.close()
                        
                        time_left = 1800 - time_passed
                        minutes = time_left // 60
                        seconds = time_left % 60
                        bot.answer_callback_query(call.id, f"⏳ Ждите {minutes}:{seconds:02d}")
                        return
            
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (bonus_amount, user_id))
            cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, user_id))
            
            experience_gained = max(1, int(bonus_amount * 0.02))
            cursor.execute('UPDATE users SET experience = experience + ?, total_earned = total_earned + ? WHERE user_id = ?',
                          (experience_gained, bonus_amount, user_id))
            
            cursor.execute('COMMIT')
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            balance_result = cursor.fetchone()
            new_balance = balance_result[0] if balance_result else bonus_amount
            
            result_text = f"*✅ Бонус получен*\n\n"
            result_text += f"> *+{bonus_amount}❄️*\n\n"
            result_text += f"*💸 Баланс: {format_balance(new_balance)}❄️*\n"
            result_text += f"*🎮 Бонус уровня {user_level}: +{user_level}%*"
            
            bot.edit_message_text(
                result_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
            
            bot.answer_callback_query(call.id, "✅")
            
            user_bonus_cooldown[user_id] = current_time
            
            logging.info(f"Пользователь {user_id} получил бонус {bonus_amount}❄️ баланс: {new_balance}❄️")
            
            add_experience(user_id, experience_gained, "бонус")
            
        except Exception as e:
            try:
                if conn:
                    cursor.execute('ROLLBACK')
            except:
                pass
            logging.error(f"Ошибка получения бонуса: {e}")
            
            try:
                if conn:
                    conn.close()
                
                simple_conn = get_db_connection()
                simple_cursor = simple_conn.cursor()
                
                simple_cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
                simple_result = simple_cursor.fetchone()
                
                if simple_result and simple_result[0]:
                    last_bonus = simple_result[0]
                    
                    if isinstance(last_bonus, str):
                        try:
                            last_bonus_time = int(float(last_bonus))
                        except:
                            try:
                                last_bonus_time = int(last_bonus)
                            except:
                                last_bonus_time = 0
                    else:
                        last_bonus_time = int(last_bonus) if last_bonus else 0
                    
                    if last_bonus_time > 0:
                        time_passed = current_time - last_bonus_time
                        
                        if time_passed < 1700:
                            time_left = 1800 - time_passed
                            minutes = time_left // 60
                            seconds = time_left % 60
                            bot.answer_callback_query(call.id, f"⏳ Ждите {minutes}:{seconds:02d}")
                            return
                
                user_level = get_user_level(user_id)
                level_multiplier = 1 + (user_level * 0.01)
                min_bonus_with_level = int(MIN_BONUS * level_multiplier)
                max_bonus_with_level = int(MAX_BONUS * level_multiplier)
                bonus_amount = random.randint(min_bonus_with_level, max_bonus_with_level)
                
                simple_cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (bonus_amount, user_id))
                simple_cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, user_id))
                
                experience_gained = max(1, int(bonus_amount * 0.02))
                simple_cursor.execute('UPDATE users SET experience = experience + ?, total_earned = total_earned + ? WHERE user_id = ?',
                                     (experience_gained, bonus_amount, user_id))
                
                simple_conn.commit()
                
                simple_cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                balance_result = simple_cursor.fetchone()
                new_balance = balance_result[0] if balance_result else bonus_amount
                
                result_text = f"*✅ Бонус получен*\n\n"
                result_text += f"> *+{bonus_amount}❄️*\n\n"
                result_text += f"*💸 Баланс: {format_balance(new_balance)}❄️*\n"
                result_text += f"*🎮 Бонус уровня {user_level}: +{user_level}%*"
                
                bot.edit_message_text(
                    result_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✅")
                logging.info(f"Пользователь {user_id} получил бонус {bonus_amount}❄️ (альтернативный метод) баланс: {new_balance}❄️")
                
                simple_conn.close()
                
                add_experience(user_id, experience_gained, "бонус")
                
            except Exception as e2:
                logging.error(f"Ошибка альтернативного метода: {e2}")
                bot.answer_callback_query(call.id, "❌ Ошибка получения")
                
        finally:
            if user_id in bonus_processing:
                bonus_processing.remove(user_id)
            if conn:
                conn.close()
                
    except Exception as e:
        logging.error(f"Критическая ошибка в бонусе: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")
        
        if user_id in bonus_processing:
            bonus_processing.remove(user_id)

# ========== ОБРАБОТКА КАПЧИ ==========
@bot.message_handler(func=lambda message: True)
def handle_captcha_answer(message):
    try:
        user_id = message.from_user.id
        
        if user_id in user_captcha_status:
            user_answer = message.text.strip()
            correct_answer = user_captcha_status[user_id]
            
            if user_answer == correct_answer:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET captcha_passed = 1 WHERE user_id = ?', (user_id,))
                conn.commit()
                conn.close()
                
                del user_captcha_status[user_id]
                
                bot.send_message(message.chat.id, "✅ Капча пройдена! Доступ к боту открыт.")
                
                start(message)
            else:
                bot.send_message(message.chat.id, "❌ Неверный ответ. Попробуйте снова.")
                captcha_question, correct_answer = generate_captcha()
                user_captcha_status[user_id] = correct_answer
                bot.send_message(message.chat.id, f"🔒 Решите пример:\n\n{captcha_question}")
    
    except Exception as e:
        logging.error(f"Ошибка обработки капчи: {e}")

# ========== ТОПЫ ==========
@bot.message_handler(func=lambda message: message.text == "Топ снежков")
def handle_top_menu(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        user_id = message.from_user.id
        
        user_top_mode[user_id] = 'balance'
        title = "🎅 Топ снежков 🎅"
        
        user_top_page[user_id] = 1
        
        top_message = create_top_message(user_id, 1)
        
        markup = create_top_keyboard(user_id, 1)
        
        bot.send_message(message.chat.id, top_message, reply_markup=markup, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_top_menu: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки топа. Попробуйте снова.")

def create_top_message(user_id, page=1):
    try:
        mode = user_top_mode.get(user_id, 'balance')
        
        if mode == 'balance':
            top_data = get_balance_top_page(page, 5)
            title = "🎅 Топ снежков 🎅"
        else:
            top_data = get_scam_top_page(page, 5)
            title = "👥 Топ скама 👥"
        
        top_users = top_data['users']
        
        message_text = f"<b>{title}</b>\n\n"
        
        if top_users:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            
            for i, user in enumerate(top_users):
                if mode == 'balance':
                    user_id_db, display_name, value, position = user
                    value_text = f"⟨{format_balance(value)}❄️⟩"
                else:
                    user_id_db, nickname, username_db, first_name, value, position = user
                    value_text = f"⟨{value} скам⟩"
                    username = username_db
                
                user_prestige_id = get_user_id_number(user_id_db)
                
                if user_prestige_id > 0:
                    if user_prestige_id <= 10:
                        id_display = f"👑#{user_prestige_id}"
                    elif user_prestige_id <= 50:
                        id_display = f"⭐#{user_prestige_id}"
                    elif user_prestige_id <= 100:
                        id_display = f"✨#{user_prestige_id}"
                    elif user_prestige_id <= 500:
                        id_display = f"🔹#{user_prestige_id}"
                    else:
                        id_display = f"#{user_prestige_id}"
                else:
                    id_display = "?#"
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT nickname, username FROM users WHERE user_id = ?', (user_id_db,))
                user_data = cursor.fetchone()
                conn.close()
                
                display_html = ""
                if user_data:
                    nickname_db, username = user_data
                    if nickname_db and nickname_db.strip():
                        if username:
                            display_html = f'<a href="https://t.me/{username}">{nickname_db.strip()}</a>'
                        else:
                            display_html = nickname_db.strip()
                    elif username:
                        display_html = f'<a href="https://t.me/{username}">@{username}</a>'
                    else:
                        display_html = first_name if 'first_name' in locals() else f"ID: {user_id_db}"
                else:
                    display_html = display_name if mode == 'balance' else first_name
                
                if len(display_html) > 20:
                    import re
                    text_only = re.sub(r'<[^>]+>', '', display_html)
                    if len(text_only) > 18:
                        display_html = display_html[:15] + "..."
                
                page_position = ((page - 1) * 5) + i + 1
                if page_position <= 3:
                    medal = medals[page_position-1]
                elif page_position <= 5:
                    medal = medals[page_position-1]
                else:
                    medal = f"{page_position}."
                
                message_text += f"{medal} {id_display} {display_html} {value_text}\n"
        
        user_prestige_id = get_user_id_number(user_id)
        if user_prestige_id > 0:
            message_text += f"\n🎯 <b>Твой ID:</b> #{user_prestige_id}"
        
        return message_text
        
    except Exception as e:
        return "❌ Ошибка загрузки топа"

def get_balance_top_page(page=1, limit=5):
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT 
        user_id,
        CASE 
            WHEN username IS NOT NULL AND username != '' THEN '@' || username 
            ELSE first_name 
        END as display_name,
        balance,
        ROW_NUMBER() OVER (ORDER BY balance DESC) as position
    FROM users 
    WHERE balance > 0 AND is_banned = 0
    LIMIT ? OFFSET ?
    ''', (limit, offset))
    
    top_users = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE balance > 0 AND is_banned = 0')
    total_users = cursor.fetchone()[0]
    
    total_pages = (total_users + limit - 1) // limit
    
    conn.close()
    
    return {
        'users': top_users,
        'total': total_users,
        'current_page': page,
        'total_pages': total_pages
    }

def get_scam_top_page(page=1, limit=5):
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    has_nickname = 'nickname' in columns
    
    if has_nickname:
        cursor.execute('''
        SELECT 
            u.user_id,
            u.nickname,
            u.username,
            u.first_name,
            COUNT(r.user_id) as ref_count,
            ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
        WHERE u.is_banned = 0
        GROUP BY u.user_id
        HAVING COUNT(r.user_id) > 0
        ORDER BY ref_count DESC
        LIMIT ? OFFSET ?
        ''', (limit, offset))
    else:
        cursor.execute('''
        SELECT 
            u.user_id,
            NULL as nickname,
            u.username,
            u.first_name,
            COUNT(r.user_id) as ref_count,
            ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
        WHERE u.is_banned = 0
        GROUP BY u.user_id
        HAVING COUNT(r.user_id) > 0
        ORDER BY ref_count DESC
        LIMIT ? OFFSET ?
        ''', (limit, offset))
    
    top_scammers = cursor.fetchall()
    
    cursor.execute('''
    SELECT COUNT(DISTINCT u.user_id) 
    FROM users u
    JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
    ''')
    total_scammers = cursor.fetchone()[0] or 1
    
    total_pages = (total_scammers + limit - 1) // limit
    
    conn.close()
    
    return {
        'users': top_scammers,
        'total': total_scammers,
        'current_page': page,
        'total_pages': total_pages,
        'has_nickname': has_nickname
    }

def create_top_keyboard(user_id, current_page):
    markup = InlineKeyboardMarkup(row_width=3)
    
    mode = user_top_mode.get(user_id, 'balance')
    
    if mode == 'balance':
        top_data = get_balance_top_page(current_page, 5)
    else:
        top_data = get_scam_top_page(current_page, 5)
    
    total_pages = top_data['total_pages']
    
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"top_page_{current_page-1}"))
    
    page_button_text = f"{current_page}/{total_pages}"
    if total_pages > 1:
        page_button_text = f"📄 {current_page}/{total_pages}"
    buttons.append(InlineKeyboardButton(page_button_text, callback_data="top_current"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"top_page_{current_page+1}"))
    
    if buttons:
        markup.row(*buttons)
    
    mode_buttons = []
    if mode == 'balance':
        mode_buttons.append(InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"))
        mode_buttons.append(InlineKeyboardButton("👥 Скам", callback_data="top_mode_scam"))
    else:
        mode_buttons.append(InlineKeyboardButton("👥 Скам", callback_data="top_mode_scam"))
        mode_buttons.append(InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"))
    
    markup.row(*mode_buttons)
    
    markup.row(InlineKeyboardButton("🔄 Обновить", callback_data="top_refresh"))
    
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('top_'))
def top_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data.startswith('top_page_'):
            page = int(call.data.split('_')[2])
            
            user_top_page[user_id] = page
            
            top_message = create_top_message(user_id, page)
            markup = create_top_keyboard(user_id, page)
            
            bot.edit_message_text(
                top_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id)
            
        elif call.data.startswith('top_mode_'):
            mode = call.data.split('_')[2]
            
            user_top_mode[user_id] = mode
            user_top_page[user_id] = 1
            
            top_message = create_top_message(user_id, 1)
            markup = create_top_keyboard(user_id, 1)
            
            bot.edit_message_text(
                top_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id, f"✅ Переключено на {'снежки' if mode == 'balance' else 'скам'}")
            
        elif call.data == 'top_refresh':
            page = user_top_page.get(user_id, 1)
            top_message = create_top_message(user_id, page)
            markup = create_top_keyboard(user_id, page)
            
            bot.edit_message_text(
                top_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id, "✅ Топ обновлен!")
            
        elif call.data == 'top_current':
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        logging.error(f"Ошибка в top_callback_handler: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка обновления топа")
        except:
            pass

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_user_id_number(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT user_id FROM users 
        WHERE is_banned = 0 
        ORDER BY registered_at ASC
        ''')
        
        all_users = cursor.fetchall()
        conn.close()
        
        for i, (db_user_id,) in enumerate(all_users, 1):
            if db_user_id == user_id:
                return i
        
        return 0
    except:
        return 0

def get_prestige_id(user_id):
    try:
        id_number = get_user_id_number(user_id)
        
        if id_number == 0:
            return "ID: ?"
        
        if id_number <= 10:
            return f"👑 ID: #{id_number}"
        elif id_number <= 50:
            return f"⭐ ID: #{id_number}"
        elif id_number <= 100:
            return f"✨ ID: #{id_number}"
        elif id_number <= 500:
            return f"🔹 ID: #{id_number}"
        else:
            return f"ID: #{id_number}"
    except:
        return "ID: ?"

# ========== ИГРЫ (обработчики) ==========
def format_game_result(user_id, username, first_name, is_win, amount, game_name=None):
    try:
        if username:
            display_name = f"@{username}"
        else:
            display_name = first_name
        
        balance = get_balance(user_id)
        
        formatted_amount = format_balance(abs(amount))
        
        if is_win:
            result_text = f"🎉 {display_name} выиграл {formatted_amount}❄️️!"
            balance_text = f"💰 Баланс: {format_balance(balance)}❄️"
        else:
            result_text = f"😢 {display_name} проиграл {formatted_amount}❄️!"
            balance_text = f"💰 Баланс: {format_balance(balance)}❄️"
        
        full_message = f"<blockquote>{result_text}\n<b>{balance_text}</b></blockquote>"
        
        return full_message
    except Exception as e:
        logging.error(f"Ошибка форматирования результата игры: {e}")
        return f"❌ Ошибка"

def update_game_with_bonus(user_id, win_amount, game_name):
    try:
        if win_amount > 0:
            update_balance(user_id, win_amount, game_name)
            add_referral_win_bonus(user_id, win_amount, game_name)
    except:
        pass

def add_referral_win_bonus(user_id, win_amount, game_name):
    try:
        if win_amount < 1:
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            conn.close()
            return
        
        referrer_id = result[0]
        
        cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (referrer_id,))
        referrer_data = cursor.fetchone()
        
        if not referrer_data or referrer_data[0] == 1:
            conn.close()
            return
        
        bonus_amount = int(win_amount * 0.01)
        if bonus_amount < 1:
            bonus_amount = 1
        
        cursor.execute('''
        INSERT INTO referral_wins (referrer_id, referee_id, win_amount, bonus_amount, game_name)
        VALUES (?, ?, ?, ?, ?)
        ''', (referrer_id, user_id, win_amount, bonus_amount, game_name))
        
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                     (bonus_amount, referrer_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка бонуса от выигрыша: {e}")

# Рулетка (остальные игры аналогично, но из-за ограничения длины покажу только рулетку)
@bot.message_handler(func=lambda message: message.text.lower().startswith(('рул ', 'рулетка ')))
def handle_roulette(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        user_level = get_user_level(message.from_user.id)
        if user_level < 1:
            bot.send_message(message.chat.id, "🚫 Игры доступны с 1 уровня!")
            return
            
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        winning_number = random.randint(0, 36)
        win = False
        multiplier = 1
        
        red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        
        try:
            number_bet = int(bet_type)
            if 0 <= number_bet <= 36:
                win = winning_number == number_bet
                multiplier = 36
            else:
                bot.send_message(message.chat.id, "❌ Число 0-36")
                update_balance(user_id, bet_amount)
                return
        except ValueError:
            if bet_type in ['красный', 'крас', 'кр', 'к']:
                win = winning_number in red_numbers
                multiplier = 2
            elif bet_type in ['черный', 'чер', 'чр', 'ч']:
                win = winning_number in black_numbers
                multiplier = 2
            elif bet_type in ['зеленый', 'зел', 'з', '0', 'зеро']:
                win = winning_number == 0
                multiplier = 36
            elif bet_type in ['большие', 'бол', 'б']:
                win = winning_number >= 19 and winning_number <= 36
                multiplier = 2
            elif bet_type in ['малые', 'мал', 'м']:
                win = winning_number >= 1 and winning_number <= 18
                multiplier = 2
            elif bet_type in ['чет', 'четные', 'четн']:
                win = winning_number % 2 == 0 and winning_number != 0
                multiplier = 2
            elif bet_type in ['нечет', 'нечетные', 'неч']:
                win = winning_number % 2 == 1 and winning_number != 0
                multiplier = 2
            else:
                bot.send_message(message.chat.id, "❌ Неверный тип")
                update_balance(user_id, bet_amount)
                return
        
        if win:
            win_amount = bet_amount * multiplier
            update_game_with_bonus(user_id, win_amount, "🎰 Рулетка")
            
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            
            image_path = get_roulette_photo(winning_number)
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=result_message,
                            parse_mode='HTML'
                        )
                except:
                    bot.send_message(message.chat.id, result_message, parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        else:
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            
            image_path = get_roulette_photo(winning_number)
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=result_message,
                            parse_mode='HTML'
                        )
                except:
                    bot.send_message(message.chat.id, result_message, parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

def get_roulette_photo(winning_number):
    try:
        filename = f"{winning_number}.png"
        filepath = f"/app/{filename}"
        
        if os.path.exists(filepath):
            return filepath
        
        current_dir = os.getcwd()
        for ext in ['.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']:
            filename = f"{winning_number}{ext}"
            filepath = os.path.join(current_dir, filename)
            if os.path.exists(filepath):
                return filepath
        
        return None
        
    except Exception as e:
        logging.error(f"Ошибка поиска изображения рулетки: {e}")
        return None

# ========== ОБРАБОТКА РЕФЕРАЛОВ И ЧЕКОВ ==========
def process_ref_or_check(user_id, username, first_name, ref_code):
    """Обработка реферальной ссылки или чека"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT activated_at FROM check_activations 
            WHERE user_id = ? 
            ORDER BY activated_at DESC 
            LIMIT 1
        ''', (user_id,))
        
        last_activation = cursor.fetchone()
        
        if last_activation and last_activation[0]:
            last_time = datetime.strptime(last_activation[0], '%Y-%m-%d %H:%M:%S')
            current_time = datetime.now()
            time_diff = current_time - last_time
            
            if time_diff.total_seconds() < 1800:
                time_left = 1800 - int(time_diff.total_seconds())
                minutes = time_left // 60
                seconds = time_left % 60
                
                bot.send_message(user_id,
                    f"⏳ Вы недавно активировали чек.\n"
                    f"Перезарядка:\n"
                    f"**{minutes} минут {seconds} секунд**\n\n"
                    f"💡 Можно активировать только 1 чек в 30 минут",
                    parse_mode='Markdown'
                )
                conn.close()
                return
        
        cursor.execute(
            'SELECT amount, max_activations, current_activations FROM checks WHERE code = ?',
            (ref_code,)
        )
        check_data = cursor.fetchone()
        
        if check_data:
            amount, max_activations, current_activations = check_data
            
            cursor.execute(
                'SELECT * FROM check_activations WHERE user_id = ? AND check_code = ?',
                (user_id, ref_code)
            )
            already_activated = cursor.fetchone()
            
            if already_activated:
                bot.send_message(user_id, "❌ Вы уже активировали этот чек!")
                conn.close()
                return
            
            if current_activations >= max_activations:
                bot.send_message(user_id, "❌ Чек уже использован максимальное количество раз!")
                conn.close()
                return
            
            cursor.execute(
                'UPDATE checks SET current_activations = current_activations + 1 WHERE code = ?',
                (ref_code,)
            )
            
            cursor.execute(
                'INSERT INTO check_activations (user_id, check_code, activated_at) VALUES (?, ?, datetime("now"))',
                (user_id, ref_code)
            )
            
            update_balance(user_id, amount, "чек")
            
            conn.commit()
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance = cursor.fetchone()[0]
            
            bot.send_message(user_id,
                f"🎉 *Чек активирован!*\n\n"
                f"💰 +{format_balance(amount)}❄️\n"
                f"💳 Баланс: {format_balance(new_balance)}❄️\n\n"
                f"⏰ Следующий чек можно активировать через 30 минут",
                parse_mode='Markdown'
            )
            
            logging.info(f"Пользователь {user_id} активировал чек {ref_code} на сумму {amount}❄️")
            
            if current_activations + 1 >= max_activations:
                cursor.execute('DELETE FROM checks WHERE code = ?', (ref_code,))
                conn.commit()
                logging.info(f"Чек {ref_code} полностью использован и удален")
            
            conn.close()
            return
        
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                
                cursor.execute('SELECT user_id FROM users WHERE user_id = ? AND is_banned = 0', (referrer_id,))
                referrer_data = cursor.fetchone()
                
                if referrer_data:
                    if referrer_id == user_id:
                        bot.send_message(user_id, "❌ Нельзя использовать свою реферальную ссылку!")
                        conn.close()
                        return
                    
                    cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,))
                    existing_referrer = cursor.fetchone()
                    
                    if existing_referrer and existing_referrer[0]:
                        bot.send_message(user_id, "❌ У вас уже есть реферер!")
                        conn.close()
                        return
                    
                    cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer_id, user_id))
                    
                    REFERRAL_BONUS = 888
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (REFERRAL_BONUS, referrer_id))
                    
                    conn.commit()
                    
                    try:
                        bot.send_message(
                            referrer_id,
                            f"🎉 Новый реферал!\n"
                            f"👤 @{username if username else first_name}\n"
                            f"💰 +{REFERRAL_BONUS}❄️\n\n"
                            f"Теперь у вас {get_referral_count(referrer_id)} рефералов!"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка уведомления реферера: {e}")
                    
                    bot.send_message(user_id, f"✅ Вы зарегистрировались по приглашению!")
                    
                    logging.info(f"Пользователь {user_id} зарегистрирован по реферальной ссылке от {referrer_id}")
                    
                else:
                    bot.send_message(user_id, "❌ Реферальная ссылка недействительна!")
                
            except ValueError:
                bot.send_message(user_id, "❌ Неверный формат реферальной ссылки!")
        else:
            bot.send_message(user_id, "❌ Неизвестный код!")
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка обработки реф/чека: {e}")
        try:
            conn.close()
        except:
            pass

def get_referral_count(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

# ========== АДМИН КОМАНДЫ ==========
@bot.message_handler(func=lambda message: message.text.lower().startswith('выдать ') and is_admin(message.from_user.id))
def handle_give_money(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: выдать @username 1000к")
            return
        
        target = parts[1]
        amount = parse_bet_amount(' '.join(parts[2:]), float('inf'))
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        if target.startswith('@'):
            cursor.execute('UPDATE users SET balance = balance + ? WHERE username = ?', (amount, target[1:]))
        else:
            try:
                target_id = int(target)
                cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, target_id))
            except:
                bot.send_message(message.chat.id, "❌ Неверный ID пользователя")
                conn.close()
                return
        
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Выдано ❄️{format_balance(amount)} пользователю {target}")
    
    except Exception as e:
        print(f"Ошибка в handle_give_money: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при выдаче денег")

@bot.message_handler(func=lambda message: message.text.lower().startswith('бан ') and is_admin(message.from_user.id))
def handle_ban_username(message):
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: бан @username [причина]\n"
                           "       или: бан ID [причина]\n\n"
                           "Примеры:\n"
                           "• бан @ivan Нарушение правил\n"
                           "• бан 123456789 Спам\n"
                           "• бан @user (ответом на сообщение)")
            return
        
        target = parts[1].strip()
        ban_reason = "Нарушение правил"
        if len(parts) > 2:
            ban_reason = ' '.join(parts[2:])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if message.reply_to_message:
            target_user_id = message.reply_to_message.from_user.id
            target_username = message.reply_to_message.from_user.username
            target_first_name = message.reply_to_message.from_user.first_name
            
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (target_user_id,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_username, target_first_name = user_data
            
            target_name = f"@{target_username}" if target_username else target_first_name
            
            cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                          (ban_reason, target_user_id))
            conn.commit()
            
            bot.send_message(message.chat.id, 
                           f"✅ Пользователь {target_name} забанен!\n"
                           f"📝 Причина: {ban_reason}")
            
            try:
                bot.send_message(target_user_id, 
                               f"🚫 Вы забанены в боте!\n"
                               f"📝 Причина: {ban_reason}\n"
                               f"⏰ Время бана: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                               f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
            except:
                pass
        
        elif target.startswith('@'):
            username = target[1:]
            
            cursor.execute('SELECT user_id, first_name FROM users WHERE username = ?', (username,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_user_id, target_first_name = user_data
                
                cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                              (ban_reason, target_user_id))
                conn.commit()
                
                bot.send_message(message.chat.id, 
                               f"✅ Пользователь @{username} забанен!\n"
                               f"📝 Причина: {ban_reason}")
                
                try:
                    bot.send_message(target_user_id, 
                                   f"🚫 Вы забанены в боте!\n"
                                   f"📝 Причина: {ban_reason}\n"
                                   f"⏰ Время бана: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                   f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
                except:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь @{username} не найден в базе данных")
        
        else:
            try:
                target_user_id = int(target)
                
                cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (target_user_id,))
                user_data = cursor.fetchone()
                
                if user_data:
                    target_username, target_first_name = user_data
                    target_name = f"@{target_username}" if target_username else target_first_name
                    
                    cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                                  (ban_reason, target_user_id))
                    conn.commit()
                    
                    bot.send_message(message.chat.id, 
                                   f"✅ Пользователь {target_name} (ID: {target_user_id}) забанен!\n"
                                   f"📝 Причина: {ban_reason}")
                    
                    try:
                        bot.send_message(target_user_id, 
                                       f"🚫 Вы забанены в боте!\n"
                                       f"📝 Причина: {ban_reason}\n"
                                       f"⏰ Время бана: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                       f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
                    except:
                        pass
                else:
                    bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден в базе данных")
                    
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте @username или ID")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_ban_username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при бане пользователя: {str(e)[:100]}")

# ========== ОБРАБОТКА КНОПКИ "НАЗАД" ==========
@bot.message_handler(func=lambda message: message.text == "◀️ Назад")
def handle_back(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        user_id = message.from_user.id
        user_level = get_user_level(user_id)
        
        markup = create_main_menu(message.chat.id, user_level)
        
        if message.chat.id > 0:
            welcome_text = "✨ Главное меню ✨\n\nВыберите действие:"
        else:
            welcome_text = f"👋 Главное меню!\n\nИспользуйте меню ниже для работы с ботом."
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_back: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# ========== ОЧИСТКА ДАННЫХ ==========
def cleanup_bonus_cooldowns():
    while True:
        time.sleep(60)
        current_time = time.time()
        
        to_remove = []
        for user_id, timestamp in user_bonus_cooldown.items():
            if current_time - timestamp > 10:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del user_bonus_cooldown[user_id]
        
        bonus_processing.clear()

def cleanup_courier_data():
    while True:
        time.sleep(300)
        current_time = time.time()
        
        jobs_to_remove = []
        for user_id, job in COURIER_JOBS.items():
            if current_time - job.get("start_time", current_time) > 1800:
                jobs_to_remove.append(user_id)
        
        for user_id in jobs_to_remove:
            if user_id in COURIER_JOBS:
                job = COURIER_JOBS[user_id]
                stats = get_courier_stats(user_id)
                
                if job["earnings"] > 0:
                    update_balance(user_id, job["earnings"])
                    stats["earned"] += job["earnings"]
                    stats["deliveries"] += job["done"]
                    stats["xp"] += job["done"]
                    save_courier_stats(user_id, stats)
                
                del COURIER_JOBS[user_id]

def cleanup_snow_data():
    while True:
        time.sleep(60)
        current_time = time.time()
        
        snow_to_remove = []
        for user_id, job in SNOW_JOBS.items():
            if current_time - job.get("start_time", current_time) > 1800:
                snow_to_remove.append(user_id)
        
        for user_id in snow_to_remove:
            del SNOW_JOBS[user_id]
            if user_id in SNOW_LAST_MESSAGE:
                del SNOW_LAST_MESSAGE[user_id]
        
        msg_to_remove = []
        for user_id, msg_data in SNOW_LAST_MESSAGE.items():
            if current_time - msg_data.get("timestamp", current_time) > 3600:
                msg_to_remove.append(user_id)
        
        for user_id in msg_to_remove:
            del SNOW_LAST_MESSAGE[user_id]
        
        cooldown_to_remove = []
        for user_id, cooldown_end in SNOW_COOLDOWN.items():
            if current_time > cooldown_end + 14400:
                cooldown_to_remove.append(user_id)
        
        for user_id in cooldown_to_remove:
            del SNOW_COOLDOWN[user_id]

# ========== ЗАПУСК БОТА ==========
if __name__ == "__main__":
    init_db()
    
    # Загрузка магазина домов
    def load_house_shop():
        try:
            if os.path.exists('house_shop.json'):
                with open('house_shop.json', 'r', encoding='utf-8') as f:
                    HOUSE_SHOP.update(json.load(f))
                logging.info(f"Загружен магазин домов: {len(HOUSE_SHOP)} домов")
        except Exception as e:
            logging.error(f"Ошибка загрузки магазина: {e}")
            HOUSE_SHOP.clear()
    
    load_house_shop()
    
    # Запуск потоков очистки
    cleanup_thread = threading.Thread(target=cleanup_bonus_cooldowns, daemon=True)
    cleanup_thread.start()
    
    courier_cleanup_thread = threading.Thread(target=cleanup_courier_data, daemon=True)
    courier_cleanup_thread.start()
    
    snow_cleanup_thread = threading.Thread(target=cleanup_snow_data, daemon=True)
    snow_cleanup_thread.start()
    
    print("Бот запущен!")
    bot.polling(none_stop=True)