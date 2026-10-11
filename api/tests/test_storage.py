import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.storage import (
    InsufficientStorageError,
    InvalidUploadError,
    StorageError,
    StorageManager,
    StoredObject,
    UnsupportedFileTypeError,
    parse_size,
)


class MemoryUpload:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content)
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class SmallChunkUpload(MemoryUpload):
    async def read(self, size: int = -1) -> bytes:
        return await super().read(min(size, 3))


class StorageManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / ".localstorage"
        self.manager = StorageManager(
            self.root,
            minimum_free_bytes=0,
        )

    @staticmethod
    def visible_contents(path: Path) -> set[str]:
        internal = {
            ".storage.lock",
            ".storage-index.sqlite3",
            ".storage-index.sqlite3-journal",
            ".storage-index.sqlite3-wal",
            ".storage-index.sqlite3-shm",
        }
        return {item.name for item in path.iterdir() if item.name not in internal}

    def test_parse_storage_sizes(self) -> None:
        self.assertEqual(parse_size(123), 123)
        self.assertEqual(parse_size("1.5 MB"), 1_500_000)
        self.assertEqual(parse_size("2 GiB"), 2 * 1024**3)
        with self.assertRaises(ValueError):
            parse_size("-1 GB")
        with self.assertRaises(ValueError):
            parse_size(True)

    async def test_creates_default_and_supports_multiple_storage_roots(self) -> None:
        extra_root = Path(self.temp_dir.name) / "secondary" / ".storage"
        storage_id = self.manager.add_storage(
            extra_root, "1 MiB", storage_id="secondary"
        )
        stored = await self.manager.save_upload(
            MemoryUpload(b"hello"),
            "C:\\fakepath\\episode.txt",
            storage_id=storage_id,
        )

        self.assertTrue(self.root.is_dir())
        self.assertTrue(extra_root.is_dir())
        self.assertEqual(stored.storage_id, "secondary")
        self.assertEqual(stored.media_type, "text/plain")
        self.assertEqual(stored.path.read_bytes(), b"hello")
        self.assertEqual(self.manager.get_storage(storage_id).used_bytes, 5)
        self.assertEqual(len(self.manager.list_storages()), 2)
        self.assertNotIn("episode", stored.filename)
        entries = self.manager.list_entries(storage_id=storage_id)
        self.assertIn("", {entry.relative_path for entry in entries})
        self.assertIn(stored.filename, {entry.relative_path for entry in entries})

    async def test_index_persists_and_is_reused_by_a_new_manager(self) -> None:
        stored = await self.manager.save_upload(
            MemoryUpload(b"persistent"), "episode.txt"
        )
        second_manager = StorageManager(
            self.root,
            minimum_free_bytes=0,
        )

        self.assertTrue(stored.path.is_file())
        self.assertIn(
            stored.filename,
            {
                entry.relative_path
                for entry in second_manager.list_entries()
            },
        )

    def test_first_registration_purges_unindexed_existing_contents(self) -> None:
        existing_root = Path(self.temp_dir.name) / "existing"
        nested = existing_root / "shows" / "old"
        nested.mkdir(parents=True)
        (nested / "episode.txt").write_text("unindexed", encoding="utf-8")

        manager = StorageManager(existing_root, minimum_free_bytes=0)

        self.assertEqual(self.visible_contents(existing_root), set())
        self.assertTrue((existing_root / ".storage-index.sqlite3").is_file())
        self.assertEqual(
            {entry.relative_path for entry in manager.list_entries()},
            {""},
        )

    def test_add_directory_indexes_all_parent_directories(self) -> None:
        entry = self.manager.add_directory("shows/space-opera/season-1")
        self.assertTrue(entry.is_directory)
        self.assertEqual(entry.relative_path, "shows/space-opera/season-1")
        self.assertEqual(
            {
                item.relative_path
                for item in self.manager.list_entries()
                if item.is_directory
            },
            {"", "shows", "shows/space-opera", "shows/space-opera/season-1"},
        )

    async def test_async_management_helpers_work(self) -> None:
        await self.manager.async_add_directory("shows/example")
        other_root = Path(self.temp_dir.name) / "async-storage"
        storage_id = await self.manager.async_add_storage(
            other_root, storage_id="async"
        )
        entries = await self.manager.async_list_entries()
        info = await self.manager.async_get_storage(self.manager.default_storage_id)

        self.assertIn("shows/example", {entry.relative_path for entry in entries})
        self.assertEqual(info.used_bytes, 0)
        self.assertEqual(storage_id, "async")

    async def test_remove_file_and_recursive_directory_updates_index(self) -> None:
        self.manager.add_directory("shows/example")
        stored = await self.manager.save_upload(
            MemoryUpload(b"episode"),
            "episode.txt",
            directory="shows/example",
        )
        self.manager.remove(f"shows/example/{stored.filename}")
        self.assertFalse(stored.path.exists())

        stored = await self.manager.save_upload(
            MemoryUpload(b"episode two"),
            "episode-two.txt",
            directory="shows/example",
        )
        self.assertIn(
            f"shows/example/{stored.filename}",
            {entry.relative_path for entry in self.manager.list_entries()},
        )

        with self.assertRaises(StorageError):
            self.manager.remove("shows", recursive=False)
        self.manager.remove("shows")

        self.assertFalse((self.root / "shows").exists())
        self.assertEqual(
            {entry.relative_path for entry in self.manager.list_entries()},
            {""},
        )

    async def test_reconciliation_deletes_unindexed_and_prunes_missing_entries(self) -> None:
        unindexed = self.root / "outside.txt"
        unindexed.write_text("external", encoding="utf-8")
        report = self.manager.reconcile_storage()
        self.assertGreaterEqual(report.removed_count, 1)
        self.assertFalse(unindexed.exists())

        stored = await self.manager.save_upload(
            MemoryUpload(b"indexed"), "a.txt"
        )
        stored.path.unlink()
        entries = self.manager.list_entries()
        self.assertNotIn(stored.filename, {entry.relative_path for entry in entries})

    def test_reconciliation_removes_symlink_without_touching_its_target(self) -> None:
        outside_file = Path(self.temp_dir.name) / "outside.txt"
        outside_file.write_text("keep this", encoding="utf-8")
        link = self.root / "outside-link"
        link.symlink_to(outside_file)

        self.manager.reconcile_storage()

        self.assertFalse(link.exists())
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "keep this")

    def test_corrupt_index_fails_closed_without_deleting_storage_files(self) -> None:
        important_file = self.root / "important.txt"
        important_file.write_text("keep until index is repaired", encoding="utf-8")
        (self.root / ".storage-index.sqlite3").write_bytes(b"not a sqlite database")

        with self.assertRaises(StorageError):
            self.manager.reconcile_storage()
        self.assertEqual(
            important_file.read_text(encoding="utf-8"),
            "keep until index is repaired",
        )

    async def test_accepts_supported_content_signatures(self) -> None:
        image_png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\xaeB`\x82"
        image_webp = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP"
        image_bmp = b"BM" + (14).to_bytes(4, "little") + b"\x00" * 8
        video_mp4 = (16).to_bytes(4, "big") + b"ftypisom" + b"\x00" * 4
        video_avi = b"RIFF" + (8).to_bytes(4, "little") + b"AVI " + b"\x00" * 4
        supported_uploads = [
            ("cover.jpg", b"\xff\xd8\xff\x00\xff\xd9", "image/jpeg"),
            ("cover.jpeg", b"\xff\xd8\xff\x00\xff\xd9", "image/jpeg"),
            ("cover.png", image_png, "image/png"),
            ("cover.gif", b"GIF89a\x00;", "image/gif"),
            ("cover.webp", image_webp, "image/webp"),
            ("cover.bmp", image_bmp, "image/bmp"),
            ("cover.tif", b"II*\x00", "image/tiff"),
            ("cover.tiff", b"II*\x00", "image/tiff"),
            ("episode.mp4", video_mp4, "video/mp4"),
            ("episode.m4v", video_mp4, "video/mp4"),
            ("episode.mov", video_mp4, "video/quicktime"),
            ("episode.mkv", b"\x1a\x45\xdf\xa3\x00", "video/x-matroska"),
            ("episode.webm", b"\x1a\x45\xdf\xa3\x00", "video/webm"),
            ("episode.avi", video_avi, "video/x-msvideo"),
            ("notes.txt", b"Plain text\n", "text/plain"),
            ("captions.srt", b"1\n00:00:00,000 --> 00:00:01,000\nHello\n", "text/plain"),
            ("captions.vtt", b"WEBVTT\n\nHello\n", "text/plain"),
        ]

        for filename, content, expected_type in supported_uploads:
            with self.subTest(filename=filename):
                stored = await self.manager.save_upload(
                    MemoryUpload(content), filename
                )
                self.assertEqual(stored.media_type, expected_type)
                self.assertEqual(stored.path.read_bytes(), content)

    async def test_accepts_signatures_split_across_short_reads(self) -> None:
        content = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP"
        stored = await self.manager.save_upload(
            SmallChunkUpload(content), "cover.webp"
        )
        self.assertEqual(stored.path.read_bytes(), content)

    async def test_rejects_unsupported_types_and_mismatched_signatures(self) -> None:
        with self.assertRaises(UnsupportedFileTypeError):
            await self.manager.save_upload(MemoryUpload(b"<script>"), "bad.html")
        with self.assertRaises(UnsupportedFileTypeError):
            await self.manager.save_upload(MemoryUpload(b"\x89PNG\r\n\x1a\n"), "bad.jpg")

        self.assertEqual(
            self.visible_contents(self.root), set()
        )

    async def test_rejects_invalid_and_empty_text(self) -> None:
        with self.assertRaises(InvalidUploadError):
            await self.manager.save_upload(MemoryUpload(b"\xff"), "bad.txt")
        with self.assertRaises(InvalidUploadError):
            await self.manager.save_upload(MemoryUpload(b"before\x00after"), "bad.txt")
        with self.assertRaises(InvalidUploadError):
            await self.manager.save_upload(MemoryUpload(b""), "empty.txt")

    async def test_enforces_allocated_space_and_cleans_partial_uploads(self) -> None:
        limited_manager = StorageManager(
            Path(self.temp_dir.name) / "limited",
            "4 B",
            minimum_free_bytes=0,
        )
        with self.assertRaises(InsufficientStorageError):
            await limited_manager.save_upload(
                MemoryUpload(b"five!"),
                "too-large.txt",
            )
        self.assertEqual(
            self.visible_contents(Path(self.temp_dir.name) / "limited"), set()
        )

    async def test_serializes_quota_checks_across_managers_for_same_path(self) -> None:
        first_manager = StorageManager(
            self.root, "7 B", minimum_free_bytes=0
        )
        second_manager = StorageManager(
            self.root, "7 B", minimum_free_bytes=0
        )
        results = await asyncio.gather(
            first_manager.save_upload(MemoryUpload(b"first"), "first.txt"),
            second_manager.save_upload(MemoryUpload(b"other"), "second.txt"),
            return_exceptions=True,
        )

        self.assertEqual(sum(isinstance(item, StoredObject) for item in results), 1)
        self.assertEqual(
            sum(isinstance(item, InsufficientStorageError) for item in results),
            1,
        )
        self.assertEqual(
            first_manager.get_storage(first_manager.default_storage_id).used_bytes,
            5,
        )

    async def test_checks_physical_space_before_writing_each_chunk(self) -> None:
        content = b"valid text"
        with patch(
            "core.storage.shutil.disk_usage",
            return_value=SimpleNamespace(free=1),
        ):
            with self.assertRaises(InsufficientStorageError):
                await self.manager.save_upload(MemoryUpload(content), "text.txt")
        self.assertEqual(self.visible_contents(self.root), set())

    async def test_rejects_paths_as_storage_ids(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.add_storage(
                Path(self.temp_dir.name) / "other",
                storage_id="../outside",
            )


if __name__ == "__main__":
    unittest.main()
