import asyncio
import logging
import datetime
import random
import string
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, LabeledPrice
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= КОНФИГ =================
BOT_TOKEN = "9233529693:AAGCJvIMICxQIwAjLI97NyiNhYGg4WCZn2k"
ADMIN_IDS = [84007999305]
CHANNEL_ID = "@casehab"
CHANNEL_LINK = "https://t.me/casehab"

# ================= БАЗА ДАННЫХ =================
DB_PATH = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, balance INTEGER DEFAULT 1000, last_bonus TEXT DEFAULT '', joined_at TEXT, referrer_id INTEGER, referrals INTEGER DEFAULT 0, last_seen TEXT DEFAULT '')")
        await db.execute("CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, details TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, rarity TEXT, value INTEGER, obtained_at TEXT, is_withdrawn INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS quests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, quest_key TEXT, progress INTEGER DEFAULT 0, target INTEGER, reward INTEGER, claimed INTEGER DEFAULT 0, day TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_used (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, code TEXT, activated_at TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER, created_at TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, user_id INTEGER, item_name TEXT, item_id INTEGER, created_at TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.commit()

async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def add_user(user_id, username, full_name, referrer_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            exists = await cur.fetchone()
        now = datetime.datetime.now().isoformat()
        if not exists:
            await db.execute("INSERT INTO users (user_id, username, full_name, balance, joined_at, referrer_id, last_seen) VALUES (?, ?, ?, 1000, ?, ?, ?)", (user_id, username, full_name, now, referrer_id, now))
            if referrer_id:
                await db.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (referrer_id,))
        else:
            await db.execute("UPDATE users SET last_seen = ?, username = ?, full_name = ? WHERE user_id = ?", (now, username, full_name, user_id))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

async def update_balance(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def log_activity(user_id, action, details=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO activity (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)", (user_id, action, details, datetime.datetime.now().isoformat()))
        await db.commit()

async def get_recent_activity(limit=30):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT a.action, a.details, a.timestamp, u.username, u.full_name FROM activity a LEFT JOIN users u ON a.user_id = u.user_id ORDER BY a.id DESC LIMIT ?", (limit,)) as cur:
            return await cur.fetchall()

async def get_online_users(minutes=15):
    threshold = (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name, username FROM users WHERE last_seen > ?", (threshold,)) as cur:
            return await cur.fetchall()

async def add_item(user_id, item_name, rarity, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO inventory (user_id, item_name, rarity, value, obtained_at) VALUES (?, ?, ?, ?, ?)", (user_id, item_name, rarity, value, datetime.datetime.now().isoformat()))
        await db.commit()

async def get_inventory(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, item_name, rarity, value, is_withdrawn FROM inventory WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchall()

async def get_item(item_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)) as cur:
            return await cur.fetchone()

async def delete_item(item_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        await db.commit()

async def get_top_players(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT username, full_name, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)) as cur:
            return await cur.fetchall()

async def can_claim_bonus(user_id):
    user = await get_user(user_id)
    if not user or not user[5]: return True
    try: return datetime.date.fromisoformat(user[5][:10]) < datetime.date.today()
    except: return True

async def claim_bonus(user_id, amount):
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ?, last_bonus = ? WHERE user_id = ?", (amount, today, user_id))
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur: users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM coupons WHERE status = 'pending'") as cur: pending = (await cur.fetchone())[0]
        return users, pending

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            return [row[0] for row in await cur.fetchall()]

DAILY_QUESTS = {"open_cases": {"name": "🎁 Открой 3 кейса", "target": 3, "reward": 1000}, "sell_items": {"name": "💸 Продай 2 предмета", "target": 2, "reward": 800}, "upgrade_item": {"name": "⬆️ Сделай 1 апгрейд", "target": 1, "reward": 1500}, "open_cheap": {"name": "🟢 Открой 1 дешёвый кейс", "target": 1, "reward": 500}}

async def init_daily_quests(user_id):
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        for key, q in DAILY_QUESTS.items():
            async with db.execute("SELECT id FROM quests WHERE user_id=? AND quest_key=? AND day=?", (user_id, key, today)) as cur:
                if not await cur.fetchone():
                    await db.execute("INSERT INTO quests (user_id, quest_key, progress, target, reward, claimed, day) VALUES (?, ?, 0, ?, ?, 0, ?)", (user_id, key, q["target"], q["reward"], today))
        await db.commit()

async def add_quest_progress(user_id, quest_key, amount=1):
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE quests SET progress = progress + ? WHERE user_id=? AND quest_key=? AND day=? AND claimed=0", (amount, user_id, quest_key, today))
        await db.commit()

async def get_user_quests(user_id):
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, quest_key, progress, target, reward, claimed FROM quests WHERE user_id=? AND day=?", (user_id, today)) as cur:
            return await cur.fetchall()

async def claim_quest(quest_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT progress, target, reward, claimed FROM quests WHERE id=? AND user_id=?", (quest_id, user_id)) as cur:
            row = await cur.fetchone()
        if not row or row[3] or row[0] < row[1]: return None
        await db.execute("UPDATE quests SET claimed=1 WHERE id=?", (quest_id,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (row[2], user_id))
        await db.commit()
        return row[2]

def generate_code(length=8): return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

async def create_promo(code, reward, uses):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO promo_codes (code, reward, uses_left, created_at) VALUES (?, ?, ?, ?)", (code.upper(), reward, uses, datetime.datetime.now().isoformat()))
        await db.commit()

async def activate_promo(user_id, code):
    code = code.upper().strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT reward, uses_left FROM promo_codes WHERE code=?", (code,)) as cur: promo = await cur.fetchone()
        if not promo: return "not_found"
        if promo[1] <= 0: return "used_up"
        async with db.execute("SELECT id FROM promo_used WHERE user_id=? AND code=?", (user_id, code)) as cur:
            if await cur.fetchone(): return "already_used"
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code=?", (code,))
        await db.execute("INSERT INTO promo_used (user_id, code, activated_at) VALUES (?, ?, ?)", (user_id, code, datetime.datetime.now().isoformat()))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (promo[0], user_id))
        await db.commit()
        return promo[0]

async def generate_coupon(user_id, item_id, item_name):
    code = f"GIFT-{generate_code(4)}-{generate_code(4)}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO coupons (code, user_id, item_name, item_id, created_at) VALUES (?, ?, ?, ?, ?)", (code, user_id, item_name, item_id, datetime.datetime.now().isoformat()))
        await db.execute("UPDATE inventory SET is_withdrawn = 1 WHERE id = ?", (item_id,))
        await db.commit()
    return code

async def get_coupon_info(code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT c.user_id, c.item_name, u.username, u.full_name, c.status FROM coupons c JOIN users u ON c.user_id = u.user_id WHERE c.code = ?", (code.upper(),)) as cur:
            return await cur.fetchone()

async def mark_coupon_given(code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE coupons SET status = 'given' WHERE code = ?", (code.upper(),))
        await db.commit()

# ================= КЕЙСЫ ЗА STARS =================
CASES = {
    "poor": {"name": "🥺 Нищий кейс", "price_stars": 15, "display_chance": "20% на большой выигрыш", "items": [("Подарок 2 звезды", "common", 2, 40), ("Подарок 3 звезды", "common", 3, 30), ("Подарок 5 звезд", "rare", 5, 29), ("Подарок 20 звезд", "epic", 20, 1)]},
    "medium": {"name": "🐻 Средний кейс", "price_stars": 50, "display_chance": "Шанс на Алмаз 20%", "items": [("🐻 Мишка", "common", 20, 40), ("🌹 Роза", "common", 25, 40), ("💎 Алмаз", "epic", 100, 20)]},
    "rich": {"name": "👑 Богатый кейс", "price_stars": 1000, "display_chance": "Шанс на NFT и Кубок", "items": [("🎁 Дешевый NFT", "rare", 150, 50), ("🏆 Кубок", "epic", 300, 30), ("💖 Сердечко", "epic", 400, 15), ("💎 Алмаз", "legendary", 500, 5)]}
}
RARITY_EMOJI = {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡", "mythic": "🔴"}

def open_case(case_key):
    items = CASES[case_key]["items"]
    weights = [i[3] for i in items]
    return random.choices(items, weights=weights, k=1)[0]

def try_upgrade(rarity):
    chances = {"common": 0.70, "rare": 0.55, "epic": 0.40, "legendary": 0.25, "mythic": 0.15}
    return random.random() < chances.get(rarity, 0.5)

DEFAULT_PROMOS = [("WELCOME2024", 2000, 100), ("STARTBOT", 1000, 500)]

# ================= БОТ И КНОПКИ =================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class PromoState(StatesGroup):
    waiting_code = State()
class AdminState(StatesGroup):
    waiting_broadcast = State()
    waiting_coupon = State()
    waiting_promo = State()
    waiting_channel_post = State()

def check_sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ])

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Кейсы за Stars", callback_data="cases_menu")],
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"), InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="ref_menu")],
        [InlineKeyboardButton(text="🎯 Квесты", callback_data="quests"), InlineKeyboardButton(text="🎁 Бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top")],
        [InlineKeyboardButton(text="🔑 Промокод", callback_data="promo_prompt")],
    ])

def admin_menu(is_maintenance):
    maint_text = "🟢 Включить тех.работы" if not is_maintenance else "🔴 Выключить тех.работы"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🟢 Кто онлайн", callback_data="admin_online")],
        [InlineKeyboardButton(text="📋 Активность", callback_data="admin_activity")],
        [InlineKeyboardButton(text="🎁 Проверить купон", callback_data="admin_coupon")],
        [InlineKeyboardButton(text="🔑 Создать промокод", callback_data="admin_promo")],
        [InlineKeyboardButton(text="📢 Рассылка (в боте)", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📝 Пост в канал", callback_data="admin_channel_post")],
        [InlineKeyboardButton(text="📊 Статистика канала", callback_data="admin_channel_stats")],
        [InlineKeyboardButton(text=maint_text, callback_data="admin_toggle_maint")],
        [InlineKeyboardButton(text="◀️ Закрыть", callback_data="admin_close")],
    ])

def cases_menu():
    buttons = [[InlineKeyboardButton(text=f"{c['name']} — {c['price_stars']} ⭐", callback_data=f"open_case:{k}")] for k, c in CASES.items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_button(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]])

def inventory_keyboard(items):
    buttons = []
    for i, name, rarity, value, withdrawn in items:
        if withdrawn: buttons.append([InlineKeyboardButton(text=f"✅ {name} (Выведен)", callback_data="noop")])
        else: buttons.append([InlineKeyboardButton(text=f"💸 Продать {name} ({value})", callback_data=f"sell:{i}"), InlineKeyboardButton(text=f"📦 Вывести", callback_data=f"withdraw:{i}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def quests_keyboard(quests):
    buttons = []
    for q_id, key, progress, target, reward, claimed in quests:
        name = DAILY_QUESTS.get(key, {}).get("name", key)
        if claimed: text, cb = f"✅ {name} (получено)", "noop"
        elif progress >= target: text, cb = f"🎁 Забрать {reward} — {name}", f"claim_quest:{q_id}"
        else: text, cb = f"⏳ {name} [{progress}/{target}]", "noop"
        buttons.append([InlineKeyboardButton(text=text, callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= ПРОВЕРКА ПОДПИСКИ И ТЕХ.РАБОТ =================
@dp.message()
async def check_user_status(message: Message):
    if message.from_user.id in ADMIN_IDS: return
    if await get_setting("maintenance") == "True":
        return await message.answer("🛠 <b>Технические работы!</b>\n\nБот скоро вернется. Следите за новостями в канале!")
    
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=message.from_user.id)
        if member.status not in ["member", "administrator", "creator"]:
            return await message.answer("⚠️ <b>Для использования бота подпишись на наш канал!</b>", reply_markup=check_sub_kb())
    except Exception:
        pass 

# ================= ХЭНДЛЕРЫ =================
@dp.message(CommandStart())
async def start_cmd(message: Message):
    u = message.from_user
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if referrer_id == u.id: referrer_id = None
    await add_user(u.id, u.username or "", u.full_name, referrer_id)
    await init_daily_quests(u.id)
    await log_activity(u.id, "🚀 Зашёл в бота", f"@{u.username or 'нет'}")
    user = await get_user(u.id)
    await message.answer(f"👋 <b>Привет, {u.full_name}!</b>\n\n💰 Твой баланс: <b>{user[3]}</b> монет\n\nВыбери действие 👇", reply_markup=main_menu())

@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=cb.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            await cb.message.edit_text("✅ Спасибо за подписку! Теперь тебе доступны все функции.", reply_markup=main_menu())
        else:
            await cb.answer("❌ Ты еще не подписался!", show_alert=True)
    except Exception:
        await cb.answer("⚠️ Не удалось проверить подписку. Убедись, что бот админ в канале.", show_alert=True)

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    await cb.message.edit_text(f"🏠 <b>Главное меню</b>\n\n💰 Баланс: <b>{user[3]}</b> монет", reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery): await cb.answer()

@dp.callback_query(F.data == "ref_menu")
async def ref_menu(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
    await cb.message.edit_text(f"👥 <b>Пригласи друзей!</b>\n\nТы пригласил: <b>{user[7]}</b> из 3.\n\n🔗 Ссылка:\n<code>{ref_link}</code>", reply_markup=back_button())
    await cb.answer()

@dp.callback_query(F.data == "cases_menu")
async def show_cases(cb: CallbackQuery):
    await cb.message.edit_text("🎁 <b>Кейсы за Telegram Stars</b>", reply_markup=cases_menu())
    await cb.answer()

@dp.callback_query(F.data.startswith("open_case:"))
async def handle_open_case(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    case = CASES[key]
    prices = [LabeledPrice(label=case["name"], amount=case["price_stars"])]
    await bot.send_invoice(chat_id=cb.from_user.id, title=case["name"], description=f"Открой кейс! {case['display_chance']}", payload=f"case_{key}_{cb.from_user.id}", provider_token="", currency="XTR", prices=prices)
    await cb.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    case_key = parts[1]
    user_id = int(parts[2])
    case = CASES[case_key]
    name, rarity, value, weight = open_case(case_key)
    await add_item(user_id, name, rarity, value)
    await log_activity(user_id, f"🎁 Купил и открыл {case['name']}", f"Выпало: {name} ({value}⭐)")
    await add_quest_progress(user_id, "open_cases", 1)
    if case_key == "poor": await add_quest_progress(user_id, "open_cheap", 1)
    await message.answer(f"🎉 <b>Оплата прошла!</b>\n\n{RARITY_EMOJI[rarity]} Тебе выпало: <b>{name}</b>\n⭐ Редкость: <b>{rarity.upper()}</b>\n💵 Стоимость: <b>{value}</b> Stars\n\nПерейди в 🎒 Инвентарь, чтобы вывести подарок!", reply_markup=main_menu())

@dp.callback_query(F.data == "inventory")
async def show_inventory(cb: CallbackQuery):
    items = await get_inventory(cb.from_user.id)
    if not items: await cb.message.edit_text("🎒 <b>Инвентарь пуст</b>", reply_markup=back_button())
    else: await cb.message.edit_text(f"🎒 <b>Твой инвентарь</b>\n\nНажми 📦 Вывести, чтобы получить купон.", reply_markup=inventory_keyboard(items))
    await cb.answer()

@dp.callback_query(F.data.startswith("withdraw:"))
async def withdraw_item(cb: CallbackQuery):
    item_id = int(cb.data.split(":")[1])
    item = await get_item(item_id)
    user = await get_user(cb.from_user.id)
    if not item or item[1] != cb.from_user.id: return await cb.answer("❌ Предмет не найден!", show_alert=True)
    if item[6] == 1: return await cb.answer("❌ Уже выведен!", show_alert=True)
    if user[7] < 3: return await cb.answer(f"❌ Нужно 3 друга!\nУ тебя: {user[7]}/3", show_alert=True)
    code = await generate_coupon(cb.from_user.id, item_id, item[2])
    await cb.answer(f"✅ Купон создан: {code}", show_alert=True)
    await cb.message.edit_text(f"🎉 <b>Купон создан!</b>\n\nПредмет: <b>{item[2]}</b>\nКод:\n<code>{code}</code>\n\n📩 <b>Отправь код админу!</b>", reply_markup=back_button())

@dp.callback_query(F.data.startswith("sell:"))
async def sell_item(cb: CallbackQuery):
    item = await get_item(int(cb.data.split(":")[1]))
    if not item or item[1] != cb.from_user.id: return await cb.answer("❌ Предмет не найден!", show_alert=True)
    if item[6] == 1: return await cb.answer("❌ Нельзя продать выведенный предмет!", show_alert=True)
    await delete_item(item[0])
    await update_balance(cb.from_user.id, item[4])
    await cb.answer(f"✅ Продано: {item[2]} (+{item[4]} монет)", show_alert=True)
    items = await get_inventory(cb.from_user.id)
    if not items: await cb.message.edit_text("🎒 Инвентарь пуст", reply_markup=back_button())
    else: await cb.message.edit_text(f"🎒 <b>Твой инвентарь</b>", reply_markup=inventory_keyboard(items))

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    maint = await get_setting("maintenance") == "True"
    await message.answer("👑 <b>Админ-панель</b>\n\nВыбери действие:", reply_markup=admin_menu(maint))

@dp.callback_query(F.data == "admin_close")
async def admin_close(cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    users, pending = await get_stats()
    maint = await get_setting("maintenance") == "True"
    await cb.message.edit_text(f"📈 <b>Статистика</b>\n\n👥 Пользователей: <b>{users}</b>\n⏳ Купонов на выдачу: <b>{pending}</b>\n🛠 Тех.работы: {'ВКЛ' if maint else 'ВЫКЛ'}", reply_markup=admin_menu(maint))
    await cb.answer()

@dp.callback_query(F.data == "admin_online")
async def admin_online(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    users = await get_online_users(15)
    if not users: text = "Никого нет онлайн за последние 15 минут."
    else:
        text = "🟢 <b>Онлайн (15 мин):</b>\n\n"
        for i, (full_name, username) in enumerate(users[:20]):
            text += f"{i+1}. {full_name} (@{username or 'нет'})\n"
    maint = await get_setting("maintenance") == "True"
    await cb.message.edit_text(text, reply_markup=admin_menu(maint))
    await cb.answer()

@dp.callback_query(F.data == "admin_toggle_maint")
async def admin_toggle_maint(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    current = await get_setting("maintenance") == "True"
    await set_setting("maintenance", str(not current))
    status_text = "ВКЛЮЧЕНЫ" if not current else "ВЫКЛЮЧЕНЫ"
    await cb.answer(f"Тех.работы {status_text}!", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=admin_menu(not current))

@dp.callback_query(F.data == "admin_coupon")
async def admin_coupon_prompt(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminState.waiting_coupon)
    await cb.message.edit_text("🎁 <b>Проверка купона</b>\n\nОтправь код купона:", reply_markup=back_button())
    await cb.answer()

@dp.message(AdminState.waiting_coupon)
async def admin_coupon_check(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    code = message.text.strip().upper()
    info = await get_coupon_info(code)
    await state.clear()
    maint = await get_setting("maintenance") == "True"
    
    if not info:
        return await message.answer("❌ Купон не найден.", reply_markup=admin_menu(maint))
    
    user_id, item_name, username, full_name, status = info
    if status == 'given':
        return await message.answer(f"⚠️ УЖЕ ВЫДАН!\nПользователь: {full_name} (@{username})\nПриз: {item_name}", reply_markup=admin_menu(maint))
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я выдал подарок", callback_data=f"confirm_give:{code}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_close")]
    ])
    await message.answer(f"🔍 <b>Купон:</b>\n👤 {full_name} (@{username})\n🆔 <code>{user_id}</code>\n🎁 {item_name}\n\nВыдал подарок?", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_give:"))
async def admin_confirm_give(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    code = cb.data.split(":")[1]
    await mark_coupon_given(code)
    info = await get_coupon_info(code)
    if info:
        user_id = info[0]
        try: await bot.send_message(user_id, f"🎉 <b>Твой подарок выдан!</b>\nКупон <code>{code}</code> погашен.")
        except: pass
    maint = await get_setting("maintenance") == "True"
    await cb.message.edit_text(f"✅ Купон {code} погашен!", reply_markup=admin_menu(maint))
    await cb.answer("Купон выдан!")

@dp.callback_query(F.data == "admin_promo")
async def admin_promo_prompt(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminState.waiting_promo)
    await cb.message.edit_text("🔑 <b>Создание промокода</b>\n\nОтправь в формате:\n<code>СУММА КОЛИЧЕСТВО_АКТИВАЦИЙ</code>\n\nПример: <code>5000 10</code>", reply_markup=back_button())
    await cb.answer()

@dp.message(AdminState.waiting_promo)
async def admin_promo_create(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        parts = message.text.split()
        reward = int(parts[0])
        uses = int(parts[1])
        code = generate_code(8)
        await create_promo(code, reward, uses)
        await state.clear()
        maint = await get_setting("maintenance") == "True"
        await message.answer(f"✅ <b>Промокод создан!</b>\n\nКод: <code>{code}</code>\nНаграда: {reward} монет\nАктиваций: {uses}", reply_markup=admin_menu(maint))
    except:
        await message.answer("❌ Ошибка. Формат: <code>5000 10</code>")

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_prompt(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminState.waiting_broadcast)
    await cb.message.edit_text("📢 <b>Рассылка</b>\n\nОтправь текст для всех пользователей:", reply_markup=back_button())
    await cb.answer()

@dp.message(AdminState.waiting_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    users = await get_all_users()
    await state.clear()
    await message.answer(f"⏳ Рассылка для {len(users)}...")
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, message.text)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    maint = await get_setting("maintenance") == "True"
    await message.answer(f"✅ Доставлено: {success} из {len(users)}", reply_markup=admin_menu(maint))

# --- УПРАВЛЕНИЕ КАНАЛОМ ---
@dp.callback_query(F.data == "admin_channel_post")
async def admin_channel_post_prompt(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    await state.set_state(AdminState.waiting_channel_post)
    await cb.message.edit_text("📝 <b>Пост в канал</b>\n\nОтправь текст поста:", reply_markup=back_button())
    await cb.answer()

@dp.message(AdminState.waiting_channel_post)
async def admin_channel_post_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
    maint = await get_setting("maintenance") == "True"
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message.text)
        await message.answer("✅ Пост успешно опубликован в канале!", reply_markup=admin_menu(maint))
    except Exception as e:
        await message.answer(f"❌ Ошибка!\nУбедись, что бот админ в канале.\n<code>{e}</code>", reply_markup=admin_menu(maint))

@dp.callback_query(F.data == "admin_channel_stats")
async def admin_channel_stats(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    maint = await get_setting("maintenance") == "True"
    try:
        chat = await bot.get_chat(chat_id=CHANNEL_ID)
        count = await bot.get_chat_member_count(chat_id=CHANNEL_ID)
        await cb.message.edit_text(f"📊 <b>Статистика канала</b>\n\nНазвание: <b>{chat.title}</b>\n👥 Подписчиков: <b>{count}</b>", reply_markup=admin_menu(maint))
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка!\nБот должен быть админом в канале.\n<code>{e}</code>", reply_markup=admin_menu(maint))
    await cb.answer()

async def main():
    await init_db()
    for code, reward, uses in DEFAULT_PROMOS: 
        await create_promo(code, reward, uses)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
