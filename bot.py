#!/usr/bin/env python3
"""
Telegram AI Bot – финальная версия с дедупликацией по хешу текста поста.
Исправлена ошибка NameError: name 'dp' is not defined.
"""

import asyncio
import logging
import os
import json
import time
import hashlib
import aiohttp
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from aiohttp import web

# ============================================
# КЛЮЧИ
# ============================================
TELEGRAM_TOKEN = "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0"
DEEPSEEK_API_KEY = "sk-3ff13ab1a93f4a099554f788b553e5e0"
SERPAPI_KEY = "3ed7bf5fee50fcbe3e6783bb00d5e43843b94da518017d47ebeb148fc0e265c9"

# ============================================
# НАСТРОЙКИ
# ============================================
ADMIN_ID = 682446170
PORT = int(os.getenv("PORT", "8080"))

MONITOR_CHANNEL_ID = -1003154677228
TARGET_GROUP_ID = -1002688844179
MONITORING_ENABLED = True

HISTORY_FILE = "history.json"
PROCESSED_FILE = "processed_posts.json"
MAX_HISTORY = 50
DUPLICATE_TIMEOUT = 3600  # 1 час

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================
# ИНИЦИАЛИЗАЦИЯ БОТА И ДИСПЕТЧЕРА (ДО ДЕКОРАТОРОВ)
# ============================================
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Глобальные хранилища
user_history = defaultdict(list)
processed_hashes = {}

# ============================================
# ЗАГРУЗКА/СОХРАНЕНИЕ ОБРАБОТАННЫХ ПОСТОВ
# ============================================
def load_processed():
    global processed_hashes
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                processed_hashes = data
                logger.info(f"Загружено {len(processed_hashes)} обработанных постов")
        except Exception as e:
            logger.error(f"Ошибка загрузки processed_hashes: {e}")

def save_processed():
    try:
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            json.dump(processed_hashes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения processed_hashes: {e}")

load_processed()

# ============================================
# ФУНКЦИЯ БЕЗОПАСНОЙ ОТПРАВКИ
# ============================================
async def safe_send(chat_id: int, text: str, reply_to_message_id: int = None):
    if not text:
        return
    if len(text) <= 4096:
        if reply_to_message_id:
            await bot.send_message(chat_id, text, reply_to_message_id=reply_to_message_id)
        else:
            await bot.send_message(chat_id, text)
        return
    for i in range(0, len(text), 4000):
        part = text[i:i+4000]
        if reply_to_message_id and i == 0:
            await bot.send_message(chat_id, part, reply_to_message_id=reply_to_message_id)
        else:
            await bot.send_message(chat_id, part)
        await asyncio.sleep(0.5)

# ============================================
# ПОИСК ЧЕРЕЗ SERPAPI
# ============================================
async def search_web(query: str, num_results: int = 3) -> str:
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "num": num_results,
        "hl": "ru",
        "gl": "ru"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://serpapi.com/search", params=params) as resp:
                data = await resp.json()
                results = data.get("organic_results", [])
                if not results:
                    return "❌ Информация не найдена."
                answer = "🔍 **Источники:**\n\n"
                for i, res in enumerate(results[:num_results], 1):
                    title = res.get("title", "Без заголовка")
                    link = res.get("link", "#")
                    snippet = res.get("snippet", "Нет описания")
                    answer += f"{i}. **{title}**\n   {snippet}\n   {link}\n\n"
                return answer
    except Exception as e:
        logger.error(f"Ошибка SerpAPI: {e}")
        return "⚠️ Ошибка поиска."

EXPERT_PROMPT = """Ты – эксперт по ставкам на спорт. Анализируй по методологии (кадры, тактика, мотивация, усталость, верификация). Отвечай кратко – до 2500 символов. Указывай ссылки на источники. Без воды и повторов."""

# ============================================
# ИСТОРИЯ ДИАЛОГОВ
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
# AI ОТВЕТ
# ============================================
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    timeout=60.0
)

async def get_ai_response(user_id: int, user_message: str) -> str:
    search_query = user_message + " травмы состав прогноз"
    search_results = await search_web(search_query, num_results=3)
    context = f"Запрос: {user_message}\n\n{search_results}\n\nДай краткий анализ по методологии (до 2500 символов)."
    history = user_history[user_id][-20:]
    messages = [{"role": "system", "content": EXPERT_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": context})
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )
        answer = response.choices[0].message.content
        user_history[user_id].append({"role": "user", "content": user_message})
        user_history[user_id].append({"role": "assistant", "content": answer})
        if len(user_history[user_id]) > MAX_HISTORY * 2:
            user_history[user_id] = user_history[user_id][-MAX_HISTORY*2:]
        save_history()
        return answer
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return f"⚠️ Ошибка: {str(e)}"

# ============================================
# КОМАНДЫ
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await safe_send(message.chat.id, "🤖 Эксперт по ставкам. Напиши матч – проанализирую.\n/clear_history, /admin_stats, /toggle_monitor")

@dp.message(Command("clear_history"))
async def clear_history(message: types.Message):
    if message.from_user.id in user_history:
        del user_history[message.from_user.id]
        save_history()
        await message.answer("✅ История очищена.")
    else:
        await message.answer("Нет истории.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав.")
        return
    bot_info = await message.bot.get_me()
    await message.answer(f"**Статус**\n@{bot_info.username}\nМониторинг: {'✅' if MONITORING_ENABLED else '❌'}\nПользователей: {len(user_history)}\nОбработано постов: {len(processed_hashes)}", parse_mode="Markdown")

@dp.message(Command("toggle_monitor"))
async def toggle_monitor(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global MONITORING_ENABLED
    MONITORING_ENABLED = not MONITORING_ENABLED
    await message.answer(f"Мониторинг {'вкл' if MONITORING_ENABLED else 'выкл'}.")

@dp.message(Command("test"))
async def test_cmd(message: types.Message):
    await message.reply("✅ Бот активен")

# ============================================
# МОНИТОРИНГ КАНАЛА (ДЕДУПЛИКАЦИЯ ПО ХЕШУ ТЕКСТА)
# ============================================
@dp.channel_post()
async def handle_channel_post(post: types.Message):
    global processed_hashes
    if not MONITORING_ENABLED:
        return
    if post.chat.id != MONITOR_CHANNEL_ID:
        return

    text = post.text or post.caption or ""
    if not text:
        text = "[Пост без текста]"
    
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    now = time.time()

    if text_hash in processed_hashes:
        last_time = processed_hashes[text_hash]
        if now - last_time < DUPLICATE_TIMEOUT:
            logger.info(f"Пост с хешем {text_hash[:8]} уже обработан {now-last_time:.0f} сек назад, пропускаем")
            return
    processed_hashes[text_hash] = now
    # Очистка старых хешей (старше 24 часов)
    to_delete = [h for h, ts in processed_hashes.items() if now - ts > 86400]
    for h in to_delete:
        del processed_hashes[h]
    if to_delete:
        logger.info(f"Очищено {len(to_delete)} старых хешей")
    save_processed()

    logger.info(f"Обрабатываю пост: {text[:100]}")
    comment = await get_ai_response(ADMIN_ID, f"Прокомментируй пост: {text}")
    await safe_send(TARGET_GROUP_ID, f"📢 **Пост в канале:**\n{text}\n\n💬 **Комментарий бота:**\n{comment}")

# ============================================
# ОБЩЕНИЕ В ГРУППЕ И ЛИЧКЕ
# ============================================
@dp.message()
async def group_chat(message: types.Message):
    if message.chat.type in ["group", "supergroup"] and message.chat.id == TARGET_GROUP_ID:
        if message.from_user.id != bot.id and not (message.text and message.text.startswith("/")):
            await bot.send_chat_action(message.chat.id, "typing")
            answer = await get_ai_response(message.from_user.id, message.text)
            await safe_send(message.chat.id, answer, reply_to_message_id=message.message_id)

@dp.message()
async def private_response(message: types.Message):
    if message.chat.type == "private" and not (message.text and message.text.startswith("/")):
        await bot.send_chat_action(message.chat.id, "typing")
        answer = await get_ai_response(message.from_user.id, message.text)
        await safe_send(message.chat.id, answer, reply_to_message_id=message.message_id)

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
    logger.info("🚀 Запуск бота с дедупликацией по хешу текста поста")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())