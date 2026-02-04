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

user_last_action = {}
user_captcha_status = {}

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
            mining_trees INTEGER DEFAULT 0
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
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_registered_at ON users(registered_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_checks_code ON checks(code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_checks_created_by ON checks(created_by)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_houses_user ON user_houses(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_houses_current ON user_houses(is_current)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_wins_referrer ON referral_wins(referrer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_wins_created ON referral_wins(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_creator ON contests(creator_id)')
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        required_columns = [
            ('nickname', 'TEXT'),
            ('mining_trees', 'INTEGER DEFAULT 0'),
            ('last_snow_work', 'TIMESTAMP'),
            ('snow_cooldown_end', 'TIMESTAMP'),
            ('current_snow_job', 'TEXT'),
            ('snow_job_progress', 'INTEGER DEFAULT 0'),
            ('snow_job_total', 'INTEGER DEFAULT 0'),
            ('snow_job_end_time', 'TIMESTAMP'),
            ('snow_territory', 'TEXT'),
            ('last_bonus', 'INTEGER DEFAULT 0')
        ]
        
        for column_name, column_type in required_columns:
            if column_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                    logging.info(f"Добавлена колонка {column_name}")
                except sqlite3.Error as e:
                    logging.error(f"Ошибка добавления колонки {column_name}: {e}")
        
        conn.commit()
        logging.info("База данных успешно инициализирована")
        
        cursor.execute('PRAGMA integrity_check')
        integrity = cursor.fetchone()[0]
        if integrity == 'ok':
            logging.info("Проверка целостности БД: OK")
        else:
            logging.warning(f"Проблемы с целостностью БД: {integrity}")
            
    except sqlite3.Error as e:
        logging.error(f"Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()

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

def is_captcha_passed(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False

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

def format_balance(balance):
    return f"{balance:,}".replace(",", " ")

def get_or_create_user(user_id, username, first_name):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        referral_code = f"ref{user_id}"
        
        cursor.execute(
            'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp())
        )
        conn.commit()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_balance(user_id, amount):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ?, last_activity = CURRENT_TIMESTAMP WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()
    return True

def is_private_chat(chat_id):
    return chat_id > 0

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
                    logging.info(f"Пользователю {user_id} начислены проценты: {interest}❄️")
                except Exception as e:
                    logging.error(f"Ошибка отправки уведомления о процентах для {user_id}: {e}")
    
    conn.close()

def get_balance(user_id):
    calculate_interest(user_id)
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

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

def get_click_streak(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT click_streak FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_click_streak(user_id, amount):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET click_streak = click_streak + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()
    return True

def create_clicker_keyboard():
    symbols = ["❌", "❌", "❌", "❌", "✅"]
    random.shuffle(symbols)
    
    markup = InlineKeyboardMarkup()
    row = []
    for i, symbol in enumerate(symbols):
        row.append(InlineKeyboardButton(symbol, callback_data=f"clicker_{symbol}"))
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    return markup

def create_main_menu(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if chat_id > 0:
        markup.add(
            KeyboardButton("Я"),
            KeyboardButton("Майнинг"),
            KeyboardButton("Банк"),
            KeyboardButton("Игры"),
            KeyboardButton("Работа"),
            KeyboardButton("Топ снежков"),
            KeyboardButton("🏠 Дом"),
            KeyboardButton("Бонус")
        )
    else:
        markup.add(
            KeyboardButton("Баланс"),
            KeyboardButton("Топ"),
            KeyboardButton("Игры")
        )
    
    return markup

pending_ref_codes = {}

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
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}\nОбратитесь к администратору.")
            return
        
        ref_code = None
        if len(message.text.split()) > 1:
            ref_code = message.text.split()[1].strip()
            logging.info(f"Пользователь {user_id} пришел по ссылке с кодом: {ref_code}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            is_new_user = True
            
            if ref_code:
                pending_ref_codes[user_id] = ref_code
                logging.info(f"Сохранен реф-код для нового пользователя {user_id}: {ref_code}")
            
            referral_code = f"ref{user_id}"
            
            cursor.execute(
                'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp())
            )
            conn.commit()
            
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
            if ref_code:
                pending_ref_codes[user_id] = ref_code
                logging.info(f"Сохранен реф-код для существующего пользователя {user_id}: {ref_code}")
            
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для доступа к боту решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        conn.close()
        
        if ref_code:
            process_ref_or_check(user_id, username, first_name, ref_code)
        
        markup = create_main_menu(message.chat.id)
        
        if message.chat.id > 0:
            welcome_text = "✨ Добро пожаловать! ✨\n\nВыберите действие из меню ниже:"
        else:
            welcome_text = f"👋 Привет, {first_name}!\n\nИспользуйте меню ниже для работы с ботом в этом чате.\n\n💡 Для полного функционала напишите мне в ЛС!"
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')
    
    except Exception as e:
        logging.error(f"Ошибка в start: {e}", exc_info=True)
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте снова позже.")
# === СИСТЕМА МАЙНИНГА ЕЛОК ===
@bot.message_handler(func=lambda message: message.text == "Майнинг")
def handle_mining(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT video_cards, last_mining_collect, balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            video_cards, last_collect, balance = result
            
            # Рассчитываем накопленные елки
            accumulated_trees = 0
            if video_cards > 0 and last_collect:
                if isinstance(last_collect, str):
                    try:
                        last_collect_time = datetime.strptime(last_collect, '%Y-%m-%d %H:%M:%S').timestamp()
                    except:
                        last_collect_time = time.time() - 86400
                else:
                    last_collect_time = last_collect
                
                current_time = time.time()
                time_passed = current_time - last_collect_time
                
                if time_passed > 0:
                    # 1 уровень = 1 елка в час, 2 уровень = 2 елки, и т.д.
                    income_per_hour = video_cards
                    accumulated_trees = int(income_per_hour * (time_passed / 3600))
            
            # Доход в час
            income_per_hour = video_cards
            
            # Стоимость следующей карты
            card_price = 2000 * (video_cards + 1)
            
            # Формируем сообщение
            message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
            message_text += f"🎮 *Видеокарт:* {video_cards}\n"
            message_text += f"💰 *Доход:* {income_per_hour} 🎄/час\n\n"
            
            if video_cards == 0:
                message_text += "💡 Купите первую видеокарту чтобы начать майнить!"
            elif accumulated_trees > 0:
                message_text += f"📦 *Накоплено:* {accumulated_trees} 🎄"
            else:
                message_text += "⏳ Доход еще не накоплен"
            
            bot.send_message(message.chat.id, message_text, 
                           reply_markup=create_mining_keyboard(video_cards, accumulated_trees, card_price),
                           parse_mode='Markdown')
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка в майнинге: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки майнинга")

def create_mining_keyboard(video_cards, accumulated_trees, card_price):
    """Создает клавиатуру для майнинга"""
    markup = InlineKeyboardMarkup(row_width=2)
    
    if accumulated_trees > 0:
        markup.add(
            InlineKeyboardButton(f"🔄 Собрать {accumulated_trees}🎄", callback_data="mining_collect")
        )
    
    markup.add(
        InlineKeyboardButton(f"💳 Купить карту {format_balance(card_price)}❄️", callback_data="mining_buy")
    )
    
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('mining_'))
def mining_callback_handler(call):
    user_id = call.from_user.id
    
    try:
        if call.data == "mining_collect":
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT video_cards, last_mining_collect, balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ Ошибка загрузки данных!")
                conn.close()
                return
                
            video_cards, last_collect, balance = result
            
            if video_cards == 0:
                bot.answer_callback_query(call.id, "❌ У вас нет видеокарт для сбора!")
                conn.close()
                return
                
            current_time = time.time()
            
            # Рассчитываем накопленные елки
            accumulated_trees = 0
            if last_collect:
                if isinstance(last_collect, str):
                    try:
                        last_collect_time = datetime.strptime(last_collect, '%Y-%m-%d %H:%M:%S').timestamp()
                    except:
                        last_collect_time = current_time - 86400
                else:
                    last_collect_time = last_collect
                
                time_passed = current_time - last_collect_time
                
                if time_passed > 0:
                    income_per_hour = video_cards
                    accumulated_trees = int(income_per_hour * (time_passed / 3600))
            
            if accumulated_trees > 0:
                cursor.execute(
                    'UPDATE users SET balance = balance + ?, last_mining_collect = ? WHERE user_id = ?',
                    (accumulated_trees, current_time, user_id)
                )
                conn.commit()
                
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                new_balance = cursor.fetchone()[0]
                
                # Обновляем статистику майнинга
                cursor.execute('UPDATE users SET mining_trees = mining_trees + ? WHERE user_id = ?', 
                             (accumulated_trees, user_id))
                conn.commit()
                
                bot.answer_callback_query(call.id, f"✅ Собрано {accumulated_trees}🎄")
                
                # Пересчитываем для обновленного сообщения
                new_video_cards = video_cards
                new_income_per_hour = new_video_cards
                new_card_price = 2000 * (new_video_cards + 1)
                
                message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
                message_text += f"🎮 *Видеокарт:* {new_video_cards}\n"
                message_text += f"💰 *Доход:* {new_income_per_hour} 🎄/час\n\n"
                message_text += f"✅ *Собрано:* {accumulated_trees} 🎄\n"
                message_text += f"💳 *Баланс:* {format_balance(new_balance)}❄️"
                
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_mining_keyboard(new_video_cards, 0, new_card_price),
                    parse_mode='Markdown'
                )
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
                
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                new_balance = cursor.fetchone()[0]
                
                bot.answer_callback_query(call.id, f"✅ Куплена видеокарта {new_video_cards} уровня!")
                
                message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
                message_text += f"🎮 *Видеокарт:* {new_video_cards}\n"
                message_text += f"💰 *Доход:* {new_income_per_hour} 🎄/час\n\n"
                message_text += f"💳 *Баланс:* {format_balance(new_balance)}❄️"
                
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_mining_keyboard(new_video_cards, 0, new_card_price),
                    parse_mode='Markdown'
                )
            else:
                bot.answer_callback_query(call.id, 
                    f"❌ Недостаточно денег! Нужно: {format_balance(card_price)}❄️",
                    show_alert=True)
            
            conn.close()
    
    except Exception as e:
        logging.error(f"Ошибка в mining_callback_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка базы данных")
@bot.message_handler(func=lambda message: message.text == "Баланс" and message.chat.id < 0)
def handle_balance_group(message):
    try:
        user_id = message.from_user.id
        
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!")
            return
            
        balance = get_balance(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, nickname FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            first_name, nickname = result
            display_name = nickname if nickname and nickname.strip() else first_name
        else:
            display_name = message.from_user.first_name
        
        response = f"👤 {display_name}\n💰 Баланс: ❄️{format_balance(balance)}"
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logging.error(f"Ошибка в handle_balance_group: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text == "Топ" and message.chat.id < 0)
def handle_top_group(message):
    try:
        user_id = message.from_user.id
        
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT user_id, balance, 
               CASE 
                   WHEN username IS NOT NULL AND username != '' THEN '@' || username 
                   ELSE first_name 
               END as display_name
        FROM users 
        WHERE balance > 0 AND is_banned = 0
        ORDER BY balance DESC
        LIMIT 3
        ''')
        
        top_users = cursor.fetchall()
        
        response = "🏆 Топ снежков:\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id_db, balance, display_name) in enumerate(top_users, 1):
            cursor.execute('SELECT nickname FROM users WHERE user_id = ?', (user_id_db,))
            nickname_result = cursor.fetchone()
            
            if nickname_result and nickname_result[0]:
                display_name = nickname_result[0]
            
            response += f"{medals[i-1]} {display_name}: ❄️{format_balance(balance)}\n"
        
        conn.close()
        
        user_position = get_user_position_in_top(user_id, 'balance')
        user_balance = get_balance(user_id)
        
        if user_position:
            response += f"\n🎯 Твоя позиция: #{user_position}\n💰 Твой баланс: ❄️{format_balance(user_balance)}"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_top_group: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

def process_ref_or_check(user_id, username, first_name, ref_code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT amount, max_activations, current_activations FROM checks WHERE code = ?', (ref_code,))
        check_data = cursor.fetchone()
        
        if check_data:
            amount, max_activations, current_activations = check_data
            
            cursor.execute('SELECT * FROM check_activations WHERE user_id = ? AND check_code = ?', (user_id, ref_code))
            already_activated = cursor.fetchone()
            
            if already_activated:
                bot.send_message(user_id, "❌ Вы уже активировали этот чек!")
            elif current_activations >= max_activations:
                bot.send_message(user_id, "❌ Чек уже использован максимальное количество раз!")
            else:
                cursor.execute('UPDATE checks SET current_activations = current_activations + 1 WHERE code = ? AND current_activations < max_activations', (ref_code,))
                
                if cursor.rowcount > 0:
                    cursor.execute('INSERT OR IGNORE INTO check_activations (user_id, check_code) VALUES (?, ?)', (user_id, ref_code))
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
                    conn.commit()
                    
                    bot.send_message(user_id, f"🎉 Вы активировали чек на ❄️{format_balance(amount)}!")
                    logging.info(f"Пользователь {user_id} активировал чек {ref_code} на сумму {amount}")
                else:
                    bot.send_message(user_id, "❌ Чек уже был активирован другим пользователем!")
            
            conn.close()
            return
        
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                
                cursor.execute('SELECT user_id, username, first_name FROM users WHERE user_id = ? AND is_banned = 0', (referrer_id,))
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
                        referrer_username = referrer_data[1] if referrer_data[1] else referrer_data[2]
                        new_user_name = f"@{username}" if username else first_name
                        
                        bot.send_message(
                            referrer_id,
                            f"🎉 Новый реферал!\n"
                            f"👤 {new_user_name}\n"
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
        
        bonus_amount = int(win_amount * 0.03)
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

@bot.message_handler(func=lambda message: message.text == "👥 Скам")
def handle_scam(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(referral_wins)")
        referral_wins_exists = cursor.fetchone()
        
        if not referral_wins_exists:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_wins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referee_id INTEGER,
                win_amount INTEGER,
                bonus_amount INTEGER,
                game_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.send_message(message.chat.id, "❌ Реферальный код не найден")
            conn.close()
            return
        
        ref_code = result[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
        ref_count_result = cursor.fetchone()
        ref_count = ref_count_result[0] if ref_count_result else 0
        
        cursor.execute('''
            SELECT 
                SUM(bonus_amount) as total_bonus,
                COUNT(*) as total_wins
            FROM referral_wins 
            WHERE referrer_id = ?
        ''', (user_id,))
        
        bonus_stats = cursor.fetchone()
        total_bonus = bonus_stats[0] if bonus_stats and bonus_stats[0] else 0
        total_wins = bonus_stats[1] if bonus_stats and bonus_stats[1] else 0
        
        ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
        
        message_text = f"👥 Твоя ссылка:\n`{ref_link}`\n\n"
        message_text += f"📊 Статистика:\n"
        message_text += f"• Рефералов: {ref_count}\n"
        message_text += f"• Бонусы от игр: {format_balance(total_bonus)}❄️\n"
        message_text += f"• Выигрышей: {total_wins}\n\n"
        message_text += f"💡 +3% от ВСЕХ выигрышей рефералов"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄", callback_data="refresh_scam"))
        
        bot.send_message(message.chat.id, message_text, parse_mode='Markdown', reply_markup=markup)
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка в handle_scam: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:50]}")

@bot.callback_query_handler(func=lambda call: call.data == "refresh_scam")
def refresh_scam_callback(call):
    try:
        user_id = call.from_user.id
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            conn.close()
            return
        
        ref_code = result[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
        ref_count_result = cursor.fetchone()
        ref_count = ref_count_result[0] if ref_count_result else 0
        
        cursor.execute('''
            SELECT 
                SUM(bonus_amount) as total_bonus,
                COUNT(*) as total_wins
            FROM referral_wins 
            WHERE referrer_id = ?
        ''', (user_id,))
        
        bonus_stats = cursor.fetchone()
        total_bonus = bonus_stats[0] if bonus_stats and bonus_stats[0] else 0
        total_wins = bonus_stats[1] if bonus_stats and bonus_stats[1] else 0
        
        ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
        
        message_text = f"👥 Твоя ссылка:\n`{ref_link}`\n\n"
        message_text += f"📊 Статистика:\n"
        message_text += f"• Рефералов: {ref_count}\n"
        message_text += f"• Бонусы от игр: {format_balance(total_bonus)}❄️\n"
        message_text += f"• Выигрышей: {total_wins}\n\n"
        message_text += f"💡 +3% от ВСЕХ выигрышей рефералов"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄", callback_data="refresh_scam"))
        
        try:
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logging.error(f"Ошибка редактирования: {e}")
        
        bot.answer_callback_query(call.id, "✅")
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка refresh_scam: {e}")
        bot.answer_callback_query(call.id, "❌")

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

def get_prestige_badge(user_id):
    try:
        id_number = get_user_id_number(user_id)
        
        if id_number == 0:
            return ""
        
        if id_number == 1:
            return "👑 Первый пользователь"
        elif id_number <= 3:
            return "👑 Основатель"
        elif id_number <= 10:
            return "⭐ Первые 10"
        elif id_number <= 50:
            return "✨ Первые 50"
        elif id_number <= 100:
            return "🔹 Первые 100"
        elif id_number <= 500:
            return "🟢 Первые 500"
        else:
            return ""
    except:
        return ""

@bot.message_handler(func=lambda message: message.text.lower() == "я")
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
            SELECT first_name, video_cards, bank_deposit, last_mining_collect, registered_at 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            first_name, video_cards, bank_deposit, last_mining_collect, registered_at = result
            
            total_accumulated = 0
            if last_mining_collect and last_mining_collect > 0 and video_cards > 0:
                current_time = time.time()
                hours_passed = int((current_time - last_mining_collect) / 3600)
                if hours_passed > 0:
                    hourly_income = video_cards * (video_cards + 1) // 2
                    total_accumulated = hourly_income * hours_passed
            
            prestige_id = get_prestige_id(user_id)
            prestige_badge = get_prestige_badge(user_id)
            
            reg_date = "Неизвестно"
            if registered_at:
                try:
                    reg_date = registered_at[:10]
                except:
                    reg_date = str(registered_at)[:10]
            
            message_text = f"👤 *{first_name}*\n"
            message_text += f"{prestige_id}\n\n"
            
            message_text += f"💰 *Баланс:* ❄️{format_balance(balance)}\n"
            
            if video_cards > 0:
                message_text += f"*Елки:* 🎄{total_accumulated}\n"
            else:
                message_text += f"🎄 *Елки:* 🎄0\n"
            
            if bank_deposit > 0:
                message_text += f"🏦 *В банке:* ❄️{format_balance(bank_deposit)}\n"
            
            message_text += f"📅 *Регистрация:* {reg_date}"
            
            current_house = get_current_house(user_id)
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                message_text += f"\n🏠 *Дом:* {house_name}"
            
            try:
                snowman_path = "g.png"
                
                if not os.path.exists(snowman_path):
                    bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
                    conn.close()
                    return
                
                if current_house:
                    house_info = HOUSE_SHOP.get(current_house, {})
                    house_image = house_info.get('image')
                    
                    if house_image and os.path.exists(house_image):
                        house_img = Image.open(house_image).convert("RGBA")
                        snowman_img = Image.open(snowman_path).convert("RGBA")
                        
                        house_width, house_height = house_img.size
                        snowman_width, snowman_height = snowman_img.size
                        
                        if (house_width, house_height) != (snowman_width, snowman_height):
                            snowman_img = snowman_img.resize((house_width, house_height), Image.Resampling.LANCZOS)
                        
                        combined = Image.new('RGBA', (house_width, house_height))
                        combined.paste(house_img, (0, 0))
                        combined.paste(snowman_img, (0, 0), snowman_img)
                        
                        temp_file = f"temp_combo_{user_id}.png"
                        combined.save(temp_file, "PNG")
                        
                        with open(temp_file, 'rb') as photo:
                            bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                        
                        os.remove(temp_file)
                        conn.close()
                        return
                    else:
                        with open(snowman_path, 'rb') as photo:
                            bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                        conn.close()
                        return
                else:
                    with open(snowman_path, 'rb') as photo:
                        bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                    conn.close()
                    return
                    
            except Exception as e:
                logging.error(f"Ошибка создания изображения: {e}")
                
                try:
                    with open("g.png", 'rb') as photo:
                        bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                except:
                    bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
                
                conn.close()
                return
            
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
    
    except Exception as e:
        logging.error(f"Ошибка в handle_me: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

user_houses = {}
HOUSE_SHOP = {}

def load_house_shop():
    try:
        if os.path.exists('house_shop.json'):
            import json
            with open('house_shop.json', 'r', encoding='utf-8') as f:
                HOUSE_SHOP = json.load(f)
            logging.info(f"Загружен магазин домов: {len(HOUSE_SHOP)} домов")
    except Exception as e:
        logging.error(f"Ошибка загрузки магазина: {e}")
        HOUSE_SHOP = {}

def save_house_shop():
    try:
        import json
        with open('house_shop.json', 'w', encoding='utf-8') as f:
            json.dump(HOUSE_SHOP, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения магазина: {e}")

@bot.message_handler(func=lambda message: message.text == "🏠 Дом")
def handle_house(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"),
            InlineKeyboardButton("🚪 Шкаф", callback_data="house_wardrobe"),
            InlineKeyboardButton("🏠 Текущий дом", callback_data="house_current"),
            InlineKeyboardButton("❓ Помощь", callback_data="house_help")
        )
        
        current_house = get_current_house(user_id)
        
        if current_house:
            house_info = HOUSE_SHOP.get(current_house, {})
            house_name = house_info.get('name', 'Неизвестный дом')
            response = f"🏠 *Ваш дом*\n\n🏡 *{house_name}*\n\nВыберите действие:"
        else:
            response = "🏠 *Ваш дом*\n\n🚫 У вас еще нет дома!\n\n🛒 Купите дом в магазине:"
        
        bot.send_message(message.chat.id, response, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в доме: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки дома")

def get_current_house(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='user_houses'
        """)
        
        if not cursor.fetchone():
            cursor.execute("""
            CREATE TABLE user_houses (
                user_id INTEGER,
                house_id TEXT,
                is_current INTEGER DEFAULT 0,
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, house_id)
            )
            """)
            conn.commit()
        
        cursor.execute("""
        SELECT house_id FROM user_houses 
        WHERE user_id = ? AND is_current = 1
        """, (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
        
    except Exception as e:
        logging.error(f"Ошибка получения дома: {e}")
        return None

def get_user_houses(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT house_id, is_current FROM user_houses 
        WHERE user_id = ? ORDER BY purchased_at DESC
        """, (user_id,))
        
        houses = cursor.fetchall()
        conn.close()
        
        return houses
        
    except Exception as e:
        logging.error(f"Ошибка получения домов: {e}")
        return []

def purchase_house(user_id, house_id):
    try:
        house_info = HOUSE_SHOP.get(house_id)
        if not house_info:
            return False, "Дом не найден в магазине"
        
        houses = get_user_houses(user_id)
        for house, _ in houses:
            if house == house_id:
                return False, "У вас уже есть этот дом"
        
        price = house_info['price']
        balance = get_balance(user_id)
        
        if balance < price:
            return False, f"Недостаточно средств. Нужно: {format_balance(price)}❄️"
        
        update_balance(user_id, -price)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        is_first = len(houses) == 0
        
        cursor.execute("""
        INSERT INTO user_houses (user_id, house_id, is_current) 
        VALUES (?, ?, ?)
        """, (user_id, house_id, 1 if is_first else 0))
        
        conn.commit()
        conn.close()
        
        return True, "✅ Дом куплен!"
        
    except Exception as e:
        logging.error(f"Ошибка покупки дома: {e}")
        return False, "❌ Ошибка покупки"

def set_current_house(user_id, house_id):
    try:
        houses = get_user_houses(user_id)
        has_house = False
        for house, _ in houses:
            if house == house_id:
                has_house = True
                break
        
        if not has_house:
            return False, "У вас нет этого дома"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        UPDATE user_houses SET is_current = 0 WHERE user_id = ?
        """, (user_id,))
        
        cursor.execute("""
        UPDATE user_houses SET is_current = 1 
        WHERE user_id = ? AND house_id = ?
        """, (user_id, house_id))
        
        conn.commit()
        conn.close()
        
        return True, "✅ Дом установлен как текущий!"
        
    except Exception as e:
        logging.error(f"Ошибка установки дома: {e}")
        return False, "❌ Ошибка"

@bot.message_handler(func=lambda message: message.text.lower().startswith('дом ') and is_admin(message.from_user.id))
def handle_add_house(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, 
                           "❌ Формат: дом [цена] [название_файла.png]\n"
                           "Пример: дом 1000000 mansion.png")
            return
        
        try:
            price = int(parts[1])
            if price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверная цена")
            return
        
        filename = parts[2].strip()
        
        if not os.path.exists(filename):
            bot.send_message(message.chat.id, f"❌ Файл '{filename}' не найден")
            return
        
        house_id = f"house_{int(time.time())}_{random.randint(1000, 9999)}"
        house_name = os.path.splitext(filename)[0].replace('_', ' ').title()
        
        HOUSE_SHOP[house_id] = {
            "name": house_name,
            "price": price,
            "image": filename,
            "added_by": message.from_user.id,
            "added_at": time.time()
        }
        
        save_house_shop()
        
        bot.send_message(message.chat.id,
                       f"✅ Дом добавлен в магазин!\n\n"
                       f"🏡 Название: {house_name}\n"
                       f"💰 Цена: {format_balance(price)}❄️\n"
                       f"🖼 Файл: {filename}\n"
                       f"🔑 ID: {house_id}")
        
    except Exception as e:
        logging.error(f"Ошибка добавления дома: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

def create_house_shop_keyboard(page=1):
    markup = InlineKeyboardMarkup(row_width=2)
    
    house_ids = list(HOUSE_SHOP.keys())
    total_houses = len(house_ids)
    
    if total_houses == 0:
        markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
        return markup
    
    total_pages = total_houses
    page = max(1, min(page, total_pages))
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"shop_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="shop_current"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"shop_page_{page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    current_house_id = house_ids[page-1]
    house_info = HOUSE_SHOP.get(current_house_id, {})
    
    markup.row(InlineKeyboardButton(f"💰 Купить за {format_balance(house_info.get('price', 0))}❄️", 
                                   callback_data=f"buy_house_{current_house_id}"))
    
    markup.row(
        InlineKeyboardButton("🚪 Шкаф", callback_data="house_wardrobe"),
        InlineKeyboardButton("🔙 Назад", callback_data="house_back")
    )
    
    return markup

@bot.callback_query_handler(func=lambda call: call.data in ["house_shop", "shop_current"] or call.data.startswith("shop_page_"))
def handle_shop_with_images(call):
    try:
        user_id = call.from_user.id
        
        if call.data == "house_shop":
            page = 1
        elif call.data.startswith("shop_page_"):
            page = int(call.data.split("_")[2])
        else:
            page = 1
        
        house_ids = list(HOUSE_SHOP.keys())
        total_houses = len(house_ids)
        
        if total_houses == 0:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
            
            bot.edit_message_text(
                "🛒 *Магазин домов*\n\n🚫 В магазине пока нет домов.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        
        page = max(1, min(page, total_houses))
        house_id = house_ids[page-1]
        house_info = HOUSE_SHOP.get(house_id, {})
        
        house_image = house_info.get('image')
        
        if house_image and os.path.exists(house_image):
            try:
                caption = f"🛒 *Магазин домов*\n\n"
                caption += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                caption += f"💰 Цена: {format_balance(house_info.get('price', 0))}❄️\n"
                caption += f"📊 Страница: {page}/{total_houses}\n\n"
                caption += "💡 Нажмите '💰 Купить' чтобы приобрести этот дом"
                
                with open(house_image, 'rb') as img_file:
                    bot.send_photo(
                        call.message.chat.id,
                        img_file,
                        caption=caption,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                
            except Exception as e:
                logging.error(f"Ошибка отправки изображения: {e}")
                text = f"🛒 *Магазин домов*\n\n"
                text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                text += f"💰 Цена: {format_balance(house_info.get('price', 0))}❄️\n"
                text += f"📊 Страница: {page}/{total_houses}\n\n"
                text += "❌ Изображение недоступно"
                
                try:
                    bot.edit_message_text(
                        text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                except:
                    bot.send_message(
                        call.message.chat.id,
                        text,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
        else:
            text = f"🛒 *Магазин домов*\n\n"
            text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
            text += f"💰 Цена: {format_balance(house_info.get('price', 0))}❄️\n"
            text += f"📊 Страница: {page}/{total_houses}\n\n"
            text += "❌ Изображение дома недоступно"
            
            try:
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_house_shop_keyboard(page),
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=create_house_shop_keyboard(page),
                    parse_mode='Markdown'
                )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logging.error(f"Ошибка в магазине: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_house_"))
def handle_buy_house(call):
    try:
        user_id = call.from_user.id
        house_id = call.data[10:]
        house_info = HOUSE_SHOP.get(house_id)
        
        if not house_info:
            bot.answer_callback_query(call.id, "❌ Дом не найден")
            return
        
        house_name = house_info['name']
        house_price = house_info['price']
        
        balance = get_balance(user_id)
        
        if balance < house_price:
            bot.answer_callback_query(
                call.id, 
                f"❌ Недостаточно средств! Нужно: {format_balance(house_price)}❄️",
                show_alert=True
            )
            return
        
        success, message = purchase_house(user_id, house_id)
        
        if success:
            page = 1
            if call.message.caption:
                import re
                match = re.search(r'Страница (\d+)/(\d+)', call.message.caption)
                if match:
                    page = int(match.group(1))
            
            try:
                house_ids = list(HOUSE_SHOP.keys())
                total_houses = len(house_ids)
                page = max(1, min(page, total_houses))
                current_house_id = house_ids[page-1]
                current_house_info = HOUSE_SHOP.get(current_house_id, {})
                
                caption = f"🛒 *Магазин домов*\n\n"
                caption += f"🏡 *{current_house_info.get('name', 'Неизвестный дом')}*\n"
                caption += f"💰 Цена: {format_balance(current_house_info.get('price', 0))}❄️\n"
                caption += f"📊 Страница: {page}/{total_houses}\n\n"
                caption += "✅ Дом куплен! Зайдите в шкаф чтобы выбрать его"
                
                house_image = current_house_info.get('image')
                if house_image and os.path.exists(house_image):
                    try:
                        with open(house_image, 'rb') as img_file:
                            bot.edit_message_media(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                media=telebot.types.InputMediaPhoto(
                                    media=img_file,
                                    caption=caption,
                                    parse_mode='Markdown'
                                ),
                                reply_markup=create_house_shop_keyboard(page)
                            )
                    except:
                        bot.edit_message_caption(
                            caption=caption,
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=create_house_shop_keyboard(page),
                            parse_mode='Markdown'
                        )
                else:
                    bot.edit_message_caption(
                        caption=caption,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                    
            except Exception as e:
                logging.error(f"Ошибка обновления магазина: {e}")
                pass
            
            bot.answer_callback_query(call.id, f"✅ Куплен дом '{house_name}'!")
            
            house_image = house_info.get('image')
            if house_image and os.path.exists(house_image):
                try:
                    with open(house_image, 'rb') as img_file:
                        bot.send_photo(
                            call.message.chat.id,
                            img_file,
                            caption=f"🎉 Вы купили новый дом!\n\n"
                                  f"🏡 *{house_name}*\n"
                                  f"💰 Цена: {format_balance(house_price)}❄️\n\n"
                                  f"💡 Зайдите в 🚪 Шкаф чтобы выбрать этот дом как текущий",
                            parse_mode='Markdown'
                        )
                except:
                    pass
        else:
            bot.answer_callback_query(call.id, message, show_alert=True)
            
    except Exception as e:
        logging.error(f"Ошибка покупки дома: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка покупки")

def create_wardrobe_keyboard(user_id, page=1):
    markup = InlineKeyboardMarkup(row_width=2)
    
    houses = get_user_houses(user_id)
    total_houses = len(houses)
    
    if total_houses == 0:
        markup.row(InlineKeyboardButton("🛒 В магазин", callback_data="house_shop"))
        markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
        return markup
    
    total_pages = total_houses
    page = max(1, min(page, total_pages))
    
    current_house = get_current_house(user_id)
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"wardrobe_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="wardrobe_current"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"wardrobe_page_{page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    house_id, is_current = houses[page-1]
    house_info = HOUSE_SHOP.get(house_id, {"name": "Неизвестный дом"})
    
    if house_id != current_house:
        markup.row(InlineKeyboardButton(f"✅ Выбрать {house_info['name']}", callback_data=f"set_house_{house_id}"))
    
    markup.row(
        InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"),
        InlineKeyboardButton("🔙 Назад", callback_data="house_back")
    )
    
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "house_wardrobe" or 
                                          call.data.startswith("wardrobe_page_") or 
                                          call.data == "wardrobe_current")
def handle_wardrobe(call):
    try:
        user_id = call.from_user.id
        
        if call.data == "house_wardrobe":
            page = 1
        elif call.data.startswith("wardrobe_page_"):
            page = int(call.data.split("_")[2])
        else:
            page = 1
        
        houses = get_user_houses(user_id)
        total_houses = len(houses)
        
        if total_houses == 0:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🛒 В магазин", callback_data="house_shop"))
            markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
            
            bot.edit_message_text(
                "🚪 *Шкаф*\n\n🚫 У вас еще нет домов.\n\n🛒 Купите дом в магазине!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        
        page = max(1, min(page, total_houses))
        house_id, is_current = houses[page-1]
        house_info = HOUSE_SHOP.get(house_id, {})
        current_house = get_current_house(user_id)
        
        house_image = house_info.get('image')
        
        if house_image and os.path.exists(house_image):
            try:
                caption = f"🚪 *Ваш шкаф*\n\n"
                caption += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                caption += f"📊 Страница: {page}/{total_houses}\n"
                
                if house_id == current_house:
                    caption += f"\n✅ *Текущий дом*\n"
                else:
                    caption += f"\n💡 Нажмите '✅ Выбрать' чтобы установить этот дом как текущий"
                
                with open(house_image, 'rb') as img_file:
                    bot.send_photo(
                        call.message.chat.id,
                        img_file,
                        caption=caption,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                
            except Exception as e:
                logging.error(f"Ошибка отправки изображения шкафа: {e}")
                text = f"🚪 *Ваш шкаф*\n\n"
                text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                text += f"📊 Страница: {page}/{total_houses}\n"
                
                if house_id == current_house:
                    text += f"\n✅ *Текущий дом*\n"
                else:
                    text += f"\n💡 Нажмите '✅ Выбрать' чтобы установить этот дом как текущий"
                
                try:
                    bot.edit_message_text(
                        text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                except:
                    bot.send_message(
                        call.message.chat.id,
                        text,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
        else:
            text = f"🚪 *Ваш шкаф*\n\n"
            text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
            text += f"📊 Страница: {page}/{total_houses}\n"
            
            if house_id == current_house:
                text += f"\n✅ *Текущий дом*\n"
            else:
                text += f"\n💡 Нажмите '✅ Выбрать' чтобы установить этот дом как текущий"
            
            try:
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_wardrobe_keyboard(user_id, page),
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=create_wardrobe_keyboard(user_id, page),
                    parse_mode='Markdown'
                )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logging.error(f"Ошибка в шкафу: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data in ["house_current", "house_help", "house_back", "set_house_", "wardrobe_current"])
def house_other_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data == "house_current":
            current_house = get_current_house(user_id)
            
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                
                house_image = house_info.get('image')
                if house_image and os.path.exists(house_image):
                    try:
                        with open(house_image, 'rb') as img_file:
                            bot.send_photo(
                                call.message.chat.id,
                                img_file,
                                caption=f"🏠 *Текущий дом*\n\n"
                                      f"🏡 *{house_name}*\n\n"
                                      f"💡 Чтобы сменить дом, зайдите в 🚪 Шкаф",
                                parse_mode='Markdown'
                            )
                    except:
                        bot.send_message(
                            call.message.chat.id,
                            f"🏠 *Текущий дом*\n\n"
                            f"🏡 *{house_name}*",
                            parse_mode='Markdown'
                        )
                else:
                    bot.send_message(
                        call.message.chat.id,
                        f"🏠 *Текущий дом*\n\n"
                        f"🏡 *{house_name}*",
                        parse_mode='Markdown'
                    )
            else:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🛒 В магазин", callback_data="house_shop"))
                
                bot.send_message(
                    call.message.chat.id,
                    "🚫 У вас еще нет дома!\n\n🛒 Купите дом в магазине:",
                    reply_markup=markup
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data == "house_help":
            help_text = (
                "🏠 *Система домов*\n\n"
                "🛒 *Магазин* - Покупайте новые дома (отображаются с картинками)\n"
                "🚪 *Шкаф* - Управляйте своими домами\n"
                "🏠 *Текущий дом* - Просмотр активного дома\n\n"
                "*Как использовать:*\n"
                "1. Купите дом в магазине (перелистывайте кнопками ⬅️➡️)\n"
                "2. Выберите его в шкафе как текущий\n"
                "3. Ваш дом будет отображаться в профиле\n\n"
                "*Для администраторов:*\n"
                "`дом [цена] [файл.png]` - добавить дом в магазин"
            )
            
            try:
                bot.edit_message_text(
                    help_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    help_text,
                    parse_mode='Markdown'
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data == "house_back":
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"),
                InlineKeyboardButton("🚪 Шкаф", callback_data="house_wardrobe"),
                InlineKeyboardButton("🏠 Текущий дом", callback_data="house_current"),
                InlineKeyboardButton("❓ Помощь", callback_data="house_help")
            )
            
            current_house = get_current_house(user_id)
            
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                response = f"🏠 *Ваш дом*\n\n🏡 *{house_name}*\n\nВыберите действие:"
            else:
                response = "🏠 *Ваш дом*\n\n🚫 У вас еще нет дома!\n\n🛒 Купите дом в магазине:"
            
            try:
                bot.edit_message_text(
                    response,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    response,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data.startswith("set_house_"):
            house_id = call.data[10:]
            house_info = HOUSE_SHOP.get(house_id)
            
            if not house_info:
                bot.answer_callback_query(call.id, "❌ Дом не найден")
                return
            
            success, message = set_current_house(user_id, house_id)
            
            if success:
                page = 1
                if call.message.caption:
                    import re
                    match = re.search(r'Страница (\d+)/(\d+)', call.message.caption)
                    if match:
                        page = int(match.group(1))
                
                try:
                    houses = get_user_houses(user_id)
                    total_houses = len(houses)
                    page = max(1, min(page, total_houses))
                    
                    current_house_id = get_current_house(user_id)
                    house_info = HOUSE_SHOP.get(current_house_id, {})
                    
                    caption = f"🚪 *Ваш шкаф*\n\n"
                    caption += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                    caption += f"📊 Страница: {page}/{total_houses}\n"
                    caption += f"\n✅ *Теперь это текущий дом!*"
                    
                    bot.edit_message_caption(
                        caption=caption,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                    
                except Exception as e:
                    logging.error(f"Ошибка обновления шкафа: {e}")
                
                bot.answer_callback_query(call.id, f"✅ Выбран дом '{house_info['name']}'!")
                
            else:
                bot.answer_callback_query(call.id, message, show_alert=True)
                
        elif call.data == "wardrobe_current":
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике домов: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка")
        except:
            pass

load_house_shop()

@bot.message_handler(func=lambda message: message.text == "Работа")
def handle_work(message):
    if is_spam(message.from_user.id):
        return
    
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    bot.send_message(message.chat.id, "💼 Выберите способ заработка:", reply_markup=create_work_menu())

@bot.message_handler(func=lambda message: message.text == "◀️ Назад")
def handle_back(message):
    if is_spam(message.from_user.id):
        return
    
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    markup = create_main_menu()
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text.lower().startswith('лог ') and is_admin(message.from_user.id))
def handle_user_logs(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: лог ID/@username\n"
                           "Примеры:\n"
                           "`лог 123456789`\n"
                           "`лог @username`\n"
                           "`лог all` - все логи", 
                           parse_mode='Markdown')
            return
        
        target = parts[1].strip()
        
        if target.lower() == 'all':
            send_all_logs(message)
            return
        
        user_id = None
        
        if target.startswith('@'):
            username = target[1:].lower()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = ?', (username,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                user_id = result[0]
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь {target} не найден")
                return
        else:
            try:
                user_id = int(target)
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный ID. Используйте цифры или @username")
                return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, first_name, balance, bank_deposit, 
                   registered_at, last_activity, is_banned
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        conn.close()
        
        if not user_data:
            bot.send_message(message.chat.id, f"❌ Пользователь с ID {user_id} не найден")
            return
        
        username, first_name, balance, bank_deposit, registered_at, last_activity, is_banned = user_data
        
        log_filename = f"logs_user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        
        with open(log_filename, 'w', encoding='utf-8') as log_file:
            log_file.write(f"ЛОГИ ПОЛЬЗОВАТЕЛЯ\n")
            log_file.write(f"{'='*50}\n\n")
            
            log_file.write(f"👤 ИНФОРМАЦИЯ:\n")
            log_file.write(f"ID: {user_id}\n")
            log_file.write(f"Username: @{username if username else 'нет'}\n")
            log_file.write(f"Имя: {first_name}\n")
            log_file.write(f"Баланс: {format_balance(balance)}❄️\n")
            log_file.write(f"В банке: {format_balance(bank_deposit)}❄️\n")
            log_file.write(f"Статус: {'🚫 ЗАБАНЕН' if is_banned else '✅ АКТИВЕН'}\n")
            log_file.write(f"Регистрация: {registered_at}\n")
            log_file.write(f"Последняя активность: {last_activity}\n\n")
            
            log_file.write(f"📊 АКТИВНОСТЬ:\n")
            log_file.write(f"{'='*50}\n")
            
            if os.path.exists('bot.log'):
                with open('bot.log', 'r', encoding='utf-8') as bot_log:
                    lines = bot_log.readlines()
                    user_logs = []
                    
                    for line in lines:
                        if str(user_id) in line:
                            user_logs.append(line)
                    
                    if user_logs:
                        for log_line in user_logs[-1000:]:
                            log_file.write(log_line)
                    else:
                        log_file.write("Логи не найдены\n")
            else:
                log_file.write("Файл логов не найден\n")
            
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"📈 СТАТИСТИКА ИЗ БАЗЫ:\n")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
            ref_count = cursor.fetchone()[0]
            log_file.write(f"Рефералов: {ref_count}\n")
            
            cursor.execute('SELECT COUNT(*) FROM checks WHERE created_by = ?', (user_id,))
            checks_created = cursor.fetchone()[0]
            log_file.write(f"Чеков создано: {checks_created}\n")
            
            cursor.execute('SELECT COUNT(*) FROM check_activations WHERE user_id = ?', (user_id,))
            checks_activated = cursor.fetchone()[0]
            log_file.write(f"Чеков активировано: {checks_activated}\n")
            
            conn.close()
            
            if user_id in SNOW_JOBS:
                job = SNOW_JOBS[user_id]
                log_file.write(f"\n❄️ СНЕЖНАЯ РАБОТА:\n")
                log_file.write(f"Прогресс: {job['clicks_done']}/150\n")
                log_file.write(f"Заработок: {format_balance(job['current_earnings'])}❄️\n")
                log_file.write(f"Ошибок: {job['wrong_clicks']}\n")
                log_file.write(f"Уборок: {job['completed']}\n")
            
            if user_id in SNOW_COOLDOWN:
                log_file.write(f"Снег кулдаун: до {datetime.fromtimestamp(SNOW_COOLDOWN[user_id])}\n")
            
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"Бот: @{(bot.get_me()).username}\n")
        
        with open(log_filename, 'rb') as file_to_send:
            caption = (
                f"📋 Логи пользователя\n"
                f"👤 ID: {user_id}\n"
                f"📛 Имя: {first_name}\n"
                f"📊 Баланс: {format_balance(balance)}❄️\n"
                f"📅 Регистрация: {registered_at}\n"
                f"⏰ Последняя активность: {last_activity}"
            )
            
            bot.send_document(
                message.chat.id,
                file_to_send,
                caption=caption,
                timeout=60
            )
        
        os.remove(log_filename)
        
    except Exception as e:
        logging.error(f"Ошибка в команде лог: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:200]}")

def send_all_logs(message):
    try:
        if not os.path.exists('bot.log'):
            bot.send_message(message.chat.id, "❌ Файл логов не найден")
            return
        
        bot.send_message(message.chat.id, "⏳ Подготавливаю все логи...")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        log_filename = f"all_logs_{timestamp}.txt"
        zip_filename = f"logs_{timestamp}.zip"
        
        shutil.copy2('bot.log', log_filename)
        
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(log_filename, os.path.basename(log_filename))
        
        with open(zip_filename, 'rb') as zip_file:
            bot.send_document(
                message.chat.id,
                zip_file,
                caption=f"📦 Все логи бота\n📅 {timestamp}",
                timeout=60
            )
        
        os.remove(log_filename)
        os.remove(zip_filename)
        
    except Exception as e:
        logging.error(f"Ошибка отправки всех логов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

def log_user_action(user_id, action, details=""):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        username = user_data[0] if user_data else "Unknown"
        first_name = user_data[1] if user_data else "Unknown"
        
        log_message = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"USER:{user_id} "
            f"NAME:{first_name} "
            f"USERNAME:@{username if username else 'none'} "
            f"ACTION:{action} "
            f"DETAILS:{details}"
        )
        
        logging.info(log_message)
        
        user_log_file = f"user_logs_{user_id % 100}.log"
        with open(user_log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
            
    except Exception as e:
        logging.error(f"Ошибка логирования: {e}")

@bot.message_handler(func=lambda message: message.text.lower() == 'очиститьлоги' and is_admin(message.from_user.id))
def handle_clear_logs(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ ДА, ОЧИСТИТЬ", callback_data="clear_logs_confirm"),
            InlineKeyboardButton("❌ ОТМЕНА", callback_data="clear_logs_cancel")
        )
        
        if os.path.exists('bot.log'):
            size_mb = os.path.getsize('bot.log') / (1024 * 1024)
            size_info = f"📁 Текущий размер: {size_mb:.2f} MB\n"
        else:
            size_info = ""
        
        bot.send_message(
            message.chat.id,
            f"⚠️ ОЧИСТКА ЛОГОВ\n\n"
            f"{size_info}"
            f"Эта операция:\n"
            f"• Удалит логи старше 7 дней\n"
            f"• Оставит последние 1000 строк\n"
            f"• Создаст бэкап\n\n"
            f"Подтвердите очистку:",
            reply_markup=markup
        )
        
    except Exception as e:
        logging.error(f"Ошибка в очистке логов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('clear_logs_'))
def clear_logs_callback(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет прав!")
            return
            
        if call.data == "clear_logs_confirm":
            bot.answer_callback_query(call.id, "⏳ Очищаю...")
            
            if clear_old_logs():
                bot.edit_message_text(
                    "✅ Логи очищены!\n"
                    "Старые записи удалены,\n"
                    "оставлены последние 1000 строк.",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.edit_message_text(
                    "❌ Ошибка очистки логов",
                    call.message.chat.id,
                    call.message.message_id
                )
                
        elif call.data == "clear_logs_cancel":
            bot.answer_callback_query(call.id, "❌ Отменено")
            bot.edit_message_text(
                "❌ Очистка логов отменена",
                call.message.chat.id,
                call.message.message_id
            )
            
    except Exception as e:
        logging.error(f"Ошибка в callback очистки логов: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

def clear_old_logs():
    try:
        if not os.path.exists('bot.log'):
            return False
        
        backup_name = f"bot_log_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.log"
        shutil.copy2('bot.log', backup_name)
        
        with open('bot.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if len(lines) <= 1000:
            lines_to_keep = lines
        else:
            lines_to_keep = lines[-1000:]
        
        with open('bot.log', 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
        
        for filename in os.listdir('.'):
            if filename.startswith('bot_log_backup_') and filename.endswith('.log'):
                file_time_str = filename[15:-4]
                try:
                    file_time = datetime.strptime(file_time_str, '%Y%m%d_%H%M')
                    if (datetime.now() - file_time).days > 7:
                        os.remove(filename)
                except:
                    pass
        
        logging.info("Логи очищены")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка очистки логов: {e}")
        return False

@bot.message_handler(func=lambda message: message.text == "🖱️ Клиер")
def handle_clicker(message):
    if is_spam(message.from_user.id):
        return
    
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    bot.send_message(message.chat.id, "🎯 Найди правильную кнопку:", reply_markup=create_clicker_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('clicker_'))
def clicker_callback_handler(call):
    if is_spam(call.from_user.id):
        bot.answer_callback_query(call.id, "⏳ Слишком быстро! Подождите немного.")
        return
        
    user_id = call.from_user.id
    
    banned, reason = is_banned(user_id)
    if banned:
        bot.answer_callback_query(call.id, "🚫 Вы забанены!")
        return
    
    symbol = call.data.split('_')[1]
    
    try:
        if symbol == "✅":
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT click_power, click_streak FROM users WHERE user_id = ?', (user_id,))
            click_power, click_streak = cursor.fetchone()
            
            new_streak = click_streak + 1
            cursor.execute('UPDATE users SET click_streak = ? WHERE user_id = ?', (new_streak, user_id))
            
            cursor.execute(
                'UPDATE users SET balance = balance + ?, last_click = ? WHERE user_id = ?',
                (click_power, time.time(), user_id)
            )
            conn.commit()
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance = cursor.fetchone()[0]
            
            conn.close()
            
            bot.answer_callback_query(call.id, "✅ Верно! +❄️" + format_balance(click_power))
            bot.edit_message_text(
                f"👻 Серия: {new_streak}\n❄️ Баланс: ❄️{format_balance(new_balance)}",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_clicker_keyboard()
            )
        else:
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET click_streak = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, "❌ Неверно! Серия сброшена.")
            bot.edit_message_text(
                "❌ Неверный выбор! Серия сброшена.\n🎯 Найди правильную кнопку:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_clicker_keyboard()
            )
    
    except Exception as e:
        print(f"Ошибка в clicker_callback_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка базы данных")

def create_work_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    scam_button = KeyboardButton("👥 Скам")
    snow_button = KeyboardButton("❄️ Чистка снега")
    back_button = KeyboardButton("◀️ Назад")
    markup.add(scam_button, snow_button, back_button)
    return markup

SNOW_COOLDOWN = {}
SNOW_JOBS = {}
SNOW_LAST_MESSAGE = {}

@bot.message_handler(func=lambda message: message.text == "❄️ Чистка снега")
def handle_snow_work_new(message):
    try:
        user_id = message.from_user.id
        
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        current_time = time.time()
        if user_id in SNOW_COOLDOWN:
            cooldown_end = SNOW_COOLDOWN[user_id]
            if current_time < cooldown_end:
                time_left = int(cooldown_end - current_time)
                minutes = time_left // 160
                seconds = time_left % 160
                
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
        
        base_earnings = 1000
        bonus_per_job = 25
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
            f"❄️ УБОРКА СНЕГА\n\n"
            f"🎯 100 кликов\n"
            f"💰 {format_balance(earnings)}❄️\n"
            f"📈 Надбавка: +50❄️\n"
            f"❗ Штраф: -100❄️ за ошибку\n"
            f"🏆 Выполнено: {completed_jobs}"
        )
        
        markup = create_snow_keyboard(150, earnings)
        msg = bot.send_message(message.chat.id, stats_msg, reply_markup=markup)
        
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
                update_balance(user_id, earnings)
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
                    f"✅ УБОРКА ЗАВЕРШЕНА!\n\n"
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
                    f"⚠️ УБОРКА ЗАВЕРШЕНА\n\n"
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
                    call.message.message_id
                )
            except:
                bot.send_message(call.message.chat.id, result_msg)
            
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

@bot.message_handler(func=lambda message: message.text.lower() == "сбросснег")
def handle_snow_reset(message):
    user_id = message.from_user.id
    
    if user_id in SNOW_JOBS:
        del SNOW_JOBS[user_id]
        if user_id in SNOW_LAST_MESSAGE:
            del SNOW_LAST_MESSAGE[user_id]
        bot.send_message(message.chat.id, "✅ Уборка сброшена")
    else:
        bot.send_message(message.chat.id, "⚠️ Нет активной уборки")

@bot.message_handler(func=lambda message: message.text.lower() == "снегстат")
def handle_snow_stat(message):
    user_id = message.from_user.id
    
    message_text = "❄️ СТАТИСТИКА\n\n"
    
    if user_id in SNOW_JOBS:
        job = SNOW_JOBS[user_id]
        
        message_text += f"📊 Активная уборка:\n"
        message_text += f"🎯 {job['clicks_done']}/150\n"
        message_text += f"💰 {format_balance(job['current_earnings'])}❄️\n"
        message_text += f"❌ Ошибок: {job['wrong_clicks']}\n"
        message_text += f"🏆 Всего уборок: {job['completed']}"
    else:
        message_text += "📭 Нет активной уборки\n"
        message_text += "💡 Начните через 'Работа'"
    
    if user_id in SNOW_COOLDOWN:
        cooldown_end = SNOW_COOLDOWN[user_id]
        current_time = time.time()
        
        if current_time < cooldown_end:
            time_left = int(cooldown_end - current_time)
            minutes = time_left // 60
            seconds = time_left % 60
            
            message_text += f"\n\n⏳ До следующей: {minutes}м {seconds}с"
    
    bot.send_message(message.chat.id, message_text)

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

snow_cleanup_thread = threading.Thread(target=cleanup_snow_data, daemon=True)
snow_cleanup_thread.start()

@bot.message_handler(func=lambda message: message.text == "Банк")
def handle_bank(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        bank_deposit = get_bank_deposit(user_id)
        
        bank_text = f"""🏦 Банковские услуги:

❄️ На вкладе: ❄️{format_balance(bank_deposit)}
📈 Проценты: 0.5% каждый час
❄️ Начисляются автоматически при любом действии

📝 Команды:
• вклад [сумма] - положить под 0.5% в час
• снять [сумма] - забрать с вклада"""
        
        bot.send_message(message.chat.id, bank_text)
    except Exception as e:
        print(f"Ошибка в handle_bank: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('вклад '))
def handle_deposit(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
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
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
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

def get_user_display_name(user_id, username, first_name, nickname=None):
    try:
        if nickname and nickname.strip():
            return nickname.strip()
        
        if username:
            return f"@{username}"
        else:
            return first_name if first_name else f"ID: {user_id}"
    except:
        return f"ID: {user_id}"

@bot.message_handler(func=lambda message: message.text.lower().startswith('ник '))
def handle_change_nickname(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: ник [ваш новый ник]\n"
                           "Пример: ник ⛄СнежныйВолк❄️\n"
                           "💡 Ник может содержать эмодзи и символы")
            return
        
        new_nickname = parts[1].strip()
        
        if len(new_nickname) > 32:
            bot.send_message(message.chat.id, "❌ Слишком длинный ник! Макс. 32 символа")
            return
        
        if len(new_nickname) < 2:
            bot.send_message(message.chat.id, "❌ Слишком короткий ник! Мин. 2 символа")
            return
        
        forbidden_chars = ['<', '>', '&', '"', "'", '`', '\\', '/', ';']
        for char in forbidden_chars:
            if char in new_nickname:
                bot.send_message(message.chat.id, f"❌ Ник содержит запрещенный символ: {char}")
                return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'nickname' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
            conn.commit()
        
        cursor.execute('UPDATE users SET nickname = ? WHERE user_id = ?', 
                      (new_nickname, user_id))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, 
                       f"✅ Ваш ник изменен на: {new_nickname}\n\n"
                       f"💡 Теперь вас будут видеть с этим ником в топах!")
        
    except Exception as e:
        logging.error(f"Ошибка смены ника: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при смене ника. Попробуйте позже.")

user_top_page = {}
user_top_mode = {}

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

@bot.message_handler(func=lambda message: message.text.lower().startswith('ценадома ') and is_admin(message.from_user.id))
def handle_change_house_price(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, 
                           "❌ Формат: ценадома [ID_дома] [новая_цена]\n"
                           "Пример: ценадома house_12345 2000000\n\n"
                           "📝 Чтобы узнать ID дома, используйте команду: `магазин`")
            return
        
        house_id = parts[1].strip()
        try:
            new_price = int(parts[2])
            if new_price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной")
                return
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная цена. Введите число")
            return
        
        if house_id not in HOUSE_SHOP:
            bot.send_message(message.chat.id, f"❌ Дом с ID '{house_id}' не найден")
            return
        
        old_price = HOUSE_SHOP[house_id]['price']
        house_name = HOUSE_SHOP[house_id]['name']
        
        HOUSE_SHOP[house_id]['price'] = new_price
        HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
        HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
        
        save_house_shop()
        
        bot.send_message(message.chat.id,
                       f"✅ Цена дома изменена!\n\n"
                       f"🏡 Дом: {house_name}\n"
                       f"🆔 ID: `{house_id}`\n"
                       f"💰 Старая цена: {format_balance(old_price)}❄️\n"
                       f"💰 Новая цена: {format_balance(new_price)}❄️\n\n"
                       f"💡 Изменения вступят в силу сразу")
        
    except Exception as e:
        logging.error(f"Ошибка изменения цены дома: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower().startswith('массцена ') and is_admin(message.from_user.id))
def handle_mass_price_change(message):
    try:
        if not is_admin(message.from_user.id):
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: массцена [процент] или массцена [фиксированная_сумма]\n"
                           "Примеры:\n"
                           "массцена +20% - увеличить все цены на 20%\n"
                           "массцена -10% - уменьшить все цены на 10%\n"
                           "массцена 1000000 - установить всем минимальную цену 1M")
            return
        
        change = parts[1].strip()
        
        if not HOUSE_SHOP:
            bot.send_message(message.chat.id, "❌ В магазине нет домов")
            return
        
        changed_count = 0
        report = "📊 *Массовое изменение цен*\n\n"
        
        if change.endswith('%'):
            try:
                percent = float(change[:-1])
                if percent == 0:
                    bot.send_message(message.chat.id, "❌ Процент не может быть 0%")
                    return
                
                report += f"📈 Изменение на {percent}%\n\n"
                
                for house_id, house_info in HOUSE_SHOP.items():
                    old_price = house_info['price']
                    multiplier = 1 + (percent / 100)
                    new_price = int(old_price * multiplier)
                    
                    new_price = (new_price // 1000) * 1000
                    if new_price < 1000:
                        new_price = 1000
                    
                    HOUSE_SHOP[house_id]['price'] = new_price
                    HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
                    HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
                    
                    report += f"🏡 {house_info['name']}:\n"
                    report += f"   {format_balance(old_price)}❄️ → {format_balance(new_price)}❄️\n"
                    changed_count += 1
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный процент")
                return
                
        else:
            try:
                min_price = parse_bet_amount(change, float('inf'))
                if min_price is None or min_price < 0:
                    bot.send_message(message.chat.id, "❌ Неверная сумма")
                    return
                
                report += f"💰 Установка минимальной цены: {format_balance(min_price)}❄️\n\n"
                
                for house_id, house_info in HOUSE_SHOP.items():
                    old_price = house_info['price']
                    new_price = max(old_price, min_price)
                    
                    if new_price != old_price:
                        HOUSE_SHOP[house_id]['price'] = new_price
                        HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
                        HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
                        
                        report += f"🏡 {house_info['name']}:\n"
                        report += f"   {format_balance(old_price)}❄️ → {format_balance(new_price)}❄️\n"
                        changed_count += 1
                
            except:
                bot.send_message(message.chat.id, "❌ Неверная сумма")
                return
        
        if changed_count > 0:
            save_house_shop()
            
            report += f"\n✅ Изменено: {changed_count}/{len(HOUSE_SHOP)} домов"
            bot.send_message(message.chat.id, report, parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, "ℹ️ Ни одна цена не была изменена")
        
    except Exception as e:
        logging.error(f"Ошибка массового изменения цен: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower() == 'эко')
def handle_eco_oneline(message):
    try:
        user_id = message.from_user.id
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance, bank_deposit FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return
        
        user_total = user_data[0] + user_data[1]
        
        cursor.execute('SELECT SUM(balance + bank_deposit) FROM users')
        total = cursor.fetchone()[0] or 1
        
        conn.close()
        
        percentage = (user_total / total) * 100
        
        bot.send_message(message.chat.id, 
                        f"💵 {format_balance(user_total)}❄️ |  {percentage:.4f}%")
        
    except:
        pass

@bot.message_handler(func=lambda message: message.text in ["Топ снежков", "Топ скам"])
def handle_top_menu(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        user_id = message.from_user.id
        
        if message.text == "Топ снежков":
            user_top_mode[user_id] = 'balance'
            title = "🎅 Топ снежков 🎅"
        else:
            user_top_mode[user_id] = 'scam'
            title = "👥 Топ скама 👥"
        
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

def get_user_position_in_top(user_id, mode='balance'):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if mode == 'balance':
            cursor.execute('''
            SELECT position FROM (
                SELECT user_id, ROW_NUMBER() OVER (ORDER BY balance DESC) as position
                FROM users 
                WHERE balance > 0 AND is_banned = 0
            ) WHERE user_id = ?
            ''', (user_id,))
        else:
            cursor.execute('''
            SELECT position FROM (
                SELECT 
                    u.user_id,
                    ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
                FROM users u
                LEFT JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
                WHERE u.is_banned = 0
                GROUP BY u.user_id
                HAVING COUNT(r.user_id) > 0
            ) WHERE user_id = ?
            ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
        
    except Exception as e:
        logging.error(f"Ошибка получения позиции пользователя: {e}")
        return None

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

@bot.message_handler(func=lambda message: message.text.lower() == 'мойид')
def handle_my_id(message):
    try:
        user_id = message.from_user.id
        
        prestige_id = get_prestige_id(user_id)
        prestige_badge = get_prestige_badge(user_id)
        id_number = get_user_id_number(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT registered_at FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        reg_date = "Неизвестно"
        if result and result[0]:
            try:
                reg_date = result[0]
                if isinstance(reg_date, str):
                    reg_date = reg_date[:19]
            except:
                reg_date = str(result[0])[:19]
        
        message_text = f"🆔 *ИНФОРМАЦИЯ О ID*\n\n"
        message_text += f"{prestige_id}\n"
        
        if prestige_badge:
            message_text += f"{prestige_badge}\n\n"
        else:
            message_text += f"\n"
        
        message_text += f"📊 *Номер регистрации:* {id_number}\n"
        message_text += f"📅 *Дата регистрации:* {reg_date}\n\n"
        
        message_text += "*🎯 Уровни престижа:*\n"
        message_text += "👑 #1-3 - Основатель\n"
        message_text += "👑 #1-10 - Первые 10\n"
        message_text += "⭐ #11-50 - Первые 50\n"
        message_text += "✨ #51-100 - Первые 100\n"
        message_text += "🔹 #101-500 - Первые 500\n"
        message_text += "#501+ - Обычный ID\n\n"
        message_text += "*💡 ID навсегда - чем меньше номер, тем больше уважения!*"
        
        bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower() == 'обновить' and is_admin(message.from_user.id))
def handle_update_usernames(message):
    try:
        if not is_admin(message.from_user.id):
            return
        
        bot.send_message(message.chat.id, "⏳ Начинаю обновление username для всех пользователей...")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, username FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        
        updated_count = 0
        failed_count = 0
        
        for user in users:
            user_id, current_username = user
            
            try:
                chat_user = bot.get_chat(user_id)
                new_username = chat_user.username
                
                if new_username != current_username:
                    cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', 
                                  (new_username, user_id))
                    updated_count += 1
                    
            except Exception as e:
                failed_count += 1
                logging.warning(f"Не удалось обновить пользователя {user_id}: {e}")
            
            time.sleep(0.1)
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Обновление завершено!\n\n"
            f"📊 Статистика:\n"
            f"• Всего проверено: {len(users)}\n"
            f"• Обновлено: {updated_count}\n"
            f"• Ошибок: {failed_count}\n\n"
            f"💡 Теперь в топах и переводах будут использоваться актуальные username!"
        )
        
    except Exception as e:
        logging.error(f"Ошибка обновления username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower() == 'блокреф' and is_admin(message.from_user.id))
def handle_block_admin_refs(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        admin_ids = ADMIN_IDS
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        bot.send_message(message.chat.id, "🛡️ *БЛОКИРОВКА РЕФЕРАЛЬНЫХ СВЯЗЕЙ С АДМИНАМИ*\n\n⏳ Обрабатываю...")
        
        blocked_refs_count = 0
        removed_bonuses_count = 0
        
        for admin_id in admin_ids:
            try:
                cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (admin_id,))
                admin_ref = cursor.fetchone()
                
                if admin_ref and admin_ref[0]:
                    cursor.execute('UPDATE users SET referred_by = NULL WHERE user_id = ?', (admin_id,))
                    blocked_refs_count += 1
                
                cursor.execute('UPDATE users SET referred_by = NULL WHERE referred_by = ?', (admin_id,))
                
                cursor.execute('DELETE FROM referral_wins WHERE referee_id = ?', (admin_id,))
                removed_count = cursor.rowcount
                removed_bonuses_count += removed_count
                
                cursor.execute('DELETE FROM referral_wins WHERE referrer_id = ?', (admin_id,))
                
                logging.info(f"Заблокирован админ {admin_id}, удалено {removed_count} бонусов")
                
            except Exception as e:
                logging.error(f"Ошибка обработки админа {admin_id}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        report = f"✅ *БЛОКИРОВКА ЗАВЕРШЕНА!*\n\n"
        report += f"👮 Администраторов обработано: {len(admin_ids)}\n"
        report += f"🔗 Удалено реферальных связей: {blocked_refs_count}\n"
        report += f"💰 Удалено бонусных начислений: {removed_bonuses_count}\n\n"
        report += f"*📝 Что изменилось:*\n"
        report += f"1. Админы НЕ МОГУТ быть чьими-то рефералами\n"
        report += f"2. С админов НЕ начисляются бонусы 3%\n"
        report += f"3. Админы НЕ получают бонусы от других\n"
        report += f"4. Все старые бонусы от админов УДАЛЕНЫ\n\n"
        report += f"🛡️ *Система защищена от накрутки!*"
        
        bot.send_message(message.chat.id, report, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка блокировки админов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

def get_roulette_photo(winning_number):
    try:
        filename = f"{winning_number}.png"
        filepath = f"/app/{filename}"
        
        if os.path.exists(filepath):
            logging.info(f"✅ Найдено изображение рулетки: {filepath}")
            return filepath
        
        other_formats = ['.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']
        for ext in other_formats:
            filename = f"{winning_number}{ext}"
            filepath = f"/app/{filename}"
            if os.path.exists(filepath):
                logging.info(f"✅ Найдено изображение рулетки: {filepath}")
                return filepath
        
        current_dir = os.getcwd()
        for ext in ['.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']:
            filename = f"{winning_number}{ext}"
            filepath = os.path.join(current_dir, filename)
            if os.path.exists(filepath):
                logging.info(f"✅ Найдено изображение рулетки: {filepath}")
                return filepath
        
        logging.warning(f"❌ Изображение для числа {winning_number} не найдено")
        return None
        
    except Exception as e:
        logging.error(f"Ошибка поиска изображения рулетки: {e}")
        return None

WIN_PHRASES = [
    "🎉 Урааа!",
    "🎯 Попал в точку!",
    "🔥 В яблочко!",
    "✨ Невероятно!",
    "💰 мегагей",
    "💎 Радуйся суко!",
    "🌟 Фантастик момбастик!",
    "⚡ Иба четка",
    "🏆 Чемпион!",
    "💫 Залет!",
    "🎊 Праздник!",
    "🤑 Дальше больше!"
]

LOSE_PHRASES = [
    "❌ Не повезло...",
    "💸 Упс...",
    "😔 извинись потом",
    "📉 Не в этот раз",
    "🌀 Не судьба",
    "🌪️ Вращение не удалось",
    "💨 Унесло бабки",
    "⚰️ Похороны ставки",
    "📉 Дальше меньше",
    "🌧 Не твой день",
    "🎭 Луз",
    "🔚 Нечетенька"
]

BASKETBALL_WIN_PHRASES = [
    "🏀 Отличный бросок!",
    "🎯 Точное попадание!",
    "🔥 Забил!",
    "✨ Идеально!",
    "💰 Чистая игра!",
    "💎 Бросок мастера!",
    "🌟 Свисток! Это гол!",
    "⚡ Молниеносный бросок!",
    "🏆 Чемпионский бросок!",
    "💫 Волшебный мяч!",
    "🎊 Праздник в зале!",
    "🤑 Игрок месяца!"
]

BASKETBALL_LOSE_PHRASES = [
    "❌ Мяч не попал...",
    "💸 Почти забил",
    "😔 Мимо кольца",
    "📉 Не судьба",
    "🌀 Мяч улетел",
    "🌪️ Плохой бросок",
    "💨 Воздушный шар",
    "⚰️ Похороны мяча",
    "📉 Провальная атака",
    "🌧️ Дождь неудач",
    "🎭 Игра окончена",
    "🔚 Конец матча"
]

def update_game_with_bonus(user_id, win_amount, game_name):
    try:
        if win_amount > 0:
            update_balance(user_id, win_amount)
            add_referral_win_bonus(user_id, win_amount, game_name)
    except:
        pass

@bot.message_handler(func=lambda message: message.text.lower().startswith(('рул ', 'рулетка ')))
def handle_roulette(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
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
            new_balance = get_balance(user_id)
            
            image_path = get_roulette_photo(winning_number)
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"<b>✅ Удача</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                            parse_mode='HTML'
                        )
                except:
                    bot.send_message(message.chat.id, 
                                   f"<b>✅ Удача</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                                   parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, 
                               f"<b>✅ Удача</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                               parse_mode='HTML')
        else:
            new_balance = get_balance(user_id)
            
            image_path = get_roulette_photo(winning_number)
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"<b>❌ Не повезло</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                            parse_mode='HTML'
                        )
                except:
                    bot.send_message(message.chat.id, 
                                   f"<b>❌ Не повезло</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                                   parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, 
                               f"<b>❌ Не повезло</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                               parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('куб ', 'кубик ')))
def handle_dice(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
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
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎲')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        if bet_type in ['бол', 'большие', 'б']:
            win = result in [4, 5, 6]
            multiplier = 2
        
        elif bet_type in ['мал', 'малые', 'м']:
            win = result in [1, 2, 3]
            multiplier = 2
        
        elif bet_type in ['чет', 'четные', 'четн']:
            win = result in [2, 4, 6]
            multiplier = 2
        
        elif bet_type in ['нечет', 'нечетные', 'неч']:
            win = result in [1, 3, 5]
            multiplier = 2
        
        else:
            try:
                target = int(bet_type)
                if 1 <= target <= 6:
                    win = result == target
                    multiplier = 6
                else:
                    bot.send_message(message.chat.id, "❌ Неверный тип")
                    update_balance(user_id, bet_amount)
                    return
            except:
                bot.send_message(message.chat.id, "❌ Неверный тип")
                update_balance(user_id, bet_amount)
                return
        
        if win:
            win_amount = bet_amount * multiplier
            update_game_with_bonus(user_id, win_amount, "🎲 Кубик")
            new_balance = get_balance(user_id)
            
            win_phrase = random.choice(WIN_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{win_phrase}</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}!\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
        else:
            new_balance = get_balance(user_id)
            lose_phrase = random.choice(LOSE_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{lose_phrase}</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}.\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('бск ', 'баскетбол ')))
def handle_basketball(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🏀')
        time.sleep(2)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 2.5
        
        if result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_game_with_bonus(user_id, win_amount, "🏀 Баскетбол")
            new_balance = get_balance(user_id)
            
            win_phrase = random.choice(BASKETBALL_WIN_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{win_phrase}</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}!\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
        else:
            new_balance = get_balance(user_id)
            lose_phrase = random.choice(BASKETBALL_LOSE_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{lose_phrase}</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}.\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('слот ', 'слоты ')))
def handle_slots(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎰')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        if result == 1:
            win = True
            multiplier = 64
        elif result == 22:
            win = True
            multiplier = 10
        elif result == 43:
            win = True
            multiplier = 5
        elif result == 64:
            win = True
            multiplier = 3
        
        if win:
            win_amount = bet_amount * multiplier
            update_game_with_bonus(user_id, win_amount, "🎰 Слоты")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 Выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('фтб ', 'футбол ')))
def handle_football(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='⚽')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1.5
        
        if result == 3 or result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_game_with_bonus(user_id, win_amount, "⚽ Футбол")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 ГОООЛ! Выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Мяч не забит! Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('дартс '))
def handle_darts(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        max_loss = bet_amount * 2
        if max_loss > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств!\nНужно минимум: ❄️{format_balance(max_loss)}")
            return
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎯')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        update_balance(user_id, -bet_amount)
        
        if result == 6:
            win_amount = bet_amount * 5
            update_game_with_bonus(user_id, win_amount, "🎯 Дартс")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, 
                           f"🎯 ПОПАДАНИЕ В ЯБЛОЧКО!\n✅ Выиграли ❄️{format_balance(win_amount)}!\n💰 Ставка: ❄️{format_balance(bet_amount)}\n📈 Коэффициент: ×5\n❄️ Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 1:
            update_balance(user_id, -bet_amount)
            total_loss = bet_amount * 2
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, 
                           f"🎯 ПОЛНЫЙ ПРОМАХ!\n❌ Списанно: ❄️{format_balance(total_loss)}\n💰 Ставка: ❄️{format_balance(bet_amount)}\n📉 Штраф: ×2\n❄️ Баланс: ❄️{format_balance(new_balance)}")
        
        else:
            new_balance = get_balance(user_id)
            ring = "внутреннее кольцо" if result == 5 else "внешнее кольцо"
            bot.send_message(message.chat.id, 
                           f"🎯 Попадание в {ring}\n❌ Проиграли ставку\n💸 Списанно: ❄️{format_balance(bet_amount)}\n❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('боул ', 'боулинг ')))
def handle_bowling(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎳')
        time.sleep(3)
        
        result = dice_message.dice.value
        
        if result == 6:
            win_amount = bet_amount * 2
            update_game_with_bonus(user_id, win_amount, "🎳 Боулинг")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎳 СТРАЙК! Все кегли сбиты! Выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 5:
            update_balance(user_id, bet_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"⚖️ Осталась 1 кегля! Возврат ставки ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 1:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Сбито 1-2 кегли! Осталось 8-9. Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
        
        else:
            new_balance = get_balance(user_id)
            if result == 2:
                remaining = "6-7 кеглей"
            elif result == 3:
                remaining = "4-5 кеглей"
            elif result == 4:
                remaining = "2-3 кегли"
            else:
                remaining = "кеглей"
            
            bot.send_message(message.chat.id, f"❌ Осталось {remaining}! Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('чек ') and not is_admin(message.from_user.id))
def handle_check(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: чек 10ккк 2")
            return
        
        amount = parse_bet_amount(parts[1], balance)
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        try:
            activations = int(parts[2])
            if activations <= 0 or activations > 100:
                bot.send_message(message.chat.id, "❌ Количество активаций должно быть от 1 до 100")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверное количество активаций")
            return
        
        total_amount = amount * activations
        
        if total_amount > balance:
            bot.send_message(message.chat.id, f"❌ Недостаточно средств для создания чека! Нужно: ❄️{format_balance(total_amount)}")
            return
        
        update_balance(user_id, -total_amount)
        
        code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO checks (code, amount, max_activations, created_by) VALUES (?, ?, ?, ?)',
            (code, amount, activations, user_id)
        )
        
        conn.commit()
        conn.close()
        
        check_link = f"https://t.me/{(bot.get_me()).username}?start={code}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Активировать❄️", url=check_link))
        
        bot.send_message(message.chat.id,
                f"💳 Чек создан!\n"
                f"❄️ Сумма: ❄️{format_balance(amount)}\n"
                f"🔢 Активаций: {activations}\n",
                reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в создании чека: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании чека. Попробуйте снова.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('чеф ') and is_admin(message.from_user.id))
def handle_admin_check(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: чеф 1000к 10")
            return
        
        amount = parse_bet_amount(parts[1], float('inf'))
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        try:
            max_activations = int(parts[2])
            if max_activations <= 0:
                bot.send_message(message.chat.id, "❌ Количество активаций должно быть больше 0")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверное количество активаций")
            return
        
        import random
        import string
        check_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO checks (code, amount, max_activations, created_by) VALUES (?, ?, ?, ?)',
            (check_code, amount, max_activations, message.from_user.id)
        )
        conn.commit()
        conn.close()
        
        check_link = f"https://t.me/{(bot.get_me()).username}?start={check_code}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Активировать❄️", url=check_link))
        
        check_text = f"""
<code>🧾 Мультичек</code>
<b>❄️ +{format_balance(amount)}</b>
<b>🔢 Кол-во:</b> <b>{max_activations}</b>
        """.strip()
        
        bot.send_message(
            message.chat.id, 
            check_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    except Exception as e:
        print(f"Ошибка в handle_admin_check: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании чека")

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

@bot.message_handler(func=lambda message: message.text.lower().startswith('забрать ') and is_admin(message.from_user.id))
def handle_take_money(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        if not message.reply_to_message:
            bot.send_message(message.chat.id, "❌ Ответьте на сообщение пользователя, у которого хотите забрать деньги")
            return
        
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username
        target_first_name = message.reply_to_message.from_user.first_name
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: забрать 1000к")
            return
        
        amount = parse_bet_amount(' '.join(parts[1:]), float('inf'))
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        get_or_create_user(target_user_id, target_username, target_first_name)
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (target_user_id,))
        user_balance = cursor.fetchone()
        
        if user_balance:
            balance = user_balance[0]
            if balance < amount:
                bot.send_message(message.chat.id, f"❌ У пользователя недостаточно средств! Баланс: ❄️{format_balance(balance)}")
                conn.close()
                return
            
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, target_user_id))
            conn.commit()
            
            target_name = f"@{target_username}" if target_username else target_first_name
            
            bot.send_message(message.chat.id, 
                           f"✅ Забрано ❄️{format_balance(amount)} у пользователя {target_name}\n"
                           f"❄️ Новый баланс пользователя: ❄️{format_balance(balance - amount)}")
            
            try:
                bot.send_message(target_user_id, 
                               f"⚠️ У вас забрали ❄️{format_balance(amount)} администратором\n"
                               f"❄️ Новый баланс: ❄️{format_balance(balance - amount)}")
            except:
                pass
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_take_money: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при заборе денег")

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

@bot.message_handler(func=lambda message: message.text.lower().startswith('разбан ') and is_admin(message.from_user.id))
def handle_unban_username(message):
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: разбан @username\n"
                           "       или: разбан ID\n\n"
                           "Примеры:\n"
                           "• разбан @ivan\n"
                           "• разбан 123456789\n"
                           "• разбан @user (ответом на сообщение)")
            return
        
        target = parts[1].strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if message.reply_to_message:
            target_user_id = message.reply_to_message.from_user.id
            
            cursor.execute('SELECT username, first_name, is_banned FROM users WHERE user_id = ?', (target_user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                bot.send_message(message.chat.id, "❌ Пользователь не найден в базе данных")
                conn.close()
                return
            
            username, first_name, is_banned = user_data
            
            if is_banned == 0:
                bot.send_message(message.chat.id, "⚠️ Пользователь не забанен")
                conn.close()
                return
            
            cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                          (target_user_id,))
            conn.commit()
            
            target_name = f"@{username}" if username else first_name
            bot.send_message(message.chat.id, f"✅ Пользователь {target_name} разбанен!")
            
            try:
                bot.send_message(target_user_id, 
                               f"🎉 Вы разбанены в боте!\n"
                               f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
            except:
                pass
        
        elif target.startswith('@'):
            username = target[1:]
            
            cursor.execute('SELECT user_id, first_name, is_banned FROM users WHERE username = ?', (username,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_user_id, first_name, is_banned = user_data
                
                if is_banned == 0:
                    bot.send_message(message.chat.id, f"⚠️ Пользователь @{username} не забанен")
                    conn.close()
                    return
                
                cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                              (target_user_id,))
                conn.commit()
                
                bot.send_message(message.chat.id, f"✅ Пользователь @{username} разбанен!")
                
                try:
                    bot.send_message(target_user_id, 
                                   f"🎉 Вы разбанены в боте!\n"
                                   f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
                except:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь @{username} не найден в базе данных")
        
        else:
            try:
                target_user_id = int(target)
                
                cursor.execute('SELECT username, first_name, is_banned FROM users WHERE user_id = ?', (target_user_id,))
                user_data = cursor.fetchone()
                
                if user_data:
                    username, first_name, is_banned = user_data
                    
                    if is_banned == 0:
                        bot.send_message(message.chat.id, f"⚠️ Пользователь с ID {target_user_id} не забанен")
                        conn.close()
                        return
                    
                    cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                                  (target_user_id,))
                    conn.commit()
                    
                    target_name = f"@{username}" if username else first_name
                    bot.send_message(message.chat.id, f"✅ Пользователь {target_name} (ID: {target_user_id}) разбанен!")
                    
                    try:
                        bot.send_message(target_user_id, 
                                       f"🎉 Вы разбанены в боте!\n"
                                       f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
                    except:
                        pass
                else:
                    bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден в базе данных")
                    
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте @username или ID")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_unban_username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при разбане пользователя: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('передать ', 'кинуть ', 'дать ')))
def handle_transfer(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.split()
        
        if message.reply_to_message:
            if len(parts) < 2:
                bot.send_message(message.chat.id, 
                               "❌ Формат ответа: `передать сумма`\n"
                               "Пример: `передать 1000к`",
                               parse_mode='Markdown')
                return
            
            target_user_id = message.reply_to_message.from_user.id
            target_username = message.reply_to_message.from_user.username
            target_first_name = message.reply_to_message.from_user.first_name
            
            amount_text = ' '.join(parts[1:])
            transfer_amount = parse_bet_amount(amount_text, balance)
            
            target_identifier = f"@{target_username}" if target_username else target_first_name
            
        elif len(parts) >= 3:
            target_identifier = parts[1].strip()
            amount_text = ' '.join(parts[2:])
            
            target_user_id = None
            
            if target_identifier.startswith('@'):
                username = target_identifier[1:].lower()
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = ? AND is_banned = 0', (username,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    target_user_id = result[0]
                else:
                    bot.send_message(message.chat.id, f"❌ Пользователь {target_identifier} не найден или забанен")
                    return
            else:
                try:
                    target_user_id = int(target_identifier)
                except ValueError:
                    bot.send_message(message.chat.id, f"❌ Неверный формат. Используйте @username или ID")
                    return
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (target_user_id,))
            target_data = cursor.fetchone()
            conn.close()
            
            if target_data:
                target_username, target_first_name = target_data
                target_identifier = f"@{target_username}" if target_username else target_first_name
            else:
                target_first_name = "Неизвестный"
                target_username = None
                target_identifier = f"ID: {target_user_id}"
        
        else:
            bot.send_message(message.chat.id, 
                           "❌ Формат:\n"
                           "• Ответьте `передать сумма` на сообщение\n"
                           "• `передать @username сумма`\n"
                           "• `кинуть ID сумма`\n\n"
                           "Примеры:\n"
                           "`передать @ivan 1000к`\n"
                           "`кинуть 123456789 500к`\n"
                           "[Ответить] `дать 1000`")
            return
        
        if not target_user_id:
            bot.send_message(message.chat.id, "❌ Получатель не найден")
            return
        
        if target_user_id == user_id:
            bot.send_message(message.chat.id, "❌ Нельзя передавать деньги самому себе")
            return
        
        target_banned, target_reason = is_banned(target_user_id)
        if target_banned:
            bot.send_message(message.chat.id, f"❌ Получатель забанен!")
            return
        
        if 'transfer_amount' not in locals():
            transfer_amount = parse_bet_amount(amount_text, balance)
        
        if transfer_amount is None:
            bot.send_message(message.chat.id, 
                           "❌ Неверная сумма\n"
                           "Примеры: `1000`, `10к`, `100к`, `1кк`, `1ккк`",
                           parse_mode='Markdown')
            return
        
        if transfer_amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма: 10❄️")
            return
        
        if transfer_amount > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств!\n"
                           f"Ваш баланс: ❄️{format_balance(balance)}\n"
                           f"Нужно ещё: ❄️{format_balance(transfer_amount - balance)}")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, username FROM users WHERE user_id = ?', (target_user_id,))
        target_data = cursor.fetchone()
        
        if not target_data:
            if not target_username and not target_first_name:
                try:
                    chat_member = bot.get_chat_member(target_user_id, target_user_id)
                    target_first_name = chat_member.user.first_name
                    target_username = chat_member.user.username
                except:
                    target_first_name = "Пользователь"
                    target_username = None
            
            get_or_create_user(target_user_id, target_username, target_first_name)
            target_display = f"@{target_username}" if target_username else target_first_name
        else:
            target_first_name, target_username = target_data
            target_display = f"@{target_username}" if target_username else target_first_name
        
        conn.close()
        
        update_balance(user_id, -transfer_amount)
        update_balance(target_user_id, transfer_amount)
        
        new_balance = get_balance(user_id)
        target_balance = get_balance(target_user_id)
        
        sender_username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        
        bot.send_message(message.chat.id,
                       f"✅ *Перевод выполнен!*\n\n"
                       f"👤 *Кому:* {target_display}\n"
                       f"💰 *Сумма:* ❄️{format_balance(transfer_amount)}\n"
                       f"📊 *Ваш баланс:* ❄️{format_balance(new_balance)}",
                       parse_mode='Markdown')
        
        try:
            bot.send_message(target_user_id,
                           f"🎉 *Вам перевели деньги!*\n\n"
                           f"👤 *От:* {sender_username}\n"
                           f"💰 *Сумма:* ❄️{format_balance(transfer_amount)}\n"
                           f"📊 *Ваш баланс:* ❄️{format_balance(target_balance)}",
                           parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Не удалось уведомить получателя {target_user_id}: {e}")
        
        log_user_action(user_id, "TRANSFER_SUCCESS", f"to={target_user_id} amount={transfer_amount}")
        
    except Exception as e:
        logging.error(f"Ошибка в передаче денег: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при передаче. Попробуйте позже.")

def parse_prizes_from_text(prizes_text, winners_count):
    try:
        prizes = []
        
        lines = prizes_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            line = line.replace('❄️', '').replace('⛄', '').replace('🎄', '').replace('💰', '')
            
            import re
            
            matches = re.findall(r'[\d\s.,]+', line)
            if matches:
                for match in matches:
                    try:
                        clean_match = match.replace(' ', '').replace(',', '').replace('.', '')
                        
                        if 'ккк' in line.lower():
                            prize = int(float(clean_match.replace('ккк', '').replace('kkk', '')) * 1000000000)
                        elif 'кк' in line.lower():
                            prize = int(float(clean_match.replace('кк', '').replace('kk', '')) * 1000000)
                        elif 'к' in line.lower() or 'k' in line.lower():
                            prize = int(float(clean_match.replace('к', '').replace('k', '')) * 1000)
                        else:
                            prize = int(clean_match)
                            
                        if prize > 0:
                            prizes.append(prize)
                    except:
                        continue
        
        if not prizes:
            base_prize = 1000000
            for i in range(winners_count):
                prize_amount = base_prize // (2 ** i)
                if prize_amount < 1000:
                    prize_amount = 1000
                prizes.append(prize_amount)
        
        while len(prizes) < winners_count:
            prizes.append(1000)
            
        while len(prizes) > winners_count:
            prizes = prizes[:winners_count]
            
        return prizes
        
    except Exception as e:
        logging.error(f"Ошибка парсинга призов: {e}")
        prizes = []
        base_prize = 100
        for i in range(winners_count):
            prize_amount = base_prize // (2 ** i)
            if prize_amount < 100:
                prize_amount = 100
            prizes.append(prize_amount)
        return prizes

USER_CONTESTS = {}
ACTIVE_CONTESTS = {}
CONTEST_PARTICIPANTS = {}

@bot.message_handler(func=lambda message: message.text.lower() == 'конкурс')
def handle_contest_start(message):
    try:
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            bot.send_message(message.chat.id, "❌ Только администраторы могут создавать конкурсы")
            return
        
        USER_CONTESTS[user_id] = {
            "step": 1,
            "data": {
                "creator_id": user_id,
                "creator_name": message.from_user.first_name,
                "creator_username": message.from_user.username if message.from_user.username else "",
                "start_time": time.time()
            }
        }
        
        bot.send_message(
            message.chat.id,
            "🎉 *СОЗДАНИЕ КОНКУРСА*\n\n"
            "1️⃣ *Шаг 1:* Пришлите ID канала или @username\n\n"
            "*Примеры:*\n"
            "• @channel_username\n"
            "• -1001234567890\n"
            "• https://t.me/channel_username\n\n"
            "⚠️ *Бот должен быть администратором канала*",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка начала конкурса: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка начала конкурса")

@bot.message_handler(func=lambda message: message.from_user.id in USER_CONTESTS)
def handle_contest_steps(message):
    user_id = message.from_user.id
    
    try:
        contest_data = USER_CONTESTS.get(user_id)
        
        if not contest_data:
            bot.send_message(message.chat.id, "❌ Сессия устарела. Используйте /конкурс")
            return
            
        step = contest_data["step"]
        data = contest_data["data"]
        
        if step == 1:
            channel_input = message.text.strip()
            
            bot.send_message(message.chat.id, "⏳ Проверяю канал...")
            
            try:
                if channel_input.startswith('https://t.me/'):
                    channel_input = '@' + channel_input.replace('https://t.me/', '')
                
                chat = bot.get_chat(channel_input)
                
                if chat.type != 'channel':
                    bot.send_message(message.chat.id, "❌ Это не канал")
                    return
                
                bot_id = bot.get_me().id
                try:
                    admins = bot.get_chat_administrators(chat.id)
                    is_admin = any(admin.user.id == bot_id for admin in admins)
                    
                    if not is_admin:
                        bot.send_message(message.chat.id,
                                       f"❌ Бот не админ в канале!\n"
                                       f"Добавьте бота как администратора в: {chat.title}")
                        return
                except:
                    bot.send_message(message.chat.id,
                                   f"⚠️ Не могу проверить права. Убедитесь что бот админ в: {chat.title}")
                
                data["channel_id"] = chat.id
                data["channel_title"] = chat.title
                data["channel_username"] = f"@{chat.username}" if chat.username else f"ID: {chat.id}"
                contest_data["step"] = 2
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Канал: {chat.title}\n\n"
                    f"2️⃣ *Шаг 2:* Сколько участников нужно?\n"
                    f"• Минимум: 10\n"
                    f"• Максимум: 1000\n\n"
                    f"Пример: `100`",
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                error_msg = str(e).lower()
                if "not found" in error_msg:
                    bot.send_message(message.chat.id, "❌ Канал не найден")
                elif "forbidden" in error_msg:
                    bot.send_message(message.chat.id, "❌ Нет доступа к каналу")
                else:
                    bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:50]}")
                return
            
        elif step == 2:
            try:
                max_participants = int(message.text.strip())
                if max_participants < 10:
                    bot.send_message(message.chat.id, "❌ Минимум 10 участников")
                    return
                if max_participants > 1000:
                    bot.send_message(message.chat.id, "❌ Максимум 1000 участников")
                    return
                    
                data["max_participants"] = max_participants
                contest_data["step"] = 3
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Участников: {max_participants}\n\n"
                    f"3️⃣ *Шаг 3:* Сколько будет победителей?\n"
                    f"• Минимум: 1\n"
                    f"• Максимум: {min(10, max_participants)}\n\n"
                    f"Пример: `5`",
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")
                return
                
        elif step == 3:
            try:
                winners_count = int(message.text.strip())
                max_participants = data.get("max_participants", 10)
                
                if winners_count < 1:
                    bot.send_message(message.chat.id, "❌ Минимум 1 победитель")
                    return
                if winners_count > min(10, max_participants):
                    bot.send_message(message.chat.id, 
                                   f"❌ Максимум {min(10, max_participants)} победителей")
                    return
                    
                data["winners_count"] = winners_count
                contest_data["step"] = 4
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Победителей: {winners_count}\n\n"
                    f"4️⃣ *Шаг 4:* Введите призы\n\n"
                    f"*Пример:*\n"
                    f"1 место - 1.000.000❄️\n"
                    f"2 место - 500.000❄️\n"
                    f"3 место - 250.000❄️",
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")
                return
                
        elif step == 4:
            prizes_text = message.text.strip()
            if not prizes_text:
                bot.send_message(message.chat.id, "❌ Введите призы")
                return
                
            data["prizes_text"] = prizes_text
            
            preview_text = f"""
📋 *ПРЕДПРОСМОТР КОНКУРСА*

*🎯 Канал:* {data.get('channel_title', 'N/A')}
*👥 Участников:* {data.get('max_participants', 'N/A')}
*🏆 Победителей:* {data.get('winners_count', 'N/A')}

*💰 Призы:*
{data.get('prizes_text', 'N/A')}

*👤 Организатор:* {data.get('creator_name', 'N/A')}
"""
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ ОПУБЛИКОВАТЬ", callback_data="contest_publish"),
                InlineKeyboardButton("✏️ ИЗМЕНИТЬ", callback_data="contest_edit"),
                InlineKeyboardButton("❌ ОТМЕНА", callback_data="contest_cancel")
            )
            
            bot.send_message(
                message.chat.id,
                preview_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
    except Exception as e:
        logging.error(f"Ошибка в шаге {step}: {e}", exc_info=True)
        bot.send_message(message.chat.id, f"❌ Ошибка. Начните заново: /конкурс")
        if user_id in USER_CONTESTS:
            del USER_CONTESTS[user_id]

@bot.callback_query_handler(func=lambda call: call.data.startswith('contest_'))
def contest_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data == "contest_publish":
            if user_id not in USER_CONTESTS:
                bot.answer_callback_query(call.id, "❌ Данные утеряны", show_alert=True)
                return
            
            contest_data = USER_CONTESTS[user_id]["data"]
            
            required = ['channel_id', 'max_participants', 'winners_count', 'prizes_text']
            for field in required:
                if field not in contest_data:
                    bot.answer_callback_query(call.id, f"❌ Нет данных: {field}", show_alert=True)
                    return
            
            contest_id = f"contest_{user_id}_{int(time.time())}"
            
            try:
                bot_username = (bot.get_me()).username
                if not bot_username:
                    bot_username = "bot"
                
                participate_link = f"https://t.me/{bot_username}?start={contest_id}"
                
                post_text = f"""🎊 *КОНКУРС!* 🎊


*👥 Участников:* {contest_data.get('max_participants', 'N/A')}
*🏆 Победителей:* {contest_data.get('winners_count', 'N/A')}

*💰 ПРИЗОВОЙ ФОНД:*
{contest_data.get('prizes_text', 'N/A')}



*👤 Организатор:* {contest_data.get('creator_name', 'N/A')}"""
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎯 УЧАСТВОВАТЬ", url=participate_link))
                
                bot.send_message(
                    contest_data['channel_id'],
                    post_text,
                    parse_mode='Markdown',
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
                
                ACTIVE_CONTESTS[contest_id] = {
                    **contest_data,
                    "contest_id": contest_id,
                    "created_at": time.time(),
                    "status": "active",
                    "published": True
                }
                
                CONTEST_PARTICIPANTS[contest_id] = []
                
                bot.edit_message_text(
                    f"✅ *КОНКУРС ОПУБЛИКОВАН!*\n\n"
                    f"📢 Канал: {contest_data.get('channel_title', 'N/A')}\n"
                    f"👥 Участников: 0/{contest_data.get('max_participants', 'N/A')}\n"
                    f"🏆 Победителей: {contest_data.get('winners_count', 'N/A')}\n"
                    f"🔗 ID конкурса: `{contest_id}`\n\n"
                    f"*Команды управления:*\n"
                    f"`итоги {contest_id}` — Подвести итоги\n"
                    f"`участники {contest_id}` — Список участников\n"
                    f"`отмена {contest_id}` — Отменить конкурс",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✅ Опубликовано в канале!", show_alert=True)
                
                if user_id in USER_CONTESTS:
                    del USER_CONTESTS[user_id]
                
            except Exception as e:
                logging.error(f"Ошибка публикации: {e}")
                error_msg = str(e).lower()
                if "chat not found" in error_msg:
                    bot.answer_callback_query(call.id, "❌ Канал не найден", show_alert=True)
                elif "forbidden" in error_msg:
                    bot.answer_callback_query(call.id, "❌ Бот не может писать в канал", show_alert=True)
                elif "admin" in error_msg:
                    bot.answer_callback_query(call.id, "❌ Бот не админ канала", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:40]}", show_alert=True)
                return
            
        elif call.data == "contest_edit":
            if user_id in USER_CONTESTS:
                USER_CONTESTS[user_id]["step"] = 1
                
                bot.edit_message_text(
                    "✏️ *РЕДАКТИРОВАНИЕ*\n\n"
                    "Пришлите ID канала или @username:",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.answer_callback_query(call.id, "✏️ Редактирование...")
            else:
                bot.answer_callback_query(call.id, "❌ Данные утеряны", show_alert=True)
                
        elif call.data == "contest_cancel":
            if user_id in USER_CONTESTS:
                del USER_CONTESTS[user_id]
            
            try:
                bot.edit_message_text(
                    "❌ Создание отменено",
                    call.message.chat.id,
                    call.message.message_id
                )
            except:
                pass
            bot.answer_callback_query(call.id, "❌ Отменено")
            
    except Exception as e:
        logging.error(f"Ошибка в колбэке конкурса: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)
        except:
            pass

@bot.message_handler(func=lambda message: message.text.lower().startswith('итоги ') and is_admin(message.from_user.id))
def handle_contest_results(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: итоги ID_конкурса")
            return
        
        contest_id = parts[1].strip()
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден")
            return
        
        contest = ACTIVE_CONTESTS[contest_id]
        participants = CONTEST_PARTICIPANTS.get(contest_id, [])
        
        if len(participants) < contest.get('winners_count', 1):
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно участников!\n"
                           f"Нужно: {contest['winners_count']}\n"
                           f"Есть: {len(participants)}")
            return
        
        winners = random.sample(participants, contest['winners_count'])
        
        prizes_text = contest.get('prizes_text', '')
        prizes_list = parse_prizes_from_text(prizes_text, len(winners))
        
        winners_text = "🏆 *ПОБЕДИТЕЛИ И ПРИЗЫ:*\n\n"
        total_awarded = 0
        awards_given = 0
        awards_failed = 0
        
        for i, winner_id in enumerate(winners, 1):
            try:
                user = bot.get_chat(winner_id)
                username = f"@{user.username}" if user.username else user.first_name
                
                prize_amount = 0
                if i <= len(prizes_list):
                    prize_amount = prizes_list[i-1]
                
                if prize_amount > 0:
                    update_balance(winner_id, prize_amount)
                    total_awarded += prize_amount
                    awards_given += 1
                    
                    winners_text += f"{i}. {username} - ❄️{format_balance(prize_amount)}\n"
                    
                    try:
                        bot.send_message(
                            winner_id,
                            f"🎉 *ВЫ ВЫИГРАЛИ В КОНКУРСЕ!*\n\n"
                            f"🏆 Место: #{i}\n"
                            f"💰 Приз: ❄️{format_balance(prize_amount)}\n"
                            f"📢 Конкурс: {contest.get('channel_title', 'N/A')}\n\n"
                            f"🎰 Удачи в казино!",
                            parse_mode='Markdown'
                        )
                    except:
                        winners_text += " (не удалось уведомить)\n"
                        awards_failed += 1
                else:
                    winners_text += f"{i}. {username} - ❌ нет приза\n"
                    
            except Exception as e:
                logging.error(f"Ошибка начисления приза для {winner_id}: {e}")
                winners_text += f"{i}. ID: {winner_id} - ❌ ошибка начисления\n"
        
        winners_text += f"\n📊 Всего участников: {len(participants)}"
        winners_text += f"\n💰 Всего выдано: ❄️{format_balance(total_awarded)}"
        
        bot.send_message(message.chat.id, winners_text, parse_mode='Markdown')
        
        channel_post = f"""🎊 *ИТОГИ КОНКУРСА!* 🎊

{winners_text}

Поздравляем победителей! 🎉

👤 Организатор: {contest.get('creator_name', 'N/A')}"""
        
        try:
            bot.send_message(
                contest['channel_id'],
                channel_post,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Не удалось опубликовать в канале: {e}")
        
        ACTIVE_CONTESTS[contest_id]['status'] = 'finished'
        ACTIVE_CONTESTS[contest_id]['winners'] = winners
        ACTIVE_CONTESTS[contest_id]['prizes_awarded'] = prizes_list
        ACTIVE_CONTESTS[contest_id]['total_awarded'] = total_awarded
        
        report = f"✅ Итоги подведены!\n\n"
        report += f"📊 Статистика:\n"
        report += f"👥 Участников: {len(participants)}\n"
        report += f"🏆 Победителей: {len(winners)}\n"
        report += f"💰 Выдано призов: {awards_given}/{len(winners)}\n"
        report += f"💸 Общая сумма: ❄️{format_balance(total_awarded)}\n"
        report += f"⚠️ Не удалось уведомить: {awards_failed}"
        
        bot.send_message(message.chat.id, report)
        
    except Exception as e:
        logging.error(f"Ошибка итогов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower().startswith('участники ') and is_admin(message.from_user.id))
def handle_contest_participants(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: участники ID_конкурса")
            return
        
        contest_id = parts[1].strip()
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден")
            return
        
        participants = CONTEST_PARTICIPANTS.get(contest_id, [])
        
        if not participants:
            bot.send_message(message.chat.id, "📭 Участников пока нет")
            return
        
        text = f"👥 *УЧАСТНИКИ:* {len(participants)}\n\n"
        
        for i, user_id in enumerate(participants[:20], 1):
            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else user.first_name
                text += f"{i}. {username}\n"
            except:
                text += f"{i}. ID: {user_id}\n"
        
        if len(participants) > 20:
            text += f"\n... и ещё {len(participants) - 20}"
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка участников: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('отмена ') and is_admin(message.from_user.id))
def handle_contest_cancel(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: отмена ID_конкурса")
            return
        
        contest_id = parts[1].strip()
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден")
            return
        
        contest = ACTIVE_CONTESTS[contest_id]
        participants = len(CONTEST_PARTICIPANTS.get(contest_id, []))
        
        ACTIVE_CONTESTS[contest_id]['status'] = 'cancelled'
        
        try:
            bot.send_message(
                contest['channel_id'],
                f"❌ *КОНКУРС ОТМЕНЕН*\n\n"
                f"Конкурс был отменен организатором.\n"
                f"Участников было: {participants}",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            f"✅ Конкурс отменен\n"
            f"👥 Участников было: {participants}"
        )
        
    except Exception as e:
        logging.error(f"Ошибка отмены: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower() == 'моиконкурсы' and is_admin(message.from_user.id))
def handle_my_contests(message):
    try:
        user_id = message.from_user.id
        
        my_contests = []
        for contest_id, contest in ACTIVE_CONTESTS.items():
            if contest.get('creator_id') == user_id:
                participants = len(CONTEST_PARTICIPANTS.get(contest_id, []))
                my_contests.append((contest_id, contest, participants))
        
        if not my_contests:
            bot.send_message(message.chat.id, "📭 У вас нет активных конкурсов")
            return
        
        text = "🎯 *ВАШИ КОНКУРСЫ:*\n\n"
        
        for contest_id, contest, participants in my_contests:
            status = "✅" if contest.get('status') == 'active' else "🏁"
            text += f"{status} *{contest.get('channel_title', 'N/A')}*\n"
            text += f"ID: `{contest_id}`\n"
            text += f"Участников: {participants}/{contest.get('max_participants', 'N/A')}\n\n"
        
        text += "*Команды:*\n`итоги ID` `участники ID` `отмена ID`"
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка моих конкурсов: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

def cleanup_old_contests():
    while True:
        time.sleep(86400)
        current_time = time.time()
        
        to_remove = []
        for contest_id, contest in ACTIVE_CONTESTS.items():
            if contest.get('status') in ['finished', 'cancelled']:
                if current_time - contest.get('created_at', current_time) > 604800:
                    to_remove.append(contest_id)
        
        for contest_id in to_remove:
            try:
                del ACTIVE_CONTESTS[contest_id]
            except:
                pass
                
            try:
                del CONTEST_PARTICIPANTS[contest_id]
            except:
                pass
            
            logging.info(f"Удален старый конкурс: {contest_id}")

contest_cleanup_thread = threading.Thread(target=cleanup_old_contests, daemon=True)
contest_cleanup_thread.start()

@bot.message_handler(func=lambda message: message.text.lower() == 'конкурсы')
def handle_contests_info(message):
    info_text = """
🎯 *СИСТЕМА КОНКУРСОВ*

*Для организаторов (админов):*
`конкурс` — Создать новый конкурс
`моиконкурсы` — Ваши конкурсы

*Команды управления:*
`итоги ID_конкурса` — Подвести итоги
`участники ID_конкурса` — Список участников
`отмена ID_конкурса` — Отменить конкурс

*Как участвовать:*
1. Найдите пост конкурса в канале
2. Нажмите кнопку "🎯 УЧАСТВОВАТЬ"
3. Подпишитесь на канал если требуется
4. Ждите результатов!

*Примечание:*
• Бот должен быть администратором канала
• Конкурс автоматически завершается после подведения итогов
"""
    
    bot.send_message(message.chat.id, info_text, parse_mode='Markdown')

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
                
                if user_id in pending_ref_codes:
                    ref_code = pending_ref_codes[user_id]
                    del pending_ref_codes[user_id]
                    
                    username = message.from_user.username
                    first_name = message.from_user.first_name
                    process_ref_or_check(user_id, username, first_name, ref_code)
                
                markup = create_main_menu(message.chat.id)
                bot.send_message(message.chat.id, "✅ Капча пройдена! Добро пожаловать!", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ Неверный ответ. Попробуйте снова.\nОтправьте /start")
                del user_captcha_status[user_id]
        
    except Exception as e:
        logging.error(f"Ошибка обработки капчи: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка. Попробуйте /start")

init_db()

if __name__ == "__main__":
    logging.info("Бот запускается...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)