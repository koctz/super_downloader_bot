import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

@dataclass
class Config:
    bot_token: str
    download_path: str
    max_file_size: int
    channel_id: str   # Добавили ID канала
    channel_url: str  # Добавили ссылку на канал
    admin_id: str  # Добавь это поле
    users_db_path: str # Добавь путь к файлу пользователей

# Проверка токена
token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("Переменная BOT_TOKEN не найдена в .env файле!")

# Получаем данные канала (можно добавить дефолтные значения, чтобы не упало, если забыл прописать)
channel_id = os.getenv("CHANNEL_ID", "-100123456789")
channel_url = os.getenv("CHANNEL_URL", "https://t.me/your_channel")

conf = Config(
    bot_token=token,
    download_path=os.path.join(os.getcwd(), "downloads"),
    max_file_size=50 * 1024 * 1024,
    channel_id=channel_id,
    channel_url=channel_url
    admin_id=os.getenv("ADMIN_ID"),
    users_db_path=os.path.join(os.getcwd(), "data", "users.txt") # Путь к файлу
)

# Автосоздание папки data
data_dir = os.path.join(os.getcwd(), "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Автосоздание папки загрузок
if not os.path.exists(conf.download_path):
    os.makedirs(conf.download_path)
