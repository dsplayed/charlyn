"""Video utilities for Charlyn — anime download, storage.to upload, and worker registration."""
import json
import os
import subprocess
import urllib.request
import urllib.error
from typing import Optional

STORAGE_TO_API = "https://storage.to/api"
VIDEO_WORKER_URL = os.getenv("VIDEO_WORKER_URL", "https://charlyn-video.dsplay.workers.dev")
VIDEO_API_KEY = os.getenv("VIDEO_API_KEY", "")

MAX_PART_DURATION = 30 * 60  # 30 minutes in seconds


def _worker_post(path: str, data: dict) -> dict | None:
    api_key = VIDEO_API_KEY
    if not api_key:
        return None
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{VIDEO_WORKER_URL}{path}",
            data=body,
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "User-Agent": "Charlyn/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None


def _storage_to_init(filename: str, content_type: str, size: int) -> dict | None:
    """Step 1: Initiate upload to storage.to. Returns presigned URL and key."""
    try:
        body = json.dumps({
            "filename": filename,
            "content_type": content_type,
            "size": size,
        }).encode()
        req = urllib.request.Request(
            f"{STORAGE_TO_API}/upload/init",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Charlyn/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode() if e.fp else str(e)
        return None
    except Exception:
        return None


def _storage_to_upload_file(presigned_url: str, file_data: bytes, content_type: str) -> bool:
    """Step 2: PUT file bytes to presigned URL."""
    try:
        req = urllib.request.Request(
            presigned_url,
            data=file_data,
            headers={"Content-Type": content_type},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=600) as _:
            return True
    except Exception:
        return False


def _storage_to_confirm(filename: str, size: int, content_type: str, r2_key: str) -> dict | None:
    """Step 3: Confirm upload and get shareable URL."""
    try:
        body = json.dumps({
            "filename": filename,
            "size": size,
            "content_type": content_type,
            "r2_key": r2_key,
        }).encode()
        req = urllib.request.Request(
            f"{STORAGE_TO_API}/upload/confirm",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Charlyn/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode() if e.fp else str(e)
        return None
    except Exception:
        return None


def upload_to_storage_to(file_path: str) -> dict | None:
    """Upload a file to storage.to. Returns {url, raw_url, ...} or None."""
    if not os.path.exists(file_path):
        return None

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    content_type_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
    }
    content_type = content_type_map.get(ext, "video/mp4")
    size = os.path.getsize(file_path)

    init = _storage_to_init(filename, content_type, size)
    if not init:
        return None

    if init.get("type") == "multipart":
        return None

    presigned_url = init.get("presigned_url")
    r2_key = init.get("r2_key")
    if not presigned_url or not r2_key:
        return None

    with open(file_path, "rb") as f:
        file_data = f.read()

    ok = _storage_to_upload_file(presigned_url, file_data, content_type)
    if not ok:
        return None

    confirm = _storage_to_confirm(filename, size, content_type, r2_key)
    if not confirm:
        return None

    return confirm.get("file") or confirm


def get_video_duration(file_path: str) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def split_video(file_path: str, max_duration: int = MAX_PART_DURATION) -> list[str]:
    """Split video into parts if longer than max_duration seconds.
    Returns list of output file paths."""
    duration = get_video_duration(file_path)
    if duration is None:
        return [file_path]

    if duration <= max_duration:
        return [file_path]

    base, ext = os.path.splitext(file_path)
    parts: list[str] = []
    part_num = 1
    start = 0.0

    while start < duration:
        output = f"{base}_part{part_num}{ext}"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", file_path,
             "-ss", str(start),
             "-t", str(max_duration),
             "-c", "copy",
             "-avoid_negative_ts", "make_zero",
             output],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            return [file_path]

        parts.append(output)
        start += max_duration
        part_num += 1

    return parts


def register_with_worker(title: str, storage_url: str, raw_url: str,
                         content_type: str = "video/mp4", size: int = 0,
                         duration: int = 0, part: int = 1,
                         total_parts: int = 1) -> str:
    """Register a storage.to URL with the video worker and get a watch URL."""
    result = _worker_post("/api/register", {
        "title": title,
        "storage_url": storage_url,
        "raw_url": raw_url,
        "content_type": content_type,
        "size": size,
        "duration": duration,
        "part": part,
        "total_parts": total_parts,
    })
    if not result:
        return f"Failed to register with worker. Check VIDEO_API_KEY."

    watch_url = result["watchUrl"]
    return watch_url


def anime_download(anime_name: str) -> str:
    """Download an anime episode using ani-cli.
    Returns the path to the downloaded file or error message."""
    import tempfile
    output_dir = tempfile.mkdtemp(prefix="anime_")

    try:
        result = subprocess.run(
            ["ani-cli", "--download", "--download-dir", output_dir, anime_name],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            return f"ani-cli failed: {result.stderr[:500]}"

        files = os.listdir(output_dir)
        video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.avi', '.webm'))]
        if not video_files:
            return f"No video files found. Output:\n{result.stdout[:1000]}"

        video_files.sort(key=lambda f: os.path.getmtime(os.path.join(output_dir, f)), reverse=True)
        downloaded = os.path.join(output_dir, video_files[0])
        size_mb = os.path.getsize(downloaded) / (1024 * 1024)
        return f"Downloaded: {downloaded} ({size_mb:.1f} MB)"
    except subprocess.TimeoutExpired:
        return "Download timed out after 1 hour"
    except FileNotFoundError:
        return "ani-cli not found. Install it on the server via: brew install ani-cli"
    except Exception as e:
        return f"Download error: {e}"


def download_and_upload(anime_name: str) -> str:
    """Download an anime episode, upload to storage.to, register with worker.
    Auto-splits if video is longer than 30 minutes."""
    dl_result = anime_download(anime_name)
    if not dl_result.startswith("Downloaded:"):
        return dl_result

    file_path = dl_result.replace("Downloaded: ", "").split(" (")[0]
    if not os.path.exists(file_path):
        return f"Downloaded file not found: {file_path}"

    duration = get_video_duration(file_path)
    if duration and duration > MAX_PART_DURATION:
        parts = split_video(file_path)
        if len(parts) == 1 and parts[0] == file_path:
            return _upload_single(file_path, anime_name, duration)

        results = []
        total = len(parts)
        for i, part_path in enumerate(parts, 1):
            r = _upload_single(part_path, f"{anime_name} (Part {i})", duration=None, part=i, total_parts=total)
            results.append(r)
        return "\n---\n".join(results)

    return _upload_single(file_path, anime_name, duration)


def _upload_single(file_path: str, title: str, duration: Optional[float] = None,
                   part: int = 1, total_parts: int = 1) -> str:
    """Upload a single file to storage.to and register with worker."""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    ext = os.path.splitext(file_path)[1].lower()
    content_type_map = {
        ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime",
    }
    content_type = content_type_map.get(ext, "video/mp4")

    sto = upload_to_storage_to(file_path)
    if not sto:
        return f"storage.to upload failed for {title}"

    storage_url = sto.get("url", "")
    raw_url = sto.get("raw_url", "")

    watch_url = register_with_worker(
        title=title,
        storage_url=storage_url,
        raw_url=raw_url,
        content_type=content_type,
        size=os.path.getsize(file_path),
        duration=int(duration) if duration else 0,
        part=part,
        total_parts=total_parts,
    )

    part_str = f"Part {part}/{total_parts} — " if total_parts > 1 else ""
    return (
        f"{part_str}{title}\n"
        f"Size: {size_mb:.1f} MB\n"
        f"Watch: {watch_url}\n"
        f"Direct: {raw_url}\n"
        f"Download page: {storage_url}"
    )
