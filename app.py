#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek
Uses long polling (no webhook) and a health check server for hosting.
"""

import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import AsyncOpenAI
from aiohttp import web

# ============================================
# CONFIGURATION
# ============================================
# Токены (лучше использовать переменные окружения на хостинге)
# Сейчас токены вставлены прямо из ваших данных
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-3ff13ab1a93f4a099554f788b553e5e0")

PORT = int(os.getenv("PORT", "8080"))

# Инициализация DeepSeek (совместим с OpenAI SDK)
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# ============================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Привет! Я ИИ-бот на движке DeepSeek.\n"
        "Просто напиши мне любое сообщение, и я отвечу.\n\n"
        "📌 Команды:\n"
        "/start - показать это сообщение\n"
        "/help - справка\n"
        "/about - информация о боте"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 Справка:\n"
        "Я отвечаю на любые текстовые сообщения, используя нейросеть DeepSeek.\n"
        "Модель: deepseek-chat\n\n"
        "Просто напиши вопрос или фразу — я постараюсь помочь."
    )

@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    await message.answer(
        "ℹ️ Бот создан с помощью BetterDeepSeek.\n"
        "Использует API DeepSeek (бесплатные токены).\n"
        "Работает в режиме long polling.\n"
        "Хостинг: Bothost"
    )

@dp.message()
async def handle_message(message: types.Message):
    # Показываем статус "печатает"
    await bot.send_chat_action(message.chat.id, "typing")
    
    user_text = message.text
    if not user_text:
        return
    
    try:
        # Запрос к DeepSeek
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты — дружелюбный и полезный ИИ-ассистент. Отвечай кратко и по делу, на русском языке."},
                {"role": "user", "content": user_text}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        answer = response.choices[0].message.content
        await message.reply(answer)
    except Exception as e:
        error_msg = f"⚠️ Ошибка при обращении к DeepSeek: {str(e)}"
        await message.reply(error_msg)

# ============================================
# HEALTH CHECK HTTP-СЕРВЕР (для хостинга)
# ============================================
async def health_check(request):
    return web.Response(text="OK", status=200)

async def run_http_server():
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)  # корень тоже отдаём OK
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"✅ HTTP health server running on port {PORT}")
    # держим сервер запущенным бесконечно
    await asyncio.Event().wait()

# ============================================
# ЗАПУСК
# ============================================
async def main():
    # Запускаем бота (long polling) и HTTP-сервер параллельно
    print("🚀 Starting bot and health server...")
    await asyncio.gather(
        dp.start_polling(bot),
        run_http_server()
    )

if __name__ == "__main__":
    asyncio.run(main())