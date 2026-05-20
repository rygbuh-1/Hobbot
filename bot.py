#!/usr/bin/env python3
"""
Telegram AI Bot with DeepSeek – мониторинг канала + сохранение истории в файл.
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

# Канал для мониторинга (посты отсюда)
MONITOR_CHANNEL_ID = -1003154677228
# Куда отправлять комментарии (группа)
TARGET_GROUP_ID = -1002688844179
MONITORING_ENABLED = True

# Файл для хранения истории разговоров
HISTORY_FILE = "history.json"

# Максимальное количество хранимых сообщений на пользователя (увеличено до 200)
MAX_HISTORY = 200

# Память диалога (загружается из файла при старте)
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
# ЗАГРУЗКА / СОХРАНЕНИЕ ИСТОРИИ
# ============================================
def load_history():
    global user_history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Преобразуем ключи из строк в int
                user_history = defaultdict(list, {int(k): v for k, v in data.items()})
                logger.info(f"Загружена история для {len(user_history)} пользователей")
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}")
    else:
        logger.info("Файл истории не найден, начинаем с пустой")

def save_history():
    try:
        # Преобразуем defaultdict в обычный dict с ключами-строками для JSON
        to_save = {str(k): v for k, v in user_history.items()}
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
        logger.debug("История сохранена")
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")

# Загружаем историю при старте
load_history()

# ============================================
# AI ОТВЕТ (с памятью, загруженной из файла)
# ============================================
async def get_ai_response(user_id: int, user_message: str, system_prompt: str = None) -> str:
    history = user_history[user_id]
    default_system = "Ты — дружелюбный, остроумный ИИ-ассистент. Отвечай естественно, как человек в чате. Пиши на русском, кратко и по делу."
    messages = [{"role": "system", "content": system_prompt or default_system}]
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
        # Обновляем историю
        user_history[user_id].append({"role": "user", "content": user_message})
        user_history[user_id].append({"role": "assistant", "content": answer})
        # Ограничиваем длину
        if len(user_history[user_id]) > MAX_HISTORY * 2:
            user_history[user_id] = user_history[user_id][-MAX_HISTORY*2:]
        # Сохраняем изменения в файл
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
    await message.answer("🤖 Бот активен. Отвечаю в группе, мониторю канал, запоминаю историю разговоров в файле.\n\nКоманды:\n/clear_history - очистить вашу историю\n/admin_stats - статистика")

@dp.message(Command("clear_history"))
async def clear_history(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_history:
        del user_history[user_id]
        save_history()
        await message.answer("✅ Ваша история диалогов очищена.")
    else:
        await message.answer("У вас нет сохранённой истории.")

@dp.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(f"Нет прав")
        return
    bot_info = await message.bot.get_me()
    await message.answer(
        f"✅ Статус\n"
        f"Бот: @{bot_info.username}\n"
        f"Мониторинг канала: {'ВКЛ' if MONITORING_ENABLED else 'ВЫКЛ'}\n"
        f"Канал: {MONITOR_CHANNEL_ID}\n"
        f"Группа: {TARGET_GROUP_ID}\n"
        f"Пользователей с историей: {len(user_history)}"
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
    await message.reply("✅ Бот работает")

# ============================================
# МОНИТОРИНГ НОВЫХ ПОСТОВ В КАНАЛЕ
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
    system_prompt = "Ты — эксперт, который комментирует посты в канале. Пиши интересно, кратко, иногда с юмором. Отвечай на русском."
    comment = await get_ai_response(ADMIN_ID, f"Прокомментируй этот пост: {text}", system_prompt)
    try:
        await bot.send_message(chat_id=TARGET_GROUP_ID, text=f"📢 Новый пост в канале:\n{text}\n\n💬 Комментарий бота:\n{comment}")
    except Exception as e:
        logger.error(f"Не удалось отправить комментарий в группу: {e}")

# ============================================
# ОБЫЧНОЕ ОБЩЕНИЕ В ГРУППЕ
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

    user_text = message.text or "Сообщение без текста"
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, user_text)
    await message.reply(answer)

# ============================================
# ОТВЕТЫ В ЛИЧКЕ
# ============================================
@dp.message()
async def private_response(message: types.Message):
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        return
    user_text = message.text or "Сообщение"
    await bot.send_chat_action(message.chat.id, "typing")
    answer = await get_ai_response(message.from_user.id, user_text)
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
    logger.info("🚀 Бот запущен. История сохраняется в файл, лимит памяти увеличен до 200 сообщений на пользователя.")
    await asyncio.gather(dp.start_polling(bot), run_http())

if __name__ == "__main__":
    asyncio.run(main())