from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from config import REQUIRE_SUBSCRIPTION, CHANNEL_ID

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        if not REQUIRE_SUBSCRIPTION or not CHANNEL_ID:
            return await handler(event, data)
        
        user_id = event.from_user.id
        bot = event.bot
        
        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                return await handler(event, data)
            else:
                await event.answer(
                    f"❌ Для использования бота необходимо подписаться на наш канал: https://t.me/..."
                    # Замените ... на username канала
                )
                return
        except Exception:
            # Если ошибка (канал не найден и т.д.), пропускаем проверку
            return await handler(event, data)