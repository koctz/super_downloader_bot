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
            
        # Фикс пути к Node.js для решения n-challenge
        os.environ["YT_DLP_JS_EXECUTOR"] = "/usr/bin/node"
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    def _get_opts(self, url, filename_tmpl=None, quality=None):
        is_yt = "youtube.com" in url or "youtu.be" in url
        cookies = os.path.join(os.getcwd(), "cookies.txt")
        
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
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "rm_cachedir": True,
            "cookiefile": cookies if os.path.exists(cookies) else None,
            "user_agent": random.choice(self.user_agents),
        }

        if is_yt:
            opts["extractor_args"] = {
                "youtube": {
                    "oauth2": True,  # Критично для 2026 года
                    "player_client": ["tv", "web"],
                }
            }
        return opts

    async def get_video_info(self, url: str):
        """Этот метод искал твой бот и не находил"""
        url = self._normalize_url(url)
        opts = self._get_opts(url)
        
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    thumb = info.get('thumbnail') or (info.get('thumbnails')[-1]['url'] if info.get('thumbnails') else None)
                    return {
                        'title': info.get('title', 'Video'),
                        'thumbnail': thumb,
                        'duration': info.get('duration', 0)
                    }
                except Exception as e:
                    print(f"Info extraction error: {e}")
                    return None
        return await asyncio.to_thread(extract)

    async def get_yt_resolutions(self, url: str):
        url = self._normalize_url(url)
        opts = self._get_opts(url)
        
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    res = {f.get('height') for f in info.get('formats', []) if f.get('height') and f.get('height') >= 360}
                    return sorted(list(res), reverse=True) if res else [1080, 720, 360]
                except:
                    return [1080, 720, 360]
        return await asyncio.to_thread(extract)

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        loop = asyncio.get_running_loop()
        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_callback(clean_p)))

        if "tiktok.com" in url and mode != 'audio':
            try: return await self._download_tiktok_via_api(url, unique_id)
            except: pass

        opts = self._get_opts(url, temp_path_tmpl, quality)
        opts['progress_hooks'] = [ydl_hook]
        opts['quiet'] = False # Включаем лог для OAuth

        def run_dl():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
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
            cmd = ["ffmpeg", "-y", "-i", downloaded_path, "-c", "copy", "-movflags", "+faststart", final_path]
        
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(downloaded_path): os.remove(downloaded_path)

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

    async def _download_tiktok_via_api(self, url: str, unique_id: str) -> DownloadedVideo:
        temp_path = os.path.join(self.download_path, f"final_{unique_id}.mp4")
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.tikwm.com/api/", data={'url': url}) as r:
                res = await r.json()
                data = res['data']
                async with session.get(data['play']) as vr:
                    with open(temp_path, 'wb') as f: f.write(await vr.read())
                return DownloadedVideo(
                    path=temp_path, title=data.get('title', 'TikTok'),
                    duration=int(data.get('duration', 0)),
                    author=data.get('author', {}).get('nickname', 'User'),
                    width=data.get('width', 0), height=data.get('height', 0),
                    thumb_url=data.get('cover', ''), file_size=os.path.getsize(temp_path)
                )
