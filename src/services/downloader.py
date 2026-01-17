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
        """Извлечение аудио дорожки и конвертация в MP3"""
        base = os.path.basename(input_path)
        output_path = os.path.join(self.download_path, os.path.splitext(base)[0] + ".mp3")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", 
            "-acodec", "libmp3lame",
            "-q:a", "2", 
            output_path
        ]
        
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass
        return output_path

    def _process_video(self, input_path, duration):
        """Финальная версия: исправляет растянутость и ориентацию видео"""
        base = os.path.basename(input_path).replace("raw_", "final_")
        if not base.endswith(".mp4"):
            base = os.path.splitext(base)[0] + ".mp4"
            
        output_path = os.path.join(self.download_path, base)
        file_size = os.path.getsize(input_path)

        vf_params = "scale='trunc(oh*a/2)*2:720',setsar=1,format=yuv420p"

        cmd = [
            "ffmpeg", "-y", 
            "-display_rotation", "0", 
            "-i", input_path,
            "-vf", vf_params,
            "-c:v", "libx264", 
            "-preset", "ultrafast", 
            "-crf", "23",
            "-c:a", "aac", 
            "-b:a", "128k",
            "-movflags", "faststart", 
            output_path
        ]

        if file_size > 48 * 1024 * 1024:
            target_bitrate = int((42 * 1024 * 1024 * 8) / max(duration, 1))
            cmd[12] = "-b:v"
            cmd[13] = str(target_bitrate)

        print(f"DEBUG: Обработка видео: {input_path}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass

        if result.returncode != 0:
            raise DownloadError(f"Ошибка FFmpeg")

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
                    if video_res.status != 200:
                        raise DownloadError("Не удалось скачать видео")
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
        if "instagram.com" in url:
            cookies_path = os.path.join(os.getcwd(), "cookies.txt")
            if os.path.exists(cookies_path):
                opts['cookiefile'] = cookies_path
            opts['http_headers'] = {'Referer': 'https://www.instagram.com/', 'Origin': 'https://www.instagram.com'}
        elif "youtube.com" in url or "youtu.be" in url:
            opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}
        return opts

    def _download_sync(self, url: str, temp_path_raw: str) -> DownloadedVideo:
        opts = self._get_opts(url, temp_path_raw)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            if not os.path.exists(downloaded_path):
                unique_id = temp_path_raw.split('raw_')[1].split('.')[0]
                possible_files = [f for f in os.listdir(self.download_path) if unique_id in f]
                if possible_files: downloaded_path = os.path.join(self.download_path, possible_files[0])
                else: raise DownloadError("Файл не найден")

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
        """Главный метод: качает видео и, если нужно, превращает в аудио"""
        url = self._normalize_url(url)
        unique_id = str(hash(url))[-8:]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")

        # 1. Сначала всегда получаем видео
        if "tiktok.com" in url:
            data = await self._download_tiktok_via_api(url, temp_path)
        else:
            data = await asyncio.to_thread(self._download_sync, url, temp_path)

        # 2. Если пользователь нажал кнопку "Аудио" — конвертируем
        if mode == 'audio':
            print(f"DEBUG: Конвертирую в аудио: {data.path}")
            audio_path = self._process_audio(data.path)
            data.path = audio_path
            data.file_size = os.path.getsize(audio_path)
        
        return data
