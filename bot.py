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
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, balance INTEGER DEFAULT 1000, coins INTEGER DEFAULT 0, referrer_id INTEGER, referrals INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, rarity TEXT, value INTEGER, is_withdrawn INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, user_id INTEGER, item_name TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, rank INTEGER DEFAULT 1)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS hr_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, details TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY, reason TEXT)")
        
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

# ================= КЕЙСЫ =================
CASES = {
    "poor": {"name": "🥺 Нищий", "price": 15, "coin_price": 5, "mon_price": 15000, "items": [("2 звезды", "common", 2, 70, "50%"), ("5 звезд", "rare", 5, 25, "30%"), ("20 звезд", "epic", 20, 5, "15%"), ("💎 Алмаз", "legendary", 500, 3, "4%"), ("🚀 Ракета", "legendary", 1000, 1.5, "0.8%"), ("🏆 Кубок", "mythic", 5000, 0.5, "0.2%")]},
    "rich": {"name": "👑 Богатый", "price": 100, "coin_price": 30, "mon_price": 100000, "items": [("10 звезд", "common", 10, 60, "50%"), ("50 звезд", "rare", 50, 30, "40%"), ("NFT Кубок", "epic", 500, 9, "9%"), ("👑 Корона", "legendary", 2500, 1, "1%")]},
    "nft": {"name": "💎 NFT Кейс", "price": 700, "coin_price": 250, "mon_price": 1000000, "items": [("25 звезд", "common", 25, 60, "60%"), ("50 звезд", "rare", 50, 25, "25%"), ("Сердечко", "epic", 200, 10, "10%"), ("🚀 Ракета", "legendary", 1000, 4, "4%"), ("👑 ТОП NFT", "mythic", 5000, 1, "1%")]}
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
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 КЕЙСЫ", callback_data="cases"), InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games")],
        [InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="⭐ КУПИТЬ STARS", callback_data="buy_stars")],
        [InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inv"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="prof")],
        [InlineKeyboardButton(text="🏆 ТОП ИГРОКОВ", callback_data="top_players"), InlineKeyboardButton(text="🔑 ПРОМОКОД", callback_data="promo")],
        [InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="ref"), InlineKeyboardButton(text="ℹ️ О БОТЕ", callback_data="about")]
    ])

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
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Выбери действие ниже 👇"
    )
    await message.answer(text, reply_markup=main_menu())

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
    await cb.message.edit_text(text, reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data == "about")
async def about_bot(cb: CallbackQuery):
    text = (
        f"ℹ️ <b>О БОТЕ CASEHAB</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Лучший бот для открытия кейсов!\n\n"
        f"📩 <b>Поддержка:</b> {CONTACT_ADMIN}"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "prof")
async def prof(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    text = (
        f"👤 <b>ПРОФИЛЬ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{user[0]}</code>\n"
        f"💰 <b>Монеты:</b> {user[3]}\n"
        f"💎 <b>Коэны:</b> {user[4]}\n"
        f"👥 <b>Рефералы:</b> {user[6]}/3\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "ref")
async def ref(cb: CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
    text = (
        f"👥 <b>РЕФЕРАЛЫ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Пригласи 3 друзей и получи доступ к выводу!\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "top_players")
async def top_players(cb: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name, balance FROM users ORDER BY balance DESC LIMIT 5") as cur:
            tops = await cur.fetchall()
    text = "🏆 <b>ТОП 5 ИГРОКОВ</b>\n━━━━━━━━━━━━━━━━━━\n"
    for i, (name, bal) in enumerate(tops, 1): 
        text += f"{i}. <b>{name}</b> — {bal} 💰\n"
    text += "━━━━━━━━━━━━━━━━━━"
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "shop")
async def shop_menu(cb: CallbackQuery):
    price = await get_setting("shop_price")
    text = (
        f"🛒 <b>МАГАЗИН</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Обмен Монет на Коэны.\n\n"
        f"💱 <b>Курс:</b> {price} Монет = 10 Коэнов\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"(В разработке)"
    )
    await cb.message.edit_text(text, reply_markup=back_btn())
    await cb.answer()

# --- КЕЙСЫ ---
@dp.callback_query(F.data == "cases")
async def cases_menu(cb: CallbackQuery):
    kb = []
    for k, c in CASES.items(): kb.append([InlineKeyboardButton(text=f"{c['name']}", callback_data=f"view_{k}")])
    kb.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_main")])
    text = "🎁 <b>ВЫБЕРИ КЕЙС</b>\n━━━━━━━━━━━━━━━━━━"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
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
    
    text = f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐\n━━━━━━━━━━━━━━━━━━"
    await msg.edit_text(text, reply_markup=back_btn("cases"))
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
    
    text = f"🎉 <b>ПОБЕДА!</b>\n━━━━━━━━━━━━━━━━━━\nВы выиграли: <b>{name}</b>\n💰 Стоимость: {val}⭐\n━━━━━━━━━━━━━━━━━━"
    await msg.edit_text(text, reply_markup=back_btn("cases"))
    await cb.answer("Поздравляем!")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_pay(message: Message):
    key = message.successful_payment.invoice_payload.split("_")[1]
    msg = await message.answer("<b>🎰 ОПЛАТА ПРОШЛА...</b>")
    name, rarity, val, w, fake = open_case(key)
    await add_item(message.from_user.id, name, rarity, val)
    await msg.edit_text(f"🎉 Вы выиграли: <b>{name}</b>", reply_markup=main_menu())

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
        kb.append([InlineKeyboardButton(text=f"💸 ПРОДАТЬ {name} ({val})", callback_data=f"sell_{i}")])
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
        await message.answer(f"🎉 <b>ПОБЕДА!</b>\nТы выиграл <b>{bet}</b> монет.", reply_markup=main_menu())
    else:
        await upd_bal(message.from_user.id, -bet)
        await message.answer(f"😢 <b>ПРОИГРЫШ.</b>\nТы потерял <b>{bet}</b> монет.", reply_markup=main_menu())

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
        if not promo or promo[1] <= 0: return await message.answer("❌ НЕВЕРНЫЙ ИЛИ ИСПОЛЬЗОВАННЫЙ ПРОМОКОД.", reply_markup=main_menu())
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[0], message.from_user.id))
        await db.commit()
    await message.answer(f"✅ <b>АКТИВИРОВАН!</b>\nПолучено <b>{promo[0]}</b> монет.", reply_markup=main_menu())

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
    try: await bot.send_message(target_id, f"👑 Администратор {action_text.lower()} вам {amount} {curr_text}.")
    except: pass

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
