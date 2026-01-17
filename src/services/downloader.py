import os
import asyncio
import yt_dlp
import subprocess
from dataclasses import dataclass
from src.config import conf

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

    def _get_opts(self, filename):
        return {
            # Выбираем лучшее качество, но ограничиваем его, чтобы не качать 4К
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            'outtmpl': filename,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            # Маскировка под браузер
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    def _compress_video(self, input_path):
        """Принудительное сжатие видео до ~48MB через FFmpeg"""
        output_path = input_path.replace(".mp4", "_compressed.mp4")
        
        # Получаем длительность видео для расчета битрейта
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        duration = float(probe.stdout)
        
        # Рассчитываем битрейт (цель 45МБ, чтобы был запас), битрейт в битах в секунду
        # (45 * 1024 * 1024 * 8) / duration
        target_size_bits = 45 * 1024 * 1024 * 8
        bitrate = int(target_size_bits / duration)

        # Запуск сжатия
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-b:v', str(bitrate),
            '-preset', 'veryfast', '-pass', '1', '-an', '-f', 'mp4', '/dev/null'
        ])
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-b:v', str(bitrate),
            '-preset', 'veryfast', '-pass', '2',
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p', '-movflags', 'faststart',
            output_path
        ])
        
        # Удаляем оригинал, возвращаем путь к сжатому
        os.remove(input_path)
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:] # Короткий ID для файла
        temp_filename = os.path.join(self.download_path, f"temp_{unique_id}.mp4")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_filename)) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            
            # Если файл все равно в другом расширении (mkv/webm), фиксим это
            if not path.endswith('.mp4'):
                new_path = path.rsplit('.', 1)[0] + ".mp4"
                subprocess.run(['ffmpeg', '-i', path, '-c', 'copy', new_path])
                os.remove(path)
                path = new_path

            file_size = os.path.getsize(path)

            # ПРОВЕРКА РАЗМЕРА И СЖАТИЕ
            if file_size > 50 * 1024 * 1024:
                # Если видео больше 50МБ, сжимаем его
                path = self._compress_video(path)
                file_size = os.path.getsize(path)

            return DownloadedVideo(
                path=path,
                title=info.get('title', 'Video'),
                duration=int(info.get('duration', 0)),
                author=info.get('uploader', 'Unknown'),
                width=info.get('width', 0),
                height=info.get('height', 0),
                thumb_url=info.get('thumbnail', ''),
                file_size=file_size
            )

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
