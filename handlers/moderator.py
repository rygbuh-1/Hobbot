from aiogram import Router, types
from aiogram.filters import Command
from config import ENABLE_MODERATION, FORBIDDEN_WORDS, ADMIN_IDS, GROUP_ID

router = Router()

@router.message()
async def moderate_message(message: types.Message):
    # Работаем только в указанной группе (если задана)
    if GROUP_ID and message.chat.id != int(GROUP_ID):
        return
    if not ENABLE_MODERATION:
        return
    # Пропускаем сообщения администраторов
    if message.from_user.id in ADMIN_IDS:
        return
    text = message.text or message.caption or ""
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in text_lower:
            await message.delete()
            await message.answer(f"⚠️ Сообщение от {message.from_user.full_name} удалено (запрещённое слово: {word})")
            return
    # Дополнительно: удаление ссылок (простой пример)
    if "http://" in text_lower or "https://" in text_lower or "t.me/" in text_lower:
        # Проверяем, не является ли ссылка разрешённой (можно настроить белый список)
        await message.delete()
        await message.answer(f"⚠️ Сообщение от {message.from_user.full_name} удалено (ссылки запрещены)")
        return