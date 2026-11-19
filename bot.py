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
        await db.execute("CREATE TABLE IF NOT EXISTS pending_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, target_id INTEGER, amount INTEGER, req_type TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS hr_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, details TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY, reason TEXT)")
        
        await db.execute("INSERT OR IGNORE INTO admins (user_id, rank) VALUES (?, 3)", (ADMIN_IDS[0],))
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'False')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('panic', 'False')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bj_chance', '20')")
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
    "poor": {"name": "🥺 Нищий", "price": 15, "coin_price": 5, "items": [("2 звезды", "common", 2, 70), ("5 звезд", "rare", 5, 25), ("20 звезд", "epic", 20, 5)]},
    "rich": {"name": "👑 Богатый", "price": 100, "coin_price": 30, "items": [("10 звезд", "common", 10, 60), ("50 звезд", "rare", 50, 30), ("NFT", "epic", 500, 10)]}
}

def open_case(key):
    items = CASES[key]["items"]
    if asyncio.run(get_setting("panic")) == "True":
        items = [i for i in items if i[2] <= 50]
    weights = [i[3] for i in items]
    return random.choices(items, weights=weights, k=1)[0]

# ================= КЛАВИАТУРЫ =================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases"), InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inv"), InlineKeyboardButton(text="👤 Профиль", callback_data="prof")],
        [InlineKeyboardButton(text="🔑 Промокод", callback_data="promo"), InlineKeyboardButton(text="👥 Рефералы", callback_data="ref")]
    ])

def back_btn(cb="back_main"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=cb)]])

def admin_menu(rank):
    kb = []
    if rank >= 2:
        kb.append([InlineKeyboardButton(text="🎁 Проверить купон", callback_data="admin_coupon")])
        kb.append([InlineKeyboardButton(text="🔑 Создать промо", callback_data="admin_promo")])
        kb.append([InlineKeyboardButton(text="🚫 Наказания", callback_data="admin_bans")])
    if rank == 3:
        kb.append([InlineKeyboardButton(text="💰 Выдать валюту", callback_data="admin_give")])
        kb.append([InlineKeyboardButton(text="🚨 Паника", callback_data="admin_panic"), InlineKeyboardButton(text="🛠 Тех.работы", callback_data="admin_maint")])
        kb.append([InlineKeyboardButton(text="👥 HR-Панель", callback_data="admin_staff")])
        kb.append([InlineKeyboardButton(text="⚙️ Шансы БД", callback_data="admin_odds")])
    kb.append([InlineKeyboardButton(text="Закрыть", callback_data="close_admin")])
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

# ================= ПОЛЬЗОВАТЕЛЬСКИЕ ХЭНДЛЕРЫ =================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if await get_setting("maintenance") == "True" and await get_admin_rank(message.from_user.id) == 0:
        return await message.answer("🛠 <b>На боте проводятся технические работы.</b>")

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
    user = await get_user(cb.from_user.id)
    await cb.message.edit_text(f"🏠 <b>Главное меню</b>\n\n💰 Баланс: <b>{user[3]}</b>\n💎 Коэны: <b>{user[4]}</b>", reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data == "prof")
async def prof(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    await cb.message.edit_text(f"👤 Профиль\n\n💰 Баланс: {user[3]}\n💎 Коэны: {user[4]}\n👥 Рефералы: {user[6]}/3", reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "ref")
async def ref(cb: CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={cb.from_user.id}"
    await cb.message.edit_text(f"👥 <b>Пригласи друзей!</b>\n\n🔗 Ссылка:\n<code>{link}</code>", reply_markup=back_btn())
    await cb.answer()

@dp.callback_query(F.data == "cases")
async def cases_menu(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{CASES['poor']['name']} ({CASES['poor']['price']}⭐)", callback_data="open_poor_stars")],
        [InlineKeyboardButton(text=f"{CASES['poor']['name']} ({CASES['poor']['coin_price']}💎)", callback_data="open_poor_coins")],
        [InlineKeyboardButton(text=f"{CASES['rich']['name']} ({CASES['rich']['price']}⭐)", callback_data="open_rich_stars")],
        [InlineKeyboardButton(text=f"{CASES['rich']['name']} ({CASES['rich']['coin_price']}💎)", callback_data="open_rich_coins")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await cb.message.edit_text("🎁 Выберите кейс:", reply_markup=kb)
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
    if user[4] < case["coin_price"]:
        return await cb.answer("❌ Недостаточно Коэнов!", show_alert=True)
    
    await upd_bal(cb.from_user.id, -case["coin_price"], is_coin=True)
    name, rarity, val, w = open_case(key)
    await add_item(cb.from_user.id, name, rarity, val)
    await cb.message.edit_text(f"🎉 Вы выиграли: <b>{name}</b>", reply_markup=back_btn("cases"))
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
        [InlineKeyboardButton(text="🃏 Блэкджек (20%)", callback_data="game_bj")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])
    await cb.message.edit_text("🎮 Игры:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("game_"))
async def game_bet(cb: CallbackQuery, state: FSMContext):
    await state.update_data(game=cb.data)
    await cb.message.edit_text("Введите сумму ставки (Монеты):", reply_markup=back_btn("games"))
    await state.set_state(UserState.waiting_bet)
    await cb.answer()

@dp.message(UserState.waiting_bet)
async def play_game(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    bet = int(message.text)
    user = await get_user(message.from_user.id)
    if user[3] < bet: return await message.answer("❌ Недостаточно монет!")
    
    data = await state.get_data()
    game = data.get("game")
    await state.clear()
    
    if game == "game_up":
        win = random.random() < 0.5
    elif game == "game_coin":
        win = random.choice([True, False])
    elif game == "game_bj":
        chance = int(await get_setting("bj_chance")) / 100.0
        win = random.random() < chance
        
    if win:
        await upd_bal(message.from_user.id, bet)
        await message.answer(f"🎉 Победа! Вы выиграли {bet} монет.", reply_markup=main_menu())
    else:
        await upd_bal(message.from_user.id, -bet)
        await message.answer(f"😢 Проигрыш. Вы потеряли {bet} монет.", reply_markup=main_menu())

@dp.callback_query(F.data == "promo")
async def promo_enter(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔑 Введите промокод:", reply_markup=back_btn())
    await state.set_state(UserState.waiting_promo)
    await cb.answer()

@dp.message(UserState.waiting_promo)
async def promo_check(message: Message, state: FSMContext):
    code = message.text.upper().strip()
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT reward, uses_left FROM promo_codes WHERE code = ?", (code,)) as cur:
            promo = await cur.fetchone()
        if not promo or promo[1] <= 0:
            return await message.answer("❌ Неверный или использованный промокод.", reply_markup=main_menu())
            
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[0], message.from_user.id))
        await db.commit()
    await message.answer(f"✅ Активирован! Получено {promo[0]} монет.", reply_markup=main_menu())

# ================= АДМИН-ПАНЕЛЬ =================
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    rank = await get_admin_rank(message.from_user.id)
    if rank == 0: return
    await message.answer("👑 Админка:", reply_markup=admin_menu(rank))

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

@dp.callback_query(F.data == "admin_coupon")
async def admin_coupon(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) < 2: return await cb.answer("Нет прав!", show_alert=True)
    await cb.message.edit_text("Отправьте код купона:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_coupon)
    await cb.answer()

@dp.message(AdminState.waiting_coupon)
async def admin_check_coupon(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT c.user_id, c.item_name, u.full_name, c.status FROM coupons c JOIN users u ON c.user_id = u.user_id WHERE c.code = ?", (code,)) as cur:
            info = await cur.fetchone()
            
    if not info: return await message.answer("❌ Купон не найден.", reply_markup=main_menu())
    uid, item, name, status = info
    if status == 'given': return await message.answer("⚠️ Купон УЖЕ ВЫДАН!", reply_markup=main_menu())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я выдал подарок", callback_data=f"givecoupon_{code}")]])
    await message.answer(f"🔍 <b>Купон:</b>\n👤 {name} ({uid})\n🎁 {item}\n\nВыдать?", reply_markup=kb)

@dp.callback_query(F.data.startswith("givecoupon_"))
async def admin_give_coupon(cb: CallbackQuery):
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
    await message.answer(f"✅ Промокод: <code>{code}</code>\nСумма: {data['val']}\nАктиваций: {message.text}", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "admin_give")
async def admin_give_req(cb: CallbackQuery, state: FSMContext):
    rank = await get_admin_rank(cb.from_user.id)
    if rank == 0: return
    await cb.message.edit_text("Введите ID игрока для выдачи:", reply_markup=back_btn("close_admin"))
    await state.set_state(AdminState.waiting_give_id)
    await cb.answer()

@dp.message(AdminState.waiting_give_id)
async def admin_give_id(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    await state.update_data(target_id=int(message.text))
    await message.answer("Введите сумму для выдачи:")
    await state.set_state(AdminState.waiting_give_amount)

@dp.message(AdminState.waiting_give_amount)
async def admin_give_amt(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    amount = int(message.text)
    data = await state.get_data()
    target_id = data['target_id']
    admin_id = message.from_user.id
    rank = await get_admin_rank(admin_id)
    await state.clear()
    
    if rank == 3:
        await upd_bal(target_id, amount)
        await add_hr_log(admin_id, "Выдача валюты", f"Выдал {amount} монет юзеру {target_id}")
        await message.answer(f"✅ Выдано {amount} монет пользователю {target_id}.", reply_markup=main_menu())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_give_{target_id}_{amount}_{admin_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data="deny_req")]
        ])
        try:
            await bot.send_message(ADMIN_IDS[0], f"⚠️ <b>Запрос на выдачу!</b>\nАдмин: @{message.from_user.username} (Ранг: {rank})\nКому: {target_id}\nСумма: {amount} монет", reply_markup=kb)
            await message.answer("📨 Запрос отправлен Директору.", reply_markup=main_menu())
        except:
            await message.answer("❌ Ошибка. Директор не в сети.")

@dp.callback_query(F.data.startswith("approve_give_"))
async def approve_give(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_IDS[0]: return await cb.answer("Вы не Директор!", show_alert=True)
    _, _, target_id, amount, admin_id = cb.data.split("_")
    await upd_bal(int(target_id), int(amount))
    await add_hr_log(int(admin_id), "Аппрув выдачи", f"Директор одобрил выдачу {amount} монет юзеру {target_id}")
    await cb.message.edit_text(f"✅ Вы одобрили выдачу {amount} монет для {target_id}.")
    await cb.answer("Выдано!")

@dp.callback_query(F.data == "deny_req")
async def deny_give(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_IDS[0]: return
    await cb.message.edit_text("❌ Запрос отклонен.")
    await cb.answer("Отклонено.")

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
    await message.answer(f"✅ Шанс БД: {message.text}%", reply_markup=main_menu())
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
    for log in logs:
        text += f"👤 {log[0]} | {log[1]}\n📝 {log[2]}\n🕒 {log[3][:16]}\n\n"
    await cb.message.edit_text(text, reply_markup=back_btn("admin_staff"))
    await cb.answer()

@dp.callback_query(F.data == "hr_set_staff")
async def hr_set_staff_prompt(cb: CallbackQuery, state: FSMContext):
    if await get_admin_rank(cb.from_user.id) != 3: return
    await cb.message.edit_text("Введите ID пользователя, чтобы назначить его Замом (ранг 2):", reply_markup=back_btn("admin_staff"))
    await state.set_state(AdminState.waiting_staff_id)
    await cb.answer()

@dp.message(AdminState.waiting_staff_id)
async def hr_set_staff_save(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число!")
    uid = int(message.text)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO admins (user_id, rank) VALUES (?, 2)", (uid,))
        await db.commit()
    await add_hr_log(message.from_user.id, "Назначение", f"Назначил {uid} Замом")
    await message.answer(f"✅ Пользователь {uid} назначен Заместителем!", reply_markup=main_menu())
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
    await add_hr_log(message.from_user.id, "Бан", f"Забанил {uid} по причине: {reason}")
    await message.answer(f"✅ Пользователь {uid} забанен.", reply_markup=main_menu())
    await state.clear()

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
