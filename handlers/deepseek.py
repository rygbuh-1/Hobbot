from aiogram import Router, types
from aiogram.filters import Command
from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY

router = Router()
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Привет! Я ИИ-бот на движке DeepSeek.\n"
        "Просто напиши мне любое сообщение, и я отвечу.\n\n"
        "📌 Команды:\n"
        "/start - показать это сообщение\n"
        "/help - справка\n"
        "/about - информация о боте\n\n"
        "👑 Администратору: используйте /admin_stats для статистики"
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 Справка:\n"
        "Я отвечаю на любые текстовые сообщения, используя нейросеть DeepSeek.\n"
        "Модель: deepseek-chat\n\n"
        "Просто напиши вопрос или фразу — я постараюсь помочь."
    )

@router.message(Command("about"))
async def cmd_about(message: types.Message):
    await message.answer(
        "ℹ️ Бот создан с помощью BetterDeepSeek.\n"
        "Использует API DeepSeek.\n"
        "Включены функции администрирования канала и модерации."
    )

@router.message()
async def handle_message(message: types.Message):
    if not message.text:
        return
    
    # Показываем статус "печатает"
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты — дружелюбный и полезный ИИ-ассистент. Отвечай кратко и по делу, на русском языке."},
                {"role": "user", "content": message.text}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        answer = response.choices[0].message.content
        await message.reply(answer)
    except Exception as e:
        await message.reply(f"⚠️ Ошибка DeepSeek: {str(e)}")