import os
import asyncio
import yt_dlp
import subprocess
import random
import aiohttp
import re
import time
import sys
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
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url: url = url.replace("vk.ru", "vk.com")
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    async def get_yt_resolutions(self, url: str):
        url = self._normalize_url(url)
        opts = self._get_opts(url, "temp", quality=None)
        opts.update({'extract_flat': False, 'quiet': True})
        
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    res = set()
                    for f in formats:
                        h = f.get('height')
                        if h and h >= 360 and f.get('vcodec') != 'none' and f.get('format_id') != '18':
                            res.add(h)
                    return sorted(list(res), reverse=True) if res else [1080, 720, 360]
                except Exception as e:
                    print(f"Format extraction error: {e}")
                    return [1080, 720, 360]
        
        return await asyncio.to_thread(extract)

    async def get_video_info(self, url: str):
        url = self._normalize_url(url)
        opts = {
            'extract_flat': True,
            'quiet': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'user_agent': random.choice(self.user_agents)
        }
        def get_info():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    thumb = info.get('thumbnail') or (info.get('thumbnails')[-1]['url'] if info.get('thumbnails') else None)
                    return {'title': info.get('title', 'Video'), 'thumbnail': thumb, 'duration': info.get('duration')}
                except: return None
        return await asyncio.to_thread(get_info)

    def _process_video(self, input_path, is_insta=False):
        if not os.path.exists(input_path): return input_path
        output_path = input_path.replace("raw_", "final_")
        if not output_path.endswith(".mp4"):
            output_path = os.path.splitext(output_path)[0] + ".mp4"

        file_size = os.path.getsize(input_path)
        limit = 1900 * 1024 * 1024 

        if file_size <= limit and not is_insta and input_path.lower().endswith(".mp4"):
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-movflags", "+faststart", output_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", output_path]

        subprocess.run(cmd, capture_output=True)
        if os.path.exists(output_path):
            if os.path.exists(input_path): os.remove(input_path)
            return output_path
        return input_path

    def _get_opts(self, url, filename_tmpl, quality=None):
        is_yt = "youtube.com" in url or "youtu.be" in url
        cookies = os.path.join(os.getcwd(), "cookies.txt")
        
        if is_yt and quality:
            fmt = f"bestvideo[height<={quality}][format_id!=18]+bestaudio/best[height<={quality}][format_id!=18]/best"
        else:
            fmt = "bestvideo[height<=1080][format_id!=18]+bestaudio/best/best"

        opts = {
            "format": fmt,
            "outtmpl": filename_tmpl,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "quiet": False,
            "no_warnings": False,
            "nocheckcertificate": True,
            "rm_cachedir": True,
            "javascript_executor": "node", 
            "cookiefile": cookies if os.path.exists(cookies) else None,
            "user_agent": random.choice(self.user_agents),
        }

        if is_yt:
            opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["tv", "web_creator"],
                    "player_skip": ["web", "android", "ios"]
                }
            }
        return opts

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")
        loop = asyncio.get_running_loop()

        if "tiktok.com" in url and mode != 'audio':
            try: return await self._download_tiktok_via_api(url, temp_path)
            except: pass

        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_callback(clean_p)))

        opts = self._get_opts(url, temp_path, quality)
        opts['progress_hooks'] = [ydl_hook]

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
        
        if mode == 'audio':
            final_path = self._process_audio(downloaded_path)
        else:
            final_path = self._process_video(downloaded_path, "instagram" in url)

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

    def _process_audio(self, input_path):
        output_path = os.path.splitext(input_path)[0] + ".mp3"
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path], capture_output=True)
        if os.path.exists(input_path): os.remove(input_path)
        return output_path

    async def _download_tiktok_via_api(self, url: str, temp_path: str) -> DownloadedVideo:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.tikwm.com/api/", data={'url': url}) as r:
                res = await r.json()
                data = res['data']
                async with session.get(data['play']) as vr:
                    with open(temp_path, 'wb') as f: f.write(await vr.read())
                return DownloadedVideo(
                    path=temp_path, 
                    title=data.get('title', 'TikTok'), 
                    duration=int(data.get('duration', 0)), 
                    author=data.get('author', {}).get('nickname', 'User'), 
                    width=data.get('width', 0), 
                    height=data.get('height', 0), 
                    thumb_url=data.get('cover', ''), 
                    file_size=os.path.getsize(temp_path)
                )
