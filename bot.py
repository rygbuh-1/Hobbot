#!/usr/bin/env python3
"""
Минимальный рабочий бот для диагностики.
Отвечает на /start и /admin_stats.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web
import os

TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")
ADMIN_ID = 682446170
PORT = int(os.getenv("PORT", "8080"))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(f"Бот работает! Ваш ID: {message.from_user.id}")

@dp.message(Command("admin_stats"))
async def stats(message: types.Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.answer(f"⛔ Нет прав. Ваш ID: {user_id}, ожидается {ADMIN_ID}")
        return
    await message.answer("✅ Вы администратор! Бот функционирует.")

@dp.message()
async def echo(message: types.Message):
    await message.answer("Эхо: " + message.text)

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
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())