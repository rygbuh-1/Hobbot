#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – Эксперт по ставкам на спорт (без авто-поиска, с запросом источников).
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
# СИСТЕМНЫЙ ПРОМПТ ЭКСПЕРТА (без авто-поиска, требует источники)
# ============================================
EXPERT_PROMPT = """Ты — профессиональный эксперт в области ставок на спорт.
Твоя задача — анализировать матчи и давать советы, строго следуя методологии из 5 шагов.

ВАЖНЕЙШЕЕ ПРАВИЛО: Ты НЕ ИЩЕШЬ информацию в интернете самостоятельно. Если у тебя нет актуальных данных о травмах, составах, мотивации — ты ДОЛЖЕН запросить их у пользователя. Не выдумывай факты, не гадай.

Когда пользователь предоставляет ссылки или конкретную информацию — используй их как источник. Указывай, откуда взяты данные (например: «согласно ссылке 1»). Если пользователь не дал источники, а ты не уверен — честно скажи, что информации недостаточно, и попроси предоставить ссылки на новости или официальные составы.

Методология (выполняй последовательно):
1. Кадровый аудит (травмы, дисквы) — нужны источники.
2. Прогноз состава и тактики — основывайся на новостях или прошлых матчах.
3. Турнирная мотивация — проверяй таблицу, положение команд.
4. Фактор усталости (календарь, перелёты) — запрашивай данные.
5. Верификация за час до игры — смотри официальные составы.

Если пользователь не предоставил никакой информации, задай уточняющие вопросы: какой матч, когда, какие есть новости, ссылки.

Ты должен быть максимально полезным и точным, но никогда не жертвовать правдивостью. Лучше сказать «я не знаю, нужны источники», чем дать ложный прогноз."""

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
# AI ОТВЕТ (без поиска)
# ============================================
async def get_ai_response(user_id: int, user_message: str) -> str:
    history = user_history[user_id]
    messages = [{"role": "system", "content": EXPERT_PROMPT}]
    messages.extend(history[-20:])  # последние 20 сообщений для контекста
    messages.append({"role": "user", "content": user_message})
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=1500
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
    await message.answer(
        "🤖 Эксперт по ставкам на спорт.\n"
        "Присылайте матчи и ссылки на новости (травмы, составы).\n"
        "Я не ищу информацию сам — вы должны предоставить источники, чтобы я мог дать точный прогноз по методологии.\n\n"
        "Команды:\n"
        "/clear_history – очистить историю\n"
        "/admin_stats – статистика (админ)\n"
        "/toggle_monitor – вкл/выкл мониторинг канала"
    )

@dp.message(Command("clear_history"))
async def clear_history(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history:
        del user_history[user_id]
        save_history()
        await message.answer("✅ История очищена.")
    else:
        await message.answer("Нет сохранённой истории.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет прав.")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"Статус бота\n"
        f"Username: @{bot_info.username}\n"
        f"Мониторинг: {'ВКЛ' if MONITORING_ENABLED else 'ВЫКЛ'}\n"
        f"Пользователей: {len(user_history)}"
    )

@dp.message(Command("toggle_monitor"))
async def toggle_monitor(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global MONITORING_ENABLED
    MONITORING_ENABLED = not MONITORING_ENABLED
    await message.answer(f"Мониторинг канала {'включён' if MONITORING_ENABLED else 'выключен'}.")

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
    comment = await get_ai_response(ADMIN_ID, f"Проанализируй этот пост как эксперт по ставкам. Пост: {text}")
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
    answer = await get_ai_response(message.from_user.id, message.text)
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
    logger.info("🚀 Бот-эксперт (без авто-поиска, запрашивает источники) запущен.")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())