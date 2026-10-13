import tempfile
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request
from starlette.responses import Response

from core.config import get_settings
from core.security import create_access_token
from core.storage import StorageManager
from models import Episode, GenreEnum, RoleEnum, Seasons, Shows, Users
from routes.auth import login, register
from routes.media import (
    _replace_stored_upload,
    create_my_episode_playback,
    create_season,
    create_show,
    delete_my_episode,
    delete_my_season,
    delete_my_show,
    delete_show,
    get_episode_video,
    get_show_by_title,
    get_show_thumbnail,
    list_season_episodes,
    list_shows,
)
from routes.users import read_user_me
from schemas import UserRegister


class MemoryUpload:
    def __init__(self, content: bytes, filename: str) -> None:
        self.content = content
        self.filename = filename
        self.size = len(content)
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content)
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_creates_user_with_hashed_password(self) -> None:
        class Result:
            def scalar_one_or_none(self):
                return None

        class Session:
            def __init__(self):
                self.added = None
                self.committed = False
                self.refreshed = False

            async def execute(self, statement):
                return Result()

            def add(self, instance):
                self.added = instance

            async def commit(self):
                self.committed = True

            async def refresh(self, instance):
                self.refreshed = True

        session = Session()
        with patch("routes.auth.hash_password", return_value="hashed-secret"):
            created = await register(
                UserRegister(
                    handle="route-test",
                    email="route-test@example.com",
                    password="plain-secret",
                ),
                db=session,
            )
        self.assertIs(created, session.added)
        self.assertEqual(created.password_hashed, "hashed-secret")
        self.assertTrue(session.committed)
        self.assertTrue(session.refreshed)

    async def test_login_accepts_credentials_and_rejects_bad_password(self) -> None:
        user = SimpleNamespace(
            email="route-test@example.com",
            password_hashed="stored-hash",
        )

        class Result:
            def scalar_one_or_none(self):
                return user

        class Session:
            async def execute(self, statement):
                return Result()

        form = SimpleNamespace(
            username="route-test@example.com",
            password="correct-password",
        )
        with (
            patch("routes.auth.verify_password", return_value=True),
            patch("routes.auth.create_access_token", return_value="signed-token"),
        ):
            result = await login(form_data=form, db=Session())
        self.assertEqual(result, {"access_token": "signed-token", "token_type": "bearer"})

        with patch("routes.auth.verify_password", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                await login(form_data=form, db=Session())
        self.assertEqual(raised.exception.status_code, 401)

    async def test_current_user_route_returns_dependency_user(self) -> None:
        user = Users(
            handle="route-user",
            email="route-user@example.com",
            password_hashed="hash",
        )
        self.assertIs(await read_user_me(current_user=user), user)

    async def test_create_and_list_show_without_thumbnail(self) -> None:
        class Result:
            def scalars(self):
                return self

            def all(self):
                return [show]

        class Session:
            def __init__(self):
                self.added = None
                self.committed = False
                self.refreshed = False
                self.statements = []

            def add(self, instance):
                self.added = instance

            async def commit(self):
                self.committed = True

            async def refresh(self, instance):
                self.refreshed = True

            async def execute(self, statement):
                self.statements.append(str(statement))
                return Result()

        session = Session()
        storage = SimpleNamespace()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage=storage)))
        creator = Users(
            handle="show-creator",
            email="show-creator@example.com",
            password_hashed="hash",
        )
        show = await create_show(
            request=request,
            title="Test Show",
            description="A show",
            genre=GenreEnum.ANIME,
            thumbnail=None,
            db=session,
            current_user=creator,
        )
        self.assertIs(show, session.added)
        self.assertEqual(show.title, "Test Show")
        self.assertTrue(session.committed)
        self.assertTrue(session.refreshed)
        self.assertEqual(await list_shows(db=session), [show])
        self.assertIn("is_private", session.statements[-1])
        self.assertIn("is false", session.statements[-1].lower())

    async def test_create_season_assigns_the_next_number_and_creator(self) -> None:
        creator = Users(
            handle="season-creator",
            email="season-creator@example.com",
            password_hashed="hash",
        )
        show = SimpleNamespace(id=uuid.uuid4(), created_by_id=creator.id)

        class Storage:
            async def async_add_directory(self, directory):
                self.directory = directory

        class Session:
            def __init__(self):
                self.scalar_calls = 0
                self.added = None

            async def get(self, model, identity):
                return show

            async def scalar(self, statement):
                self.scalar_calls += 1
                return show if self.scalar_calls == 1 else 4

            def add(self, instance):
                self.added = instance

            async def commit(self):
                pass

            async def refresh(self, instance):
                pass

        storage = Storage()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage=storage)))
        session = Session()
        season = await create_season(
            show_id=show.id,
            request=request,
            name="The next chapter",
            description="New season",
            thumbnail=None,
            db=session,
            current_user=creator,
        )

        self.assertEqual(season.season_number, 5)
        self.assertEqual(season.name, "The next chapter")
        self.assertEqual(season.created_by, creator)
        self.assertEqual(storage.directory, f"{show.id}/season-5")

    async def test_create_season_records_thumbnail_url(self) -> None:
        creator = Users(
            handle="season-thumbnail-creator",
            email="season-thumbnail@example.com",
            password_hashed="hash",
        )
        show = SimpleNamespace(id=uuid.uuid4(), created_by_id=creator.id)

        class Storage:
            async def async_add_directory(self, directory):
                self.directory = directory

        class Session:
            def __init__(self):
                self.scalar_calls = 0
                self.added = None

            async def get(self, model, identity):
                return show

            async def scalar(self, statement):
                self.scalar_calls += 1
                return show if self.scalar_calls == 1 else None

            def add(self, instance):
                self.added = instance

            async def commit(self):
                pass

            async def refresh(self, instance):
                pass

        storage = Storage()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage=storage)))
        session = Session()
        thumbnail = MemoryUpload(b"thumbnail", "cover.png")
        with patch("routes.media._replace_stored_upload") as save_thumbnail:
            season = await create_season(
                show_id=show.id,
                request=request,
                name="Illustrated season",
                description="Season with artwork",
                thumbnail=thumbnail,
                db=session,
                current_user=creator,
            )

        self.assertEqual(
            season.thumbnail_url,
            f"/api/v1/media/seasons/{season.id}/thumbnail",
        )
        save_thumbnail.assert_awaited_once_with(
            storage,
            upload=thumbnail,
            directory=f"{show.id}/season-1/thumbnail",
            fallback_filename="cover.jpg",
        )

    async def test_get_show_by_title_returns_404_when_missing(self) -> None:
        class Result:
            def scalar_one_or_none(self):
                return None

        class Session:
            async def execute(self, statement):
                return Result()

        with self.assertRaises(HTTPException) as raised:
            await get_show_by_title("missing", db=Session())
        self.assertEqual(raised.exception.status_code, 404)

    async def test_get_show_by_title_returns_matching_show(self) -> None:
        show = SimpleNamespace(title="Example")

        class Result:
            def scalar_one_or_none(self):
                return show

        class Session:
            async def execute(self, statement):
                return Result()

        self.assertIs(await get_show_by_title("example", db=Session()), show)

    async def test_list_season_episodes_returns_episodes_in_order(self) -> None:
        season_id = uuid.uuid4()
        show_id = uuid.uuid4()
        episodes = [
            SimpleNamespace(episode_number=1),
            SimpleNamespace(episode_number=2),
        ]

        class Result:
            def scalars(self):
                return self

            def all(self):
                return episodes

        class Session:
            async def get(self, model, identity):
                lookups.append((model, identity))
                if model is Seasons:
                    return SimpleNamespace(id=identity, show_id=show_id)
                return SimpleNamespace(id=identity, is_private=False)

            async def execute(self, statement):
                self.statement = str(statement)
                return Result()

        lookups = []
        session = Session()
        self.assertEqual(
            await list_season_episodes(season_id, db=session),
            episodes,
        )
        self.assertEqual(lookups, [(Seasons, season_id), (Shows, show_id)])
        self.assertIn("ORDER BY episodes.episode_number ASC", session.statement)

    async def test_list_season_episodes_returns_404_for_missing_season(self) -> None:
        class Session:
            async def get(self, model, identity):
                return None

        with self.assertRaises(HTTPException) as raised:
            await list_season_episodes(uuid.uuid4(), db=Session())
        self.assertEqual(raised.exception.status_code, 404)

    async def test_delete_show_removes_storage_and_database_record(self) -> None:
        show_id = uuid.uuid4()

        class Storage:
            def __init__(self):
                self.removed = []

            async def async_list_storages(self):
                return [SimpleNamespace(storage_id="main")]

            async def async_list_entries(self, **kwargs):
                return [
                    SimpleNamespace(relative_path=str(show_id), is_directory=True)
                ]

            async def async_remove(self, relative_path, **kwargs):
                self.removed.append((relative_path, kwargs["storage_id"]))

        class Session:
            def __init__(self):
                self.committed = False
                self.rolled_back = False
                self.executed = False

            async def get(self, model, identity):
                return SimpleNamespace(id=identity)

            async def execute(self, statement):
                self.executed = True

            async def commit(self):
                self.committed = True

            async def rollback(self):
                self.rolled_back = True

        storage = Storage()
        session = Session()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage=storage)))
        admin = SimpleNamespace(role=RoleEnum.ADMIN)

        await delete_show(show_id, request, session, admin)
        self.assertEqual(storage.removed, [(str(show_id), "main")])
        self.assertTrue(session.executed)
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)

    async def test_delete_show_requires_admin_and_existing_show(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

        class Session:
            async def get(self, model, identity):
                return SimpleNamespace(id=identity)

        with self.assertRaises(HTTPException) as raised:
            await delete_show(
                uuid.uuid4(),
                request,
                Session(),
                SimpleNamespace(role=RoleEnum.USER),
            )
        self.assertEqual(raised.exception.status_code, 403)

        class MissingShowSession:
            async def get(self, model, identity):
                return None

        with self.assertRaises(HTTPException) as raised:
            await delete_show(
                uuid.uuid4(),
                request,
                MissingShowSession(),
                SimpleNamespace(role=RoleEnum.ADMIN),
            )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_owner_delete_routes_remove_media_and_records(self) -> None:
        owner_id = uuid.uuid4()
        show_id = uuid.uuid4()
        season_id = uuid.uuid4()
        episode_id = uuid.uuid4()
        owner = SimpleNamespace(id=owner_id)
        show = SimpleNamespace(id=show_id, created_by_id=owner_id)
        season = SimpleNamespace(
            id=season_id,
            show_id=show_id,
            season_number=2,
            created_by_id=owner_id,
        )
        episode = SimpleNamespace(
            id=episode_id,
            season_id=season_id,
            created_by_id=owner_id,
        )
        paths = {
            "show": str(show_id),
            "season": f"{show_id}/season-2",
            "episode": f"{show_id}/season-2/episode-{episode_id}",
        }
        models = {
            (Shows, show_id): show,
            (Seasons, season_id): season,
            (Episode, episode_id): episode,
        }

        class Storage:
            def __init__(self):
                self.removed = []

            async def async_list_storages(self):
                return [SimpleNamespace(storage_id="main")]

            async def async_list_entries(self, **kwargs):
                return [
                    SimpleNamespace(relative_path=path, is_directory=True)
                    for path in paths.values()
                ]

            async def async_remove(self, path, **kwargs):
                self.removed.append((path, kwargs["storage_id"], kwargs["recursive"]))

        class Session:
            def __init__(self):
                self.committed = False
                self.rolled_back = False
                self.statements = []

            async def get(self, model, identity):
                return models.get((model, identity))

            async def execute(self, statement):
                self.statements.append(statement)

            async def commit(self):
                self.committed = True

            async def rollback(self):
                self.rolled_back = True

        routes = (
            (delete_my_show, show_id, "show"),
            (delete_my_season, season_id, "season"),
            (delete_my_episode, episode_id, "episode"),
        )
        for route, media_id, path_key in routes:
            with self.subTest(path=path_key):
                storage = Storage()
                session = Session()
                request = SimpleNamespace(
                    app=SimpleNamespace(state=SimpleNamespace(storage=storage))
                )
                await route(
                    media_id,
                    request,
                    session,
                    owner,
                )
                self.assertEqual(
                    storage.removed,
                    [(paths[path_key], "main", True)],
                )
                self.assertEqual(len(session.statements), 1)
                self.assertTrue(session.committed)
                self.assertFalse(session.rolled_back)

    async def test_owner_delete_routes_reject_content_owned_by_another_user(self) -> None:
        show_id = uuid.uuid4()
        owner = SimpleNamespace(id=uuid.uuid4())
        other_user = SimpleNamespace(id=uuid.uuid4())
        show = SimpleNamespace(id=show_id, created_by_id=owner.id)

        class Session:
            async def get(self, model, identity):
                return show if model is Shows and identity == show_id else None

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with self.assertRaises(HTTPException) as raised:
            await delete_my_show(show_id, request, Session(), other_user)
        self.assertEqual(raised.exception.status_code, 404)

    async def test_thumbnail_route_serves_indexed_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = StorageManager(
                Path(directory) / "storage",
                minimum_free_bytes=0,
                reconciliation_interval_seconds=None,
            )
            self.addCleanup(manager.close)
            show_id = uuid.uuid4()
            thumbnail_dir = f"{show_id}/thumbnail"
            await manager.async_add_directory(thumbnail_dir)
            png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\xaeB`\x82"
            stored = await manager.save_upload(
                MemoryUpload(png, "cover.png"),
                filename="cover.png",
                directory=thumbnail_dir,
            )
            show = Shows(
                id=show_id,
                title="Thumbnail Show",
                description="description",
                genre=GenreEnum.ANIME,
                thumbnail_url=f"/api/v1/media/shows/{show_id}/thumbnail",
            )

            class Session:
                async def get(self, model, identity):
                    return show

            request = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(storage=manager))
            )
            response = await get_show_thumbnail(request, show_id, Session())
            self.assertEqual(Path(response.path), stored.path)

    async def test_episode_video_route_streams_byte_ranges_for_public_show(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = StorageManager(
                Path(directory) / "storage",
                minimum_free_bytes=0,
                reconciliation_interval_seconds=None,
            )
            self.addCleanup(storage.close)
            episode_id = uuid.uuid4()
            season_id = uuid.uuid4()
            show_id = uuid.uuid4()
            episode = SimpleNamespace(id=episode_id, season_id=season_id)
            season = SimpleNamespace(
                id=season_id,
                show_id=show_id,
                season_number=1,
            )
            show = SimpleNamespace(is_private=False)
            video_bytes = (16).to_bytes(4, "big") + b"ftypisom" + b"\x00" * 4
            video_directory = (
                f"{show_id}/season-1/episode-{episode_id}"
            )
            stored = await _replace_stored_upload(
                storage,
                MemoryUpload(video_bytes, "episode.mp4"),
                video_directory,
                "video.mp4",
            )

            class Session:
                async def get(self, model, identity):
                    if model is Episode:
                        return episode
                    if model is Seasons:
                        return season
                    return show

            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": f"/api/v1/media/episodes/{episode_id}/video",
                    "headers": [],
                    "query_string": b"",
                    "app": SimpleNamespace(
                        state=SimpleNamespace(storage=storage)
                    ),
                }
            )
            response = await get_episode_video(
                episode_id,
                request,
                db=Session(),
            )
            self.assertEqual(Path(response.path), stored.path)
            self.assertEqual(response.headers["accept-ranges"], "bytes")
            self.assertTrue(
                response.headers["content-disposition"].startswith("inline;")
            )

            sent = []
            scope = {
                "type": "http",
                "method": "GET",
                "path": request.url.path,
                "headers": [(b"range", b"bytes=4-11")],
            }

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)

            await response(scope, receive, send)
            response_start = next(
                message for message in sent if message["type"] == "http.response.start"
            )
            response_body = b"".join(
                message["body"]
                for message in sent
                if message["type"] == "http.response.body"
            )
            response_headers = dict(response_start["headers"])
            self.assertEqual(response_start["status"], 206)
            self.assertEqual(response_headers[b"content-range"], b"bytes 4-11/16")
            self.assertEqual(response_body, video_bytes[4:12])

    async def test_episode_video_route_hides_private_shows(self) -> None:
        episode_id = uuid.uuid4()
        episode = SimpleNamespace(id=episode_id, season_id=uuid.uuid4())
        season = SimpleNamespace(show_id=uuid.uuid4(), season_number=1)

        class Session:
            async def get(self, model, identity):
                if model is Episode:
                    return episode
                if model is Seasons:
                    return season
                return SimpleNamespace(is_private=True)

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/api/v1/media/episodes/{episode_id}/video",
                "headers": [],
                "query_string": b"",
            }
        )
        with self.assertRaises(HTTPException) as raised:
            await get_episode_video(
                episode_id,
                request,
                playback_token=None,
                db=Session(),
            )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_owner_can_get_scoped_private_episode_playback_url(self) -> None:
        owner_id = uuid.uuid4()
        episode_id = uuid.uuid4()
        owner = SimpleNamespace(id=owner_id, email="private-owner@example.com")
        show = SimpleNamespace(id=uuid.uuid4(), created_by_id=owner_id)
        season = SimpleNamespace(show_id=show.id)
        episode = SimpleNamespace(season_id=uuid.uuid4())

        class Session:
            async def get(self, model, identity):
                if model is Episode:
                    return episode
                if model is Seasons:
                    return season
                return show

        result = await create_my_episode_playback(
            episode_id,
            Response(),
            Session(),
            owner,
        )
        playback_url = result["playback_url"]
        self.assertIn(f"/media/episodes/{episode_id}/video?", playback_url)
        playback_token = parse_qs(urlparse(playback_url).query)["playback_token"][0]
        payload = jwt.decode(
            playback_token,
            get_settings().SECRET_KEY,
            algorithms=[get_settings().ALGORITHM],
        )
        self.assertEqual(payload["sub"], owner.email)
        self.assertEqual(payload["purpose"], "episode-playback")
        self.assertEqual(payload["episode_id"], str(episode_id))

    async def test_private_episode_video_accepts_owner_playback_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = StorageManager(
                Path(directory) / "storage",
                minimum_free_bytes=0,
                reconciliation_interval_seconds=None,
            )
            self.addCleanup(storage.close)
            owner_id = uuid.uuid4()
            episode_id = uuid.uuid4()
            season_id = uuid.uuid4()
            show_id = uuid.uuid4()
            owner = SimpleNamespace(id=owner_id, email="private-owner@example.com")
            episode = SimpleNamespace(id=episode_id, season_id=season_id)
            season = SimpleNamespace(
                id=season_id,
                show_id=show_id,
                season_number=1,
            )
            show = SimpleNamespace(is_private=True, created_by_id=owner_id)
            video_bytes = (16).to_bytes(4, "big") + b"ftypisom" + b"\x00" * 4
            stored = await _replace_stored_upload(
                storage,
                MemoryUpload(video_bytes, "episode.mp4"),
                f"{show_id}/season-1/episode-{episode_id}",
                "video.mp4",
            )
            token = create_access_token(
                {
                    "sub": owner.email,
                    "purpose": "episode-playback",
                    "episode_id": str(episode_id),
                },
                expires_delta=timedelta(hours=12),
            )

            class Result:
                def scalar_one_or_none(self):
                    return owner

            class Session:
                async def get(self, model, identity):
                    if model is Episode:
                        return episode
                    if model is Seasons:
                        return season
                    return show

                async def execute(self, statement):
                    return Result()

            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": f"/api/v1/media/episodes/{episode_id}/video",
                    "headers": [],
                    "query_string": b"",
                    "app": SimpleNamespace(
                        state=SimpleNamespace(storage=storage)
                    ),
                }
            )
            response = await get_episode_video(
                episode_id,
                request,
                playback_token=token,
                db=Session(),
            )
            self.assertEqual(Path(response.path), stored.path)

    async def test_replacing_upload_removes_the_previous_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = StorageManager(
                Path(directory) / "storage",
                minimum_free_bytes=0,
                reconciliation_interval_seconds=None,
            )
            self.addCleanup(manager.close)
            thumbnail_dir = f"{uuid.uuid4()}/thumbnail"
            png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\xaeB`\x82"

            first = await _replace_stored_upload(
                manager,
                MemoryUpload(png, "first.png"),
                thumbnail_dir,
                "cover.jpg",
            )
            replacement = await _replace_stored_upload(
                manager,
                MemoryUpload(png, "replacement.png"),
                thumbnail_dir,
                "cover.jpg",
            )

            entries = await manager.async_list_entries()
            thumbnail_files = [
                entry
                for entry in entries
                if entry.relative_path.startswith(f"{thumbnail_dir}/")
                and not entry.is_directory
            ]
            storage_info = await manager.async_get_storage(replacement.storage_id)
            self.assertEqual(len(thumbnail_files), 1)
            self.assertEqual(
                thumbnail_files[0].relative_path,
                replacement.path.relative_to(storage_info.path).as_posix(),
            )
            self.assertFalse(first.path.exists())


if __name__ == "__main__":
    unittest.main()
