import os
import asyncio
import yt_dlp
from dataclasses import dataclass
from src.config import conf

# 1. Структура данных для возврата результата
# Это "паспорт" скачанного видео
@dataclass
class DownloadedVideo:
    path: str           # Путь к файлу на диске
    title: str          # Заголовок видео
    duration: int       # Длительность в секундах
    author: str         # Автор канала/аккаунта
    width: int          # Ширина (для правильного отображения плеера)
    height: int         # Высота
    thumb_url: str      # Ссылка на обложку
    file_size: int      # Размер файла в байтах

# 2. Исключения для обработки ошибок
class DownloadError(Exception):
    pass

class VideoTooBigError(Exception):
    pass

# 3. Основной класс загрузчика
class VideoDownloader:
    def __init__(self):
        # Настройки yt-dlp для максимальной совместимости
        self.ydl_opts = {
    # Формат: ищем лучшее видео (h264) и лучшее аудио (m4a/aac)
    # Это гарантирует воспроизведение на iPhone
    'format': 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]/best',
    
    'outtmpl': os.path.join(conf.download_path, '%(id)s.%(ext)s'),
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'geo_bypass': True,
    
    # Добавляем пост-обработку для исправления метаданных
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4',  # Убеждаемся, что на выходе MP4
    }],
    
    # Маскировка под браузер
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
}

    # Вспомогательный синхронный метод (запускается в отдельном потоке)
    def _download_sync(self, url: str) -> DownloadedVideo:
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                # Шаг 1: Извлекаем информацию без скачивания
                info = ydl.extract_info(url, download=False)
                
                # Проверка на стрим (их качать сложнее, пока пропустим)
                if info.get('is_live'):
                    raise DownloadError("Прямые эфиры пока не поддерживаются.")

                # Проверка примерного размера (если доступно)
                # filesize_approx может не быть, тогда рискуем и качаем
                estimated_size = info.get('filesize') or info.get('filesize_approx') or 0
                if estimated_size > conf.max_file_size:
                     raise VideoTooBigError(f"Видео слишком большое (~{estimated_size / 1024 / 1024:.1f} MB). Лимит: {conf.max_file_size / 1024 / 1024} MB")

                # Шаг 2: Скачиваем
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Проверяем реальный размер после скачивания
                real_size = os.path.getsize(filename)
                if real_size > conf.max_file_size:
                    os.remove(filename) # Удаляем, если превысили лимит
                    raise VideoTooBigError(f"Файл оказался слишком большим ({real_size / 1024 / 1024:.1f} MB).")

                return DownloadedVideo(
                    path=filename,
                    title=info.get('title', 'Video'),
                    duration=info.get('duration', 0),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0),
                    height=info.get('height', 0),
                    thumb_url=info.get('thumbnail', ''),
                    file_size=real_size
                )

            except yt_dlp.utils.DownloadError as e:
                raise DownloadError(f"Ошибка загрузки: {str(e)}")
            except VideoTooBigError:
                raise # Прокидываем эту ошибку дальше
            except Exception as e:
                raise DownloadError(f"Неизвестная ошибка: {str(e)}")

    # Асинхронная обертка — именно её мы будем вызывать в боте
    async def download(self, url: str) -> DownloadedVideo:
        # Запускаем тяжелую задачу в отдельном потоке, чтобы бот не тупил
        return await asyncio.to_thread(self._download_sync, url)
