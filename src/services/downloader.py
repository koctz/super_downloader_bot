import os
import asyncio
import yt_dlp
import subprocess
import random
import aiohttp
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
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url: url = url.replace("vk.ru", "vk.com")
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    def _process_audio(self, input_path):
        base = os.path.basename(input_path)
        output_path = os.path.join(self.download_path, os.path.splitext(base)[0] + ".mp3")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path
        ]
        
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
    file_size = os.path.getsize(input_path)
    MAX_SIZE_BYTES = 46 * 1024 * 1024 

    # БОЛЬШЕ НЕ УГАДЫВАЕМ is_insta ПО ИМЕНИ ФАЙЛА
    # is_insta приходит параметром

    if file_size <= MAX_SIZE_BYTES and not is_insta:
        print(f"DEBUG: Быстрая перепаковка (YouTube/TikTok/VK): {input_path}")
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c", "copy", "-map_metadata", "0",
            "-movflags", "+faststart", output_path
        ]
    else:
        print(f"DEBUG: Глубокая обработка (Instagram или сжатие): {input_path}")
        
        target_total_bitrate = int((MAX_SIZE_BYTES * 8) / max(duration, 1))
        video_bitrate = int(target_total_bitrate * 0.85)
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", "scale='trunc(oh*a/2)*2:720',setsar=1",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-vsync", "cfr",
            "-profile:v", "main",
            "-level", "3.1",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-video_track_timescale", "30000"
        ]

        if file_size > MAX_SIZE_BYTES:
            cmd.extend([
                "-b:v", str(video_bitrate),
                "-maxrate", str(video_bitrate),
                "-bufsize", str(video_bitrate * 2)
            ])
        
        cmd.append(output_path)

    try:
        subprocess.run(cmd, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise DownloadError("Видео слишком длинное для обработки сервером.")

    if os.path.exists(input_path):
        try: os.remove(input_path)
        except: pass

    return output_path

        
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
                    path=final_path,
                    title=data.get('title', 'TikTok Video'),
                    duration=int(duration),
                    author=data.get('author', {}).get('nickname', 'TikTok User'),
                    width=data.get('width', 0),
                    height=data.get('height', 0),
                    thumb_url=data.get('cover', ''),
                    file_size=os.path.getsize(final_path),
                )

    def _get_opts(self, url, filename_tmpl):
        # Ограничиваем формат до 720p сразу при скачивании
        opts = {
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
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

    def _download_sync(self, url: str, temp_path_raw: str) -> DownloadedVideo:
        opts = self._get_opts(url, temp_path_raw)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            
            # Фикс для случаев, когда yt-dlp меняет расширение
            if not os.path.exists(downloaded_path):
                base_no_ext = os.path.splitext(downloaded_path)[0]
                for ext in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base_no_ext + ext):
                        downloaded_path = base_no_ext + ext
                        break

            duration = info.get("duration", 0)
            final_path = self._process_video(downloaded_path, duration)

            return DownloadedVideo(
                path=final_path,
                title=info.get("title", "Video"),
                duration=int(duration or 0),
                author=info.get("uploader", "Unknown"),
                width=info.get("width", 0),
                height=info.get("height", 0),
                thumb_url=info.get("thumbnail", ""),
                file_size=os.path.getsize(final_path),
            )

    async def download(self, url: str, mode: str = 'video') -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url)))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")

        if "tiktok.com" in url:
            data = await self._download_tiktok_via_api(url, temp_path)
        else:
            data = await asyncio.to_thread(self._download_sync, url, temp_path)

        if mode == 'audio':
            audio_path = self._process_audio(data.path)
            data.path = audio_path
            data.file_size = os.path.getsize(audio_path)
        
        return data
