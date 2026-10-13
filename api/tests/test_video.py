import asyncio
import json
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from core.storage import StorageManager
from core.video import VideoTranscodingError, browser_compatible_video
from models import Episode, Seasons, Shows
from routes.media import _store_browser_compatible_episode, transcode_my_episode


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and ffprobe are required for video transcoding tests.",
)
class VideoTranscodingTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcodes_uploaded_video_to_h264_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.avi"
            subprocess.run(
                [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=64x64:d=0.25",
                    "-c:v",
                    "mpeg4",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            upload = _MemoryVideoUpload(source.read_bytes(), "source.avi")

            manager = StorageManager(
                Path(directory) / "storage",
                minimum_free_bytes=0,
                reconciliation_interval_seconds=None,
            )
            self.addCleanup(manager.close)
            stored = await _store_browser_compatible_episode(
                manager,
                upload,
                "show/season-1/episode-1",
            )

            probe = subprocess.run(
                [
                    shutil.which("ffprobe") or "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=format_name:stream=codec_name,codec_type,pix_fmt,width,height",
                    "-of",
                    "json",
                    str(stored.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metadata = json.loads(probe.stdout)
            video_stream = next(
                stream
                for stream in metadata["streams"]
                if stream["codec_type"] == "video"
            )
            self.assertIn("mp4", metadata["format"]["format_name"])
            self.assertEqual(video_stream["codec_name"], "h264")
            self.assertEqual(video_stream["pix_fmt"], "yuv420p")

    async def test_rejects_upload_larger_than_available_storage(self) -> None:
        upload = _MemoryVideoUpload(b"video", "source.mp4")
        with self.assertRaisesRegex(
            VideoTranscodingError,
            "available storage capacity",
        ):
            async with browser_compatible_video(
                upload,
                max_input_bytes=4,
            ):
                self.fail("Oversized input should be rejected before transcoding.")

    async def test_owner_can_transcode_an_existing_episode_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.avi"
            subprocess.run(
                [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=64x64:d=0.25",
                    "-c:v",
                    "mpeg4",
                    str(source_path),
                ],
                check=True,
                capture_output=True,
            )
            manager = StorageManager(
                Path(directory) / "storage",
                minimum_free_bytes=0,
                reconciliation_interval_seconds=None,
            )
            self.addCleanup(manager.close)

            owner = SimpleNamespace(id=uuid.uuid4())
            show_id = uuid.uuid4()
            season_id = uuid.uuid4()
            episode_id = uuid.uuid4()
            show = SimpleNamespace(id=show_id, created_by_id=owner.id)
            season = SimpleNamespace(
                id=season_id,
                show_id=show_id,
                season_number=1,
            )
            episode = SimpleNamespace(
                id=episode_id,
                season_id=season_id,
                created_by_id=owner.id,
            )
            episode_directory = f"{show_id}/season-1/episode-{episode_id}"
            await manager.async_add_directory(episode_directory)
            await manager.save_upload(
                _MemoryVideoUpload(source_path.read_bytes(), "original.avi"),
                filename="original.avi",
                directory=episode_directory,
            )
            objects = {
                Episode: (episode_id, episode),
                Seasons: (season_id, season),
            }

            class Session:
                async def get(self, model, identity):
                    if model is Shows:
                        return show if identity == show_id else None
                    expected_id, value = objects[model]
                    return value if identity == expected_id else None

            request = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(storage=manager))
            )
            converted_episode = await transcode_my_episode(
                episode_id,
                request,
                db=Session(),
                current_user=owner,
            )
            self.assertIs(converted_episode, episode)

            entries = await manager.async_list_entries(
                storage_id=manager.default_storage_id
            )
            stored_videos = [
                entry
                for entry in entries
                if entry.relative_path.startswith(f"{episode_directory}/")
                and not entry.is_directory
            ]
            self.assertEqual(len(stored_videos), 1)
            self.assertTrue(stored_videos[0].relative_path.endswith(".mp4"))


class _MemoryVideoUpload:
    def __init__(self, content: bytes, filename: str) -> None:
        self.content = content
        self.filename = filename
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content)
        await asyncio.sleep(0)
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk
