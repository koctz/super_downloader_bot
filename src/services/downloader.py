import os
import asyncio
import yt_dlp
import subprocess
import random
import aiohttp
import time
import re
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
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url: url = url.replace("vk.ru", "vk.com")
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    # НОВЫЙ МЕТОД: Получение доступных разрешений для YouTube
    async def get_formats(self, url: str):
        url = self._normalize_url(url)
        if "youtube.com" not in url and "youtu.be" not in url:
            return None
        if "watch?v=" not in url: # Для Shorts оставляем стандарт
            return None

        def extract():
            opts = self._get_opts(url, "")
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(extract)
            formats = []
            seen_heights = set()
            allowed_heights = [360, 480, 720, 1080]
            
            for f in info.get('formats', []):
                h = f.get('height')
                if h in allowed_heights and h not in seen_heights:
                    if f.get('vcodec') != 'none': # Только видео дорожки
                        seen_heights.add(h)
            
            if not seen_heights: return None

            return {
                "formats": sorted(list(seen_heights)),
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "Unknown"),
                "uploader_url": info.get("uploader_url", "")
            }
        except:
            return None

    def _process_audio(self, input_path):
        base = os.path.basename(input_path)
        output_path = os.path.join(self.download_path, os.path.splitext(base)[0] + ".mp3")
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path]
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass
        return output_path

    def _process_video(self, input_path, duration, is_insta=False):
        base = os.path.basename(input_path).replace("raw_", "final_")
        if not base.endswith(".mp4"):
            base = os.path.splitext(base)[0] + ".mp4"
        output_path = os.path.join(self.download_path, base)
        
        if not os.path.exists(input_path):
            return input_path

        file_size = os.path.getsize(input_path)
        MTPROTO_LIMIT = 1950 * 1024 * 1024 
        
        if file_size <= MTPROTO_LIMIT and not is_insta:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-map_metadata", "0", "-movflags", "+faststart", output_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", "scale='trunc(oh*a/2)*2:720',setsar=1", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path]

        try:
            subprocess.run(cmd, capture_output=True, timeout=600)
        except:
            pass
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass
        return output_path

    def _get_opts(self, url, filename_tmpl, quality=None):
        # Если передано качество, формируем спец. строку формата
        if quality:
            fmt = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
        else:
            fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'

        opts = {
            'format': fmt,
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'user_agent': random.choice(self.user_agents),
        }
        if "instagram.com" in url:
            cookies_path = os.path.join(os.getcwd(), "cookies.txt")
            if os.path.exists(cookies_path): opts['cookiefile'] = cookies_path
        elif "youtube.com" in url or "youtu.be" in url:
            opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}
        return opts

    # ОБНОВЛЕННЫЙ МЕТОД: принимает параметр quality
    async def download(self, url: str, mode: str = 'video', progress_callback=None, quality=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url)))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")
        loop = asyncio.get_running_loop()

        if "tiktok.com" in url:
            data = await self._download_tiktok_via_api(url, temp_path)
        else:
            data = await asyncio.to_thread(self._download_sync, url, temp_path, progress_callback, loop, quality)

        if mode == 'audio':
            audio_path = self._process_audio(data.path)
            data.path = audio_path
            data.file_size = os.path.getsize(audio_path)
        return data

    def _download_sync(self, url: str, temp_path_raw: str, progress_callback=None, loop=None, quality=None) -> DownloadedVideo:
        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback and loop:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(progress_callback(clean_p))
                )

        opts = self._get_opts(url, temp_path_raw, quality=quality)
        opts['progress_hooks'] = [ydl_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            
            # Проверка расширения (yt-dlp может изменить mp4 на mkv)
            if not os.path.exists(downloaded_path):
                base_no_ext = os.path.splitext(downloaded_path)[0]
                for ext in [".mp4", ".mkv", ".webm"]:
                    if os.path.exists(base_no_ext + ext):
                        downloaded_path = base_no_ext + ext
                        break

            duration = info.get("duration", 0)
            is_insta = "instagram" in (info.get("extractor", "") or "").lower()
            final_path = self._process_video(downloaded_path, duration, is_insta=is_insta)

            return DownloadedVideo(
                path=final_path, title=info.get("title", "Video"),
                duration=int(duration or 0), author=info.get("uploader", "Unknown"),
                width=info.get("width", 0), height=info.get("height", 0),
                thumb_url=info.get("thumbnail", ""), file_size=os.path.getsize(final_path)
            )

    async def _download_tiktok_via_api(self, url: str, temp_path: str) -> DownloadedVideo:
        api_url = "https://www.tikwm.com/api/"
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, data={'url': url}) as response:
                res = await response.json()
                if res.get('code') != 0:
                    raise DownloadError(f"TikTok API Error: {res.get('msg')}")
                data = res['data']
                video_url = data.get('play')
                async with session.get(video_url) as video_res:
                    with open(temp_path, 'wb') as f:
                        f.write(await video_res.read())
                duration = data.get('duration', 0)
                final_path = self._process_video(temp_path, duration)
                return DownloadedVideo(
                    path=final_path, title=data.get('title', 'TikTok Video'),
                    duration=int(duration), author=data.get('author', {}).get('nickname', 'TikTok User'),
                    width=data.get('width', 0), height=data.get('height', 0),
                    thumb_url=data.get('cover', ''), file_size=os.path.getsize(final_path)
                )
