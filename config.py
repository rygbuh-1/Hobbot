import os

# Telegram Bot Token (лучше задать через переменную окружения)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8535231779:AAFU4goz5X8ZqgDJV4MKzXyHDEHWpAEvbD0")

# DeepSeek API Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-3ff13ab1a93f4a099554f788b553e5e0")

# ID администратора (вы)
ADMIN_IDS = [682446170]  # ваш Telegram ID

# ID канала, который будет администрировать бот (пример: -1001234567890)
# Узнать ID канала можно, переслав любое сообщение из канала боту @userinfobot
CHANNEL_ID = os.getenv("-1003154677228", None)  # Замените на ваш ID канала

# ID супергруппы, привязанной к каналу (для модерации)
GROUP_ID = os.getenv("-1002688844179", None)

# Включить обязательную подписку на канал перед использованием бота
REQUIRE_SUBSCRIPTION = True

# Включить автоматическую модерацию (удаление ссылок/мата)
ENABLE_MODERATION = True

# Список запрещённых слов (можно добавить свои)
FORBIDDEN_WORDS = ["спам", "реклама", "мат"]

# Порт для health check сервера
PORT = int(os.getenv("PORT", "8080"))