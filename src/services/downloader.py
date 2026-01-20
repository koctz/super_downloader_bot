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
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url: url = url.replace("vk.ru", "vk.com")
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url
        
    async def get_yt_resolutions(self, url: str):
        """Метод специально для YouTube: вытягивает только реально доступные разрешения"""
        url = self._normalize_url(url)
        opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': random.choice(self.user_agents),
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None
        }
        
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                available_heights = set()
                for f in formats:
                    h = f.get('height')
                    # Фильтруем только видео-потоки
                    if h and h >= 360 and f.get('vcodec') != 'none':
                        available_heights.add(h)
                return sorted(list(available_heights), reverse=True)
        
        return await asyncio.to_thread(extract)
    
    async def get_video_info(self, url: str):
        url = self._normalize_url(url)
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(self._get_info_sync, url)

    def _get_info_sync(self, url: str):
        opts = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
            'user_agent': random.choice(self.user_agents),
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                thumb = info.get('thumbnail')
                if not thumb and info.get('thumbnails'):
                    thumb = info['thumbnails'][-1].get('url')
                
                return {
                    'title': info.get('title', 'Video'),
                    'thumbnail': thumb,
                    'duration': info.get('duration')
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
        ext = os.path.splitext(base)[1].lower()
        output_path = os.path.join(self.download_path, base)

        if not os.path.exists(input_path):
            return input_path

        # Если это MP4, делаем faststart для стриминга в ТГ
        if ext == ".mp4":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-movflags", "+faststart", output_path]
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(output_path):
                os.remove(input_path)
                return output_path

        # Для MKV/WebM просто переносим (ТГ их поддерживает как файлы или видео)
        if ext in [".webm", ".mkv"]:
            os.rename(input_path, output_path)
            return output_path

        return input_path

    def _get_opts(self, url, filename_tmpl, quality=None):
        url = url.strip()
        is_yt = ("youtube.com" in url) or ("youtu.be" in url)
        
        if is_yt and quality and quality.isdigit():
            q = int(quality)
            # Принудительно исключаем формат 18, чтобы yt-dlp даже не смотрел на него
            fmt = f"bestvideo[height<={q}][format_id!=18]+bestaudio/best[height<={q}][format_id!=18]"
        elif "instagram.com" in url or "vk.com" in url:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        else:
            fmt = "bestvideo+bestaudio/best"

        opts = {
            "format": fmt,
            "outtmpl": filename_tmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False, # Выключаем quiet, чтобы видеть ошибки если что
            "merge_output_format": "mp4",
            "user_agent": random.choice(self.user_agents),
            "rm_cachedir": True,
        }

        if is_yt:
            # 🔥 КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: используем ios и web_creator
            # Это обходит проблему с PO Token в 99% случаев
            opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["ios", "web_creator"],
                }
            }
        
        if ("instagram.com" in url) and os.path.exists("cookies.txt"):
            opts["cookiefile"] = "cookies.txt"

        return opts

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        q_suffix = quality if quality else "max"
        
        # Временный путь (yt-dlp сам добавит расширение при мердже)
        temp_path = os.path.join(self.download_path, f"raw_{q_suffix}_{unique_id}")
        loop = asyncio.get_running_loop()

        if "tiktok.com" in url and mode != 'audio':
            try:
                # ТикТок через API обычно быстрее и без ватермарок
                data = await self._download_tiktok_via_api(url, temp_path + ".mp4")
                return data
            except:
                pass

        data = await asyncio.to_thread(self._download_sync, url, temp_path, quality, progress_callback, loop)

        if mode == 'audio':
            audio_path = self._process_audio(data.path)
            data.path = audio_path
            data.file_size = os.path.getsize(audio_path)
            
        return data

    def _download_sync(self, url: str, temp_path_raw: str, quality: str = None, progress_callback=None, loop=None) -> DownloadedVideo:
        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback and loop:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(progress_callback(clean_p))
                )

        opts = self._get_opts(url, temp_path_raw, quality)
        opts['progress_hooks'] = [ydl_hook]
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            
            # Если файл не найден (бывает при смене расширений в процессе мерджа)
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
                path=final_path, 
                title=info.get("title", "Video"),
                duration=int(duration or 0), 
                author=info.get("uploader", "Unknown"),
                width=info.get("width", 0), 
                height=info.get("height", 0),
                thumb_url=info.get("thumbnail", ""), 
                file_size=os.path.getsize(final_path)
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
                return DownloadedVideo(
                    path=temp_path, 
                    title=data.get('title', 'TikTok Video'),
                    duration=int(duration), 
                    author=data.get('author', {}).get('nickname', 'TikTok User'),
                    width=data.get('width', 0), 
                    height=data.get('height', 0),
                    thumb_url=data.get('cover', ''), 
                    file_size=os.path.getsize(temp_path)
                )
