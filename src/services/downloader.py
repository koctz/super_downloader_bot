import os
import asyncio
import yt_dlp
import subprocess
import random
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
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url: url = url.replace("vk.ru", "vk.com")
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    def _get_opts(self, url, filename_tmpl):
        # Базовые настройки для всех сайтов
        opts = {
            'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'user_agent': random.choice(self.user_agents),
            'wait_for_video_data': 5,
        }

        # Настройки для INSTAGRAM (требует куки и реферер)
        if "instagram.com" in url:
            cookies_path = os.path.join(os.getcwd(), "cookies.txt")
            if os.path.exists(cookies_path):
                opts['cookiefile'] = cookies_path
            opts['http_headers'] = {
                'Referer': 'https://www.instagram.com/',
                'Origin': 'https://www.instagram.com',
            }

        # Настройки для TIKTOK (аккаунт не нужен, нужны спец. аргументы)
        elif "tiktok.com" in url:
            opts['extractor_args'] = {'tiktok': {'webpage_download': True}}
            # Для тиктока часто лучше использовать мобильный UA
            opts['user_agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'

        # Настройки для YOUTUBE
        elif "youtube.com" in url or "youtu.be" in url:
            opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}

        return opts

    def _process_video(self, input_path, duration):
        """Обработка FFmpeg: сжатие под лимит 50МБ и исправление формата"""
        base = os.path.basename(input_path).replace("raw_", "final_")
        if not base.endswith(".mp4"):
            base = os.path.splitext(base)[0] + ".mp4"
            
        output_path = os.path.join(self.download_path, base)
        file_size = os.path.getsize(input_path)

        # Если файл больше 48МБ, сжимаем
        if file_size > 48 * 1024 * 1024:
            target_bitrate = int((43 * 1024 * 1024 * 8) / max(duration, 1))
            print(f"DEBUG: Файл большой ({file_size}), сжимаем до битрейта {target_bitrate}")
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "libx264", "-preset", "ultrafast", "-b:v", str(target_bitrate),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "faststart", output_path
            ]
        else:
            # Даже если размер норм, пересобираем для iPhone (pix_fmt yuv420p)
            print(f"DEBUG: Копируем/быстрая обработка")
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-movflags", "faststart", output_path
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass

        if result.returncode != 0:
            raise DownloadError(f"FFmpeg error: {result.stderr[:200]}")

        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(hash(url))[-8:]
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        opts = self._get_opts(url, temp_path_tmpl)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                print(f"DEBUG: Начинаю yt-dlp загрузку: {url}")
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                # Иногда yt-dlp меняет расширение в процессе
                if not os.path.exists(downloaded_path):
                    possible_files = [f for f in os.listdir(self.download_path) if unique_id in f]
                    if possible_files:
                        downloaded_path = os.path.join(self.download_path, possible_files[0])
                    else:
                        raise DownloadError("Файл не найден после загрузки")

                duration = info.get("duration", 0)
                final_path = self._process_video(downloaded_path, duration)

                return DownloadedVideo(
                    path=final_path,
                    title=info.get("title", "Video"),
                    duration=int(duration or 0),
                    author=info.get("uploader", "Unknown"),
                    width=info.get("width", 0) or 0,
                    height=info.get("height", 0) or 0,
                    thumb_url=info.get("thumbnail", ""),
                    file_size=os.path.getsize(final_path),
                )

        except Exception as e:
            print(f"DEBUG ERROR: {e}")
            raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
