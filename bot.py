#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek + Admin & Moderation features
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiohttp import web

from config import TELEGRAM_TOKEN, PORT
from handlers import deepseek, admin, moderator
from middlewares.subscription import SubscriptionMiddleware

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Регистрация middleware для проверки подписки
dp.message.middleware(SubscriptionMiddleware())
dp.callback_query.middleware(SubscriptionMiddleware())

# Регистрация роутеров
dp.include_router(admin.router)
dp.include_router(moderator.router)
dp.include_router(deepseek.router)  # должен быть последним, чтобы не перехватывать команды

# Health check HTTP сервер
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
    logging.info(f"✅ Health check server running on port {PORT}")
    await asyncio.Event().wait()

async def main():
    logging.info("🚀 Starting bot...")
    await asyncio.gather(
        dp.start_polling(bot),
        run_http_server()
    )

if __name__ == "__main__":
    asyncio.run(main())