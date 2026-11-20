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
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, LabeledPrice
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= КОНФИГ =================
BOT_TOKEN = os.environ.get("9254195561:AAE6CofEP8-YXxWig89-TqoH6JR3sLXvUYA", "9254195561:AAE6CofEP8-YXxWig89-TqoH6JR3sLXvUYA")
ADMIN_IDS = [8400799305]
CHANNEL_ID = "@casehab"
CHANNEL_LINK = "https://t.me/casehab"
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
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, balance INTEGER DEFAULT 1000, coins INTEGER DEFAULT 0, referrer_id INTEGER, referrals INTEGER DEFAULT 0, last_bonus TEXT DEFAULT '')")
        await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, rarity TEXT, value INTEGER, is_withdrawn INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, user_id INTEGER, item_name TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, rank INTEGER DEFAULT 1)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS hr_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, details TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY, reason TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS quests (user_id INTEGER, quest_key TEXT, progress INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, PRIMARY KEY (user_id, quest_key))")
        
        await db.execute("INSERT OR IGNORE INTO admins (user_id, rank) VALUES (?, 3)", (ADMIN_IDS[0],))
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'False')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('panic', 'False')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bj_chance', '20')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('shop_price', '100000')")
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

async def upd_bal(user_id, amount, is_coin=False):
    async with aiosqlite.connect(DB_PATH) as db:
        if is_coin: await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        else: await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def add_item(user_id, name, rarity, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO inventory (user_id, item_name, rarity, value) VALUES (?, ?, ?, ?)", (user_id, name, rarity, value))
        await db.commit()

def gen_code(l=8): return "".join(random.choices(string.ascii_uppercase + string.digits, k=l))

async def add_hr_log(admin_id, action, details=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO hr_logs (admin_id, action, details, timestamp) VALUES (?, ?, ?, ?)", (admin_id, action, details, datetime.datetime.now().isoformat()))
        await db.commit()

# ================= КЕЙСЫ =================
CASES = {
    "poor": {"name": "🥺 Нищий", "price": 15, "coin_price": 5, "mon_price": 15000, "items": [("2 звезды", "common", 2, 70, "50%"), ("5 звезд", "rare", 5, 25, "30%"), ("20 звезд", "epic", 20, 5, "15%"), ("💎 Алмаз", "legendary", 500, 3, "4%"), ("🚀 Ракета", "legendary", 1000, 1.5, "0.8%"), ("🏆 Кубок", "mythic", 5000, 0.5, "0.2%")]},
    "rich": {"name": "👑 Богатый", "price": 100, "coin_price": 30, "mon_price": 100000, "items": [("10 звезд", "common", 10, 60, "50%"), ("50 звезд", "rare", 50, 30, "40%"), ("NFT Кубок", "epic", 500, 9, "9%"), ("👑 Корона", "legendary", 2500, 1, "1%")]},
    "nft": {"name": "💎 NFT Кейс", "price": 700, "coin_price": 250, "mon_price": 1000000, "items": [("50 звезд", "common", 50, 60, "60%"), ("100 звезд", "rare", 100, 25, "25%"), ("Сердечко", "epic", 200, 10, "10%"), ("🚀 Ракета", "legendary", 1000, 4, "4%"), ("👑 ТОП NFT", "mythic", 5000, 1, "1%")]}
}

def open_case(key):
    items = CASES[key]["items"]
    if asyncio.run(get_setting("panic")) == "True": items = [i for i in items if i[2] <= 50]
    weights = [i[3] for i in items]
    return random.choices(items, weights=weights, k=1)[0]

# ================= АНИМАЦИЯ =================
async def play_animation(message: Message, case_name: str):
    emojis = ["🍒", "🍋", "💎", "🎁", "👑", "🚀", "⭐", "🏆"]
    msg = await message.edit_text(f"<b>🎰 ЗАПУСК РУЛЕТКИ...</b>\n\n[ ⬜️ ⬜️ ⬜️ ]")
    await asyncio.sleep(0.2)
    for i in range(4):
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
        [InlineKeyboardButton(text="🎯 КВЕСТЫ", callback_data="quests"), InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily_bonus")],
        [InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="⭐ STARS/ПРЕМКА", callback_data="buy_stars")],
        [InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inv"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="prof")],
        [InlineKeyboardButton(text="🏆 ТОП", callback_data="top_players"), InlineKeyboardButton(text="🔑 ПРОМОКОД", callback_data="promo")],
        [InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="ref"), InlineKeyboardButton(text="ℹ️ О БОТЕ", callback_data="about")],
        [InlineKeyboardButton(text="📜 КОМАНДЫ", callback_data="commands")]
    ]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="👑 АДМИН ПАНЕЛЬ", callback_data="admin_panel")])
        kb.append([InlineKeyboardButton(text="🟢 ПИНГ (НЕ СПАТЬ)", callback_data="ping_bot")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_btn(cb="back_main"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ НАЗАД", callback_data=cb)]])

def admin_menu(rank):
    kb = []
    kb.append([InlineKeyboardButton(text="📜 МОИ ПРАВА", callback_data="my_rights")])
    if rank >= 2:
        kb.append([InlineKeyboardButton(text="🎁 КУПОН", callback_data="admin_coupon"), InlineKeyboardButton(text="🔑 ПРОМО", callback_data="admin_promo")])
        kb.append([InlineKeyboardButton(text="🚫 НАКАЗАНИЯ", callback_data="admin_bans")])
    if rank == 3:
        kb.append([InlineKeyboardButton(text="💰 ВЫДАТЬ ВАЛЮТУ", callback_data="admin_give_menu")])
        kb.append([InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ БАЛАНС", callback_data="admin_edit_bal")])
        kb.append([InlineKeyboardButton(text="🚨 ПАНИКА", callback_data="admin_panic"), InlineKeyboardButton(text="🛠 ТЕХ.РАБОТЫ", callback_data="admin_maint")])
        kb.append([InlineKeyboardButton(text="👥 HR-ПАНЕЛЬ", callback_data="admin_staff")])
        kb.append([InlineKeyboardButton(text="⚙️ ШАНСЫ БД", callback_data="admin_odds")])
        kb.append([InlineKeyboardButton(text="🛒 НАСТРОЙКИ МАГАЗИНА", callback_data="admin_shop")])
    kb.append([InlineKeyboardButton(text="ЗАКРЫТЬ", callback_data="close_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

class UserState(StatesGroup):
    waiting_promo = State()
    waiting_bet = State()
    waiting_coin_amount = State()

class AdminState(StatesGroup):
    waiting_coupon = State()
    waiting_promo_val = State()
    waiting_promo_uses = State()
    waiting_give_id = State()
    waiting_give_amount = State()
    waiting_staff_id = State()
    waiting_bj_chance = State()
    waiting_ban_id = State()
    waiting_ban_reason = State()
    waiting_shop_price = State()
    waiting_edit_id = State()
    waiting_edit_type = State()
    waiting_edit_amount = State()
    waiting_edit_action = State()

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
    if user is None:
        await add_user(u.id, u.username or "", u.full_name, ref_id)
        user = await get_user(u.id)
        
    text = (
        f"👋 <b>ДОБРО ПОЖАЛОВАТЬ, {u.full_name.upper()}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Монеты:</b> {user[3]}\n"
        f"💎 <b>Коэны:</b> {user[4]}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(text, reply_markup=main_menu(u.id))

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    text = (
        f"🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Монеты:</b> {user[3]}\n"
        f"💎 <b>Коэны:</b> {user[4]}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await cb.message.edit_text(text, reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

@dp.callback_query(F.data == "commands")
async def commands_menu(cb: CallbackQuery):
    text = (
        f"📜 <b>ВСЕ КОМАНДЫ И ФУНКЦИИ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎁 <b>Кейсы</b> — Открытие кейсов за Stars, Коэны и Монеты.\n"
        f"🎮 <b>Игры</b> — Апгрейд, Монетка, Блэкджек.\n"
        f"🎯 <b>Квесты</b> — Выполняй задания и получай монеты.\n"
        f"🎁 <b>Бонус</b> — Ежедневный бонус (раз в 24 часа).\n"
        f"🛒 <b>Магазин</b> — Обмен Монет на Коэны.\n"
        f"⭐ <b>Stars</b> — Покупка звезд и премиума.\n"
        f"🎒 <b>Инвентарь</b> — Просмотр, продажа и вывод предметов.\n"
        f"👤 <b>Профиль</b> — Твой ID и баланс.\n"
        f"🏆 <b>Топ</b> — Лучшие игроки по балансу.\n"
        f"🔑 <b>Промокод</b> — Активация бонусного кода.\n"
        f"👥 <b>Рефералы</b> — Пригласи друзей для вывода.\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>АДМИН ПАНЕЛЬ:</b> /admin"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("Нет прав!", show_alert=True)
    await cb.message.edit_text("👑 <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=admin_menu(3))
    await cb.answer()

@dp.callback_query(F.data == "ping_bot")
async def ping_bot(cb: CallbackQuery):
    await cb.answer("🟢 Я ЖИВ! Бот работает.", show_alert=True)

@dp.callback_query(F.data == "about")
async def about_bot(cb: CallbackQuery):
    text = f"ℹ️ <b>О БОТЕ CASEHAB</b>\n━━━━━━━━━━━━━━━━━━\nЛучший бот для открытия кейсов!\n\n📩 <b>Поддержка:</b> {CONTACT_ADMIN}"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "prof")
async def prof(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    text = f"👤 <b>ПРОФИЛЬ</b>\n━━━━━━━━━━━━━━━━━━\n🆔 <b>ID:</b> <code>{user[0]}</code>\n💰 <b>Монеты:</b> {user[3]}\n💎 <b>Коэны:</b> {user[4]}\n👥 <b>Рефералы:</b> {user[6]}/3\n━━━━━━━━━━━━━━━━━━"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "ref")
async def ref(cb: CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
    text = f"👥 <b>РЕФЕРАЛЫ</b>\n━━━━━━━━━━━━━━━━━━\nПригласи 3 друзей и получи доступ к выводу!\n\n🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>"
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

@dp.callback_query(F.data == "daily_bonus")
async def daily_bonus(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    today = str(datetime.date.today())
    if user[7] == today: return await cb.answer("❌ ВЫ УЖЕ ЗАБРАЛИ БОНУС СЕГОДНЯ!", show_alert=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + 5000, last_bonus = ? WHERE user_id = ?", (today, cb.from_user.id))
        await db.commit()
    await cb.answer("✅ ВЫ ПОЛУЧИЛИ 5000 МОНЕТ!", show_alert=True)
    await back_main(cb)

# ================= МАГАЗИН И КВЕСТЫ =================
@dp.callback_query(F.data == "shop")
async def shop_menu(cb: CallbackQuery):
    price = await get_setting("shop_price")
    text = f"🛒 <b>МАГАЗИН</b>\n━━━━━━━━━━━━━━━━━━\nОбмен Монет на Коэны.\n\n💱 <b>Курс:</b> {price} Монет = 10 Коэнов\n\nВведите количество Коэнов:"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "quests")
async def quests_menu(cb: CallbackQuery):
    # Заглушка для квестов
    text = "🎯 <b>КВЕСТЫ</b>\n━━━━━━━━━━━━━━━━━━\n▪️ Открой 1 кейс — 2000💰\n▪️ Сделай 1 апгрейд — 3000💰\n▪️ Пригласи друга — 5000💰\n\n(Скоро заработает полностью)"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

# ================= ПОКУПКА ЗВЕЗД =================
@dp.callback_query(F.data == "buy_stars")
async def buy_stars_menu(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 50 Stars — 50 руб", callback_data="buy_50_stars")],
        [InlineKeyboardButton(text="⭐ 100 Stars — 100 руб", callback_data="buy_100_stars")],
        [InlineKeyboardButton(text="👑 Премиум 3 мес — 150 Stars", callback_data="buy_prem3")],
        [InlineKeyboardButton(text="👑 Премиум 6 мес — 300 Stars", callback_data="buy_prem6")],
        [InlineKeyboardButton(text="👑 Премиум 12 мес — 500 Stars", callback_data="buy_prem12")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await cb.message.edit_text("⭐ <b>Магазин Stars и Премиума</b>\n\nВыберите товар:\n(Оплата в рублях на карту)", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_stars(cb: CallbackQuery, state: FSMContext):
    item = cb.data.split("_")[1]
    names = {"50": "50 Stars", "100": "100 Stars", "prem3": "Премиум 3 месяца", "prem6": "Премиум 6 месяцев", "prem12": "Премиум 12 месяцев"}
    name = names.get(item, "Товар")
    await cb.message.edit_text(f"⭐ <b>Покупка: {name}</b>\n\nПереведите сумму на карту:\n<code>{CARD_NUMBER}</code> ({CARD_BANK})\n\n📩 <b>Отправьте чек:</b> {CONTACT_ADMIN}", reply_markup=back_btn("buy_stars"))
    await cb.answer()

# --- КЕЙСЫ ---
@dp.callback_query(F.data == "cases")
async def cases_menu(cb: CallbackQuery):
    kb = []
    for k, c in CASES.items(): kb.append([InlineKeyboardButton(text=f"{c['name']}", callback_data=f"view_{k}")])
    kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
    await cb.message.edit_text("🎁 <b>ВЫБЕРИ КЕЙС</b>\n━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await cb.answer()

@dp.callback_query(F.data.startswith("view_"))
async def view_case(cb: CallbackQuery):
    key = cb.data.split("_")[1]
    case = CASES[key]
    text = f"🎁 <b>{case['name'].upper()}</b>\n━━━━━━━━━━━━━━━━━━\n"
    for item in case["items"]: text += f"▪️ {item[0]} — {item[4]}\n"
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
    case = CASES[key]
    prices = [LabeledPrice(label=case["name"], amount=case["price"])]
    await bot.send_invoice(chat_id=cb.from_user.id, title=case["name"], description="Открыть кейс?", payload=f"case_{key}", provider_token="", currency="XTR", prices=prices)
    await cb.answer()

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_coins"))
async def open_coins(cb: CallbackQuery):
    key = cb.data.split("_")[1]
    case = CASES[key]
    user = await get_user(cb.from_user.id)
    if user[4] < case["coin_price"]: return await cb.answer("❌ НЕДОСТАТОЧНО КОЭНОВ!", show_alert=True)
    await upd_bal(cb.from_user.id, -case["coin_price"], is_coin=True)
    msg = await play_animation(cb.message, case['name'])
    name, rarity, val, w, fake = open_case(key)
    await add_item(cb.from_user.id, name, rarity, val)
    await msg.edit_text(f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐", reply_markup=back_btn("cases"))
    await cb.answer("Поздравляем!")

@dp.callback_query(F.data.startswith("open_") & F.data.endswith("_mon"))
async def open_mon(cb: CallbackQuery):
    key = cb.data.split("_")[1]
    case = CASES[key]
    user = await get_user(cb.from_user.id)
    if user[3] < case["mon_price"]: return await cb.answer("❌ НЕДОСТАТОЧНО МОНЕТ!", show_alert=True)
    await upd_bal(cb.from_user.id, -case["mon_price"], is_coin=False)
    msg = await play_animation(cb.message, case['name'])
    name, rarity, val, w, fake = open_case(key)
    await add_item(cb.from_user.id, name, rarity, val)
    await msg.edit_text(f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐", reply_markup=back_btn("cases"))
    await cb.answer("Поздравляем!")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_pay(message: Message):
    key = message.successful_payment.invoice_payload.split("_")[1]
    name, rarity, val, w, fake = open_case(key)
    await add_item(message.from_user.id, name, rarity, val)
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
    if user[6] < 3:
        return await cb.answer(f"❌ НУЖНО 3 РЕФЕРАЛА! У тебя: {user[6]}/3", show_alert=True)
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 АПГРЕЙД X2 (50%)", callback_data="game_up")],
        [InlineKeyboardButton(text="🪙 МОНЕТКА (50%)", callback_data="game_coin")],
        [InlineKeyboardButton(text="🃏 БЛЭКДЖЕК (20%)", callback_data="game_bj")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")]
    ])
    await cb.message.edit_text("🎮 <b>ИГРЫ</b>", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("game_"))
async def game_bet(cb: CallbackQuery, state: FSMContext):
    await state.update_data(game=cb.data)
    await cb.message.edit_text("💰 <b>ВВЕДИ СУММУ СТАВКИ (МОНЕТЫ):</b>", reply_markup=back_btn("games"))
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
    
    if game == "game_up": win = random.random() < 0.5
    elif game == "game_coin": win = random.choice([True, False])
    elif game == "game_bj": win = random.random() < (int(await get_setting("bj_chance")) / 100.0)
        
    if win:
        await upd_bal(message.from_user.id, bet)
        await message.answer(f"🎉 <b>ПОБЕДА!</b>\nТы выиграл <b>{bet}</b> монет.", reply_markup=main_menu(message.from_user.id))
    else:
        await upd_bal(message.from_user.id, -bet)
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
        async with db.execute("SELECT reward, uses_left FROM promo_codes WHERE code = ?", (code,)) as cur:
            promo = await cur.fetchone()
        if not promo or promo[1] <= 0: return await message.answer("❌ НЕВЕРНЫЙ ПРОМОКОД.", reply_markup=main_menu(message.from_user.id))
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[0], message.from_user.id))
        await db.commit()
    await message.answer(f"✅ <b>АКТИВИРОВАН!</b>\nПолучено <b>{promo[0]}</b> монет.", reply_markup=main_menu(message.from_user.id))

# ================= АДМИН-ПАНЕЛЬ =================
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    rank = await get_admin_rank(message.from_user.id)
    if rank == 0: return
    await message.answer("👑 <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=admin_menu(rank))

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

@dp.callback_query(F.data == "admin_panic")
async def admin_panic(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cur = await get_setting("panic") == "True"
    await set_setting("panic", str(not cur))
    await cb.answer(f"🚨 ПАНИКА: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)

@dp.callback_query(F.data == "admin_maint")
async def admin_maint(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cur = await get_setting("maintenance") == "True"
    await set_setting("maintenance", str(not cur))
    await cb.answer(f"🛠 ТЕХ.РАБОТЫ: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)

@dp.callback_query(F.data == "admin_edit_bal")
async def admin_edit_bal(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("🆔 <b>ВВЕДИ ID ИГРОКА:</b>", reply_markup=back_btn("close_admin"))
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
    await message.answer("💱 <b>ЧТО ИЗМЕНИТЬ?</b>", reply_markup=kb)
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
    await cb.message.edit_text("⚙️ <b>ВЫБЕРИ ДЕЙСТВИЕ:</b>", reply_markup=kb)
    await state.set_state(AdminState.waiting_edit_action)
    await cb.answer()

@dp.callback_query(F.data.startswith("edit_action_"))
async def admin_edit_bal_action(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await state.update_data(edit_action=cb.data.split("_")[2])
    await cb.message.edit_text("🔢 <b>ВВЕДИ СУММУ:</b>", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_edit_amount)
    await cb.answer()

@dp.message(AdminState.waiting_edit_amount)
async def admin_edit_bal_amount(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ ВВЕДИ ЧИСЛО!")
    amount = int(message.text)
    data = await state.get_data()
    target_id = data.get('target_id')
    edit_type = data.get('edit_type')
    edit_action = data.get('edit_action')
    await state.clear()
    is_coin = (edit_type == "coins")
    final_amount = amount if edit_action == "add" else -amount
    await upd_bal(target_id, final_amount, is_coin=is_coin)
    action_text = "НАЧИСЛЕНО" if edit_action == "add" else "СПИСАНО"
    curr_text = "КОЭНОВ" if is_coin else "МОНЕТ"
    await message.answer(f"✅ {action_text} {amount} {curr_text} ПОЛЬЗОВАТЕЛЮ {target_id}.", reply_markup=admin_menu(3))

@dp.callback_query(F.data == "admin_coupon")
async def admin_coupon(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) < 2: return await cb.answer("Нет прав!", show_alert=True)
    await cb.message.edit_text("Отправьте код купона:", reply_markup=back_btn("close_admin"))
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
    if status == 'given': return await message.answer("⚠️ Купон УЖЕ ВЫДАН!", reply_markup=main_menu(message.from_user.id))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я выдал подарок", callback_data=f"givecoupon_{code}")]])
    await message.answer(f"🔍 <b>Купон:</b>\n👤 {name} ({uid})\n🎁 {item}\n\nВыдать?", reply_markup=kb)

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
    try: await bot.send_message(uid, f"🎉 Твой подарок выдан! Купон {code} погашен.")
    except: pass
    await cb.answer()

@dp.callback_query(F.data == "admin_promo")
async def admin_promo(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) < 2: return
    await cb.message.edit_text("Введите сумму награды:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_promo_val)
    await cb.answer()

@dp.message(AdminState.waiting_promo_val)
async def admin_promo_val(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(val=int(message.text))
    await message.answer("Введите количество активаций:")
    await state.set_state(AdminState.waiting_promo_uses)

@dp.message(AdminState.waiting_promo_uses)
async def admin_promo_uses(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    code = gen_code(8)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO promo_codes (code, reward, uses_left) VALUES (?, ?, ?)", (code, data['val'], int(message.text)))
        await db.commit()
    await message.answer(f"✅ Промокод: <code>{code}</code>\nСумма: {data['val']}\nАктиваций: {message.text}", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_shop")
async def admin_shop(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    price = await get_setting("shop_price")
    await cb.message.edit_text(f"Текущая цена: {price} Монет за 10 Коэнов.\n\nВведите новую цену:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_shop_price)
    await cb.answer()

@dp.message(AdminState.waiting_shop_price)
async def admin_set_shop(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await set_setting("shop_price", message.text)
    await message.answer(f"✅ Цена обновлена: {message.text} Монет за 10 Коэнов.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_odds")
async def admin_odds(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("Введите новый шанс Блэкджека (в %):", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_bj_chance)
    await cb.answer()

@dp.message(AdminState.waiting_bj_chance)
async def set_bj_chance(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await set_setting("bj_chance", message.text)
    await message.answer(f"✅ Шанс БД: {message.text}%", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_staff")
async def admin_staff(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Логи действий", callback_data="hr_logs")],
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
    if not logs: return await cb.message.edit_text("Логов пока нет.", reply_markup=back_btn("admin_staff"))
    text = "📜 <b>Последние действия:</b>\n\n"
    for log in logs: text += f"👤 {log[0]} | {log[1]}\n📝 {log[2]}\n🕒 {log[3][:16]}\n\n"
    await cb.message.edit_text(text, reply_markup=back_btn("admin_staff"))
    await cb.answer()

@dp.callback_query(F.data == "hr_set_staff")
async def hr_set_staff_prompt(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("Введите ID пользователя, чтобы назначить его Замом:", reply_markup=back_btn("admin_staff"))
    await state.set_state(AdminState.waiting_staff_id)
    await cb.answer()

@dp.message(AdminState.waiting_staff_id)
async def hr_set_staff_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    uid = int(message.text)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO admins (user_id, rank) VALUES (?, 2)", (uid,))
        await db.commit()
    await message.answer(f"✅ Пользователь {uid} назначен Заместителем!", reply_markup=main_menu(message.from_user.id))
    await state.clear()
    try: await bot.send_message(uid, "👑 Вам выданы права Заместителя! Напишите /admin")
    except: pass

@dp.callback_query(F.data == "admin_bans")
async def admin_bans(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) < 2: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="ban_user")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="close_admin")]
    ])
    await cb.message.edit_text("🛠 <b>Управление наказаниями</b>", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "ban_user")
async def ban_user(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Введите ID пользователя для бана:", reply_markup=back_btn("admin_bans"))
    await state.set_state(AdminState.waiting_ban_id)
    await cb.answer()

@dp.message(AdminState.waiting_ban_id)
async def ban_user_id(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(uid=int(message.text))
    await message.answer("Введите причину бана:")
    await state.set_state(AdminState.waiting_ban_reason)

@dp.message(AdminState.waiting_ban_reason)
async def ban_user_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = data['uid']
    reason = message.text
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO bans (user_id, reason) VALUES (?, ?)", (uid, reason))
        await db.commit()
    await message.answer(f"✅ Пользователь {uid} забанен.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# ================= АНТИ-СОН =================
async def keep_alive():
    while True:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("SELECT 1")
            await db.commit()
        await asyncio.sleep(600)

# ================= ЗАПУСК =================
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
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
