import asyncio
import logging
from src.bot import start_bot

# Настройка логирования (чтобы видеть ошибки в консоли)
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("🛑 Бот остановлен!")
