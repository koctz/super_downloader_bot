import yt_dlp

def get_youtube_formats(url: str):
    """
    Возвращает:
    - title: название ролика
    - thumbnail: ссылка на превью
    - channel: название канала
    - channel_url: ссылка на канал
    - formats: список доступных видеоформатов
    - audio_format: ID аудиоформата
    """

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title")
    thumbnail = info.get("thumbnail")
    channel = info.get("channel")
    channel_url = info.get("channel_url")

    formats = []
    for f in info["formats"]:
        # Берём только форматы, где есть и видео, и аудио
        if f.get("vcodec") != "none" and f.get("acodec") != "none":
            size = None
            if f.get("filesize"):
                size = round(f["filesize"] / 1024 / 1024)

            resolution = f.get("resolution")
            if not resolution:
                if f.get("height"):
                    resolution = f"{f['height']}p"
                else:
                    resolution = "unknown"

            formats.append({
                "format_id": f["format_id"],
                "resolution": resolution,
                "ext": f["ext"],
                "size": size,
            })

    # Ищем лучший аудиоформат
    audio_format = None
    for f in info["formats"]:
        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            audio_format = f["format_id"]
            break

    return {
        "title": title,
        "thumbnail": thumbnail,
        "channel": channel,
        "channel_url": channel_url,
        "formats": formats,
        "audio_format": audio_format,
    }
