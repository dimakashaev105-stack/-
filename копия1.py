import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import random
import os
import re
import shutil
from datetime import datetime
import threading
import logging

BOT_TOKEN = "8287060486:AAH0tRlAnM2s4rYXKQRDlIB-XMZOhTcMuyI"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

ADMIN_IDS = [8139807344, 5255608302]

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
            last_bonus INTEGER DEFAULT 0
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
        
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        
        has_nickname = False
        for col in columns:
            if col[1] == 'nickname':
                has_nickname = True
                break
        
        if not has_nickname:
            cursor.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
            logging.info("✅ Добавлена колонка nickname")
        
        conn.commit()
        logging.info("✅ База данных инициализирована")
        
        cursor.execute('PRAGMA integrity_check')
        integrity = cursor.fetchone()[0]
        if integrity == 'ok':
            logging.info("✅ Проверка целостности БД: OK")
        else:
            logging.warning(f"⚠️ Проблемы с целостностью БД: {integrity}")
            
    except sqlite3.Error as e:
        logging.error(f"❌ Ошибка инициализации БД: {e}")
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

def get_balance(user_id):
    calculate_interest(user_id)
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def notify_interest(user_id, interest_amount, bank_deposit):
    try:
        bot.send_message(
            user_id,
            f"🏦 *Проценты начислены!*\n\n"
            f"💎 На вкладе: {format_balance(bank_deposit)}❄️\n"
            f"📈 Начислено: +{format_balance(interest_amount)}❄️\n"
            f"⏳ Следующие через час",
            parse_mode='Markdown'
        )
        logging.info(f"Пользователю {user_id} начислены проценты: {interest_amount}❄️")
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления для {user_id}: {e}")

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
                    notify_interest(user_id, interest, bank_deposit)
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление для {user_id}: {e}")
    
    conn.close()

@bot.message_handler(func=lambda message: message.text.lower() == 'проценты')
def handle_check_interest(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        calculate_interest(user_id)
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT bank_deposit, balance, last_interest_calc 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            bank_deposit, balance, last_calc = result
            
            message_text = "🏦 *Проценты*\n\n"
            
            if bank_deposit > 0:
                current_time = time.time()
                
                if last_calc:
                    if isinstance(last_calc, str):
                        try:
                            last_calc_time = datetime.strptime(last_calc, '%Y-%m-%d %H:%M:%S').timestamp()
                        except:
                            last_calc_time = current_time - 3600
                    else:
                        last_calc_time = last_calc
                    
                    time_since_last = current_time - last_calc_time
                    time_to_next = 3600 - time_since_last
                    
                    if time_to_next > 0:
                        minutes = int(time_to_next // 60)
                        seconds = int(time_to_next % 60)
                        message_text += f"⏳ До следующих: {minutes}м {seconds}с\n"
                    else:
                        message_text += "✅ Следующие скоро\n"
                
                interest_per_hour = int(bank_deposit * 0.005)
                
                message_text += f"\n💎 На вкладе: {format_balance(bank_deposit)}❄️\n"
                message_text += f"📈 В час: +{format_balance(interest_per_hour)}❄️\n"
                message_text += f"💰 Баланс: {format_balance(balance)}❄️\n"
                message_text += f"🎯 Ставка: 0.5%/час\n\n"
                message_text += "*Начисляются автоматически каждый час*"
                
            else:
                message_text += "💎 *Вклада нет*\n\n"
                message_text += "📝 Для получения процентов:\n"
                message_text += "1. Сделайте вклад\n"
                message_text += "2. Получайте +0.5% каждый час\n\n"
                message_text += "💰 *Пример:*\n"
                message_text += "Вклад: 1.000.000❄️\n"
                message_text += "В час: +5.000❄️\n"
                message_text += "В день: +120.000❄️\n\n"
                message_text += "🔧 *Команда:* `вклад сумма`"
            
            bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
            
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
        
        conn.close()
    
    except Exception as e:
        logging.error(f"Ошибка в handle_check_interest: {e}")
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

def calculate_mining_income(video_cards):
    base_income = 25000000
    return base_income * (2 ** (video_cards - 1)) if video_cards > 0 else 0

def calculate_video_card_price(video_cards):
    base_price = 500000000
    return base_price * (2 ** video_cards)

def create_mining_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("❄️ Собрать", callback_data="mining_collect"),
        InlineKeyboardButton("🖥 Купить", callback_data="mining_buy")
    )
    return markup

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

def create_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    markup.add(
        KeyboardButton("👤 Профиль"),
        KeyboardButton("🖥 Майнинг"),
        KeyboardButton("🏦 Банк"),
        KeyboardButton("🎮 Игры"),
        KeyboardButton("💼 Работа"),
        KeyboardButton("🏆 Топ"),
        KeyboardButton("🏠 Дом"),
        KeyboardButton("🎁 Бонус")
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
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        ref_code = None
        if len(message.text.split()) > 1:
            ref_code = message.text.split()[1].strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            is_new_user = True
            
            if ref_code:
                pending_ref_codes[user_id] = ref_code
            
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
                           f"🔒 Решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом.")
            return
        
        captcha_passed = user_data[0]
        
        if captcha_passed == 0:
            if ref_code:
                pending_ref_codes[user_id] = ref_code
            
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом.")
            return
        
        conn.close()
        
        if ref_code:
            process_ref_or_check(user_id, username, first_name, ref_code)
        
        markup = create_main_menu()
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)
    
    except Exception as e:
        logging.error(f"Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

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
                bot.send_message(user_id, "❌ Чек уже активирован!")
            elif current_activations >= max_activations:
                bot.send_message(user_id, "❌ Чек использован!")
            else:
                cursor.execute('UPDATE checks SET current_activations = current_activations + 1 WHERE code = ? AND current_activations < max_activations', (ref_code,))
                
                if cursor.rowcount > 0:
                    cursor.execute('INSERT OR IGNORE INTO check_activations (user_id, check_code) VALUES (?, ?)', (user_id, ref_code))
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
                    conn.commit()
                    
                    bot.send_message(user_id, f"🎉 Чек активирован! +{format_balance(amount)}❄️")
                    logging.info(f"Пользователь {user_id} активировал чек {ref_code} на сумму {amount}")
                else:
                    bot.send_message(user_id, "❌ Чек уже активирован!")
            
            conn.close()
            return
        
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                
                cursor.execute('SELECT user_id, username, first_name FROM users WHERE user_id = ? AND is_banned = 0', (referrer_id,))
                referrer_data = cursor.fetchone()
                
                if referrer_data:
                    if referrer_id == user_id:
                        bot.send_message(user_id, "❌ Нельзя пригласить себя!")
                        conn.close()
                        return
                    
                    cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,))
                    existing_referrer = cursor.fetchone()
                    
                    if existing_referrer and existing_referrer[0]:
                        bot.send_message(user_id, "❌ Реферер уже есть!")
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
                            f"Всего рефералов: {get_referral_count(referrer_id)}"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка уведомления реферера: {e}")
                    
                    bot.send_message(user_id, f"✅ Регистрация по приглашению!")
                    
                    logging.info(f"Пользователь {user_id} зарегистрирован по реферальной ссылке от {referrer_id}")
                    
                else:
                    bot.send_message(user_id, "❌ Ссылка недействительна!")
                
            except ValueError:
                bot.send_message(user_id, "❌ Неверный формат ссылки!")
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
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            ref_code = result[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
            ref_count = cursor.fetchone()[0]
            
            REFERRAL_BONUS = 888
            earned = ref_count * REFERRAL_BONUS
            
            ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
            
            message_text = f"👨🏻‍💻 Ваша ссылка:\n{ref_link}\n\n"
            message_text += f"📊 Статистика:\n"
            message_text += f"👥 Рефералов: {ref_count}\n"
            message_text += f"💰 Заработано: {format_balance(earned)}❄️\n\n"
            message_text += "💡 Приглашайте друзей!"
            
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "❌ Код не найден")
        
        conn.close()
    except Exception as e:
        print(f"Ошибка в handle_scam: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

def combine_house_with_snowman(house_image_path, snowman_image_path="g.png"):
    """Накладывает снеговика (g.png) поверх дома"""
    try:
        # Проверяем и скачиваем g.png если его нет
        if not os.path.exists(snowman_image_path):
            try:
                import requests
                # URL из вашего репозитория
                url = "https://raw.githubusercontent.com/dimakashaev105-stack/-/main/g.png"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    with open(snowman_image_path, "wb") as f:
                        f.write(response.content)
                    logging.info(f"✅ {snowman_image_path} скачан с GitHub")
                else:
                    logging.warning(f"Не удалось скачать {snowman_image_path}")
                    return None
            except Exception as e:
                logging.error(f"Ошибка скачивания {snowman_image_path}: {e}")
                return None
        
        # Проверяем наличие дома
        if not os.path.exists(house_image_path):
            logging.error(f"Файл дома не найден: {house_image_path}")
            return None
        
        # Открываем дом (фон)
        house_img = Image.open(house_image_path).convert("RGBA")
        
        # Открываем снеговика (прозрачный PNG)
        snowman_img = Image.open(snowman_image_path).convert("RGBA")
        
        # Получаем размеры дома
        house_width, house_height = house_img.size
        
        # Масштабируем снеговика до размеров дома
        snowman_img = snowman_img.resize((house_width, house_height), Image.LANCZOS)
        
        # Создаем новое изображение с домом как фон
        result_img = Image.new("RGBA", (house_width, house_height))
        result_img.paste(house_img, (0, 0))
        
        # Накладываем снеговика поверх дома
        result_img = Image.alpha_composite(result_img, snowman_img)
        
        return result_img
        
    except Exception as e:
        logging.error(f"Ошибка наложения снеговика на дом: {e}")
        return None

# Также добавьте функцию для скачивания изображений домов если их нет
def ensure_image_exists(image_path):
    """Проверяет наличие изображения и скачивает если нужно"""
    if os.path.exists(image_path):
        return True
    
    try:
        import requests
        # Получаем имя файла
        filename = os.path.basename(image_path)
        # URL для дома (предполагаем что дома тоже в репозитории)
        url = f"https://raw.githubusercontent.com/dimakashaev105-stack/-/main/{filename}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # Создаем папку если нужно
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            with open(image_path, "wb") as f:
                f.write(response.content)
            logging.info(f"✅ {filename} скачан с GitHub")
            return True
        else:
            logging.warning(f"Не удалось скачать {filename}")
            return False
    except Exception as e:
        logging.error(f"Ошибка скачивания {image_path}: {e}")
        return False

# В функции handle_me обновите часть с домом:
@bot.message_handler(func=lambda message: message.text.lower() == "👤 профиль")
def handle_me(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        calculate_interest(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT first_name, balance, video_cards, bank_deposit FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            first_name, balance, video_cards, bank_deposit = result
            
            message_text = f"👤 {first_name}\n"
            message_text += f"💰 {format_balance(balance)}❄️\n"
            message_text += f"🖥 {video_cards} видеокарт\n"
            message_text += f"🏦 {format_balance(bank_deposit)}❄️ (+0.5%/час)"
            
            current_house = get_current_house(user_id)
            
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                house_image = house_info.get('image')
                
                message_text += f"\n🏠 {house_name}"
                
                if house_image:
                    # Проверяем наличие изображения дома
                    ensure_image_exists(house_image)
                    
                    if os.path.exists(house_image):
                        # Создаем изображение дома со снеговиком
                        combined_image = combine_house_with_snowman(house_image)
                        
                        if combined_image:
                            # Конвертируем в байты
                            img_byte_arr = io.BytesIO()
                            combined_image.save(img_byte_arr, format='PNG')
                            img_byte_arr.seek(0)
                            
                            bot.send_photo(message.chat.id, img_byte_arr, caption=message_text)
                            conn.close()
                            return
                        else:
                            # Если не удалось наложить, отправляем просто дом
                            try:
                                with open(house_image, 'rb') as img_file:
                                    bot.send_photo(message.chat.id, img_file, caption=message_text)
                                    conn.close()
                                    return
                            except:
                                pass
                    else:
                        # Если файла дома нет, проверяем есть ли он в репозитории
                        filename = os.path.basename(house_image)
                        github_url = f"https://raw.githubusercontent.com/dimakashaev105-stack/-/main/{filename}"
                        try:
                            import requests
                            response = requests.get(github_url, timeout=5)
                            if response.status_code == 200:
                                # Сразу отправляем из памяти
                                img_byte_arr = io.BytesIO(response.content)
                                bot.send_photo(message.chat.id, img_byte_arr, caption=message_text)
                                conn.close()
                                return
                        except:
                            pass
            
            conn.close()
            
            # Если нет дома или ошибка, отправляем только текст
            bot.send_message(message.chat.id, message_text)
            
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
    
    except Exception as e:
        logging.error(f"Ошибка в handle_me: {e}", exc_info=True)
        
        try:
            if 'conn' in locals():
                conn.close()
        except:
            pass
            
        bot.send_message(message.chat.id, "❌ Ошибка.")

user_houses = {}
HOUSE_SHOP = {}

def load_house_shop():
    global HOUSE_SHOP
    try:
        if os.path.exists('house_shop.json'):
            import json
            with open('house_shop.json', 'r', encoding='utf-8') as f:
                HOUSE_SHOP = json.load(f)
            logging.info(f"✅ Загружен магазин: {len(HOUSE_SHOP)} домов")
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
            InlineKeyboardButton("🏠 Текущий", callback_data="house_current"),
            InlineKeyboardButton("❓ Помощь", callback_data="house_help")
        )
        
        current_house = get_current_house(user_id)
        
        if current_house:
            house_info = HOUSE_SHOP.get(current_house, {})
            house_name = house_info.get('name', 'Неизвестный дом')
            response = f"🏠 *Ваш дом*\n\n🏡 {house_name}\n\nВыберите действие:"
        else:
            response = "🏠 *Ваш дом*\n\n🚫 Дома нет\n\n🛒 Купите в магазине:"
        
        bot.send_message(message.chat.id, response, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в доме: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

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
            return False, "Дом не найден"
        
        houses = get_user_houses(user_id)
        for house, _ in houses:
            if house == house_id:
                return False, "Уже есть"
        
        price = house_info['price']
        balance = get_balance(user_id)
        
        if balance < price:
            return False, f"Нужно: {format_balance(price)}❄️"
        
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
        
        return True, "✅ Куплен!"
        
    except Exception as e:
        logging.error(f"Ошибка покупки дома: {e}")
        return False, "❌ Ошибка"

def set_current_house(user_id, house_id):
    try:
        houses = get_user_houses(user_id)
        has_house = False
        for house, _ in houses:
            if house == house_id:
                has_house = True
                break
        
        if not has_house:
            return False, "Нет дома"
        
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
        
        return True, "✅ Установлен!"
        
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
                           "❌ Формат: дом [цена] [файл.png]\n"
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
                       f"✅ Дом добавлен!\n\n"
                       f"🏡 {house_name}\n"
                       f"💰 {format_balance(price)}❄️\n"
                       f"🖼 {filename}\n"
                       f"🔑 {house_id}")
        
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
    
    markup.row(InlineKeyboardButton(f"💰 Купить {format_balance(house_info.get('price', 0))}❄️", 
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
                "🛒 *Магазин домов*\n\n🚫 Нет домов.",
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
        
        caption = f"🛒 *Магазин домов*\n\n"
        caption += f"🏡 {house_info.get('name', 'Неизвестный дом')}\n"
        caption += f"💰 {format_balance(house_info.get('price', 0))}❄️\n"
        caption += f"📊 {page}/{total_houses}\n\n"
        caption += "💡 Нажмите '💰 Купить'"
        
        if house_image and os.path.exists(house_image):
            try:
                if os.path.exists("g.png"):
                    base_img = Image.open("g.png").convert("RGBA")
                    house_img = Image.open(house_image).convert("RGBA")
                    
                    width, height = base_img.size
                    house_img = house_img.resize((width, height), Image.LANCZOS)
                    
                    combined = Image.alpha_composite(base_img, house_img)
                    
                    img_byte_arr = io.BytesIO()
                    combined.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    bot.send_photo(
                        call.message.chat.id,
                        img_byte_arr,
                        caption=caption,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                    
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                    except:
                        pass
                    
                else:
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
                try:
                    bot.edit_message_text(
                        caption,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                except:
                    bot.send_message(
                        call.message.chat.id,
                        caption,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
        else:
            try:
                bot.edit_message_text(
                    caption,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_house_shop_keyboard(page),
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    caption,
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
                f"❌ Нужно: {format_balance(house_price)}❄️",
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
                caption += f"🏡 {current_house_info.get('name', 'Неизвестный дом')}\n"
                caption += f"💰 {format_balance(current_house_info.get('price', 0))}❄️\n"
                caption += f"📊 {page}/{total_houses}\n\n"
                caption += "✅ Куплен! Выберите в шкафе"
                
                house_image = current_house_info.get('image')
                if house_image and os.path.exists(house_image):
                    try:
                        if os.path.exists("g.png"):
                            base_img = Image.open("g.png").convert("RGBA")
                            house_img = Image.open(house_image).convert("RGBA")
                            
                            width, height = base_img.size
                            house_img = house_img.resize((width, height), Image.LANCZOS)
                            
                            combined = Image.alpha_composite(base_img, house_img)
                            
                            img_byte_arr = io.BytesIO()
                            combined.save(img_byte_arr, format='PNG')
                            img_byte_arr.seek(0)
                            
                            bot.edit_message_media(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                media=telebot.types.InputMediaPhoto(
                                    media=img_byte_arr,
                                    caption=caption,
                                    parse_mode='Markdown'
                                ),
                                reply_markup=create_house_shop_keyboard(page)
                            )
                        else:
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
            
            bot.answer_callback_query(call.id, f"✅ Куплен '{house_name}'!")
            
            house_image = house_info.get('image')
            if house_image and os.path.exists(house_image):
                try:
                    if os.path.exists("g.png"):
                        base_img = Image.open("g.png").convert("RGBA")
                        house_img = Image.open(house_image).convert("RGBA")
                        
                        width, height = base_img.size
                        house_img = house_img.resize((width, height), Image.LANCZOS)
                        
                        combined = Image.alpha_composite(base_img, house_img)
                        
                        img_byte_arr = io.BytesIO()
                        combined.save(img_byte_arr, format='PNG')
                        img_byte_arr.seek(0)
                        
                        bot.send_photo(
                            call.message.chat.id,
                            img_byte_arr,
                            caption=f"🎉 Новый дом!\n\n"
                                  f"🏡 {house_name}\n"
                                  f"💰 {format_balance(house_price)}❄️\n\n"
                                  f"💡 Выберите в 🚪 Шкаф",
                            parse_mode='Markdown'
                        )
                    else:
                        with open(house_image, 'rb') as img_file:
                            bot.send_photo(
                                call.message.chat.id,
                                img_file,
                                caption=f"🎉 Новый дом!\n\n"
                                      f"🏡 {house_name}\n"
                                      f"💰 {format_balance(house_price)}❄️\n\n"
                                      f"💡 Выберите в 🚪 Шкаф",
                                parse_mode='Markdown'
                            )
                except:
                    pass
        else:
            bot.answer_callback_query(call.id, message, show_alert=True)
            
    except Exception as e:
        logging.error(f"Ошибка покупки дома: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

def create_wardrobe_keyboard(user_id, page=1):
    markup = InlineKeyboardMarkup(row_width=2)
    
    houses = get_user_houses(user_id)
    total_houses = len(houses)
    
    if total_houses == 0:
        markup.row(InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"))
        markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
        return markup
    
    total_pages = total_houses
    page = max(1, min(page, total_houses))
    
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
            markup.row(InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"))
            markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
            
            bot.edit_message_text(
                "🚪 *Шкаф*\n\n🚫 Домов нет.\n\n🛒 Купите в магазине!",
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
        
        caption = f"🚪 *Шкаф*\n\n"
        caption += f"🏡 {house_info.get('name', 'Неизвестный дом')}\n"
        caption += f"📊 {page}/{total_houses}\n"
        
        if house_id == current_house:
            caption += f"\n✅ *Текущий дом*\n"
        else:
            caption += f"\n💡 Нажмите '✅ Выбрать'"
        
        if house_image and os.path.exists(house_image):
            try:
                if os.path.exists("g.png"):
                    base_img = Image.open("g.png").convert("RGBA")
                    house_img = Image.open(house_image).convert("RGBA")
                    
                    width, height = base_img.size
                    house_img = house_img.resize((width, height), Image.LANCZOS)
                    
                    combined = Image.alpha_composite(base_img, house_img)
                    
                    img_byte_arr = io.BytesIO()
                    combined.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    bot.send_photo(
                        call.message.chat.id,
                        img_byte_arr,
                        caption=caption,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                    
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                    except:
                        pass
                    
                else:
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
                try:
                    bot.edit_message_text(
                        caption,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                except:
                    bot.send_message(
                        call.message.chat.id,
                        caption,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
        else:
            try:
                bot.edit_message_text(
                    caption,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_wardrobe_keyboard(user_id, page),
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    caption,
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
                        if os.path.exists("g.png"):
                            base_img = Image.open("g.png").convert("RGBA")
                            house_img = Image.open(house_image).convert("RGBA")
                            
                            width, height = base_img.size
                            house_img = house_img.resize((width, height), Image.LANCZOS)
                            
                            combined = Image.alpha_composite(base_img, house_img)
                            
                            img_byte_arr = io.BytesIO()
                            combined.save(img_byte_arr, format='PNG')
                            img_byte_arr.seek(0)
                            
                            bot.send_photo(
                                call.message.chat.id,
                                img_byte_arr,
                                caption=f"🏠 *Текущий дом*\n\n"
                                      f"🏡 {house_name}\n\n"
                                      f"💡 Смените в 🚪 Шкаф",
                                parse_mode='Markdown'
                            )
                        else:
                            with open(house_image, 'rb') as img_file:
                                bot.send_photo(
                                    call.message.chat.id,
                                    img_file,
                                    caption=f"🏠 *Текущий дом*\n\n"
                                          f"🏡 {house_name}\n\n"
                                          f"💡 Смените в 🚪 Шкаф",
                                    parse_mode='Markdown'
                                )
                    except:
                        bot.send_message(
                            call.message.chat.id,
                            f"🏠 *Текущий дом*\n\n"
                            f"🏡 {house_name}",
                            parse_mode='Markdown'
                        )
                else:
                    bot.send_message(
                        call.message.chat.id,
                        f"🏠 *Текущий дом*\n\n"
                        f"🏡 {house_name}",
                        parse_mode='Markdown'
                    )
            else:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"))
                
                bot.send_message(
                    call.message.chat.id,
                    "🚫 Дома нет!\n\n🛒 Купите в магазине:",
                    reply_markup=markup
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data == "house_help":
            help_text = (
                "🏠 *Система домов*\n\n"
                "🛒 *Магазин* - Покупайте дома\n"
                "🚪 *Шкаф* - Управляйте домами\n"
                "🏠 *Текущий дом* - Активный дом\n\n"
                "*Как использовать:*\n"
                "1. Купите дом в магазине\n"
                "2. Выберите в шкафе\n"
                "3. Дом в профиле\n\n"
                "*Для администраторов:*\n"
                "`дом [цена] [файл.png]` - добавить дом"
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
                InlineKeyboardButton("🏠 Текущий", callback_data="house_current"),
                InlineKeyboardButton("❓ Помощь", callback_data="house_help")
            )
            
            current_house = get_current_house(user_id)
            
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                response = f"🏠 *Ваш дом*\n\n🏡 {house_name}\n\nВыберите действие:"
            else:
                response = "🏠 *Ваш дом*\n\n🚫 Дома нет\n\n🛒 Купите в магазине:"
            
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
                    
                    caption = f"🚪 *Шкаф*\n\n"
                    caption += f"🏡 {house_info.get('name', 'Неизвестный дом')}\n"
                    caption += f"📊 {page}/{total_houses}\n"
                    caption += f"\n✅ *Текущий дом!*"
                    
                    bot.edit_message_caption(
                        caption=caption,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                    
                except Exception as e:
                    logging.error(f"Ошибка обновления шкафа: {e}")
                    pass
                
                bot.answer_callback_query(call.id, f"✅ Выбран '{house_info['name']}'!")
                
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

@bot.message_handler(func=lambda message: message.text == "🖥 Майнинг")
def handle_mining(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        message_text = "🖥 Майнинг ферма\n\n"
        message_text += "⏳ В разработке!\n"
        message_text += "Скоро здесь будет функционал!\n\n"
        message_text += "💡 Следите за обновлениями!"
        
        bot.send_message(message.chat.id, message_text)
    
    except Exception as e:
        print(f"Ошибка в handle_mining: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('mining_'))
def mining_callback_handler(call):
    if is_spam(call.from_user.id):
        bot.answer_callback_query(call.id, "⏳ Слишком быстро!")
        return
        
    user_id = call.from_user.id
    
    banned, reason = is_banned(user_id)
    if banned:
        bot.answer_callback_query(call.id, "🚫 Вы забанены!")
        return
    
    bot.answer_callback_query(call.id, "⏳ В разработке!")
    
    message_text = "🖥 Майнинг ферма\n\n"
    message_text += "⏳ В разработке!\n"
    message_text += "Скоро здесь будет функционал!\n\n"
    message_text += "💡 Следите за обновлениями!"
    
    try:
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id
        )
    except:
        bot.send_message(call.message.chat.id, message_text)

def create_work_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    clicker_button = KeyboardButton("....")
    scam_button = KeyboardButton("👥 Скам")
    snow_button = KeyboardButton("❄️ Чистка снега")
    back_button = KeyboardButton("◀️ Назад")
    markup.add(clicker_button, scam_button, snow_button, back_button)
    return markup

@bot.message_handler(func=lambda message: message.text == "💼 Работа")
def handle_work(message):
    if is_spam(message.from_user.id):
        return
    
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
        return
        
    bot.send_message(message.chat.id, "💼 Заработок:", reply_markup=create_work_menu())

@bot.message_handler(func=lambda message: message.text == "◀️ Назад")
def handle_back(message):
    if is_spam(message.from_user.id):
        return
    
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
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
                           "`лог all`", 
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
                bot.send_message(message.chat.id, "❌ Неверный ID.")
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
                f"📋 Логи\n"
                f"👤 ID: {user_id}\n"
                f"📛 {first_name}\n"
                f"📊 {format_balance(balance)}❄️\n"
                f"📅 {registered_at}\n"
                f"⏰ {last_activity}"
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
        
        bot.send_message(message.chat.id, "⏳ Подготовка...")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        log_filename = f"all_logs_{timestamp}.txt"
        zip_filename = f"logs_{timestamp}.zip"
        
        shutil.copy2('bot.log', log_filename)
        
        import zipfile
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(log_filename, os.path.basename(log_filename))
        
        with open(zip_filename, 'rb') as zip_file:
            bot.send_document(
                message.chat.id,
                zip_file,
                caption=f"📦 Логи бота\n📅 {timestamp}",
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
            InlineKeyboardButton("✅ ДА", callback_data="clear_logs_confirm"),
            InlineKeyboardButton("❌ ОТМЕНА", callback_data="clear_logs_cancel")
        )
        
        if os.path.exists('bot.log'):
            size_mb = os.path.getsize('bot.log') / (1024 * 1024)
            size_info = f"📁 Размер: {size_mb:.2f} MB\n"
        else:
            size_info = ""
        
        bot.send_message(
            message.chat.id,
            f"⚠️ ОЧИСТКА ЛОГОВ\n\n"
            f"{size_info}"
            f"Удалить логи старше 7 дней?\n"
            f"Оставить 1000 строк\n"
            f"Создать бэкап",
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
                    "Оставлены последние 1000 строк.",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.edit_message_text(
                    "❌ Ошибка",
                    call.message.chat.id,
                    call.message.message_id
                )
                
        elif call.data == "clear_logs_cancel":
            bot.answer_callback_query(call.id, "❌ Отменено")
            bot.edit_message_text(
                "❌ Отменено",
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
                    bot.send_message(message.chat.id, "❄️ Уборка устарела\nНачните заново")
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
            f"❄️ Уборка снега\n\n"
            f"🎯 100 кликов\n"
            f"💰 {format_balance(earnings)}❄️\n"
            f"📈 +50❄️\n"
            f"❗ -100❄️ за ошибку\n"
            f"🏆 {completed_jobs}"
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
        f"❌ {job['wrong_clicks']}"
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
                    f"✅ Уборка завершена!\n\n"
                    f"🎯 100 кликов\n"
                    f"❌ {wrong_clicks} ошибок\n"
                    f"💰 +{format_balance(earnings)}❄️\n"
                    f"📊 {format_balance(new_balance)}❄️\n"
                    f"🏆 {completed_count}\n\n"
                    f"⏳ Следующая через 3 мин"
                )
                bot.answer_callback_query(call.id, f"✅ +{format_balance(earnings)}❄️")
            else:
                result_msg = (
                    f"⚠️ Уборка завершена\n\n"
                    f"🎯 100 кликов\n"
                    f"❌ {wrong_clicks} ошибок\n"
                    f"💸 0❄️\n"
                    f"📊 {format_balance(new_balance)}❄️\n\n"
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
    
    message_text = "❄️ Статистика\n\n"
    
    if user_id in SNOW_JOBS:
        job = SNOW_JOBS[user_id]
        
        message_text += f"📊 Активная уборка:\n"
        message_text += f"🎯 {job['clicks_done']}/150\n"
        message_text += f"💰 {format_balance(job['current_earnings'])}❄️\n"
        message_text += f"❌ {job['wrong_clicks']} ошибок\n"
        message_text += f"🏆 {job['completed']} уборок"
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

@bot.message_handler(func=lambda message: message.text == "🏦 Банк")
def handle_bank(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        bank_deposit = get_bank_deposit(user_id)
        
        bank_text = f"""🏦 Банк

❄️ На вкладе: {format_balance(bank_deposit)}❄️
📈 Проценты: 0.5% каждый час
❄️ Начисляются автоматически

📝 Команды:
• вклад [сумма] - положить под 0.5% в час
• снять [сумма] - забрать с вклада"""
        
        bot.send_message(message.chat.id, bank_text)
    except Exception as e:
        print(f"Ошибка в handle_bank: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('вклад '))
def handle_deposit(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
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
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
            return
        
        update_balance(user_id, -deposit_amount)
        update_bank_deposit(user_id, deposit_amount)
        
        new_balance = get_balance(user_id)
        new_deposit = get_bank_deposit(user_id)
        
        bot.send_message(message.chat.id,
                       f"✅ Положили {format_balance(deposit_amount)}❄️ под 0.5% в час\n"
                       f"❄️ На вкладе: {format_balance(new_deposit)}❄️\n"
                       f"❄️ Баланс: {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_deposit: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('снять '))
def handle_withdraw(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
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
                       f"✅ Сняли {format_balance(withdraw_amount)}❄️ с вклада\n"
                       f"❄️ Осталось: {format_balance(new_deposit)}❄️\n"
                       f"❄️ Баланс: {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_withdraw: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

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
                           "❌ Формат: ник [новый ник]\n"
                           "Пример: ник ⛄СнежныйВолк❄️")
            return
        
        new_nickname = parts[1].strip()
        
        if len(new_nickname) > 32:
            bot.send_message(message.chat.id, "❌ Макс. 32 символа")
            return
        
        if len(new_nickname) < 2:
            bot.send_message(message.chat.id, "❌ Мин. 2 символа")
            return
        
        forbidden_chars = ['<', '>', '&', '"', "'", '`', '\\', '/', ';']
        for char in forbidden_chars:
            if char in new_nickname:
                bot.send_message(message.chat.id, f"❌ Запрещенный символ: {char}")
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
                       f"✅ Ник изменен: {new_nickname}\n\n"
                       f"💡 Будет отображаться в топах!")
        
    except Exception as e:
        logging.error(f"Ошибка смены ника: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

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
                           "❌ Формат: ценадома [ID_дома] [цена]\n"
                           "Пример: ценадома house_12345 2000000")
            return
        
        house_id = parts[1].strip()
        try:
            new_price = int(parts[2])
            if new_price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной")
                return
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная цена")
            return
        
        if house_id not in HOUSE_SHOP:
            bot.send_message(message.chat.id, f"❌ Дом '{house_id}' не найден")
            return
        
        old_price = HOUSE_SHOP[house_id]['price']
        house_name = HOUSE_SHOP[house_id]['name']
        
        HOUSE_SHOP[house_id]['price'] = new_price
        HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
        HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
        
        save_house_shop()
        
        bot.send_message(message.chat.id,
                       f"✅ Цена изменена!\n\n"
                       f"🏡 {house_name}\n"
                       f"🆔 `{house_id}`\n"
                       f"💰 Было: {format_balance(old_price)}❄️\n"
                       f"💰 Стало: {format_balance(new_price)}❄️")
        
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
                           "❌ Формат: массцена [процент] или массцена [сумма]\n"
                           "Примеры:\n"
                           "массцена +20% - увеличить на 20%\n"
                           "массцена -10% - уменьшить на 10%\n"
                           "массцена 1000000 - минимальная цена 1M")
            return
        
        change = parts[1].strip()
        
        if not HOUSE_SHOP:
            bot.send_message(message.chat.id, "❌ Нет домов")
            return
        
        changed_count = 0
        report = "📊 *Изменение цен*\n\n"
        
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
                
                report += f"💰 Минимальная цена: {format_balance(min_price)}❄️\n\n"
                
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
            bot.send_message(message.chat.id, "ℹ️ Ничего не изменено")
        
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

@bot.message_handler(func=lambda message: message.text in ["🏆 Топ"])
def handle_top_menu(message):
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
            InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"),
            InlineKeyboardButton("👥 Рефералы", callback_data="top_mode_scam")
        )
        
        bot.send_message(message.chat.id, "🏆 Выберите топ:", reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в handle_top_menu: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

def create_top_message(user_id, page=1):
    try:
        mode = user_top_mode.get(user_id, 'balance')
        
        if mode == 'balance':
            top_data = get_balance_top_page(page, 5)
            title = "🏆 Топ снежков"
            empty_message = "📭 Топ пуст!"
        else:
            top_data = get_scam_top_page(page, 5)
            title = "🏆 Топ рефералов"
            empty_message = "📭 Топ пуст!"
        
        top_users = top_data['users']
        total_pages = top_data['total_pages']
        current_page = top_data['current_page']
        
        user_position = get_user_position_in_top(user_id, mode)
        
        message_text = f"*{title}*\n\n"
        
        if not top_users:
            message_text += empty_message
        else:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            
            for i, user in enumerate(top_users):
                if mode == 'balance':
                    user_id_db, display_name, value, position = user
                    value_text = f"⟨{format_balance(value)}❄️⟩"
                else:
                    user_id_db, display_name, value, position = user
                    value_text = f"⟨{value}⟩"
                
                page_position = ((page - 1) * 5) + i + 1
                
                if page_position <= 3:
                    medal = medals[page_position-1]
                elif page_position <= 5:
                    medal = medals[page_position-1]
                else:
                    medal = f"{page_position}."
                
                display_name = str(display_name).strip()
                
                if display_name.startswith('@'):
                    username = display_name[1:]
                    display_html = f'<a href="https://t.me/{username}">{display_name}</a>'
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('SELECT nickname, username FROM users WHERE user_id = ?', (user_id_db,))
                    user_data = cursor.fetchone()
                    conn.close()
                    
                    if user_data and user_data[0] and user_data[0].strip():
                        nickname = user_data[0].strip()
                        username = user_data[1] if user_data[1] else None
                        
                        if username:
                            display_html = f'<a href="https://t.me/{username}">{nickname}</a>'
                        else:
                            display_html = nickname
                    else:
                        if user_data and user_data[1]:
                            username = user_data[1]
                            display_html = f'<a href="https://t.me/{username}">@{username}</a>'
                        else:
                            display_html = display_name
                
                if len(display_html) > 25:
                    import re
                    text_only = re.sub(r'<[^>]+>', '', display_html)
                    if len(text_only) > 22:
                        display_html = display_html[:20] + "..."
                
                message_text += f"{medal} {display_html} {value_text}\n"
        
        if total_pages > 1:
            message_text += f"\n📄 {current_page}/{total_pages}"
        
        if user_position:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if mode == 'balance':
                cursor.execute('SELECT balance, nickname, username FROM users WHERE user_id = ?', (user_id,))
                user_data = cursor.fetchone()
                
                if user_data:
                    balance, nickname, username = user_data
                    balance = balance if balance is not None else 0
                    
                    display_name = ""
                    if nickname and nickname.strip():
                        if username:
                            display_name = f'<a href="https://t.me/{username}">{nickname.strip()}</a>'
                        else:
                            display_name = nickname.strip()
                    elif username:
                        display_name = f'<a href="https://t.me/{username}">@{username}</a>'
                    else:
                        cursor.execute('SELECT first_name FROM users WHERE user_id = ?', (user_id,))
                        first_name_result = cursor.fetchone()
                        if first_name_result:
                            display_name = first_name_result[0] or f"ID: {user_id}"
                    
                    message_text += f"\n\n🎯 *Ваша позиция:* #{user_position}\n"
                    message_text += f"👤 {display_name}\n"
                    message_text += f"💰 {format_balance(balance)}❄️"
            
            else:
                cursor.execute('SELECT nickname, username FROM users WHERE user_id = ?', (user_id,))
                user_data = cursor.fetchone()
                
                cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
                ref_count = cursor.fetchone()[0]
                
                conn.close()
                
                display_name = ""
                if user_data:
                    nickname, username = user_data
                    if nickname and nickname.strip():
                        if username:
                            display_name = f'<a href="https://t.me/{username}">{nickname.strip()}</a>'
                        else:
                            display_name = nickname.strip()
                    elif username:
                        display_name = f'<a href="https://t.me/{username}">@{username}</a>'
                    else:
                        cursor.execute('SELECT first_name FROM users WHERE user_id = ?', (user_id,))
                        first_name_result = cursor.fetchone()
                        if first_name_result:
                            display_name = first_name_result[0] or f"ID: {user_id}"
                
                message_text += f"\n\n🎯 *Ваша позиция:* #{user_position if user_position > 0 else 'не в топе'}\n"
                message_text += f"👤 {display_name}\n"
                message_text += f"👥 {ref_count}"
        
        return message_text
        
    except Exception as e:
        logging.error(f"Ошибка создания сообщения топа: {e}")
        return "❌ Ошибка."

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
        buttons.append(InlineKeyboardButton("⬅️", callback_data=f"top_page_{current_page-1}"))
    
    page_button_text = f"{current_page}/{total_pages}"
    if total_pages > 1:
        page_button_text = f"📄 {current_page}/{total_pages}"
    buttons.append(InlineKeyboardButton(page_button_text, callback_data="top_current"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("➡️", callback_data=f"top_page_{current_page+1}"))
    
    if buttons:
        markup.row(*buttons)
    
    mode_buttons = []
    if mode == 'balance':
        mode_buttons.append(InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"))
        mode_buttons.append(InlineKeyboardButton("👥 Рефералы", callback_data="top_mode_scam"))
    else:
        mode_buttons.append(InlineKeyboardButton("👥 Рефералы", callback_data="top_mode_scam"))
        mode_buttons.append(InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"))
    
    markup.row(*mode_buttons)
    
    markup.row(InlineKeyboardButton("🔄 Обновить", callback_data="top_refresh"))
    
    return markup

@bot.message_handler(func=lambda message: message.text.lower() == 'обновить' and is_admin(message.from_user.id))
def handle_update_usernames(message):
    try:
        if not is_admin(message.from_user.id):
            return
        
        bot.send_message(message.chat.id, "⏳ Обновление username...")
        
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
            f"• Проверено: {len(users)}\n"
            f"• Обновлено: {updated_count}\n"
            f"• Ошибок: {failed_count}"
        )
        
    except Exception as e:
        logging.error(f"Ошибка обновления username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('top_'))
def top_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data.startswith('top_mode_'):
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
            bot.answer_callback_query(call.id, f"✅ {'Снежки' if mode == 'balance' else 'Рефералы'}")
            
        elif call.data.startswith('top_page_'):
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
            bot.answer_callback_query(call.id, "✅ Обновлено!")
            
        elif call.data == 'top_current':
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        logging.error(f"Ошибка в top_callback_handler: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка")
        except:
            pass

@bot.message_handler(func=lambda message: message.text.lower().startswith(('рул ', 'рулетка ')))
def handle_roulette(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
            
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: рул красный 1000к")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
            return
        
        update_balance(user_id, -bet_amount)
        
        winning_number = random.randint(0, 36)
        
        win = False
        multiplier = 1
        bet_type_name = ""
        
        red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        
        try:
            number_bet = int(bet_type)
            if 0 <= number_bet <= 36:
                win = winning_number == number_bet
                multiplier = 36
                bet_type_name = f"число {number_bet}"
            else:
                bot.send_message(message.chat.id, "❌ Число должно быть от 0 до 36")
                update_balance(user_id, bet_amount)
                return
        except ValueError:
            if bet_type in ['красный', 'крас', 'кра', 'кр', 'к']:
                win = winning_number in red_numbers
                multiplier = 2
                bet_type_name = "красный"
            elif bet_type in ['черный', 'чер', 'черн', 'ч', 'чр']:
                win = winning_number in black_numbers
                multiplier = 2
                bet_type_name = "черный"
            elif bet_type in ['зеленый', 'зел', 'з', '0', 'зеро', 'ноль']:
                win = winning_number == 0
                multiplier = 36
                bet_type_name = "зеленый"
            elif bet_type in ['большие', 'бол', 'б', 'бльш']:
                win = winning_number >= 19 and winning_number <= 36
                multiplier = 2
                bet_type_name = "большие"
            elif bet_type in ['малые', 'мал', 'м', 'мл']:
                win = winning_number >= 1 and winning_number <= 18
                multiplier = 2
                bet_type_name = "малые"
            elif bet_type in ['чет', 'четные', 'четн', 'ч']:
                win = winning_number % 2 == 0 and winning_number != 0
                multiplier = 2
                bet_type_name = "четные"
            elif bet_type in ['нечет', 'нечетные', 'неч', 'н', 'нечетн']:
                win = winning_number % 2 == 1 and winning_number != 0
                multiplier = 2
                bet_type_name = "нечетные"
            else:
                bot.send_message(message.chat.id, "❌ Неверный тип ставки.")
                update_balance(user_id, bet_amount)
                return
        
        color = "🔴" if winning_number in red_numbers else "⚫" if winning_number in black_numbers else "🟢"
        
        if win:
            win_amount = bet_amount * multiplier
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            
            image_path = get_roulette_photo(winning_number)
            
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"🎉 {bet_type_name} выиграла!\n"
                                   f"🎯 {winning_number} {color}\n"
                                   f"💰 +{format_balance(win_amount)}❄️\n"
                                   f"📊 {format_balance(new_balance)}❄️"
                        )
                except Exception as e:
                    logging.error(f"Ошибка отправки фото: {e}")
                    bot.send_message(message.chat.id, 
                                   f"🎉 {bet_type_name} выиграла!\n"
                                   f"🎯 {winning_number} {color}\n"
                                   f"💰 +{format_balance(win_amount)}❄️\n"
                                   f"📊 {format_balance(new_balance)}❄️")
            else:
                bot.send_message(message.chat.id, 
                               f"🎉 {bet_type_name} выиграла!\n"
                               f"🎯 {winning_number} {color}\n"
                               f"💰 +{format_balance(win_amount)}❄️\n"
                               f"📊 {format_balance(new_balance)}❄️")
        else:
            new_balance = get_balance(user_id)
            
            image_path = get_roulette_photo(winning_number)
            
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"❌ {bet_type_name} проиграла!\n"
                                   f"🎯 {winning_number} {color}\n"
                                   f"💸 -{format_balance(bet_amount)}❄️\n"
                                   f"📊 {format_balance(new_balance)}❄️"
                        )
                except Exception as e:
                    logging.error(f"Ошибка отправки фото: {e}")
                    bot.send_message(message.chat.id, 
                                   f"❌ {bet_type_name} проиграла!\n"
                                   f"🎯 {winning_number} {color}\n"
                                   f"💸 -{format_balance(bet_amount)}❄️\n"
                                   f"📊 {format_balance(new_balance)}❄️")
            else:
                bot.send_message(message.chat.id, 
                               f"❌ {bet_type_name} проиграла!\n"
                               f"🎯 {winning_number} {color}\n"
                               f"💸 -{format_balance(bet_amount)}❄️\n"
                               f"📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        logging.error(f"Ошибка в handle_roulette: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

def get_roulette_photo(winning_number):
    try:
        filename = f"{winning_number}.png"
        filepath = f"/app/{filename}"
        
        if os.path.exists(filepath):
            logging.info(f"✅ Найдено изображение: {filepath}")
            return filepath
        
        other_formats = ['.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']
        for ext in other_formats:
            filename = f"{winning_number}{ext}"
            filepath = f"/app/{filename}"
            if os.path.exists(filepath):
                logging.info(f"✅ Найдено изображение: {filepath}")
                return filepath
        
        current_dir = os.getcwd()
        for ext in ['.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']:
            filename = f"{winning_number}{ext}"
            filepath = os.path.join(current_dir, filename)
            if os.path.exists(filepath):
                logging.info(f"✅ Найдено изображение: {filepath}")
                return filepath
        
        logging.warning(f"❌ Изображение для {winning_number} не найдено")
        return None
        
    except Exception as e:
        logging.error(f"Ошибка поиска изображения: {e}")
        return None

@bot.message_handler(func=lambda message: message.text.lower().startswith(('куб ', 'кубик ')))
def handle_dice(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: куб 1 1000к")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎲')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        if bet_type in ['бол', 'большие', 'больше', 'б']:
            win = result in [4, 5, 6]
            multiplier = 2
            bet_type_name = "большие"
        
        elif bet_type in ['мал', 'малые', 'меньше', 'м']:
            win = result in [1, 2, 3]
            multiplier = 2
            bet_type_name = "малые"
        
        elif bet_type in ['чет', 'четные', 'четн', 'ч']:
            win = result in [2, 4, 6]
            multiplier = 2
            bet_type_name = "четные"
        
        elif bet_type in ['нечет', 'нечетные', 'неч', 'н']:
            win = result in [1, 3, 5]
            multiplier = 2
            bet_type_name = "нечетные"
        
        else:
            try:
                target = int(bet_type)
                if 1 <= target <= 6:
                    win = result == target
                    multiplier = 6
                    bet_type_name = f"число {target}"
                else:
                    bot.send_message(message.chat.id, "❌ Неверный тип ставки.")
                    update_balance(user_id, bet_amount)
                    return
            except:
                bot.send_message(message.chat.id, "❌ Неверный тип ставки.")
                update_balance(user_id, bet_amount)
                return
        
        if win:
            win_amount = bet_amount * multiplier
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 {bet_type_name} выиграла! {result}\n+{format_balance(win_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ {bet_type_name} проиграла! {result}\n-{format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_dice: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('слот ', 'слоты ')))
def handle_slots(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: слот 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
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
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 +{format_balance(win_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ -{format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_slots: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('бск ', 'баскетбол ')))
def handle_basketball(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: бск 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🏀')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 2.5
        
        if result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 +{format_balance(win_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ -{format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_basketball: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('фтб ', 'футбол ')))
def handle_football(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: фтб 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
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
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 ГОООЛ! +{format_balance(win_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ -{format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_football: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('дартс '))
def handle_darts(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: дартс 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        max_possible_loss = bet_amount * 2
        if max_possible_loss > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств!\n"
                           f"Нужно: {format_balance(max_possible_loss)}❄️\n"
                           f"Ваш: {format_balance(balance)}❄️")
            return
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎯')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        update_balance(user_id, -bet_amount)
        
        if result == 6:
            win_amount = bet_amount * 5
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            
            bot.send_message(message.chat.id, 
                           f"🎯 ЯБЛОЧКО! 🎯\n"
                           f"✅ +{format_balance(win_amount)}❄️\n"
                           f"📊 {format_balance(new_balance)}❄️")
        
        elif result == 1:
            update_balance(user_id, -bet_amount)
            total_loss = bet_amount * 2
            new_balance = get_balance(user_id)
            
            bot.send_message(message.chat.id, 
                           f"🎯 ПРОМАХ! 🎯\n"
                           f"❌ -{format_balance(total_loss)}❄️\n"
                           f"📊 {format_balance(new_balance)}❄️")
        
        else:
            new_balance = get_balance(user_id)
            
            if result == 5:
                ring = "внутреннее кольцо"
            else:
                ring = "внешнее кольцо"
            
            bot.send_message(message.chat.id, 
                           f"🎯 {ring}\n"
                           f"❌ -{format_balance(bet_amount)}❄️\n"
                           f"📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_darts: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('боул ', 'боулинг ')))
def handle_bowling(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро!")
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: боул 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎳')
        time.sleep(3)
        
        result = dice_message.dice.value
        
        if result == 6:
            win_amount = bet_amount * 2
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎳 СТРАЙК! +{format_balance(win_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        
        elif result == 5:
            update_balance(user_id, bet_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"⚖️ 1 кегля! Возврат {format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        
        elif result == 1:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ 1-2 кегли! -{format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
        
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
            
            bot.send_message(message.chat.id, f"❌ {remaining}! -{format_balance(bet_amount)}❄️\n📊 {format_balance(new_balance)}❄️")
    
    except Exception as e:
        print(f"Ошибка в handle_bowling: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('чек ') and not is_admin(message.from_user.id))
def handle_check(message):
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
                bot.send_message(message.chat.id, "❌ От 1 до 100")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверное количество")
            return
        
        total_amount = amount * activations
        
        if total_amount > balance:
            bot.send_message(message.chat.id, f"❌ Нужно: {format_balance(total_amount)}❄️")
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
                f"❄️ {format_balance(amount)}❄️\n"
                f"🔢 {activations}\n", 
                reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в создании чека: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('чеф ') and is_admin(message.from_user.id))
def handle_admin_check(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
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
                bot.send_message(message.chat.id, "❌ Количество должно быть больше 0")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверное количество")
            return
        
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
<b>🔢 {max_activations}</b>
        """.strip()
        
        bot.send_message(
            message.chat.id, 
            check_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    except Exception as e:
        print(f"Ошибка в handle_admin_check: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('выдать ') and is_admin(message.from_user.id))
def handle_give_money(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
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
                bot.send_message(message.chat.id, "❌ Неверный ID")
                conn.close()
                return
        
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Выдано {format_balance(amount)}❄️ {target}")
    
    except Exception as e:
        print(f"Ошибка в handle_give_money: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('забрать ') and is_admin(message.from_user.id))
def handle_take_money(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
            return
        
        if not message.reply_to_message:
            bot.send_message(message.chat.id, "❌ Ответьте на сообщение")
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
                bot.send_message(message.chat.id, f"❌ Недостаточно! {format_balance(balance)}❄️")
                conn.close()
                return
            
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, target_user_id))
            conn.commit()
            
            target_name = f"@{target_username}" if target_username else target_first_name
            
            bot.send_message(message.chat.id, 
                           f"✅ Забрано {format_balance(amount)}❄️ у {target_name}\n"
                           f"❄️ Новый баланс: {format_balance(balance - amount)}❄️")
            
            try:
                bot.send_message(target_user_id, 
                               f"⚠️ Забрано {format_balance(amount)}❄️\n"
                               f"❄️ Новый баланс: {format_balance(balance - amount)}❄️")
            except:
                pass
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_take_money: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('бан ') and is_admin(message.from_user.id))
def handle_ban_username(message):
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: бан @username [причина]\n"
                           "       или: бан ID [причина]")
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
                           f"✅ {target_name} забанен!\n"
                           f"📝 {ban_reason}")
            
            try:
                bot.send_message(target_user_id, 
                               f"🚫 Вы забанены!\n"
                               f"📝 {ban_reason}\n"
                               f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
                               f"✅ @{username} забанен!\n"
                               f"📝 {ban_reason}")
                
                try:
                    bot.send_message(target_user_id, 
                                   f"🚫 Вы забанены!\n"
                                   f"📝 {ban_reason}\n"
                                   f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                except:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ @{username} не найден")
        
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
                                   f"✅ {target_name} забанен!\n"
                                   f"📝 {ban_reason}")
                    
                    try:
                        bot.send_message(target_user_id, 
                                       f"🚫 Вы забанены!\n"
                                       f"📝 {ban_reason}\n"
                                       f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    except:
                        pass
                else:
                    bot.send_message(message.chat.id, f"❌ ID {target_user_id} не найден")
                    
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат.")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_ban_username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower().startswith('разбан ') and is_admin(message.from_user.id))
def handle_unban_username(message):
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: разбан @username\n"
                           "       или: разбан ID")
            return
        
        target = parts[1].strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if message.reply_to_message:
            target_user_id = message.reply_to_message.from_user.id
            
            cursor.execute('SELECT username, first_name, is_banned FROM users WHERE user_id = ?', (target_user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                bot.send_message(message.chat.id, "❌ Пользователь не найден")
                conn.close()
                return
            
            username, first_name, is_banned = user_data
            
            if is_banned == 0:
                bot.send_message(message.chat.id, "⚠️ Не забанен")
                conn.close()
                return
            
            cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                          (target_user_id,))
            conn.commit()
            
            target_name = f"@{username}" if username else first_name
            bot.send_message(message.chat.id, f"✅ {target_name} разбанен!")
            
            try:
                bot.send_message(target_user_id, 
                               f"🎉 Вы разбанены!")
            except:
                pass
        
        elif target.startswith('@'):
            username = target[1:]
            
            cursor.execute('SELECT user_id, first_name, is_banned FROM users WHERE username = ?', (username,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_user_id, first_name, is_banned = user_data
                
                if is_banned == 0:
                    bot.send_message(message.chat.id, f"⚠️ @{username} не забанен")
                    conn.close()
                    return
                
                cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                              (target_user_id,))
                conn.commit()
                
                bot.send_message(message.chat.id, f"✅ @{username} разбанен!")
                
                try:
                    bot.send_message(target_user_id, 
                                   f"🎉 Вы разбанены!")
                except:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ @{username} не найден")
        
        else:
            try:
                target_user_id = int(target)
                
                cursor.execute('SELECT username, first_name, is_banned FROM users WHERE user_id = ?', (target_user_id,))
                user_data = cursor.fetchone()
                
                if user_data:
                    username, first_name, is_banned = user_data
                    
                    if is_banned == 0:
                        bot.send_message(message.chat.id, f"⚠️ ID {target_user_id} не забанен")
                        conn.close()
                        return
                    
                    cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                                  (target_user_id,))
                    conn.commit()
                    
                    target_name = f"@{username}" if username else first_name
                    bot.send_message(message.chat.id, f"✅ {target_name} разбанен!")
                    
                    try:
                        bot.send_message(target_user_id, 
                                       f"🎉 Вы разбанены!")
                    except:
                        pass
                else:
                    bot.send_message(message.chat.id, f"❌ ID {target_user_id} не найден")
                    
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат.")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_unban_username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

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
                               "❌ Формат: `передать сумма`\n"
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
                    bot.send_message(message.chat.id, f"❌ {target_identifier} не найден")
                    return
            else:
                try:
                    target_user_id = int(target_identifier)
                except ValueError:
                    bot.send_message(message.chat.id, f"❌ Неверный формат")
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
                           "• Ответьте `передать сумма`\n"
                           "• `передать @username сумма`\n"
                           "• `кинуть ID сумма`")
            return
        
        if not target_user_id:
            bot.send_message(message.chat.id, "❌ Получатель не найден")
            return
        
        if target_user_id == user_id:
            bot.send_message(message.chat.id, "❌ Нельзя передавать себе")
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
            bot.send_message(message.chat.id, "❌ Минимум: 10❄️")
            return
        
        if transfer_amount > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно!\n"
                           f"Ваш: {format_balance(balance)}❄️\n"
                           f"Нужно ещё: {format_balance(transfer_amount - balance)}❄️")
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
                       f"👤 {target_display}\n"
                       f"💰 {format_balance(transfer_amount)}❄️\n"
                       f"📊 {format_balance(new_balance)}❄️",
                       parse_mode='Markdown')
        
        try:
            bot.send_message(target_user_id,
                           f"🎉 *Вам перевели!*\n\n"
                           f"👤 {sender_username}\n"
                           f"💰 {format_balance(transfer_amount)}❄️\n"
                           f"📊 {format_balance(target_balance)}❄️",
                           parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Не удалось уведомить {target_user_id}: {e}")
        
        log_user_action(user_id, "TRANSFER_SUCCESS", f"to={target_user_id} amount={transfer_amount}")
        
    except Exception as e:
        logging.error(f"Ошибка в передаче: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

@bot.message_handler(func=lambda message: message.text.lower().startswith('рассылка ') and is_admin(message.from_user.id))
def handle_broadcast(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
            return
        
        broadcast_text = message.text[len('рассылка '):].strip()
        
        if not broadcast_text:
            bot.send_message(message.chat.id, "❌ Введите текст")
            return
        
        bot.send_message(message.chat.id, f"⏳ Начинаю...\n{broadcast_text[:100]}...")
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        conn.close()
        
        total_users = len(users)
        successful = 0
        failed = 0
        
        bot.send_message(message.chat.id, f"📊 Всего: {total_users}")
        
        for user_data in users:
            user_id = user_data[0]
            try:
                bot.send_message(user_id, f"📢 Рассылка:\n\n{broadcast_text}")
                successful += 1
                
                time.sleep(0.05)
                
            except Exception as e:
                failed += 1
                print(f"Ошибка при отправке {user_id}: {e}")
        
        report_message = f"✅ Рассылка завершена!\n\n"
        report_message += f"📊 Статистика:\n"
        report_message += f"• Всего: {total_users}\n"
        report_message += f"• Успешно: {successful}\n"
        report_message += f"• Не удалось: {failed}\n"
        
        bot.send_message(message.chat.id, report_message)
    
    except Exception as e:
        print(f"Ошибка в рассылке: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text.lower() == 'статистика' and is_admin(message.from_user.id))
def handle_statistics(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE captcha_passed = 1')
        active_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(registered_at) = DATE("now")')
        new_today = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(balance) FROM users')
        total_balance = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(bank_deposit) FROM users')
        total_deposits = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats_message = f"📊 Статистика:\n\n"
        stats_message += f"👥 Всего: {total_users}\n"
        stats_message += f"✅ Активных: {active_users}\n"
        stats_message += f"🚫 Забанено: {banned_users}\n"
        stats_message += f"📈 Новых сегодня: {new_today}\n"
        stats_message += f"💰 Общий баланс: {format_balance(total_balance)}❄️\n"
        stats_message += f"🏦 Общая сумма в банке: {format_balance(total_deposits)}❄️\n"
        
        bot.send_message(message.chat.id, stats_message)
    
    except Exception as e:
        print(f"Ошибка в статистике: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text.lower().startswith('поиск ') and is_admin(message.from_user.id))
def handle_search_user(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Нет прав")
            return
        
        search_query = message.text[len('поиск '):].strip()
        
        if not search_query:
            bot.send_message(message.chat.id, "❌ Введите запрос")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, username, first_name, balance, is_banned, 
                   registered_at, last_activity 
            FROM users 
            WHERE user_id = ? OR username LIKE ? OR first_name LIKE ?
            LIMIT 10
        ''', (search_query, f'%{search_query}%', f'%{search_query}%'))
        
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            bot.send_message(message.chat.id, f"❌ '{search_query}' не найдены")
            return
        
        result_message = f"🔍 Результаты '{search_query}':\n\n"
        
        for i, user in enumerate(users, 1):
            user_id, username, first_name, balance, is_banned, registered_at, last_activity = user
            
            display_name = f"@{username}" if username else first_name
            status = "🚫 Забанен" if is_banned == 1 else "✅ Активен"
            
            try:
                reg_date = registered_at[:10] if registered_at else "Неизвестно"
                last_active = last_activity[:16] if last_activity else "Неизвестно"
            except:
                reg_date = "Неизвестно"
                last_active = "Неизвестно"
            
            result_message += f"{i}. {display_name} (ID: {user_id})\n"
            result_message += f"   {status}\n"
            result_message += f"   {format_balance(balance)}❄️\n"
            result_message += f"   📅 {reg_date}\n"
            result_message += f"   ⏰ {last_active}\n\n"
        
        bot.send_message(message.chat.id, result_message)
    
    except Exception as e:
        print(f"Ошибка в поиске: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: message.from_user.id in user_captcha_status)
def check_captcha_answer(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            if user_id in user_captcha_status:
                del user_captcha_status[user_id]
            return
        
        correct_answer = user_captcha_status.get(user_id)
        
        if not correct_answer:
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            bot.send_message(message.chat.id, 
                           f"🔒 Решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом.")
            return
        
        user_answer = message.text.strip()
        
        if user_answer == correct_answer:
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET captcha_passed = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            del user_captcha_status[user_id]
            
            ref_code = pending_ref_codes.pop(user_id, None)
            if ref_code:
                process_ref_or_check(user_id, username, first_name, ref_code)
            
            markup = create_main_menu()
            bot.send_message(message.chat.id, "✅ Капча пройдена!\n\nГлавное меню:", reply_markup=markup)
        else:
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            bot.send_message(message.chat.id, 
                           f"❌ Неверно!\n\n"
                           f"🔒 Решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом.")
    
    except Exception as e:
        logging.error(f"Ошибка в проверке капчи: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка.")

if __name__ == "__main__":
    try:
        init_db()
        load_house_shop()
        
        print("Бот запущен...")
        bot.polling(none_stop=True)
        
    except Exception as e:
        logging.error(f"Ошибка запуска бота: {e}")
        print(f"Ошибка: {e}")