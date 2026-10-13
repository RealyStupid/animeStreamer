# AnimeWatcher

AnimeWatcher is a full-stack media library and video streaming project built with a FastAPI backend and a Next.js frontend. The app is designed around a personal/local media collection: users can create and manage shows, organize seasons and episodes, upload media files, and browse a streaming interface that serves videos from the backend.

This repository is a working prototype and active development project, not a production-ready public streaming platform. The current implementation focuses on the core architecture: API-driven media management, secure user auth, local storage handling, and a modern frontend for browsing and viewing content.

## Project status

- Active prototype
- Backend: FastAPI + SQLAlchemy + PostgreSQL-ready config
- Frontend: Next.js 16 + React 19 + TypeScript
- Local-first media storage with indexed file management
- Authentication and user account flow in place
- Show/season/episode management and streaming endpoints implemented
- Frontend pages for landing, browse, login, register, profile, and viewing

## Why this project exists

The goal is to build a lightweight media app that feels like a personal anime/video library:

- keep metadata in a database
- store uploaded content safely on disk
- serve files through a backend so they can be streamed reliably
- provide a clean modern interface for catalog browsing and playback

This repository is intentionally structured around a frontend + backend split so the media system can evolve without coupling video storage, metadata, and UI logic together.

## Architecture overview

The project is split into two major app areas:

### Backend (`/api`)
The backend is a FastAPI service that handles:

- user registration and authentication
- JWT-based access control
- show, season, and episode CRUD APIs
- upload validation and media storage management
- browser-compatible video conversion/transcoding flow
- serving thumbnails and episode video files
- database connectivity and startup checks

### Frontend (`/site`)
The frontend is a Next.js application that provides:

- landing page and navigation
- registration/login UI
- creator dashboard for media management
- library browsing and genre search
- per-show season/episode layout
- video watch pages

## Stack

### Backend
- Python 3.14 (present in the repo virtual environment)
- FastAPI
- SQLAlchemy
- PostgreSQL-ready async database engine
- Pydantic + Pydantic Settings
- JWT auth via python-jose
- password hashing via pwdlib
- Alembic for migrations
- local filesystem storage manager with SQLite indexing

### Frontend
- Next.js 16
- React 19
- TypeScript
- Tailwind CSS via Next/PostCSS
- Client-side API layer for backend communication

## Features implemented

### Authentication and app security
- user sign-up and login endpoints
- JWT access token generation and validation
- current-user retrieval via secure dependency injection
- CORS configuration and HTTP security headers
- startup logging and request logging middleware

### Media model and database
The API defines a relational media model with:

- `Users`
- `Shows`
- `Seasons`
- `Episode`
- tag support for shows
- genre enum support and private/public show visibility

### Upload and storage management
- indexed local storage for uploaded videos and thumbnails
- directory provisioning and quota-aware management
- upload validation and file type checks
- random generated filenames for stored media
- storage diagnostics and reconciliation logic
- optional browser-compatible video conversion before serving

### Browsing and playback flow
- list public shows
- view show pages and seasons
- load episodes and playback URLs
- serve asset media through backend endpoints
- watch page flow for front-end playback rendering

### Frontend user experience
- home landing page
- login and registration screens
- profile page with signed-in creator dashboard
- library browsing/search by title and genre
- management workflow for created shows
- content cards and media thumbnails

## Repository layout

```text
animeStreamer/
├── README.md
├── .gitignore
├── .venv/                        # local Python environment
├── api/
│   ├── alembic/                  # migrations
│   ├── core/                    # config, db, logging, security, storage, startup checks
│   ├── docs/                    # project docs for major subsystems
│   ├── models/                  # SQLAlchemy models
│   ├── routes/                  # API route modules
│   ├── schemas/                 # Pydantic response/request schemas
│   ├── tests/                   # backend tests
│   ├── .env.example             # environment template
│   ├── .env                     # local env (ignored in git if present)
│   ├── main.py                  # FastAPI app entry point
│   ├── requirements.txt         # Python dependencies
│   └── .localDevStorage/        # local dev media storage
├── site/
│   ├── src/                     # Next.js app source
│   ├── public/                  # static assets
│   ├── package.json             # frontend dependencies/scripts
│   ├── .env.local               # frontend API base URL
│   ├── next.config.ts
│   └── ...
└── .git/
```

## Local development setup

### Prerequisites
- Python 3.12+ (the repo currently includes a Python 3.14 virtual environment)
- Node.js 20+
- PostgreSQL database available for the API (the app is configured for a PostgreSQL-style async URL)
- A terminal with shell support for running both services

### 1) Set up the backend

```bash
cd api
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then start the API:

```bash
cd api
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The app will expose:

- API root: `http://localhost:8000`
- Health check: `http://localhost:8000/api/health`
- Swagger docs: `http://localhost:8000/api/docs`

### 2) Set up the frontend

```bash
cd site
npm install
npm run dev
```

Then open:

- Frontend: `http://localhost:3000`

### Environment configuration

The backend uses `api/.env` values such as:

```dotenv
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/animewatcher
SECRET_KEY=insecure-dev-secret-change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALLOWED_ORIGINS=http://localhost:3000
ENVIRONMENT=development
DEBUG=true
```

The frontend expects an API URL in `site/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL="http://localhost:8000/"
```

## Typical workflow

1. Start PostgreSQL and ensure the configured database exists.
2. Run the API and confirm the health endpoint responds.
3. Start the Next.js app.
4. Create an account from the registration page.
5. Sign in to the profile dashboard.
6. Add shows, seasons, and episode uploads through the creator flow.
7. Browse the public library and open a watch page to play media.

## Important notes

- This project is designed for local development and personal media hosting, not a public SaaS deployment.
- Default secrets and credentials in the repo are intentionally development-friendly and should be replaced before production use.
- The storage system is intentionally local and managed by the backend; do not point it at a repository folder or a directory containing unrelated files.
- Alembic migrations are part of the backend architecture and should be used when modifying the database schema.

## Potential next steps

The current roadmap for the project is aligned with the architecture already in place:

- complete media CRUD polish and validation
- expand frontend detail pages for seasons and episodes
- improve watch-page UX and playback features
- harden auth and production configuration
- add deployment and hosting guidance for real environments
- continue refining storage/transcoding workflow for larger media collections

## Project philosophy

AnimeWatcher aims to be a clean, modern media app with a clear separation between:

- metadata and user data
- media storage and upload handling
- backend APIs and frontend presentation
- personal/local-first hosting and user management

That structure makes the project a useful base for continuing work on streaming, library management, and self-hosted entertainment tooling.

## License

This project does not currently declare a license file or explicit project license in the repository. If you are planning to distribute or reuse it publicly, add a license before doing so.
