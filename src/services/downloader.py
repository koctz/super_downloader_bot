import os
import asyncio
import yt_dlp
import subprocess
from dataclasses import dataclass
from src.config import conf

# Исключения
class DownloadError(Exception):
    pass

class VideoTooBigError(Exception):
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

    def _get_opts(self, filename_tmpl):
        return {
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    def _compress_video(self, input_path):
        """Принудительное сжатие видео до ~45MB через FFmpeg (2-pass)"""
        output_path = input_path.replace(".mp4", "_compressed.mp4")
        
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        try:
            duration = float(probe.stdout.strip())
        except:
            duration = 10

        target_size_bits = 45 * 1024 * 1024 * 8
        bitrate = int(target_size_bits / duration)

        # 1-й проход
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-b:v', str(bitrate),
            '-preset', 'veryfast', '-pass', '1', '-an', '-f', 'mp4', '/dev/null'
        ])
        
        # 2-й проход
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-b:v', str(bitrate),
            '-preset', 'veryfast', '-pass', '2',
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p', '-movflags', 'faststart',
            output_path
        ])
        
        if os.path.exists("ffmpeg2pass-0.log"): os.remove("ffmpeg2pass-0.log")
        if os.path.exists("ffmpeg2pass-0.log.mbtree"): os.remove("ffmpeg2pass-0.log.mbtree")
        
        if os.path.exists(input_path):
            os.remove(input_path)
        
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:]
        temp_path_tmpl = os.path.join(self.download_path, f"video_{unique_id}.%(ext)s")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_path_tmpl)) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
                
                # Если файл не найден по ожидаемому пути, ищем его в папке
                if not os.path.exists(path):
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"video_{unique_id}")]
                    if not files:
                        raise DownloadError("Файл не найден после загрузки.")
                    path = os.path.join(self.download_path, files[0])

                # Финальный MP4 путь
                final_mp4 = os.path.join(self.download_path, f"final_{unique_id}.mp4")
                
                # Быстрый ремукс для iPhone и фикса контейнера
                subprocess.run([
                    'ffmpeg', '-y', '-i', path,
                    '-c', 'copy', '-movflags', 'faststart', 
                    final_mp4
                ], capture_output=True)

                if os.path.exists(path) and path != final_mp4:
                    os.remove(path)
                
                path = final_mp4
                file_size = os.path.getsize(path)

                if file_size > 50 * 1024 * 1024:
                    path = self._compress_video(path)
                    file_size = os.path.getsize(path)

                return DownloadedVideo(
                    path=path,
                    title=info.get('title', 'Video'),
                    duration=int(info.get('duration', 0)),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0) or 0,
                    height=info.get('height', 0) or 0,
                    thumb_url=info.get('thumbnail', ''),
                    file_size=file_size
                )

            except Exception as e:
                raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
