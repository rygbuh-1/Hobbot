#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – Эксперт по ставкам на спорт с самостоятельным поиском в интернете (Google).
"""

import asyncio
import logging
import os
import json
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from aiohttp import web
from googlesearch import search  # pip install google-search

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-3ff13ab1a93f4a099554f788b553e5e0")
ADMIN_ID = 682446170
PORT = int(os.getenv("PORT", "8080"))

MONITOR_CHANNEL_ID = -1003154677228
TARGET_GROUP_ID = -1002688844179
MONITORING_ENABLED = True

HISTORY_FILE = "history.json"
MAX_HISTORY = 200

# Включить автоматический поиск в интернете (можно отключить админом)
AUTO_WEB_SEARCH = True

user_history = defaultdict(list)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ============================================
# ФУНКЦИЯ ПОИСКА В ИНТЕРНЕТЕ
# ============================================
async def search_web(query: str, num_results: int = 5) -> list:
    """Ищет в Google и возвращает список словарей {'title': ..., 'url': ..., 'snippet': ...}"""
    results = []
    try:
        # Выполняем поиск синхронно, но в отдельном потоке, чтобы не блокировать event loop
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(
            None, lambda: list(search(query, num_results=num_results, advanced=True))
        )
        for result in search_results:
            results.append({
                "title": result.title,
                "url": result.url,
                "snippet": result.description
            })
        logger.info(f"Поиск по запросу '{query}' вернул {len(results)} результатов")
    except Exception as e:
        logger.error(f"Ошибка поиска Google: {e}")
    return results

# ============================================
# СИСТЕМНЫЙ ПРОМПТ ЭКСПЕРТА (с использованием результатов поиска)
# ============================================
SPORTS_ANALYST_PROMPT = """Ты — профессиональный эксперт в области ставок на спорт.
Твоя задача — анализировать матчи на основе предоставленной информации и результатов интернет-поиска.

ВАЖНО: если тебе переданы результаты поиска, ты обязан использовать их как основные источники. Не выдумывай факты, ссылайся на найденную информацию.

Следуй методологии (5 шагов) и всегда указывай источник (ссылку) для каждого утверждения. Если источник не указан — считай, что это твоё мнение, но лучше найти подтверждение.

Если поиск не дал результатов, честно скажи об этом и предложи пользователю предоставить ссылки вручную.

Ты должен говорить правду, не гадать, не выдумывать. Если чего-то не знаешь — так и скажи."""

# ============================================
# ЗАГРУЗКА / СОХРАНЕНИЕ ИСТОРИИ
# ============================================
def load_history():
    global user_history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                user_history = defaultdict(list, {int(k): v for k, v in data.items()})
                logger.info(f"Загружена история для {len(user_history)} пользователей")
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}")

def save_history():
    try:
        to_save = {str(k): v for k, v in user_history.items()}
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")

load_history()

# ============================================
# AI ОТВЕТ С ПОИСКОМ
# ============================================
async def get_ai_response(user_id: int, user_message: str, perform_search: bool = True) -> str:
    history = user_history[user_id]
    # Определяем, нужно ли искать в интернете
    search_context = ""
    if AUTO_WEB_SEARCH and perform_search and len(user_message) > 10:
        # Улучшим запрос: убираем лишние слова, добавляем "футбол травмы состав"
        search_query = user_message[:100] + " травмы состав прогноз"
        results = await search_web(search_query, num_results=3)
        if results:
            search_context = "\n\nРезультаты поиска в интернете (источники):\n"
            for i, res in enumerate(results, 1):
                search_context += f"{i}. {res['title']} - {res['url']}\n   {res['snippet']}\n"
        else:
            search_context = "\n\n(Поиск не дал результатов. Пользователь может предоставить ссылки вручную.)"
    
    # Формируем системный промпт
    system_prompt = SPORTS_ANALYST_PROMPT + "\n\n" + search_context if search_context else SPORTS_ANALYST_PROMPT
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-20:])  # последние 10 пар сообщений, чтобы не перегружать
    messages.append({"role": "user", "content": user_message})
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        answer = response.choices[0].message.content
        # Обновляем историю
        user_history[user_id].append({"role": "user", "content": user_message})
        user_history[user_id].append({"role": "assistant", "content": answer})
        if len(user_history[user_id]) > MAX_HISTORY * 2:
            user_history[user_id] = user_history[user_id][-MAX_HISTORY*2:]
        save_history()
        return answer
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return f"⚠️ Ошибка DeepSeek: {str(e)}"

# ============================================
# КОМАНДЫ
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Эксперт по ставкам на спорт с автоматическим поиском в интернете.\n"
        "Я сам ищу актуальную информацию (травмы, составы, новости) и даю прогнозы по методологии.\n\n"
        "Команды:\n"
        "/toggle_search – вкл/выкл автоматический поиск (админ)\n"
        "/clear_history – очистить историю\n"
        "/admin_stats – статистика"
    )

@dp.message(Command("toggle_search"))
async def toggle_search(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global AUTO_WEB_SEARCH
    AUTO_WEB_SEARCH = not AUTO_WEB_SEARCH
    await message.answer(f"Автоматический поиск в интернете {'включён' if AUTO_WEB_SEARCH else 'выключен'}.")

@dp.message(Command("clear_history"))
async def clear_history(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history:
        del user_history[user_id]
        save_history()
        await message.answer("✅ История очищена.")
    else:
        await message.answer("Истории нет.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"Статус\nБот: @{bot_info.username}\n"
        f"Поиск: {'ВКЛ' if AUTO_WEB_SEARCH else 'ВЫКЛ'}\n"
        f"Пользователей: {len(user_history)}"
    )

# ============================================
# МОНИТОРИНГ КАНАЛА (тоже с поиском)
# ============================================
@dp.channel_post()
async def handle_channel_post(post: types.Message):
    if not MONITORING_ENABLED:
        return
    if post.chat.id != MONITOR_CHANNEL_ID:
        return
    text = post.text or post.caption or ""
    if not text:
        text = "[Пост без текста]"
    comment = await get_ai_response(ADMIN_ID, f"Проанализируй этот пост как эксперт по ставкам, используй поиск если нужно: {text}", perform_search=True)
    try:
        await bot.send_message(chat_id=TARGET_GROUP_ID, text=f"📢 Пост в канале:\n{text}\n\n💬 Анализ бота:\n{comment}")
    except Exception as e:
        logger.error(f"Ошибка отправки комментария: {e}")

# ============================================
# ОБЩЕНИЕ В ГРУППЕ
# ============================================
@dp.message()
async def group_chat(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        return
    if message.chat.id != TARGET_GROUP_ID:
        return
    if message.from_user.id == bot.id:
        return
    if message.text and message.text.startswith("/"):
        return
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, message.text, perform_search=True)
    await message.reply(answer)

# ============================================
# ЛИЧКА
# ============================================
@dp.message()
async def private_response(message: types.Message):
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        return
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, message.text, perform_search=True)
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
    logger.info("🚀 Бот-эксперт с поиском Google запущен.")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())