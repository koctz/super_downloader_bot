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
            # Просим h264, если есть, иначе любое до 1080p
            'format': 'bestvideo[vcodec^=avc1][height<=1080]+bestaudio[acodec^=mp4a]/best[height<=1080]/best',
            'outtmpl': filename_tmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        }

    def _process_video(self, input_path, target_bitrate=None):
        """Обработка видео: смена кодека под iPhone и сжатие если нужно"""
        # Создаем имя для финального файла (всегда mp4)
        base_name = os.path.basename(input_path).replace("raw_", "final_")
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(self.download_path, f"{name_without_ext}.mp4")
        
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast', 
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', 'faststart'
        ]

        if target_bitrate:
            cmd += ['-b:v', str(target_bitrate), '-maxrate', str(target_bitrate), '-bufsize', str(target_bitrate * 2)]
        else:
            cmd += ['-crf', '23']

        cmd.append(output_path)
        
        # Запускаем обработку
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Сразу удаляем исходник (raw), он нам больше не нужен
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass
                
        if result.returncode != 0:
            raise DownloadError(f"Ошибка FFmpeg: {result.stderr[:200]}")
            
        return output_path

    def _download_sync(self, url: str) -> DownloadedVideo:
        unique_id = str(hash(url))[-8:]
        # Временный шаблон для скачивания
        temp_path_tmpl = os.path.join(self.download_path, f"raw_{unique_id}.%(ext)s")
        
        with yt_dlp.YoutubeDL(self._get_opts(temp_path_tmpl)) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                # Проверка: если файл скачался с другим расширением
                if not os.path.exists(downloaded_path):
                    files = [f for f in os.listdir(self.download_path) if f.startswith(f"raw_{unique_id}")]
                    if not files:
                        raise DownloadError("Не удалось найти скачанный файл.")
                    downloaded_path = os.path.join(self.download_path, files[0])

                file_size = os.path.getsize(downloaded_path)
                duration = info.get('duration', 0)
                
                target_bitrate = None
                # Считаем битрейт для сжатия под лимит 50МБ (целимся в 45МБ)
                if file_size > 48 * 1024 * 1024 and duration > 0:
                    target_size_bits = 45 * 1024 * 1024 * 8
                    target_bitrate = int(target_size_bits / duration)

                # Запускаем перекодировку/сжатие
                final_path = self._process_video(downloaded_path, target_bitrate)

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
                # Если произошла ошибка, пытаемся почистить всё по этому ID
                for f in os.listdir(self.download_path):
                    if unique_id in f:
                        try: os.remove(os.path.join(self.download_path, f))
                        except: pass
                raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
