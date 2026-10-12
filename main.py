import os
import sqlite3
import random
import asyncio

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus


# =========================
# ОСНОВНЫЕ НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@AbumCountry1")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

DB_NAME = "gift_chance.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# =========================
# ПОДАРКИ И БАЗОВЫЕ ВЕСА
# =========================

GIFTS = [
    ("teddy", "Teddy Bear 🧸", 50, False),
    ("heart", "Heart ❤️", 50, False),
    ("rose", "Rose 🌹", 30, False),
    ("mystery", "Mystery Gift 🎁", 30, False),
    ("ring", "Golden Ring 💍", 10, True),
    ("diamond", "Diamond 💎", 10, True),
    ("bouquet", "Flower Bouquet 💐", 15, True),
    ("cake", "Birthday Cake 🎂", 15, True),
    ("nft", "Legendary NFT 🖼️", 1, True),
]


# =========================
# БАЗА ДАННЫХ
# =========================

def connect_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                tickets INTEGER NOT NULL DEFAULT 0
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS invite_links (
                inviter_id INTEGER PRIMARY KEY,
                link TEXT UNIQUE NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                referred_id INTEGER PRIMARY KEY,
                inviter_id INTEGER NOT NULL,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS gifts (
                gift_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                weight REAL NOT NULL,
                rare INTEGER NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS wins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                gift_name TEXT NOT NULL,
                won_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        for key, name, weight, rare in GIFTS:
            db.execute("""
                INSERT OR IGNORE INTO gifts
                (gift_key, name, weight, rare)
                VALUES (?, ?, ?, ?)
            """, (key, name, weight, int(rare)))

        # Буст по умолчанию: 0,5% веса за приглашение.
        db.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('bonus_percent', '0.5')
        """)


def register_user(user_id, username):
    with connect_db() as db:
        db.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET username = excluded.username
        """, (user_id, username))


def get_referral_count(user_id):
    with connect_db() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM referrals WHERE inviter_id = ?",
            (user_id,)
        ).fetchone()

    return row[0]


def get_ticket_count(user_id):
    with connect_db() as db:
        row = db.execute(
            "SELECT tickets FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    return row[0] if row else 0


def get_bonus_percent():
    with connect_db() as db:
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'bonus_percent'"
        ).fetchone()

    return float(row[0]) if row else 0.5


def get_current_gift_weights(user_id):
    referrals = get_referral_count(user_id)
    bonus = get_bonus_percent()

    with connect_db() as db:
        rows = db.execute("""
            SELECT gift_key, name, weight, rare
            FROM gifts
            ORDER BY rowid
        """).fetchall()

    result = []

    for key, name, weight, rare in rows:
        current_weight = float(weight)

        if rare:
            current_weight *= 1 + referrals * bonus / 100

        result.append((key, name, current_weight))

    return referrals, result


# =========================
# ПРОВЕРКА АДМИНИСТРАТОРА
# =========================

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


# =========================
# КОМАНДА /START
# =========================

@router.message(CommandStart())
async def start_command(message: Message):
    user = message.from_user
    register_user(user.id, user.username)

    await message.answer(
        "🎁 <b>Gift Chance Bot</b>\n\n"
        "Приглашай людей в наш канал и получай попытки "
        "выиграть подарки!\n\n"
        "📨 /invite — твоя ссылка для приглашений\n"
        "🎲 /gift — открыть подарок\n"
        "📊 /stats — твоя статистика\n"
        "🎁 /gifts — текущие шансы подарков\n\n"
        "За каждого нового участника, который вступит "
        "в канал по твоей ссылке, ты получишь одну попытку.",
        parse_mode="HTML"
    )


# =========================
# КОМАНДА /INVITE
# =========================

@router.message(Command("invite"))
async def invite_command(message: Message):
    user = message.from_user
    register_user(user.id, user.username)

    with connect_db() as db:
        row = db.execute(
            "SELECT link FROM invite_links WHERE inviter_id = ?",
            (user.id,)
        ).fetchone()

    if row:
        invite_url = row[0]
    else:
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                name=f"ref-{user.id}"
            )
        except Exception:
            await message.answer(
                "❌ Не удалось создать ссылку.\n\n"
                "Проверь, что бот добавлен в канал "
                "администратором и может приглашать участников."
            )
            return

        invite_url = invite.invite_link

        with connect_db() as db:
            db.execute("""
                INSERT OR REPLACE INTO invite_links
                (inviter_id, link)
                VALUES (?, ?)
            """, (user.id, invite_url))

    await message.answer(
        "🔗 <b>Твоя персональная ссылка:</b>\n\n"
        f"{invite_url}\n\n"
        "Отправляй её друзьям. За каждого нового "
        "участника, вступившего по этой ссылке, "
        "начисляется одна попытка.\n\n"
        "⚠️ Повторные вступления одного человека "
        "не дают дополнительные попытки.",
        parse_mode="HTML"
    )


# =========================
# ОТСЛЕЖИВАНИЕ ВСТУПЛЕНИЙ
# =========================

def is_active_member(member):
    status = member.status

    if status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    ):
        return True

    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))

    return False


def is_target_channel(chat):
    if CHANNEL_ID.startswith("@"):
        return chat.username == CHANNEL_ID[1:]

    return str(chat.id) == CHANNEL_ID


@router.chat_member()
async def track_referral(event: ChatMemberUpdated):
    if not is_target_channel(event.chat):
        return

    old_member = event.old_chat_member
    new_member = event.new_chat_member

    # Засчитываем только реальное вступление.
    if is_active_member(old_member):
        return

    if not is_active_member(new_member):
        return

    invited_user = new_member.user

    if invited_user.is_bot:
        return

    # Вступление должно произойти именно по нашей ссылке.
    if not event.invite_link:
        return

    used_link = event.invite_link.invite_link

    with connect_db() as db:
        row = db.execute(
            "SELECT inviter_id FROM invite_links WHERE link = ?",
            (used_link,)
        ).fetchone()

        if not row:
            return

        inviter_id = row[0]

        if inviter_id == invited_user.id:
            return

        # Один приглашённый человек учитывается только один раз.
        cursor = db.execute("""
            INSERT OR IGNORE INTO referrals
            (referred_id, inviter_id)
            VALUES (?, ?)
        """, (invited_user.id, inviter_id))

        if cursor.rowcount == 0:
            return

        db.execute("""
            INSERT OR IGNORE INTO users (user_id, tickets)
            VALUES (?, 0)
        """, (inviter_id,))

        db.execute("""
            UPDATE users
            SET tickets = tickets + 1
            WHERE user_id = ?
        """, (inviter_id,))

        total = db.execute("""
            SELECT COUNT(*) FROM referrals
            WHERE inviter_id = ?
        """, (inviter_id,)).fetchone()[0]

    try:
        await bot.send_message(
            inviter_id,
            "🎉 <b>Новый участник по твоей ссылке!</b>\n\n"
            "Тебе начислена одна попытка открыть подарок.\n"
            f"👥 Всего приглашено: {total}\n"
            "🎲 Открыть подарок: /gift",
            parse_mode="HTML"
        )
    except Exception:
        # Если пользователь временно недоступен,
        # попытка всё равно сохранена в базе.
        pass


# =========================
# КОМАНДА /GIFT
# =========================

@router.message(Command("gift"))
async def gift_command(message: Message):
    user = message.from_user
    register_user(user.id, user.username)

    tickets = get_ticket_count(user.id)

    if tickets <= 0:
        await message.answer(
            "🎁 У тебя пока нет попыток.\n\n"
            "Пригласи нового участника через /invite, "
            "чтобы получить попытку."
        )
        return

    referrals, gifts = get_current_gift_weights(user.id)

    if not gifts:
        await message.answer("❌ Список подарков пока пуст.")
        return

    selected = random.choices(
        gifts,
        weights=[item[2] for item in gifts],
        k=1
    )[0]

    gift_key, gift_name, _ = selected

    with connect_db() as db:
        # Списываем одну попытку и записываем выигрыш.
        db.execute("""
            UPDATE users
            SET tickets = tickets - 1
            WHERE user_id = ? AND tickets > 0
        """, (user.id,))

        row = db.execute(
            "SELECT tickets FROM users WHERE user_id = ?",
            (user.id,)
        ).fetchone()

        if not row or row[0] < 0:
            await message.answer("❌ Не удалось открыть подарок.")
            return

        db.execute("""
            INSERT INTO wins (user_id, gift_key, gift_name)
            VALUES (?, ?, ?)
        """, (user.id, gift_key, gift_name))

    await message.answer(
        "🎉 <b>Твой подарок:</b>\n\n"
        f"{gift_name}\n\n"
        f"👥 Приглашено: {referrals}\n"
        f"🎲 Осталось попыток: {get_ticket_count(user.id)}",
        parse_mode="HTML"
    )


# =========================
# КОМАНДА /STATS
# =========================

@router.message(Command("stats"))
async def stats_command(message: Message):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username)

    referrals = get_referral_count(user_id)
    tickets = get_ticket_count(user_id)

    with connect_db() as db:
        wins_count = db.execute(
            "SELECT COUNT(*) FROM wins WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

    await message.answer(
        "📊 <b>Твоя статистика</b>\n\n"
        f"👥 Приглашено участников: {referrals}\n"
        f"🎲 Доступно попыток: {tickets}\n"
        f"🎁 Открыто подарков: {wins_count}\n"
        f"📈 Буст редких подарков: "
        f"+{referrals * get_bonus_percent():.2f}% к весу\n\n"
        "🔗 Твоя ссылка: /invite",
        parse_mode="HTML"
    )


# =========================
# КОМАНДА /GIFTS
# =========================

@router.message(Command("gifts"))
async def gifts_command(message: Message):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username)

    referrals, gifts = get_current_gift_weights(user_id)
    total_weight = sum(item[2] for item in gifts)

    lines = []

    for key, name, weight in gifts:
        chance = weight / total_weight * 100
        lines.append(f"{name} — <b>{chance:.2f}%</b>")

    await message.answer(
        "🎁 <b>Шансы выпадения подарков</b>\n\n"
        + "\n".join(lines)
        + f"\n\n👥 Твои приглашения: {referrals}\n"
        f"📈 Буст редких подарков: "
        f"+{referrals * get_bonus_percent():.2f}% к весу\n\n"
        "Шансы автоматически пересчитываются "
        "после каждого нового приглашения.",
        parse_mode="HTML"
    )


# =========================
# АДМИН-КОМАНДЫ
# =========================

@router.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    await message.answer(
        "⚙️ <b>Панель настроек</b>\n\n"
        "Изменить базовый вес подарка:\n"
        "<code>/setweight teddy 50</code>\n\n"
        "Доступные ключи:\n"
        "<code>teddy, heart, rose, mystery, ring, "
        "diamond, bouquet, cake, nft</code>\n\n"
        "Изменить буст за приглашение:\n"
        "<code>/setbonus 0.5</code>\n\n"
        "Значение 0.5 означает увеличение веса "
        "каждого редкого подарка на 0,5% за "
        "каждого нового приглашённого.\n\n"
        "Изменения сохраняются в базе данных.",
        parse_mode="HTML"
    )


@router.message(Command("setweight"))
async def setweight_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts) != 3:
        await message.answer(
            "Формат: /setweight nft 1"
        )
        return

    key = parts[1].lower()

    try:
        weight = float(parts[2])
    except ValueError:
        await message.answer("❌ Вес должен быть числом.")
        return

    if weight <= 0:
        await message.answer("❌ Вес должен быть больше нуля.")
        return

    with connect_db() as db:
        cursor = db.execute("""
            UPDATE gifts SET weight = ?
            WHERE gift_key = ?
        """, (weight, key))

    if cursor.rowcount == 0:
        await message.answer("❌ Неизвестный ключ подарка.")
        return

    await message.answer(
        f"✅ Базовый вес подарка <b>{key}</b> теперь {weight:g}.",
        parse_mode="HTML"
    )


@router.message(Command("setbonus"))
async def setbonus_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = (message.text or "").split()

    if len(parts) != 2:
        await message.answer("Формат: /setbonus 0.5")
        return

    try:
        bonus = float(parts[1])
    except ValueError:
        await message.answer("❌ Буст должен быть числом.")
        return

    if bonus < 0 or bonus > 100:
        await message.answer(
            "❌ Укажи значение от 0 до 100."
        )
        return

    with connect_db() as db:
        db.execute("""
            INSERT INTO settings (key, value)
            VALUES ('bonus_percent', ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (str(bonus),))

    await message.answer(
        f"✅ Буст установлен: +{bonus:g}% к весу "
        "каждого редкого подарка за приглашение."
    )


# =========================
# ЗАПУСК
# =========================

async def main():
    init_db()

    print("Gift Chance Bot запущен.")

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types()
    )


if __name__ == "__main__":
    asyncio.run(main())
