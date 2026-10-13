"""Video normalization for browser-compatible episode playback."""

import asyncio
import shutil
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol


class AsyncVideoUpload(Protocol):
    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...


class VideoTranscodingError(Exception):
    """Raised when FFmpeg cannot produce a browser-compatible video."""


class VideoTranscoderUnavailable(VideoTranscodingError):
    """Raised when the FFmpeg executable is not installed."""


class _TemporaryVideoUpload:
    def __init__(self, path: Path) -> None:
        self.filename = "episode.mp4"
        self.size = path.stat().st_size
        self._file = path.open("rb")

    async def read(self, size: int = -1) -> bytes:
        return await asyncio.to_thread(self._file.read, size)

    def close(self) -> None:
        self._file.close()


class StoredVideoUpload:
    """Async-readable wrapper for a video already present in storage."""

    def __init__(self, path: Path) -> None:
        self.filename = path.name
        self.size = path.stat().st_size
        self._file = path.open("rb")

    async def read(self, size: int = -1) -> bytes:
        return await asyncio.to_thread(self._file.read, size)

    def close(self) -> None:
        self._file.close()


@asynccontextmanager
async def browser_compatible_video(
    upload: AsyncVideoUpload,
    max_input_bytes: int,
) -> AsyncGenerator[_TemporaryVideoUpload, None]:
    """Transcode an upload to H.264/AAC MP4 for broad browser support."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise VideoTranscoderUnavailable(
            "FFmpeg is required to process episode videos but is not installed."
        )

    with tempfile.TemporaryDirectory(prefix="animewatcher-video-") as directory:
        source_path = Path(directory) / "source-upload"
        output_path = Path(directory) / "episode.mp4"

        with source_path.open("wb") as source_file:
            total_bytes = 0
            while chunk := await upload.read(1024 * 1024):
                if not isinstance(chunk, bytes):
                    raise VideoTranscodingError(
                        "The uploaded video stream did not return bytes."
                    )
                total_bytes += len(chunk)
                if total_bytes > max_input_bytes:
                    raise VideoTranscodingError(
                        "The uploaded video exceeds the available storage capacity."
                    )
                source_file.write(chunk)

        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            (
                "scale='min(1920,iw)':'min(1080,ih)':"
                "force_original_aspect_ratio=decrease:force_divisible_by=2"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60 * 60,
            )
        except (asyncio.CancelledError, TimeoutError):
            process.kill()
            await process.communicate()
            raise

        if process.returncode != 0 or not output_path.is_file():
            details = stderr.decode("utf-8", errors="replace").strip()
            message = "FFmpeg could not convert this video."
            if details:
                message = f"{message} {details[-1000:]}"
            raise VideoTranscodingError(message)
        if output_path.stat().st_size == 0:
            raise VideoTranscodingError("FFmpeg produced an empty video.")

        converted = _TemporaryVideoUpload(output_path)
        try:
            yield converted
        finally:
            converted.close()
