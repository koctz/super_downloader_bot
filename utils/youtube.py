import yt_dlp

def get_youtube_formats(url: str):
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
        # Берём только форматы, которые можно скачать как единый файл
        if (
            f.get("vcodec") != "none" and
            f.get("acodec") != "none" and
            f.get("height") and
            f.get("ext") in ("mp4", "webm")
        ):
            size = None
            if f.get("filesize"):
                size = round(f["filesize"] / 1024 / 1024)

            resolution = f"{f['height']}p"

            formats.append({
                "format_id": f["format_id"],
                "resolution": resolution,
                "size": size,
            })

    # Сортировка по качеству (от высокого к низкому)
    formats.sort(key=lambda x: int(x["resolution"][:-1]), reverse=True)

    # Аудио
    audio_format = None
    for f in info["formats"]:
        if (
            f.get("vcodec") == "none" and
            f.get("acodec") != "none" and
            f.get("filesize")
        ):
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
