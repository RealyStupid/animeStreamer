"""
    API route for controlling the creation and management of shows and media.
"""
import mimetypes
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from jose import JWTError, jwt
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.config import get_settings
from core.security import create_access_token, get_current_user
from core.storage import AsyncReadable, StorageManager, StoredObject
from core.video import (
    StoredVideoUpload,
    VideoTranscoderUnavailable,
    VideoTranscodingError,
    browser_compatible_video,
)
from models import Shows, Seasons, Episode, GenreEnum, RoleEnum, Users
from schemas import (
    EpisodePlaybackResponse,
    EpisodeResponse,
    SeasonResponse,
    ShowResponse,
)


media = APIRouter(prefix="/media", tags=["Media"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")


async def _owned_show(
    show_id: uuid.UUID,
    current_user: Users,
    db: AsyncSession,
) -> Shows:
    show = await db.get(Shows, show_id)
    if show is None or show.created_by_id != current_user.id:
        raise _not_found()
    return show


async def _owned_season(
    season_id: uuid.UUID,
    current_user: Users,
    db: AsyncSession,
) -> Seasons:
    season = await db.get(Seasons, season_id)
    if season is None:
        raise _not_found()
    await _owned_show(season.show_id, current_user, db)
    return season


async def _owned_episode(
    episode_id: uuid.UUID,
    current_user: Users,
    db: AsyncSession,
) -> Episode:
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise _not_found()
    await _owned_season(episode.season_id, current_user, db)
    return episode


async def _thumbnail_response(
    request: Request,
    directory: str,
) -> FileResponse:
    storage_manager: StorageManager = request.app.state.storage
    entries = await storage_manager.async_list_entries()
    match = next(
        (
            entry
            for entry in entries
            if entry.relative_path.startswith(f"{directory}/")
            and not entry.is_directory
        ),
        None,
    )
    if match is None:
        raise _not_found()

    storage_info = await storage_manager.async_get_storage(match.storage_id)
    file_path = storage_info.path / match.relative_path
    if not file_path.exists():
        raise _not_found()
    return FileResponse(path=file_path)


async def _episode_video_path(
    request: Request,
    episode: Episode,
    season: Seasons,
) -> Path:
    storage_manager: StorageManager = request.app.state.storage
    storage_id = storage_manager.default_storage_id
    directory = (
        f"{season.show_id}/season-{season.season_number}/episode-{episode.id}"
    )
    entries = await storage_manager.async_list_entries(storage_id=storage_id)
    match = next(
        (
            entry
            for entry in entries
            if entry.relative_path.startswith(f"{directory}/")
            and not entry.is_directory
        ),
        None,
    )
    if match is None:
        raise _not_found()

    storage_info = await storage_manager.async_get_storage(storage_id)
    file_path = storage_info.path / match.relative_path
    if not file_path.is_file():
        raise _not_found()
    return file_path


async def _episode_video_response(
    request: Request,
    episode: Episode,
    season: Seasons,
) -> FileResponse:
    file_path = await _episode_video_path(request, episode, season)
    return FileResponse(
        path=file_path,
        media_type=mimetypes.guess_type(file_path.name)[0],
        filename=file_path.name,
        content_disposition_type="inline",
    )


async def _replace_stored_upload(
    storage_manager: StorageManager,
    upload: AsyncReadable,
    directory: str,
    fallback_filename: str,
) -> StoredObject:
    storage_id = storage_manager.default_storage_id
    await storage_manager.async_add_directory(directory, storage_id=storage_id)
    filename = getattr(upload, "filename", None)
    stored = await storage_manager.save_upload(
        upload=upload,
        filename=(
            filename
            if isinstance(filename, str) and filename
            else fallback_filename
        ),
        directory=directory,
        storage_id=storage_id,
    )
    storage_info = await storage_manager.async_get_storage(storage_id)
    new_path = stored.path.relative_to(storage_info.path).as_posix()
    entries = await storage_manager.async_list_entries(storage_id=storage_id)
    for entry in entries:
        if (
            entry.relative_path.startswith(f"{directory}/")
            and not entry.is_directory
            and entry.relative_path != new_path
        ):
            await storage_manager.async_remove(
                entry.relative_path,
                storage_id=storage_id,
                recursive=False,
            )
    return stored


async def _store_browser_compatible_episode(
    storage_manager: StorageManager,
    upload: AsyncReadable,
    directory: str,
    max_input_bytes: int | None = None,
) -> StoredObject:
    storage_id = storage_manager.default_storage_id
    storage_info = await storage_manager.async_get_storage(storage_id)
    async with browser_compatible_video(
        upload,
        max_input_bytes=(
            storage_info.available_bytes
            if max_input_bytes is None
            else max_input_bytes
        ),
    ) as converted:
        return await _replace_stored_upload(
            storage_manager,
            upload=converted,
            directory=directory,
            fallback_filename="episode.mp4",
        )


async def _remove_media_directory(
    storage_manager: StorageManager,
    directory: str,
) -> None:
    for storage_info in await storage_manager.async_list_storages():
        entries = await storage_manager.async_list_entries(
            storage_id=storage_info.storage_id,
        )
        if any(
            entry.relative_path == directory and entry.is_directory
            for entry in entries
        ):
            await storage_manager.async_remove(
                directory,
                storage_id=storage_info.storage_id,
                recursive=True,
            )


# --- creating shows ---
@media.post("/shows", response_model=ShowResponse, status_code=status.HTTP_201_CREATED)
async def create_show(
    request: Request,
    title: str = Form(...),
    description: str = Form("No description provided"),
    genre: GenreEnum = Form(GenreEnum.DRAMA),
    is_private: bool = Form(False),
    thumbnail: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """Create a new show; requires a signed-in user."""
    storage_manager = request.app.state.storage
    
    # Generate the Show UUID upfront so we own the folder path structure
    show_id = uuid.uuid4()
    thumbnail_url_str = None

    #  If a thumbnail is provided, provision the UUID folder and save it securely
    if thumbnail:
        try:
            thumbnail_dir = f"{show_id}/thumbnail"
            
            # Create the directory and its index entry via storage manager
            await storage_manager.async_add_directory(thumbnail_dir)
            
            # Stream and validate the upload into the show's unique folder[cite: 9]
            stored_obj = await storage_manager.save_upload(
                upload=thumbnail,
                filename=thumbnail.filename or "cover.jpg",
                directory=thumbnail_dir
            )
            
            # Construct an API endpoint URL to serve this specific file later
            thumbnail_url_str = f"/api/v1/media/shows/{show_id}/thumbnail"
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to process show thumbnail: {str(e)}"
            )

    # Save the show record into PostgreSQL using the pre-generated UUID[cite: 10]
    new_show = Shows(
        id=show_id,
        title=title,
        description=description,
        genre=genre,
        thumbnail_url=thumbnail_url_str,
        is_private=is_private,
        created_by=current_user,
    )
    
    db.add(new_show)
    await db.commit()
    await db.refresh(new_show)
    new_show.created_by = current_user

    return new_show

@media.get("/shows/list", response_model=list[ShowResponse])
async def list_shows(db: AsyncSession = Depends(get_db)):
    """Returns a list of all registered shows in the database."""
    result = await db.execute(
        select(Shows)
        .where(Shows.is_private.is_(False))
        .options(selectinload(Shows.created_by))
    )
    shows = result.scalars().all()
    return shows

@media.get("/shows/title/{title}", response_model=ShowResponse)
async def get_show_by_title(title: str, db: AsyncSession = Depends(get_db)):
    """Finds and returns a specific show by its exact title."""
    # Using case-insensitive matching or exact match. Let's do exact/insensitive match:
    result = await db.execute(
        select(Shows)
        .where(
            func.lower(Shows.title) == title.lower(),
            Shows.is_private.is_(False),
        )
        .options(selectinload(Shows.created_by))
    )
    show = result.scalar_one_or_none()
    
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
        
    return show

# admin only for deletion
@media.delete("/shows/{show_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_show(
    show_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
) -> None:
    """Delete a show and its indexed local-storage directory; admins only."""
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete shows.",
        )

    show = await db.get(Shows, show_id)
    if show is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show not found.",
        )

    try:
        await _remove_media_directory(
            request.app.state.storage,
            str(show_id),
        )
        await db.execute(delete(Shows).where(Shows.id == show_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@media.delete("/my/shows/{show_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_show(
    show_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
) -> None:
    await _owned_show(show_id, current_user, db)
    try:
        await _remove_media_directory(request.app.state.storage, str(show_id))
        await db.execute(delete(Shows).where(Shows.id == show_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@media.get("/shows/{show_id}/thumbnail")
async def get_show_thumbnail(request: Request, show_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    show = await db.get(Shows, show_id)
    if show is None or show.is_private or not show.thumbnail_url:
        raise _not_found()
    return await _thumbnail_response(request, f"{show_id}/thumbnail")


@media.get("/my/shows", response_model=list[ShowResponse])
async def list_my_shows(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    result = await db.execute(
        select(Shows)
        .where(Shows.created_by_id == current_user.id)
        .options(selectinload(Shows.created_by))
        .order_by(Shows.created_at.desc())
    )
    return result.scalars().all()


@media.get("/my/shows/{show_id}", response_model=ShowResponse)
async def get_my_show(
    show_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    show = await _owned_show(show_id, current_user, db)
    show.created_by = current_user
    return show


@media.patch("/my/shows/{show_id}", response_model=ShowResponse)
async def update_my_show(
    show_id: uuid.UUID,
    request: Request,
    title: str | None = Form(None),
    description: str | None = Form(None),
    genre: GenreEnum | None = Form(None),
    is_private: bool | None = Form(None),
    thumbnail: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    show = await _owned_show(show_id, current_user, db)
    if title is not None:
        show.title = title
    if description is not None:
        show.description = description
    if genre is not None:
        show.genre = genre
    if is_private is not None:
        show.is_private = is_private
    if thumbnail is not None:
        directory = f"{show_id}/thumbnail"
        await _replace_stored_upload(
            request.app.state.storage,
            upload=thumbnail,
            directory=directory,
            fallback_filename="cover.jpg",
        )
        show.thumbnail_url = f"/api/v1/media/shows/{show_id}/thumbnail"
    show.created_by = current_user
    await db.commit()
    await db.refresh(show)
    return show


@media.get("/my/shows/{show_id}/thumbnail")
async def get_my_show_thumbnail(
    show_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    show = await _owned_show(show_id, current_user, db)
    if not show.thumbnail_url:
        raise _not_found()
    return await _thumbnail_response(request, f"{show_id}/thumbnail")


# --- Seasons ---
@media.post("/shows/{show_id}/seasons", response_model=SeasonResponse, status_code=status.HTTP_201_CREATED)
async def create_season(
    show_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: str = Form("No description provided"),
    thumbnail: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """Create a new season for a specific show; requires a signed-in user."""
    show = await _owned_show(show_id, current_user, db)
    await db.scalar(
        select(Shows).where(Shows.id == show.id).with_for_update()
    )
    last_season_number = await db.scalar(
        select(func.max(Seasons.season_number)).where(Seasons.show_id == show_id)
    )
    season_number = (last_season_number or 0) + 1
    season_id = uuid.uuid4()

    storage_manager: StorageManager = request.app.state.storage
    season_dir = f"{show_id}/season-{season_number}"
    thumbnail_url = (
        f"/api/v1/media/seasons/{season_id}/thumbnail"
        if thumbnail is not None
        else None
    )
    try:
        await storage_manager.async_add_directory(season_dir)
        if thumbnail is not None:
            await _replace_stored_upload(
                storage_manager,
                upload=thumbnail,
                directory=f"{season_dir}/thumbnail",
                fallback_filename="cover.jpg",
            )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create season storage: {error}",
        ) from error

    new_season = Seasons(
        id=season_id,
        show_id=show_id,
        season_number=season_number,
        name=name,
        description=description,
        thumbnail_url=thumbnail_url,
        created_by=current_user,
    )
    db.add(new_season)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A season was added at the same time. Please try again.",
        ) from error
    await db.refresh(new_season)
    new_season.created_by = current_user

    return new_season

@media.get("/shows/{show_id}/seasons", response_model=list[SeasonResponse])
async def list_show_seasons(show_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all seasons for a specific show."""
    show = await db.get(Shows, show_id)
    if show is None or show.is_private:
        raise _not_found()

    result = await db.execute(
        select(Seasons)
        .where(Seasons.show_id == show_id)
        .options(selectinload(Seasons.created_by))
        .order_by(Seasons.season_number.asc())
    )
    return result.scalars().all()


@media.get("/my/shows/{show_id}/seasons", response_model=list[SeasonResponse])
async def list_my_show_seasons(
    show_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    await _owned_show(show_id, current_user, db)
    result = await db.execute(
        select(Seasons)
        .where(Seasons.show_id == show_id)
        .options(selectinload(Seasons.created_by))
        .order_by(Seasons.season_number.asc())
    )
    return result.scalars().all()


@media.patch("/my/seasons/{season_id}", response_model=SeasonResponse)
async def update_my_season(
    season_id: uuid.UUID,
    request: Request,
    name: str | None = Form(None),
    description: str | None = Form(None),
    thumbnail: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    season = await _owned_season(season_id, current_user, db)
    if name is not None:
        season.name = name
    if description is not None:
        season.description = description
    if thumbnail is not None:
        directory = f"{season.show_id}/season-{season.season_number}/thumbnail"
        await _replace_stored_upload(
            request.app.state.storage,
            upload=thumbnail,
            directory=directory,
            fallback_filename="cover.jpg",
        )
        season.thumbnail_url = (
            f"/api/v1/media/seasons/{season_id}/thumbnail"
        )
    season.created_by = current_user
    await db.commit()
    await db.refresh(season)
    season.created_by = current_user
    return season


@media.delete("/my/seasons/{season_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_season(
    season_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
) -> None:
    season = await _owned_season(season_id, current_user, db)
    season_directory = (
        f"{season.show_id}/season-{season.season_number}"
    )
    try:
        await _remove_media_directory(
            request.app.state.storage,
            season_directory,
        )
        await db.execute(delete(Seasons).where(Seasons.id == season_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@media.get("/seasons/{season_id}/thumbnail")
async def get_season_thumbnail(
    season_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    season = await db.get(Seasons, season_id)
    if season is None:
        raise _not_found()
    show = await db.get(Shows, season.show_id)
    if show is None or show.is_private or not season.thumbnail_url:
        raise _not_found()
    return await _thumbnail_response(
        request,
        f"{season.show_id}/season-{season.season_number}/thumbnail",
    )


@media.get("/my/seasons/{season_id}/thumbnail")
async def get_my_season_thumbnail(
    season_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    season = await _owned_season(season_id, current_user, db)
    if not season.thumbnail_url:
        raise _not_found()
    return await _thumbnail_response(
        request,
        f"{season.show_id}/season-{season.season_number}/thumbnail",
    )


# --- Episode ---
@media.post("/seasons/{season_id}/episodes", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode(
    season_id: uuid.UUID,
    request: Request,
    title: str = Form(...),
    episode_number: int = Form(...),
    description: str = Form("No description provided"),
    duration_secs: int | None = Form(None),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """Upload a video file and create a new episode for a season; requires a signed-in user."""

    # Verify the season exists and load its show relationship to get the show_id
    season = await _owned_season(season_id, current_user, db)

    # Check if this episode number already exists in the season
    existing_episode = await db.execute(
        select(Episode).where(
            Episode.season_id == season_id,
            Episode.episode_number == episode_number
        )
    )
    if existing_episode.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode {episode_number} already exists in this season."
        )

    episode_id = uuid.uuid4()
    storage_manager: StorageManager = request.app.state.storage
    episode_dir = (
        f"{season.show_id}/season-{season.season_number}/episode-{episode_id}"
    )

    try:
        await _store_browser_compatible_episode(
            storage_manager,
            upload=video,
            directory=episode_dir,
        )
    except VideoTranscoderUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except VideoTranscodingError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process video upload: {str(e)}"
        )

    # Construct API endpoint URL to stream/serve this episode later
    video_url_str = f"/api/v1/media/episodes/{episode_id}/video"

    # Save episode record into database
    new_episode = Episode(
        id=episode_id,
        season_id=season_id,
        episode_number=episode_number,
        title=title,
        description=description,
        video_url=video_url_str,
        duration_secs=duration_secs,
        created_by=current_user,
    )

    db.add(new_episode)
    await db.commit()
    await db.refresh(new_episode)
    new_episode.created_by = current_user

    return new_episode


@media.get(
    "/seasons/{season_id}/episodes",
    response_model=list[EpisodeResponse],
)
async def list_season_episodes(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List episodes in a season in playback order."""
    season = await db.get(Seasons, season_id)
    if season is None:
        raise _not_found()
    show = await db.get(Shows, season.show_id)
    if show is None or show.is_private:
        raise _not_found()

    result = await db.execute(
        select(Episode)
        .where(Episode.season_id == season_id)
        .options(selectinload(Episode.created_by))
        .order_by(Episode.episode_number.asc())
    )
    return result.scalars().all()


@media.get(
    "/my/seasons/{season_id}/episodes",
    response_model=list[EpisodeResponse],
)
async def list_my_season_episodes(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    await _owned_season(season_id, current_user, db)
    result = await db.execute(
        select(Episode)
        .where(Episode.season_id == season_id)
        .options(selectinload(Episode.created_by))
        .order_by(Episode.episode_number.asc())
    )
    return result.scalars().all()


@media.get("/episodes/{episode_id}/video")
async def get_episode_video(
    episode_id: uuid.UUID,
    request: Request,
    playback_token: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise _not_found()
    season = await db.get(Seasons, episode.season_id)
    if season is None:
        raise _not_found()
    show = await db.get(Shows, season.show_id)
    if show is None:
        raise _not_found()
    if show.is_private:
        if playback_token is None:
            raise _not_found()
        settings = get_settings()
        try:
            token_payload = jwt.decode(
                playback_token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
        except JWTError:
            raise _not_found() from None
        if (
            token_payload.get("purpose") != "episode-playback"
            or token_payload.get("episode_id") != str(episode_id)
        ):
            raise _not_found()
        owner_result = await db.execute(
            select(Users).where(Users.email == token_payload.get("sub"))
        )
        owner = owner_result.scalar_one_or_none()
        if owner is None or show.created_by_id != owner.id:
            raise _not_found()
    return await _episode_video_response(request, episode, season)


@media.post(
    "/my/episodes/{episode_id}/playback",
    response_model=EpisodePlaybackResponse,
)
async def create_my_episode_playback(
    episode_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    await _owned_episode(episode_id, current_user, db)
    playback_token = create_access_token(
        {
            "sub": current_user.email,
            "purpose": "episode-playback",
            "episode_id": str(episode_id),
        },
        expires_delta=timedelta(hours=12),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "playback_url": (
            f"/api/v1/media/episodes/{episode_id}/video?"
            f"{urlencode({'playback_token': playback_token})}"
        )
    }


@media.post(
    "/my/episodes/{episode_id}/transcode",
    response_model=EpisodeResponse,
)
async def transcode_my_episode(
    episode_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    episode = await _owned_episode(episode_id, current_user, db)
    season = await db.get(Seasons, episode.season_id)
    if season is None:
        raise _not_found()

    storage_manager: StorageManager = request.app.state.storage
    source_path = await _episode_video_path(request, episode, season)
    source = StoredVideoUpload(source_path)
    try:
        storage_info = await storage_manager.async_get_storage(
            storage_manager.default_storage_id
        )
        await _store_browser_compatible_episode(
            storage_manager,
            upload=source,
            directory=(
                f"{season.show_id}/season-{season.season_number}"
                f"/episode-{episode.id}"
            ),
            max_input_bytes=storage_info.available_bytes + source.size,
        )
    except VideoTranscoderUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except VideoTranscodingError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    finally:
        source.close()

    episode.created_by = current_user
    return episode


@media.delete("/my/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_episode(
    episode_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
) -> None:
    episode = await _owned_episode(episode_id, current_user, db)
    season = await db.get(Seasons, episode.season_id)
    if season is None:
        raise _not_found()
    episode_directory = (
        f"{season.show_id}/season-{season.season_number}"
        f"/episode-{episode.id}"
    )
    try:
        await _remove_media_directory(
            request.app.state.storage,
            episode_directory,
        )
        await db.execute(delete(Episode).where(Episode.id == episode_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@media.get("/my/episodes/{episode_id}/video")
async def get_my_episode_video(
    episode_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    episode = await _owned_episode(episode_id, current_user, db)
    season = await db.get(Seasons, episode.season_id)
    if season is None:
        raise _not_found()
    return await _episode_video_response(request, episode, season)


@media.patch("/my/episodes/{episode_id}", response_model=EpisodeResponse)
async def update_my_episode(
    episode_id: uuid.UUID,
    request: Request,
    title: str | None = Form(None),
    description: str | None = Form(None),
    duration_secs: int | None = Form(None),
    video: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    episode = await _owned_episode(episode_id, current_user, db)
    if title is not None:
        episode.title = title
    if description is not None:
        episode.description = description
    if duration_secs is not None:
        episode.duration_secs = duration_secs
    if video is not None:
        season = await db.get(Seasons, episode.season_id)
        if season is None:
            raise _not_found()
        try:
            await _store_browser_compatible_episode(
                request.app.state.storage,
                upload=video,
                directory=(
                    f"{season.show_id}/season-{season.season_number}"
                    f"/episode-{episode.id}"
                ),
            )
        except VideoTranscoderUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        except VideoTranscodingError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
    episode.created_by = current_user
    await db.commit()
    await db.refresh(episode)
    episode.created_by = current_user
    return episode
