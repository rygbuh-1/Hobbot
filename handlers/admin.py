from aiogram import Router, types, F
from aiogram.filters import Command
from config import ADMIN_IDS, CHANNEL_ID, GROUP_ID

router = Router()

# Фильтр для проверки прав администратора
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        f"🤖 *Статистика бота:*\n"
        f"ID бота: {message.bot.id}\n"
        f"Имя: @{message.bot.username}\n"
        f"Администраторы: {', '.join(map(str, ADMIN_IDS))}\n"
        f"Канал: {CHANNEL_ID if CHANNEL_ID else 'не задан'}\n"
        f"Группа: {GROUP_ID if GROUP_ID else 'не задана'}",
        parse_mode="Markdown"
    )

@router.message(Command("post"))
async def send_post(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not CHANNEL_ID:
        await message.answer("❌ ID канала не задан в конфиге.")
        return
    text = message.text.replace("/post", "", 1).strip()
    if not text:
        await message.answer("Укажите текст поста после команды.\nПример: /post Привет, канал!")
        return
    try:
        sent = await message.bot.send_message(chat_id=CHANNEL_ID, text=text)
        await message.answer(f"✅ Пост отправлен в канал. ID сообщения: {sent.message_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("pin"))
async def pin_message(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not CHANNEL_ID:
        await message.answer("❌ ID канала не задан.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID сообщения.\nПример: /pin 123")
        return
    msg_id = int(parts[1])
    try:
        await message.bot.pin_chat_message(chat_id=CHANNEL_ID, message_id=msg_id)
        await message.answer(f"✅ Сообщение {msg_id} закреплено в канале.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("unpin"))
async def unpin_message(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not CHANNEL_ID:
        await message.answer("❌ ID канала не задан.")
        return
    try:
        await message.bot.unpin_chat_message(chat_id=CHANNEL_ID)
        await message.answer("✅ Закреплённое сообщение откреплено.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("ban"))
async def ban_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not GROUP_ID:
        await message.answer("❌ ID группы не задан для модерации.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID пользователя.\nПример: /ban 123456789")
        return
    user_id = int(parts[1])
    try:
        await message.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await message.answer(f"✅ Пользователь {user_id} забанен в группе.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("unban"))
async def unban_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not GROUP_ID:
        await message.answer("❌ ID группы не задан.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID пользователя.\nПример: /unban 123456789")
        return
    user_id = int(parts[1])
    try:
        await message.bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await message.answer(f"✅ Пользователь {user_id} разбанен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("check_sub"))
async def check_subscription(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not CHANNEL_ID:
        await message.answer("❌ ID канала не задан.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Укажите ID пользователя.\nПример: /check_sub 123456789")
        return
    user_id = int(parts[1])
    try:
        member = await message.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
        await message.answer(f"Пользователь {user_id} подписан на канал: {'✅ да' if is_member else '❌ нет'}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")