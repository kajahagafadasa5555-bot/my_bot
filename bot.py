import asyncio
import logging
import datetime
import random
import string
import os
import aiosqlite
import traceback
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, LabeledPrice, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= КОНФИГ =================
BOT_TOKEN = os.environ.get("9254195561:AAE6CofEP8-YXxWig89-TqoH6JR3sLXvUYA", "9254195561:AAE6CofEP8-YXxWig89-TqoH6JR3sLXvUYA")
ADMIN_IDS = [8400799305]
CONTACT_ADMIN = "@drag_monster_zl"
CARD_NUMBER = "9112 3801 7930 6727"
CARD_BANK = "Беларусь Банк"
DB_PATH = "bot.db"
USD_TO_BYN = 2.9943

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ================= ГЛОБАЛЬНЫЙ ПЕРЕХВАТ ОШИБОК =================
async def send_error_to_admin(update_type: str, error: Exception, user_id: int, data: str = ""):
    tb = traceback.format_exc()
    text = (
        f"🚨 <b>ОШИБКА В БОТЕ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Юзер:</b> <code>{user_id}</code>\n"
        f"📌 <b>Где:</b> {update_type} | {data}\n"
        f"❌ <b>Ошибка:</b> <code>{str(error)}</code>\n\n"
        f"📝 <b>Трейс:</b>\n<pre>{tb[-1000:]}</pre>"
    )
    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, text)
        except: pass

@dp.errors()
async def global_error_handler(event: types.ErrorEvent):
    try:
        update = event.update
        exc = event.exception
        user_id = 0
        data = ""
        update_type = "Unknown"
        
        if update.callback_query:
            user_id = update.callback_query.from_user.id
            data = update.callback_query.data
            update_type = "Callback"
        elif update.message:
            user_id = update.message.from_user.id
            data = update.message.text or ""
            update_type = "Message"
            
        await send_error_to_admin(update_type, exc, user_id, data)
    except Exception as e:
        logging.error(f"Error in error handler: {e}")

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            balance INTEGER DEFAULT 1000, coins INTEGER DEFAULT 0,
            referrer_id INTEGER, referrals INTEGER DEFAULT 0,
            last_bonus TEXT DEFAULT '', xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
            jackpot_contribution INTEGER DEFAULT 0, wins_count INTEGER DEFAULT 0,
            bonus_streak INTEGER DEFAULT 0)""")
        await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, rarity TEXT, value INTEGER, is_withdrawn INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, user_id INTEGER, item_name TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, rank INTEGER DEFAULT 1)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS hr_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, details TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY, reason TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS quests (user_id INTEGER, quest_key TEXT, progress INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, PRIMARY KEY (user_id, quest_key))")
        await db.execute("CREATE TABLE IF NOT EXISTS achievements (user_id INTEGER, achievement_key TEXT, unlocked_at TEXT, PRIMARY KEY (user_id, achievement_key))")
        await db.execute("CREATE TABLE IF NOT EXISTS cases (key TEXT PRIMARY KEY, name TEXT, price INTEGER, coin_price INTEGER, mon_price INTEGER, is_active INTEGER DEFAULT 1)")
        await db.execute("CREATE TABLE IF NOT EXISTS case_items (id INTEGER PRIMARY KEY AUTOINCREMENT, case_key TEXT, name TEXT, rarity TEXT, value INTEGER, weight REAL, display_chance TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS jackpot (id INTEGER PRIMARY KEY, amount INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS crash_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bet INTEGER, multiplier REAL, win INTEGER, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_activations (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))")
        await db.execute("CREATE TABLE IF NOT EXISTS pity (user_id INTEGER, case_key TEXT, fail_count INTEGER DEFAULT 0, PRIMARY KEY (user_id, case_key))")
        await db.execute("CREATE TABLE IF NOT EXISTS button_names (key TEXT PRIMARY KEY, text TEXT)")
        await db.execute("""CREATE TABLE IF NOT EXISTS star_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_key TEXT, 
            item_name TEXT, price_byn REAL, status TEXT DEFAULT 'pending', 
            created_at TEXT)""")

        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = [row[1] for row in await cur.fetchall()]
        needed_columns = {"xp": "INTEGER DEFAULT 0", "level": "INTEGER DEFAULT 1", "jackpot_contribution": "INTEGER DEFAULT 0", "wins_count": "INTEGER DEFAULT 0", "bonus_streak": "INTEGER DEFAULT 0"}
        for col, col_type in needed_columns.items():
            if col not in columns: await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")

        defaults = [
            ('maintenance', 'False'), ('panic', 'False'), ('bj_chance', '20'), ('shop_price', '100000'),
            ('jackpot_enabled', 'True'), ('crash_chance', '40'), ('pity_threshold', '30'),
            ('real_chance_up', '50'), ('real_chance_coin', '50'), ('real_chance_bj', '20'), ('real_chance_crash', '40')
        ]
        for k, v in defaults: await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        star_prices = {"50": 1.19, "100": 2.39, "150": 3.69, "250": 6.09, "500": 11.99, "1000": 23.99, "10000": 239.00, "prem3": 17.99, "prem6": 22.99, "prem12": 39.99}
        for k, v in star_prices.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (f"price_{k}_usd", str(v)))

        btn_defaults = {
            "btn_cases": "🎁 КЕЙСЫ", "btn_games": "🎮 ИГРЫ", "btn_quests": "🎯 КВЕСТЫ", "btn_achievements": "🏆 ДОСТИЖЕНИЯ",
            "btn_bonus": "🎁 БОНУС", "btn_wheel": "🎰 КОЛЕСО", "btn_shop": "🛒 МАГАЗИН", "btn_buy_stars": "⭐ STARS/ПРЕМКА",
            "btn_inv": "🎒 ИНВЕНТАРЬ", "btn_prof": "👤 ПРОФИЛЬ", "btn_top": "🏆 ТОП", "btn_promo": "🔑 ПРОМОКОД",
            "btn_ref": "👥 РЕФЕРАЛЫ", "btn_crash": "🎰 CRASH", "btn_commands": "📜 КОМАНДЫ", "btn_about": "ℹ️ О БОТЕ",
            "btn_admin_panel": "👑 АДМИН ПАНЕЛЬ"
        }
        for k, v in btn_defaults.items():
            await db.execute("INSERT OR IGNORE INTO button_names (key, text) VALUES (?, ?)", (k, v))

        await db.execute("INSERT OR IGNORE INTO admins (user_id, rank) VALUES (?, 3)", (ADMIN_IDS[0],))
        await db.execute("INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 0)")

        async with db.execute("SELECT COUNT(*) FROM cases") as cur:
            if (await cur.fetchone())[0] == 0:
                cases_data = [("poor", "🥺 Нищий", 15, 5, 15000), ("rich", "👑 Богатый", 100, 30, 100000), ("nft", "💎 NFT Кейс", 700, 250, 1000000)]
                for c in cases_data: await db.execute("INSERT INTO cases (key, name, price, coin_price, mon_price) VALUES (?, ?, ?, ?, ?)", c)
                items_data = [
                    ("poor", "2 звезды", "common", 2, 70, "50%"), ("poor", "5 звезд", "rare", 5, 25, "30%"), ("poor", "20 звезд", "epic", 20, 5, "15%"), ("poor", "💎 Алмаз", "legendary", 500, 3, "4%"), ("poor", "🚀 Ракета", "legendary", 1000, 1.5, "0.8%"), ("poor", "🏆 Кубок", "mythic", 5000, 0.5, "0.2%"),
                    ("rich", "10 звезд", "common", 10, 60, "50%"), ("rich", "50 звезд", "rare", 50, 30, "40%"), ("rich", "NFT Кубок", "epic", 500, 9, "9%"), ("rich", "👑 Корона", "legendary", 2500, 1, "1%"),
                    ("nft", "50 звезд", "common", 50, 60, "60%"), ("nft", "100 звезд", "rare", 100, 25, "25%"), ("nft", "Сердечко", "epic", 200, 10, "10%"), ("nft", "🚀 Ракета", "legendary", 1000, 4, "4%"), ("nft", "👑 ТОП NFT", "mythic", 5000, 1, "1%")
                ]
                for i in items_data: await db.execute("INSERT INTO case_items (case_key, name, rarity, value, weight, display_chance) VALUES (?, ?, ?, ?, ?, ?)", i)
        await db.commit()

async def get_setting(key):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else None
    except: return None

async def set_setting(key, value):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            await db.commit()
    except Exception as e: logging.error(f"set_setting error: {e}")

async def get_button(key):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT text FROM button_names WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else key
    except: return key

async def get_admin_rank(user_id):
    if user_id in ADMIN_IDS: return 3
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT rank FROM admins WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0
    except: return 0

async def add_user(user_id, username, full_name, ref_id=None):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
                if not await cur.fetchone():
                    await db.execute("INSERT INTO users (user_id, username, full_name, referrer_id) VALUES (?, ?, ?, ?)", (user_id, username, full_name, ref_id))
                    if ref_id: await db.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                else:
                    await db.execute("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?", (username, full_name, user_id))
                await db.commit()
    except Exception as e: logging.error(f"add_user error: {e}")

async def safe_get_user(user_id, username="", full_name=""):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    await add_user(user_id, username, full_name)
                    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur2:
                        row = await cur2.fetchone()
                if not row:
                    return {"user_id": user_id, "username": username, "full_name": full_name, "balance": 1000, "coins": 0, "referrals": 0, "last_bonus": "", "xp": 0, "level": 1, "wins_count": 0, "bonus_streak": 0}
                return {
                    "user_id": row[0], "username": row[1] or "", "full_name": row[2] or "Игрок",
                    "balance": row[3] or 0, "coins": row[4] or 0,
                    "referrals": row[6] if len(row) > 6 and row[6] else 0,
                    "last_bonus": row[7] if len(row) > 7 and row[7] else "",
                    "xp": row[9] if len(row) > 9 and row[9] else 0,
                    "level": row[10] if len(row) > 10 and row[10] else 1,
                    "wins_count": row[12] if len(row) > 12 and row[12] else 0,
                    "bonus_streak": row[13] if len(row) > 13 and row[13] else 0,
                }
    except Exception as e:
        logging.error(f"safe_get_user error: {e}")
        return {"user_id": user_id, "username": username, "full_name": full_name, "balance": 1000, "coins": 0, "referrals": 0, "last_bonus": "", "xp": 0, "level": 1, "wins_count": 0, "bonus_streak": 0}

async def upd_bal(user_id, amount, is_coin=False, add_jackpot=True):
    try:
        if amount <= 0 and not is_coin: pass 
        async with aiosqlite.connect(DB_PATH) as db:
            if is_coin: await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
            else:
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
                if amount < 0 and add_jackpot: await db.execute("UPDATE jackpot SET amount = amount + ? WHERE id = 1", (abs(amount) // 10,))
            await db.commit()
    except Exception as e: logging.error(f"upd_bal error: {e}")

async def add_xp(user_id, xp):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (xp, user_id))
            async with db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    xp_val, lvl = row[0] or 0, row[1] or 1
                    new_lvl = xp_val // 1000 + 1
                    if new_lvl > lvl:
                        await db.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_lvl, user_id))
                        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (new_lvl * 5000, user_id))
                        try: await bot.send_message(user_id, f"🎉 <b>НОВЫЙ УРОВЕНЬ!</b>\nУровень: {new_lvl}\nБонус: {new_lvl * 5000} 💰")
                        except: pass
            await db.commit()
    except Exception as e: logging.error(f"add_xp error: {e}")

async def add_item(user_id, name, rarity, value):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO inventory (user_id, item_name, rarity, value) VALUES (?, ?, ?, ?)", (user_id, name, rarity, value))
            await db.commit()
    except Exception as e: logging.error(f"add_item error: {e}")

async def check_achievement(user_id, key):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM achievements WHERE user_id = ? AND achievement_key = ?", (user_id, key)) as cur:
                if await cur.fetchone(): return False
            await db.execute("INSERT INTO achievements (user_id, achievement_key, unlocked_at) VALUES (?, ?, ?)", (user_id, key, datetime.datetime.now().isoformat()))
            await db.commit()
        return True
    except: return False

def gen_code(l=8): return "".join(random.choices(string.ascii_uppercase + string.digits, k=l))

async def add_hr_log(admin_id, action, details=""):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO hr_logs (admin_id, action, details, timestamp) VALUES (?, ?, ?, ?)", (admin_id, action, details, datetime.datetime.now().isoformat()))
            await db.commit()
    except: pass

# ================= КЕЙСЫ =================
async def get_cases():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT key, name, price, coin_price, mon_price FROM cases WHERE is_active = 1") as cur:
                rows = await cur.fetchall()
        return {r[0]: {"name": r[1], "price": r[2], "coin_price": r[3], "mon_price": r[4]} for r in rows}
    except: return {}

async def get_case_items(case_key):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, name, rarity, value, weight, display_chance FROM case_items WHERE case_key = ?", (case_key,)) as cur:
                return await cur.fetchall()
    except: return []

async def get_pity(user_id, case_key):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT fail_count FROM pity WHERE user_id = ? AND case_key = ?", (user_id, case_key)) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0
    except: return 0

async def update_pity(user_id, case_key, increment=True):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if increment: await db.execute("INSERT INTO pity (user_id, case_key, fail_count) VALUES (?, ?, 1) ON CONFLICT(user_id, case_key) DO UPDATE SET fail_count = fail_count + 1", (user_id, case_key))
            else: await db.execute("INSERT OR REPLACE INTO pity (user_id, case_key, fail_count) VALUES (?, ?, 0)", (user_id, case_key))
            await db.commit()
    except: pass

async def open_case(case_key, user_id):
    try:
        items = await get_case_items(case_key)
        if not items: return (0, "Пусто", "common", 0, 0, "0%")
        threshold = int(await get_setting("pity_threshold") or 30)
        fails = await get_pity(user_id, case_key)
        if fails >= threshold:
            rare_items = [i for i in items if i[2] in ("legendary", "mythic")]
            if rare_items:
                chosen = random.choices(rare_items, weights=[i[4] for i in rare_items], k=1)[0]
                await update_pity(user_id, case_key, increment=False)
                return chosen
        weights = [i[4] for i in items]
        chosen = random.choices(items, weights=weights, k=1)[0]
        if chosen[2] in ("legendary", "mythic"): await update_pity(user_id, case_key, increment=False)
        else: await update_pity(user_id, case_key, increment=True)
        return chosen
    except Exception as e:
        logging.error(f"open_case error: {e}")
        return (0, "Ошибка", "common", 0, 0, "0%")

# ================= АНИМАЦИЯ =================
async def play_animation(message: Message, case_name: str):
    try:
        emojis = ["🍒", "🍋", "💎", "🎁", "👑", "🚀", "⭐", "🏆"]
        msg = await message.edit_text(f"<b>🎰 ЗАПУСК РУЛЕТКИ...</b>\n\n[ ⬜️ ⬜️ ⬜️ ]")
        await asyncio.sleep(0.2)
        for _ in range(4):
            e1, e2, e3 = random.choices(emojis, k=3)
            await msg.edit_text(f"<b>🎰 КРУТИМ...</b>\n\n[ {e1} {e2} {e3} ]")
            await asyncio.sleep(0.2)
        await msg.edit_text("<b>🔥 ПОЧТИ ГОТОВО...</b>\n\n[ 🔥 🔥 🔥 ]")
        await asyncio.sleep(0.3)
        return msg
    except: return message

# ================= КЛАВИАТУРЫ =================
async def main_menu(user_id):
    try:
        kb = [
            [InlineKeyboardButton(text=await get_button("btn_cases"), callback_data="cases"), InlineKeyboardButton(text=await get_button("btn_games"), callback_data="games")],
            [InlineKeyboardButton(text=await get_button("btn_quests"), callback_data="quests"), InlineKeyboardButton(text=await get_button("btn_achievements"), callback_data="achievements")],
            [InlineKeyboardButton(text=await get_button("btn_bonus"), callback_data="daily_bonus"), InlineKeyboardButton(text=await get_button("btn_wheel"), callback_data="wheel")],
            [InlineKeyboardButton(text=await get_button("btn_shop"), callback_data="shop"), InlineKeyboardButton(text=await get_button("btn_buy_stars"), callback_data="buy_stars")],
            [InlineKeyboardButton(text=await get_button("btn_inv"), callback_data="inv"), InlineKeyboardButton(text=await get_button("btn_prof"), callback_data="prof")],
            [InlineKeyboardButton(text=await get_button("btn_top"), callback_data="top_players"), InlineKeyboardButton(text=await get_button("btn_promo"), callback_data="promo")],
            [InlineKeyboardButton(text=await get_button("btn_ref"), callback_data="ref"), InlineKeyboardButton(text=await get_button("btn_crash"), callback_data="crash_game")],
            [InlineKeyboardButton(text=await get_button("btn_commands"), callback_data="commands"), InlineKeyboardButton(text=await get_button("btn_about"), callback_data="about")]
        ]
        if user_id in ADMIN_IDS: kb.append([InlineKeyboardButton(text=await get_button("btn_admin_panel"), callback_data="admin_panel")])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except: return None

def back_btn(cb="back_main"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ НАЗАД", callback_data=cb)]])

async def admin_menu(rank, user_id):
    try:
        kb = [[InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_stats"), InlineKeyboardButton(text="📖 СПРАВОЧНИК", callback_data="admin_help")]]
        if rank >= 2:
            kb.append([InlineKeyboardButton(text="🎁 КУПОН", callback_data="admin_coupon"), InlineKeyboardButton(text="🔑 ПРОМО", callback_data="admin_promo")])
            kb.append([InlineKeyboardButton(text="🚫 БАНЫ", callback_data="admin_bans")])
        if rank == 3:
            kb.append([InlineKeyboardButton(text="💰 ВЫДАТЬ ВАЛЮТУ", callback_data="admin_give_menu"), InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ БАЛАНС", callback_data="admin_edit_bal")])
            kb.append([InlineKeyboardButton(text="🚨 ПАНИКА", callback_data="admin_panic"), InlineKeyboardButton(text="🛠 ТЕХ.РАБОТЫ", callback_data="admin_maint")])
            kb.append([InlineKeyboardButton(text="👥 HR-ПАНЕЛЬ", callback_data="admin_staff")])
            kb.append([InlineKeyboardButton(text="⚙️ ШАНСЫ БД", callback_data="admin_odds"), InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="admin_shop")])
            kb.append([InlineKeyboardButton(text="🎁 КЕЙСЫ", callback_data="admin_cases")])
            kb.append([InlineKeyboardButton(text="🎲 РЕАЛЬНЫЙ ШАНС", callback_data="admin_real_chance"), InlineKeyboardButton(text="🎭 ЛИПОВЫЙ ШАНС", callback_data="admin_fake_chance")])
            kb.append([InlineKeyboardButton(text="🏷️ НАЗВАНИЯ КНОПОК", callback_data="admin_button_names")])
            kb.append([InlineKeyboardButton(text="⭐ НАСТРОЙКА ЦЕН STARS", callback_data="admin_stars_prices")])
            kb.append([InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ STARS", callback_data="admin_confirm_stars")])
            kb.append([InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast")])
            kb.append([InlineKeyboardButton(text="💾 БД", callback_data="admin_backup"), InlineKeyboardButton(text="📈 ЛОГИ", callback_data="hr_logs")])
            kb.append([InlineKeyboardButton(text="🎰 PITY-ПОРОГ", callback_data="admin_pity")])
        kb.append([InlineKeyboardButton(text="ЗАКРЫТЬ", callback_data="close_admin")])
        return InlineKeyboardMarkup(inline_keyboard=kb)
    except: return None

# ================= СОСТОЯНИЯ =================
class UserState(StatesGroup):
    waiting_promo = State()
    waiting_bet = State()
    waiting_crash_bet = State()

class AdminState(StatesGroup):
    waiting_coupon = State()
    waiting_promo_val = State()
    waiting_promo_uses = State()
    waiting_staff_id = State()
    waiting_bj_chance = State()
    waiting_ban_id = State()
    waiting_ban_reason = State()
    waiting_unban_id = State()
    waiting_shop_price = State()
    waiting_edit_id = State()
    waiting_edit_type = State()
    waiting_edit_amount = State()
    waiting_edit_action = State()
    waiting_crash_chance = State()
    waiting_broadcast_msg = State()
    waiting_case_key = State()
    waiting_case_name = State()
    waiting_case_price = State()
    waiting_item_name = State()
    waiting_item_rarity = State()
    waiting_item_value = State()
    waiting_item_weight = State()
    waiting_item_chance = State()
    waiting_pity_threshold = State()
    waiting_edit_item_name = State()
    waiting_edit_item_rarity = State()
    waiting_edit_item_value = State()
    waiting_edit_item_weight = State()
    waiting_edit_item_chance = State()
    waiting_button_key = State()
    waiting_button_text = State()
    waiting_stars_price = State()
    waiting_stars_price_key = State()
    waiting_real_chance_val = State()
    waiting_fake_chance_val = State()

# ================= ПОЛЬЗОВАТЕЛЬСКИЕ ХЭНДЛЕРЫ =================
@dp.message(CommandStart())
@dp.message(Command("menu"))
async def cmd_start(message: Message):
    try:
        if await get_setting("maintenance") == "True" and await get_admin_rank(message.from_user.id) == 0:
            return await message.answer("🛠 <b>НА БОТЕ ТЕХНИЧЕСКИЕ РАБОТЫ.</b>")
        u = message.from_user
        args = message.text.split()
        ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
        if ref_id == u.id: ref_id = None
        await add_user(u.id, u.username or "", u.full_name, ref_id)
        user = await safe_get_user(u.id, u.username, u.full_name)
        
        if await check_achievement(u.id, "start"):
            await message.answer("🏅 <b>ДОСТИЖЕНИЕ:</b> Первый шаг!")
            
        text = (
            f"👋 <b>ДОБРО ПОЖАЛОВАТЬ, {user['full_name'].upper()}!</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Монеты:</b> {user['balance']}\n💎 <b>Коэны:</b> {user['coins']}\n"
            f"⭐ <b>Уровень:</b> {user['level']} (XP: {user['xp']})\n"
            f"🔥 <b>Серия бонусов:</b> {user['bonus_streak']} дн.\n━━━━━━━━━━━━━━━━━━"
        )
        await message.answer(text, reply_markup=await main_menu(u.id))
    except Exception as e:
        logging.error(f"cmd_start error: {e}")
        await message.answer("⚠️ Ошибка, попробуйте /menu")

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery, state: FSMContext):
    try:
        await state.clear() # Защита от зависания
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        text = (
            f"🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Монеты:</b> {user['balance']}\n💎 <b>Коэны:</b> {user['coins']}\n"
            f"⭐ <b>Уровень:</b> {user['level']} (XP: {user['xp']})\n"
            f"🔥 <b>Серия бонусов:</b> {user['bonus_streak']} дн.\n━━━━━━━━━━━━━━━━━━"
        )
        await cb.message.edit_text(text, reply_markup=await main_menu(cb.from_user.id))
        await cb.answer()
    except:
        await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "about")
async def about_bot(cb: CallbackQuery):
    try:
        text = f"ℹ️ <b>О БОТЕ</b>\n━━━━━━━━━━━━━━━━━━\nЛучший бот для открытия кейсов!\n\n📩 <b>Поддержка:</b> {CONTACT_ADMIN}"
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "commands")
async def commands_menu(cb: CallbackQuery):
    try:
        text = (
            f"📜 <b>ВСЕ КОМАНДЫ</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🎁 Кейсы, 🎮 Игры, 🎯 Квесты, 🏆 Достижения\n"
            f"🎁 Бонус (streak!), 🎰 Колесо, 🛒 Магазин, ⭐ Stars\n"
            f"🎒 Инвентарь, 👤 Профиль, 🏆 Топ, 🔑 Промокод\n"
            f"👥 Рефералы, 🎰 Crash\n\n"
            f"⚙️ <b>Команды:</b>\n"
            f"/start или /menu — Открыть меню\n"
            f"/admin — Админ-панель\n"
        )
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "prof")
async def prof(cb: CallbackQuery):
    try:
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        achievements_count = 0
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM achievements WHERE user_id = ?", (cb.from_user.id,)) as cur:
                achievements_count = (await cur.fetchone())[0]
        text = (
            f"👤 <b>ПРОФИЛЬ</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
            f"💰 <b>Монеты:</b> {user['balance']}\n💎 <b>Коэны:</b> {user['coins']}\n"
            f"⭐ <b>Уровень:</b> {user['level']} (XP: {user['xp']})\n"
            f"🔥 <b>Серия бонусов:</b> {user['bonus_streak']} дн.\n"
            f"🏆 <b>Побед:</b> {user['wins_count']}\n👥 <b>Рефералы:</b> {user['referrals']}/3\n"
            f"🏅 <b>Достижения:</b> {achievements_count}\n━━━━━━━━━━━━━━━━━━"
        )
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "achievements")
async def achievements_menu(cb: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT achievement_key FROM achievements WHERE user_id = ?", (cb.from_user.id,)) as cur:
                user_ach = [r[0] for r in await cur.fetchall()]
        ach_list = {
            "start": "🚀 Первый шаг", "first_case": "🎁 Первый кейс", "first_bet": "🎮 Первая ставка",
            "10k_earned": "💰 10к монет", "100k_earned": "💎 100к монет", "case_100": "🔥 100 кейсов",
            "bj_win": "🃏 Победа в БД", "crash_win": "📈 Победа в Crash", "referral_3": "👥 3 реферала"
        }
        text = "🏆 <b>ДОСТИЖЕНИЯ</b>\n━━━━━━━━━━━━━━━━━━\n"
        for k, name in ach_list.items():
            text += f"{'✅' if k in user_ach else '❌'} {name}\n"
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "ref")
async def ref(cb: CallbackQuery):
    try:
        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        text = f"👥 <b>РЕФЕРАЛЫ</b>\n━━━━━━━━━━━━━━━━━━\nПригласи 3 друзей и получи доступ к выводу!\nВаши рефералы: {user['referrals']}/3\n\n🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>"
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "top_players")
async def top_players(cb: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT full_name, balance FROM users ORDER BY balance DESC LIMIT 5") as cur:
                tops = await cur.fetchall()
        text = "🏆 <b>ТОП 5 ИГРОКОВ</b>\n━━━━━━━━━━━━━━━━━━\n"
        for i, (name, bal) in enumerate(tops, 1): text += f"{i}. <b>{name}</b> — {bal} 💰\n"
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= БОНУСЫ / КОЛЕСО =================
@dp.callback_query(F.data == "daily_bonus")
async def daily_bonus(cb: CallbackQuery):
    try:
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        today = datetime.date.today()
        today_str = str(today)
        yesterday_str = str(today - datetime.timedelta(days=1))
        last = user['last_bonus']
        if last == today_str: return await cb.answer("❌ ВЫ УЖЕ ЗАБРАЛИ БОНУС СЕГОДНЯ!", show_alert=True)
        streak = user['bonus_streak']
        if last == yesterday_str: streak += 1
        else: streak = 1
        if streak > 7: streak = 1
        rewards = {1: 5000, 2: 7000, 3: 10000, 4: 12000, 5: 15000, 6: 18000, 7: 25000}
        reward = rewards.get(streak, 5000)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET balance = balance + ?, last_bonus = ?, bonus_streak = ? WHERE user_id = ?", (reward, today_str, streak, cb.from_user.id))
            await db.commit()
        await cb.answer(f"✅ БОНУС: {reward} 💰\n🔥 Серия: {streak}/7 дней!", show_alert=True)
        await back_main(cb, state=None)
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "wheel")
async def wheel_spin(cb: CallbackQuery):
    try:
        prizes = [100, 500, 1000, 5000, 10000, 50000, "ДЖЕКПОТ"]
        weights = [40, 25, 15, 10, 7, 2.9, 0.1]
        prize = random.choices(prizes, weights=weights, k=1)[0]
        msg = await cb.message.edit_text("🎰 <b>КРУТИМ КОЛЕСО...</b>")
        await asyncio.sleep(0.5)
        if prize == "ДЖЕКПОТ":
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur:
                    jp = (await cur.fetchone())[0]
                await db.execute("UPDATE jackpot SET amount = 0 WHERE id = 1")
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (jp, cb.from_user.id))
                await db.commit()
            await msg.edit_text(f"🎉 <b>ДЖЕКПОТ!!!</b>\nВы выиграли {jp} 💰!", reply_markup=back_btn())
        else:
            await upd_bal(cb.from_user.id, prize, add_jackpot=False)
            await msg.edit_text(f"🎉 <b>ВЫ ВЫИГРАЛИ:</b> {prize} 💰", reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= КВЕСТЫ =================
@dp.callback_query(F.data == "quests")
async def quests_menu(cb: CallbackQuery):
    try:
        quests = {"open_1": {"name": "Открой 1 кейс", "target": 1, "reward": 2000}, "upgrade_1": {"name": "Сделай 1 ставку", "target": 1, "reward": 3000}, "ref_1": {"name": "Пригласи 1 друга", "target": 1, "reward": 5000}}
        text = "🎯 <b>КВЕСТЫ</b>\n━━━━━━━━━━━━━━━━━━\n"
        kb = []
        async with aiosqlite.connect(DB_PATH) as db:
            for k, q in quests.items():
                async with db.execute("SELECT progress, claimed FROM quests WHERE user_id = ? AND quest_key = ?", (cb.from_user.id, k)) as cur:
                    row = await cur.fetchone()
                    prog = row[0] if row else 0
                    claimed = row[1] if row else 0
                status = "✅" if claimed else "⏳"
                text += f"{status} {q['name']} ({prog}/{q['target']}) — {q['reward']}💰\n"
                if prog >= q['target'] and not claimed:
                    kb.append([InlineKeyboardButton(text=f"🎁 ЗАБРАТЬ: {q['name']}", callback_data=f"claim_{k}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

async def update_quest_progress(user_id, quest_type):
    try:
        quests = {"case": "open_1", "bet": "upgrade_1", "ref": "ref_1"}
        q_key = quests.get(quest_type)
        if not q_key: return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO quests (user_id, quest_key, progress) VALUES (?, ?, 1) ON CONFLICT(user_id, quest_key) DO UPDATE SET progress = progress + 1", (user_id, q_key))
            await db.commit()
    except: pass

@dp.callback_query(F.data.startswith("claim_"))
async def claim_quest(cb: CallbackQuery):
    try:
        q_key = cb.data.split("_")[1]
        quests = {"open_1": 2000, "upgrade_1": 3000, "ref_1": 5000}
        target = {"open_1": 1, "upgrade_1": 1, "ref_1": 1}
        reward = quests.get(q_key, 0)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT progress, claimed FROM quests WHERE user_id = ? AND quest_key = ?", (cb.from_user.id, q_key)) as cur:
                row = await cur.fetchone()
                if not row or row[0] < target[q_key] or row[1] == 1:
                    return await cb.answer("❌ Нельзя забрать!", show_alert=True)
            await db.execute("UPDATE quests SET claimed = 1 WHERE user_id = ? AND quest_key = ?", (cb.from_user.id, q_key))
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, cb.from_user.id))
            await db.commit()
        await cb.answer(f"✅ ПОЛУЧЕНО {reward} МОНЕТ!", show_alert=True)
        await quests_menu(cb)
    except: await cb.answer("Ошибка", show_alert=True)

# ================= CRASH =================
@dp.callback_query(F.data == "crash_game")
async def crash_game(cb: CallbackQuery, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur:
                jp = (await cur.fetchone())[0]
        text = f"🎰 <b>CRASH</b>\n━━━━━━━━━━━━━━━━━━\n💸 Множитель растет, но может упасть!\n🏆 Джекпот: {jp} 💰\n\nВведите сумму ставки:"
        await cb.message.edit_text(text, reply_markup=back_btn("games"))
        await state.set_state(UserState.waiting_crash_bet)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(UserState.waiting_crash_bet)
async def crash_bet(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
        bet = int(message.text)
        if bet <= 0: return await message.answer("❌ Ставка должна быть больше 0!")
        user = await safe_get_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        if user['balance'] < bet: return await message.answer("❌ НЕДОСТАТОЧНО МОНЕТ!")
        await state.update_data(bet=bet)
        await upd_bal(message.from_user.id, -bet)
        await state.clear()
        crash_chance = int(await get_setting("real_chance_crash") or 40) / 100.0
        crash_point = random.uniform(1.1, 10.0) if random.random() > crash_chance else random.uniform(1.01, 1.5)
        msg = await message.answer("📈 <b>CRASH...</b>\nМножитель: x1.00\n\nНажмите ЗАБРАТЬ!")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="crash_take")]])
        await msg.edit_text("📈 <b>CRASH...</b>\nМножитель: x1.00\n\nНажмите ЗАБРАТЬ!", reply_markup=kb)
        for i in range(1, 20):
            mult = 1 + (i * 0.5)
            if mult >= crash_point:
                await msg.edit_text(f"💥 <b>КРАШ!</b>\nМножитель: x{mult:.2f}\nВы потеряли {bet} 💰!", reply_markup=back_btn("games"))
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("INSERT INTO crash_history (user_id, bet, multiplier, win, timestamp) VALUES (?, ?, ?, ?, ?)", (message.from_user.id, bet, mult, 0, datetime.datetime.now().isoformat()))
                    await db.commit()
                return
            try: await msg.edit_text(f"📈 <b>CRASH...</b>\nМножитель: x{mult:.2f}\n\nНажмите ЗАБРАТЬ!", reply_markup=kb)
            except: pass
            await asyncio.sleep(0.8)
    except: await message.answer("Ошибка в игре")

@dp.callback_query(F.data == "crash_take")
async def crash_take(cb: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        bet = data.get("bet", 0)
        if bet == 0: return await cb.answer("❌ Ставка не найдена!", show_alert=True)
        win = int(bet * 1.5)
        await upd_bal(cb.from_user.id, win, add_jackpot=False)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO crash_history (user_id, bet, multiplier, win, timestamp) VALUES (?, ?, ?, ?, ?)", (cb.from_user.id, bet, 1.5, 1, datetime.datetime.now().isoformat()))
            await db.commit()
        await cb.message.edit_text(f"✅ <b>ВЫ ЗАБРАЛИ!</b>\nВыигрыш: {win} 💰 (x1.5)", reply_markup=back_btn("games"))
        await state.clear()
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= МАГАЗИН И КЕЙСЫ =================
@dp.callback_query(F.data == "shop")
async def shop_menu(cb: CallbackQuery):
    try:
        price = await get_setting("shop_price") or "100000"
        text = f"🛒 <b>МАГАЗИН</b>\n━━━━━━━━━━━━━━━━━━\n💱 <b>Курс:</b> {price} Монет = 10 Коэнов\n\nВведите количество Коэнов (кратно 10):"
        await cb.message.edit_text(text, reply_markup=back_btn())
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "cases")
async def cases_menu(cb: CallbackQuery):
    try:
        cases = await get_cases()
        kb = []
        for k, c in cases.items(): kb.append([InlineKeyboardButton(text=f"{c['name']}", callback_data=f"view_{k}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
        await cb.message.edit_text("🎁 <b>ВЫБЕРИ КЕЙС</b>\n━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("view_"))
async def view_case(cb: CallbackQuery):
    try:
        key = cb.data.split("_")[1]
        cases = await get_cases()
        if key not in cases: return await cb.answer("Кейс не найден!", show_alert=True)
        case = cases[key]
        items = await get_case_items(key)
        text = f"🎁 <b>{case['name'].upper()}</b>\n━━━━━━━━━━━━━━━━━━\n"
        for item in items: text += f"▪️ {item[1]} — {item[5]}\n"
        text += "━━━━━━━━━━━━━━━━━━"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ ЗА {case['price']} STARS", callback_data=f"open_{key}_stars"), InlineKeyboardButton(text=f"💎 ЗА {case['coin_price']} КОЭНОВ", callback_data=f"open_{key}_coins")],
            [InlineKeyboardButton(text=f"💰 ЗА {case['mon_price']} МОНЕТ", callback_data=f"open_{key}_mon")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="cases")]
        ])
        await cb.message.edit_text(text, reply_markup=kb)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_stars"))
async def open_stars(cb: CallbackQuery):
    try:
        key = cb.data.split("_")[1]
        cases = await get_cases()
        if key not in cases: return await cb.answer("Ошибка", show_alert=True)
        case = cases[key]
        prices = [LabeledPrice(label=case["name"], amount=int(case["price"]))]
        await bot.send_invoice(chat_id=cb.from_user.id, title=case["name"], description="Открыть кейс?", payload=f"case_{key}", provider_token="", currency="XTR", prices=prices)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_coins"))
async def open_coins(cb: CallbackQuery):
    try:
        if await get_setting("panic") == "True": return await cb.answer("🚨 БОТ НА ПАНИКЕ!", show_alert=True)
        key = cb.data.split("_")[1]
        cases = await get_cases()
        if key not in cases: return await cb.answer("Ошибка", show_alert=True)
        case = cases[key]
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        if user['coins'] < case["coin_price"]: return await cb.answer("❌ НЕДОСТАТОЧНО КОЭНОВ!", show_alert=True)
        await upd_bal(cb.from_user.id, -case["coin_price"], is_coin=True)
        msg = await play_animation(cb.message, case['name'])
        item_id, name, rarity, val, w, fake = await open_case(key, cb.from_user.id)
        await add_item(cb.from_user.id, name, rarity, val)
        await add_xp(cb.from_user.id, 10)
        await update_quest_progress(cb.from_user.id, "case")
        if await check_achievement(cb.from_user.id, "first_case"):
            try: await cb.message.answer("🏅 <b>ДОСТИЖЕНИЕ:</b> Первый кейс!")
            except: pass
        await msg.edit_text(f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐", reply_markup=back_btn("cases"))
        await cb.answer("Поздравляем!")
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_mon"))
async def open_mon(cb: CallbackQuery):
    try:
        if await get_setting("panic") == "True": return await cb.answer("🚨 БОТ НА ПАНИКЕ!", show_alert=True)
        key = cb.data.split("_")[1]
        cases = await get_cases()
        if key not in cases: return await cb.answer("Ошибка", show_alert=True)
        case = cases[key]
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        if user['balance'] < case["mon_price"]: return await cb.answer("❌ НЕДОСТАТОЧНО МОНЕТ!", show_alert=True)
        await upd_bal(cb.from_user.id, -case["mon_price"], is_coin=False)
        msg = await play_animation(cb.message, case['name'])
        item_id, name, rarity, val, w, fake = await open_case(key, cb.from_user.id)
        await add_item(cb.from_user.id, name, rarity, val)
        await add_xp(cb.from_user.id, 10)
        await update_quest_progress(cb.from_user.id, "case")
        await msg.edit_text(f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐", reply_markup=back_btn("cases"))
        await cb.answer("Поздравляем!")
    except: await cb.answer("Ошибка", show_alert=True)

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_pay(message: Message):
    try:
        key = message.successful_payment.invoice_payload.split("_")[1]
        item_id, name, rarity, val, w, fake = await open_case(key, message.from_user.id)
        await add_item(message.from_user.id, name, rarity, val)
        await add_xp(message.from_user.id, 10)
        await message.answer(f"🎉 Вы выиграли: <b>{name}</b>", reply_markup=await main_menu(message.from_user.id))
    except: await message.answer("Ошибка при оплате.")

@dp.callback_query(F.data == "inv")
async def inv(cb: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, item_name, value FROM inventory WHERE user_id = ? AND is_withdrawn = 0", (cb.from_user.id,)) as cur:
                items = await cur.fetchall()
        if not items: return await cb.message.edit_text("🎒 <b>ИНВЕНТАРЬ ПУСТ</b>", reply_markup=back_btn())
        text = "🎒 <b>ТВОЙ ИНВЕНТАРЬ</b>\n━━━━━━━━━━━━━━━━━━\n"
        kb = []
        for i, name, val in items:
            text += f"▪️ {name} ({val}⭐)\n"
            kb.append([InlineKeyboardButton(text=f"💸 ПРОДАТЬ", callback_data=f"sell_{i}"), InlineKeyboardButton(text=f"📦 ВЫВЕСТИ", callback_data=f"withdraw_{i}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("sell_"))
async def sell(cb: CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[1])
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT value FROM inventory WHERE id = ?", (item_id,)) as cur:
                row = await cur.fetchone()
                if not row: return await cb.answer("❌ Предмет не найден!", show_alert=True)
                val = row[0]
            await db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (val, cb.from_user.id))
            await db.commit()
        await cb.answer(f"✅ ПРОДАНО ЗА {val} МОНЕТ!", show_alert=True)
        await inv(cb)
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("withdraw_"))
async def withdraw(cb: CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[1])
        user = await safe_get_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        if user['referrals'] < 3: return await cb.answer(f"❌ НУЖНО 3 РЕФЕРАЛА! У тебя: {user['referrals']}/3", show_alert=True)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT item_name FROM inventory WHERE id = ?", (item_id,)) as cur:
                row = await cur.fetchone()
                if not row: return await cb.answer("❌ Предмет не найден!", show_alert=True)
                item_name = row[0]
            code = gen_code(8)
            await db.execute("INSERT INTO coupons (code, user_id, item_name) VALUES (?, ?, ?)", (code, cb.from_user.id, item_name))
            await db.execute("UPDATE inventory SET is_withdrawn = 1 WHERE id = ?", (item_id,))
            await db.commit()
        await cb.message.edit_text(f"🎉 <b>КУПОН СОЗДАН!</b>\n\nКод: <code>{code}</code>\nОтправь его админу: {CONTACT_ADMIN}", reply_markup=back_btn("inv"))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= ИГРЫ =================
@dp.callback_query(F.data == "games")
async def games(cb: CallbackQuery):
    try:
        bj_chance = await get_setting("bj_chance") or "20"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🎮 АПГРЕЙД X2 (50%)", callback_data="game_up")],
            [InlineKeyboardButton(text=f"🪙 МОНЕТКА (50%)", callback_data="game_coin")],
            [InlineKeyboardButton(text=f"🃏 БЛЭКДЖЕК ({bj_chance}%)", callback_data="game_bj")],
            [InlineKeyboardButton(text=f"📈 CRASH", callback_data="crash_game")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")]
        ])
        await cb.message.edit_text("🎮 <b>ИГРЫ</b>", reply_markup=kb)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("game_"))
async def game_bet(cb: CallbackQuery, state: FSMContext):
    try:
        await state.update_data(game=cb.data)
        await cb.message.edit_text("💰 <b>ВВЕДИ СУММУ СТАВКИ:</b>", reply_markup=back_btn("games"))
        await state.set_state(UserState.waiting_bet)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(UserState.waiting_bet)
async def play_game(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
        bet = int(message.text)
        if bet <= 0: return await message.answer("❌ Ставка должна быть больше 0!")
        user = await safe_get_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        if user['balance'] < bet: return await message.answer("❌ НЕДОСТАТОЧНО МОНЕТ!")
        data = await state.get_data()
        game = data.get("game")
        await state.clear()
        await upd_bal(message.from_user.id, -bet)
        await update_quest_progress(message.from_user.id, "bet")
        await add_xp(message.from_user.id, 5)
        
        if game == "game_up": win = random.random() < (int(await get_setting("real_chance_up") or 50) / 100.0)
        elif game == "game_coin": win = random.random() < (int(await get_setting("real_chance_coin") or 50) / 100.0)
        elif game == "game_bj": win = random.random() < (int(await get_setting("real_chance_bj") or 20) / 100.0)
        else: win = False
        
        if win:
            await upd_bal(message.from_user.id, bet * 2)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET wins_count = wins_count + 1 WHERE user_id = ?", (message.from_user.id,))
                await db.commit()
            await message.answer(f"🎉 <b>ПОБЕДА!</b>\nТы выиграл <b>{bet * 2}</b> монет.", reply_markup=await main_menu(message.from_user.id))
        else:
            await message.answer(f"😢 <b>ПРОИГРЫШ.</b>\nТы потерял <b>{bet}</b> монет.", reply_markup=await main_menu(message.from_user.id))
    except: await message.answer("Ошибка в игре")

@dp.callback_query(F.data == "promo")
async def promo_enter(cb: CallbackQuery, state: FSMContext):
    try:
        await cb.message.edit_text("🔑 <b>ВВЕДИ ПРОМОКОД:</b>", reply_markup=back_btn())
        await state.set_state(UserState.waiting_promo)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(UserState.waiting_promo)
async def promo_check(message: Message, state: FSMContext):
    try:
        code = message.text.upper().strip()
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM promo_activations WHERE user_id = ? AND code = ?", (message.from_user.id, code)) as cur:
                if await cur.fetchone():
                    return await message.answer("❌ ВЫ УЖЕ АКТИВИРОВАЛИ ЭТОТ ПРОМОКОД!", reply_markup=await main_menu(message.from_user.id))
            async with db.execute("SELECT reward, uses_left FROM promo_codes WHERE code = ?", (code,)) as cur:
                promo = await cur.fetchone()
            if not promo or promo[1] <= 0: return await message.answer("❌ НЕВЕРНЫЙ ПРОМОКОД.", reply_markup=await main_menu(message.from_user.id))
            await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[0], message.from_user.id))
            await db.execute("INSERT INTO promo_activations (user_id, code) VALUES (?, ?)", (message.from_user.id, code))
            await db.commit()
        await message.answer(f"✅ <b>АКТИВИРОВАН!</b>\nПолучено <b>{promo[0]}</b> монет.", reply_markup=await main_menu(message.from_user.id))
    except: await message.answer("Ошибка при вводе промокода.")

# ================= ПОКУПКА ЗВЕЗД =================
@dp.callback_query(F.data == "buy_stars")
async def buy_stars_menu(cb: CallbackQuery):
    try:
        items = [("50", "50 ⭐ Stars", 1.19), ("100", "100 ⭐ Stars", 2.39), ("150", "150 ⭐ Stars", 3.69), ("250", "250 ⭐ Stars", 6.09), ("500", "500 ⭐ Stars", 11.99), ("1000", "1000 ⭐ Stars", 23.99), ("10000", "10000 ⭐ Stars", 239.00),
                 ("prem3", "👑 Premium 3 мес", 17.99), ("prem6", "👑 Premium 6 мес", 22.99), ("prem12", "👑 Premium 12 мес", 39.99)]
        kb = []
        for key, name, usd in items:
            byn = round(usd * USD_TO_BYN, 2)
            kb.append([InlineKeyboardButton(text=f"{name} | {usd}$ | {byn} BYN", callback_data=f"order_{key}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
        await cb.message.edit_text("⭐ <b>Магазин Stars и Premium</b>\n\nВыберите товар:\n(Цены указаны в долларах и белорусских рублях)", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("order_"))
async def create_star_order(cb: CallbackQuery):
    try:
        key = cb.data.split("_")[1]
        prices = {"50": 1.19, "100": 2.39, "150": 3.69, "250": 6.09, "500": 11.99, "1000": 23.99, "10000": 239.00, "prem3": 17.99, "prem6": 22.99, "prem12": 39.99}
        names = {"50": "50 Stars", "100": "100 Stars", "150": "150 Stars", "250": "250 Stars", "500": "500 Stars", "1000": "1000 Stars", "10000": "10000 Stars", "prem3": "Premium 3 мес", "prem6": "Premium 6 мес", "prem12": "Premium 12 мес"}
        usd = prices[key]
        byn = round(usd * USD_TO_BYN, 2)
        name = names[key]
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO star_orders (user_id, item_key, item_name, price_byn, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                             (cb.from_user.id, key, name, byn, datetime.datetime.now().isoformat()))
            await db.commit()
            
        text = f"⭐ <b>Заказ: {name}</b>\n\nСтоимость: <b>{usd}$</b> (~{byn} BYN)\n\n💳 <b>Реквизиты для оплаты:</b>\n<code>{CARD_NUMBER}</code> ({CARD_BANK})\n\n📩 Отправьте чек админу: {CONTACT_ADMIN}\n\n⚠️ После оплаты заказ появится в админ-панели для подтверждения."
        await cb.message.edit_text(text, reply_markup=back_btn("buy_stars"))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= АДМИНКА =================
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    try:
        rank = await get_admin_rank(message.from_user.id)
        if rank == 0: return
        await message.answer("👑 <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=await admin_menu(rank, message.from_user.id))
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(cb: CallbackQuery):
    try:
        rank = await get_admin_rank(cb.from_user.id)
        if rank == 0: return await cb.answer("Нет прав!", show_alert=True)
        await cb.message.edit_text("👑 <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=await admin_menu(rank, cb.from_user.id))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    try:
        await cb.message.delete()
        await cb.answer()
    except: await cb.answer("Ошибка")

@dp.callback_query(F.data == "admin_help")
async def admin_help(cb: CallbackQuery):
    try:
        text = (
            "📖 <b>СПРАВОЧНИК АДМИНИСТРАТОРА</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "👑 <b>ГЛАВНЫЕ КОМАНДЫ:</b>\n"
            "▪️ /start — Открыть главное меню\n"
            "▪️ /menu — Открыть главное меню\n"
            "▪️ /admin — Открыть админ-панель\n\n"
            "📊 <b>СТАТИСТИКА:</b>\n"
            "Показывает общее число юзеров, активных сегодня, денег в системе и джекпот.\n\n"
            "🎁 <b>КУПОНЫ:</b>\n"
            "Позволяет проверить код купона, который ввел игрок, и подтвердить выдачу предмета.\n\n"
            "🔑 <b>ПРОМО:</b>\n"
            "Создание промокода. Вы задаете сумму награды и количество активаций. Бот выдаст код.\n\n"
            "🚫 <b>БАНЫ:</b>\n"
            "Бан по ID (с причиной) и разбан. Также есть список всех забаненных.\n\n"
            "💰 <b>ВЫДАТЬ ВАЛЮТУ / ИЗМЕНИТЬ БАЛАНС:</b>\n"
            "Начисление или списание Монет и Коэнов конкретному игроку по его ID.\n\n"
            "🚨 <b>ПАНИКА:</b>\n"
            "Экстренная блокировка. Запрещает открывать кейсы и играть (защита от взлома/бага).\n\n"
            "🛠 <b>ТЕХ.РАБОТЫ:</b>\n"
            "Бот перестает отвечать обычным юзерам (только админы могут зайти).\n\n"
            "👥 <b>HR-ПАНЕЛЬ:</b>\n"
            "▪️ Логи — история действий админов.\n"
            "▪️ Назначить Зама — выдает права 2-го уровня (купоны, промо, баны).\n\n"
            "⚙️ <b>ШАНСЫ БД / НАСТРОЙКА CRASH:</b>\n"
            "Изменение процента победы в Блэкджеке и частоты краша в Crash-игре.\n\n"
            "🛒 <b>МАГАЗИН:</b>\n"
            "Изменение курса обмена Монет на Коэны.\n\n"
            "🎁 <b>КЕЙСЫ:</b>\n"
            "▪️ Создание новых кейсов.\n"
            "▪️ Добавление/редактирование/удаление предметов.\n"
            "▪️ Настройка их цены, веса и шанса выпадения.\n\n"
            "🎲 <b>РЕАЛЬНЫЙ ШАНС:</b>\n"
            "Настройка реального шанса выигрыша в играх (Апгрейд, Монетка, БД, Crash) и в кейсах.\n\n"
            "🎭 <b>ЛИПОВЫЙ ШАНС:</b>\n"
            "Настройка текста шанса, который видят игроки. Можно написать '50%', а реальный оставить 1%.\n\n"
            "🏷️ <b>НАЗВАНИЯ КНОПОК:</b>\n"
            "Изменение текста на кнопках главного меню. Можно вставлять любые эмодзи и прем-стикеры.\n\n"
            "⭐ <b>НАСТРОЙКА ЦЕН STARS:</b>\n"
            "Изменение цен на товары в магазине Stars/Премиум.\n\n"
            "✅ <b>ПОДТВЕРДИТЬ STARS:</b>\n"
            "Просмотр и подтверждение заказов на покупку Telegram Stars/Premium.\n\n"
            "📢 <b>РАССЫЛКА:</b>\n"
            "Отправка сообщения всем пользователям бота.\n\n"
            "💾 <b>БД:</b>\n"
            "Скачивание файла базы данных (бэкап).\n\n"
            "🎰 <b>PITY-ПОРОГ:</b>\n"
            "Количество неудачных открытий кейса подряд, после которого игроку гарантированно падает редкий предмет (legendary/mythic)."
        )
        await cb.message.edit_text(text, reply_markup=back_btn("close_admin"))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= АДМИН: РЕАЛЬНЫЙ ШАНС =================
@dp.callback_query(F.data == "admin_real_chance")
async def admin_real_chance(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        kb = [
            [InlineKeyboardButton(text="🎮 Апгрейд X2", callback_data="set_real_up"), InlineKeyboardButton(text="🪙 Монетка", callback_data="set_real_coin")],
            [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="set_real_bj"), InlineKeyboardButton(text="📈 Crash", callback_data="set_real_crash")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")]
        ]
        await cb.message.edit_text("🎲 <b>НАСТРОЙКА РЕАЛЬНОГО ШАНСА</b>\n\nВыберите игру:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("set_real_"))
async def set_real_chance_prompt(cb: CallbackQuery, state: FSMContext):
    try:
        game = cb.data.split("_")[2]
        if game == "up": key = "real_chance_up"
        elif game == "coin": key = "real_chance_coin"
        elif game == "bj": key = "real_chance_bj"
        elif game == "crash": key = "real_chance_crash"
        else: return
        await state.update_data(chance_key=key)
        current = await get_setting(key) or "50"
        await cb.message.edit_text(f"Текущий реальный шанс: <b>{current}%</b>\n\nВведите новый шанс (в %):", reply_markup=back_btn("admin_real_chance"))
        await state.set_state(AdminState.waiting_real_chance_val)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_real_chance_val)
async def set_real_chance_val(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        data = await state.get_data()
        await set_setting(data['chance_key'], message.text)
        await message.answer(f"✅ Шанс обновлен: {message.text}%", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

# ================= АДМИН: ЛИПОВЫЙ ШАНС =================
@dp.callback_query(F.data == "admin_fake_chance")
async def admin_fake_chance(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        kb = [
            [InlineKeyboardButton(text="🎮 Апгрейд X2", callback_data="set_fake_up"), InlineKeyboardButton(text="🪙 Монетка", callback_data="set_fake_coin")],
            [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="set_fake_bj"), InlineKeyboardButton(text="📈 Crash", callback_data="set_fake_crash")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")]
        ]
        await cb.message.edit_text("🎭 <b>НАСТРОЙКА ЛИПОВОГО ШАНСА (ТЕКСТ)</b>\n\nВыберите игру, чтобы изменить текст на кнопке:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("set_fake_"))
async def set_fake_chance_prompt(cb: CallbackQuery, state: FSMContext):
    try:
        game = cb.data.split("_")[2]
        if game == "up": key = "fake_text_up"
        elif game == "coin": key = "fake_text_coin"
        elif game == "bj": key = "fake_text_bj"
        elif game == "crash": key = "fake_text_crash"
        else: return
        await state.update_data(fake_key=key)
        current = await get_setting(key) or "50%"
        await cb.message.edit_text(f"Текущий текст: <b>{current}</b>\n\nВведите новый текст (например, '50%'):", reply_markup=back_btn("admin_fake_chance"))
        await state.set_state(AdminState.waiting_fake_chance_val)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_fake_chance_val)
async def set_fake_chance_val(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        await set_setting(data['fake_key'], message.text)
        await message.answer(f"✅ Текст обновлен: {message.text}", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

# ================= АДМИН: ПОДТВЕРЖДЕНИЕ STARS =================
@dp.callback_query(F.data == "admin_confirm_stars")
async def admin_confirm_stars(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, user_id, item_name, price_byn, created_at FROM star_orders WHERE status = 'pending'") as cur:
                orders = await cur.fetchall()
        
        if not orders:
            return await cb.message.edit_text("✅ Нет новых заказов на Stars/Premium.", reply_markup=back_btn("close_admin"))
        
        text = "✅ <b>НОВЫЕ ЗАКАЗЫ (ОЖИДАЮТ ОПЛАТЫ):</b>\n\n"
        kb = []
        for o in orders:
            order_id, user_id, item_name, price_byn, created_at = o
            text += f"🆔 Заказ #{order_id}\n👤 Юзер: {user_id}\n📦 Товар: {item_name}\n💰 Сумма: {price_byn} BYN\n\n"
            kb.append([InlineKeyboardButton(text=f"✅ Подтвердить #{order_id}", callback_data=f"confirm_order_{order_id}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")])
        
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_order_"))
async def admin_confirm_order(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        order_id = int(cb.data.split("_")[2])
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, item_name FROM star_orders WHERE id = ?", (order_id,)) as cur:
                order = await cur.fetchone()
            if not order: return await cb.answer("Заказ не найден!", show_alert=True)
            await db.execute("UPDATE star_orders SET status = 'confirmed' WHERE id = ?", (order_id,))
            await db.commit()
            
        user_id, item_name = order
        await cb.message.edit_text(f"✅ Заказ #{order_id} подтверждён! Выдайте {item_name} пользователю {user_id} вручную.", reply_markup=back_btn("admin_confirm_stars"))
        try: await bot.send_message(user_id, f"🎉 Ваш заказ <b>{item_name}</b> подтверждён! Ожидайте выдачи.")
        except: pass
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

# ================= АДМИН: НАСТРОЙКА ЦЕН STARS =================
@dp.callback_query(F.data == "admin_stars_prices")
async def admin_stars_prices(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        kb = [
            [InlineKeyboardButton(text="50 Stars", callback_data="sp_50"), InlineKeyboardButton(text="100 Stars", callback_data="sp_100")],
            [InlineKeyboardButton(text="150 Stars", callback_data="sp_150"), InlineKeyboardButton(text="250 Stars", callback_data="sp_250")],
            [InlineKeyboardButton(text="500 Stars", callback_data="sp_500"), InlineKeyboardButton(text="1000 Stars", callback_data="sp_1000")],
            [InlineKeyboardButton(text="10000 Stars", callback_data="sp_10000")],
            [InlineKeyboardButton(text="Premium 3 мес", callback_data="sp_prem3"), InlineKeyboardButton(text="Premium 6 мес", callback_data="sp_prem6")],
            [InlineKeyboardButton(text="Premium 12 мес", callback_data="sp_prem12")],
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")]
        ]
        await cb.message.edit_text("⭐ <b>НАСТРОЙКА ЦЕН STARS/PREMIUM</b>\n\nВыберите товар для изменения цены (в долларах):", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("sp_"))
async def stars_price_set(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        key = cb.data[3:]
        await state.update_data(price_key=key)
        current = await get_setting(f"price_{key}_usd") or "0"
        await cb.message.edit_text(f"Текущая цена: <b>{current}$</b>\n\nВведите новую цену в долларах (например 2.39):", reply_markup=back_btn("admin_stars_prices"))
        await state.set_state(AdminState.waiting_stars_price)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_stars_price)
async def stars_price_save(message: Message, state: FSMContext):
    try:
        try: float(message.text)
        except: return await message.answer("Введите число (например 2.39)!")
        data = await state.get_data()
        await set_setting(f"price_{data['price_key']}_usd", message.text)
        await message.answer(f"✅ Цена обновлена: {message.text}$", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

# ================= АДМИН: ОСТАЛЬНОЕ =================
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) < 2: return await cb.answer("Нет прав!", show_alert=True)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cur: total_users = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE last_bonus = ?", (str(datetime.date.today()),)) as cur: active_today = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM inventory") as cur: total_items = (await cur.fetchone())[0]
            async with db.execute("SELECT SUM(balance) FROM users") as cur: total_money = (await cur.fetchone())[0] or 0
            async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur: jp = (await cur.fetchone())[0]
        text = f"📊 <b>СТАТИСТИКА</b>\n━━━━━━━━━━━━━━━━━━\n👥 Юзеров: {total_users}\n🔥 Активных: {active_today}\n🎒 Предметов: {total_items}\n💰 Денег: {total_money}\n🏆 Джекпот: {jp}\n━━━━━━━━━━━━━━━━━━"
        await cb.message.edit_text(text, reply_markup=back_btn("close_admin"))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "admin_panic")
async def admin_panic(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        cur = await get_setting("panic") == "True"
        await set_setting("panic", str(not cur))
        await add_hr_log(cb.from_user.id, "TOGGLE_PANIC", f"Panic: {not cur}")
        await cb.answer(f"🚨 ПАНИКА: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "admin_maint")
async def admin_maint(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        cur = await get_setting("maintenance") == "True"
        await set_setting("maintenance", str(not cur))
        await add_hr_log(cb.from_user.id, "TOGGLE_MAINT", f"Maint: {not cur}")
        await cb.answer(f"🛠 ТЕХ.РАБОТЫ: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        await cb.message.edit_text("📢 <b>РАССЫЛКА</b>\nОтправьте текст:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_broadcast_msg)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_broadcast_msg)
async def do_broadcast(message: Message, state: FSMContext):
    try:
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM users") as cur:
                users = await cur.fetchall()
        success, fail = 0, 0
        await message.answer(f"📢 Начинаю рассылку для {len(users)}...")
        for u in users:
            try:
                await bot.send_message(u[0], message.text)
                success += 1
                await asyncio.sleep(0.05)
            except: fail += 1
        await message.answer(f"✅ <b>ЗАВЕРШЕНО!</b>\nУспешно: {success}\nОшибок: {fail}", reply_markup=await admin_menu(3, message.from_user.id))
    except: await message.answer("Ошибка при рассылке")

@dp.callback_query(F.data == "admin_backup")
async def admin_backup(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        doc = FSInputFile(DB_PATH)
        await bot.send_document(cb.from_user.id, doc, caption="💾 Резервная копия БД")
        await cb.answer()
    except Exception as e: await cb.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data == "admin_pity")
async def admin_pity(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        th = await get_setting("pity_threshold") or "30"
        await cb.message.edit_text(f"Текущий pity-порог: <b>{th}</b> неудач.\n\nВведите новый порог:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_pity_threshold)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_pity_threshold)
async def set_pity_threshold(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Введите число!")
        await set_setting("pity_threshold", message.text)
        await message.answer(f"✅ Pity-порог: {message.text}", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

# --- КЕЙСЫ: РЕДАКТИРОВАНИЕ ---
@dp.callback_query(F.data == "admin_cases")
async def admin_cases(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        cases = await get_cases()
        kb = []
        for k, c in cases.items(): kb.append([InlineKeyboardButton(text=f"{c['name']} ({k})", callback_data=f"editcase_{k}")])
        kb.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ КЕЙС", callback_data="add_case")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")])
        await cb.message.edit_text("🎁 <b>УПРАВЛЕНИЕ КЕЙСАМИ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("editcase_"))
async def edit_case_menu(cb: CallbackQuery):
    try:
        key = cb.data.split("_")[1]
        cases = await get_cases()
        if key not in cases: return await cb.answer("Кейс не найден!", show_alert=True)
        c = cases[key]
        items = await get_case_items(key)
        text = f"🎁 <b>{c['name']}</b> (key: {key})\n💰 Монеты: {c['mon_price']}\n💎 Коэны: {c['coin_price']}\n⭐ Stars: {c['price']}\n\n<b>Предметы:</b>\n"
        kb = []
        for item in items:
            text += f"▪️ [id:{item[0]}] {item[1]} ({item[2]}) — {item[5]} (вес: {item[4]})\n"
            kb.append([
                InlineKeyboardButton(text=f"✏️ Имя", callback_data=f"edititem_{item[0]}"),
                InlineKeyboardButton(text=f"🎲 Шанс", callback_data=f"edititemchance_{item[0]}"),
                InlineKeyboardButton(text=f"🎭 Липа", callback_data=f"edititemfake_{item[0]}"),
                InlineKeyboardButton(text=f"🗑", callback_data=f"delitem_{item[0]}")
            ])
        text += f"\nВсего: {len(items)}"
        kb.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ ПРЕДМЕТ", callback_data=f"additem_{key}")])
        kb.append([InlineKeyboardButton(text="🗑 УДАЛИТЬ КЕЙС", callback_data=f"delcase_{key}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_cases")])
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("delitem_"))
async def delete_item(cb: CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[1])
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT case_key, name FROM case_items WHERE id = ?", (item_id,)) as cur:
                row = await cur.fetchone()
            if not row: return await cb.answer("Не найден!", show_alert=True)
            await db.execute("DELETE FROM case_items WHERE id = ?", (item_id,))
            await db.commit()
        await cb.answer(f"✅ '{row[1]}' удалён!", show_alert=True)
        class FakeCb:
            def __init__(self, data): self.data = data; self.from_user = cb.from_user; self.message = cb.message
            async def answer(self, *a, **k): pass
        await edit_case_menu(FakeCb(f"editcase_{row[0]}"))
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("delcase_"))
async def delete_case_confirm(cb: CallbackQuery, state: FSMContext):
    try:
        key = cb.data.split("_")[1]
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ДА", callback_data=f"delcase_confirm_{key}")], [InlineKeyboardButton(text="❌ НЕТ", callback_data="admin_cases")]])
        await cb.message.edit_text(f"⚠️ Удалить кейс <b>{key}</b>?", reply_markup=kb)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("delcase_confirm_"))
async def delete_case_execute(cb: CallbackQuery):
    try:
        key = cb.data.split("_")[2]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM case_items WHERE case_key = ?", (key,))
            await db.execute("DELETE FROM cases WHERE key = ?", (key,))
            await db.execute("DELETE FROM pity WHERE case_key = ?", (key,))
            await db.commit()
        await cb.answer(f"✅ Кейс {key} удалён!", show_alert=True)
        await admin_cases(cb)
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("edititem_"))
async def edit_item_start(cb: CallbackQuery, state: FSMContext):
    try:
        item_id = int(cb.data.split("_")[1])
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT case_key, name, rarity, value, weight, display_chance FROM case_items WHERE id = ?", (item_id,)) as cur:
                item = await cur.fetchone()
        if not item: return await cb.answer("Не найден!", show_alert=True)
        await state.update_data(edit_item_id=item_id, edit_case_key=item[0])
        await cb.message.edit_text(
            f"✏️ <b>Редактирование</b>\n\nСейчас: <b>{item[1]}</b>\nРедкость: {item[2]}\nЦена: {item[3]}⭐\nВес: {item[4]}\nШанс: {item[5]}\n\nВведите новое название (или /skip):", reply_markup=back_btn("admin_cases"))
        await state.set_state(AdminState.waiting_edit_item_name)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_edit_item_name)
async def edit_item_name(message: Message, state: FSMContext):
    try:
        if message.text != "/skip": await state.update_data(edit_item_name=message.text)
        await message.answer("Новая редкость (common/rare/epic/legendary/mythic) или /skip:")
        await state.set_state(AdminState.waiting_edit_item_rarity)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_edit_item_rarity)
async def edit_item_rarity(message: Message, state: FSMContext):
    try:
        if message.text != "/skip":
            if message.text.lower() not in ["common", "rare", "epic", "legendary", "mythic"]:
                return await message.answer("❌ Неверная редкость!")
            await state.update_data(edit_item_rarity=message.text.lower())
        await message.answer("Новая цена (число) или /skip:")
        await state.set_state(AdminState.waiting_edit_item_value)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_edit_item_value)
async def edit_item_value(message: Message, state: FSMContext):
    try:
        if message.text != "/skip":
            if not message.text.isdigit(): return await message.answer("Число!")
            await state.update_data(edit_item_value=int(message.text))
        await message.answer("Новый вес (число) или /skip:")
        await state.set_state(AdminState.waiting_edit_item_weight)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_edit_item_weight)
async def edit_item_weight(message: Message, state: FSMContext):
    try:
        if message.text != "/skip":
            try: await state.update_data(edit_item_weight=float(message.text))
            except: return await message.answer("Число!")
        await message.answer("Новый шанс ('5%') или /skip:")
        await state.set_state(AdminState.waiting_edit_item_chance)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_edit_item_chance)
async def edit_item_chance(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        item_id = data['edit_item_id']
        updates, params = [], []
        if 'edit_item_name' in data: updates.append("name = ?"); params.append(data['edit_item_name'])
        if 'edit_item_rarity' in data: updates.append("rarity = ?"); params.append(data['edit_item_rarity'])
        if 'edit_item_value' in data: updates.append("value = ?"); params.append(data['edit_item_value'])
        if 'edit_item_weight' in data: updates.append("weight = ?"); params.append(data['edit_item_weight'])
        if message.text != "/skip": updates.append("display_chance = ?"); params.append(message.text)
        if updates:
            params.append(item_id)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(f"UPDATE case_items SET {', '.join(updates)} WHERE id = ?", params)
                await db.commit()
        await message.answer("✅ Обновлено!", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data.startswith("edititemchance_"))
async def edit_item_chance_prompt(cb: CallbackQuery, state: FSMContext):
    try:
        item_id = int(cb.data.split("_")[1])
        await state.update_data(edit_item_chance_id=item_id)
        await cb.message.edit_text("Введите новый реальный вес (шанс) для этого предмета (например, 5.0):", reply_markup=back_btn("admin_cases"))
        await state.set_state(AdminState.waiting_edit_item_weight)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("edititemfake_"))
async def edit_item_fake_prompt(cb: CallbackQuery, state: FSMContext):
    try:
        item_id = int(cb.data.split("_")[1])
        await state.update_data(edit_item_fake_id=item_id)
        await cb.message.edit_text("Введите липовый шанс для отображения (например, '10%'):", reply_markup=back_btn("admin_cases"))
        await state.set_state(AdminState.waiting_edit_item_chance)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_edit_item_weight)
async def save_item_weight(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        item_id = data.get('edit_item_chance_id')
        if not item_id: return
        weight = float(message.text)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE case_items SET weight = ? WHERE id = ?", (weight, item_id))
            await db.commit()
        await message.answer(f"✅ Вес (реальный шанс) обновлен: {weight}", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_edit_item_chance)
async def save_item_fake(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        item_id = data.get('edit_item_fake_id')
        if not item_id: return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE case_items SET display_chance = ? WHERE id = ?", (message.text, item_id))
            await db.commit()
        await message.answer(f"✅ Липовый шанс обновлен: {message.text}", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "add_case")
async def add_case_start(cb: CallbackQuery, state: FSMContext):
    try:
        await cb.message.edit_text("Ключ (латиница):", reply_markup=back_btn("admin_cases"))
        await state.set_state(AdminState.waiting_case_key)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_case_key)
async def add_case_key(message: Message, state: FSMContext):
    try:
        await state.update_data(key=message.text.strip().lower())
        await message.answer("Название:")
        await state.set_state(AdminState.waiting_case_name)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_case_name)
async def add_case_name(message: Message, state: FSMContext):
    try:
        await state.update_data(name=message.text)
        await message.answer("Цена Stars:")
        await state.set_state(AdminState.waiting_case_price)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_case_price)
async def add_case_price(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        data = await state.get_data()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO cases (key, name, price, coin_price, mon_price) VALUES (?, ?, ?, 0, 0)", (data['key'], data['name'], int(message.text)))
            await db.commit()
        await message.answer(f"✅ Кейс {data['key']} создан!", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data.startswith("additem_"))
async def add_item_start(cb: CallbackQuery, state: FSMContext):
    try:
        await state.update_data(case_key=cb.data.split("_")[1])
        await cb.message.edit_text("Название предмета:", reply_markup=back_btn("admin_cases"))
        await state.set_state(AdminState.waiting_item_name)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_item_name)
async def add_item_name(message: Message, state: FSMContext):
    try:
        await state.update_data(item_name=message.text)
        await message.answer("Редкость:")
        await state.set_state(AdminState.waiting_item_rarity)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_item_rarity)
async def add_item_rarity(message: Message, state: FSMContext):
    try:
        r = message.text.lower()
        if r not in ["common", "rare", "epic", "legendary", "mythic"]: return await message.answer("❌ Неверно!")
        await state.update_data(rarity=r)
        await message.answer("Цена (звезды):")
        await state.set_state(AdminState.waiting_item_value)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_item_value)
async def add_item_value(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        await state.update_data(value=int(message.text))
        await message.answer("Вес (реальный шанс):")
        await state.set_state(AdminState.waiting_item_weight)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_item_weight)
async def add_item_weight(message: Message, state: FSMContext):
    try:
        w = float(message.text)
        await state.update_data(weight=w)
        await message.answer("Липовый шанс (например '50%'):")
        await state.set_state(AdminState.waiting_item_chance)
    except: await message.answer("Число!")

@dp.message(AdminState.waiting_item_chance)
async def add_item_chance(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO case_items (case_key, name, rarity, value, weight, display_chance) VALUES (?, ?, ?, ?, ?, ?)", (data['case_key'], data['item_name'], data['rarity'], data['value'], data['weight'], message.text))
            await db.commit()
        await message.answer("✅ Предмет добавлен!", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

# --- ОСТАЛЬНЫЕ АДМИН-ФУНКЦИИ ---
@dp.callback_query(F.data == "admin_coupon")
async def admin_coupon(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) < 2: return
        await cb.message.edit_text("Код купона:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_coupon)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_coupon)
async def admin_check_coupon(message: Message, state: FSMContext):
    try:
        if await get_admin_rank(message.from_user.id) < 2: return
        code = message.text.strip().upper()
        await state.clear()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT c.user_id, c.item_name, u.full_name, c.status FROM coupons c JOIN users u ON c.user_id = u.user_id WHERE c.code = ?", (code,)) as cur:
                info = await cur.fetchone()
        if not info: return await message.answer("❌ Не найден.", reply_markup=await main_menu(message.from_user.id))
        uid, item, name, status = info
        if status == 'given': return await message.answer("⚠️ УЖЕ ВЫДАН!", reply_markup=await main_menu(message.from_user.id))
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я выдал", callback_data=f"givecoupon_{code}")]])
        await message.answer(f"🔍 {name} ({uid})\n🎁 {item}", reply_markup=kb)
    except: await message.answer("Ошибка при проверке купона")

@dp.callback_query(F.data.startswith("givecoupon_"))
async def admin_give_coupon(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) < 2: return
        code = cb.data.split("_")[1]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE coupons SET status = 'given' WHERE code = ?", (code,))
            await db.commit()
            async with db.execute("SELECT user_id FROM coupons WHERE code = ?", (code,)) as cur:
                uid = (await cur.fetchone())[0]
        await cb.message.edit_text(f"✅ Купон {code} погашен!")
        try: await bot.send_message(uid, f"🎉 Подарок выдан! Купон {code}.")
        except: pass
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "admin_promo")
async def admin_promo(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) < 2: return
        await cb.message.edit_text("Сумма награды:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_promo_val)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_promo_val)
async def admin_promo_val(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return
        await state.update_data(val=int(message.text))
        await message.answer("Активаций:")
        await state.set_state(AdminState.waiting_promo_uses)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_promo_uses)
async def admin_promo_uses(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return
        data = await state.get_data()
        code = gen_code(8)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO promo_codes (code, reward, uses_left) VALUES (?, ?, ?)", (code, data['val'], int(message.text)))
            await db.commit()
        await message.answer(f"✅ Промокод: <code>{code}</code>\n{data['val']}💰, активаций: {message.text}", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_shop")
async def admin_shop(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        price = await get_setting("shop_price") or "100000"
        await cb.message.edit_text(f"Цена: {price} за 10 Коэнов.\nНовая цена:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_shop_price)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_shop_price)
async def admin_set_shop(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        await set_setting("shop_price", message.text)
        await message.answer(f"✅ {message.text} Монет за 10 Коэнов", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_odds")
async def admin_odds(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        bj = await get_setting("bj_chance") or "20"
        await cb.message.edit_text(f"Шанс БД: {bj}%\nНовый шанс:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_bj_chance)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_bj_chance)
async def set_bj_chance(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        await set_setting("bj_chance", message.text)
        await message.answer(f"✅ Шанс БД: {message.text}%", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_crash")
async def admin_crash(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        cc = await get_setting("crash_chance") or "40"
        await cb.message.edit_text(f"Шанс краша: {cc}%\nНовый шанс:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_crash_chance)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_crash_chance)
async def set_crash_chance(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        await set_setting("crash_chance", message.text)
        await message.answer(f"✅ Шанс краша: {message.text}%", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_bans")
async def admin_bans(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) < 2: return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Забанить", callback_data="ban_user"), InlineKeyboardButton(text="✅ Разбанить", callback_data="unban_user")],
            [InlineKeyboardButton(text="📜 Список", callback_data="ban_list")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="close_admin")]
        ])
        await cb.message.edit_text("🛠 <b>Наказания</b>", reply_markup=kb)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "ban_list")
async def ban_list(cb: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, reason FROM bans") as cur:
                bans = await cur.fetchall()
        if not bans: return await cb.message.edit_text("Пусто.", reply_markup=back_btn("admin_bans"))
        text = "🚫 <b>ЗАБАНЕННЫЕ:</b>\n"
        for b in bans: text += f"👤 {b[0]} — {b[1]}\n"
        await cb.message.edit_text(text, reply_markup=back_btn("admin_bans"))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "ban_user")
async def ban_user(cb: CallbackQuery, state: FSMContext):
    try:
        await cb.message.edit_text("ID для бана:", reply_markup=back_btn("admin_bans"))
        await state.set_state(AdminState.waiting_ban_id)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_ban_id)
async def ban_user_id(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return
        await state.update_data(uid=int(message.text))
        await message.answer("Причина:")
        await state.set_state(AdminState.waiting_ban_reason)
    except: await message.answer("Ошибка")

@dp.message(AdminState.waiting_ban_reason)
async def ban_user_reason(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bans (user_id, reason) VALUES (?, ?)", (data['uid'], message.text))
            await db.commit()
        await message.answer(f"✅ {data['uid']} забанен.", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "unban_user")
async def unban_user(cb: CallbackQuery, state: FSMContext):
    try:
        await cb.message.edit_text("ID для разбана:", reply_markup=back_btn("admin_bans"))
        await state.set_state(AdminState.waiting_unban_id)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_unban_id)
async def unban_user_id(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return
        uid = int(message.text)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM bans WHERE user_id = ?", (uid,))
            await db.commit()
        await message.answer(f"✅ {uid} разбанен.", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_staff")
async def admin_staff(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📜 Логи", callback_data="hr_logs")],
            [InlineKeyboardButton(text="⬆️ Назначить Зама", callback_data="hr_set_staff")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="close_admin")]
        ])
        await cb.message.edit_text("👥 <b>HR-Панель</b>", reply_markup=kb)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "hr_logs")
async def hr_logs(cb: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT admin_id, action, details, timestamp FROM hr_logs ORDER BY id DESC LIMIT 15") as cur:
                logs = await cur.fetchall()
        if not logs: return await cb.message.edit_text("Пусто.", reply_markup=back_btn("admin_staff"))
        text = "📜 <b>Логи:</b>\n\n"
        for log in logs: text += f"👤 {log[0]} | {log[1]}\n📝 {log[2]}\n🕒 {log[3][:16]}\n\n"
        await cb.message.edit_text(text, reply_markup=back_btn("admin_staff"))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "hr_set_staff")
async def hr_set_staff_prompt(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        await cb.message.edit_text("ID для назначения Замом:", reply_markup=back_btn("admin_staff"))
        await state.set_state(AdminState.waiting_staff_id)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_staff_id)
async def hr_set_staff_save(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return
        uid = int(message.text)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO admins (user_id, rank) VALUES (?, 2)", (uid,))
            await db.commit()
        await message.answer(f"✅ {uid} — Зам!", reply_markup=await main_menu(message.from_user.id))
        await state.clear()
        try: await bot.send_message(uid, "👑 Вам выданы права Заместителя! /admin")
        except: pass
    except: await message.answer("Ошибка")

@dp.callback_query(F.data == "admin_edit_bal")
async def admin_edit_bal(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        await cb.message.edit_text("ID игрока:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_edit_id)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_edit_id)
async def admin_edit_bal_id(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        await state.update_data(target_id=int(message.text))
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 МОНЕТЫ", callback_data="edit_type_balance"), InlineKeyboardButton(text="💎 КОЭНЫ", callback_data="edit_type_coins")], [InlineKeyboardButton(text="◀️ ОТМЕНА", callback_data="close_admin")]])
        await message.answer("Что изменить?", reply_markup=kb)
        await state.set_state(AdminState.waiting_edit_type)
    except: await message.answer("Ошибка")

@dp.callback_query(F.data.startswith("edit_type_"))
async def admin_edit_bal_type(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        await state.update_data(edit_type=cb.data.split("_")[2])
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ НАЧИСЛИТЬ", callback_data="edit_action_add"), InlineKeyboardButton(text="➖ СПИСАТЬ", callback_data="edit_action_sub")], [InlineKeyboardButton(text="◀️ ОТМЕНА", callback_data="close_admin")]])
        await cb.message.edit_text("Действие:", reply_markup=kb)
        await state.set_state(AdminState.waiting_edit_action)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("edit_action_"))
async def admin_edit_bal_action(cb: CallbackQuery, state: FSMContext):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        await state.update_data(edit_action=cb.data.split("_")[2])
        await cb.message.edit_text("Сумма:", reply_markup=back_btn("close_admin"))
        await state.set_state(AdminState.waiting_edit_amount)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_edit_amount)
async def admin_edit_bal_amount(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit(): return await message.answer("Число!")
        amount = int(message.text)
        if amount <= 0: return await message.answer("Сумма должна быть больше 0!")
        data = await state.get_data()
        await state.clear()
        is_coin = (data.get('edit_type') == "coins")
        final = amount if data.get('edit_action') == "add" else -amount
        await upd_bal(data['target_id'], final, is_coin=is_coin)
        await add_hr_log(message.from_user.id, "EDIT_BAL", f"{data['target_id']}, {data['edit_type']}, {final}")
        await message.answer(f"✅ Готово.", reply_markup=await admin_menu(3, message.from_user.id))
    except: await message.answer("Ошибка")

# ================= НАЗВАНИЯ КНОПОК =================
@dp.callback_query(F.data == "admin_button_names")
async def admin_button_names(cb: CallbackQuery):
    try:
        if await get_admin_rank(cb.from_user.id) != 3: return
        kb = []
        for key in ["btn_cases", "btn_games", "btn_quests", "btn_achievements", "btn_bonus", "btn_wheel", "btn_shop", "btn_buy_stars", "btn_inv", "btn_prof", "btn_top", "btn_promo", "btn_ref", "btn_crash", "btn_commands", "btn_about", "btn_admin_panel"]:
            text = await get_button(key)
            kb.append([InlineKeyboardButton(text=text, callback_data=f"bn_{key}")])
        kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")])
        await cb.message.edit_text("🏷️ <b>Выберите кнопку для изменения названия:</b>\n\n(Можно вставлять любые эмодзи и прем-стикеры)", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("bn_"))
async def admin_change_button_text(cb: CallbackQuery, state: FSMContext):
    try:
        key = cb.data[3:]
        await state.update_data(button_key=key)
        current = await get_button(key)
        await cb.message.edit_text(f"Текущее название: {current}\n\nВведите новое название:", reply_markup=back_btn("admin_button_names"))
        await state.set_state(AdminState.waiting_button_text)
        await cb.answer()
    except: await cb.answer("Ошибка", show_alert=True)

@dp.message(AdminState.waiting_button_text)
async def save_button_text(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        key = data.get('button_key')
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE button_names SET text = ? WHERE key = ?", (message.text, key))
            await db.commit()
        await message.answer(f"✅ Название обновлено!", reply_markup=await admin_menu(3, message.from_user.id))
        await state.clear()
    except: await message.answer("Ошибка")

# ================= ФОНОВЫЕ ЗАДАЧИ =================
async def keep_alive():
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("SELECT 1")
                await db.commit()
        except: pass
        await asyncio.sleep(600)

async def web_server():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    asyncio.create_task(web_server())
    asyncio.create_task(keep_alive())
    print("Бот запущен! Все системы в норме.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
