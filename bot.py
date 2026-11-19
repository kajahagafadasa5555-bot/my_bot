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

BOT_TOKEN = os.environ.get("9190963992:AAFB5GiGVksUKSvcQopsLxjnzWjpqpgALBs", "9190963992:AAFB5GiGVksUKSvcQopsLxjnzWjpqpgALBs")
ADMIN_IDS = [8400799305]
CHANNEL_ID = "@casehab"
CHANNEL_LINK = "https://t.me/casehab"
CONTACT_ADMIN = "@drag_monster_zl"
DB_PATH = "bot.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class UserState(StatesGroup):
    waiting_promo = State()
    waiting_bet = State()

class AdminState(StatesGroup):
    waiting_coupon = State()
    waiting_promo_amount = State()
    waiting_promo_uses = State()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, balance INTEGER DEFAULT 1000, coins INTEGER DEFAULT 0, referrer_id INTEGER, referrals INTEGER DEFAULT 0, last_seen TEXT DEFAULT '')")
        await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, rarity TEXT, value INTEGER, is_withdrawn INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, user_id INTEGER, item_name TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, rank INTEGER DEFAULT 1)")
        await db.execute("CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")
        
        await db.execute("INSERT OR IGNORE INTO admins (user_id, rank) VALUES (?, 3)", (ADMIN_IDS[0],))
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'False')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('panic', 'False')")
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
                await db.execute("UPDATE users SET username = ?, full_name = ?, last_seen = ? WHERE user_id = ?", (username, full_name, datetime.datetime.now().isoformat(), user_id))
            await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

async def upd_bal(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def add_item(user_id, name, rarity, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO inventory (user_id, item_name, rarity, value) VALUES (?, ?, ?, ?)", (user_id, name, rarity, value))
        await db.commit()

CASES = {
    "poor": {"name": "🥺 Нищий", "price": 15, "items": [("2 звезды", "common", 2, 70), ("5 звезд", "rare", 5, 25), ("20 звезд", "epic", 20, 5)]},
    "rich": {"name": "👑 Богатый", "price": 100, "items": [("10 звезд", "common", 10, 60), ("50 звезд", "rare", 50, 30), ("NFT", "epic", 500, 10)]}
}

def open_case(key):
    items = CASES[key]["items"]
    if asyncio.run(get_setting("panic")) == "True":
        items = [i for i in items if i[2] <= 50]
    weights = [i[3] for i in items]
    return random.choices(items, weights=weights, k=1)[0]

# --- КЛАВИАТУРЫ ---
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases"), InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inv"), InlineKeyboardButton(text="👤 Профиль", callback_data="prof")],
        [InlineKeyboardButton(text="🔑 Промокод", callback_data="promo")]
    ])

def back_btn():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Купон", callback_data="admin_coupon")],
        [InlineKeyboardButton(text="🚨 Паника", callback_data="admin_panic")],
        [InlineKeyboardButton(text="🛠 Тех.работы", callback_data="admin_maint")],
        [InlineKeyboardButton(text="Закрыть", callback_data="close_admin")]
    ])# --- ХЭНДЛЕРЫ ---
@dp.message()
async def check_status(message: Message):
    if await get_admin_rank(message.from_user.id) > 0: return
    if await get_setting("maintenance") == "True":
        return await message.answer("🛠 На боте тех.работы.")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    u = message.from_user
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if ref_id == u.id: ref_id = None
    
    await add_user(u.id, u.username or "", u.full_name, ref_id)
    user = await get_user(u.id)
    
    if user is None:
        await add_user(u.id, u.username or "", u.full_name, ref_id)
        user = await get_user(u.id)
        
    await message.answer(f"👋 <b>Привет, {u.full_name}!</b>\n\n💰 Баланс: <b>{user[3]}</b>\n💎 Коэны: <b>{user[4]}</b>", reply_markup=main_menu())

@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery):
    await cb.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data == "prof")
async def prof(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    await cb.message.edit_text(f"👤 Профиль\n\n💰 Баланс: {user[3]}\n💎 Коэны: {user[4]}\n👥 Рефералы: {user[6]}/3", reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "cases")
async def cases_menu(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{CASES['poor']['name']} ({CASES['poor']['price']}⭐)", callback_data="open_poor")],
        [InlineKeyboardButton(text=f"{CASES['rich']['name']} ({CASES['rich']['price']}⭐)", callback_data="open_rich")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await cb.message.edit_text("🎁 Выберите кейс:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("open_"))
async def open_c(cb: CallbackQuery):
    key = cb.data.replace("open_", "")
    case = CASES[key]
    prices = [LabeledPrice(label=case["name"], amount=case["price"])]
    await bot.send_invoice(chat_id=cb.from_user.id, title=case["name"], description="Открыть кейс?", payload=f"case_{key}", provider_token="", currency="XTR", prices=prices)
    await cb.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_pay(message: Message):
    key = message.successful_payment.invoice_payload.split("_")[1]
    name, rarity, val, w = open_case(key)
    await add_item(message.from_user.id, name, rarity, val)
    await message.answer(f"🎉 Вы выиграли: <b>{name}</b>", reply_markup=main_menu())

@dp.callback_query(F.data == "inv")
async def inv(cb: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, item_name, value FROM inventory WHERE user_id = ? AND is_withdrawn = 0", (cb.from_user.id,)) as cur:
            items = await cur.fetchall()
    if not items: return await cb.message.edit_text("🎒 Инвентарь пуст", reply_markup=back_btn())
    kb = []
    for i, name, val in items:
        kb.append([InlineKeyboardButton(text=f"💸 Продать {name} ({val})", callback_data=f"sell_{i}")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    await cb.message.edit_text("🎒 Ваши предметы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
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
    await cb.answer(f"✅ Продано за {val} монет!", show_alert=True)
    await inv(cb)

@dp.callback_query(F.data == "games")
async def games(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Апгрейд x2 (50%)", callback_data="game_up")],
        [InlineKeyboardButton(text="🪙 Монетка (50%)", callback_data="game_coin")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await cb.message.edit_text("🎮 Игры:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("game_"))
async def game_bet(cb: CallbackQuery, state: FSMContext):
    await state.update_data(game=cb.data)
    await cb.message.edit_text("Введите сумму ставки:", reply_markup=back_btn())
    await state.set_state(UserState.waiting_bet)
    await cb.answer()

@dp.message(UserState.waiting_bet)
async def play_game(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    bet = int(message.text)
    user = await get_user(message.from_user.id)
    if user[3] < bet: return await message.answer("❌ Недостаточно монет!")
    
    data = await state.get_data()
    await state.clear()
    
    win = random.random() < 0.5 # Шанс 50%
    if win:
        await upd_bal(message.from_user.id, bet)
        await message.answer(f"🎉 Победа! Вы выиграли {bet} монет.", reply_markup=main_menu())
    else:
        await upd_bal(message.from_user.id, -bet)
        await message.answer(f"😢 Проигрыш. Вы потеряли {bet} монет.", reply_markup=main_menu())

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if await get_admin_rank(message.from_user.id) == 0: return
    await message.answer("👑 Админка:", reply_markup=admin_menu())

@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()

@dp.callback_query(F.data == "admin_panic")
async def admin_panic(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cur = await get_setting("panic") == "True"
    await set_setting("panic", str(not cur))
    await cb.answer(f"Паника: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)

@dp.callback_query(F.data == "admin_maint")
async def admin_maint(cb: CallbackQuery):
    if await get_admin_rank(cb.from_user.id) != 3: return
    cur = await get_setting("maintenance") == "True"
    await set_setting("maintenance", str(not cur))
    await cb.answer(f"Тех.работы: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)

# --- ЗАПУСК ---
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
