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
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url: url = url.replace("vk.ru", "vk.com")
        return url

    async def get_formats(self, url: str):
        url = self._normalize_url(url)
        # Проверяем, что это YouTube, но НЕ Shorts
        is_youtube = any(domain in url for domain in ["youtube.com", "youtu.be"])
        is_shorts = "shorts" in url
        
        if not is_youtube or is_shorts:
            return None

        def extract():
            opts = {
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(extract)
            if not info: return None

            seen_heights = set()
            allowed_heights = [360, 480, 720, 1080]
            
            for f in info.get('formats', []):
                h = f.get('height')
                if h in allowed_heights:
                    # Проверяем наличие видеопотока
                    if f.get('vcodec') != 'none':
                        seen_heights.add(h)
            
            if not seen_heights:
                seen_heights = {360, 720} # Запасной вариант

            return {
                "formats": sorted(list(seen_heights)),
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "Unknown"),
                "uploader_url": info.get("uploader_url", "")
            }
        except Exception as e:
            print(f"Get formats error: {e}")
            return None

    def _process_audio(self, input_path):
        base = os.path.basename(input_path)
        output_path = os.path.join(self.download_path, os.path.splitext(base)[0] + ".mp3")
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path]
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(input_path) and input_path != output_path:
            try: os.remove(input_path)
            except: pass
        return output_path

    def _process_video(self, input_path, duration, is_insta=False):
        if not os.path.exists(input_path): return input_path
        base = os.path.basename(input_path).replace("raw_", "final_")
        if not base.endswith(".mp4"):
            base = os.path.splitext(base)[0] + ".mp4"
        output_path = os.path.join(self.download_path, base)
        
        file_size = os.path.getsize(input_path)
        MTPROTO_LIMIT = 1950 * 1024 * 1024 
        
        if file_size <= MTPROTO_LIMIT and not is_insta:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-map_metadata", "0", "-movflags", "+faststart", output_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", "scale='trunc(oh*a/2)*2:720',setsar=1", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path]

        subprocess.run(cmd, capture_output=True)
        if os.path.exists(input_path) and input_path != output_path:
            try: os.remove(input_path)
            except: pass
        return output_path

    def _get_opts(self, url, filename_tmpl, quality=None):
        if quality:
            fmt = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]'
        else:
            fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best'

        return {
            'format': fmt,
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'user_agent': random.choice(self.user_agents),
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
        }

    async def download(self, url: str, mode: str = 'video', progress_callback=None, quality=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url)))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")
        
        if "tiktok.com" in url:
            data = await self._download_tiktok_via_api(url, temp_path)
        else:
            data = await asyncio.to_thread(self._download_sync, url, temp_path, progress_callback, quality)

        if mode == 'audio':
            audio_path = self._process_audio(data.path)
            data.path = audio_path
            data.file_size = os.path.getsize(audio_path)
        return data

    def _download_sync(self, url: str, temp_path_raw: str, progress_callback=None, quality=None) -> DownloadedVideo:
        loop = asyncio.get_event_loop()
        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_callback(clean_p)))

        opts = self._get_opts(url, temp_path_raw, quality)
        opts['progress_hooks'] = [ydl_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            
            # Если yt-dlp скачал в mkv/webm, фиксим путь
            if not os.path.exists(path):
                for ext in ['.mkv', '.webm', '.mp4']:
                    if os.path.exists(os.path.splitext(path)[0] + ext):
                        path = os.path.splitext(path)[0] + ext
                        break

            is_insta = "instagram" in url
            final_path = self._process_video(path, info.get('duration', 0), is_insta)

            return DownloadedVideo(
                path=final_path, title=info.get("title", "Video"),
                duration=int(info.get("duration") or 0), author=info.get("uploader", "Unknown"),
                width=info.get("width", 0), height=info.get("height", 0),
                thumb_url=info.get("thumbnail", ""), file_size=os.path.getsize(final_path)
            )

    async def _download_tiktok_via_api(self, url: str, temp_path: str) -> DownloadedVideo:
        api_url = "https://www.tikwm.com/api/"
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, data={'url': url}) as response:
                res = await response.json()
                data = res['data']
                async with session.get(data.get('play')) as video_res:
                    with open(temp_path, 'wb') as f: f.write(await video_res.read())
                final_path = self._process_video(temp_path, data.get('duration', 0))
                return DownloadedVideo(
                    path=final_path, title=data.get('title', 'TikTok'),
                    duration=int(data.get('duration', 0)), author=data.get('author', {}).get('nickname', 'User'),
                    width=data.get('width', 0), height=data.get('height', 0),
                    thumb_url=data.get('cover', ''), file_size=os.path.getsize(final_path)
                )
