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
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
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
        opts = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'javascript_executor': '/usr/bin/node',
            'extractor_args': {'youtube': {'player_client': ['web', 'tv']}},
        }
        
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    res = set()
                    for f in formats:
                        h = f.get('height')
                        # Нам нужны только форматы с видео (не ID 18)
                        if h and h >= 360 and f.get('vcodec') != 'none' and f.get('format_id') != '18':
                            res.add(h)
                    return sorted(list(res), reverse=True) if res else [1080, 720, 360]
                except:
                    return [1080, 720, 360]
        
        return await asyncio.to_thread(extract)

    async def get_video_info(self, url: str):
        url = self._normalize_url(url)
        return await asyncio.to_thread(self._get_info_sync, url)

    def _get_info_sync(self, url: str):
        opts = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                thumb = info.get('thumbnail')
                if not thumb and info.get('thumbnails'):
                    thumb = info['thumbnails'][-1].get('url')
                return {'title': info.get('title', 'Video'), 'thumbnail': thumb, 'duration': info.get('duration')}
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
        if not os.path.exists(input_path): return input_path
        base = os.path.basename(input_path).replace("raw_", "final_")
        if not base.endswith(".mp4"): base = os.path.splitext(base)[0] + ".mp4"
        output_path = os.path.join(self.download_path, base)

        file_size = os.path.getsize(input_path)
        MTPROTO_LIMIT = 1900 * 1024 * 1024 
        
        # Если это YouTube и файл нормальный - просто копируем контейнер
        if file_size <= MTPROTO_LIMIT and not is_insta and input_path.lower().endswith(".mp4"):
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-movflags", "+faststart", output_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", output_path]

        subprocess.run(cmd, capture_output=True)
        if os.path.exists(output_path):
            if os.path.exists(input_path): os.remove(input_path)
            return output_path
        return input_path

    def _get_opts(self, url, filename_tmpl, quality=None):
        is_yt = ("youtube.com" in url) or ("youtu.be" in url)
        
        # Запрещаем ID 18, чтобы не качал 109МБ
        if is_yt and quality:
            fmt = f"bestvideo[height<={quality}][format_id!=18]+bestaudio/best[height<={quality}][format_id!=18]/best"
        else:
            fmt = "bestvideo+bestaudio/best"

        opts = {
            "format": fmt,
            "outtmpl": filename_tmpl,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "quiet": False,
            "nocheckcertificate": True,
            "javascript_executor": "/usr/bin/node", # ФИКС
            "rm_cachedir": True,
        }

        cookies_path = os.path.join(os.getcwd(), "cookies.txt")
        if os.path.exists(cookies_path):
            opts["cookiefile"] = cookies_path

        if is_yt:
            opts["extractor_args"] = {"youtube": {"player_client": ["web", "tv"]}}
            
        return opts

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")
        
        if "tiktok.com" in url and mode != 'audio':
            try: return await self._download_tiktok_via_api(url, temp_path)
            except: pass

        data = await asyncio.to_thread(self._download_sync, url, temp_path, quality, progress_callback, asyncio.get_running_loop())

        if mode == 'audio':
            audio_path = self._process_audio(data.path)
            data.path, data.file_size = audio_path, os.path.getsize(audio_path)
            
        return data

    def _download_sync(self, url, temp_path_raw, quality, progress_callback, loop) -> DownloadedVideo:
        def ydl_hook(d):
            if d['status'] == 'downloading' and progress_callback:
                p = d.get('_percent_str', '0%')
                clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_callback(clean_p)))

        opts = self._get_opts(url, temp_path_raw, quality)
        opts['progress_hooks'] = [ydl_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            
            # Если скачалось несколько файлов (видео+аудио), yt-dlp их склеит
            if not os.path.exists(downloaded_path):
                for ext in [".mp4", ".mkv", ".webm"]:
                    if os.path.exists(os.path.splitext(downloaded_path)[0] + ext):
                        downloaded_path = os.path.splitext(downloaded_path)[0] + ext
                        break

            final_path = self._process_video(downloaded_path, info.get("duration", 0), "instagram" in url)
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
                return DownloadedVideo(
                    path=temp_path, title=data.get('title', 'TikTok'),
                    duration=int(data.get('duration', 0)), author=data.get('author', {}).get('nickname', 'User'),
                    width=data.get('width', 0), height=data.get('height', 0),
                    thumb_url=data.get('cover', ''), file_size=os.path.getsize(temp_path)
                )
