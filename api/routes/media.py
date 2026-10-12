"""
    API route for controlling the creation and management of shows and media.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func

from core.database import get_db
from core.security import get_current_user
from core.storage import StorageManager


from models import Shows, GenreEnum, RoleEnum, Users


from schemas import ShowResponse


import uuid


media = APIRouter(prefix="/media", tags=["Media"])

@media.post("/shows", response_model=ShowResponse, status_code=status.HTTP_201_CREATED)
async def create_show(
    request: Request,
    title: str = Form(...),
    description: str = Form("No description provided"),
    genre: GenreEnum = Form(GenreEnum.DRAMA),
    thumbnail: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db)
):
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
        thumbnail_url=thumbnail_url_str
    )
    
    db.add(new_show)
    await db.commit()
    await db.refresh(new_show)

    return new_show

@media.get("/shows/list", response_model=list[ShowResponse])
async def list_shows(db: AsyncSession = Depends(get_db)):
    """Returns a list of all registered shows in the database."""
    result = await db.execute(select(Shows))
    shows = result.scalars().all()
    return shows


@media.get("/shows/title/{title}", response_model=ShowResponse)
async def get_show_by_title(title: str, db: AsyncSession = Depends(get_db)):
    """Finds and returns a specific show by its exact title."""
    # Using case-insensitive matching or exact match. Let's do exact/insensitive match:
    result = await db.execute(select(Shows).where(func.lower(Shows.title) == title.lower()))
    show = result.scalar_one_or_none()
    
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
        
    return show

@media.delete(
    "/shows/{show_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
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

    storage_manager: StorageManager = request.app.state.storage
    show_directory = str(show_id)

    try:
        storages = await storage_manager.async_list_storages()
        for storage_info in storages:
            entries = await storage_manager.async_list_entries(
                storage_id=storage_info.storage_id,
                recursive=False,
                include_root=False,
            )
            if any(
                entry.relative_path == show_directory and entry.is_directory
                for entry in entries
            ):
                await storage_manager.async_remove(
                    show_directory,
                    storage_id=storage_info.storage_id,
                    recursive=True,
                )

        await db.execute(delete(Shows).where(Shows.id == show_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise

@media.get("/shows/{show_id}/thumbnail")
async def get_show_thumbnail(request: Request, show_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    storage_manager: StorageManager = request.app.state.storage

    # Verify the show exists in the database
    show = await db.get(Shows, show_id)
    if not show or not show.thumbnail_url:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    # Look up entries under this show's UUID directory via the storage index
    entries = await storage_manager.async_list_entries()
    match = next((e for e in entries if e.relative_path.startswith(f"{show_id}/thumbnail/") and not e.is_directory), None)

    if not match:
        raise HTTPException(status_code=404, detail="Thumbnail file missing from storage index")

    # Resolve the absolute path and serve it cleanly
    storage_info = await storage_manager.async_get_storage(match.storage_id)
    file_path = storage_info.path / match.relative_path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing from disk")

    return FileResponse(path=file_path)