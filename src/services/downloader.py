import os
import asyncio
import yt_dlp
import subprocess
import random
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
        # Список современных User-Agents для имитации разных браузеров
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
        ]

    def _get_opts(self, filename_tmpl):
        """
        Настройки yt-dlp:
        - Ограничение 480p для скорости.
        - Ротация User-Agent.
        - Поддержка Cookies (Netscape format).
        - Имитация заголовков Instagram.
        """
        opts = {
            'format': 'bestvideo[ext=mp4][vcodec^=avc1][height<=480]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best[height<=480]/best',
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': random.choice(self.user_agents),
            'nocheckcertificate': True,
            # Добавляем заголовки, чтобы запрос выглядел как переход внутри соцсети
            'http_headers': {
                'Referer': 'https://www.instagram.com/',
                'Origin': 'https://www.instagram.com',
            },
            'wait_for_video_data': 5,
            'socket_timeout': 30,
        }

        # ПУТЬ К КУКАМ: Ищем cookies.txt в корне проекта
        cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
        if os.path.exists(cookies_path):
            opts['cookiefile'] = cookies_path
            # Принудительно указываем формат, если расширение его не прописало
            print(f"DEBUG: Использую куки из {cookies_path}")
        
        return opts

    def _process_video(self, input_path, force_recode=False, target_bitrate=None):
        """Обработка через FFmpeg: Copy-mode или Recode-mode"""
        base_name = os.path.basename(input_path).replace("raw_", "final_")
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(self.download_path, f"{name_without_ext}.mp4")
        
        cmd = ['ffmpeg', '-y', '-i', input_path]

        if target_bitrate:
            cmd += [
                '-c:v', 'libx264', '-preset', 'ultrafast', '-b:v', str(target_bitrate),
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k'
            ]
        elif force_recode:
            cmd += [
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k'
            ]
        else:
            cmd += ['-c', 'copy']

        cmd += ['-movflags', 'faststart', output_path]
        
        print(f"DEBUG: FFmpeg запуск (Mode: {'Recode' if force_recode else 'Copy'})")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if os.path.exists(input_path):
            os.remove(input_path)
            
        if result.returncode != 0:
            if not force_recode and not target_bitrate:
                print("DEBUG: Copy failed, retrying with full recode...")
                return self._process_video(input_path, force_recode=True)
            raise DownloadError(f"FFmpeg error: {result.stderr[:100]}")
            
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:]
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_path_tmpl)) as ydl:
            try:
                print(f"DEBUG: Начинаю yt-dlp загрузку: {url}")
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                if not os.path.exists(downloaded_path):
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"raw_{unique_id}")]
                    if not files: raise DownloadError("Файл не найден после загрузки")
                    downloaded_path = os.path.join(self.download_path, files[0])

                file_size = os.path.getsize(downloaded_path)
                duration = info.get('duration', 0)
                is_mp4 = downloaded_path.lower().endswith('.mp4')

                target_bitrate = None
                if file_size > 48 * 1024 * 1024 and duration > 0:
                    target_bitrate = int((42 * 1024 * 1024 * 8) / duration)
                
                force_recode = not is_mp4 or target_bitrate is not None
                final_path = self._process_video(downloaded_path, force_recode, target_bitrate)

                return DownloadedVideo(
                    path=final_path,
                    title=info.get('title', 'Video'),
                    duration=int(duration or 0),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0) or 0,
                    height=info.get('height', 0) or 0,
                    thumb_url=info.get('thumbnail', ''),
                    file_size=os.path.getsize(final_path)
                )

            except Exception as e:
                for f in os.listdir(self.download_path):
                    if unique_id in f:
                        try: os.remove(os.path.join(self.download_path, f))
                        except: pass
                raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
