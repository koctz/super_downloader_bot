import os
import asyncio
import yt_dlp
import subprocess
import random
import aiohttp
import re
import time
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
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
            
        # Устанавливаем путь к Node.js через переменную окружения (фикс ошибки флага)
        os.environ["YT_DLP_JS_EXECUTOR"] = "/usr/bin/node"

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    def _get_opts(self, url, filename_tmpl, quality=None):
        is_yt = "youtube.com" in url or "youtu.be" in url
        cookies = os.path.join(os.getcwd(), "cookies.txt")
        
        # Формат: ищем MP4 для легкой склейки и совместимости с ТГ
        if is_yt:
            if quality:
                fmt = f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best"
            else:
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        else:
            fmt = "bestvideo+bestaudio/best"

        opts = {
            "format": fmt,
            "outtmpl": filename_tmpl,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "quiet": False,
            "nocheckcertificate": True,
            "rm_cachedir": True,
            "cookiefile": cookies if os.path.exists(cookies) else None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

        if is_yt:
            opts["extractor_args"] = {
                "youtube": {
                    # ВКЛЮЧАЕМ OAUTH2 - это решит проблему "Requested format is not available"
                    "oauth2": True,
                    "player_client": ["tv", "web"],
                }
            }
        return opts

    async def get_yt_resolutions(self, url: str):
        url = self._normalize_url(url)
        opts = self._get_opts(url, "temp")
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    res = {f.get('height') for f in info.get('formats', []) if f.get('height') and f.get('height') >= 360}
                    return sorted(list(res), reverse=True) if res else [1080, 720, 360]
                except: return [1080, 720, 360]
        return await asyncio.to_thread(extract)

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        # Используем шаблон для расширения, так как yt-dlp может менять его при мердже
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        loop = asyncio.get_running_loop()
        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_callback(clean_p)))

        opts = self._get_opts(url, temp_path_tmpl, quality)
        opts['progress_hooks'] = [ydl_hook]

        def run_dl():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
                # Проверка реального пути (если расширение изменилось на .mkv или .webm)
                if not os.path.exists(path):
                    for e in ['.mp4', '.mkv', '.webm']:
                        if os.path.exists(os.path.splitext(path)[0] + e):
                            path = os.path.splitext(path)[0] + e
                            break
                return info, path

        info, downloaded_path = await asyncio.to_thread(run_dl)
        
        final_path = os.path.join(self.download_path, f"final_{unique_id}.mp4")
        if mode == 'audio':
            final_path = final_path.replace(".mp4", ".mp3")
            cmd = ["ffmpeg", "-y", "-i", downloaded_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", final_path]
        else:
            # Принудительная пересборка в MP4 для Телеграм
            cmd = ["ffmpeg", "-y", "-i", downloaded_path, "-c", "copy", "-movflags", "+faststart", final_path]
        
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(downloaded_path):
            try: os.remove(downloaded_path)
            except: pass

        return DownloadedVideo(
            path=final_path,
            title=info.get("title", "Video"),
            duration=int(info.get("duration") or 0),
            author=info.get("uploader", "Unknown"),
            width=info.get("width", 0),
            height=info.get("height", 0),
            thumb_url=info.get("thumbnail", ""),
            file_size=os.path.getsize(final_path)
        )
