import os
import asyncio
import yt_dlp
import subprocess
import random
import aiohttp  # Нужно установить: pip install aiohttp
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

    async def _download_tiktok_via_api(self, url: str, temp_path: str) -> DownloadedVideo:
        """Специальный метод обхода блокировки TikTok через API TikWM"""
        api_url = "https://www.tikwm.com/api/"
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, data={'url': url}) as response:
                res = await response.json()
                if res.get('code') != 0:
                    raise DownloadError(f"TikTok API Error: {res.get('msg')}")
                
                data = res['data']
                video_url = data.get('play') # Видео без водяного знака
                
                # Скачиваем сам файл
                async with session.get(video_url) as video_res:
                    if video_res.status != 200:
                        raise DownloadError("Не удалось скачать видео по прямой ссылке")
                    with open(temp_path, 'wb') as f:
                        f.write(await video_res.read())

                # Передаем в твой FFmpeg для оптимизации
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
            opts['http_headers'] = {
                'Referer': 'https://www.instagram.com/',
                'Origin': 'https://www.instagram.com',
            }
        elif "youtube.com" in url or "youtu.be" in url:
            opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web']}}

        return opts

    def _process_video(self, input_path, duration):
        """Финальная версия: исправляет растянутость и ориентацию видео"""
        base = os.path.basename(input_path).replace("raw_", "final_")
        if not base.endswith(".mp4"):
            base = os.path.splitext(base)[0] + ".mp4"
            
        output_path = os.path.join(self.download_path, base)
        file_size = os.path.getsize(input_path)

        # ПАРАМЕТРЫ ДЛЯ ИСПРАВЛЕНИЯ "КРИВИЗНЫ":
        # 1. scale='trunc(oh*a/2)*2:720' — подгоняет ширину под высоту 720p, сохраняя пропорции (кратно 2 для кодека)
        # 2. setsar=1 — исправляет растянутые пиксели
        # 3. format=yuv420p — стандарт для мобилок
        vf_params = "scale='trunc(oh*a/2)*2:720',setsar=1,format=yuv420p"

        cmd = [
            "ffmpeg", "-y", 
            "-display_rotation", "0", # Игнорируем встроенный поворот в метаданных
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

        # Если файл слишком тяжелый, заменяем -crf на конкретный битрейт
        if file_size > 48 * 1024 * 1024:
            target_bitrate = int((42 * 1024 * 1024 * 8) / max(duration, 1))
            # Удаляем -crf 23 (индексы 12, 13) и вставляем битрейт
            cmd[12] = "-b:v"
            cmd[13] = str(target_bitrate)

        print(f"DEBUG: Исправляю пропорции видео: {input_path}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass

        if result.returncode != 0:
            print(f"FFMPEG ERROR: {result.stderr}")
            raise DownloadError(f"Ошибка FFmpeg при исправлении пропорций")

        return output_path

    def _download_sync(self, url: str, temp_path_raw: str) -> DownloadedVideo:
        """Твоя стандартная синхронная загрузка для YouTube/Insta/VK"""
        opts = self._get_opts(url, temp_path_raw)
        with yt_dlp.YoutubeDL(opts) as ydl:
            print(f"DEBUG: Начинаю yt-dlp загрузку: {url}")
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)

            if not os.path.exists(downloaded_path):
                # Поиск файла если yt-dlp изменил расширение
                unique_id = temp_path_raw.split('raw_')[1].split('.')[0]
                possible_files = [f for f in os.listdir(self.download_path) if unique_id in f]
                if possible_files:
                    downloaded_path = os.path.join(self.download_path, possible_files[0])
                else:
                    raise DownloadError("Файл не найден после загрузки")

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

    async def download(self, url: str) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(hash(url))[-8:]
        # Генерируем путь для временного файла
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}.mp4")

        # Если это TikTok — используем асинхронный API-обход
        if "tiktok.com" in url:
            print(f"DEBUG: TikTok обнаружен. Использую API-обход для URL: {url}")
            return await self._download_tiktok_via_api(url, temp_path)
        
        # Для остальных (YouTube, Instagram, VK) — используем твой стандартный метод
        return await asyncio.to_thread(self._download_sync, url, temp_path)
