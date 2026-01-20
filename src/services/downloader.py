import os
import asyncio
import yt_dlp
import subprocess
import random
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
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if "vk.ru" in url:
            url = url.replace("vk.ru", "vk.com")
        if "youtube.com/shorts/" in url:
            video_id = url.split("shorts/")[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"
        return url

    async def get_video_info(self, url: str):
        url = self._normalize_url(url)
        return await asyncio.to_thread(self._get_info_sync, url)

    def _get_info_sync(self, url: str):
        opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True, 'user_agent': random.choice(self.user_agents)}
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                thumb = info.get('thumbnail') or (info.get('thumbnails')[-1]['url'] if info.get('thumbnails') else None)
                return {'title': info.get('title', 'Video'), 'thumbnail': thumb, 'duration': info.get('duration')}
            except:
                return None

    async def download(self, url: str, mode: str = 'video', quality: str = None, progress_callback=None) -> DownloadedVideo:
        url = self._normalize_url(url)
        unique_id = str(abs(hash(url + str(time.time()))))[:8]
        temp_path = os.path.join(self.download_path, f"raw_{unique_id}")
        loop = asyncio.get_running_loop()

        data = await asyncio.to_thread(self._download_sync, url, temp_path, quality, progress_callback, loop)
        if mode == 'audio':
            audio_path = self._process_audio(data.path)
            data.path = audio_path
            data.file_size = os.path.getsize(audio_path)
        return data

    def _download_sync(self, url: str, temp_path_raw: str, quality: str = None, progress_callback=None, loop=None) -> DownloadedVideo:
        url = self._normalize_url(url)

        # Шаг 1: получаем информацию о видео без скачивания
        opts = {'quiet': True, 'no_warnings': True, 'user_agent': random.choice(self.user_agents)}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])

        # Шаг 2: выбираем формат по высоте
        best_fmt = None
        if quality:
            q = int(quality)
            # точное совпадение
            for f in formats:
                if f.get('height') == q and f.get('vcodec') != 'none':
                    best_fmt = f
                    break
            if not best_fmt:
                # fallback на ближайшее меньшее разрешение
                lower_fmts = [f for f in formats if f.get('height') and f.get('height') <= q and f.get('vcodec') != 'none']
                if lower_fmts:
                    best_fmt = max(lower_fmts, key=lambda x: x['height'])
                else:
                    # fallback на любое видео
                    best_fmt = max([f for f in formats if f.get('vcodec') != 'none'], key=lambda x: x.get('height', 0))
        else:
            best_fmt = max([f for f in formats if f.get('vcodec') != 'none'], key=lambda x: x.get('height', 0))

        # Шаг 3: формируем опции для скачивания выбранного формата
        ydl_opts = {
            'format': f"{best_fmt['format_id']}+bestaudio",
            'outtmpl': temp_path_raw,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
        }

        if progress_callback and loop:
            def ydl_hook(d):
                if d['status'] == 'downloading':
                    p = d.get('_percent_str', '0%')
                    clean_p = re.sub(r'\x1b\[[0-9;]*m', '', p).strip()
                    loop.call_soon_threadsafe(lambda: asyncio.create_task(progress_callback(clean_p)))
            ydl_opts['progress_hooks'] = [ydl_hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
            result = ydl2.extract_info(url, download=True)
            downloaded_path = ydl2.prepare_filename(result)

        # Шаг 4: перекодирование mp4 только если нужно
        final_path = self._process_video(downloaded_path)

        return DownloadedVideo(
            path=final_path,
            title=info.get("title", "Video"),
            duration=int(info.get("duration") or 0),
            author=info.get("uploader", "Unknown"),
            width=best_fmt.get("width", 0),
            height=best_fmt.get("height", 0),
            thumb_url=info.get("thumbnail", ""),
            file_size=os.path.getsize(final_path)
        )

    def _process_audio(self, input_path):
        output_path = input_path.rsplit('.', 1)[0] + ".mp3"
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path], capture_output=True)
        if os.path.exists(input_path): os.remove(input_path)
        return output_path

    def _process_video(self, input_path):
        # Если mp4, делаем faststart
        output_path = input_path.rsplit('.', 1)[0] + "_f.mp4"
        if input_path.endswith('.mp4'):
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-movflags", "+faststart", output_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", output_path]
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(output_path):
            if os.path.exists(input_path): os.remove(input_path)
            return output_path
        return input_path
