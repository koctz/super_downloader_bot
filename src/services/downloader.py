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

        self.desktop_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    # -----------------------------
    # NORMALIZATION OF DOMAINS
    # -----------------------------
    def _normalize_url(self, url: str) -> str:
        original = url

        # VK
        url = url.replace("vk.ru", "vk.com")

        # YouTube Shorts → нормальный формат
        if "youtube.com/shorts/" in url:
            parts = url.split("youtube.com/shorts/")
            video_id = parts[1].split("?")[0]
            url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"DEBUG: Нормализованный URL: {original} → {url}")
        return url

    # -----------------------------
    # YT-DLP OPTIONS
    # -----------------------------
    def _get_opts(self, url):
        opts = {
            "outtmpl": os.path.join(self.download_path, "raw_%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "format": "mp4/best",
            "http_headers": {
                "User-Agent": self.desktop_ua,
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"]  # самый стабильный клиент
                }
            }
        }

        # INSTAGRAM
        if "instagram.com" in url:
            cookies_path = os.path.join(os.getcwd(), "cookies_instagram.txt")
            if os.path.exists(cookies_path):
                opts["cookiefile"] = cookies_path

        return opts

    # -----------------------------
    # FFMPEG PROCESSING
    # -----------------------------
    def _process_video(self, input_path, duration):
        base = os.path.basename(input_path).replace("raw_", "final_")
        output_path = os.path.join(self.download_path, base)

        file_size = os.path.getsize(input_path)

        # Telegram limit 50 MB
        if file_size <= 48 * 1024 * 1024:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", "-movflags", "faststart", output_path]
        else:
            target_bitrate = int((42 * 1024 * 1024 * 8) / max(duration, 1))
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "libx264", "-preset", "ultrafast",
                "-b:v", str(target_bitrate),
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "faststart",
                output_path
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        try:
            os.remove(input_path)
        except:
            pass

        if result.returncode != 0:
            raise DownloadError(f"FFmpeg error: {result.stderr[:200]}")

        return output_path

    # -----------------------------
    # MAIN DOWNLOAD FUNCTION
    # -----------------------------
    def _download_sync(self, url: str) -> DownloadedVideo:
        url = self._normalize_url(url)
        opts = self._get_opts(url)

        print(f"DEBUG: Начинаю yt-dlp загрузку: {url}")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info)

                if not os.path.exists(downloaded_path):
                    raise DownloadError("Downloaded file not found")

                duration = info.get("duration", 0)
                final_path = self._process_video(downloaded_path, duration)

                print(f"DEBUG: Загрузка завершена. Файл: {final_path}, Размер: {os.path.getsize(final_path)}")

                return DownloadedVideo(
                    path=final_path,
                    title=info.get("title", "Video"),
                    duration=int(duration or 0),
                    author=info.get("uploader", "Unknown"),
                    width=info.get("width", 0) or 0,
                    height=info.get("height", 0) or 0,
                    thumb_url=info.get("thumbnail", ""),
                    file_size=os.path.getsize(final_path),
                )

        except Exception as e:
            print(f"DEBUG ERROR: {e}")
            raise DownloadError(str(e))

    async def download(self, url: str) -> DownloadedVideo:
        return await asyncio.to_thread(self._download_sync, url)
