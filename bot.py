#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – автоматическое определение группы, исправлено общение.
"""

import asyncio
import logging
import json
import os
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from aiohttp import web

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-3ff13ab1a93f4a099554f788b553e5e0")
ADMIN_ID = 682446170

CHANNEL_ID = -1003154677228
SETTINGS_FILE = "settings.json"

ENABLE_MODERATION = True
FORBIDDEN_WORDS = ["спам", "реклама", "мат"]
PORT = int(os.getenv("PORT", "8080"))

# Состояния
GROUP_TALK_ENABLED = True
GROUP_ID = None

user_history = defaultdict(list)
MAX_HISTORY = 10

# ============================================
# ЗАГРУЗКА НАСТРОЕК
# ============================================
def load_settings():
    global GROUP_ID, GROUP_TALK_ENABLED
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                GROUP_ID = data.get("group_id")
                GROUP_TALK_ENABLED = data.get("group_talk_enabled", True)
                logging.info(f"Загружены настройки: group_id={GROUP_ID}, talk={GROUP_TALK_ENABLED}")
        except Exception as e:
            logging.error(f"Ошибка загрузки настроек: {e}")

def save_settings():
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"group_id": GROUP_ID, "group_talk_enabled": GROUP_TALK_ENABLED}, f)
    logging.info(f"Сохранены настройки: group_id={GROUP_ID}, talk={GROUP_TALK_ENABLED}")

# ============================================
# ЛОГИРОВАНИЕ
# ============================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_settings()

# ============================================
# DEEPSEEK CLIENT
# ============================================
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ============================================
# ПОМОЩНИК: ОТВЕТ С ПАМЯТЬЮ
# ============================================
async def get_ai_response(user_id: int, user_message: str) -> str:
    history = user_history[user_id]
    messages = [
        {"role": "system", "content": "Ты — дружелюбный, остроумный ИИ-ассистент. Отвечай естественно, как человек в чате. Пиши на русском, кратко и по делу."}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )
        answer = response.choices[0].message.content
        user_history[user_id].append({"role": "user", "content": user_message})
        user_history[user_id].append({"role": "assistant", "content": answer})
        if len(user_history[user_id]) > MAX_HISTORY * 2:
            user_history[user_id] = user_history[user_id][-MAX_HISTORY*2:]
        return answer
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return f"⚠️ Ошибка: {str(e)}"

# ============================================
# ОБЩИЕ КОМАНДЫ
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Привет! Я ИИ-бот.\n"
        "Добавь меня в группу и напиши /setgroup в этой группе, чтобы я начал общаться.\n"
        "Команды администратора: /admin_stats, /setgroup, /toggle_chat, /post, /pin и т.д."
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Просто напиши мне текст — я отвечу. В группе я отвечаю, если режим включён (/toggle_chat).")

# ============================================
# АДМИН-КОМАНДЫ
# ============================================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"⛔ Нет прав. Ваш ID: {message.from_user.id}")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"✅ Вы администратор!\n"
        f"ID бота: {bot_info.id}\n"
        f"Username: @{bot_info.username}\n"
        f"Канал: {CHANNEL_ID}\n"
        f"Группа для общения: {GROUP_ID if GROUP_ID else 'не задана'}\n"
        f"Общение в группе: {'вкл' if GROUP_TALK_ENABLED else 'выкл'}"
    )

@dp.message(Command("setgroup"))
async def set_group(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может установить группу.")
        return
    global GROUP_ID
    if message.chat.type in ["group", "supergroup"]:
        GROUP_ID = message.chat.id
        save_settings()
        await message.answer(f"✅ Группа установлена. Теперь я буду отвечать здесь.\nID: {GROUP_ID}")
        logger.info(f"Group set to {GROUP_ID} by admin in chat {message.chat.id}")
    else:
        await message.answer("❌ Эта команда работает только в группе.")

@dp.message(Command("toggle_chat"))
async def toggle_group_chat(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    global GROUP_TALK_ENABLED
    GROUP_TALK_ENABLED = not GROUP_TALK_ENABLED
    save_settings()
    status = "включён" if GROUP_TALK_ENABLED else "выключен"
    await message.answer(f"🔄 Режим общения в группе {status}.")

@dp.message(Command("test"))
async def test_command(message: types.Message):
    """Тестовая команда для проверки работы бота в группе"""
    if message.chat.type in ["group", "supergroup"]:
        await message.reply("✅ Бот работает и видит это сообщение!")
    else:
        await message.answer("Тестовая команда сработала в личке.")

# Остальные админ-команды (post, pin, unpin, ban, unban, check_sub) – сокращённо, но полный код есть в предыдущих версиях. Для краткости здесь основные.
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
    if not GROUP_ID:
        await message.answer("❌ Группа не задана. Используйте /setgroup в группе.")
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
    if not GROUP_ID:
        await message.answer("❌ Группа не задана.")
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
# АВТООПРЕДЕЛЕНИЕ ГРУППЫ ПРИ ДОБАВЛЕНИИ
# ============================================
@dp.my_chat_member()
async def on_my_chat_member(update: types.ChatMemberUpdated):
    if update.new_chat_member.status in ["member", "administrator"]:
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            global GROUP_ID
            if GROUP_ID is None:
                GROUP_ID = chat.id
                save_settings()
                logger.info(f"Auto-set group ID to {GROUP_ID}")
                await bot.send_message(chat.id, "✅ Бот добавлен в группу. Теперь я буду отвечать на сообщения. Для управления используйте /toggle_chat и /setgroup (если не сработает автоматически).")

# ============================================
# МОДЕРАЦИЯ В ГРУППЕ (удаление спама)
# ============================================
@dp.message()
async def moderate_group_messages(message: types.Message):
    if not GROUP_ID or message.chat.id != GROUP_ID:
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
# ОТВЕТЫ В ГРУППЕ (основной)
# ============================================
@dp.message()
async def ai_response_group(message: types.Message):
    # Отладочный лог
    logger.info(f"ai_response_group: chat_id={message.chat.id}, GROUP_ID={GROUP_ID}, type={message.chat.type}")
    if not GROUP_ID:
        logger.info("GROUP_ID is None, skipping group response")
        return
    if message.chat.id != GROUP_ID:
        logger.info(f"Chat ID mismatch: {message.chat.id} != {GROUP_ID}")
        return
    if not GROUP_TALK_ENABLED:
        logger.info("Group talk disabled")
        return
    if message.from_user.id == bot.id:
        return
    if message.text and message.text.startswith("/"):
        return
    if not message.text:
        return

    logger.info(f"Processing group message from {message.from_user.id}: {message.text[:50]}")
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, message.text)
    try:
        await message.reply(answer)
        logger.info("Response sent successfully")
    except Exception as e:
        logger.error(f"Failed to send response: {e}")
        await message.answer("⚠️ Не удалось отправить сообщение. Проверьте права бота.")

# ============================================
# ОТВЕТЫ В ЛИЧКЕ
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
# HEALTH CHECK
# ============================================
async def health_check(request):
    return web.Response(text="OK")

async def run_http():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    await asyncio.Event().wait()

async def main():
    logger.info("🚀 Запуск бота с исправленным общением в группе")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())