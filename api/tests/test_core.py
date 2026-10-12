import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jose import jwt
from fastapi import HTTPException

import core.security as security
from core.config import Settings, get_settings
from core.database import Base, get_db
from core.logging import LoggingConfig, configure_logging
from core.startup_checks import run_development_tests
from models import Episode, Seasons, Shows, Tags, Users
from schemas import ShowCreate, ShowResponse, TagResponse


class CoreTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_parse_allowed_origins(self) -> None:
        self.assertEqual(
            Settings(ALLOWED_ORIGINS="https://one.example, https://two.example")
            .allowed_origins_list,
            ["https://one.example", "https://two.example"],
        )
        self.assertEqual(
            Settings(
                ALLOWED_ORIGINS='["https://one.example","https://two.example"]'
            ).allowed_origins_list,
            ["https://one.example", "https://two.example"],
        )
        self.assertEqual(
            Settings(ALLOWED_ORIGINS="").allowed_origins_list,
            ["http://localhost:3000"],
        )

    def test_settings_are_cached_and_can_be_reloaded(self) -> None:
        get_settings.cache_clear()
        try:
            with patch.dict("os.environ", {"APP_NAME": "Test API"}):
                first = get_settings()
                self.assertEqual(first.APP_NAME, "Test API")
                self.assertIs(get_settings(), first)
            with patch.dict("os.environ", {"APP_NAME": "Reloaded API"}):
                get_settings.cache_clear()
                self.assertEqual(get_settings().APP_NAME, "Reloaded API")
        finally:
            get_settings.cache_clear()

    def test_logging_writes_to_configured_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger_name = "test.api.logging"
            logger = configure_logging(
                LoggingConfig(
                    name=logger_name,
                    directory=directory,
                    filename="nested/test.log",
                    level="DEBUG",
                    file_level="DEBUG",
                    console=False,
                    rotation_type="none",
                )
            )
            logger.info("startup-test-message")
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()
            contents = (Path(directory) / "nested" / "test.log").read_text(
                encoding="utf-8"
            )
            self.assertIn("startup-test-message", contents)

    def test_password_hashing_and_token_round_trip(self) -> None:
        password_hash = security.hash_password("test-password")
        self.assertNotEqual(password_hash, "test-password")
        self.assertTrue(security.verify_password("test-password", password_hash))
        self.assertFalse(security.verify_password("wrong-password", password_hash))

        test_settings = SimpleNamespace(
            SECRET_KEY="startup-test-secret",
            ALGORITHM="HS256",
            ACCESS_TOKEN_EXPIRE_MINUTES=5,
        )
        with patch.object(security, "settings", test_settings):
            token = security.create_access_token({"sub": "test@example.com"})
        payload = jwt.decode(token, test_settings.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(payload["sub"], "test@example.com")
        self.assertIn("exp", payload)

    async def test_current_user_lookup_and_invalid_token(self) -> None:
        user = Users(
            handle="tester",
            email="tester@example.com",
            password_hashed="not-used",
        )

        class Result:
            def scalar_one_or_none(self):
                return user

        class Session:
            async def execute(self, statement):
                return Result()

        test_settings = SimpleNamespace(
            SECRET_KEY="startup-test-secret",
            ALGORITHM="HS256",
            ACCESS_TOKEN_EXPIRE_MINUTES=5,
        )
        with patch.object(security, "settings", test_settings):
            token = security.create_access_token({"sub": user.email})
            resolved = await security.get_current_user(token=token, db=Session())
            self.assertIs(resolved, user)

            with self.assertRaises(HTTPException) as raised:
                await security.get_current_user(token="not-a-token", db=Session())
        self.assertEqual(raised.exception.status_code, 401)

    async def test_database_dependency_commits_and_rolls_back(self) -> None:
        class Session:
            def __init__(self):
                self.commits = 0
                self.rollbacks = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def commit(self):
                self.commits += 1

            async def rollback(self):
                self.rollbacks += 1

        session = Session()

        class SessionFactory:
            def __call__(self):
                return session

        with patch("core.database.AsyncSessionLocal", SessionFactory()):
            generator = get_db()
            self.assertIs(await anext(generator), session)
            with self.assertRaises(StopAsyncIteration):
                await anext(generator)
            self.assertEqual(session.commits, 1)

            generator = get_db()
            self.assertIs(await anext(generator), session)
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                await generator.athrow(RuntimeError("request failed"))
            self.assertEqual(session.rollbacks, 1)

    def test_orm_models_register_expected_tables(self) -> None:
        self.assertEqual(
            {"users", "shows", "tags", "show_tags", "seasons", "episodes"}
            - set(Base.metadata.tables),
            set(),
        )
        self.assertIn("tags", Shows.__mapper__.relationships)
        self.assertIn("shows", Tags.__mapper__.relationships)
        self.assertTrue(issubclass(Users, Base))
        self.assertTrue(issubclass(Seasons, Base))
        self.assertTrue(issubclass(Episode, Base))

    def test_show_schemas_accept_and_serialize_tags(self) -> None:
        created = ShowCreate(
            title="Schema Test",
            tags=["Action", "Sci-Fi"],
        )
        self.assertEqual(created.tags, ["Action", "Sci-Fi"])

        tag_id = uuid.uuid4()
        response = ShowResponse.model_validate(
            SimpleNamespace(
                id=uuid.uuid4(),
                title="Schema Test",
                description="Example",
                genre="anime",
                thumbnail_url=None,
                tags=[SimpleNamespace(id=tag_id, name="Action")],
            )
        )
        self.assertEqual(response.tags, [TagResponse(id=tag_id, name="Action")])

    def test_startup_test_runner_fails_closed_on_failed_suite(self) -> None:
        result = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="FAILED (failures=1)",
        )
        with patch("core.startup_checks.subprocess.run", return_value=result) as run:
            with self.assertRaisesRegex(RuntimeError, "refusing to start"):
                run_development_tests()
        self.assertEqual(run.call_args.kwargs["capture_output"], True)
        self.assertEqual(run.call_args.kwargs["text"], True)

    def test_startup_test_runner_accepts_passing_suite(self) -> None:
        result = SimpleNamespace(returncode=0, stdout="", stderr="Ran 1 test")
        with patch("core.startup_checks.subprocess.run", return_value=result):
            run_development_tests()


if __name__ == "__main__":
    unittest.main()
