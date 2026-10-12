import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from core.storage import StorageManager
from models import GenreEnum, RoleEnum, Shows, Users
from routes.auth import login, register
from routes.media import (
    create_show,
    delete_show,
    get_show_by_title,
    get_show_thumbnail,
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

            def add(self, instance):
                self.added = instance

            async def commit(self):
                self.committed = True

            async def refresh(self, instance):
                self.refreshed = True

            async def execute(self, statement):
                return Result()

        session = Session()
        storage = SimpleNamespace()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage=storage)))
        show = await create_show(
            request=request,
            title="Test Show",
            description="A show",
            genre=GenreEnum.ANIME,
            thumbnail=None,
            db=session,
        )
        self.assertIs(show, session.added)
        self.assertEqual(show.title, "Test Show")
        self.assertTrue(session.committed)
        self.assertTrue(session.refreshed)
        self.assertEqual(await list_shows(db=session), [show])

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


if __name__ == "__main__":
    unittest.main()
