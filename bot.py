#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek + Admin & Moderation features
Improved with graceful shutdown and signal handling.
"""

import asyncio
import logging
import signal
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiohttp import web

from config import TELEGRAM_TOKEN, PORT
from handlers import deepseek, admin, moderator
from middlewares.subscription import SubscriptionMiddleware

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

async def run_http_server(stop_event: asyncio.Event):
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"✅ Health check server running on port {PORT}")
    await stop_event.wait()
    logger.info("Stopping HTTP server...")
    await runner.cleanup()

async def main():
    logger.info("🚀 Starting bot...")
    
    # Создаём событие для сигнала завершения
    stop_event = asyncio.Event()
    
    # Обработка сигналов SIGTERM и SIGINT
    def handle_signal():
        logger.info("Received termination signal, shutting down gracefully...")
        stop_event.set()
    
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, handle_signal)
    loop.add_signal_handler(signal.SIGINT, handle_signal)
    
    # Запускаем polling и HTTP сервер параллельно
    polling_task = asyncio.create_task(dp.start_polling(bot))
    http_task = asyncio.create_task(run_http_server(stop_event))
    
    # Ждём либо завершения polling, либо сигнала
    done, pending = await asyncio.wait(
        [polling_task, http_task, stop_event.wait()],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Отменяем все задачи
    for task in pending:
        task.cancel()
    
    # Даём время на graceful shutdown
    await asyncio.sleep(2)
    
    # Закрываем сессию бота
    await bot.session.close()
    logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user.")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)