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

BOT_TOKEN = "8372072540:AAEiyq2kaJmHTTt_RFkod6EsUJNbuAB5Tvg"

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
        
        # === ОСНОВНАЯ ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ ===
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
            mining_trees INTEGER DEFAULT 0,
            mining_balance INTEGER DEFAULT 0
        )
        ''')
        
        # === ТАБЛИЦА ЧЕКОВ ===
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
        
        # === ТАБЛИЦА АКТИВАЦИЙ ЧЕКОВ ===
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
        
        # === ТАБЛИЦА ДОМОВ ПОЛЬЗОВАТЕЛЕЙ ===
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
        
        # === ТАБЛИЦА РЕФЕРАЛЬНЫХ БОНУСОВ ===
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
        
        # === ТАБЛИЦА КОНКУРСОВ ===
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
        
        # === ТАБЛИЦА УЧАСТНИКОВ КОНКУРСОВ ===
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
        
        # === ТАБЛИЦА МАЙНИНГ СТАТИСТИКИ ===
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS mining_stats (
            user_id INTEGER PRIMARY KEY,
            total_mined INTEGER DEFAULT 0,
            total_exchanged INTEGER DEFAULT 0,
            last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # === ТАБЛИЦЫ ДЛЯ РЫНКА ID ===
        
        # Таблица владения ID
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_ownership (
            id_number INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            price_paid INTEGER DEFAULT 0,
            FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица продаж ID
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            id_number INTEGER NOT NULL,
            price INTEGER NOT NULL,
            listed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (seller_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица предложений на покупку
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_offers (
            offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            id_number INTEGER NOT NULL,
            price INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица истории сделок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            id_number INTEGER NOT NULL,
            price INTEGER NOT NULL,
            sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (buyer_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # === ИНДЕКСЫ ДЛЯ БЫСТРОГО ПОИСКА ===
        
        # Индексы для users
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_registered_at ON users(registered_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_mining_balance ON users(mining_balance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_mining_trees ON users(mining_trees)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_last_mining_collect ON users(last_mining_collect)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_video_cards ON users(video_cards)')
        
        # Индексы для checks
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_checks_code ON checks(code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_checks_created_by ON checks(created_by)')
        
        # Индексы для домов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_houses_user ON user_houses(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_houses_current ON user_houses(is_current)')
        
        # Индексы для рефералов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_wins_referrer ON referral_wins(referrer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_wins_created ON referral_wins(created_at)')
        
        # Индексы для конкурсов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_creator ON contests(creator_id)')
        
        # Индексы для рынка ID
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_ownership_owner ON id_ownership(owner_id)')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_sales_status ON id_sales(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_sales_id_number ON id_sales(id_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_sales_seller ON id_sales(seller_id)')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_offers_buyer ON id_offers(buyer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_offers_owner ON id_offers(owner_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_offers_status ON id_offers(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_offers_id_number ON id_offers(id_number)')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_history_sold ON id_history(sold_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_history_buyer ON id_history(buyer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_history_seller ON id_history(seller_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_history_id_number ON id_history(id_number)')
        
        conn.commit()
        logging.info("✅ База данных успешно инициализирована")
        
        # === ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ ID ===
        init_id_system()
        
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
            'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc, mining_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp(), 0)
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
                        f"💰 На вкладе: 🌸{format_balance(bank_deposit)}\n"
                        f"📈 Начислено: +🌸{format_balance(interest)}\n"
                        f"⏰ Проценты начисляются каждый час",
                        parse_mode='Markdown'
                    )
                    logging.info(f"Пользователю {user_id} начислены проценты: {interest}🌸")
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
            KeyboardButton("Я", color="#4A90E2"),           # Синий (личный профиль)
            KeyboardButton("Майнинг", color="#8B4513"),     # Тёмно-коричневый (земля/руда)
            KeyboardButton("Банк", color="#FFD700"),        # Золотой (деньги)
            KeyboardButton("Игры", color="#FF4500"),        # Оранжево-красный (активный/азарт)
            KeyboardButton("Работа", color="#2E8B57"),      # Зелёный (зарплата/рост)
            KeyboardButton("Топ снежков", color="#00BFFF"), # Голубой (снег/лёд)
            KeyboardButton("🏠 Дом", color="#D2691E"),       # Оранжево-коричневый (дерево/уют)
            KeyboardButton("Бонус", color="#FF1493"),       # Глубокий розовый (подарок/радость)
            KeyboardButton("🎭 Рынок ID", color="#9400D3")   # Тёмно-фиолетовый (редкость/элита)
        )
    else:
        markup.add(
            KeyboardButton("Баланс", color="#2E8B57"),      # Зелёный (деньги/рост)
            KeyboardButton("Топ снежков", color="#00BFFF"), # Голубой (снег)
            KeyboardButton("Бонус", color="#FF1493")        # Розовый (подарок)
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
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        # Получаем параметр из ссылки
        start_param = None
        if len(message.text.split()) > 1:
            start_param = message.text.split()[1].strip()
            logging.info(f"Пользователь {user_id} пришел по ссылке с параметром: {start_param}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            is_new_user = True
            
            # Обработка реферальной ссылки для нового пользователя
            if start_param and start_param.startswith('ref'):
                pending_ref_codes[user_id] = start_param
                logging.info(f"Сохранен реф-код для нового пользователя {user_id}: {start_param}")
            
            referral_code = f"ref{user_id}"
            
            cursor.execute(
                'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc, mining_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp(), 0)
            )
            conn.commit()
            
            # Капча для нового пользователя
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для регистрации решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        # ====== ОБРАБОТКА КОНКУРСОВ ======
        # Проверяем, не пришел ли пользователь по ссылке конкурса
        if start_param and start_param.startswith('contest_'):
            try:
                contest_id = start_param
                logging.info(f"Пользователь {user_id} перешел по ссылке конкурса: {contest_id}")
                
                # Проверяем существование конкурса
                if contest_id in ACTIVE_CONTESTS:
                    contest = ACTIVE_CONTESTS[contest_id]
                    
                    # Проверяем статус конкурса
                    if contest.get('status') != 'active':
                        if contest.get('status') == 'finished':
                            bot.send_message(message.chat.id, "❌ Конкурс уже завершен")
                        elif contest.get('status') == 'cancelled':
                            bot.send_message(message.chat.id, "❌ Конкурс отменен")
                    else:
                        # Проверяем лимит участников
                        participants = CONTEST_PARTICIPANTS.get(contest_id, [])
                        max_participants = contest.get('max_participants', 100)
                        
                        if len(participants) >= max_participants:
                            bot.send_message(message.chat.id, 
                                           f"❌ Конкурс уже набрал максимальное количество участников: {max_participants}")
                        elif user_id in participants:
                            bot.send_message(message.chat.id, "✅ Вы уже участвуете в этом конкурсе!")
                        else:
                            # Добавляем участника
                            CONTEST_PARTICIPANTS.setdefault(contest_id, []).append(user_id)
                            
                            # Получаем информацию о канале
                            channel_id = contest.get('channel_id')
                            channel_title = contest.get('channel_title', 'Канал')
                            
                            # Проверяем подписку на канал (если нужно)
                            try:
                                if channel_id:
                                    member = bot.get_chat_member(channel_id, user_id)
                                    if member.status in ['member', 'administrator', 'creator']:
                                        subscribed = True
                                    else:
                                        subscribed = False
                                else:
                                    subscribed = True
                            except:
                                subscribed = False
                            
                            if subscribed:
                                # Успешное участие
                                participants_count = len(CONTEST_PARTICIPANTS.get(contest_id, []))
                                
                                bot.send_message(
                                    message.chat.id,
                                    f"🎉 *ВЫ УЧАСТВУЕТЕ В КОНКУРСЕ!*\n\n"
                                    f"📢 Канал: {channel_title}\n"
                                    f"👥 Участников: {participants_count}/{max_participants}\n"
                                    f"🏆 Победителей: {contest.get('winners_count', 1)}\n\n"
                                    f"💡 Результаты будут объявлены позже!\n"
                                    f"Удачи! 🍀",
                                    parse_mode='Markdown'
                                )
                                
                                # Уведомление организатору
                                try:
                                    creator_id = contest.get('creator_id')
                                    if creator_id:
                                        bot.send_message(
                                            creator_id,
                                            f"📈 *НОВЫЙ УЧАСТНИК КОНКУРСА!*\n\n"
                                            f"📢 {channel_title}\n"
                                            f"👤 ID: {user_id}\n"
                                            f"👥 Всего участников: {participants_count}/{max_participants}",
                                            parse_mode='Markdown'
                                        )
                                except:
                                    pass
                                
                                logging.info(f"Пользователь {user_id} добавлен в конкурс {contest_id}")
                            else:
                                # Требуется подписка
                                markup = InlineKeyboardMarkup()
                                markup.add(
                                    InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{channel_title}"),
                                    InlineKeyboardButton("🔄 Проверить подписку", callback_data=f"check_contest_sub_{contest_id}")
                                )
                                
                                bot.send_message(
                                    message.chat.id,
                                    f"📢 *Для участия в конкурсе*\n\n"
                                    f"Необходимо подписаться на канал:\n"
                                    f"{channel_title}\n\n"
                                    f"После подписки нажмите '🔄 Проверить'",
                                    reply_markup=markup,
                                    parse_mode='Markdown'
                                )
                else:
                    bot.send_message(message.chat.id, "❌ Конкурс не найден или завершен")
                
                # Независимо от результата с конкурсом, продолжаем обычный старт
                
            except Exception as e:
                logging.error(f"Ошибка обработки конкурса: {e}")
                # Продолжаем обычный старт даже при ошибке
        
        # ====== ОБЫЧНАЯ ОБРАБОТКА СТАРТА ======
        
        captcha_passed = user_data[0]
        
        if captcha_passed == 0:
            # Капча для существующего пользователя
            if start_param and start_param.startswith('ref'):
                pending_ref_codes[user_id] = start_param
                logging.info(f"Сохранен реф-код для существующего пользователя {user_id}: {start_param}")
            
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для доступа к боту решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        conn.close()
        
        # Обработка реферальной ссылки или чека
        if start_param:
            if start_param.startswith('contest_'):
                # Уже обработали выше, ничего не делаем
                pass
            else:
                process_ref_or_check(user_id, username, first_name, start_param)
        
        markup = create_main_menu(message.chat.id)
        
        if message.chat.id > 0:
            welcome_text = "✨ Добро пожаловать! ✨\n\nВыберите действие из меню ниже:"
        else:
            welcome_text = f"👋 Привет, {first_name}!\n\nИспользуйте меню ниже для работы с ботом в этом чате.\n\n💡 Для полного функционала напишите мне в ЛС!"
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')
    
    except Exception as e:
        logging.error(f"Ошибка в start: {e}", exc_info=True)
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте снова позже.")


# === ПОЛНОСТЬЮ ПЕРЕПИСАННЫЙ РЫНОК ID (БЕЗ БАГОВ) ===

def init_id_system():
    """Инициализация системы ID при запуске бота"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Таблица владения ID
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_ownership (
            id_number INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            price_paid INTEGER DEFAULT 0,
            FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица продаж
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            id_number INTEGER NOT NULL,
            price INTEGER NOT NULL,
            listed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (seller_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица предложений
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_offers (
            offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            id_number INTEGER NOT NULL,
            price INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица истории
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            id_number INTEGER NOT NULL,
            price INTEGER NOT NULL,
            sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (buyer_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Получаем всех пользователей
        cursor.execute('''
        SELECT user_id FROM users 
        WHERE is_banned = 0 
        ORDER BY registered_at ASC
        ''')
        
        all_users = cursor.fetchall()
        
        # Инициализируем владельцев
        for i, (user_id,) in enumerate(all_users, 1):
            cursor.execute('INSERT OR IGNORE INTO id_ownership (id_number, owner_id) VALUES (?, ?)', 
                          (i, user_id))
        
        conn.commit()
        conn.close()
        logging.info("✅ Система ID инициализирована")
        
    except Exception as e:
        logging.error(f"Ошибка инициализации ID: {e}")

# Вызываем после init_db()
init_id_system()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def get_user_id_number(user_id):
    """Номер ID пользователя"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_banned = 0 ORDER BY registered_at ASC')
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users.index(user_id) + 1 if user_id in users else 0
    except:
        return 0

def get_id_owner(id_number):
    """Владелец ID"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT owner_id FROM id_ownership WHERE id_number = ?', (id_number,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except:
        return None

def transfer_id(id_number, new_owner_id, price=0):
    """Передать ID новому владельцу"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE id_ownership 
            SET owner_id = ?, purchased_at = CURRENT_TIMESTAMP, price_paid = ?
            WHERE id_number = ?
        ''', (new_owner_id, price, id_number))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка передачи ID: {e}")
        return False

def format_id_card(id_number):
    """Красивое отображение ID"""
    owner_id = get_id_owner(id_number)
    
    # Редкость ID
    if id_number == 1:
        rank = "👑 ЛЕГЕНДАРНЫЙ"
    elif id_number <= 3:
        rank = "👑 ОСНОВАТЕЛЬ"
    elif id_number <= 10:
        rank = "⭐ ТОП-10"
    elif id_number <= 50:
        rank = "✨ ТОП-50"
    elif id_number <= 100:
        rank = "🔹 ТОП-100"
    elif id_number <= 500:
        rank = "🟢 ТОП-500"
    else:
        rank = "🔸 ОБЫЧНЫЙ"
    
    # Инфо о владельце
    if owner_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT nickname, username, first_name FROM users WHERE user_id = ?', (owner_id,))
        data = cursor.fetchone()
        conn.close()
        
        if data and data[0]:
            owner_name = data[0]
        elif data and data[1]:
            owner_name = f"@{data[1]}"
        elif data:
            owner_name = data[2]
        else:
            owner_name = f"ID: {owner_id}"
    else:
        owner_name = "Свободен"
    
    return f"""
┌─────────────────────┐
│ 🎯 ID #{id_number:<6} {rank:14} │
│ 👤 Владелец: {owner_name[:20]:20} │
└─────────────────────┘"""

# === ЦВЕТНЫЕ МЕНЮ ===

def create_main_menu():
    """Главное меню с цветными кнопками"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("👤 ПРОФИЛЬ", color="#4A90E2"),
        KeyboardButton("⛏ МАЙНИНГ", color="#964B00"),
        KeyboardButton("🏦 БАНК", color="#F4C430"),
        KeyboardButton("🎮 ИГРЫ", color="#FF6B6B"),
        KeyboardButton("💼 РАБОТА", color="#6A5ACD"),
        KeyboardButton("🏆 ТОП", color="#FFA500"),
        KeyboardButton("🏠 ДОМ", color="#8B4513"),
        KeyboardButton("🎁 БОНУС", color="#FF69B4"),
        KeyboardButton("🏪 РЫНОК ID", color="#9370DB")
    )
    return markup

def create_id_market_menu():
    """Меню рынка ID с цветными кнопками"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("🟢 КУПИТЬ ID", color="#00FF00"),
        KeyboardButton("🔴 ПРОДАТЬ ID", color="#FF4444"),
        KeyboardButton("🔵 МОИ ID", color="#4444FF"),
        KeyboardButton("🟡 ПРЕДЛОЖЕНИЯ", color="#FFD700"),
        KeyboardButton("🏪 ВСЕ ПРОДАЖИ", color="#9370DB"),
        KeyboardButton("📊 МОЯ СТАТИСТИКА", color="#50C878"),
        KeyboardButton("❓ ПОМОЩЬ", color="#808080"),
        KeyboardButton("◀️ НАЗАД", color="#A9A9A9")
    )
    return markup

# === ОСНОВНОЙ ОБРАБОТЧИК РЫНКА ===

@bot.message_handler(func=lambda message: message.text == "🏪 РЫНОК ID")
def handle_id_market(message):
    """Главное меню рынка"""
    user_id = message.from_user.id
    user_id_num = get_user_id_number(user_id)
    
    # Статистика
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM id_sales WHERE status = "active"')
    sales_count = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT COUNT(*) FROM id_offers 
        WHERE owner_id = ? AND status = "pending"
    ''', (user_id,))
    offers_count = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"""
🎭 *МИНИМАЛИСТИЧНЫЙ РЫНОК ID* 🎭

┌─────────────────────┐
│ 👤 Твой ID: #{user_id_num:<14} │
│ 📦 Продаж: {sales_count:<5} 📨 Запросов: {offers_count:<5} │
└─────────────────────┘

🟢 Купить ID — `идкуп (номер)`
🔴 Продать ID — `идпрод (сумма)`
🟡 Предложить — `идпред (номер) (сумма)`

💡 *Выбери действие кнопкой ниже:*
    """
    
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=create_id_market_menu(),
        parse_mode='Markdown'
    )

# === ПРОДАЖА ID ===

@bot.message_handler(func=lambda message: message.text == "🔴 ПРОДАТЬ ID")
def handle_sell_button(message):
    bot.send_message(
        message.chat.id,
        "💰 *Введи цену продажи*\n\n"
        "Пример: `идпрод 1кк`\n"
        "• Минимум: 1.000🌸\n"
        "• Можно использовать: к, кк, ккк",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text.lower().startswith('идпрод '))
def handle_id_sell(message):
    """Продажа ID"""
    try:
        user_id = message.from_user.id
        
        # Проверка бана
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        # Парсим сумму
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: `идпрод (сумма)`")
            return
        
        price = parse_bet_amount(' '.join(parts[1:]), float('inf'))
        if not price or price < 1000:
            bot.send_message(message.chat.id, "❌ Минимальная цена: 1.000🌸")
            return
        
        # Получаем ID пользователя
        user_id_num = get_user_id_number(user_id)
        if user_id_num == 0:
            bot.send_message(message.chat.id, "❌ Ошибка: ID не найден")
            return
        
        # Проверяем владельца
        current_owner = get_id_owner(user_id_num)
        if current_owner != user_id:
            bot.send_message(message.chat.id, "❌ Ты не владелец этого ID")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем активную продажу
        cursor.execute('''
            SELECT sale_id FROM id_sales 
            WHERE id_number = ? AND status = 'active'
        ''', (user_id_num,))
        
        if cursor.fetchone():
            bot.send_message(message.chat.id, 
                           "❌ Уже продается!\nОтмени: `идоtmена`",
                           parse_mode='Markdown')
            conn.close()
            return
        
        # Создаем продажу
        cursor.execute('''
            INSERT INTO id_sales (seller_id, id_number, price)
            VALUES (?, ?, ?)
        ''', (user_id, user_id_num, price))
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ *ID ВЫСТАВЛЕН НА ПРОДАЖУ*\n\n"
            f"{format_id_card(user_id_num)}\n"
            f"💰 Цена: {format_balance(price)}🌸\n\n"
            f"💡 Купить: `идкуп {user_id_num}`",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка продажи: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при продаже")

# === ПОКУПКА ID ===

@bot.message_handler(func=lambda message: message.text == "🟢 КУПИТЬ ID")
def handle_buy_button(message):
    bot.send_message(
        message.chat.id,
        "🎯 *Введи номер ID для покупки*\n\n"
        "Пример: `идкуп 42`\n"
        "• Посмотреть все: `идрынок`",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text.lower().startswith('идкуп '))
def handle_id_buy(message):
    """Покупка ID"""
    try:
        user_id = message.from_user.id
        
        # Проверка бана
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        # Парсим номер ID
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: `идкуп (номер)`")
            return
        
        try:
            target_id = int(parts[1])
        except:
            bot.send_message(message.chat.id, "❌ Номер должен быть числом")
            return
        
        if target_id < 1:
            bot.send_message(message.chat.id, "❌ Неверный номер")
            return
        
        # Свой ID не покупаем
        user_own_id = get_user_id_number(user_id)
        if user_own_id == target_id:
            bot.send_message(message.chat.id, "❌ Это твой ID")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ищем продажу
        cursor.execute('''
            SELECT sale_id, seller_id, price FROM id_sales 
            WHERE id_number = ? AND status = 'active'
            ORDER BY listed_at DESC LIMIT 1
        ''', (target_id,))
        
        sale = cursor.fetchone()
        
        if not sale:
            bot.send_message(
                message.chat.id,
                f"❌ ID #{target_id} не продается\n"
                f"💡 Предложи цену: `идпред {target_id} (сумма)`",
                parse_mode='Markdown'
            )
            conn.close()
            return
        
        sale_id, seller_id, price = sale
        
        # Проверяем владельца
        current_owner = get_id_owner(target_id)
        if current_owner != seller_id:
            # Авто-очистка
            cursor.execute('UPDATE id_sales SET status = "cancelled" WHERE sale_id = ?', (sale_id,))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, "❌ Эта продажа устарела")
            return
        
        # Проверяем баланс
        balance = get_balance(user_id)
        if balance < price:
            bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств!\n"
                f"💰 Нужно: {format_balance(price)}🌸\n"
                f"💳 У вас: {format_balance(balance)}🌸"
            )
            conn.close()
            return
        
        # Транзакция
        cursor.execute('BEGIN IMMEDIATE')
        
        try:
            # Списываем у покупателя
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (price, user_id))
            
            # Начисляем продавцу
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (price, seller_id))
            
            # Помечаем продажу
            cursor.execute('UPDATE id_sales SET status = "sold" WHERE sale_id = ?', (sale_id,))
            
            # История
            cursor.execute('''
                INSERT INTO id_history (seller_id, buyer_id, id_number, price)
                VALUES (?, ?, ?, ?)
            ''', (seller_id, user_id, target_id, price))
            
            # Передаем ID
            cursor.execute('''
                UPDATE id_ownership SET owner_id = ?, purchased_at = CURRENT_TIMESTAMP, price_paid = ?
                WHERE id_number = ?
            ''', (user_id, price, target_id))
            
            conn.commit()
            
            # Новый баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance = cursor.fetchone()[0]
            
            conn.close()
            
            # Уведомления
            bot.send_message(
                message.chat.id,
                f"✅ *ПОКУПКА УСПЕШНА!*\n\n"
                f"{format_id_card(target_id)}\n"
                f"💰 Цена: {format_balance(price)}🌸\n"
                f"💳 Баланс: {format_balance(new_balance)}🌸",
                parse_mode='Markdown'
            )
            
            try:
                bot.send_message(
                    seller_id,
                    f"💰 *ID ПРОДАН!*\n\n"
                    f"{format_id_card(target_id)}\n"
                    f"💰 Цена: {format_balance(price)}🌸\n"
                    f"👤 Покупатель: ID {get_user_id_number(user_id)}",
                    parse_mode='Markdown'
                )
            except:
                pass
            
        except Exception as e:
            cursor.execute('ROLLBACK')
            conn.close()
            logging.error(f"Ошибка транзакции: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка при покупке")
        
    except Exception as e:
        logging.error(f"Ошибка покупки: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при покупке")

# === ПРЕДЛОЖЕНИЕ ===

@bot.message_handler(func=lambda message: message.text == "🟡 ПРЕДЛОЖЕНИЯ")
def handle_offers_button(message):
    bot.send_message(
        message.chat.id,
        "💡 *Введи предложение*\n\n"
        "Формат: `идпред (номер) (сумма)`\n"
        "Пример: `идпред 42 500к`",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text.lower().startswith('идпред '))
def handle_id_offer(message):
    """Предложение цены"""
    try:
        user_id = message.from_user.id
        
        # Проверка бана
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Формат: `идпред (номер) (сумма)`")
            return
        
        try:
            target_id = int(parts[1])
        except:
            bot.send_message(message.chat.id, "❌ Номер должен быть числом")
            return
        
        price = parse_bet_amount(' '.join(parts[2:]), float('inf'))
        if not price or price < 1000:
            bot.send_message(message.chat.id, "❌ Минимальная сумма: 1.000🌸")
            return
        
        if target_id < 1:
            bot.send_message(message.chat.id, "❌ Неверный номер")
            return
        
        # Свой ID
        user_own_id = get_user_id_number(user_id)
        if user_own_id == target_id:
            bot.send_message(message.chat.id, "❌ Нельзя предлагать за свой ID")
            return
        
        # Владелец
        owner_id = get_id_owner(target_id)
        if not owner_id:
            bot.send_message(message.chat.id, f"❌ ID #{target_id} не существует")
            return
        
        if owner_id == user_id:
            bot.send_message(message.chat.id, "❌ Это твой ID")
            return
        
        # Проверяем баланс
        balance = get_balance(user_id)
        if balance < price:
            bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств!\n"
                f"💰 Нужно: {format_balance(price)}🌸\n"
                f"💳 У вас: {format_balance(balance)}🌸"
            )
            return
        
        # Проверяем активную продажу
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT sale_id FROM id_sales 
            WHERE id_number = ? AND status = 'active'
        ''', (target_id,))
        
        if cursor.fetchone():
            bot.send_message(
                message.chat.id,
                f"❌ ID #{target_id} уже в продаже\n"
                f"💡 Просто купи: `идкуп {target_id}`",
                parse_mode='Markdown'
            )
            conn.close()
            return
        
        # Проверяем активное предложение
        cursor.execute('''
            SELECT offer_id FROM id_offers 
            WHERE buyer_id = ? AND id_number = ? AND status = 'pending'
        ''', (user_id, target_id))
        
        if cursor.fetchone():
            bot.send_message(message.chat.id, "❌ У тебя уже есть активное предложение")
            conn.close()
            return
        
        # Блокируем средства
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (price, user_id))
        
        # Создаем предложение
        cursor.execute('''
            INSERT INTO id_offers (buyer_id, owner_id, id_number, price)
            VALUES (?, ?, ?, ?)
        ''', (user_id, owner_id, target_id, price))
        
        offer_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Уведомления
        buyer_num = get_user_id_number(user_id)
        
        try:
            bot.send_message(
                owner_id,
                f"📨 *НОВОЕ ПРЕДЛОЖЕНИЕ!*\n\n"
                f"🎯 ID: #{target_id}\n"
                f"👤 Покупатель: ID #{buyer_num}\n"
                f"💰 Сумма: {format_balance(price)}🌸\n\n"
                f"✅ Принять: `идпринять {offer_id}`\n"
                f"❌ Отклонить: `идотклонить {offer_id}`",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            f"✅ *ПРЕДЛОЖЕНИЕ ОТПРАВЛЕНО!*\n\n"
            f"🎯 ID: #{target_id}\n"
            f"💰 Сумма: {format_balance(price)}🌸\n"
            f"👤 Владелец: ID #{get_user_id_number(owner_id)}\n\n"
            f"💸 Средства заморожены\n"
            f"⏳ Ожидай решения",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка предложения: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ПРИНЯТЬ ПРЕДЛОЖЕНИЕ ===

@bot.message_handler(func=lambda message: message.text.lower().startswith('идпринять '))
def handle_id_accept(message):
    """Принять предложение"""
    try:
        user_id = message.from_user.id
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: `идпринять (номер)`")
            return
        
        try:
            offer_id = int(parts[1])
        except:
            bot.send_message(message.chat.id, "❌ Неверный номер")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем предложение
        cursor.execute('''
            SELECT buyer_id, owner_id, id_number, price, status 
            FROM id_offers WHERE offer_id = ?
        ''', (offer_id,))
        
        offer = cursor.fetchone()
        
        if not offer:
            bot.send_message(message.chat.id, "❌ Предложение не найдено")
            conn.close()
            return
        
        buyer_id, owner_id, id_number, price, status = offer
        
        # Проверка владельца
        if owner_id != user_id:
            bot.send_message(message.chat.id, "❌ Это не твое предложение")
            conn.close()
            return
        
        if status != 'pending':
            bot.send_message(message.chat.id, "❌ На это предложение уже ответили")
            conn.close()
            return
        
        # Проверка владения ID
        current_owner = get_id_owner(id_number)
        if current_owner != user_id:
            bot.send_message(
                message.chat.id,
                f"❌ Ты больше не владелец ID #{id_number}\n"
                f"Предложение автоматически отменено"
            )
            cursor.execute('UPDATE id_offers SET status = "cancelled" WHERE offer_id = ?', (offer_id,))
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (price, buyer_id))
            conn.commit()
            conn.close()
            return
        
        # Проверка покупателя
        buyer_banned, _ = is_banned(buyer_id)
        if buyer_banned:
            bot.send_message(message.chat.id, "❌ Покупатель забанен")
            cursor.execute('UPDATE id_offers SET status = "cancelled" WHERE offer_id = ?', (offer_id,))
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (price, buyer_id))
            conn.commit()
            conn.close()
            return
        
        # Транзакция
        cursor.execute('BEGIN IMMEDIATE')
        
        try:
            # Начисляем продавцу
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (price, user_id))
            
            # История
            cursor.execute('''
                INSERT INTO id_history (seller_id, buyer_id, id_number, price)
                VALUES (?, ?, ?, ?)
            ''', (user_id, buyer_id, id_number, price))
            
            # Обновляем оффер
            cursor.execute('UPDATE id_offers SET status = "accepted" WHERE offer_id = ?', (offer_id,))
            
            # Отменяем продажу если была
            cursor.execute('''
                UPDATE id_sales SET status = "cancelled" 
                WHERE id_number = ? AND status = 'active'
            ''', (id_number,))
            
            # Передаем ID
            cursor.execute('''
                UPDATE id_ownership SET owner_id = ?, purchased_at = CURRENT_TIMESTAMP, price_paid = ?
                WHERE id_number = ?
            ''', (buyer_id, price, id_number))
            
            conn.commit()
            
            # Новый баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance = cursor.fetchone()[0]
            
            conn.close()
            
            # Уведомления
            bot.send_message(
                message.chat.id,
                f"✅ *ТЫ ПРИНЯЛ ПРЕДЛОЖЕНИЕ!*\n\n"
                f"{format_id_card(id_number)}\n"
                f"💰 Сумма: {format_balance(price)}🌸\n"
                f"💳 Новый баланс: {format_balance(new_balance)}🌸",
                parse_mode='Markdown'
            )
            
            try:
                bot.send_message(
                    buyer_id,
                    f"✅ *ТВОЕ ПРЕДЛОЖЕНИЕ ПРИНЯТО!*\n\n"
                    f"{format_id_card(id_number)}\n"
                    f"💰 Сумма: {format_balance(price)}🌸",
                    parse_mode='Markdown'
                )
            except:
                pass
            
        except Exception as e:
            cursor.execute('ROLLBACK')
            conn.close()
            logging.error(f"Ошибка транзакции: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")
        
    except Exception as e:
        logging.error(f"Ошибка принятия: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОТКЛОНИТЬ ПРЕДЛОЖЕНИЕ ===

@bot.message_handler(func=lambda message: message.text.lower().startswith('идотклонить '))
def handle_id_reject(message):
    """Отклонить предложение"""
    try:
        user_id = message.from_user.id
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: `идотклонить (номер)`")
            return
        
        try:
            offer_id = int(parts[1])
        except:
            bot.send_message(message.chat.id, "❌ Неверный номер")
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем предложение
        cursor.execute('''
            SELECT buyer_id, owner_id, price, status 
            FROM id_offers WHERE offer_id = ?
        ''', (offer_id,))
        
        offer = cursor.fetchone()
        
        if not offer:
            bot.send_message(message.chat.id, "❌ Предложение не найдено")
            conn.close()
            return
        
        buyer_id, owner_id, price, status = offer
        
        # Проверка владельца
        if owner_id != user_id:
            bot.send_message(message.chat.id, "❌ Это не твое предложение")
            conn.close()
            return
        
        if status != 'pending':
            bot.send_message(message.chat.id, "❌ На это предложение уже ответили")
            conn.close()
            return
        
        # Транзакция
        cursor.execute('BEGIN IMMEDIATE')
        
        try:
            # Возвращаем деньги
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (price, buyer_id))
            
            # Обновляем статус
            cursor.execute('UPDATE id_offers SET status = "rejected" WHERE offer_id = ?', (offer_id,))
            
            conn.commit()
            conn.close()
            
            # Уведомления
            bot.send_message(
                message.chat.id,
                f"❌ *ТЫ ОТКЛОНИЛ ПРЕДЛОЖЕНИЕ*\n\n"
                f"💰 Сумма: {format_balance(price)}🌸\n"
                f"💸 Деньги возвращены покупателю",
                parse_mode='Markdown'
            )
            
            try:
                bot.send_message(
                    buyer_id,
                    f"❌ *ТВОЕ ПРЕДЛОЖЕНИЕ ОТКЛОНЕНО*\n\n"
                    f"💰 Сумма: {format_balance(price)}🌸\n"
                    f"💸 Деньги возвращены",
                    parse_mode='Markdown'
                )
            except:
                pass
            
        except Exception as e:
            cursor.execute('ROLLBACK')
            conn.close()
            logging.error(f"Ошибка транзакции: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")
        
    except Exception as e:
        logging.error(f"Ошибка отклонения: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# === МОИ ID ===

@bot.message_handler(func=lambda message: message.text == "🔵 МОИ ID")
def handle_my_id(message):
    """Мои ID и предложения"""
    user_id = message.from_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Мой ID номер
    my_id_num = get_user_id_number(user_id)
    
    # Мои ID (которыми владею)
    cursor.execute('''
        SELECT id_number, price_paid, purchased_at FROM id_ownership 
        WHERE owner_id = ?
        ORDER BY id_number ASC
    ''', (user_id,))
    
    my_ids = cursor.fetchall()
    
    # Входящие предложения
    cursor.execute('''
        SELECT offer_id, id_number, price, buyer_id 
        FROM id_offers 
        WHERE owner_id = ? AND status = 'pending'
        ORDER BY created_at DESC
    ''', (user_id,))
    
    incoming = cursor.fetchall()
    
    # Исходящие предложения
    cursor.execute('''
        SELECT offer_id, id_number, price, status, owner_id 
        FROM id_offers 
        WHERE buyer_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    ''', (user_id,))
    
    outgoing = cursor.fetchall()
    
    conn.close()
    
    text = f"📦 *МОИ ID*\n\n"
    text += f"👤 Твой ID номер: #{my_id_num}\n\n"
    
    if my_ids:
        text += "🔹 *Владею:*\n"
        for id_num, price, date in my_ids[:5]:
            if id_num == my_id_num:
                text += f"  👑 #{id_num} (родной)\n"
            else:
                price_text = f"за {format_balance(price)}🌸" if price else ""
                text += f"  🎯 #{id_num} {price_text}\n"
        text += "\n"
    
    if incoming:
        text += "📨 *Входящие предложения:*\n"
        for off_id, id_num, price, buyer_id in incoming:
            buyer_num = get_user_id_number(buyer_id)
            text += f"  • #{off_id}: ID{id_num} — {format_balance(price)}🌸 от #{buyer_num}\n"
            text += f"    ✅ `идпринять {off_id}` ❌ `идотклонить {off_id}`\n"
        text += "\n"
    
    if outgoing:
        text += "📤 *Исходящие предложения:*\n"
        for off_id, id_num, price, status, owner_id in outgoing:
            status_emoji = "⏳" if status == "pending" else "✅" if status == "accepted" else "❌"
            owner_num = get_user_id_number(owner_id)
            text += f"  {status_emoji} #{off_id}: ID{id_num} — {format_balance(price)}🌸 владельцу #{owner_num}\n"
    
    if not my_ids and not incoming and not outgoing:
        text += "У тебя пока нет ID и предложений\n\n"
        text += "💡 Купи ID: `идкуп (номер)`\n"
        text += "💡 Продай свой: `идпрод (сумма)`"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# === ВСЕ ПРОДАЖИ ===

@bot.message_handler(func=lambda message: message.text == "🏪 ВСЕ ПРОДАЖИ")
def handle_all_sales(message):
    """Список всех продаж"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id_number, price, seller_id FROM id_sales 
        WHERE status = 'active'
        ORDER BY price ASC
        LIMIT 20
    ''')
    
    sales = cursor.fetchall()
    conn.close()
    
    if not sales:
        bot.send_message(
            message.chat.id,
            "📭 *РЫНОК ПУСТ*\n\n"
            "💡 Выстави свой ID: `идпрод (сумма)`",
            parse_mode='Markdown'
        )
        return
    
    text = "🏪 *ВСЕ ПРОДАЖИ*\n\n"
    
    for id_num, price, seller_id in sales:
        # Проверка владельца
        owner = get_id_owner(id_num)
        if owner != seller_id:
            continue
            
        seller_num = get_user_id_number(seller_id)
        text += f"🎯 #{id_num:<4} — {format_balance(price):>10}🌸 (от #{seller_num})\n"
    
    text += "\n💡 Купить: `идкуп (номер)`"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# === МОЯ СТАТИСТИКА ===

@bot.message_handler(func=lambda message: message.text == "📊 МОЯ СТАТИСТИКА")
def handle_id_stats(message):
    """Статистика по ID"""
    user_id = message.from_user.id
    user_num = get_user_id_number(user_id)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Сколько ID куплено
    cursor.execute('''
        SELECT COUNT(*) FROM id_history WHERE buyer_id = ?
    ''', (user_id,))
    bought = cursor.fetchone()[0]
    
    # Сколько ID продано
    cursor.execute('''
        SELECT COUNT(*) FROM id_history WHERE seller_id = ?
    ''', (user_id,))
    sold = cursor.fetchone()[0]
    
    # Потрачено всего
    cursor.execute('''
        SELECT SUM(price) FROM id_history WHERE buyer_id = ?
    ''', (user_id,))
    spent = cursor.fetchone()[0] or 0
    
    # Заработано всего
    cursor.execute('''
        SELECT SUM(price) FROM id_history WHERE seller_id = ?
    ''', (user_id,))
    earned = cursor.fetchone()[0] or 0
    
    conn.close()
    
    text = f"""
📊 *СТАТИСТИКА ID ДЛЯ #{user_num}*

┌─────────────────────┐
│ 🎯 Твой ID: #{user_num:<14} │
│ 📥 Куплено: {bought:<5} 📤 Продано: {sold:<5} │
│ 💸 Потрачено: {format_balance(spent):<10} │
│ 💰 Заработано: {format_balance(earned):<10} │
└─────────────────────┘
    """
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# === ОТМЕНА ПРОДАЖИ ===

@bot.message_handler(func=lambda message: message.text.lower() == 'идоtmена')
def handle_id_cancel(message):
    """Отмена продажи"""
    try:
        user_id = message.from_user.id
        user_num = get_user_id_number(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT sale_id FROM id_sales 
            WHERE seller_id = ? AND status = 'active'
        ''', (user_id,))
        
        sale = cursor.fetchone()
        
        if not sale:
            bot.send_message(message.chat.id, "❌ У тебя нет активной продажи")
            conn.close()
            return
        
        cursor.execute('UPDATE id_sales SET status = "cancelled" WHERE sale_id = ?', (sale[0],))
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Продажа ID #{user_num} отменена",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка отмены: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ПОМОЩЬ ===

@bot.message_handler(func=lambda message: message.text == "❓ ПОМОЩЬ")
def handle_id_help(message):
    """Помощь по рынку ID"""
    help_text = """
🎭 *РЫНОК ID — ПОМОЩЬ*

┌─────────────────────────────────┐
│ 🟢 *КУПИТЬ ID*                    │
│   `идкуп (номер)`                │
│   Купить ID с рынка              │
├─────────────────────────────────┤
│ 🔴 *ПРОДАТЬ ID*                   │
│   `идпрод (сумма)`               │
│   Выставить свой ID              │
├─────────────────────────────────┤
│ 🟡 *ПРЕДЛОЖИТЬ*                   │
│   `идпред (номер) (сумма)`       │
│   Предложить цену за ID          │
├─────────────────────────────────┤
│ ✅ *ПРИНЯТЬ*                       │
│   `идпринять (номер)`            │
│   Принять предложение            │
├─────────────────────────────────┤
│ ❌ *ОТКЛОНИТЬ*                     │
│   `идотклонить (номер)`          │
│   Отклонить предложение          │
├─────────────────────────────────┤
│ 🚫 *ОТМЕНИТЬ ПРОДАЖУ*             │
│   `идоtmена`                     │
└─────────────────────────────────┘

💡 *Примеры:*
• `идкуп 42` — купить ID #42
• `идпрод 1кк` — продать за 1.000.000🌸
• `идпред 42 500к` — предложить 500.000🌸

⚡ *Цветные кнопки — просто нажимай!*
    """
    
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

# === НАЗАД ===

@bot.message_handler(func=lambda message: message.text == "◀️ НАЗАД")
def handle_back_from_id(message):
    """Возврат в главное меню"""
    bot.send_message(
        message.chat.id,
        "🌟 *Главное меню*",
        reply_markup=create_main_menu(),
        parse_mode='Markdown'
    )

# === ОБРАБОТЧИК ДЛЯ ИД (ПРОВЕРКА) ===

@bot.message_handler(func=lambda message: message.text.lower().startswith('ид ') and len(message.text.split()) == 2)
def handle_id_check(message):
    """Проверка конкретного ID"""
    try:
        parts = message.text.split()
        if len(parts) == 2:
            try:
                id_num = int(parts[1])
                bot.send_message(
                    message.chat.id,
                    format_id_card(id_num),
                    parse_mode='Markdown'
                )
            except:
                pass
    except:
        pass
# === ИСПРАВЛЕННАЯ СИСТЕМА МАЙНИНГА ЕЛОК ===
MINING_EXCHANGE_RATE = 70  # 1 елка = 100 снежков

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
        
        # Проверяем и добавляем необходимые колонки если их нет
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Создаем недостающие колонки
        missing_columns = []
        if 'mining_balance' not in columns:
            missing_columns.append('mining_balance')
        if 'mining_trees' not in columns:
            missing_columns.append('mining_trees')
        if 'last_mining_collect' not in columns:
            missing_columns.append('last_mining_collect')
        
        for column in missing_columns:
            try:
                if column == 'last_mining_collect':
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column} INTEGER DEFAULT 0")
                else:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column} INTEGER DEFAULT 0")
                conn.commit()
                logging.info(f"Добавлена колонка {column} для пользователя {user_id}")
            except sqlite3.Error as e:
                logging.error(f"Ошибка добавления колонки {column}: {e}")
        
        # Получаем данные пользователя
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
        
        # Устанавливаем значения по умолчанию если None
        video_cards = video_cards if video_cards is not None else 0
        last_collect = last_collect if last_collect is not None else 0
        mining_balance = mining_balance if mining_balance is not None else 0
        mining_trees = mining_trees if mining_trees is not None else 0
        
        # Если last_collect равен 0 (новый пользователь), устанавливаем текущее время
        if last_collect == 0:
            current_time = int(time.time())
            cursor.execute('UPDATE users SET last_mining_collect = ? WHERE user_id = ?', 
                          (current_time, user_id))
            last_collect = current_time
            conn.commit()
        
        # Рассчитываем накопленные елки с момента последнего сбора
        accumulated_trees = 0
        if video_cards > 0 and last_collect > 0:
            try:
                current_time = int(time.time())
                time_passed = current_time - last_collect
                
                if time_passed > 0:
                    # 1 видеокарта = 1 елка в час
                    income_per_hour = video_cards
                    accumulated_trees = int(income_per_hour * (time_passed / 3600))
                    
                    # Ограничиваем максимальное накопление (не более 24 часов)
                    max_accumulation = video_cards * 24  # Максимум 24 часа работы
                    if accumulated_trees > max_accumulation:
                        accumulated_trees = max_accumulation
                        
            except Exception as e:
                logging.error(f"Ошибка расчета накоплений: {e}")
                accumulated_trees = 0
        
        # Доход в час
        income_per_hour = video_cards
        
        # Стоимость следующей карты (в снежках)
        card_price = 5000 * (video_cards + 1)
        
        # Формируем сообщение
        message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
        message_text += f"🎮 *Видеокарт:* {video_cards}\n"
        message_text += f"💰 *Доход:* {income_per_hour} 🎄/час\n"
        message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}🌸\n\n"
        message_text += f"📦 *В хранилище:* {mining_balance}🎄\n"
        message_text += f"🌲 *Всего добыто:* {mining_trees}🎄\n"
        
        if video_cards == 0:
            message_text += "\n💡 Купите первую видеокарту чтобы начать майнить елки!"
        elif accumulated_trees > 0:
            message_text += f"📈 *Доступно для сбора:* {accumulated_trees}🎄"
            
            # Показываем время до полного накопления
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
        logging.error(f"Ошибка в майнинге: {e}", exc_info=True)
        bot.send_message(message.chat.id, f"❌ Ошибка загрузки майнинга: {str(e)[:100]}")

def create_mining_keyboard(video_cards, accumulated_trees, mining_balance, card_price):
    """Создает клавиатуру для майнинга"""
    markup = InlineKeyboardMarkup(row_width=2)
    
    if accumulated_trees > 0:
        markup.add(
            InlineKeyboardButton(f"🔄 Собрать {accumulated_trees}🎄", callback_data="mining_collect")
        )
    
    markup.add(
        InlineKeyboardButton(f"💳 Купить карту {format_balance(card_price)}🌸", callback_data="mining_buy")
    )
    
    # Кнопка обмена если есть накопленные елки
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
            
            # Проверяем на None
            video_cards = video_cards if video_cards is not None else 0
            last_collect = last_collect if last_collect is not None else 0
            mining_balance = mining_balance if mining_balance is not None else 0
            
            if video_cards == 0:
                bot.answer_callback_query(call.id, "❌ У вас нет видеокарт для сбора!")
                conn.close()
                return
            
            # Если last_collect равен 0, устанавливаем текущее время
            current_time = int(time.time())
            if last_collect == 0:
                cursor.execute('UPDATE users SET last_mining_collect = ? WHERE user_id = ?', 
                             (current_time, user_id))
                last_collect = current_time
            
            # Рассчитываем накопленные елки
            accumulated_trees = 0
            if last_collect > 0:
                time_passed = current_time - last_collect
                
                if time_passed > 0:
                    income_per_hour = video_cards
                    accumulated_trees = int(income_per_hour * (time_passed / 3600))
                    
                    # Ограничиваем максимальное накопление
                    max_accumulation = video_cards * 24  # Максимум 24 часа работы
                    if accumulated_trees > max_accumulation:
                        accumulated_trees = max_accumulation
            
            if accumulated_trees > 0:
                # Добавляем елки в хранилище
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
                
                # Пересчитываем для обновленного сообщения
                new_income_per_hour = video_cards
                new_card_price = 2000 * (video_cards + 1)
                
                message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
                message_text += f"🎮 *Видеокарт:* {video_cards}\n"
                message_text += f"💰 *Доход:* {new_income_per_hour} 🎄/час\n"
                message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}🌸\n\n"
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
                except Exception as e:
                    logging.error(f"Ошибка редактирования сообщения: {e}")
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
                message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}🌸\n\n"
                message_text += f"📦 *В хранилище:* {mining_balance}🎄\n"
                message_text += f"🌲 *Всего добыто:* {mining_trees}🎄\n"
                message_text += f"💳 *Баланс снежков:* {format_balance(new_balance)}🌸"
                
                try:
                    bot.edit_message_text(
                        message_text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_mining_keyboard(new_video_cards, 0, mining_balance, new_card_price),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logging.error(f"Ошибка редактирования покупки: {e}")
                    bot.answer_callback_query(call.id, "✅ Куплено!")
            else:
                bot.answer_callback_query(call.id, 
                    f"❌ Недостаточно снежков! Нужно: {format_balance(card_price)}🌸",
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
            
            # Проверяем на None
            mining_balance = mining_balance if mining_balance is not None else 0
            current_balance = current_balance if current_balance is not None else 0
            
            if mining_balance <= 0:
                bot.answer_callback_query(call.id, "❌ У вас нет елок для обмена!")
                conn.close()
                return
            
            # Обмен всех елок на снежки
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
            
            bot.answer_callback_query(call.id, f"✅ Обменено {mining_balance}🎄 на {format_balance(snow_amount)}🌸!")
            
            message_text = f"🖥 *Ваша майнинг ферма:*\n\n"
            message_text += f"🎮 *Видеокарт:* {video_cards}\n"
            message_text += f"💰 *Доход:* {video_cards} 🎄/час\n"
            message_text += f"💎 *Обмен:* 1🎄 = {MINING_EXCHANGE_RATE}🌸\n\n"
            message_text += f"📦 *В хранилище:* 0🎄\n"
            message_text += f"🌲 *Всего добыто:* {mining_trees}🎄\n"
            message_text += f"✅ *Обменено:* {mining_balance}🎄 → {format_balance(snow_amount)}🌸\n"
            message_text += f"💳 *Баланс снежков:* {format_balance(new_balance)}🌸"
            
            try:
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_mining_keyboard(video_cards, 0, 0, card_price),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"Ошибка редактирования обмена: {e}")
                bot.answer_callback_query(call.id, "✅ Обменено!")
            
            conn.close()
    
    except Exception as e:
        logging.error(f"Ошибка в mining_callback_handler: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Ошибка базы данных")

# === КОМАНДА ДЛЯ СБРОСА МАЙНИНГА (админ) ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('сбросмайнинг') and is_admin(message.from_user.id))
def handle_reset_mining(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: сбросмайнинг @username")
            return
        
        target = parts[1].strip()
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
                bot.send_message(message.chat.id, "❌ Неверный ID. Используйте @username или ID")
                return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Сбрасываем статистику майнинга
        cursor.execute('''
            UPDATE users 
            SET mining_balance = 0,
                last_mining_collect = ?,
                video_cards = 0,
                mining_trees = 0
            WHERE user_id = ?
        ''', (int(time.time()), user_id))
        
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Статистика майнинга для {target} сброшена")
        
        # Уведомляем пользователя
        try:
            bot.send_message(user_id, "🔄 Ваша майнинг ферма была сброшена администратором")
        except:
            pass
        
    except Exception as e:
        logging.error(f"Ошибка сброса майнинга: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

# === КОМАНДА ДЛЯ ФИКСА МАЙНИНГА ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('фиксмайнинг') and is_admin(message.from_user.id))
def handle_fix_mining(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        bot.send_message(message.chat.id, "🔧 Проверяю и исправляю таблицу майнинга...")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем наличие колонок
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        column_names = [col[1] for col in cursor.fetchall()]
        
        required_columns = [
            ('video_cards', 'INTEGER DEFAULT 0'),
            ('mining_balance', 'INTEGER DEFAULT 0'),
            ('mining_trees', 'INTEGER DEFAULT 0'),
            ('last_mining_collect', 'INTEGER DEFAULT 0')
        ]
        
        fixed_count = 0
        for column_name, column_type in required_columns:
            if column_name not in column_names:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                    fixed_count += 1
                    logging.info(f"Добавлена колонка {column_name}")
                except sqlite3.Error as e:
                    logging.error(f"Ошибка добавления колонки {column_name}: {e}")
        
        conn.commit()
        
        # Проверяем пользователей с NULL значениями
        cursor.execute('SELECT user_id FROM users WHERE video_cards IS NULL OR mining_balance IS NULL OR last_mining_collect IS NULL')
        users_with_null = cursor.fetchall()
        
        for (user_id,) in users_with_null:
            current_time = int(time.time())
            cursor.execute('''
                UPDATE users 
                SET video_cards = COALESCE(video_cards, 0),
                    mining_balance = COALESCE(mining_balance, 0),
                    mining_trees = COALESCE(mining_trees, 0),
                    last_mining_collect = COALESCE(last_mining_collect, ?)
                WHERE user_id = ?
            ''', (current_time, user_id))
            fixed_count += 1
        
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id,
                       f"✅ Фикс майнинга завершен!\n"
                       f"📊 Исправлено: {fixed_count} проблем")
        
    except Exception as e:
        logging.error(f"Ошибка фикса майнинга: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")
@bot.message_handler(func=lambda message: message.text == "Балик" and message.chat.id < 0)
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
        
        response = f"👤 {display_name}\n💰 Баланс: 🌸{format_balance(balance)}"
        
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
            
            response += f"{medals[i-1]} {display_name}: 🌸{format_balance(balance)}\n"
        
        conn.close()
        
        user_position = get_user_position_in_top(user_id, 'balance')
        user_balance = get_balance(user_id)
        
        if user_position:
            response += f"\n🎯 Твоя позиция: #{user_position}\n💰 Твой баланс: 🌸{format_balance(user_balance)}"
        
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
                    
                    bot.send_message(user_id, f"🎉 Вы активировали чек на 🌸{format_balance(amount)}!")
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
                            f"💰 +{REFERRAL_BONUS}🌸\n\n"
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
# === КОМАНДА ДЛЯ СКАЧИВАНИЯ БАЗЫ ДАННЫХ ===
@bot.message_handler(func=lambda message: message.text.lower() == 'база' and is_admin(message.from_user.id))
def handle_download_db(message):
    """Скачивание базы данных"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        if not os.path.exists('game.db'):
            bot.send_message(message.chat.id, "❌ База данных не найдена")
            return
        
        bot.send_message(message.chat.id, "⏳ Подготавливаю базу данных...")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"game_backup_{timestamp}.db"
        zip_filename = f"game_backup_{timestamp}.zip"
        
        # Создаем копию базы
        shutil.copy2('game.db', backup_filename)
        
        # Создаем ZIP архив
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(backup_filename, os.path.basename(backup_filename))
        
        # Отправляем архив
        with open(zip_filename, 'rb') as zip_file:
            bot.send_document(
                message.chat.id,
                zip_file,
                caption=f"📦 Резервная копия базы данных\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📊 Размер: {os.path.getsize(zip_filename) / 1024:.1f} KB",
                timeout=60
            )
        
        # Удаляем временные файлы
        os.remove(backup_filename)
        os.remove(zip_filename)
        
        logging.info(f"Админ {message.from_user.id} скачал базу данных")
        
    except Exception as e:
        logging.error(f"Ошибка скачивания базы: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

# === КОМАНДА ДЛЯ ЗАГРУЗКИ БАЗЫ ДАННЫХ ===
@bot.message_handler(func=lambda message: message.text.lower() == 'загрузитьбазу' and is_admin(message.from_user.id))
def handle_upload_db(message):
    """Загрузка базы данных из файла"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        bot.send_message(
            message.chat.id,
            "📤 *ЗАГРУЗКА БАЗЫ ДАННЫХ*\n\n"
            "⚠️ *ВНИМАНИЕ!* Эта операция:\n"
            "• Заменит текущую базу данных\n"
            "• Может привести к потере данных\n"
            "• Используйте только бэкапы\n\n"
            "Отправьте файл базы данных (.db или .zip)",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка запроса загрузки базы: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОБРАБОТЧИК ЗАГРУЗКИ ФАЙЛОВ БАЗЫ ===
@bot.message_handler(content_types=['document'], func=lambda message: is_admin(message.from_user.id))
def handle_db_file_upload(message):
    """Обработка загруженного файла базы данных"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        filename = message.document.file_name.lower()
        
        # Проверяем тип файла
        if not (filename.endswith('.db') or filename.endswith('.zip')):
            bot.send_message(message.chat.id, "❌ Неверный формат файла. Нужен .db или .zip")
            return
        
        # Создаем бэкап текущей базы
        if os.path.exists('game.db'):
            backup_name = f"game_backup_before_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2('game.db', backup_name)
            logging.info(f"Создан бэкап перед заменой: {backup_name}")
        
        # Сохраняем загруженный файл
        temp_filename = f"uploaded_{filename}"
        with open(temp_filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Если это ZIP архив
        if filename.endswith('.zip'):
            with zipfile.ZipFile(temp_filename, 'r') as zipf:
                # Ищем файл .db в архиве
                db_files = [f for f in zipf.namelist() if f.endswith('.db')]
                if not db_files:
                    bot.send_message(message.chat.id, "❌ В архиве нет файла базы данных (.db)")
                    os.remove(temp_filename)
                    return
                
                # Извлекаем первый файл .db
                zipf.extract(db_files[0])
                extracted_file = db_files[0]
                
                # Заменяем текущую базу
                if os.path.exists('game.db'):
                    os.remove('game.db')
                os.rename(extracted_file, 'game.db')
        
        # Если это файл .db напрямую
        else:
            if os.path.exists('game.db'):
                os.remove('game.db')
            os.rename(temp_filename, 'game.db')
            temp_filename = None
        
        # Очищаем временные файлы
        if temp_filename and os.path.exists(temp_filename):
            os.remove(temp_filename)
        
        # Переинициализируем соединение
        global DB_CONNECTION
        try:
            DB_CONNECTION = get_db_connection()
            bot.send_message(
                message.chat.id,
                "✅ *БАЗА ДАННЫХ УСПЕШНО ЗАГРУЖЕНА!*\n\n"
                "📊 Перезагружаю соединение с БД...\n"
                "🔄 Бот продолжит работу с новой базой\n\n"
                "⚠️ *Рекомендуется перезапустить бота*",
                parse_mode='Markdown'
            )
            
            logging.info(f"Админ {message.from_user.id} загрузил новую базу данных: {filename}")
            
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"❌ *ОШИБКА ЗАГРУЗКИ БАЗЫ!*\n\n"
                f"Бот попытается восстановить старую базу из бэкапа...\n"
                f"Ошибка: {str(e)[:100]}",
                parse_mode='Markdown'
            )
            
            # Пробуем восстановить из бэкапа
            try:
                backup_files = [f for f in os.listdir('.') if f.startswith('game_backup_before_upload_') and f.endswith('.db')]
                if backup_files:
                    latest_backup = max(backup_files)  # Берем последний бэкап
                    if os.path.exists('game.db'):
                        os.remove('game.db')
                    shutil.copy2(latest_backup, 'game.db')
                    bot.send_message(message.chat.id, "✅ Восстановлен бэкап базы данных")
            except:
                bot.send_message(message.chat.id, "❌ Не удалось восстановить базу из бэкапа")
    
    except Exception as e:
        logging.error(f"Ошибка загрузки базы: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка загрузки: {str(e)[:100]}")

# === КОМАНДА ДЛЯ ИНФОРМАЦИИ О БАЗЕ ===
@bot.message_handler(func=lambda message: message.text.lower() == 'инфобаза' and is_admin(message.from_user.id))
def handle_db_info(message):
    """Показывает информацию о базе данных"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем статистику
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM checks")
        checks_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(bank_deposit) FROM users")
        total_deposit = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM user_houses")
        houses_count = cursor.fetchone()[0]
        
        # Получаем размер файла базы
        db_size = os.path.getsize('game.db') if os.path.exists('game.db') else 0
        db_size_mb = db_size / (1024 * 1024)
        
        conn.close()
        
        info_text = f"""
📊 *ИНФОРМАЦИЯ О БАЗЕ ДАННЫХ*

👥 *Пользователи:* {users_count:,}
🚫 *Забанено:* {banned_count:,}
💳 *Чеков:* {checks_count:,}
🏠 *Домов:* {houses_count:,}

💰 *Общий баланс:* 🌸{format_balance(total_balance)}
🏦 *Всего на вкладах:* 🌸{format_balance(total_deposit)}

📁 *Размер базы:* {db_size_mb:.2f} MB
📅 *Дата:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Команды:*
• `база` - Скачать резервную копию
• `загрузитьбазу` - Загрузить новую базу
• `очиститьлоги` - Очистить логи
• `лог [id]` - Логи пользователя
"""
        
        bot.send_message(message.chat.id, info_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка получения информации о базе: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")
# === НАСТРОЙКИ БОНУСА ===
# Глобальные переменные для блокировки повторных кликов
user_bonus_cooldown = {}  # {user_id: timestamp}
bonus_processing = set()  # Множество пользователей, которые уже получают бонус

REQUIRED_CHANNEL = "@FECTIZ"  # Канал для подписки
MIN_BONUS = 100  # Минимальный бонус
MAX_BONUS = 2000  # Максимальный бонус


@bot.message_handler(func=lambda message: message.text == "Бонус")
def handle_daily_bonus(message):
    try:
        user_id = message.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        # Проверяем подписку
        try:
            channel_member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if channel_member.status not in ['member', 'administrator', 'creator']:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                
                bot.send_message(
                    message.chat.id,
                    "🎁 *Бонус*\n\n"
                    f"🌸 *{MIN_BONUS}-{MAX_BONUS}🌸*\n"
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
                f"🌸 *{MIN_BONUS}-{MAX_BONUS}🌸*\n"
                f"🕐 *каждые 30 мин*\n\n"
                f"❌ *Ошибка проверки подписки.*\n"
                f"Подпишитесь на: {REQUIRED_CHANNEL}\n\n"
                "После подписки нажмите *'🔄 Проверить'*",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            return
        
        # Проверяем время с блокировкой
        current_time = int(time.time())
        
        # Проверяем не обрабатывается ли уже бонус
        if user_id in bonus_processing:
            bot.send_message(message.chat.id, "⏳ Бонус уже обрабатывается...")
            return
        
        # Проверяем кулдаун
        if user_id in user_bonus_cooldown:
            last_bonus_time = user_bonus_cooldown[user_id]
            time_passed = current_time - last_bonus_time
            
            if time_passed < 2:  # 2 секунды для защиты от двойного клика
                time_left = 2 - time_passed
                bot.send_message(message.chat.id, f"⏳ Подождите {time_left} секунд")
                return
        
        # Устанавливаем временный кулдаун
        user_bonus_cooldown[user_id] = current_time
        
        # Проверяем время последнего бонуса из базы данных
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Получаем время последнего бонуса
            cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_bonus = result[0]
                
                # Преобразуем last_bonus в timestamp
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
                    
                    if time_passed < 1800:  # 30 минут = 1800 секунд
                        time_left = 1800 - time_passed
                        minutes = time_left // 60
                        seconds = time_left % 60
                        
                        # Удаляем временный кулдаун
                        if user_id in user_bonus_cooldown:
                            del user_bonus_cooldown[user_id]
                            
                        bot.send_message(message.chat.id, f"⏳ Бонус будет доступен через {minutes} минут {seconds} секунд")
                        conn.close()
                        return
                        
        except Exception as e:
            logging.error(f"Ошибка проверки времени бонуса: {e}")
            # При ошибке продолжаем, возможно это первый бонус
        finally:
            if conn:
                conn.close()
        
        # Показываем бонус с защитой от повторного клика
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"claim_bonus_{current_time}"))
        
        bonus_text = f"🎁 *Бонус*\n\n"
        bonus_text += f"🌸 *{MIN_BONUS}-{MAX_BONUS}🌸*\n"
        bonus_text += f"🕐 *каждые 30 мин*"
        
        bot.send_message(message.chat.id, bonus_text, parse_mode='Markdown', reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в бонусе: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub_bonus")
def handle_check_subscription_bonus(call):
    try:
        user_id = call.from_user.id
        current_time = int(time.time())
        
        # Блокировка от повторных кликов
        if user_id in user_bonus_cooldown:
            if current_time - user_bonus_cooldown[user_id] < 2:
                bot.answer_callback_query(call.id, "⏳ Подождите немного")
                return
        
        user_bonus_cooldown[user_id] = current_time
        
        try:
            channel_member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if channel_member.status in ['member', 'administrator', 'creator']:
                bot.answer_callback_query(call.id, "✅ Подписка подтверждена")
                
                # Обновляем сообщение
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"claim_bonus_{current_time}"))
                
                bot.edit_message_text(
                    "🎁 *Бонус*\n\n"
                    f"🌸 *{MIN_BONUS}-{MAX_BONUS}🌸*\n"
                    f"🕐 *каждые 30 мин*\n\n"
                    "✅ *Подписка подтверждена!*",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            else:
                bot.answer_callback_query(call.id, "❌ Вы не подписаны")
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                
                bot.edit_message_text(
                    "🎁 *Бонус*\n\n"
                    f"🌸 *{MIN_BONUS}-{MAX_BONUS}🌸*\n"
                    f"🕐 *каждые 30 мин*\n\n"
                    "❌ *Вы еще не подписались!*\n\n"
                    f"📢 Канал: {REQUIRED_CHANNEL}\n"
                    "После подписки нажмите *'🔄 Проверить'*",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки")
            
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_bonus_"))
def handle_claim_bonus(call):
    conn = None
    try:
        user_id = call.from_user.id
        current_time = int(time.time())
        
        # Извлекаем timestamp из callback_data
        callback_parts = call.data.split('_')
        if len(callback_parts) != 3:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
            
        callback_timestamp = int(callback_parts[2])
        
        # Проверяем не устарела ли кнопка (больше 60 секунд)
        if current_time - callback_timestamp > 60:
            bot.answer_callback_query(call.id, "❌ Время истекло, обновите страницу")
            return
        
        # Проверяем не обрабатывается ли уже бонус
        if user_id in bonus_processing:
            bot.answer_callback_query(call.id, "⏳ Уже получаете бонус...")
            return
        
        # Добавляем пользователя в обработку
        bonus_processing.add(user_id)
        
        try:
            # Проверяем подписку
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
            
            # Генерируем случайную сумму бонуса
            bonus_amount = random.randint(MIN_BONUS, MAX_BONUS)
            
            # Проверяем время через БД с транзакцией
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Начинаем транзакцию для атомарной проверки
            cursor.execute('BEGIN IMMEDIATE TRANSACTION')
            
            # Получаем время последнего бонуса с блокировкой строки
            cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_bonus = result[0]
                
                # Преобразуем last_bonus in timestamp
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
                    
                    if time_passed < 1700:  # 28 минут для надежности
                        cursor.execute('ROLLBACK')
                        conn.close()
                        
                        time_left = 1800 - time_passed
                        minutes = time_left // 60
                        seconds = time_left % 60
                        bot.answer_callback_query(call.id, f"⏳ Ждите {minutes}:{seconds:02d}")
                        return
            
            # Выдаем бонус
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (bonus_amount, user_id))
            
            # Обновляем время
            cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, user_id))
            
            # Коммитим транзакцию
            cursor.execute('COMMIT')
            
            # Получаем баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            balance_result = cursor.fetchone()
            new_balance = balance_result[0] if balance_result else bonus_amount
            
            # Показываем результат в новом формате
            result_text = f"*✅ Бонус получен*\n\n"
            result_text += f"> *+{bonus_amount}🌸*\n\n"
            result_text += f"*💸 Баланс: {format_balance(new_balance)}🌸*"
            
            bot.edit_message_text(
                result_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
            
            bot.answer_callback_query(call.id, "✅")
            
            # Устанавливаем временный кулдаун на 5 секунд
            user_bonus_cooldown[user_id] = current_time
            
            # Логируем успешное получение
            logging.info(f"Пользователь {user_id} получил бонус {bonus_amount}🌸 баланс: {new_balance}🌸")
            
        except Exception as e:
            # Откатываем транзакцию при ошибке
            try:
                if conn:
                    cursor.execute('ROLLBACK')
            except:
                pass
            logging.error(f"Ошибка получения бонуса: {e}")
            
            # Пробуем альтернативный метод (без транзакции)
            try:
                if conn:
                    conn.close()
                
                # Простая проверка без транзакции
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
                
                # Генерируем случайную сумму бонуса для альтернативного метода
                bonus_amount = random.randint(MIN_BONUS, MAX_BONUS)
                
                # Выдаем бонус
                simple_cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (bonus_amount, user_id))
                simple_cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, user_id))
                simple_conn.commit()
                
                simple_cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                balance_result = simple_cursor.fetchone()
                new_balance = balance_result[0] if balance_result else bonus_amount
                
                # Показываем результат в новом формате
                result_text = f"*✅ Бонус получен*\n\n"
                result_text += f"> *+{bonus_amount}🌸*\n\n"
                result_text += f"*💸 Баланс: {format_balance(new_balance)}🌸*"
                
                bot.edit_message_text(
                    result_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✅")
                logging.info(f"Пользователь {user_id} получил бонус {bonus_amount}🌸 (альтернативный метод) баланс: {new_balance}🌸")
                
                simple_conn.close()
                
            except Exception as e2:
                logging.error(f"Ошибка альтернативного метода: {e2}")
                bot.answer_callback_query(call.id, "❌ Ошибка получения")
                
        finally:
            # Удаляем пользователя из обработки
            if user_id in bonus_processing:
                bonus_processing.remove(user_id)
            if conn:
                conn.close()
                
    except Exception as e:
        logging.error(f"Критическая ошибка в бонусе: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")
        
        # Удаляем пользователя из обработки
        if user_id in bonus_processing:
            bonus_processing.remove(user_id)

def cleanup_bonus_cooldowns():
    """Очищает старые записи о кулдаунах"""
    while True:
        time.sleep(60)  # Каждую минуту
        current_time = time.time()
        
        # Очищаем старые кулдауны (старше 10 секунд)
        to_remove = []
        for user_id, timestamp in user_bonus_cooldown.items():
            if current_time - timestamp > 10:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del user_bonus_cooldown[user_id]
        
        # Очищаем обработку (на всякий случай)
        bonus_processing.clear()

# Запускаем очистку в отдельном потоке
cleanup_thread = threading.Thread(target=cleanup_bonus_cooldowns, daemon=True)
cleanup_thread.start()

# === ФУНКЦИЯ ДЛЯ СОЗДАНИЯ КОЛОНКИ БОНУСА ===
def ensure_bonus_column():
    """Создает колонку для бонуса если её нет"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'last_bonus' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_bonus INTEGER DEFAULT 0")
            conn.commit()
            logging.info("✅ Колонка last_bonus создана")
            
    except Exception as e:
        logging.error(f"Ошибка создания колонки: {e}")
    finally:
        if conn:
            conn.close()

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
        message_text += f"• Бонусы от игр: {format_balance(total_bonus)}🌸\n"
        message_text += f"• Выигрышей: {total_wins}\n\n"
        message_text += f"💡 +1% от ВСЕХ выигрышей рефералов"
        
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
        message_text += f"• Бонусы от игр: {format_balance(total_bonus)}🌸\n"
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
        
        # Проверяем существование колонки mining_balance
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Создаем mining_balance если её нет
        if 'mining_balance' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN mining_balance INTEGER DEFAULT 0")
            conn.commit()
        
        # Получаем данные пользователя
        cursor.execute('''
            SELECT first_name, video_cards, bank_deposit, last_mining_collect, registered_at, mining_balance 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            first_name, video_cards, bank_deposit, last_mining_collect, registered_at, mining_balance = result
            
            # Устанавливаем значения по умолчанию если None
            video_cards = video_cards if video_cards is not None else 0
            mining_balance = mining_balance if mining_balance is not None else 0
            bank_deposit = bank_deposit if bank_deposit is not None else 0
            
            # Получаем престижные данные
            prestige_id = get_prestige_id(user_id)
            prestige_badge = get_prestige_badge(user_id)
            
            # Форматируем дату регистрации
            reg_date = "Неизвестно"
            if registered_at:
                try:
                    reg_date = registered_at[:10]
                except:
                    reg_date = str(registered_at)[:10]
            
            # Создаем текст сообщения
            message_text = f"👤 *{first_name}*\n"
            message_text += f"{prestige_id}\n\n"
            
            message_text += f"💰 *Баланс:* 🌸{format_balance(balance)}\n"
            message_text += f"🎄 *Елки:* 🎄{mining_balance}\n"
            
            if bank_deposit > 0:
                message_text += f"🏦 *В банке:* 🌸{format_balance(bank_deposit)}\n"
            
            message_text += f"📅 *Регистрация:* {reg_date}"
            
            # Получаем текущий дом
            current_house = get_current_house(user_id)
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                message_text += f"\n🏠 *Дом:* {house_name}"
            
            # === СОЗДАНИЕ КОМБИНИРОВАННОГО ИЗОБРАЖЕНИЯ ===
            try:
                # Загружаем снеговика с прозрачным фоном (g.png)
                snowman_path = "g.png"
                
                if not os.path.exists(snowman_path):
                    # Если нет снеговика, просто отправляем текст
                    bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
                    conn.close()
                    return
                
                # Если есть дом
                if current_house:
                    house_info = HOUSE_SHOP.get(current_house, {})
                    house_image = house_info.get('image')
                    
                    if house_image and os.path.exists(house_image):
                        # Открываем оба изображения
                        house_img = Image.open(house_image).convert("RGBA")
                        snowman_img = Image.open(snowman_path).convert("RGBA")
                        
                        # Получаем размеры
                        house_width, house_height = house_img.size
                        snowman_width, snowman_height = snowman_img.size
                        
                        # Если снеговик не того же размера, что и дом - подгоняем
                        if (house_width, house_height) != (snowman_width, snowman_height):
                            # Растягиваем снеговика под размер дома
                            snowman_img = snowman_img.resize((house_width, house_height), Image.Resampling.LANCZOS)
                        
                        # Создаем новое изображение
                        combined = Image.new('RGBA', (house_width, house_height))
                        
                        # 1. Сначала дом как фон
                        combined.paste(house_img, (0, 0))
                        
                        # 2. Затем снеговик с прозрачностью поверх дома
                        # Используем снеговик как маску для прозрачности
                        combined.paste(snowman_img, (0, 0), snowman_img)
                        
                        # Сохраняем во временный файл
                        temp_file = f"temp_combo_{user_id}.png"
                        combined.save(temp_file, "PNG")
                        
                        # Отправляем
                        with open(temp_file, 'rb') as photo:
                            bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                        
                        # Удаляем временный файл
                        os.remove(temp_file)
                        conn.close()
                        return
                    else:
                        # Если нет изображения дома, отправляем только снеговика
                        with open(snowman_path, 'rb') as photo:
                            bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                        conn.close()
                        return
                else:
                    # Если нет дома, отправляем только снеговика
                    with open(snowman_path, 'rb') as photo:
                        bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                    conn.close()
                    return
                    
            except Exception as e:
                # Если ошибка при создании изображения
                logging.error(f"Ошибка создания изображения: {e}")
                
                # Пробуем просто отправить снеговика
                try:
                    with open("g.png", 'rb') as photo:
                        bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                except:
                    # Или просто текст
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
            return False, f"Недостаточно средств. Нужно: {format_balance(price)}🌸"
        
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
                       f"💰 Цена: {format_balance(price)}🌸\n"
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
    
    markup.row(InlineKeyboardButton(f"💰 Купить за {format_balance(house_info.get('price', 0))}🌸", 
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
                caption += f"💰 Цена: {format_balance(house_info.get('price', 0))}🌸\n"
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
                text += f"💰 Цена: {format_balance(house_info.get('price', 0))}🌸\n"
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
            text += f"💰 Цена: {format_balance(house_info.get('price', 0))}🌸\n"
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
                f"❌ Недостаточно средств! Нужно: {format_balance(house_price)}🌸",
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
                caption += f"💰 Цена: {format_balance(current_house_info.get('price', 0))}🌸\n"
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
                                  f"💰 Цена: {format_balance(house_price)}🌸\n\n"
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


# === ПЕРЕПИСАННАЯ СИСТЕМА КУРЬЕРА ===
# Одно сообщение, доставка 1 минута, кулдаун 3 минуты при отмене
# Без синих квадратиков, чистый текст

# Глобальные переменные для активных работ
COURIER_JOBS = {}  # {user_id: job_data}
COURIER_STATS = {}  # {user_id: stats_data}
COURIER_MESSAGES = {}  # {user_id: {"chat_id": int, "message_id": int}}
COURIER_TIMERS = {}  # {user_id: timer_thread}

# Настройки системы
COURIER_LEVELS = {
    1: {"name": "🛵 Начинающий", "deliveries": 3, "pay": 80, "xp_needed": 5},
    2: {"name": "🚲 Курьер", "deliveries": 4, "pay": 110, "xp_needed": 10},
    3: {"name": "🚗 Профи", "deliveries": 5, "pay": 150, "xp_needed": 15},
    4: {"name": "🚚 Эксперт", "deliveries": 6, "pay": 200, "xp_needed": 20},
    5: {"name": "✈️ Мастер", "deliveries": 7, "pay": 260, "xp_needed": 25}
}

ADDRESSES = [
    "🏢 Центр", "🌳 Парк", "🏘️ Жилой", "🏬 ТЦ",
    "🏛️ Администрация", "🎓 Университет", "🏥 Больница"
]

PACKAGES = [
    "📦 Посылка", "📮 Письмо", "🎁 Подарок",
    "📚 Документы", "💻 Техника", "🌿 Растение"
]

@bot.message_handler(func=lambda message: message.text == "🚚 Курьер")
def handle_courier(message):
    user_id = message.from_user.id
    
    banned, reason = is_banned(user_id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
        return
    
    stats = get_courier_stats(user_id)
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    
    current_time = time.time()
    
    # Проверяем кулдаун
    if stats.get("cooldown_until", 0) > current_time:
        time_left = int(stats["cooldown_until"] - current_time)
        minutes = time_left // 60
        seconds = time_left % 60
        
        bot.send_message(
            message.chat.id,
            f"⏳ *ВЫ ОТДЫХАЕТЕ*\n\n"
            f"🌸 Осталось: {minutes}м {seconds}с\n\n"
            f"💡 После отдыха можно снова работать!",
            parse_mode='Markdown'
        )
        return
    
    # Если есть активная смена - показываем её
    if user_id in COURIER_JOBS:
        show_active_job(message.chat.id, user_id, stats)
    else:
        show_courier_menu(message.chat.id, user_id, stats)

def get_courier_stats(user_id):
    """Получает или создает статистику курьера"""
    if user_id not in COURIER_STATS:
        COURIER_STATS[user_id] = {
            "level": 1,
            "xp": 0,
            "deliveries": 0,
            "earned": 0,
            "cooldown_until": 0,
            "canceled_shifts": 0
        }
    return COURIER_STATS[user_id]

def show_courier_menu(chat_id, user_id, stats):
    """Показывает меню курьера"""
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    next_level = stats["level"] + 1
    next_data = COURIER_LEVELS.get(next_level)
    
    # Прогресс опыта текстом
    xp_percent = int((stats["xp"] / level_data["xp_needed"]) * 100) if level_data["xp_needed"] > 0 else 0
    
    msg = f"""
🚚 *КУРЬЕРСКАЯ СЛУЖБА*

👤 *Уровень:* {level_data['name']}
📊 *Опыт:* {stats['xp']}/{level_data['xp_needed']} ({xp_percent}%)
📦 *Доставок:* {stats['deliveries']}
💰 *Заработано:* {format_balance(stats['earned'])}🌸

💵 *За доставку:* {level_data['pay']}🌸 + бонус
📋 *За смену:* {level_data['deliveries']} доставок
"""
    
    if next_data:
        xp_needed = level_data["xp_needed"] - stats["xp"]
        msg += f"""
⬆️ *До {next_data['name']}:*
• Нужно опыта: {xp_needed}
• Доставок: +{next_data['deliveries'] - level_data['deliveries']}
• Зарплата: +{next_data['pay'] - level_data['pay']}🌸
"""
    
    msg += f"""
⏱️ *Доставка:* 1 минута
❌ *Отмена:* кулдаун 3 минуты

💡 *Нажмите кнопку чтобы начать смену!*"""
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📦 НАЧАТЬ СМЕНУ", callback_data=f"courier_start_{user_id}"),
        InlineKeyboardButton("📊 СТАТИСТИКА", callback_data=f"courier_stats_{user_id}")
    )
    
    # Удаляем старое сообщение если было
    if user_id in COURIER_MESSAGES:
        try:
            bot.delete_message(COURIER_MESSAGES[user_id]["chat_id"], COURIER_MESSAGES[user_id]["message_id"])
        except:
            pass
    
    # Отправляем новое сообщение и сохраняем его
    sent_msg = bot.send_message(chat_id, msg.strip(), reply_markup=markup, parse_mode='Markdown')
    COURIER_MESSAGES[user_id] = {"chat_id": sent_msg.chat.id, "message_id": sent_msg.message_id}

def show_active_job(chat_id, user_id, stats):
    """Показывает активную доставку"""
    job = COURIER_JOBS[user_id]
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    
    deliveries_left = level_data["deliveries"] - job["done"]
    total_pay = job["pay"] + job["bonus"]
    
    # Прогресс текстом
    progress = int((job["done"] / level_data["deliveries"]) * 100)
    
    # Рассчитываем оставшееся время
    current_time = time.time()
    time_left = max(0, job["delivery_end_time"] - current_time)
    minutes_left = int(time_left // 60)
    seconds_left = int(time_left % 60)
    
    msg = f"""
🚚 *АКТИВНАЯ ДОСТАВКА*

📍 *Куда:* {job['address']}
📦 *Что:* {job['package']}
⏱️ *Доставка:* {minutes_left}:{seconds_left:02d} мин

📊 *Прогресс:* {job['done']}/{level_data['deliveries']} доставок ({progress}%)
💰 *За эту доставку:* {total_pay}🌸
🏆 *Заработано за смену:* {job['earnings']}🌸

💡 *Доставка автоматически завершится через 1 минуту*
"""
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("❌ ОТМЕНИТЬ СМЕНУ", callback_data=f"courier_cancel_{user_id}")
    )
    
    # Удаляем старое сообщение если было
    if user_id in COURIER_MESSAGES:
        try:
            bot.delete_message(COURIER_MESSAGES[user_id]["chat_id"], COURIER_MESSAGES[user_id]["message_id"])
        except:
            pass
    
    # Отправляем новое сообщение и сохраняем его
    sent_msg = bot.send_message(chat_id, msg.strip(), reply_markup=markup, parse_mode='Markdown')
    COURIER_MESSAGES[user_id] = {"chat_id": sent_msg.chat.id, "message_id": sent_msg.message_id}

def create_courier_job(user_id):
    """Создает новую доставку"""
    stats = get_courier_stats(user_id)
    level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
    
    base_pay = level_data["pay"]
    bonus = random.randint(10, 30)
    
    return {
        "done": 0,
        "total": level_data["deliveries"],
        "address": random.choice(ADDRESSES),
        "package": random.choice(PACKAGES),
        "pay": base_pay,
        "bonus": bonus,
        "earnings": 0,
        "start_time": time.time(),
        "delivery_start_time": time.time(),
        "delivery_end_time": time.time() + 60,  # 1 минута на доставку
        "job_id": f"{user_id}_{int(time.time())}"
    }

def start_delivery_timer(user_id):
    """Запускает таймер доставки"""
    if user_id in COURIER_TIMERS:
        try:
            COURIER_TIMERS[user_id].cancel()
        except:
            pass
    
    timer = threading.Timer(60.0, complete_delivery, args=[user_id])
    timer.daemon = True
    timer.start()
    COURIER_TIMERS[user_id] = timer

def complete_delivery(user_id):
    """Автоматически завершает доставку через 1 минуту"""
    try:
        if user_id not in COURIER_JOBS:
            return
        
        job = COURIER_JOBS[user_id]
        stats = get_courier_stats(user_id)
        level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
        
        # Доставка успешно выполнена
        total_pay = job["pay"] + job["bonus"]
        
        job["done"] += 1
        job["earnings"] += total_pay
        
        stats["deliveries"] += 1
        stats["earned"] += total_pay
        stats["xp"] += 1
        
        # Проверка на повышение уровня
        if stats["xp"] >= level_data["xp_needed"] and stats["level"] < 5:
            stats["level"] += 1
            stats["xp"] = 0
            level_up = True
        else:
            level_up = False
        
        # Проверка завершения смены
        if job["done"] >= job["total"]:
            # Смена завершена
            total_earnings = job["earnings"]
            update_balance(user_id, total_earnings)
            
            new_balance = get_balance(user_id)
            
            # Отправляем сообщение о завершении смены
            msg = f"""
✅ *СМЕНА ЗАВЕРШЕНА!*

📦 *Доставок:* {job['total']}/{job['total']}
💰 *Заработано:* {format_balance(total_earnings)}🌸
💳 *Баланс:* {format_balance(new_balance)}🌸
"""
            
            if level_up:
                new_level_data = COURIER_LEVELS.get(stats["level"])
                msg += f"""
🎉 *НОВЫЙ УРОВЕНЬ!*
⬆️ {new_level_data['name']}
"""
            
            # Удаляем старые данные
            del COURIER_JOBS[user_id]
            if user_id in COURIER_TIMERS:
                del COURIER_TIMERS[user_id]
            
            # Отправляем сообщение
            if user_id in COURIER_MESSAGES:
                try:
                    bot.edit_message_text(
                        msg.strip(),
                        COURIER_MESSAGES[user_id]["chat_id"],
                        COURIER_MESSAGES[user_id]["message_id"],
                        parse_mode='Markdown'
                    )
                except:
                    # Если не можем редактировать, отправляем новое
                    chat_id = COURIER_MESSAGES[user_id]["chat_id"]
                    bot.send_message(chat_id, msg.strip(), parse_mode='Markdown')
                    try:
                        bot.delete_message(chat_id, COURIER_MESSAGES[user_id]["message_id"])
                    except:
                        pass
                
                del COURIER_MESSAGES[user_id]
        
        else:
            # Следующая доставка
            job["address"] = random.choice(ADDRESSES)
            job["package"] = random.choice(PACKAGES)
            job["bonus"] = random.randint(10, 30)
            job["delivery_start_time"] = time.time()
            job["delivery_end_time"] = time.time() + 60
            
            # Запускаем таймер на следующую доставку
            start_delivery_timer(user_id)
            
            # Показываем обновленную информацию
            if user_id in COURIER_MESSAGES:
                show_active_job(COURIER_MESSAGES[user_id]["chat_id"], user_id, stats)
    
    except Exception as e:
        logging.error(f"Ошибка автоматической доставки: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('courier_'))
def handle_courier_callback(call):
    user_id = call.from_user.id
    
    try:
        # Проверяем, что callback предназначен этому пользователю
        if not call.data.endswith(str(user_id)):
            bot.answer_callback_query(call.id, "❌ Это не ваша кнопка!", show_alert=True)
            return
        
        action = call.data.split('_')[1]
        stats = get_courier_stats(user_id)
        
        if action == "start":
            # Проверяем кулдаун
            current_time = time.time()
            if stats.get("cooldown_until", 0) > current_time:
                time_left = int(stats["cooldown_until"] - current_time)
                minutes = time_left // 60
                seconds = time_left % 60
                bot.answer_callback_query(call.id, f"⏳ Отдых: {minutes}м {seconds}с", show_alert=True)
                return
            
            # Создаем новую смену
            COURIER_JOBS[user_id] = create_courier_job(user_id)
            
            # Запускаем таймер на первую доставку
            start_delivery_timer(user_id)
            
            # Показываем активную доставку
            show_active_job(call.message.chat.id, user_id, stats)
            bot.answer_callback_query(call.id, "🚚 Смена начата!")
        
        elif action == "stats":
            level_data = COURIER_LEVELS.get(stats["level"], COURIER_LEVELS[1])
            xp_percent = int((stats["xp"] / level_data["xp_needed"]) * 100) if level_data["xp_needed"] > 0 else 0
            
            msg = f"""
📊 *СТАТИСТИКА КУРЬЕРА*

👤 *Уровень:* {level_data['name']}
📈 *Опыт:* {stats['xp']}/{level_data['xp_needed']} ({xp_percent}%)
📦 *Всего доставок:* {stats['deliveries']}
💰 *Всего заработано:* {format_balance(stats['earned'])}🌸
⚠️ *Отмен смен:* {stats.get('canceled_shifts', 0)}
"""
            
            if user_id in COURIER_JOBS:
                job = COURIER_JOBS[user_id]
                msg += f"""
🚚 *Активная смена:*
• Доставок: {job['done']}/{job['total']}
• Заработано: {job['earnings']}🌸
"""
            
            # Проверяем кулдаун
            current_time = time.time()
            if stats.get("cooldown_until", 0) > current_time:
                time_left = int(stats["cooldown_until"] - current_time)
                minutes = time_left // 60
                seconds = time_left % 60
                msg += f"""
⏳ *Отдых:* {minutes}м {seconds}с
"""
            
            bot.answer_callback_query(call.id)
            
            # Отправляем статистику новым сообщением
            bot.send_message(call.message.chat.id, msg.strip(), parse_mode='Markdown')
        
        elif action == "cancel":
            if user_id not in COURIER_JOBS:
                bot.answer_callback_query(call.id, "❌ Нет активной смены")
                return
            
            job = COURIER_JOBS[user_id]
            
            # Начисляем заработанное
            if job["earnings"] > 0:
                update_balance(user_id, job["earnings"])
                stats["earned"] += job["earnings"]
                stats["deliveries"] += job["done"]
                stats["xp"] += job["done"]
                stats["canceled_shifts"] = stats.get("canceled_shifts", 0) + 1
            
            # Устанавливаем кулдаун на 3 минуты (180 секунд)
            stats["cooldown_until"] = time.time() + 180
            
            # Удаляем активную смену
            del COURIER_JOBS[user_id]
            if user_id in COURIER_TIMERS:
                try:
                    COURIER_TIMERS[user_id].cancel()
                except:
                    pass
                del COURIER_TIMERS[user_id]
            
            # Сообщение об отмене
            msg = f"""
❌ *СМЕНА ОТМЕНЕНА*

⏳ *Кулдаун:* 3 минуты

💡 *Что произошло:*
• Вы отменили смену
• Заработанное сохранено
• Отдых 3 минуты
"""
            
            if job["earnings"] > 0:
                msg += f"""
💰 *Заработано:* {format_balance(job['earnings'])}🌸
📦 *Доставок:* {job['done']}
"""
            
            # Обновляем сообщение
            if user_id in COURIER_MESSAGES:
                try:
                    bot.edit_message_text(
                        msg.strip(),
                        COURIER_MESSAGES[user_id]["chat_id"],
                        COURIER_MESSAGES[user_id]["message_id"],
                        parse_mode='Markdown'
                    )
                except:
                    pass
                
                del COURIER_MESSAGES[user_id]
            
            bot.answer_callback_query(call.id, "❌ Смена отменена, кулдаун 3 минуты", show_alert=True)
    
    except Exception as e:
        logging.error(f"Ошибка в callback курьера: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)

# === ОЧИСТКА СТАРЫХ ДАННЫХ ===
def cleanup_courier_data():
    """Очищает старые данные курьеров"""
    while True:
        time.sleep(300)  # Каждые 5 минут
        current_time = time.time()
        
        # Очищаем зависшие доставки (старше 30 минут)
        jobs_to_remove = []
        for user_id, job in COURIER_JOBS.items():
            if current_time - job.get("start_time", current_time) > 1800:  # 30 минут
                jobs_to_remove.append(user_id)
        
        for user_id in jobs_to_remove:
            if user_id in COURIER_JOBS:
                job = COURIER_JOBS[user_id]
                stats = get_courier_stats(user_id)
                
                # Начисляем заработанное
                if job["earnings"] > 0:
                    update_balance(user_id, job["earnings"])
                    stats["earned"] += job["earnings"]
                    stats["deliveries"] += job["done"]
                    stats["xp"] += job["done"]
                
                del COURIER_JOBS[user_id]
                
                if user_id in COURIER_TIMERS:
                    try:
                        COURIER_TIMERS[user_id].cancel()
                    except:
                        pass
                    del COURIER_TIMERS[user_id]
                
                if user_id in COURIER_MESSAGES:
                    del COURIER_MESSAGES[user_id]
                
                logging.info(f"Очищена зависшая доставка пользователя {user_id}")
        
        # Очищаем старые кулдауны (старше 1 часа)
        stats_to_clean = []
        for user_id, stats in COURIER_STATS.items():
            if stats.get("cooldown_until", 0) < current_time - 3600:  # Старше 1 часа
                stats["cooldown_until"] = 0

# Запускаем очистку в отдельном потоке
cleanup_thread = threading.Thread(target=cleanup_courier_data, daemon=True)
cleanup_thread.start()

# === КОМАНДЫ ДЛЯ АДМИНОВ ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('сброскурьер') and is_admin(message.from_user.id))
def handle_reset_courier(message):
    """Сброс статистики курьера (админ)"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Формат: сброскурьер @username")
        return
    
    target = parts[1].strip()
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
        except:
            bot.send_message(message.chat.id, "❌ Неверный ID")
            return
    
    # Сбрасываем статистику
    if user_id in COURIER_STATS:
        COURIER_STATS[user_id] = {
            "level": 1,
            "xp": 0,
            "deliveries": 0,
            "earned": 0,
            "cooldown_until": 0,
            "canceled_shifts": 0
        }
    
    if user_id in COURIER_JOBS:
        del COURIER_JOBS[user_id]
    
    if user_id in COURIER_TIMERS:
        try:
            COURIER_TIMERS[user_id].cancel()
        except:
            pass
        del COURIER_TIMERS[user_id]
    
    if user_id in COURIER_MESSAGES:
        del COURIER_MESSAGES[user_id]
    
    bot.send_message(message.chat.id, f"✅ Статистика курьера для {target} сброшена")
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
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        user_id = message.from_user.id
        
        # Отправляем главное меню
        markup = create_main_menu(message.chat.id)
        
        if message.chat.id > 0:
            welcome_text = "✨ Главное меню ✨\n\nВыберите действие:"
        else:
            welcome_text = f"👋 Главное меню!\n\nИспользуйте меню ниже для работы с ботом."
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_back: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")


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
            log_file.write(f"Баланс: {format_balance(balance)}🌸\n")
            log_file.write(f"В банке: {format_balance(bank_deposit)}🌸\n")
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
                log_file.write(f"\n🌸 СНЕЖНАЯ РАБОТА:\n")
                log_file.write(f"Прогресс: {job['clicks_done']}/150\n")
                log_file.write(f"Заработок: {format_balance(job['current_earnings'])}🌸\n")
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
                f"📊 Баланс: {format_balance(balance)}🌸\n"
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
            
            bot.answer_callback_query(call.id, "✅ Верно! +🌸" + format_balance(click_power))
            bot.edit_message_text(
                f"👻 Серия: {new_streak}\n🌸 Баланс: 🌸{format_balance(new_balance)}",
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

# === ДОБАВЛЕНИЕ КНОПКИ В МЕНЮ РАБОТЫ ===
def create_work_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    scam_button = KeyboardButton("👥 Скам")
    snow_button = KeyboardButton("🌸 Чистка снега")
    courier_button = KeyboardButton("🚚 Курьер")
    back_button = KeyboardButton("◀️ Назад")
    markup.add(scam_button, snow_button, courier_button, back_button)
    return markup




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

🌸 На вкладе: 🌸{format_balance(bank_deposit)}
📈 Проценты: 0.5% каждый час
🌸 Начисляются автоматически при любом действии

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
                       f"✅ Вы положили 🌸{format_balance(deposit_amount)} на вклад под 0.5% в час\n"
                       f"🌸 На вкладе: 🌸{format_balance(new_deposit)}\n"
                       f"🌸 Баланс: 🌸{format_balance(new_balance)}")
    
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
                       f"✅ Вы сняли 🌸{format_balance(withdraw_amount)} с вклада\n"
                       f"🌸 Осталось на вкладе: 🌸{format_balance(new_deposit)}\n"
                       f"🌸 Баланс: 🌸{format_balance(new_balance)}")
    
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
                           "Пример: ник ⛄СнежныйВолк🌸\n"
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
                       f"💰 Старая цена: {format_balance(old_price)}🌸\n"
                       f"💰 Новая цена: {format_balance(new_price)}🌸\n\n"
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
                    report += f"   {format_balance(old_price)}🌸 → {format_balance(new_price)}🌸\n"
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
                
                report += f"💰 Установка минимальной цены: {format_balance(min_price)}🌸\n\n"
                
                for house_id, house_info in HOUSE_SHOP.items():
                    old_price = house_info['price']
                    new_price = max(old_price, min_price)
                    
                    if new_price != old_price:
                        HOUSE_SHOP[house_id]['price'] = new_price
                        HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
                        HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
                        
                        report += f"🏡 {house_info['name']}:\n"
                        report += f"   {format_balance(old_price)}🌸 → {format_balance(new_price)}🌸\n"
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
                        f"💵 {format_balance(user_total)}🌸 |  {percentage:.4f}%")
        
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
                    value_text = f"⟨{format_balance(value)}🌸⟩"
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
        mode_buttons.append(InlineKeyboardButton("🌸 Снежки", callback_data="top_mode_balance"))
        mode_buttons.append(InlineKeyboardButton("👥 Скам", callback_data="top_mode_scam"))
    else:
        mode_buttons.append(InlineKeyboardButton("👥 Скам", callback_data="top_mode_scam"))
        mode_buttons.append(InlineKeyboardButton("🌸 Снежки", callback_data="top_mode_balance"))
    
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



def update_game_with_bonus(user_id, win_amount, game_name):
    try:
        if win_amount > 0:
            update_balance(user_id, win_amount)
            add_referral_win_bonus(user_id, win_amount, game_name)
    except:
        pass

# === ОБНОВЛЕННЫЙ ФОРМАТ СООБЩЕНИЙ ДЛЯ ВСЕХ ИГР ===

def format_game_result(user_id, username, first_name, is_win, amount, game_name=None):
    """Форматирует результат игры в новый стиль"""
    try:
        # Получаем имя для отображения
        if username:
            display_name = f"@{username}"
        else:
            display_name = first_name
        
        # Получаем текущий баланс
        balance = get_balance(user_id)
        
        # Форматируем сумму
        formatted_amount = format_balance(abs(amount))
        
        if is_win:
            # Для выигрыша используем ₽
            result_text = f"🎉 {display_name} выиграл {formatted_amount}🌸️!"
            balance_text = f"💰 Баланс: {format_balance(balance)}🌸"
        else:
            # Для проигрыша используем 🌸
            result_text = f"😢 {display_name} проиграл {formatted_amount}🌸!"
            balance_text = f"💰 Баланс: {format_balance(balance)}🌸"
        
        # ВСЕ внутри blockquote, баланс жирным
        full_message = f"<blockquote>{result_text}\n<b>{balance_text}</b></blockquote>"
        
        return full_message
    except Exception as e:
        logging.error(f"Ошибка форматирования результата игры: {e}")
        return f"❌ Ошибка"

# === ОБНОВЛЕННАЯ РУЛЕТКА ===
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
            
            # Новый формат сообщения
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
            # Новый формат сообщения для проигрыша
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

# === ОБНОВЛЕННЫЙ КУБИК ===
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
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎲')
        time.sleep(1)
        
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
            
            # Новый формат сообщения
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        else:
            # Новый формат сообщения для проигрыша
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОБНОВЛЕННЫЙ БАСКЕТБОЛ ===
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
        username = message.from_user.username
        first_name = message.from_user.first_name
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
        time.sleep(1)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 2.5
        
        if result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_game_with_bonus(user_id, win_amount, "🏀 Баскетбол")
            
            # Новый формат сообщения
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        else:
            # Новый формат сообщения для проигрыша
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОБНОВЛЕННЫЕ СЛОТЫ ===
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
        username = message.from_user.username
        first_name = message.from_user.first_name
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
        time.sleep(1)
        
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
            
            # Новый формат сообщения
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        else:
            # Новый формат сообщения для проигрыша
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОБНОВЛЕННЫЙ ФУТБОЛ ===
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
        username = message.from_user.username
        first_name = message.from_user.first_name
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
        time.sleep(1)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1.5
        
        if result == 3 or result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_game_with_bonus(user_id, win_amount, "⚽ Футбол")
            
            # Новый формат сообщения
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        else:
            # Новый формат сообщения для проигрыша
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОБНОВЛЕННЫЙ ДАРТС ===
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
        username = message.from_user.username
        first_name = message.from_user.first_name
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
                           f"❌ Недостаточно средств!\nНужно минимум: 🌸{format_balance(max_loss)}")
            return
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎯')
        time.sleep(1)
        
        result = dice_message.dice.value
        
        update_balance(user_id, -bet_amount)
        
        if result == 6:
            win_amount = bet_amount * 5
            update_game_with_bonus(user_id, win_amount, "🎯 Дартс")
            
            # Новый формат сообщения
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        
        elif result == 1:
            update_balance(user_id, -bet_amount)
            total_loss = bet_amount * 2
            
            # Новый формат сообщения для проигрыша
            result_message = format_game_result(user_id, username, first_name, False, total_loss)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        
        else:
            # Новый формат сообщения для проигрыша (обычного)
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

# === ОБНОВЛЕННЫЙ БОУЛИНГ ===
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
        username = message.from_user.username
        first_name = message.from_user.first_name
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
        time.sleep(1)
        
        result = dice_message.dice.value
        
        if result == 6:
            win_amount = bet_amount * 2
            update_game_with_bonus(user_id, win_amount, "🎳 Боулинг")
            
            # Новый формат сообщения
            result_message = format_game_result(user_id, username, first_name, True, win_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
        
        elif result == 5:
            update_balance(user_id, bet_amount)
            # Возврат ставки - отдельный формат
            new_balance = get_balance(user_id)
            result_text = f"⚖️ Осталась 1 кегля! Возврат ставки"
            balance_text = f"💰 Баланс: {format_balance(new_balance)}🌸"
            full_message = f"<blockquote>{result_text}\n<b>{balance_text}</b></blockquote>"
            bot.send_message(message.chat.id, full_message, parse_mode='HTML')
        
        else:
            # Новый формат сообщения для проигрыша
            result_message = format_game_result(user_id, username, first_name, False, bet_amount)
            bot.send_message(message.chat.id, result_message, parse_mode='HTML')
    
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
            bot.send_message(message.chat.id, f"❌ Недостаточно средств для создания чека! Нужно: 🌸{format_balance(total_amount)}")
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
        markup.add(InlineKeyboardButton("Активировать🌸", url=check_link))
        
        bot.send_message(message.chat.id,
                f"💳 Чек создан!\n"
                f"🌸 Сумма: 🌸{format_balance(amount)}\n"
                f"🔢 Активаций: {activations}\n",
                reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в создании чека: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании чека. Попробуйте снова.")

# === СИСТЕМА ЧЕФОВ (АДМИН ЧЕКИ) ===

@bot.message_handler(func=lambda message: message.text.lower().startswith('чеф ') and is_admin(message.from_user.id))
def handle_admin_check(message):
    """Создание чефа (админского чека)"""
    try:
        if not is_admin(message.from_user.id):
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
        
        # Генерируем уникальный код
        import random
        import string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Создаем чеф в БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO checks (code, amount, max_activations, created_by) VALUES (?, ?, ?, ?)',
            (code, amount, max_activations, message.from_user.id)
        )
        
        conn.commit()
        conn.close()
        
        check_link = f"https://t.me/{(bot.get_me()).username}?start={code}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Активировать🌸", url=check_link))
        
        check_text = f"""
<code>🧾 Мультичек</code>
<b>🌸 +{format_balance(amount)}</b>
<b>🔢 Кол-во:</b> <b>{max_activations}</b>
        """.strip()
        
        bot.send_message(
            message.chat.id, 
            check_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
        
        # Логируем создание чефа
        logging.info(f"Админ {message.from_user.id} создал чеф: {code} на {amount}🌸 × {max_activations}")
        
    except Exception as e:
        logging.error(f"Ошибка создания чефа: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании чека")

# === ОБНОВЛЕННАЯ АКТИВАЦИЯ С ОГРАНИЧЕНИЕМ 30 МИНУТ ===

def process_ref_or_check(user_id, username, first_name, ref_code):
    """Обработка реферальной ссылки или чека с ограничением времени"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Проверяем кулдаун на активацию чеков (30 минут)
        cursor.execute('''
            SELECT activated_at FROM check_activations 
            WHERE user_id = ? 
            ORDER BY activated_at DESC 
            LIMIT 1
        ''', (user_id,))
        
        last_activation = cursor.fetchone()
        
        if last_activation and last_activation[0]:
            import datetime
            last_time = datetime.datetime.strptime(last_activation[0], '%Y-%m-%d %H:%M:%S')
            current_time = datetime.datetime.now()
            time_diff = current_time - last_time
            
            # Проверяем прошло ли 30 минут
            if time_diff.total_seconds() < 1800:  # 1800 секунд = 30 минут
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
        
        # 2. Проверяем, является ли код чеком
        cursor.execute(
            'SELECT amount, max_activations, current_activations FROM checks WHERE code = ?',
            (ref_code,)
        )
        check_data = cursor.fetchone()
        
        if check_data:
            amount, max_activations, current_activations = check_data
            
            # Проверяем, не активировал ли уже этот чек
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
            
            # Активируем чек
            cursor.execute(
                'UPDATE checks SET current_activations = current_activations + 1 WHERE code = ?',
                (ref_code,)
            )
            
            cursor.execute(
                'INSERT INTO check_activations (user_id, check_code, activated_at) VALUES (?, ?, datetime("now"))',
                (user_id, ref_code)
            )
            
            cursor.execute(
                'UPDATE users SET balance = balance + ? WHERE user_id = ?',
                (amount, user_id)
            )
            
            conn.commit()
            
            # Получаем новый баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance = cursor.fetchone()[0]
            
            bot.send_message(user_id,
                f"🎉 *Чек активирован!*\n\n"
                f"💰 +{format_balance(amount)}🌸\n"
                f"💳 Баланс: {format_balance(new_balance)}🌸\n\n"
                f"⏰ Следующий чек можно активировать через 30 минут",
                parse_mode='Markdown'
            )
            
            logging.info(f"Пользователь {user_id} активировал чек {ref_code} на сумму {amount}🌸")
            
            # Удаляем полностью использованный чек
            if current_activations + 1 >= max_activations:
                cursor.execute('DELETE FROM checks WHERE code = ?', (ref_code,))
                conn.commit()
                logging.info(f"Чек {ref_code} полностью использован и удален")
            
            conn.close()
            return
        
        # 3. Проверяем реферальную ссылку (если код не чек)
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
                            f"💰 +{REFERRAL_BONUS}🌸\n\n"
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
        
        bot.send_message(message.chat.id, f"✅ Выдано 🌸{format_balance(amount)} пользователю {target}")
    
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
                bot.send_message(message.chat.id, f"❌ У пользователя недостаточно средств! Баланс: 🌸{format_balance(balance)}")
                conn.close()
                return
            
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, target_user_id))
            conn.commit()
            
            target_name = f"@{target_username}" if target_username else target_first_name
            
            bot.send_message(message.chat.id, 
                           f"✅ Забрано 🌸{format_balance(amount)} у пользователя {target_name}\n"
                           f"🌸 Новый баланс пользователя: 🌸{format_balance(balance - amount)}")
            
            try:
                bot.send_message(target_user_id, 
                               f"⚠️ У вас забрали 🌸{format_balance(amount)} администратором\n"
                               f"🌸 Новый баланс: 🌸{format_balance(balance - amount)}")
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
            bot.send_message(message.chat.id, "❌ Минимальная сумма: 10🌸")
            return
        
        if transfer_amount > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств!\n"
                           f"Ваш баланс: 🌸{format_balance(balance)}\n"
                           f"Нужно ещё: 🌸{format_balance(transfer_amount - balance)}")
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
                       f"💰 *Сумма:* 🌸{format_balance(transfer_amount)}\n"
                       f"📊 *Ваш баланс:* 🌸{format_balance(new_balance)}",
                       parse_mode='Markdown')
        
        try:
            bot.send_message(target_user_id,
                           f"🎉 *Вам перевели деньги!*\n\n"
                           f"👤 *От:* {sender_username}\n"
                           f"💰 *Сумма:* 🌸{format_balance(transfer_amount)}\n"
                           f"📊 *Ваш баланс:* 🌸{format_balance(target_balance)}",
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
                
            line = line.replace('🌸', '').replace('⛄', '').replace('🎄', '').replace('💰', '')
            
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

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ КОНКУРСОВ ===
USER_CONTESTS = {}
ACTIVE_CONTESTS = {}
CONTEST_PARTICIPANTS = {}

def parse_prizes_from_text(prizes_text, winners_count):
    """Парсит текст с призами"""
    try:
        prizes = []
        
        lines = prizes_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            line = line.replace('🌸', '').replace('⛄', '').replace('🎄', '').replace('💰', '')
            
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

def get_channel_username_from_id(channel_id):
    """Получить @username канала из ID"""
    try:
        chat = bot.get_chat(channel_id)
        if chat.username:
            return f"@{chat.username}"
        else:
            return f"ID: {channel_id}"
    except:
        return f"ID: {channel_id}"

# === ОБРАБОТЧИК ДЛЯ ПРОВЕРКИ ПОДПИСКИ НА КОНКУРС ===
@bot.callback_query_handler(func=lambda call: call.data.startswith('check_contest_sub_'))
def handle_check_contest_subscription(call):
    try:
        contest_id = call.data[19:]  # 'check_contest_sub_' = 19 символов
        user_id = call.from_user.id
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.answer_callback_query(call.id, "❌ Конкурс не найден", show_alert=True)
            return
        
        contest = ACTIVE_CONTESTS[contest_id]
        channel_id = contest.get('channel_id')
        channel_title = contest.get('channel_title', 'Канал')
        
        if not channel_id:
            bot.answer_callback_query(call.id, "❌ Ошибка конкурса", show_alert=True)
            return
        
        # Проверяем подписку
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['member', 'administrator', 'creator']:
                # Добавляем участника
                if contest_id not in CONTEST_PARTICIPANTS:
                    CONTEST_PARTICIPANTS[contest_id] = []
                
                if user_id in CONTEST_PARTICIPANTS[contest_id]:
                    bot.answer_callback_query(call.id, "✅ Вы уже участвуете!", show_alert=True)
                    return
                
                CONTEST_PARTICIPANTS[contest_id].append(user_id)
                
                participants_count = len(CONTEST_PARTICIPANTS.get(contest_id, []))
                max_participants = contest.get('max_participants', 100)
                
                # Показываем главное меню
                markup = create_main_menu(call.message.chat.id)
                
                bot.edit_message_text(
                    f"🎉 *ВЫ УЧАСТВУЕТЕ В КОНКУРСЕ!*\n\n"
                    f"📢 Канал: {channel_title}\n"
                    f"👥 Участников: {participants_count}/{max_participants}\n"
                    f"🏆 Победителей: {contest.get('winners_count', 1)}\n\n"
                    f"💡 Результаты будут объявлены позже!\n"
                    f"Удачи! 🍀",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✅ Вы успешно зарегистрированы!")
                
                # Уведомление организатору
                try:
                    creator_id = contest.get('creator_id')
                    if creator_id:
                        bot.send_message(
                            creator_id,
                            f"📈 *НОВЫЙ УЧАСТНИК КОНКУРСА!*\n\n"
                            f"📢 {channel_title}\n"
                            f"👤 ID: {user_id}\n"
                            f"👥 Всего участников: {participants_count}/{max_participants}",
                            parse_mode='Markdown'
                        )
                except:
                    pass
                
                logging.info(f"Пользователь {user_id} добавлен в конкурс {contest_id} после проверки подписки")
            else:
                bot.answer_callback_query(call.id, "❌ Вы не подписаны на канал", show_alert=True)
                
        except Exception as e:
            logging.error(f"Ошибка проверки подписки на конкурс: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки", show_alert=True)
            
    except Exception as e:
        logging.error(f"Ошибка в проверке подписки конкурса: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# === КОМАНДЫ ДЛЯ СОЗДАНИЯ И УПРАВЛЕНИЯ КОНКУРСАМИ ===

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
                    f"1 место - 1.000.000🌸\n"
                    f"2 место - 500.000🌸\n"
                    f"3 место - 250.000🌸",
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
                    bot_username = "FECTIZ_BOT"
                
                # Получаем username канала для ссылки
                channel_username = get_channel_username_from_id(contest_data['channel_id'])
                
                participate_link = f"https://t.me/{bot_username}?start={contest_id}"
                
                post_text = f"""🎊 *КОНКУРС!* 🎊

*📢 Канал:* {contest_data.get('channel_title', 'N/A')}
*👥 Участников:* {contest_data.get('max_participants', 'N/A')}
*🏆 Победителей:* {contest_data.get('winners_count', 'N/A')}

*💰 ПРИЗОВОЙ ФОНД:*
{contest_data.get('prizes_text', 'N/A')}

*👤 Организатор:* {contest_data.get('creator_name', 'N/A')}

*❗ Для участия:*
1. Нажмите кнопку ниже
2. Подпишитесь на канал (если требуется)
3. Ждите результатов!"""
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎯 УЧАСТВОВАТЬ", url=participate_link))
                
                # Публикуем в канале
                bot.send_message(
                    contest_data['channel_id'],
                    post_text,
                    parse_mode='Markdown',
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
                
                # Сохраняем конкурс
                ACTIVE_CONTESTS[contest_id] = {
                    **contest_data,
                    "contest_id": contest_id,
                    "created_at": time.time(),
                    "status": "active",
                    "published": True,
                    "channel_username": channel_username
                }
                
                CONTEST_PARTICIPANTS[contest_id] = []
                
                # Отправляем отчет организатору
                bot.edit_message_text(
                    f"✅ *КОНКУРС ОПУБЛИКОВАН!*\n\n"
                    f"📢 Канал: {contest_data.get('channel_title', 'N/A')}\n"
                    f"🔗 Ссылка для участия:\n`{participate_link}`\n\n"
                    f"👥 Участников: 0/{contest_data.get('max_participants', 'N/A')}\n"
                    f"🏆 Победителей: {contest_data.get('winners_count', 'N/A')}\n"
                    f"🆔 ID конкурса: `{contest_id}`\n\n"
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
                    
                    winners_text += f"{i}. {username} - 🌸{format_balance(prize_amount)}\n"
                    
                    try:
                        bot.send_message(
                            winner_id,
                            f"🎉 *ВЫ ВЫИГРАЛИ В КОНКУРСЕ!*\n\n"
                            f"🏆 Место: #{i}\n"
                            f"💰 Приз: 🌸{format_balance(prize_amount)}\n"
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
        winners_text += f"\n💰 Всего выдано: 🌸{format_balance(total_awarded)}"
        
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
        report += f"💸 Общая сумма: 🌸{format_balance(total_awarded)}\n"
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

def cleanup_old_contests():
    """Очистка старых конкурсов"""
    while True:
        time.sleep(86400)  # Каждые 24 часа
        current_time = time.time()
        
        to_remove = []
        for contest_id, contest in ACTIVE_CONTESTS.items():
            if contest.get('status') in ['finished', 'cancelled']:
                if current_time - contest.get('created_at', current_time) > 604800:  # 7 дней
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

# Запускаем очистку в отдельном потоке
contest_cleanup_thread = threading.Thread(target=cleanup_old_contests, daemon=True)
contest_cleanup_thread.start()

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