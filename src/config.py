import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

@dataclass
class Config:
    bot_token: str
    download_path: str
    max_file_size: int  # В байтах

# Создаем экземпляр конфига
# Если токена нет - бот упадет сразу с понятной ошибкой, а не потом
token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("Переменная BOT_TOKEN не найдена в .env файле!")

conf = Config(
    bot_token=token,
    download_path=os.path.join(os.getcwd(), "downloads"),
    max_file_size=50 * 1024 * 1024  # 50 MB по умолчанию
)

# Автосоздание папки загрузок при старте
if not os.path.exists(conf.download_path):
    os.makedirs(conf.download_path)
