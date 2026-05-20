#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – Эксперт по ставкам на спорт с авто-поиском (SerpAPI).
Исправлено: разбивка длинных сообщений на части.
"""

import asyncio
import logging
import os
import json
import aiohttp
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from aiohttp import web

# ============================================
# КЛЮЧИ (встроены)
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
MAX_HISTORY = 50

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

user_history = defaultdict(list)

deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ============================================
# ФУНКЦИЯ РАЗБИВКИ ДЛИННЫХ СООБЩЕНИЙ
# ============================================
async def safe_send(chat_id: int, text: str, reply_to_message_id: int = None):
    """Отправляет сообщение, разбивая на части если нужно (лимит Telegram 4096 символов)."""
    if not text:
        return
    # Разбиваем по 4000 символов, чтобы оставить запас
    for i in range(0, len(text), 4000):
        part = text[i:i+4000]
        if reply_to_message_id and i == 0:
            await bot.send_message(chat_id, part, reply_to_message_id=reply_to_message_id)
        else:
            await bot.send_message(chat_id, part)
        # Небольшая пауза между частями, чтобы не спамить
        await asyncio.sleep(0.5)

# ============================================
# ФУНКЦИЯ ПОИСКА ЧЕРЕЗ SERPAPI
# ============================================
async def search_web(query: str, num_results: int = 4) -> str:
    """Выполняет поиск через SerpAPI и возвращает форматированный текст со ссылками."""
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
                    return "❌ Не удалось найти информацию по запросу."
                answer = "🔍 **Результаты поиска (источники):**\n\n"
                for i, res in enumerate(results[:num_results], 1):
                    title = res.get("title", "Без заголовка")
                    link = res.get("link", "#")
                    snippet = res.get("snippet", "Нет описания")
                    answer += f"{i}. **{title}**\n   {snippet}\n   {link}\n\n"
                return answer
    except Exception as e:
        logger.error(f"Ошибка SerpAPI: {e}")
        return "⚠️ Ошибка при поиске. Попробуйте позже."

# ============================================
# СИСТЕМНЫЙ ПРОМПТ ЭКСПЕРТА
# ============================================
EXPERT_PROMPT = """Ты — профессиональный эксперт в области ставок на спорт.
Твоя задача — анализировать матчи на основе методологии из 5 шагов и предоставленных результатов поиска.

Ты ОБЯЗАН использовать информацию из поисковой выдачи (ссылки, заголовки, сниппеты) как основные источники.
Для каждого утверждения указывай источник: «Согласно [название источника](ссылка) …».
Если поиск не дал нужной информации, честно скажи об этом и попроси пользователя уточнить запрос или предоставить дополнительные данные.

Не выдумывай факты. Если информации недостаточно — дай общий анализ, но пометь, что он основан на твоих знаниях (до апреля 2025) и может быть неактуален.

Методология (применяй последовательно):
1. Кадровый аудит (травмы, дисквалификации) — ищи в найденных статьях.
2. Прогноз состава и тактики — опирайся на новости о тренировках и пресс-конференции.
3. Турнирная мотивация — проверь положение в таблице (если есть в выдаче).
4. Фактор усталости (календарь, логистика) — ищи информацию о перелётах, отдыхе.
5. Верификация данных (за час до матча) — посоветуй сверить официальные составы.

Будь объективен, краток, но информативен. Всегда указывай ссылки на источники."""

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
# AI ОТВЕТ С АВТО-ПОИСКОМ
# ============================================
async def get_ai_response(user_id: int, user_message: str) -> str:
    search_query = user_message + " травмы состав прогноз"
    search_results = await search_web(search_query, num_results=4)
    
    context = f"Пользователь спрашивает: {user_message}\n\n{search_results}\n\n"
    context += "Теперь, используя информацию из поиска (если она есть), дай развернутый анализ по методологии. Если поиск не дал конкретики, укажи это и дай общие рекомендации."
    
    history = user_history[user_id][-20:]
    messages = [{"role": "system", "content": EXPERT_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": context})
    
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=2000
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
        return f"⚠️ Ошибка DeepSeek: {str(e)}"

# ============================================
# КОМАНДЫ
# ============================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await safe_send(message.chat.id,
        "🤖 **Эксперт по ставкам на спорт с авто-поиском**\n\n"
        "Я сам ищу актуальную информацию (травмы, составы, новости) через Google и даю прогнозы по методологии из 5 шагов.\n"
        "Просто напиши название матча, и я проанализирую.\n\n"
        "📌 Команды:\n"
        "/clear_history – очистить историю диалога\n"
        "/admin_stats – статистика (админ)\n"
        "/toggle_monitor – вкл/выкл комментирование постов из канала")

@dp.message(Command("clear_history"))
async def clear_history(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history:
        del user_history[user_id]
        save_history()
        await message.answer("✅ История диалога очищена.")
    else:
        await message.answer("У вас нет сохранённой истории.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав.")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"**Статус бота**\n"
        f"Username: @{bot_info.username}\n"
        f"Мониторинг канала: {'✅ ВКЛ' if MONITORING_ENABLED else '❌ ВЫКЛ'}\n"
        f"Пользователей в истории: {len(user_history)}",
        parse_mode="Markdown"
    )

@dp.message(Command("toggle_monitor"))
async def toggle_monitor(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global MONITORING_ENABLED
    MONITORING_ENABLED = not MONITORING_ENABLED
    await message.answer(f"Мониторинг канала {'включён' if MONITORING_ENABLED else 'выключен'}.")

@dp.message(Command("test"))
async def test_cmd(message: types.Message):
    await message.reply("✅ Бот активен, поиск работает.")

# ============================================
# МОНИТОРИНГ КАНАЛА
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
    logger.info(f"Новый пост в канале: {text[:100]}")
    comment = await get_ai_response(ADMIN_ID, f"Прокомментируй этот пост как эксперт по ставкам: {text}")
    await safe_send(TARGET_GROUP_ID, f"📢 **Новый пост в канале:**\n{text}\n\n💬 **Комментарий бота:**\n{comment}")

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
    answer = await get_ai_response(message.from_user.id, message.text)
    await safe_send(message.chat.id, answer, reply_to_message_id=message.message_id)

# ============================================
# ЛИЧНЫЕ СООБЩЕНИЯ
# ============================================
@dp.message()
async def private_response(message: types.Message):
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        return
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
    logger.info("🚀 Бот-эксперт с авто-поиском (SerpAPI) и разбивкой длинных сообщений запущен.")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())