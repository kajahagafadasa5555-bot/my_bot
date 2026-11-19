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
BOT_TOKEN = "9190963992:AAFB5GiGVksUKSvcQopsLxjnzWjpqpgALBs" # ЗАМЕНИТЕ!
ADMIN_IDS = [8400799305]
CHANNEL_ID = "@casehab"
CHANNEL_LINK = "https://t.me/casehab"
CONTACT_ADMIN = "@drag_monster_zl"
DB_PATH = "bot.db"

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, balance INTEGER DEFAULT 1000, coins INTEGER DEFAULT 0, last_bonus TEXT DEFAULT '', joined_at TEXT, referrer_id INTEGER, referrals INTEGER DEFAULT 0, last_seen TEXT DEFAULT '')")
        await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, rarity TEXT, value INTEGER, obtained_at TEXT, is_withdrawn INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, user_id INTEGER, item_name TEXT, item_id INTEGER, created_at TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, rank INTEGER DEFAULT 1)") 
        await db.execute("CREATE TABLE IF NOT EXISTS hr_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, details TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, reward_type TEXT, amount INTEGER, uses_left INTEGER, created_at TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_used (user_id INTEGER, code TEXT)")
        
        # Дефолтные настройки
        await db.execute("INSERT OR IGNORE INTO admins (user_id, rank) VALUES (?, 3)", (ADMIN_IDS[0],))
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('maintenance', 'False')")
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('panic_mode', 'False')")
        
        # Настройки шансов
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('bj_win_chance', '20')")
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('bj_big_bet', '100')")
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('wheel_x0', '50')")
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('wheel_x05', '30')")
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('wheel_x2', '15')")
        await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('wheel_x10', '5')")
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

async def get_admin_rank(user_id):
    if user_id in ADMIN_IDS: return 3
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT rank FROM admins WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

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

async def update_balance(user_id, amount, currency="balance"):
    async with aiosqlite.connect(DB_PATH) as db:
        if currency == "balance": await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        else: await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

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

def generate_code(length=8): return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ================= КЕЙСЫ =================
CASES = {
    "poor": {"name": "🥺 Нищий кейс", "price_stars": 15, "price_coins": 5, "display_chance": "20% на большой выигрыш", "items": [("Подарок 2 звезды", "common", 2, 40), ("Подарок 3 звезды", "common", 3, 30), ("Подарок 5 звезд", "rare", 5, 29), ("Подарок 20 звезд", "epic", 20, 1)]},
    "medium": {"name": "🐻 Средний кейс", "price_stars": 50, "price_coins": 15, "display_chance": "Шанс на Алмаз 20%", "items": [("🐻 Мишка", "common", 20, 40), ("🌹 Роза", "common", 25, 40), ("💎 Алмаз", "epic", 100, 20)]},
    "rich": {"name": "👑 Богатый кейс", "price_stars": 1000, "price_coins": 300, "display_chance": "Шанс на NFT и Кубок", "items": [("🎁 Дешевый NFT", "rare", 150, 50), ("🏆 Кубок", "epic", 300, 30), ("💖 Сердечко", "epic", 400, 15), ("💎 Алмаз", "legendary", 500, 5)]}
}
RARITY_EMOJI = {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}

def open_case(case_key):
    items = CASES[case_key]["items"]
    if asyncio.run(get_setting("panic_mode")) == "True":
        items = [i for i in items if i[2] <= 50]
        if not items: items = CASES[case_key]["items"]
    weights = [i[3] for i in items]
    return random.choices(items, weights=weights, k=1)[0]

# ================= МАТЕМАТИКА =================
def play_upgrade(): return random.random() < 0.5
def play_coin(): return random.choice([True, False])
def play_blackjack(bet_amount, currency_type):
    win_chance = int(asyncio.run(get_setting("bj_win_chance"))) / 100.0
    big_bet = int(asyncio.run(get_setting("bj_big_bet")))
    if currency_type in ["stars", "coins"] and bet_amount >= big_bet: return False
    return random.random() < win_chance
def play_wheel():
    x0 = int(asyncio.run(get_setting("wheel_x0")))
    x05 = int(asyncio.run(get_setting("wheel_x05")))
    x2 = int(asyncio.run(get_setting("wheel_x2")))
    x10 = int(asyncio.run(get_setting("wheel_x10")))
    total = x0 + x05 + x2 + x10
    roll = random.randint(1, total)
    if roll <= x0: return 0
    elif roll <= x0 + x05: return 0.5
    elif roll <= x0 + x05 + x2: return 2
    else: return 10

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
# ================= СОСТОЯНИЯ (FSM) =================
class AdminState(StatesGroup):
    waiting_coupon = State(); waiting_broadcast = State(); waiting_channel_post = State()
    waiting_staff_id = State(); waiting_staff_rank = State(); waiting_staff_action = State()
    waiting_give_id = State(); waiting_give_amount = State()
    waiting_promo_amount = State(); waiting_promo_uses = State()
    waiting_bj_chance = State(); waiting_bj_bigbet = State()
    waiting_wheel_settings = State()
    waiting_case_name = State(); waiting_case_price = State()

class UserState(StatesGroup):
    waiting_promo = State(); waiting_bet = State(); waiting_game = State()

# ================= КЛАВИАТУРЫ =================
def check_sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ])

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases_menu"), InlineKeyboardButton(text="🎮 Игры", callback_data="games_menu")],
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"), InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Друзья", callback_data="ref_menu")],
        [InlineKeyboardButton(text="🔑 Промокод", callback_data="promo_prompt")],
    ])

def back_button(cb="back_main"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=cb)]])

def games_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Апгрейд (x2)", callback_data="game_upgrade"), InlineKeyboardButton(text="🪙 Монетка", callback_data="game_coin")],
        [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game_bj"), InlineKeyboardButton(text="🎡 Колесо", callback_data="game_wheel")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])

def cases_menu():
    buttons = []
    for k, c in CASES.items():
        buttons.append([InlineKeyboardButton(text=f"{c['name']} | {c['price_stars']} ⭐", callback_data=f"open_stars:{k}")])
        buttons.append([InlineKeyboardButton(text=f"{c['name']} | {c['price_coins']} 💎", callback_data=f"open_coins:{k}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= ПРОВЕРКА ПОДПИСКИ (ИСПРАВЛЕНО) =================
@dp.message()
async def check_user_status(message: Message):
    # ВАШ ID (И ДРУГИЕ АДМИНЫ) ПРОПУСКАЮТСЯ ВСЕГДА
    if await get_admin_rank(message.from_user.id) > 0: return 
    
    if await get_setting("maintenance") == "True":
        return await message.answer("🛠 <b>Технические работы!</b>")
    
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=message.from_user.id)
        if member.status not in ["member", "administrator", "creator"]:
            return await message.answer("⚠️ <b>Подпишись на канал!</b>", reply_markup=check_sub_kb())
    except: pass 

# ================= ПОЛЬЗОВАТЕЛЬСКИЕ ХЭНДЛЕРЫ =================
@dp.message(CommandStart())
async def start_cmd(message: Message):
    u = message.from_user
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if referrer_id == u.id: referrer_id = None
    await add_user(u.id, u.username or "", u.full_name, referrer_id)
    user = await get_user(u.id)

# ВСТАВИТЬ ЭТИ 3 СТРОКИ:
if user is None:
    await add_user(u.id, u.username or "", u.full_name, referrer_id)
    user = await get_user(u.id)

# Теперь user точно есть, и код ниже 
    await message.answer(f"👋 <b>Привет, {u.full_name}!</b>\n\n💰 Монеты: <b>{user[3]}</b>\n💎 Коэны: <b>{user[4]}</b>\n\nВыбери действие 👇", reply_markup=main_menu())

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    await cb.message.edit_text(f"🏠 <b>Главное меню</b>\n\n💰 Монеты: <b>{user[3]}</b>\n💎 Коэны: <b>{user[4]}</b>", reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=cb.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            await cb.message.edit_text("✅ Спасибо за подписку!", reply_markup=main_menu())
        else: await cb.answer("❌ Ты еще не подписался!", show_alert=True)
    except: await cb.answer("⚠️ Ошибка проверки.", show_alert=True)

@dp.callback_query(F.data == "ref_menu")
async def ref_menu(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
    await cb.message.edit_text(f"👥 <b>Пригласи друзей!</b>\n\nПриглашено: <b>{user[7]}/3</b> (нужно для вывода).\n\n🔗 Твоя ссылка:\n<code>{ref_link}</code>", reply_markup=back_button())
    await cb.answer()

# ================= КЕЙСЫ =================
@dp.callback_query(F.data == "cases_menu")
async def show_cases(cb: CallbackQuery):
    await cb.message.edit_text("🎁 <b>Выбери кейс и валюту:</b>", reply_markup=cases_menu())
    await cb.answer()

@dp.callback_query(F.data.startswith("open_stars:"))
async def handle_open_stars(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    case = CASES[key]
    prices = [LabeledPrice(label=case["name"], amount=case["price_stars"])]
    await bot.send_invoice(chat_id=cb.from_user.id, title=case["name"], description=f"Открой кейс! {case['display_chance']}", payload=f"case_{key}_{cb.from_user.id}", provider_token="", currency="XTR", prices=prices)
    await cb.answer()

@dp.callback_query(F.data.startswith("open_coins:"))
async def handle_open_coins(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    case = CASES[key]
    user = await get_user(cb.from_user.id)
    if user[4] < case["price_coins"]:
        return await cb.answer("❌ Недостаточно Коэнов!", show_alert=True)
    
    await update_balance(cb.from_user.id, -case["price_coins"], "coins")
    name, rarity, value, weight = open_case(key)
    await add_item(cb.from_user.id, name, rarity, value)
    await cb.message.edit_text(f"🎉 <b>Оплачено Коэнами!</b>\n\n{RARITY_EMOJI[rarity]} Выпало: <b>{name}</b>\n💵 Цена: {value} ⭐", reply_markup=back_button("cases_menu"))
    await cb.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    case_key = parts[1]
    user_id = int(parts[2])
    name, rarity, value, weight = open_case(case_key)
    await add_item(user_id, name, rarity, value)
    await message.answer(f"🎉 <b>Оплата прошла!</b>\n\n{RARITY_EMOJI[rarity]} Тебе выпало: <b>{name}</b>\n⭐ Стоимость: <b>{value}</b> Stars", reply_markup=main_menu())

# ================= ИНВЕНТАРЬ И ВЫВОД =================
@dp.callback_query(F.data == "inventory")
async def show_inventory(cb: CallbackQuery):
    items = await get_inventory(cb.from_user.id)
    if not items: return await cb.message.edit_text("🎒 <b>Инвентарь пуст</b>", reply_markup=back_button())
    
    buttons = []
    for i, name, rarity, value, withdrawn in items:
        if withdrawn: buttons.append([InlineKeyboardButton(text=f"✅ {name} (Выведен)", callback_data="noop")])
        else: buttons.append([InlineKeyboardButton(text=f"💸 Продать {name} ({value})", callback_data=f"sell:{i}"), InlineKeyboardButton(text=f"📦 Вывести", callback_data=f"withdraw:{i}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    await cb.message.edit_text("🎒 <b>Твой инвентарь</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@dp.callback_query(F.data.startswith("sell:"))
async def sell_item(cb: CallbackQuery):
    item = await get_item(int(cb.data.split(":")[1]))
    if not item or item[1] != cb.from_user.id or item[6] == 1: return await cb.answer("❌ Ошибка!", show_alert=True)
    await delete_item(item[0])
    await update_balance(cb.from_user.id, item[4], "balance")
    await cb.answer(f"✅ Продано: +{item[4]} монет", show_alert=True)
    await show_inventory(cb)

@dp.callback_query(F.data.startswith("withdraw:"))
async def withdraw_item(cb: CallbackQuery):
    item = await get_item(int(cb.data.split(":")[1]))
    user = await get_user(cb.from_user.id)
    if not item or item[1] != cb.from_user.id or item[6] == 1: return await cb.answer("❌ Ошибка!", show_alert=True)
    if user[7] < 3: return await cb.answer(f"❌ Нужно 3 друга!\nУ тебя: {user[7]}/3", show_alert=True)
    
    code = await generate_coupon(cb.from_user.id, item[0], item[2])
    await cb.message.edit_text(f"🎉 <b>Купон создан!</b>\n\nПредмет: <b>{item[2]}</b>\nКод: <code>{code}</code>\n\n📩 <b>Напиши {CONTACT_ADMIN} и отправь код!</b>", reply_markup=back_button())
    await cb.answer(f"Купон: {code}", show_alert=True)
    # ================= ИГРЫ =================
@dp.callback_query(F.data == "games_menu")
async def show_games(cb: CallbackQuery):
    await cb.message.edit_text("🎮 <b>Выбери игру:</b>", reply_markup=games_menu())
    await cb.answer()

@dp.callback_query(F.data.startswith("game_"))
async def game_selected(cb: CallbackQuery, state: FSMContext):
    game = cb.data.replace("game_", "")
    await state.update_data(game=game)
    await cb.message.edit_text(f"🎮 Введи сумму ставки (Монеты):", reply_markup=back_button("games_menu"))
    await state.set_state(UserState.waiting_bet)
    await cb.answer()

@dp.message(UserState.waiting_bet)
async def process_bet(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введи число!")
    bet = int(message.text)
    user = await get_user(message.from_user.id)
    if user[3] < bet: return await message.answer("❌ Недостаточно монет!")
    
    data = await state.get_data()
    game = data.get("game")
    await state.clear()
    
    if game == "upgrade":
        win = play_upgrade()
    elif game == "coin":
        win = play_coin()
    elif game == "bj":
        win = play_blackjack(bet, "balance")
    elif game == "wheel":
        multiplier = play_wheel()
        if multiplier > 0:
            await update_balance(message.from_user.id, int(bet * multiplier) - bet)
            return await message.answer(f"🎡 Выпало x{multiplier}!\n💰 Выигрыш: +{int(bet*multiplier)} монет", reply_markup=main_menu())
        else:
            await update_balance(message.from_user.id, -bet)
            return await message.answer(f"😢 Колесо остановилось на x0. Ты проиграл.", reply_markup=main_menu())
            
    if win:
        await update_balance(message.from_user.id, bet)
        await message.answer(f"🎉 <b>Победа!</b> Ты выиграл {bet} монет.", reply_markup=main_menu())
    else:
        await update_balance(message.from_user.id, -bet)
        await message.answer(f"😢 <b>Проигрыш.</b> Ты потерял {bet} монет.", reply_markup=main_menu())

# ================= ПРОМОКОДЫ =================
@dp.callback_query(F.data == "promo_prompt")
async def promo_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔑 Введи промокод:", reply_markup=back_button())
    await state.set_state(UserState.waiting_promo)
    await cb.answer()

@dp.message(UserState.waiting_promo)
async def check_promo(message: Message, state: FSMContext):
    code = message.text.upper().strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT reward_type, amount, uses_left FROM promo_codes WHERE code=?", (code,)) as cur: promo = await cur.fetchone()
        if not promo: return await message.answer("❌ Промокод не найден.")
        if promo[2] <= 0: return await message.answer("❌ Промокод использован.")
        async with db.execute("SELECT 1 FROM promo_used WHERE user_id=? AND code=?", (message.from_user.id, code)) as cur:
            if await cur.fetchone(): return await message.answer("❌ Ты уже использовал этот промокод.")
        
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code=?", (code,))
        await db.execute("INSERT INTO promo_used (user_id, code) VALUES (?, ?)", (message.from_user.id, code))
        if promo[0] == "balance": await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (promo[1], message.from_user.id))
        elif promo[0] == "coins": await db.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (promo[1], message.from_user.id))
        await db.commit()
    await message.answer(f"✅ Активирован! Получено: {promo[1]} {promo[0]}.", reply_markup=main_menu())
    await state.clear()

# ================= АДМИН-ПАНЕЛЬ =================
def admin_menu(rank, maint, panic):
    maint_text = "🟢 Вкл тех.работы" if not maint else "🔴 Выкл тех.работы"
    panic_text = "🚨 ВКЛ ПАНИКУ" if not panic else "✅ ВЫКЛ ПАНИКУ"
    kb = []
    if rank >= 2:
        kb.extend([
            [InlineKeyboardButton(text="📊 Стата", callback_data="admin_stats"), InlineKeyboardButton(text="🟢 Онлайн", callback_data="admin_online")],
            [InlineKeyboardButton(text="🎁 Купон", callback_data="admin_coupon")],
            [InlineKeyboardButton(text="🔑 Промо", callback_data="admin_promo")]
        ])
    if rank == 3:
        kb.extend([
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"), InlineKeyboardButton(text="📝 Пост", callback_data="admin_channel_post")],
            [InlineKeyboardButton(text=maint_text, callback_data="admin_toggle_maint")],
            [InlineKeyboardButton(text=panic_text, callback_data="admin_toggle_panic")],
            [InlineKeyboardButton(text="⚙️ Шансы игр", callback_data="admin_odds")],
            [InlineKeyboardButton(text="👥 Персонал", callback_data="admin_staff")]
        ])
    kb.append([InlineKeyboardButton(text="◀️ Закрыть", callback_data="admin_close")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    rank = await get_admin_rank(message.from_user.id)
    if rank == 0: return
    maint = await get_setting("maintenance") == "True"
    panic = await get_setting("panic_mode") == "True"
    await message.answer("👑 <b>Админ-панель</b>", reply_markup=admin_menu(rank, maint, panic))

@dp.callback_query(F.data == "admin_close")
async def admin_close(cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()

@dp.callback_query(F.data == "admin_toggle_maint")
async def admin_toggle_maint(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    current = await get_setting("maintenance") == "True"
    await set_setting("maintenance", str(not current))
    maint = await get_setting("maintenance") == "True"
    await cb.message.edit_reply_markup(reply_markup=admin_menu(3, maint, await get_setting("panic_mode") == "True"))
    await cb.answer("Тех.работы переключены!")

@dp.callback_query(F.data == "admin_toggle_panic")
async def admin_toggle_panic(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    current = await get_setting("panic_mode") == "True"
    await set_setting("panic_mode", str(not current))
    maint = await get_setting("maintenance") == "True"
    await cb.message.edit_reply_markup(reply_markup=admin_menu(3, maint, not current))
    await cb.answer("Паника переключена!")

# --- НАСТРОЙКА ШАНСОВ ИГР ---
@dp.callback_query(F.data == "admin_odds")
async def admin_odds(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    bj_chance = await get_setting("bj_win_chance")
    bj_bigbet = await get_setting("bj_big_bet")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🃏 Шанс БД: {bj_chance}%", callback_data="set_bj_chance")],
        [InlineKeyboardButton(text=f"💎 Порог БД: {bj_bigbet}", callback_data="set_bj_bigbet")],
        [InlineKeyboardButton(text="🎡 Шансы Колеса", callback_data="set_wheel")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_close")]
    ])
    await cb.message.edit_text("⚙️ <b>Настройка шансов</b>", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "set_bj_chance")
async def set_bj_chance_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Введите шанс Блэкджека (%):", reply_markup=back_button("admin_odds"))
    await state.set_state(AdminState.waiting_bj_chance)
    await cb.answer()

@dp.message(AdminState.waiting_bj_chance)
async def set_bj_chance_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await set_setting("bj_win_chance", message.text)
    await message.answer(f"✅ Шанс БД: {message.text}%", reply_markup=back_button("admin_odds"))
    await state.clear()

@dp.callback_query(F.data == "set_bj_bigbet")
async def set_bj_bigbet_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Введите порог крупной ставки:", reply_markup=back_button("admin_odds"))
    await state.set_state(AdminState.waiting_bj_bigbet)
    await cb.answer()

@dp.message(AdminState.waiting_bj_bigbet)
async def set_bj_bigbet_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    await set_setting("bj_big_bet", message.text)
    await message.answer(f"✅ Порог: {message.text}", reply_markup=back_button("admin_odds"))
    await state.clear()

@dp.callback_query(F.data == "set_wheel")
async def set_wheel_prompt(cb: CallbackQuery, state: FSMContext):
    w0, w05, w2, w10 = [await get_setting(f"wheel_x{i}") for i in ["0", "05", "2", "10"]]
    text = f"Текущие: x0={w0}%, x0.5={w05}%, x2={w2}%, x10={w10}%\n\nВведите 4 числа через пробел (в сумме 100):"
    await cb.message.edit_text(text, reply_markup=back_button("admin_odds"))
    await state.set_state(AdminState.waiting_wheel_settings)
    await cb.answer()

@dp.message(AdminState.waiting_wheel_settings)
async def set_wheel_save(message: Message, state: FSMContext):
    try:
        parts = list(map(int, message.text.split()))
        if len(parts) != 4 or sum(parts) != 100: return await message.answer("Ошибка! 4 числа, сумма = 100.")
        for i, val in zip(["0", "05", "2", "10"], parts):
            await set_setting(f"wheel_x{i}", val)
        await message.answer("✅ Шансы Колеса обновлены!", reply_markup=back_button("admin_odds"))
        await state.clear()
    except: await message.answer("Ошибка.")

# --- ПРОВЕРКА КУПОНОВ ---
@dp.callback_query(F.data == "admin_coupon")
async def admin_coupon(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) < 2: return
    await cb.message.edit_text("🎁 Отправь код купона:", reply_markup=back_button())
    await state.set_state(AdminState.waiting_coupon)
    await cb.answer()

@dp.message(AdminState.waiting_coupon)
async def admin_coupon_check(message: Message, state: FSMContext):
    if await get_admin_rank(message.from_user.id) < 2: return
    info = await get_coupon_info(message.text.strip())
    await state.clear()
    if not info: return await message.answer("❌ Купон не найден.")
    uid, item, username, full_name, status = info
    if status == 'given': return await message.answer("⚠️ УЖЕ ВЫДАН!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я выдал подарок", callback_data=f"confirm_give:{message.text.strip()}")]])
    await message.answer(f"🔍 <b>Купон:</b>\n👤 {full_name} (@{username})\n🎁 {item}\n\nВыдал?", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_give:"))
async def admin_confirm_give(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) < 2: return
    code = cb.data.split(":")[1]
    await mark_coupon_given(code)
    info = await get_coupon_info(code)
    if info:
        try: await bot.send_message(info[0], f"🎉 <b>Твой подарок выдан!</b>")
        except: pass
    await cb.message.edit_text(f"✅ Купон {code} погашен!")
    await cb.answer()

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
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
