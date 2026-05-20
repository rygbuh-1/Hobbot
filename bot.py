#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek + Admin & Moderation
Debug version: shows user ID when admin check fails.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.filters import Command
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from aiohttp import web
import os

# ============================================
# CONFIGURATION — ALL IDS ARE SET
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-3ff13ab1a93f4a099554f788b553e5e0")
ADMIN_IDS = [682446170]                     # your Telegram ID (as integer)

# IDs you provided via @userinfobot
CHANNEL_ID = -1003154677228                 # your channel ID
GROUP_ID = -1002688844179                   # your group ID (for moderation)

# Feature toggles
REQUIRE_SUBSCRIPTION = True                 # require users to subscribe to channel
ENABLE_MODERATION = True                    # auto-delete forbidden words/links in group
FORBIDDEN_WORDS = ["спам", "реклама", "мат"]

PORT = int(os.getenv("PORT", "8080"))

# ============================================
# LOGGING
# ============================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# DEEPSEEK CLIENT
# ============================================
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# ============================================
# BOT & DISPATCHER
# ============================================
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ============================================
# MIDDLEWARE: SUBSCRIPTION CHECK
# ============================================
class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not REQUIRE_SUBSCRIPTION or not CHANNEL_ID:
            return await handler(event, data)
        user_id = event.from_user.id
        # skip check for admins
        if user_id in ADMIN_IDS:
            return await handler(event, data)
        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                return await handler(event, data)
            else:
                await event.answer("❌ Для использования бота подпишитесь на канал.")
                return
        except Exception as e:
            logger.error(f"Subscription check error: {e}")
            return await handler(event, data)

dp.message.middleware(SubscriptionMiddleware())
dp.callback_query.middleware(SubscriptionMiddleware())

# ============================================
# COMMON COMMANDS
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Привет! Я ИИ-бот на DeepSeek.\n"
        "Просто напиши мне любое сообщение, и я отвечу.\n\n"
        "📌 Команды:\n"
        "/start - это сообщение\n"
        "/help - справка\n"
        "/about - информация\n\n"
        "👑 Админ-команды (только для вас):\n"
        "/admin_stats - статистика\n"
        "/post текст - отправить пост в канал\n"
        "/pin message_id - закрепить сообщение\n"
        "/unpin - открепить\n"
        "/ban user_id - забанить в группе\n"
        "/unban user_id - разбанить\n"
        "/check_sub user_id - проверить подписку"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("📖 Просто напишите мне текст — я отвечу, используя ИИ DeepSeek.")

@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    await message.answer("ℹ️ Бот создан для управления каналом и группой с помощью ИИ. Версия 2.1 (debug)")

# ============================================
# ADMIN COMMANDS (with debug output)
# ============================================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"admin_stats called by user {user_id}, ADMIN_IDS = {ADMIN_IDS}")
    if user_id not in ADMIN_IDS:
        await message.answer(
            f"⛔ У вас нет прав администратора.\n"
            f"Ваш ID: {user_id}\n"
            f"Ожидается ID администратора: {ADMIN_IDS}"
        )
        return
    await message.answer(
        f"🤖 *Статистика бота:*\n"
        f"ID бота: {message.bot.id}\n"
        f"Имя: @{message.bot.username}\n"
        f"Администратор: {ADMIN_IDS[0]}\n"
        f"Канал ID: {CHANNEL_ID}\n"
        f"Группа ID: {GROUP_ID}\n"
        f"Модерация: {'вкл' if ENABLE_MODERATION else 'выкл'}\n"
        f"Обязательная подписка: {'вкл' if REQUIRE_SUBSCRIPTION else 'выкл'}",
        parse_mode="Markdown"
    )

@dp.message(Command("post"))
async def send_post(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    text = message.text.replace("/post", "", 1).strip()
    if not text:
        await message.answer("Укажите текст после /post")
        return
    try:
        sent = await bot.send_message(chat_id=CHANNEL_ID, text=text)
        await message.answer(f"✅ Пост отправлен в канал. ID: {sent.message_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("pin"))
async def pin_message(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID сообщения: /pin 123")
        return
    msg_id = int(parts[1])
    try:
        await bot.pin_chat_message(chat_id=CHANNEL_ID, message_id=msg_id)
        await message.answer(f"✅ Сообщение {msg_id} закреплено")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("unpin"))
async def unpin_message(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        await bot.unpin_chat_message(chat_id=CHANNEL_ID)
        await message.answer("✅ Закрепление снято")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID пользователя: /ban 123456789")
        return
    user_id = int(parts[1])
    try:
        await bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await message.answer(f"✅ Пользователь {user_id} забанен в группе")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID пользователя: /unban 123456789")
        return
    user_id = int(parts[1])
    try:
        await bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await message.answer(f"✅ Пользователь {user_id} разбанен")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("check_sub"))
async def check_subscription(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID пользователя: /check_sub 123456789")
        return
    user_id = int(parts[1])
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
        await message.answer(f"Пользователь {user_id} подписан: {'✅ да' if is_member else '❌ нет'}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ============================================
# MODERATION IN GROUP
# ============================================
@dp.message()
async def moderate_group_messages(message: types.Message):
    if message.chat.id != GROUP_ID:
        return
    if not ENABLE_MODERATION:
        return
    if is_admin(message.from_user.id):
        return
    text = message.text or message.caption or ""
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in text_lower:
            await message.delete()
            await message.answer(f"⚠️ {message.from_user.full_name}, сообщение удалено (запрещённое слово)")
            return
    if "http://" in text_lower or "https://" in text_lower or "t.me/" in text_lower:
        await message.delete()
        await message.answer(f"⚠️ {message.from_user.full_name}, ссылки запрещены")
        return

# ============================================
# AI RESPONSE (catch-all for non-command private messages)
# ============================================
@dp.message()
async def ai_response(message: types.Message):
    if message.chat.type not in ["private"]:
        return
    if message.text and message.text.startswith("/"):
        return
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты дружелюбный ИИ-ассистент. Отвечай кратко на русском."},
                {"role": "user", "content": message.text}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        answer = response.choices[0].message.content
        await message.reply(answer)
    except Exception as e:
        await message.reply(f"⚠️ Ошибка DeepSeek: {str(e)}")

# ============================================
# HEALTH CHECK SERVER
# ============================================
async def health_check(request):
    return web.Response(text="OK", status=200)

async def run_http_server():
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"✅ Health check on port {PORT}")
    await asyncio.Event().wait()

# ============================================
# MAIN
# ============================================
async def main():
    logger.info("🚀 Запуск бота с предустановленными ID канала и группы...")
    await asyncio.gather(
        dp.start_polling(bot),
        run_http_server()
    )

if __name__ == "__main__":
    asyncio.run(main())