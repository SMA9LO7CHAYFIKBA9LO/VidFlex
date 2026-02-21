import os
import re
import uuid
import threading
import subprocess
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
import imageio_ffmpeg

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


def _strip_ansi(text: str) -> str:
    """Remove ANSI/VT100 escape sequences from a string."""
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', str(text))

app = Flask(__name__)
CORS(app)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# ---------------------------------------------------------------------------
# Setup & Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.environ.get("VERCEL") == "1":
    DOWNLOAD_DIR = "/tmp/downloads"
    CONVERT_DIR = "/tmp/conversions"
else:
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    CONVERT_DIR = os.path.join(BASE_DIR, "conversions")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(CONVERT_DIR, exist_ok=True)

SUPPORTED_VIDEO_FORMATS = ["mp4", "mkv", "avi", "mov", "webm", "flv"]
SUPPORTED_AUDIO_FORMATS = ["mp3", "aac", "wav", "ogg", "m4a", "flac"]
ALL_FORMATS = SUPPORTED_VIDEO_FORMATS + SUPPORTED_AUDIO_FORMATS


# ---------------------------------------------------------------------------
# Routes: Frontend
# ---------------------------------------------------------------------------
@app.route("/")
def index_redirect():
    from flask import redirect
    return redirect("/downloader")

@app.route("/downloader")
def index():
    return render_template("downloader.html", active_page="downloader")

@app.route("/converter")
def converter_redirect():
    from flask import redirect
    return redirect("/format-converter")

@app.route("/format-converter")
def converter():
    return render_template("converter.html", active_page="converter")


# ---------------------------------------------------------------------------
# Helper: cleanup file after response is sent
# ---------------------------------------------------------------------------
def _delete_later(path: str, delay: int = 120):
    """Delete *path* after *delay* seconds in a background thread."""
    def _rm():
        import time
        time.sleep(delay)
        try:
            os.remove(path)
        except OSError:
            pass
    t = threading.Thread(target=_rm, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Route: GET /api/info  –  fetch video metadata + available formats
# ---------------------------------------------------------------------------
@app.route("/api/info", methods=["GET"])
def get_info():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["tv", "mweb"]}},
    }

    cookies_path = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        return jsonify({"error": _strip_ansi(exc)}), 400
    except Exception as exc:
        return jsonify({"error": _strip_ansi(f"Unexpected error: {exc}")}), 500

    # Standard resolution tiers (highest first)
    STANDARD_HEIGHTS = [4320, 2160, 1440, 1080, 720, 480, 360, 240]

    # Approximate video-only bitrates (bits/sec) used for size estimation
    TYPICAL_BITRATE = {
        4320: 80_000_000,
        2160: 16_000_000,
        1440:  8_000_000,
        1080:  4_000_000,
        720:   2_500_000,
        480:   1_000_000,
        360:     500_000,
        240:     250_000,
    }

    formats_raw = info.get("formats", [])
    duration    = info.get("duration") or 0   # seconds

    # Build a lookup: exact height → best format entry (highest tbr video stream)
    best_per_height: dict[int, dict] = {}
    for f in formats_raw:
        height = f.get("height")
        vcodec = f.get("vcodec", "")
        if not height or not vcodec or vcodec == "none":
            continue
        tbr = f.get("tbr") or 0
        if height not in best_per_height or tbr > best_per_height[height].get("tbr", 0):
            best_per_height[height] = {
                "format_id": f.get("format_id", ""),
                "tbr":       tbr,
                "filesize":  f.get("filesize") or f.get("filesize_approx"),
            }

    # Determine the video's true maximum height
    max_height = max(best_per_height.keys()) if best_per_height else 0

    # Build the list — all standard tiers ≤ max_height
    sorted_resolutions = []
    for h in STANDARD_HEIGHTS:
        if h > max_height:
            continue
        if h in best_per_height:
            entry = best_per_height[h]
            # Real format: use reported filesize, fall back to bitrate estimate
            fs = entry["filesize"]
            if not fs and duration:
                tbr_bps = (entry["tbr"] or TYPICAL_BITRATE.get(h, 1_000_000)) * 1000
                fs = int(duration * tbr_bps / 8)
            sorted_resolutions.append({
                "label":     f"{h}p",
                "format_id": entry["format_id"],
                "filesize":  fs,
                "estimated": entry["filesize"] is None,
            })
        else:
            # Synthetic tier — estimate size from duration × typical bitrate
            est = None
            if duration and h in TYPICAL_BITRATE:
                est = int(duration * TYPICAL_BITRATE[h] / 8)
            sorted_resolutions.append({
                "label":     f"{h}p",
                "format_id": "",      # blank → height-based download
                "filesize":  est,
                "estimated": True,    # flag so UI can show "~" prefix
            })

    # Nothing found at all → expose the raw best
    if not sorted_resolutions and best_per_height:
        best_h = max(best_per_height.keys())
        entry  = best_per_height[best_h]
        sorted_resolutions.append({
            "label":     f"{best_h}p",
            "format_id": entry["format_id"],
            "filesize":  entry["filesize"],
            "estimated": False,
        })



    return jsonify({
        "title": info.get("title", "Unknown"),
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", ""),
        "platform": info.get("extractor_key", ""),
        "resolutions": sorted_resolutions,
    })


# ---------------------------------------------------------------------------
# Route: POST /api/download  –  download video or extract audio
# ---------------------------------------------------------------------------
@app.route("/api/download", methods=["POST"])
def download_video():
    # Accept both JSON (API) and form-encoded (native browser form submit)
    if request.content_type and "application/json" in request.content_type:
        data = request.get_json(force=True) or {}
    else:
        data = request.form

    url        = data.get("url", "").strip()
    resolution = data.get("resolution", "720p")
    format_id  = (data.get("format_id") or "").strip()
    media_type = data.get("media_type", "video")


    if not url:
        return jsonify({"error": "No URL provided"}), 400

    unique_id       = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"{unique_id}.%(ext)s")

    if media_type == "audio":
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "ffmpeg_location": FFMPEG_PATH,
            "extractor_args": {"youtube": {"player_client": ["tv", "mweb"]}},
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
        cookies_path = os.path.join(BASE_DIR, "cookies.txt")
        if os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        expected_ext = "mp3"
    else:
        # If we have an exact format_id (from the /api/info dropdown), use it directly.
        # This guarantees the user downloads EXACTLY the resolution they selected.
        # We pair the video-only stream with the best available audio and merge with FFmpeg.
        if format_id:
            fmt_string = (
                f"{format_id}+bestaudio[ext=m4a]/"
                f"{format_id}+bestaudio/"
                f"{format_id}"        # last resort: video-only if no audio available
            )
        else:
            # Fallback: no format_id — height-based best quality selection
            try:
                height = int(resolution.replace("p", ""))
            except ValueError:
                height = 720
            fmt_string = (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}][ext=mp4]/"
                f"best[height<={height}]/"
                f"best"
            )

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": fmt_string,
            "outtmpl": output_template,
            "ffmpeg_location": FFMPEG_PATH,
            "extractor_args": {"youtube": {"player_client": ["tv", "mweb"]}},
            "merge_output_format": "mp4",
        }
        cookies_path = os.path.join(BASE_DIR, "cookies.txt")
        if os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        expected_ext = "mp4"


    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "download")
    except yt_dlp.utils.DownloadError as exc:
        return jsonify({"error": _strip_ansi(exc)}), 400
    except Exception as exc:
        return jsonify({"error": _strip_ansi(f"Unexpected error: {exc}")}), 500

    # --- Locate the downloaded file ---
    # 1) Prefer yt-dlp's own reported filepath (most reliable, avoids temp files)
    out_file = None
    try:
        req_dls = info.get("requested_downloads") or []
        if req_dls and req_dls[-1].get("filepath"):
            candidate = req_dls[-1]["filepath"]
            if os.path.isfile(candidate) and not candidate.endswith(".part"):
                out_file = candidate
    except Exception:
        pass

    # 2) Fallback: scan directory, skip .part temp files, prefer .mp4
    if not out_file:
        candidates = []
        for fname in os.listdir(DOWNLOAD_DIR):
            if fname.startswith(unique_id) and not fname.endswith(".part"):
                candidates.append(os.path.join(DOWNLOAD_DIR, fname))
        if candidates:
            # prefer .mp4 if available, else take the largest file
            mp4s = [f for f in candidates if f.endswith(".mp4")]
            out_file = mp4s[0] if mp4s else max(candidates, key=os.path.getsize)

    if not out_file or not os.path.exists(out_file):
        return jsonify({"error": "Download failed – file not found on disk"}), 500

    # Use REAL extension from the actual file on disk
    real_ext = os.path.splitext(out_file)[1].lstrip(".")
    if not real_ext:
        real_ext = "mp4"   # safe default when extension is unknown

    # Build a clean, friendly download filename from the video title
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-" ).strip()[:80]
    if not safe_title:
        safe_title = "download"
    download_name = f"{safe_title}.{real_ext}"

    # Map extension → MIME type
    mime_map = {
        "mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska",
        "avi": "video/x-msvideo", "mov": "video/quicktime", "flv": "video/x-flv",
        "mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac",
        "ogg": "audio/ogg", "wav": "audio/wav", "opus": "audio/ogg",
    }
    mime = mime_map.get(real_ext, "application/octet-stream")

    _delete_later(out_file)

    return send_file(
        out_file,
        as_attachment=True,
        download_name=download_name,
        mimetype=mime,
    )


# ---------------------------------------------------------------------------
# Route: POST /api/convert  –  convert uploaded media file to target format
# ---------------------------------------------------------------------------
@app.route("/api/v2/convert", methods=["POST"])
def convert_media():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    target_format = request.form.get("target_format", "mp3").lower().strip()

    if target_format not in ALL_FORMATS:
        return jsonify({
            "error": f"Unsupported format '{target_format}'. "
                     f"Supported: {', '.join(ALL_FORMATS)}"
        }), 400

    unique_id = uuid.uuid4().hex
    original_ext = os.path.splitext(file.filename)[1]
    input_path = os.path.join(CONVERT_DIR, f"{unique_id}_input{original_ext}")
    output_path = os.path.join(CONVERT_DIR, f"{unique_id}_output.{target_format}")

    file.save(input_path)

    # Build ffmpeg command using imageio-ffmpeg's guaranteed binary path
    cmd = [FFMPEG_PATH, "-y", "-i", input_path]

    # Codec hints
    if target_format == "mp3":
        cmd += ["-codec:a", "libmp3lame", "-q:a", "2"]
    elif target_format == "aac":
        cmd += ["-codec:a", "aac", "-b:a", "192k"]
    elif target_format == "wav":
        cmd += ["-codec:a", "pcm_s16le"]
    elif target_format == "ogg":
        cmd += ["-codec:a", "libvorbis"]
    elif target_format == "m4a":
        cmd += ["-codec:a", "aac", "-b:a", "192k"]
    elif target_format == "flac":
        cmd += ["-codec:a", "flac"]
    elif target_format == "mp4":
        cmd += ["-codec:v", "libx264", "-crf", "23", "-preset", "fast",
                "-codec:a", "aac", "-b:a", "192k"]
    elif target_format == "mkv":
        cmd += ["-codec:v", "libx264", "-crf", "23", "-preset", "fast",
                "-codec:a", "aac", "-b:a", "192k"]
    elif target_format == "webm":
        cmd += ["-codec:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
                "-codec:a", "libopus"]
    elif target_format == "avi":
        cmd += ["-codec:v", "mpeg4", "-codec:a", "mp3"]
    elif target_format == "mov":
        cmd += ["-codec:v", "libx264", "-codec:a", "aac"]
    elif target_format == "flv":
        cmd += ["-codec:v", "libx264", "-codec:a", "aac"]

    cmd.append(output_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            _delete_later(input_path, 0)
            return jsonify({
                "error": "FFmpeg conversion failed",
                "details": result.stderr[-2000:],
            }), 500
    except subprocess.TimeoutExpired:
        _delete_later(input_path, 0)
        return jsonify({"error": "Conversion timed out (>5 min)"}), 500
    except FileNotFoundError:
        _delete_later(input_path, 0)
        return jsonify({
            "error": "FFmpeg not found. Please install FFmpeg and add it to PATH."
        }), 500

    _delete_later(input_path, 0)
    _delete_later(output_path)

    original_stem = os.path.splitext(file.filename)[0]
    safe_stem = "".join(c for c in original_stem if c.isalnum() or c in " _-").strip()[:60]
    download_name = f"{safe_stem}_converted.{target_format}"

    # Determine MIME type
    mime_map = {
        "mp3": "audio/mpeg", "aac": "audio/aac", "wav": "audio/wav",
        "ogg": "audio/ogg", "m4a": "audio/mp4", "flac": "audio/flac",
        "mp4": "video/mp4", "mkv": "video/x-matroska", "avi": "video/x-msvideo",
        "mov": "video/quicktime", "webm": "video/webm", "flv": "video/x-flv",
    }
    mime = mime_map.get(target_format, "application/octet-stream")

    return send_file(
        output_path,
        as_attachment=True,
        download_name=download_name,
        mimetype=mime,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
