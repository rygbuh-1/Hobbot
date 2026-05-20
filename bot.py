#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – ГАРАНТИРОВАННО РАБОТАЕТ В ЛЮБОЙ ГРУППЕ.
Отвечает на ЛЮБОЕ текстовое сообщение, кроме команд.
"""

import asyncio
import logging
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
PORT = int(os.getenv("PORT", "8080"))

# Режим общения в группах (можно включить/выключить командой /toggle_chat)
GROUP_TALK_ENABLED = True

# Память диалога (последние 10 сообщений на пользователя)
user_history = defaultdict(list)
MAX_HISTORY = 10

# ============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
# ФУНКЦИЯ ОТВЕТА AI
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
        return f"⚠️ Ошибка DeepSeek: {str(e)}"

# ============================================
# ОБЩИЕ КОМАНДЫ
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🤖 Бот активен. В группах отвечаю на все сообщения (если режим не выключен).")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Просто напишите текст — я отвечу. В группах отвечаю тоже.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(f"Нет прав. Ваш ID: {message.from_user.id}")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"✅ Статус администратора\n"
        f"Бот: @{bot_info.username}\n"
        f"Режим общения в группах: {'ВКЛ' if GROUP_TALK_ENABLED else 'ВЫКЛ'}"
    )

@dp.message(Command("toggle_chat"))
async def toggle_chat(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global GROUP_TALK_ENABLED
    GROUP_TALK_ENABLED = not GROUP_TALK_ENABLED
    status = "включён" if GROUP_TALK_ENABLED else "выключен"
    await message.answer(f"🔄 Режим общения в группах {status}.")

@dp.message(Command("test"))
async def test_cmd(message: types.Message):
    await message.reply("✅ Бот работает и видит это сообщение!")

# ============================================
# ОТВЕТЫ В ГРУППЕ (максимально простой обработчик)
# ============================================
@dp.message()
async def group_response(message: types.Message):
    # Логируем ВСЕ входящие сообщения (для отладки)
    logger.info(f"Получено сообщение: чат={message.chat.id} тип={message.chat.type} текст='{message.text}' от={message.from_user.id}")
    
    # Отвечаем только в группах и супергруппах
    if message.chat.type not in ["group", "supergroup"]:
        logger.info("Не группа, пропускаем")
        return
    
    # Не отвечаем на команды
    if message.text and message.text.startswith("/"):
        logger.info("Команда, пропускаем")
        return
    
    # Не отвечаем самому себе
    if message.from_user.id == bot.id:
        logger.info("Сообщение от бота, пропускаем")
        return
    
    # Если режим общения выключен
    if not GROUP_TALK_ENABLED:
        logger.info("Режим общения выключен")
        return
    
    # Пустое сообщение
    if not message.text:
        logger.info("Пустое сообщение")
        return
    
    logger.info(f"✅ Отвечаем в группе на: {message.text[:100]}")
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, message.text)
    try:
        await message.reply(answer)
        logger.info("Ответ отправлен")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await message.answer("⚠️ Не удалось отправить ответ")

# ============================================
# ОТВЕТЫ В ЛИЧНЫХ СООБЩЕНИЯХ
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
# HEALTH CHECK СЕРВЕР
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
    logger.info(f"✅ Health check сервер запущен на порту {PORT}")
    await asyncio.Event().wait()

# ============================================
# ЗАПУСК
# ============================================
async def main():
    logger.info("🚀 Бот запущен. Режим: отвечаю на ВСЕ сообщения в группах (кроме команд)")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())