#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – ULTIMATE FIX.
Logs everything, responds to ANY non-command message in the group.
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

# State
GROUP_TALK_ENABLED = True
GROUP_ID = None

# Conversation memory
user_history = defaultdict(list)
MAX_HISTORY = 10

# ============================================
# LOAD/SAVE SETTINGS
# ============================================
def load_settings():
    global GROUP_ID, GROUP_TALK_ENABLED
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                GROUP_ID = data.get("group_id")
                GROUP_TALK_ENABLED = data.get("group_talk_enabled", True)
                logging.info(f"Loaded settings: GROUP_ID={GROUP_ID}, TALK={GROUP_TALK_ENABLED}")
        except Exception as e:
            logging.error(f"Load settings error: {e}")

def save_settings():
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"group_id": GROUP_ID, "group_talk_enabled": GROUP_TALK_ENABLED}, f)
    logging.info(f"Saved settings: GROUP_ID={GROUP_ID}, TALK={GROUP_TALK_ENABLED}")

load_settings()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
# AI HELPER
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
# COMMON COMMANDS
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🤖 Бот работает. Команды: /setgroup, /toggle_chat, /test, /admin_stats")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Просто напиши текст — я отвечу. В группе тоже отвечаю.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(f"Нет прав. Ваш ID: {message.from_user.id}")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"✅ Админ\n"
        f"Bot: @{bot_info.username}\n"
        f"Group ID: {GROUP_ID}\n"
        f"Talk enabled: {GROUP_TALK_ENABLED}\n"
        f"Channel: {CHANNEL_ID}"
    )

@dp.message(Command("setgroup"))
async def set_group(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Только админ")
        return
    global GROUP_ID
    if message.chat.type in ["group", "supergroup"]:
        GROUP_ID = message.chat.id
        save_settings()
        await message.answer(f"✅ Группа установлена: {GROUP_ID}")
        logger.info(f"Group manually set to {GROUP_ID}")
    else:
        await message.answer("Эта команда работает только в группе.")

@dp.message(Command("toggle_chat"))
async def toggle_chat(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global GROUP_TALK_ENABLED
    GROUP_TALK_ENABLED = not GROUP_TALK_ENABLED
    save_settings()
    status = "включён" if GROUP_TALK_ENABLED else "выключен"
    await message.answer(f"Режим общения {status}.")

@dp.message(Command("test"))
async def test_cmd(message: types.Message):
    await message.reply("✅ Тест пройден")

@dp.message(Command("post"))
async def send_post(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/post", "", 1).strip()
    if not text:
        await message.answer("Текст после /post")
        return
    try:
        sent = await bot.send_message(chat_id=CHANNEL_ID, text=text)
        await message.answer(f"Пост отправлен, ID {sent.message_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("pin"))
async def pin_msg(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID")
        return
    msg_id = int(parts[1])
    try:
        await bot.pin_chat_message(chat_id=CHANNEL_ID, message_id=msg_id)
        await message.answer(f"Закреплено {msg_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("unpin"))
async def unpin_msg(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        await bot.unpin_chat_message(chat_id=CHANNEL_ID)
        await message.answer("Откреплено")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID or not GROUP_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return
    uid = int(parts[1])
    try:
        await bot.ban_chat_member(chat_id=GROUP_ID, user_id=uid)
        await message.answer(f"Забанен {uid}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID or not GROUP_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return
    uid = int(parts[1])
    try:
        await bot.unban_chat_member(chat_id=GROUP_ID, user_id=uid)
        await message.answer(f"Разбанен {uid}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("check_sub"))
async def check_sub(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return
    uid = int(parts[1])
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=uid)
        is_member = member.status in ["member", "administrator", "creator"]
        await message.answer(f"Подписка: {'✅' if is_member else '❌'}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# ============================================
# AUTO-DETECT GROUP ON ADD
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
                await bot.send_message(chat.id, "✅ Бот добавлен, группа сохранена. Теперь отвечаю.")

# ============================================
# MODERATION (optional, but here)
# ============================================
@dp.message()
async def moderate(message: types.Message):
    if not GROUP_ID or message.chat.id != GROUP_ID:
        return
    if not ENABLE_MODERATION:
        return
    if message.from_user.id == ADMIN_ID:
        return
    text = message.text or ""
    low = text.lower()
    for w in FORBIDDEN_WORDS:
        if w in low:
            await message.delete()
            await message.answer("⚠️ Удалено (запрещённое слово)")
            return
    if "http://" in low or "https://" in low:
        await message.delete()
        await message.answer("⚠️ Ссылки запрещены")
        return

# ============================================
# MAIN GROUP RESPONSE – NO EXTRA CONDITIONS (except not command and not bot itself)
# ============================================
@dp.message()
async def group_response(message: types.Message):
    # Логируем всё
    logger.info(f"group_response called: chat_id={message.chat.id}, GROUP_ID={GROUP_ID}, type={message.chat.type}, text={message.text[:50] if message.text else ''}")
    
    if message.chat.type not in ["group", "supergroup"]:
        logger.info("Not a group/supergroup, skipping")
        return
    if GROUP_ID is None:
        logger.info("GROUP_ID is None, skipping (use /setgroup)")
        return
    if message.chat.id != GROUP_ID:
        logger.info(f"Chat ID mismatch: {message.chat.id} != {GROUP_ID}")
        return
    if message.from_user.id == bot.id:
        logger.info("Message from bot, skipping")
        return
    if message.text and message.text.startswith("/"):
        logger.info("Command message, skipping")
        return
    if not message.text:
        logger.info("Empty message, skipping")
        return

    logger.info(f"✅ Processing group message: {message.text[:100]}")
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, message.text)
    try:
        await message.reply(answer)
        logger.info("Response sent")
    except Exception as e:
        logger.error(f"Failed to reply: {e}")
        await message.answer("⚠️ Ошибка отправки")

# ============================================
# PRIVATE CHAT RESPONSE
# ============================================
@dp.message()
async def private_response(message: types.Message):
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
    logger.info("🚀 ULTIMATE FIX: бот отвечает на ВСЕ сообщения в группе")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())