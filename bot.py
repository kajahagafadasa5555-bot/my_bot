import asyncio
import logging
import datetime
import random
import string
import os
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F
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

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

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

        defaults = [
            ('maintenance', 'False'), ('panic', 'False'), ('bj_chance', '20'),
            ('shop_price', '100000'), ('price_50_stars', '50'), ('price_100_stars', '100'),
            ('price_prem3', '150'), ('price_prem6', '300'), ('price_prem12', '500'),
            ('jackpot_enabled', 'True'), ('crash_chance', '40'), ('pity_threshold', '30')
        ]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        await db.execute("INSERT OR IGNORE INTO admins (user_id, rank) VALUES (?, 3)", (ADMIN_IDS[0],))
        await db.execute("INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 0)")

        async with db.execute("SELECT COUNT(*) FROM cases") as cur:
            if (await cur.fetchone())[0] == 0:
                cases_data = [
                    ("poor", "🥺 Нищий", 15, 5, 15000),
                    ("rich", "👑 Богатый", 100, 30, 100000),
                    ("nft", "💎 NFT Кейс", 700, 250, 1000000)
                ]
                for c in cases_data:
                    await db.execute("INSERT INTO cases (key, name, price, coin_price, mon_price) VALUES (?, ?, ?, ?, ?)", c)
                items_data = [
                    ("poor", "2 звезды", "common", 2, 70, "50%"), ("poor", "5 звезд", "rare", 5, 25, "30%"), ("poor", "20 звезд", "epic", 20, 5, "15%"), ("poor", "💎 Алмаз", "legendary", 500, 3, "4%"), ("poor", "🚀 Ракета", "legendary", 1000, 1.5, "0.8%"), ("poor", "🏆 Кубок", "mythic", 5000, 0.5, "0.2%"),
                    ("rich", "10 звезд", "common", 10, 60, "50%"), ("rich", "50 звезд", "rare", 50, 30, "40%"), ("rich", "NFT Кубок", "epic", 500, 9, "9%"), ("rich", "👑 Корона", "legendary", 2500, 1, "1%"),
                    ("nft", "50 звезд", "common", 50, 60, "60%"), ("nft", "100 звезд", "rare", 100, 25, "25%"), ("nft", "Сердечко", "epic", 200, 10, "10%"), ("nft", "🚀 Ракета", "legendary", 1000, 4, "4%"), ("nft", "👑 ТОП NFT", "mythic", 5000, 1, "1%")
                ]
                for i in items_data:
                    await db.execute("INSERT INTO case_items (case_key, name, rarity, value, weight, display_chance) VALUES (?, ?, ?, ?, ?, ?)", i)
        await db.commit()

async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def get_admin_rank(user_id):
    if user_id in ADMIN_IDS: return 3
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT rank FROM admins WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def add_user(user_id, username, full_name, ref_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if not await cur.fetchone():
                await db.execute("INSERT INTO users (user_id, username, full_name, referrer_id) VALUES (?, ?, ?, ?)", (user_id, username, full_name, ref_id))
                if ref_id: await db.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
            else:
                await db.execute("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?", (username, full_name, user_id))
            await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

async def upd_bal(user_id, amount, is_coin=False, add_jackpot=True):
    async with aiosqlite.connect(DB_PATH) as db:
        if is_coin: await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        else:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            if amount < 0 and add_jackpot:
                await db.execute("UPDATE jackpot SET amount = amount + ? WHERE id = 1", (abs(amount) // 10,))
        await db.commit()

async def add_xp(user_id, xp):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (xp, user_id))
        async with db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                xp_val, lvl = row
                new_lvl = xp_val // 1000 + 1
                if new_lvl > lvl:
                    await db.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_lvl, user_id))
                    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (new_lvl * 5000, user_id))
                    try: await bot.send_message(user_id, f"🎉 <b>НОВЫЙ УРОВЕНЬ!</b>\nУровень: {new_lvl}\nБонус: {new_lvl * 5000} 💰")
                    except: pass
        await db.commit()

async def add_item(user_id, name, rarity, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO inventory (user_id, item_name, rarity, value) VALUES (?, ?, ?, ?)", (user_id, name, rarity, value))
        await db.commit()

async def check_achievement(user_id, key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM achievements WHERE user_id = ? AND achievement_key = ?", (user_id, key)) as cur:
            if await cur.fetchone(): return False
        await db.execute("INSERT INTO achievements (user_id, achievement_key, unlocked_at) VALUES (?, ?, ?)", (user_id, key, datetime.datetime.now().isoformat()))
        await db.commit()
    return True

def gen_code(l=8): return "".join(random.choices(string.ascii_uppercase + string.digits, k=l))

async def add_hr_log(admin_id, action, details=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO hr_logs (admin_id, action, details, timestamp) VALUES (?, ?, ?, ?)", (admin_id, action, details, datetime.datetime.now().isoformat()))
        await db.commit()

# ================= КЕЙСЫ =================
async def get_cases():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, name, price, coin_price, mon_price FROM cases WHERE is_active = 1") as cur:
            rows = await cur.fetchall()
    return {r[0]: {"name": r[1], "price": r[2], "coin_price": r[3], "mon_price": r[4]} for r in rows}

async def get_case_items(case_key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, rarity, value, weight, display_chance FROM case_items WHERE case_key = ?", (case_key,)) as cur:
            return await cur.fetchall()

async def get_pity(user_id, case_key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT fail_count FROM pity WHERE user_id = ? AND case_key = ?", (user_id, case_key)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def update_pity(user_id, case_key, increment=True):
    async with aiosqlite.connect(DB_PATH) as db:
        if increment:
            await db.execute("INSERT INTO pity (user_id, case_key, fail_count) VALUES (?, ?, 1) ON CONFLICT(user_id, case_key) DO UPDATE SET fail_count = fail_count + 1", (user_id, case_key))
        else:
            await db.execute("INSERT OR REPLACE INTO pity (user_id, case_key, fail_count) VALUES (?, ?, 0)", (user_id, case_key))
        await db.commit()

async def open_case(case_key, user_id):
    items = await get_case_items(case_key)
    if not items: return ("Пусто", "common", 0, 0, "0%")
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
    if chosen[2] in ("legendary", "mythic"):
        await update_pity(user_id, case_key, increment=False)
    else:
        await update_pity(user_id, case_key, increment=True)
    return chosen

# ================= АНИМАЦИЯ =================
async def play_animation(message: Message, case_name: str):
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

# ================= КЛАВИАТУРЫ =================
def main_menu(user_id):
    kb = [
        [InlineKeyboardButton(text="🎁 КЕЙСЫ", callback_data="cases"), InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games")],
        [InlineKeyboardButton(text="🎯 КВЕСТЫ", callback_data="quests"), InlineKeyboardButton(text="🏆 ДОСТИЖЕНИЯ", callback_data="achievements")],
        [InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily_bonus"), InlineKeyboardButton(text="🎰 КОЛЕСО", callback_data="wheel")],
        [InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="⭐ STARS/ПРЕМКА", callback_data="buy_stars")],
        [InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inv"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="prof")],
        [InlineKeyboardButton(text="🏆 ТОП", callback_data="top_players"), InlineKeyboardButton(text="🔑 ПРОМОКОД", callback_data="promo")],
        [InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="ref"), InlineKeyboardButton(text="🎰 CRASH", callback_data="crash_game")],
        [InlineKeyboardButton(text="📜 КОМАНДЫ", callback_data="commands"), InlineKeyboardButton(text="ℹ️ О БОТЕ", callback_data="about")]
    ]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="👑 АДМИН ПАНЕЛЬ", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_btn(cb="back_main"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ НАЗАД", callback_data=cb)]])

def admin_menu(rank, user_id):
    kb = [
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_stats"), InlineKeyboardButton(text="📜 МОИ ПРАВА", callback_data="my_rights")]
    ]
    if rank >= 2:
        kb.append([InlineKeyboardButton(text="🎁 КУПОН", callback_data="admin_coupon"), InlineKeyboardButton(text="🔑 ПРОМО", callback_data="admin_promo")])
        kb.append([InlineKeyboardButton(text="🚫 БАНЫ", callback_data="admin_bans")])
    if rank == 3:
        kb.append([InlineKeyboardButton(text="💰 ВЫДАТЬ ВАЛЮТУ", callback_data="admin_give_menu"), InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ БАЛАНС", callback_data="admin_edit_bal")])
        kb.append([InlineKeyboardButton(text="🚨 ПАНИКА", callback_data="admin_panic"), InlineKeyboardButton(text="🛠 ТЕХ.РАБОТЫ", callback_data="admin_maint")])
        kb.append([InlineKeyboardButton(text="👥 HR-ПАНЕЛЬ", callback_data="admin_staff")])
        kb.append([InlineKeyboardButton(text="⚙️ ШАНСЫ БД", callback_data="admin_odds"), InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="admin_shop")])
        kb.append([InlineKeyboardButton(text="🎁 КЕЙСЫ", callback_data="admin_cases")])
        kb.append([InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast")])
        kb.append([InlineKeyboardButton(text="💾 БД", callback_data="admin_backup"), InlineKeyboardButton(text="📈 ЛОГИ", callback_data="hr_logs")])
        kb.append([InlineKeyboardButton(text="🎰 PITY-ПОРОГ", callback_data="admin_pity")])
        if user_id in ADMIN_IDS:
            kb.append([InlineKeyboardButton(text="⭐ ЦЕНЫ STARS", callback_data="admin_stars_prices")])
            kb.append([InlineKeyboardButton(text="📈 НАСТРОЙКА CRASH", callback_data="admin_crash")])
    kb.append([InlineKeyboardButton(text="ЗАКРЫТЬ", callback_data="close_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

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
    waiting_stars_price = State()
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
    waiting_edit_item_id = State()
    waiting_edit_item_name = State()
    waiting_edit_item_rarity = State()
    waiting_edit_item_value = State()
    waiting_edit_item_weight = State()
    waiting_edit_item_chance = State()
    waiting_delete_confirm = State()

# ================= ПОЛЬЗОВАТЕЛЬСКИЕ ХЭНДЛЕРЫ =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if await get_setting("maintenance") == "True" and await get_admin_rank(message.from_user.id) == 0:
        return await message.answer("🛠 <b>НА БОТЕ ТЕХНИЧЕСКИЕ РАБОТЫ.</b>")
    u = message.from_user
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if ref_id == u.id: ref_id = None
    await add_user(u.id, u.username or "", u.full_name, ref_id)
    user = await get_user(u.id)
    if await check_achievement(u.id, "start"):
        await message.answer("🏅 <b>ДОСТИЖЕНИЕ:</b> Первый шаг!")
    text = (
        f"👋 <b>ДОБРО ПОЖАЛОВАТЬ, {u.full_name.upper()}!</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Монеты:</b> {user[3]}\n💎 <b>Коэны:</b> {user[4]}\n"
        f"⭐ <b>Уровень:</b> {user[10]} (XP: {user[9]})\n"
        f"🔥 <b>Серия бонусов:</b> {user[13]} дн.\n━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(text, reply_markup=main_menu(u.id))

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    if user is None:
        await add_user(cb.from_user.id, cb.from_user.username or "", cb.from_user.full_name)
        user = await get_user(cb.from_user.id)
    text = (
        f"🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Монеты:</b> {user[3]}\n💎 <b>Коэны:</b> {user[4]}\n"
        f"⭐ <b>Уровень:</b> {user[10]} (XP: {user[9]})\n"
        f"🔥 <b>Серия бонусов:</b> {user[13]} дн.\n━━━━━━━━━━━━━━━━━━"
    )
    await cb.message.edit_text(text, reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

@dp.callback_query(F.data == "about")
async def about_bot(cb: CallbackQuery):
    text = f"ℹ️ <b>О БОТЕ</b>\n━━━━━━━━━━━━━━━━━━\nЛучший бот для открытия кейсов!\n\n📩 <b>Поддержка:</b> {CONTACT_ADMIN}"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "commands")
async def commands_menu(cb: CallbackQuery):
    text = (
        f"📜 <b>ВСЕ КОМАНДЫ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"🎁 Кейсы, 🎮 Игры, 🎯 Квесты, 🏆 Достижения\n"
        f"🎁 Бонус (streak!), 🎰 Колесо, 🛒 Магазин, ⭐ Stars\n"
        f"🎒 Инвентарь, 👤 Профиль, 🏆 Топ, 🔑 Промокод\n"
        f"👥 Рефералы, 🎰 Crash\n\n👑 <b>АДМИН:</b> /admin"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "prof")
async def prof(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    if user is None:
        await add_user(cb.from_user.id, cb.from_user.username or "", cb.from_user.full_name)
        user = await get_user(cb.from_user.id)
    achievements_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM achievements WHERE user_id = ?", (cb.from_user.id,)) as cur:
            achievements_count = (await cur.fetchone())[0]
    text = (
        f"👤 <b>ПРОФИЛЬ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{user[0]}</code>\n"
        f"💰 <b>Монеты:</b> {user[3]}\n💎 <b>Коэны:</b> {user[4]}\n"
        f"⭐ <b>Уровень:</b> {user[10]} (XP: {user[9]})\n"
        f"🔥 <b>Серия бонусов:</b> {user[13]} дн.\n"
        f"🏆 <b>Побед:</b> {user[12]}\n👥 <b>Рефералы:</b> {user[6]}/3\n"
        f"🏅 <b>Достижения:</b> {achievements_count}\n━━━━━━━━━━━━━━━━━━"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "achievements")
async def achievements_menu(cb: CallbackQuery):
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

@dp.callback_query(F.data == "ref")
async def ref(cb: CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
    user = await get_user(cb.from_user.id)
    text = f"👥 <b>РЕФЕРАЛЫ</b>\n━━━━━━━━━━━━━━━━━━\nПригласи 3 друзей и получи доступ к выводу!\nВаши рефералы: {user[6]}/3\n\n🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "top_players")
async def top_players(cb: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name, balance FROM users ORDER BY balance DESC LIMIT 5") as cur:
            tops = await cur.fetchall()
    text = "🏆 <b>ТОП 5 ИГРОКОВ</b>\n━━━━━━━━━━━━━━━━━━\n"
    for i, (name, bal) in enumerate(tops, 1): text += f"{i}. <b>{name}</b> — {bal} 💰\n"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

# ================= STREAK-БОНУС =================
@dp.callback_query(F.data == "daily_bonus")
async def daily_bonus(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    if user is None:
        await add_user(cb.from_user.id, cb.from_user.username or "", cb.from_user.full_name)
        user = await get_user(cb.from_user.id)
    today = datetime.date.today()
    today_str = str(today)
    yesterday_str = str(today - datetime.timedelta(days=1))
    last = user[7] if user[7] else ""
    if last == today_str:
        return await cb.answer("❌ ВЫ УЖЕ ЗАБРАЛИ БОНУС СЕГОДНЯ!", show_alert=True)
    streak = user[13] if user[13] else 0
    if last == yesterday_str:
        streak += 1
    else:
        streak = 1
    if streak > 7:
        streak = 1
    rewards = {1: 5000, 2: 7000, 3: 10000, 4: 12000, 5: 15000, 6: 18000, 7: 25000}
    reward = rewards.get(streak, 5000)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ?, last_bonus = ?, bonus_streak = ? WHERE user_id = ?", (reward, today_str, streak, cb.from_user.id))
        await db.commit()
    await cb.answer(f"✅ БОНУС: {reward} 💰\n🔥 Серия: {streak}/7 дней!", show_alert=True)
    await back_main(cb)

@dp.callback_query(F.data == "wheel")
async def wheel_spin(cb: CallbackQuery):
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

# ================= КВЕСТЫ =================
@dp.callback_query(F.data == "quests")
async def quests_menu(cb: CallbackQuery):
    quests = {
        "open_1": {"name": "Открой 1 кейс", "target": 1, "reward": 2000, "type": "case"},
        "upgrade_1": {"name": "Сделай 1 ставку", "target": 1, "reward": 3000, "type": "bet"},
        "ref_1": {"name": "Пригласи 1 друга", "target": 1, "reward": 5000, "type": "ref"}
    }
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

async def update_quest_progress(user_id, quest_type):
    quests = {"case": "open_1", "bet": "upgrade_1", "ref": "ref_1"}
    q_key = quests.get(quest_type)
    if not q_key: return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO quests (user_id, quest_key, progress) VALUES (?, ?, 1) ON CONFLICT(user_id, quest_key) DO UPDATE SET progress = progress + 1", (user_id, q_key))
        await db.commit()

@dp.callback_query(F.data.startswith("claim_"))
async def claim_quest(cb: CallbackQuery):
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

# ================= CRASH =================
@dp.callback_query(F.data == "crash_game")
async def crash_game(cb: CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT amount FROM jackpot WHERE id = 1") as cur:
            jp = (await cur.fetchone())[0]
    text = f"🎰 <b>CRASH</b>\n━━━━━━━━━━━━━━━━━━\n💸 Множитель растет, но может упасть!\n🏆 Джекпот: {jp} 💰\n\nВведите сумму ставки:"
    await cb.message.edit_text(text, reply_markup=back_btn("games"))
    await state.set_state(UserState.waiting_crash_bet)
    await cb.answer()

@dp.message(UserState.waiting_crash_bet)
async def crash_bet(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
    bet = int(message.text)
    user = await get_user(message.from_user.id)
    if user[3] < bet: return await message.answer("❌ НЕДОСТАТОЧНО МОНЕТ!")
    await state.update_data(bet=bet)
    await upd_bal(message.from_user.id, -bet)
    await state.clear()
    crash_chance = int(await get_setting("crash_chance")) / 100.0
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

@dp.callback_query(F.data == "crash_take")
async def crash_take(cb: CallbackQuery, state: FSMContext):
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

# ================= МАГАЗИН И КЕЙСЫ =================
@dp.callback_query(F.data == "shop")
async def shop_menu(cb: CallbackQuery):
    price = await get_setting("shop_price")
    text = f"🛒 <b>МАГАЗИН</b>\n━━━━━━━━━━━━━━━━━━\n💱 <b>Курс:</b> {price} Монет = 10 Коэнов\n\nВведите количество Коэнов (кратно 10):"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "cases")
async def cases_menu(cb: CallbackQuery):
    cases = await get_cases()
    kb = []
    for k, c in cases.items(): kb.append([InlineKeyboardButton(text=f"{c['name']}", callback_data=f"view_{k}")])
    kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
    await cb.message.edit_text("🎁 <b>ВЫБЕРИ КЕЙС</b>\n━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await cb.answer()

@dp.callback_query(F.data.startswith("view_"))
async def view_case(cb: CallbackQuery):
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

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_stars"))
async def open_stars(cb: CallbackQuery):
    key = cb.data.split("_")[1]
    cases = await get_cases()
    if key not in cases: return await cb.answer("Ошибка", show_alert=True)
    case = cases[key]
    prices = [LabeledPrice(label=case["name"], amount=case["price"])]
    await bot.send_invoice(chat_id=cb.from_user.id, title=case["name"], description="Открыть кейс?", payload=f"case_{key}", provider_token="", currency="XTR", prices=prices)
    await cb.answer()

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_coins"))
async def open_coins(cb: CallbackQuery):
    if await get_setting("panic") == "True": return await cb.answer("🚨 БОТ НА ПАНИКЕ!", show_alert=True)
    key = cb.data.split("_")[1]
    cases = await get_cases()
    if key not in cases: return await cb.answer("Ошибка", show_alert=True)
    case = cases[key]
    user = await get_user(cb.from_user.id)
    if user is None:
        await add_user(cb.from_user.id, cb.from_user.username or "", cb.from_user.full_name)
        user = await get_user(cb.from_user.id)
    if user[4] < case["coin_price"]: return await cb.answer("❌ НЕДОСТАТОЧНО КОЭНОВ!", show_alert=True)
    await upd_bal(cb.from_user.id, -case["coin_price"], is_coin=True)
    msg = await play_animation(cb.message, case['name'])
    name, rarity, val, w, fake = await open_case(key, cb.from_user.id)
    await add_item(cb.from_user.id, name, rarity, val)
    await add_xp(cb.from_user.id, 10)
    await update_quest_progress(cb.from_user.id, "case")
    if await check_achievement(cb.from_user.id, "first_case"):
        try: await cb.message.answer("🏅 <b>ДОСТИЖЕНИЕ:</b> Первый кейс!")
        except: pass
    await msg.edit_text(f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐", reply_markup=back_btn("cases"))
    await cb.answer("Поздравляем!")

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_mon"))
async def open_mon(cb: CallbackQuery):
    if await get_setting("panic") == "True": return await cb.answer("🚨 БОТ НА ПАНИКЕ!", show_alert=True)
    key = cb.data.split("_")[1]
    cases = await get_cases()
    if key not in cases: return await cb.answer("Ошибка", show_alert=True)
    case = cases[key]
    user = await get_user(cb.from_user.id)
    if user is None:
        await add_user(cb.from_user.id, cb.from_user.username or "", cb.from_user.full_name)
        user = await get_user(cb.from_user.id)
    if user[3] < case["mon_price"]: return await cb.answer("❌ НЕДОСТАТОЧНО МОНЕТ!", show_alert=True)
    await upd_bal(cb.from_user.id, -case["mon_price"], is_coin=False)
    msg = await play_animation(cb.message, case['name'])
    name, rarity, val, w, fake = await open_case(key, cb.from_user.id)
    await add_item(cb.from_user.id, name, rarity, val)
    await add_xp(cb.from_user.id, 10)
    await update_quest_progress(cb.from_user.id, "case")
    await msg.edit_text(f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐", reply_markup=back_btn("cases"))
    await cb.answer("Поздравляем!")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_pay(message: Message):
    key = message.successful_payment.invoice_payload.split("_")[1]
    name, rarity, val, w, fake = await open_case(key, message.from_user.id)
    await add_item(message.from_user.id, name, rarity, val)
    await add_xp(message.from_user.id, 10)
    await message.answer(f"🎉 Вы выиграли: <b>{name}</b>", reply_markup=main_menu(message.from_user.id))

@dp.callback_query(F.data == "inv")
async def inv(cb: CallbackQuery):
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

@dp.callback_query(F.data.startswith("sell_"))
async def sell(cb: CallbackQuery):
    item_id = int(cb.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM inventory WHERE id = ?", (item_id,)) as cur:
            val = (await cur.fetchone())[0]
        await db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (val, cb.from_user.id))
        await db.commit()
    await cb.answer(f"✅ ПРОДАНО ЗА {val} МОНЕТ!", show_alert=True)
    await inv(cb)

@dp.callback_query(F.data.startswith("withdraw_"))
async def withdraw(cb: CallbackQuery):
    item_id = int(cb.data.split("_")[1])
    user = await get_user(cb.from_user.id)
    if user[6] < 3: return await cb.answer(f"❌ НУЖНО 3 РЕФЕРАЛА! У тебя: {user[6]}/3", show_alert=True)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT item_name FROM inventory WHERE id = ?", (item_id,)) as cur:
            item_name = (await cur.fetchone())[0]
        code = gen_code(8)
        await db.execute("INSERT INTO coupons (code, user_id, item_name) VALUES (?, ?, ?)", (code, cb.from_user.id, item_name))
        await db.execute("UPDATE inventory SET is_withdrawn = 1 WHERE id = ?", (item_id,))
        await db.commit()
    await cb.message.edit_text(f"🎉 <b>КУПОН СОЗДАН!</b>\n\nКод: <code>{code}</code>\nОтправь его админу: {CONTACT_ADMIN}", reply_markup=back_btn("inv"))
    await cb.answer()

# ================= ИГРЫ =================
@dp.callback_query(F.data == "games")
async def games(cb: CallbackQuery):
    bj_chance = await get_setting("bj_chance")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎮 АПГРЕЙД X2 (50%)", callback_data="game_up")],
        [InlineKeyboardButton(text=f"🪙 МОНЕТКА (50%)", callback_data="game_coin")],
        [InlineKeyboardButton(text=f"🃏 БЛЭКДЖЕК ({bj_chance}%)", callback_data="game_bj")],
        [InlineKeyboardButton(text=f"📈 CRASH", callback_data="crash_game")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")]
    ])
    await cb.message.edit_text("🎮 <b>ИГРЫ</b>", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("game_"))
async def game_bet(cb: CallbackQuery, state: FSMContext):
    await state.update_data(game=cb.data)
    await cb.message.edit_text("💰 <b>ВВЕДИ СУММУ СТАВКИ:</b>", reply_markup=back_btn("games"))
    await state.set_state(UserState.waiting_bet)
    await cb.answer()

@dp.message(UserState.waiting_bet)
async def play_game(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
    bet = int(message.text)
    user = await get_user(message.from_user.id)
    if user[3] < bet: return await message.answer("❌ НЕДОСТАТОЧНО МОНЕТ!")
    data = await state.get_data()
    game = data.get("game")
    await state.clear()
    await upd_bal(message.from_user.id, -bet)
    await update_quest_progress(message.from_user.id, "bet")
    await add_xp(message.from_user.id, 5)
    if game == "game_up": win = random.random() < 0.5
    elif game == "game_coin": win = random.choice([True, False])
    elif game == "game_bj": win = random.random() < (int(await get_setting("bj_chance")) / 100.0)
    else: win = False
    if win:
        await upd_bal(message.from_user.id, bet * 2)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET wins_count = wins_count + 1 WHERE user_id = ?", (message.from_user.id,))
            await db.commit()
        await message.answer(f"🎉 <b>ПОБЕДА!</b>\nТы выиграл <b>{bet * 2}</b> монет.", reply_markup=main_menu(message.from_user.id))
    else:
        await message.answer(f"😢 <b>ПРОИГРЫШ.</b>\nТы потерял <b>{bet}</b> монет.", reply_markup=main_menu(message.from_user.id))

@dp.callback_query(F.data == "promo")
async def promo_enter(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔑 <b>ВВЕДИ ПРОМОКОД:</b>", reply_markup=back_btn())
    await state.set_state(UserState.waiting_promo)
    await cb.answer()

@dp.message(UserState.waiting_promo)
async def promo_check(message: Message, state: FSMContext):
    code = message.text.upper().strip()
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM promo_activations WHERE user_id = ? AND code = ?", (message.from_user.id, code)) as cur:
            if await cur.fetchone():
                return await message.answer("❌ ВЫ УЖЕ АКТИВИРОВАЛИ ЭТОТ ПРОМОКОД!", reply_markup=main_menu(message.from_user.id))
        async with db.execute("SELECT reward, uses_left FROM promo_codes WHERE code = ?", (code,)) as cur:
            promo = await cur.fetchone()
        if not promo or promo[1] <= 0: return await message.answer("❌ НЕВЕРНЫЙ ПРОМОКОД.", reply_markup=main_menu(message.from_user.id))
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[0], message.from_user.id))
        await db.execute("INSERT INTO promo_activations (user_id, code) VALUES (?, ?)", (message.from_user.id, code))
        await db.commit()
    await message.answer(f"✅ <b>АКТИВИРОВАН!</b>\nПолучено <b>{promo[0]}</b> монет.", reply_markup=main_menu(message.from_user.id))

# ================= АДМИНКА =================
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    rank = await get_admin_rank(message.from_user.id)
    if rank == 0: return
    await message.answer("👑 <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=admin_menu(rank, message.from_user.id))

@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()

@dp.callback_query(F.data == "my_rights")
async def my_rights(cb: CallbackQuery):
    rank = await get_admin_rank(cb.from_user.id)
    if rank == 3: text = "👑 <b>ДИРЕКТОР</b>\nВсе права."
    elif rank == 2: text = "⭐ <b>ЗАМ</b>\nКупоны, промо, наказания."
    else: text = "🛡 <b>МЛ. АДМИН</b>\nПросмотр."
    await cb.message.edit_text(text, reply_markup=back_btn("close_admin"))
    await cb.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
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

@dp.callback_query(F.data == "admin_panic")
async def admin_panic(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cur = await get_setting("panic") == "True"
    await set_setting("panic", str(not cur))
    await add_hr_log(cb.from_user.id, "TOGGLE_PANIC", f"Panic: {not cur}")
    await cb.answer(f"🚨 ПАНИКА: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)

@dp.callback_query(F.data == "admin_maint")
async def admin_maint(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cur = await get_setting("maintenance") == "True"
    await set_setting("maintenance", str(not cur))
    await add_hr_log(cb.from_user.id, "TOGGLE_MAINT", f"Maint: {not cur}")
    await cb.answer(f"🛠 ТЕХ.РАБОТЫ: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("📢 <b>РАССЫЛКА</b>\nОтправьте текст:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_broadcast_msg)
    await cb.answer()

@dp.message(AdminState.waiting_broadcast_msg)
async def do_broadcast(message: Message, state: FSMContext):
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
        except:
            fail += 1
    await message.answer(f"✅ <b>ЗАВЕРШЕНО!</b>\nУспешно: {success}\nОшибок: {fail}", reply_markup=admin_menu(3, message.from_user.id))

@dp.callback_query(F.data == "admin_backup")
async def admin_backup(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    try:
        doc = FSInputFile(DB_PATH)
        await bot.send_document(cb.from_user.id, doc, caption="💾 Резервная копия БД")
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
    await cb.answer()

@dp.callback_query(F.data == "admin_pity")
async def admin_pity(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    th = await get_setting("pity_threshold")
    await cb.message.edit_text(f"Текущий pity-порог: <b>{th}</b> неудач.\n\nВведите новый порог (число):", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_pity_threshold)
    await cb.answer()

@dp.message(AdminState.waiting_pity_threshold)
async def set_pity_threshold(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await set_setting("pity_threshold", message.text)
    await message.answer(f"✅ Pity-порог: {message.text}", reply_markup=admin_menu(3, message.from_user.id))
    await state.clear()

# --- КЕЙСЫ: РЕДАКТИРОВАНИЕ ---
@dp.callback_query(F.data == "admin_cases")
async def admin_cases(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cases = await get_cases()
    kb = []
    for k, c in cases.items():
        kb.append([InlineKeyboardButton(text=f"{c['name']} ({k})", callback_data=f"editcase_{k}")])
    kb.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ КЕЙС", callback_data="add_case")])
    kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")])
    await cb.message.edit_text("🎁 <b>УПРАВЛЕНИЕ КЕЙСАМИ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await cb.answer()

@dp.callback_query(F.data.startswith("editcase_"))
async def edit_case_menu(cb: CallbackQuery):
    key = cb.data.split("_")[1]
    cases = await get_cases()
    if key not in cases: return await cb.answer("Кейс не найден!", show_alert=True)
    c = cases[key]
    items = await get_case_items(key)
    text = f"🎁 <b>{c['name']}</b> (key: {key})\n💰 Монеты: {c['mon_price']}\n💎 Коэны: {c['coin_price']}\n⭐ Stars: {c['price']}\n\n<b>Предметы:</b>\n"
    kb = []
    for item in items:
        text += f"▪️ [id:{item[0]}] {item[1]} ({item[2]}) — {item[5]}\n"
        kb.append([
            InlineKeyboardButton(text=f"✏️ {item[1]}", callback_data=f"edititem_{item[0]}"),
            InlineKeyboardButton(text=f"🗑", callback_data=f"delitem_{item[0]}")
        ])
    text += f"\nВсего: {len(items)}"
    kb.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ ПРЕДМЕТ", callback_data=f"additem_{key}")])
    kb.append([InlineKeyboardButton(text="🗑 УДАЛИТЬ КЕЙС", callback_data=f"delcase_{key}")])
    kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_cases")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await cb.answer()

@dp.callback_query(F.data.startswith("delitem_"))
async def delete_item(cb: CallbackQuery, state: FSMContext):
    item_id = int(cb.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT case_key, name FROM case_items WHERE id = ?", (item_id,)) as cur:
            row = await cur.fetchone()
        if not row: return await cb.answer("Предмет не найден!", show_alert=True)
        await db.execute("DELETE FROM case_items WHERE id = ?", (item_id,))
        await db.commit()
    await cb.answer(f"✅ Предмет '{row[1]}' удалён!", show_alert=True)
    await edit_case_menu(cb.__class__(**{**cb.__dict__, 'data': f'editcase_{row[0]}'}))

@dp.callback_query(F.data.startswith("delcase_"))
async def delete_case_confirm(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split("_")[1]
    await state.update_data(del_case_key=key)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ", callback_data=f"delcase_confirm_{key}")],
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="admin_cases")]
    ])
    await cb.message.edit_text(f"⚠️ Удалить кейс <b>{key}</b> со всеми предметами?", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("delcase_confirm_"))
async def delete_case_execute(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split("_")[2]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM case_items WHERE case_key = ?", (key,))
        await db.execute("DELETE FROM cases WHERE key = ?", (key,))
        await db.execute("DELETE FROM pity WHERE case_key = ?", (key,))
        await db.commit()
    await cb.answer(f"✅ Кейс {key} удалён!", show_alert=True)
    await admin_cases(cb)

@dp.callback_query(F.data.startswith("edititem_"))
async def edit_item_start(cb: CallbackQuery, state: FSMContext):
    item_id = int(cb.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT case_key, name, rarity, value, weight, display_chance FROM case_items WHERE id = ?", (item_id,)) as cur:
            item = await cur.fetchone()
    if not item: return await cb.answer("Предмет не найден!", show_alert=True)
    await state.update_data(edit_item_id=item_id, edit_case_key=item[0])
    await cb.message.edit_text(
        f"✏️ <b>Редактирование предмета</b>\n\n"
        f"Сейчас: <b>{item[1]}</b>\nРедкость: {item[2]}\nЦена: {item[3]}⭐\nВес: {item[4]}\nШанс: {item[5]}\n\n"
        f"Введите новое название (или /skip, чтобы оставить):",
        reply_markup=back_btn("admin_cases")
    )
    await state.set_state(AdminState.waiting_edit_item_name)
    await cb.answer()

@dp.message(AdminState.waiting_edit_item_name)
async def edit_item_name(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.text != "/skip":
        await state.update_data(edit_item_name=message.text)
    await message.answer("Введите новую редкость (common/rare/epic/legendary/mythic) или /skip:")
    await state.set_state(AdminState.waiting_edit_item_rarity)

@dp.message(AdminState.waiting_edit_item_rarity)
async def edit_item_rarity(message: Message, state: FSMContext):
    if message.text != "/skip":
        if message.text.lower() not in ["common", "rare", "epic", "legendary", "mythic"]:
            return await message.answer("❌ Неверная редкость!")
        await state.update_data(edit_item_rarity=message.text.lower())
    await message.answer("Введите новую цену (число) или /skip:")
    await state.set_state(AdminState.waiting_edit_item_value)

@dp.message(AdminState.waiting_edit_item_value)
async def edit_item_value(message: Message, state: FSMContext):
    if message.text != "/skip":
        if not message.text.isdigit(): return await message.answer("Введите число!")
        await state.update_data(edit_item_value=int(message.text))
    await message.answer("Введите новый вес (число) или /skip:")
    await state.set_state(AdminState.waiting_edit_item_weight)

@dp.message(AdminState.waiting_edit_item_weight)
async def edit_item_weight(message: Message, state: FSMContext):
    if message.text != "/skip":
        try: await state.update_data(edit_item_weight=float(message.text))
        except: return await message.answer("Введите число!")
    await message.answer("Введите новый отображаемый шанс (например '5%') или /skip:")
    await state.set_state(AdminState.waiting_edit_item_chance)

@dp.message(AdminState.waiting_edit_item_chance)
async def edit_item_chance(message: Message, state: FSMContext):
    data = await state.get_data()
    item_id = data['edit_item_id']
    case_key = data['edit_case_key']
    updates = []
    params = []
    if 'edit_item_name' in data: updates.append("name = ?"); params.append(data['edit_item_name'])
    if 'edit_item_rarity' in data: updates.append("rarity = ?"); params.append(data['edit_item_rarity'])
    if 'edit_item_value' in data: updates.append("value = ?"); params.append(data['edit_item_value'])
    if 'edit_item_weight' in data: updates.append("weight = ?"); params.append(data['edit_item_weight'])
    if 'edit_item_chance' in data: updates.append("display_chance = ?"); params.append(data['edit_item_chance'])
    if message.text != "/skip": updates.append("display_chance = ?"); params.append(message.text)
    if updates:
        params.append(item_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"UPDATE case_items SET {', '.join(updates)} WHERE id = ?", params)
            await db.commit()
    await message.answer("✅ Предмет обновлён!", reply_markup=admin_menu(3, message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "add_case")
async def add_case_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Введите ключ нового кейса (латиницей, без пробелов):", reply_markup=back_btn("admin_cases"))
    await state.set_state(AdminState.waiting_case_key)
    await cb.answer()

@dp.message(AdminState.waiting_case_key)
async def add_case_key(message: Message, state: FSMContext):
    key = message.text.strip().lower()
    await state.update_data(key=key)
    await message.answer("Введите название кейса:")
    await state.set_state(AdminState.waiting_case_name)

@dp.message(AdminState.waiting_case_name)
async def add_case_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите цену в Stars:")
    await state.set_state(AdminState.waiting_case_price)

@dp.message(AdminState.waiting_case_price)
async def add_case_price(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO cases (key, name, price, coin_price, mon_price) VALUES (?, ?, ?, 0, 0)", (data['key'], data['name'], int(message.text)))
        await db.commit()
    await message.answer(f"✅ Кейс {data['key']} создан!", reply_markup=admin_menu(3, message.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("additem_"))
async def add_item_start(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split("_")[1]
    await state.update_data(case_key=key)
    await cb.message.edit_text("Введите название предмета:", reply_markup=back_btn("admin_cases"))
    await state.set_state(AdminState.waiting_item_name)
    await cb.answer()

@dp.message(AdminState.waiting_item_name)
async def add_item_name(message: Message, state: FSMContext):
    await state.update_data(item_name=message.text)
    await message.answer("Редкость (common/rare/epic/legendary/mythic):")
    await state.set_state(AdminState.waiting_item_rarity)

@dp.message(AdminState.waiting_item_rarity)
async def add_item_rarity(message: Message, state: FSMContext):
    rarity = message.text.lower()
    if rarity not in ["common", "rare", "epic", "legendary", "mythic"]:
        return await message.answer("❌ Неверная редкость!")
    await state.update_data(rarity=rarity)
    await message.answer("Стоимость (в звездах):")
    await state.set_state(AdminState.waiting_item_value)

@dp.message(AdminState.waiting_item_value)
async def add_item_value(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await state.update_data(value=int(message.text))
    await message.answer("Вес (шанс):")
    await state.set_state(AdminState.waiting_item_weight)

@dp.message(AdminState.waiting_item_weight)
async def add_item_weight(message: Message, state: FSMContext):
    try: weight = float(message.text)
    except: return await message.answer("Введите число!")
    await state.update_data(weight=weight)
    await message.answer("Отображаемый шанс (например '50%'):")
    await state.set_state(AdminState.waiting_item_chance)

@dp.message(AdminState.waiting_item_chance)
async def add_item_chance(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO case_items (case_key, name, rarity, value, weight, display_chance) VALUES (?, ?, ?, ?, ?, ?)",
                         (data['case_key'], data['item_name'], data['rarity'], data['value'], data['weight'], message.text))
        await db.commit()
    await message.answer("✅ Предмет добавлен!", reply_markup=admin_menu(3, message.from_user.id))
    await state.clear()

# --- ОСТАЛЬНЫЕ АДМИН-ФУНКЦИИ ---
@dp.callback_query(F.data == "admin_coupon")
async def admin_coupon(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) < 2: return
    await cb.message.edit_text("Код купона:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_coupon)
    await cb.answer()

@dp.message(AdminState.waiting_coupon)
async def admin_check_coupon(message: Message, state: FSMContext):
    if await get_admin_rank(message.from_user.id) < 2: return
    code = message.text.strip().upper()
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT c.user_id, c.item_name, u.full_name, c.status FROM coupons c JOIN users u ON c.user_id = u.user_id WHERE c.code = ?", (code,)) as cur:
            info = await cur.fetchone()
    if not info: return await message.answer("❌ Купон не найден.", reply_markup=main_menu(message.from_user.id))
    uid, item, name, status = info
    if status == 'given': return await message.answer("⚠️ УЖЕ ВЫДАН!", reply_markup=main_menu(message.from_user.id))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я выдал", callback_data=f"givecoupon_{code}")]])
    await message.answer(f"🔍 {name} ({uid})\n🎁 {item}", reply_markup=kb)

@dp.callback_query(F.data.startswith("givecoupon_"))
async def admin_give_coupon(cb: CallbackQuery):
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

@dp.callback_query(F.data == "admin_promo")
async def admin_promo(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) < 2: return
    await cb.message.edit_text("Сумма награды:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_promo_val)
    await cb.answer()

@dp.message(AdminState.waiting_promo_val)
async def admin_promo_val(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(val=int(message.text))
    await message.answer("Количество активаций:")
    await state.set_state(AdminState.waiting_promo_uses)

@dp.message(AdminState.waiting_promo_uses)
async def admin_promo_uses(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    code = gen_code(8)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO promo_codes (code, reward, uses_left) VALUES (?, ?, ?)", (code, data['val'], int(message.text)))
        await db.commit()
    await message.answer(f"✅ Промокод: <code>{code}</code>\n{data['val']}💰, активаций: {message.text}", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_shop")
async def admin_shop(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    price = await get_setting("shop_price")
    await cb.message.edit_text(f"Цена: {price} за 10 Коэнов.\nНовая цена:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_shop_price)
    await cb.answer()

@dp.message(AdminState.waiting_shop_price)
async def admin_set_shop(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await set_setting("shop_price", message.text)
    await message.answer(f"✅ {message.text} Монет за 10 Коэнов", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_odds")
async def admin_odds(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    bj = await get_setting("bj_chance")
    await cb.message.edit_text(f"Шанс БД: {bj}%\nНовый шанс:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_bj_chance)
    await cb.answer()

@dp.message(AdminState.waiting_bj_chance)
async def set_bj_chance(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await set_setting("bj_chance", message.text)
    await message.answer(f"✅ Шанс БД: {message.text}%", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_crash")
async def admin_crash(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cc = await get_setting("crash_chance")
    await cb.message.edit_text(f"Шанс краша: {cc}%\nНовый шанс:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_crash_chance)
    await cb.answer()

@dp.message(AdminState.waiting_crash_chance)
async def set_crash_chance(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await set_setting("crash_chance", message.text)
    await message.answer(f"✅ Шанс краша: {message.text}%", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_bans")
async def admin_bans(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) < 2: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="ban_user"), InlineKeyboardButton(text="✅ Разбанить", callback_data="unban_user")],
        [InlineKeyboardButton(text="📜 Список", callback_data="ban_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="close_admin")]
    ])
    await cb.message.edit_text("🛠 <b>Наказания</b>", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "ban_list")
async def ban_list(cb: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, reason FROM bans") as cur:
            bans = await cur.fetchall()
    if not bans: return await cb.message.edit_text("Пусто.", reply_markup=back_btn("admin_bans"))
    text = "🚫 <b>ЗАБАНЕННЫЕ:</b>\n"
    for b in bans: text += f"👤 {b[0]} — {b[1]}\n"
    await cb.message.edit_text(text, reply_markup=back_btn("admin_bans"))
    await cb.answer()

@dp.callback_query(F.data == "ban_user")
async def ban_user(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("ID для бана:", reply_markup=back_btn("admin_bans"))
    await state.set_state(AdminState.waiting_ban_id)
    await cb.answer()

@dp.message(AdminState.waiting_ban_id)
async def ban_user_id(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(uid=int(message.text))
    await message.answer("Причина:")
    await state.set_state(AdminState.waiting_ban_reason)

@dp.message(AdminState.waiting_ban_reason)
async def ban_user_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO bans (user_id, reason) VALUES (?, ?)", (data['uid'], message.text))
        await db.commit()
    await message.answer(f"✅ {data['uid']} забанен.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "unban_user")
async def unban_user(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("ID для разбана:", reply_markup=back_btn("admin_bans"))
    await state.set_state(AdminState.waiting_unban_id)
    await cb.answer()

@dp.message(AdminState.waiting_unban_id)
async def unban_user_id(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    uid = int(message.text)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bans WHERE user_id = ?", (uid,))
        await db.commit()
    await message.answer(f"✅ {uid} разбанен.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_staff")
async def admin_staff(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Логи", callback_data="hr_logs")],
        [InlineKeyboardButton(text="⬆️ Назначить Зама", callback_data="hr_set_staff")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="close_admin")]
    ])
    await cb.message.edit_text("👥 <b>HR-Панель</b>", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "hr_logs")
async def hr_logs(cb: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT admin_id, action, details, timestamp FROM hr_logs ORDER BY id DESC LIMIT 15") as cur:
            logs = await cur.fetchall()
    if not logs: return await cb.message.edit_text("Пусто.", reply_markup=back_btn("admin_staff"))
    text = "📜 <b>Логи:</b>\n\n"
    for log in logs: text += f"👤 {log[0]} | {log[1]}\n📝 {log[2]}\n🕒 {log[3][:16]}\n\n"
    await cb.message.edit_text(text, reply_markup=back_btn("admin_staff"))
    await cb.answer()

@dp.callback_query(F.data == "hr_set_staff")
async def hr_set_staff_prompt(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("ID для назначения Замом:", reply_markup=back_btn("admin_staff"))
    await state.set_state(AdminState.waiting_staff_id)
    await cb.answer()

@dp.message(AdminState.waiting_staff_id)
async def hr_set_staff_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    uid = int(message.text)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO admins (user_id, rank) VALUES (?, 2)", (uid,))
        await db.commit()
    await message.answer(f"✅ {uid} — Зам!", reply_markup=main_menu(message.from_user.id))
    await state.clear()
    try: await bot.send_message(uid, "👑 Вам выданы права Заместителя! /admin")
    except: pass

@dp.callback_query(F.data == "admin_edit_bal")
async def admin_edit_bal(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("ID игрока:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_edit_id)
    await cb.answer()

@dp.message(AdminState.waiting_edit_id)
async def admin_edit_bal_id(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
    await state.update_data(target_id=int(message.text))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 МОНЕТЫ", callback_data="edit_type_balance")],
        [InlineKeyboardButton(text="💎 КОЭНЫ", callback_data="edit_type_coins")],
        [InlineKeyboardButton(text="◀️ ОТМЕНА", callback_data="close_admin")]
    ])
    await message.answer("Что изменить?", reply_markup=kb)
    await state.set_state(AdminState.waiting_edit_type)

@dp.callback_query(F.data.startswith("edit_type_"))
async def admin_edit_bal_type(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await state.update_data(edit_type=cb.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ НАЧИСЛИТЬ", callback_data="edit_action_add")],
        [InlineKeyboardButton(text="➖ СПИСАТЬ", callback_data="edit_action_sub")],
        [InlineKeyboardButton(text="◀️ ОТМЕНА", callback_data="close_admin")]
    ])
    await cb.message.edit_text("Действие:", reply_markup=kb)
    await state.set_state(AdminState.waiting_edit_action)
    await cb.answer()

@dp.callback_query(F.data.startswith("edit_action_"))
async def admin_edit_bal_action(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await state.update_data(edit_action=cb.data.split("_")[2])
    await cb.message.edit_text("Сумма:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_edit_amount)
    await cb.answer()

@dp.message(AdminState.waiting_edit_amount)
async def admin_edit_bal_amount(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
    amount = int(message.text)
    data = await state.get_data()
    await state.clear()
    is_coin = (data.get('edit_type') == "coins")
    final = amount if data.get('edit_action') == "add" else -amount
    await upd_bal(data['target_id'], final, is_coin=is_coin)
    await add_hr_log(message.from_user.id, "EDIT_BAL", f"{data['target_id']}, {data['edit_type']}, {final}")
    await message.answer(f"✅ Готово.", reply_markup=admin_menu(3, message.from_user.id))

@dp.callback_query(F.data == "admin_stars_prices")
async def admin_stars_prices(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("Только для главного!", show_alert=True)
    p50 = await get_setting("price_50_stars")
    p100 = await get_setting("price_100_stars")
    p3 = await get_setting("price_prem3")
    p6 = await get_setting("price_prem6")
    p12 = await get_setting("price_prem12")
    text = f"⭐ <b>ЦЕНЫ</b>\n\n50 Stars: {p50}\n100 Stars: {p100}\nPrem 3м: {p3}\nPrem 6м: {p6}\nPrem 12м: {p12}\n\nЧто меняем?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50 Stars", callback_data="sp_50"), InlineKeyboardButton(text="100 Stars", callback_data="sp_100")],
        [InlineKeyboardButton(text="Prem 3м", callback_data="sp_prem3"), InlineKeyboardButton(text="Prem 6м", callback_data="sp_prem6")],
        [InlineKeyboardButton(text="Prem 12м", callback_data="sp_prem12")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="close_admin")]
    ])
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("sp_"))
async def stars_price_set(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    key = cb.data.split("_")[1]
    await state.update_data(price_key=key)
    await cb.message.edit_text("Новая цена (число):", reply_markup=back_btn("admin_stars_prices"))
    await state.set_state(AdminState.waiting_stars_price)
    await cb.answer()

@dp.message(AdminState.waiting_stars_price)
async def stars_price_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    data = await state.get_data()
    await set_setting(f"price_{data['price_key']}", message.text)
    await message.answer(f"✅ Обновлено!", reply_markup=admin_menu(3, message.from_user.id))
    await state.clear()

# ================= ФОНОВЫЕ ЗАДАЧИ =================
async def keep_alive():
    while True:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("SELECT 1")
            await db.commit()
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
    asyncio.create_task(web_server())
    asyncio.create_task(keep_alive())
    print("Бот запущен (пакет 1: streak, edit cases, pity)!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
