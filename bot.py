#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek + Admin & Moderation
Now talks in the group chat like a human.
"""

import asyncio
import logging
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from aiohttp import web
import os

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-3ff13ab1a93f4a099554f788b553e5e0")
ADMIN_ID = 682446170                     # your Telegram ID

CHANNEL_ID = -1003154677228              # your channel ID (for posts)
GROUP_ID = -1002688844179                # your group ID where bot will talk

# Feature toggles
REQUIRE_SUBSCRIPTION = False             # disabled
ENABLE_MODERATION = True
FORBIDDEN_WORDS = ["спам", "реклама", "мат"]

PORT = int(os.getenv("PORT", "8080"))

# Group talking mode (can be toggled by admin)
GROUP_TALK_ENABLED = True

# Conversation memory: user_id -> list of last messages (each is {"role": "user" or "assistant", "content": text})
# Limited to last 10 messages per user to avoid token overflow.
user_history = defaultdict(list)
MAX_HISTORY = 10

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
# HELPER: Get AI response with memory
# ============================================
async def get_ai_response(user_id: int, user_message: str) -> str:
    # Retrieve history for this user
    history = user_history[user_id]
    
    # Prepare messages for DeepSeek
    messages = [
        {"role": "system", "content": "Ты — дружелюбный, остроумный ИИ-ассистент. Отвечай естественно, как человек в чате. Пиши на русском, кратко и по делу. Если не знаешь — скажи честно."}
    ]
    # Add last history messages (excluding the current one)
    for msg in history:
        messages.append(msg)
    # Add current user message
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )
        answer = response.choices[0].message.content
        # Update history: add user message and bot response
        user_history[user_id].append({"role": "user", "content": user_message})
        user_history[user_id].append({"role": "assistant", "content": answer})
        # Trim history to MAX_HISTORY pairs (2 messages per turn)
        if len(user_history[user_id]) > MAX_HISTORY * 2:
            user_history[user_id] = user_history[user_id][-MAX_HISTORY*2:]
        return answer
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return f"⚠️ Ошибка: {str(e)}"

# ============================================
# COMMON COMMANDS
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Привет! Я ИИ-бот на DeepSeek.\n"
        "Я могу общаться в группе как человек, а также помогать админу управлять каналом.\n\n"
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
        "/check_sub user_id - проверить подписку\n"
        "/toggle_chat - включить/выключить общение в группе"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("📖 Просто напишите мне текст в личку или в группе — я отвечу. В группе я отвечаю на все сообщения, если режим включён.")

@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    await message.answer("ℹ️ Бот умеет общаться в группе, администрировать канал и модеррировать чат. Версия 4.0")

# ============================================
# ADMIN COMMANDS
# ============================================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"⛔ Нет прав. Ваш ID: {message.from_user.id}, ожидается {ADMIN_ID}")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"✅ Вы администратор!\n"
        f"ID бота: {bot_info.id}\n"
        f"Username: @{bot_info.username}\n"
        f"Канал: {CHANNEL_ID}\n"
        f"Группа: {GROUP_ID}\n"
        f"Модерация: {'вкл' if ENABLE_MODERATION else 'выкл'}\n"
        f"Общение в группе: {'вкл' if GROUP_TALK_ENABLED else 'выкл'}"
    )

@dp.message(Command("toggle_chat"))
async def toggle_group_chat(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    global GROUP_TALK_ENABLED
    GROUP_TALK_ENABLED = not GROUP_TALK_ENABLED
    status = "включён" if GROUP_TALK_ENABLED else "выключен"
    await message.answer(f"🔄 Режим общения в группе {status}.")

@dp.message(Command("post"))
async def send_post(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.replace("/post", "", 1).strip()
    if not text:
        await message.answer("Укажите текст после /post")
        return
    try:
        sent = await bot.send_message(chat_id=CHANNEL_ID, text=text)
        await message.answer(f"✅ Пост отправлен. ID: {sent.message_id}")
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
        await message.answer(f"✅ Закреплено {msg_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("unpin"))
async def unpin_message(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        await bot.unpin_chat_message(chat_id=CHANNEL_ID)
        await message.answer("✅ Откреплено")
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
        await message.answer(f"✅ Пользователь {user_id} забанен")
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
# MODERATION IN GROUP (delete bad messages)
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
        if word in text_lower:
            await message.delete()
            await message.answer(f"⚠️ {message.from_user.full_name}, сообщение удалено (запрещённое слово)")
            return
    if "http://" in text_lower or "https://" in text_lower or "t.me/" in text_lower:
        await message.delete()
        await message.answer(f"⚠️ {message.from_user.full_name}, ссылки запрещены")
        return

# ============================================
# AI RESPONSE IN GROUP (like a human)
# ============================================
@dp.message()
async def ai_response_group(message: types.Message):
    # Only respond in the designated group and if group talk enabled
    if message.chat.id != GROUP_ID:
        return
    if not GROUP_TALK_ENABLED:
        return
    # Ignore messages from the bot itself
    if message.from_user.id == bot.id:
        return
    # Ignore commands
    if message.text and message.text.startswith("/"):
        return
    # Ignore messages that were deleted or empty
    if not message.text:
        return
    
    # Show typing action
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Get AI response with memory
    user_id = message.from_user.id
    answer = await get_ai_response(user_id, message.text)
    
    # Reply in the group (mention the user optionally)
    await message.reply(answer)

# ============================================
# AI RESPONSE IN PRIVATE (with memory)
# ============================================
@dp.message()
async def ai_response_private(message: types.Message):
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        return
    if not message.text:
        return
    
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, message.text)
    await message.reply(answer)

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
    logger.info("🚀 Запуск бота с режимом общения в группе (как человек)")
    await asyncio.gather(
        dp.start_polling(bot),
        run_http_server()
    )

if __name__ == "__main__":
    asyncio.run(main())