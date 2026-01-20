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
        if not base.endswith(".mp4"):
            base = os.path.splitext(base)[0] + ".mp4"
            
        output_path = os.path.join(self.download_path, base)
        if not os.path.exists(input_path):
            return input_path

        file_size = os.path.getsize(input_path)
        MTPROTO_LIMIT = 1980 * 1024 * 1024 
        
        # ПРАВКА: Если файл MP4 и под лимитом - просто копируем (быстро и без потери качества)
        if file_size <= MTPROTO_LIMIT and not is_insta and input_path.endswith(".mp4"):
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-map_metadata", "0", "-movflags", "+faststart", output_path]
        else:
            # ПРАВКА: Если конвертируем, убираем принудительный scale=720, чтобы сохранить исходное разрешение
            # Мы используем crf 23 для баланса веса и качества
            cmd = ["ffmpeg", "-y", "-i", input_path, 
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", 
                   "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path]

        try:
            subprocess.run(cmd, capture_output=True, timeout=900)
        except Exception as e:
            print(f"FFmpeg Error: {e}")
            if input_path.endswith(".mp4"):
                return input_path
            
        if os.path.exists(output_path):
            if os.path.exists(input_path):
                try: os.remove(input_path)
                except: pass
            return output_path
        return input_path

# ✅ НОВЫЙ КОД
    def _get_opts(self, url, filename_tmpl, quality=None):
        # Если качество не передано, ставим 1080
        q = quality if quality else "1080"
        
        # 🔥 Новая логика строки формата:
        # Сначала ищем видео нужной высоты (не выше q) в MP4, 
        # если нет - берем любое видео не выше q и склеиваем с лучшим звуком.
        fmt = f"bestvideo[height<={q}]+bestaudio/best[height<={q}]/best"

        opts = {
            'format': fmt,
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'merge_output_format': 'mp4', # Обязательно для склейки разных потоков
            'user_agent': random.choice(self.user_agents),
        }
        
        if "instagram.com" in url:
            cookies_path = os.path.join(os.getcwd(), "cookies.txt")
            if os.path.exists(cookies_path): opts['cookiefile'] = cookies_path
        elif "youtube.com" in url or "youtu.be" in url:
            # Важно: ограничиваем протокол, чтобы не лезли m3u8, которые весят странно
            opts['prefer_native_hls'] = True
            opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}
            
        return opts

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")
        loop = asyncio.get_running_loop()

        if "tiktok.com" in url and mode != 'audio':
            try:
                data = await self._download_tiktok_via_api(url, temp_path)
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
        print(f"DEBUG: Скачиваю URL: {url} | Выбранное качество: {quality}")
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
            except Exception as e:
                raise DownloadError(f"Download failed: {str(e)}")
                
            downloaded_path = ydl.prepare_filename(info)
            
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
