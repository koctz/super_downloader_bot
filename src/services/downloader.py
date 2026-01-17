import os
import asyncio
import yt_dlp
import subprocess
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

    def _get_opts(self, filename_tmpl):
        return {
            # Принудительно просим h264 (avc1), если он есть
            'format': 'bestvideo[vcodec^=avc1][height<=1080]+bestaudio[acodec^=mp4a]/best[height<=1080]/best',
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    def _compress_video(self, input_path):
        """Двухпроходное сжатие для видео > 50MB"""
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

        # 2-pass сжатие
        for pass_num in [1, 2]:
            cmd = [
                'ffmpeg', '-y', '-i', input_path,
                '-c:v', 'libx264', '-b:v', str(bitrate),
                '-preset', 'veryfast', '-pass', str(pass_num),
                '-pix_fmt', 'yuv420p', '-movflags', 'faststart'
            ]
            if pass_num == 1:
                cmd += ['-an', '-f', 'mp4', '/dev/null']
            else:
                cmd += ['-c:a', 'aac', '-b:a', '128k', output_path]
            subprocess.run(cmd)
        
        if os.path.exists("ffmpeg2pass-0.log"): os.remove("ffmpeg2pass-0.log")
        if os.path.exists("ffmpeg2pass-0.log.mbtree"): os.remove("ffmpeg2pass-0.log.mbtree")
        os.remove(input_path)
        return output_path

    def _convert_for_iphone(self, input_path):
        """Быстрое перекодирование в H.264 для видео < 50MB"""
        output_path = input_path.replace(".mp4", "_iphone.mp4")
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264',      # Кодек, который понимает iPhone
            '-preset', 'ultrafast', # Максимальная скорость
            '-crf', '23',           # Хорошее качество
            '-c:a', 'aac',          # Аудио кодек Apple
            '-pix_fmt', 'yuv420p',  # Цветовой профиль Apple
            '-movflags', 'faststart',
            output_path
        ])
        os.remove(input_path)
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:]
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_path_tmpl)) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                # Проверка существования файла (yt-dlp может менять расширение)
                if not os.path.exists(downloaded_path):
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"raw_{unique_id}")]
                    if not files: raise DownloadError("Файл не найден")
                    downloaded_path = os.path.join(self.download_path, files[0])

                file_size = os.path.getsize(downloaded_path)

                # Выбираем стратегию обработки
                if file_size > 50 * 1024 * 1024:
                    # Если тяжелое — сжимаем (долго)
                    final_path = self._compress_video(downloaded_path)
                else:
                    # Если легкое — просто перекодируем под iPhone (быстро)
                    final_path = self._convert_for_iphone(downloaded_path)

                return DownloadedVideo(
                    path=final_path,
                    title=info.get('title', 'Video'),
                    duration=int(info.get('duration', 0)),
                    author=info.get('uploader', 'Unknown'),
                    width=info.get('width', 0) or 0,
                    height=info.get('height', 0) or 0,
                    thumb_url=info.get('thumbnail', ''),
                    file_size=os.path.getsize(final_path)
                )

            except Exception as e:
                raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
