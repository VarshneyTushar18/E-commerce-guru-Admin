from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import hash_password
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.routers import admin

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.admin_email).first():
            admin_user = User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                name="Admin",
            )
            db.add(admin_user)
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Ecomm Guru Blog Admin", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.state.templates = templates

static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(admin.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401 and request.url.path.startswith("/admin"):
        return RedirectResponse(url="/login", status_code=303)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def root():
    return RedirectResponse("/admin")
