import os
import asyncio
import yt_dlp
import subprocess
from dataclasses import dataclass
from src.config import conf

# Исключения
class DownloadError(Exception):
    pass

@dataclass
class DownloadedVideo:
    path: str
    title: str
    duration: int
    author: str
    width: int
    height: int
    thumb_url: str
    file_size: int

class VideoDownloader:
    def __init__(self):
        self.download_path = conf.download_path

    def _get_opts(self, filename_tmpl):
        """Настройки yt-dlp: ищем лучший h264 или просто лучшее видео до 1080p"""
        return {
            'format': 'bestvideo[vcodec^=avc1][height<=1080]+bestaudio[acodec^=mp4a]/best[height<=1080]/best',
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    def _process_video(self, input_path, target_bitrate=None):
        """
        Обработка видео через FFmpeg:
        1. Всегда перекодируем в h264 + aac + yuv420p (для iPhone).
        2. Если задан target_bitrate — сжимаем.
        3. Используем пресет ultrafast для скорости.
        """
        # Генерируем имя финального файла
        base_name = os.path.basename(input_path).replace("raw_", "final_")
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(self.download_path, f"{name_without_ext}.mp4")
        
        print(f"DEBUG: Начало обработки FFmpeg. Вход: {input_path}")
        
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast', 
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', 'faststart'
        ]

        if target_bitrate:
            print(f"DEBUG: Видео тяжелое, применяем сжатие. Битрейт: {target_bitrate}")
            cmd += [
                '-b:v', str(target_bitrate), 
                '-maxrate', str(target_bitrate), 
                '-bufsize', str(target_bitrate * 2)
            ]
        else:
            print("DEBUG: Видео легкое, просто фиксим формат под iPhone")
            cmd += ['-crf', '24']

        cmd.append(output_path)
        
        # Запуск FFmpeg с таймаутом 10 минут
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                print(f"DEBUG FFmpeg Error: {result.stderr}")
                raise DownloadError(f"Ошибка FFmpeg: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            print("DEBUG: FFmpeg завис по таймауту")
            raise DownloadError("Обработка видео заняла слишком много времени.")

        # Удаляем исходный "сырой" файл сразу после успеха
        if os.path.exists(input_path):
            os.remove(input_path)
            print(f"DEBUG: Удален временный файл {input_path}")
            
        print(f"DEBUG: Обработка завершена. Выход: {output_path}")
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        """Синхронная логика скачивания"""
        unique_id = str(hash(url))[-8:]
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        print(f"DEBUG: Запуск yt-dlp для {url}")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_path_tmpl)) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                # Если файл скачался с другим расширением, находим его
                if not os.path.exists(downloaded_path):
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"raw_{unique_id}")]
                    if not files:
                        raise DownloadError("Не удалось найти скачанный файл.")
                    downloaded_path = os.path.join(self.download_path, files[0])

                original_size = os.path.getsize(downloaded_path)
                duration = info.get('duration', 0)
                
                print(f"DEBUG: Скачано. Размер: {original_size} байт, Длительность: {duration} сек.")

                target_bitrate = None
                # Если файл больше 48МБ (с запасом), считаем битрейт для сжатия до ~42МБ
                if original_size > 48 * 1024 * 1024 and duration > 0:
                    # Целевой размер 42МБ в битах
                    target_size_bits = 42 * 1024 * 1024 * 8
                    target_bitrate = int(target_size_bits / duration)
                    # Если битрейт вышел слишком низким, ставим минимум для хоть какого-то качества
                    if target_bitrate < 150000: target_bitrate = 150000

                # Обработка через FFmpeg
                final_path = self._process_video(downloaded_path, target_bitrate)

                return DownloadedVideo(
                    path=final_path,
                    title=info.get('title', 'Video'),
                    duration=int(duration or 0),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0) or 0,
                    height=info.get('height', 0) or 0,
                    thumb_url=info.get('thumbnail', ''),
                    file_size=os.path.getsize(final_path)
                )

            except Exception as e:
                print(f"DEBUG ERROR в _download_sync: {e}")
                # Чистим мусор при ошибке
                for f in os.listdir(self.download_path):
                    if unique_id in f:
                        try: os.remove(os.path.join(self.download_path, f))
                        except: pass
                raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        """Асинхронный вызов"""
        return await asyncio.to_thread(self._download_sync, url)
