import os
import asyncio
import yt_dlp
import subprocess
from dataclasses import dataclass
from src.config import conf

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
        Универсальная обработка: если нужен конкретный битрейт (сжатие) — используем его.
        Если нет — просто перекодируем в совместимый формат.
        """
        output_path = input_path.replace("raw_", "final_")
        
        # Базовая команда
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # МАКСИМАЛЬНАЯ СКОРОСТЬ
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', 'faststart'
        ]

        # Если нужно сжать под 50МБ
        if target_bitrate:
            cmd += ['-b:v', str(target_bitrate), '-maxrate', str(target_bitrate), '-bufsize', str(target_bitrate * 2)]
        else:
            cmd += ['-crf', '23'] # Хорошее качество по умолчанию

        cmd.append(output_path)
        
        # Запускаем один раз (1-pass)
        subprocess.run(cmd, capture_output=True)
        
        if os.path.exists(input_path):
            os.remove(input_path)
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:]
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_path_tmpl)) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                # Проверка существования
                if not os.path.exists(downloaded_path):
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"raw_{unique_id}")]
                    if not files: raise DownloadError("Файл не найден")
                    downloaded_path = os.path.join(self.download_path, files[0])

                file_size = os.path.getsize(downloaded_path)
                duration = info.get('duration', 0)
                
                target_bitrate = None
                # Если файл больше 50МБ, считаем битрейт для 1-pass сжатия
                if file_size > 50 * 1024 * 1024 and duration > 0:
                    target_size_bits = 45 * 1024 * 1024 * 8
                    target_bitrate = int(target_size_bits / duration)

                # Запускаем обработку (теперь это ВСЕГДА 1-pass и всегда ultrafast)
                final_path = self._process_video(downloaded_path, target_bitrate)

                return DownloadedVideo(
                    path=final_path,
                    title=info.get('title', 'Video'),
                    duration=int(duration),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0) or 0,
                    height=info.get('height', 0) or 0,
                    thumb_url=info.get('thumbnail', ''),
                    file_size=os.path.getsize(final_path)
                )

            except Exception as e:
                raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
