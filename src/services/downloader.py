import os
import asyncio
import yt_dlp
import subprocess
from dataclasses import dataclass
from src.config import conf

# Исключения для обработки ошибок
class DownloadError(Exception):
    pass

class VideoTooBigError(Exception):
    pass

@dataclass
class DownloadedVideo:
    path: str           # Путь к файлу на диске
    title: str          # Заголовок видео
    duration: int       # Длительность в секундах
    author: str         # Автор
    width: int          # Ширина
    height: int         # Высота
    thumb_url: str      # Ссылка на обложку
    file_size: int      # Размер файла в байтах

class VideoDownloader:
    def __init__(self):
        self.download_path = conf.download_path

    def _get_opts(self, filename):
        """Базовые настройки yt-dlp"""
        return {
            # Просим лучшее качество до 1080p
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            'outtmpl': filename,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    def _compress_video(self, input_path):
        """Принудительное сжатие видео до ~45MB через FFmpeg (2-pass)"""
        output_path = input_path.replace(".mp4", "_compressed.mp4")
        
        # 1. Получаем длительность видео через ffprobe
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        try:
            duration = float(probe.stdout.strip())
        except:
            duration = 10 # Заглушка, если не удалось определить

        # 2. Рассчитываем битрейт для попадания в 45МБ (с запасом)
        # Формула: (Размер в битах) / длительность
        target_size_bits = 45 * 1024 * 1024 * 8
        bitrate = int(target_size_bits / duration)

        # 3. Первый проход (анализ)
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-b:v', str(bitrate),
            '-preset', 'veryfast', '-pass', '1', '-an', '-f', 'mp4', '/dev/null'
        ])
        
        # 4. Второй проход (создание файла) + фикс для iPhone (yuv420p)
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-b:v', str(bitrate),
            '-preset', 'veryfast', '-pass', '2',
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p', '-movflags', 'faststart',
            output_path
        ])
        
        # Удаляем временные логи первого прохода и оригинал
        if os.path.exists("ffmpeg2pass-0.log"): os.remove("ffmpeg2pass-0.log")
        if os.path.exists("ffmpeg2pass-0.log.mbtree"): os.remove("ffmpeg2pass-0.log.mbtree")
        os.remove(input_path)
        
        return output_path

def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:]
        # Указываем только шаблон папки и ID, расширение пусть выберет yt-dlp
        temp_path_template = os.path.join(self.download_path, f"video_{unique_id}.%(ext)s")
        
        opts = self._get_opts(temp_path_template)
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                # 1. Извлекаем инфо и скачиваем
                info = ydl.extract_info(url, download=True)
                
                # 2. Получаем РЕАЛЬНЫЙ путь к скачанному файлу
                path = ydl.prepare_filename(info)
                
                # Если файл скачался, но под другим расширением (например .webp или .mkv)
                # или если yt-dlp не обновил путь в переменной:
                if not os.path.exists(path):
                    # Ищем файл в папке downloads, который начинается на наш ID
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"video_{unique_id}")]
                    if not files:
                        raise DownloadError("Файл не найден после загрузки.")
                    path = os.path.join(self.download_path, files[0])

                # 3. Принудительная конвертация в MP4 (если это не MP4) или фикс кодеков
                # Даже если это mp4, прогоним через быстрый ремукс для фикса метаданных
                final_mp4 = os.path.join(self.download_path, f"final_{unique_id}.mp4")
                
                # Используем ffmpeg для гарантии совместимости с iPhone и исправления контейнера
                subprocess.run([
                    'ffmpeg', '-y', '-i', path,
                    '-c', 'copy', # Копируем потоки без перекодировки (быстро)
                    '-movflags', 'faststart', 
                    final_mp4
                ], capture_output=True)

                # Удаляем промежуточный файл
                if os.path.exists(path) and path != final_mp4:
                    os.remove(path)
                
                path = final_mp4
                file_size = os.path.getsize(path)

                # 4. Проверка лимита 50МБ и запуск сжатия если нужно
                if file_size > 50 * 1024 * 1024:
                    path = self._compress_video(path)
                    file_size = os.path.getsize(path)

                return DownloadedVideo(
                    path=path,
                    title=info.get('title', 'Video'),
                    duration=int(info.get('duration', 0)),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0) or 0,
                    height=info.get('height', 0) or 0,
                    thumb_url=info.get('thumbnail', ''),
                    file_size=file_size
                )

            except Exception as e:
                # Очистка при ошибке
                if 'path' in locals() and os.path.exists(path):
                    os.remove(path)
                raise DownloadError(f"Ошибка: {str(e)}")

    async def download(self, url: str) -> DownloadedVideo:
        """Асинхронная обертка для запуска в потоке"""
        return await asyncio.to_thread(self._download_sync, url)
