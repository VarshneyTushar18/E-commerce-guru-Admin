from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import asyncio
import re

from app.auth import create_session_token, decode_session_token, hash_password, verify_password
from app.database import SessionLocal, get_db
from app.models import AIJob, AIJobStatus, Blog, BlogStatus, TopicSuggestion, User
from app.services.ai_agent import agent
from app.services.wordpress import publisher

router = APIRouter()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get("session")
    if not token:
        return None
    user_id = decode_session_token(token)
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return request.app.state.templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid email or password"}
        )
    token = create_session_token(user.id)
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=86400 * 7, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    stats = {
        "total": db.query(Blog).count(),
        "drafts": db.query(Blog).filter(Blog.status == BlogStatus.DRAFT).count(),
        "review": db.query(Blog).filter(Blog.status == BlogStatus.REVIEW).count(),
        "published": db.query(Blog).filter(Blog.status == BlogStatus.PUBLISHED).count(),
        "ai_jobs": db.query(AIJob).filter(AIJob.status.notin_([AIJobStatus.COMPLETED, AIJobStatus.FAILED])).count(),
    }
    recent = db.query(Blog).order_by(Blog.created_at.desc()).limit(5).all()
    return request.app.state.templates.TemplateResponse(
        "admin/dashboard.html", {"request": request, "user": user, "stats": stats, "recent": recent}
    )


@router.get("/admin/blogs", response_class=HTMLResponse)
async def blogs_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    status_filter = request.query_params.get("status", "")
    q = db.query(Blog).order_by(Blog.created_at.desc())
    if status_filter:
        q = q.filter(Blog.status == status_filter)
    blogs = q.all()
    return request.app.state.templates.TemplateResponse(
        "admin/blogs.html",
        {
            "request": request,
            "user": user,
            "blogs": blogs,
            "status_filter": status_filter,
            "synced": request.query_params.get("synced"),
            "sync_created": request.query_params.get("created"),
            "sync_updated": request.query_params.get("updated"),
            "sync_error": request.query_params.get("sync_error"),
        },
    )


@router.post("/admin/blogs/sync")
async def sync_blogs(db: Session = Depends(get_db), user: User = Depends(require_auth)):
    try:
        result = await publisher.sync_to_database(db, limit=100)
        return RedirectResponse(
            f"/admin/blogs?synced=1&created={result['created']}&updated={result['updated']}",
            status_code=303,
        )
    except Exception as e:
        from urllib.parse import quote
        return RedirectResponse(f"/admin/blogs?sync_error={quote(str(e)[:200])}", status_code=303)


@router.get("/admin/blogs/{blog_id}", response_class=HTMLResponse)
async def blog_detail(blog_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(404, "Blog not found")
    return request.app.state.templates.TemplateResponse(
        "admin/blog_detail.html", {"request": request, "user": user, "blog": blog}
    )


@router.get("/admin/blogs/{blog_id}/edit", response_class=HTMLResponse)
async def blog_edit_page(blog_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(404, "Blog not found")
    return request.app.state.templates.TemplateResponse(
        "admin/blog_edit.html", {"request": request, "user": user, "blog": blog}
    )


@router.post("/admin/blogs/{blog_id}/edit")
async def blog_edit_save(
    blog_id: int,
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    excerpt: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    keywords: str = Form(""),
    category: str = Form("Ecommerce News"),
    tags: str = Form(""),
    push_to_wordpress: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(404)

    blog.title = title.strip()
    blog.content = content
    blog.excerpt = excerpt
    blog.meta_title = meta_title or title.strip()
    blog.meta_description = meta_description
    blog.keywords = keywords
    blog.category = category
    blog.tags = tags
    blog.word_count = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", content)))
    db.commit()

    if push_to_wordpress == "1" and publisher.is_configured():
        try:
            result = await publisher.update_remote(blog)
            if blog.wp_post_id:
                blog.wp_post_url = result.get("wp_post_url", blog.wp_post_url)
            else:
                publisher.mark_published(blog, result)
            db.commit()
            return RedirectResponse(f"/admin/blogs/{blog_id}?saved=1&pushed=1", status_code=303)
        except Exception as e:
            from urllib.parse import quote
            return RedirectResponse(f"/admin/blogs/{blog_id}/edit?error={quote(str(e)[:200])}", status_code=303)

    return RedirectResponse(f"/admin/blogs/{blog_id}?saved=1", status_code=303)


@router.post("/admin/blogs/{blog_id}/generate-images")
async def generate_blog_images(blog_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(404)

    def run():
        thread_db = SessionLocal()
        try:
            b = thread_db.query(Blog).filter(Blog.id == blog_id).first()
            return agent.attach_images_to_blog(thread_db, b)
        finally:
            thread_db.close()

    try:
        await asyncio.to_thread(run)
        return RedirectResponse(f"/admin/blogs/{blog_id}?images=1", status_code=303)
    except Exception as e:
        from urllib.parse import quote
        return RedirectResponse(f"/admin/blogs/{blog_id}?image_error={quote(str(e)[:200])}", status_code=303)


@router.post("/admin/blogs/{blog_id}/publish")
async def publish_blog(blog_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(404)
    try:
        result = await publisher.publish(blog)
        publisher.mark_published(blog, result)
        db.commit()
    except Exception as e:
        blog.status = BlogStatus.FAILED
        db.commit()
        raise HTTPException(400, str(e))
    return RedirectResponse(f"/admin/blogs/{blog_id}?published=1", status_code=303)


@router.post("/admin/blogs/{blog_id}/delete")
async def delete_blog(blog_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        return RedirectResponse("/admin/blogs", status_code=303)

    wp_ok = True
    if blog.wp_post_id and publisher.is_configured():
        try:
            wp_ok = await publisher.trash_remote(blog.wp_post_id)
        except Exception as e:
            from urllib.parse import quote
            return RedirectResponse(
                f"/admin/blogs/{blog_id}?delete_error={quote(str(e)[:200])}",
                status_code=303,
            )

    db.delete(blog)
    db.commit()
    suffix = "" if wp_ok else "?delete_warn=wp_unpublished_failed"
    return RedirectResponse(f"/admin/blogs{suffix}", status_code=303)


@router.get("/admin/ai", response_class=HTMLResponse)
async def ai_generator(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    jobs = db.query(AIJob).order_by(AIJob.created_at.desc()).limit(20).all()
    topics = db.query(TopicSuggestion).filter(TopicSuggestion.used == False).order_by(TopicSuggestion.priority.desc()).limit(15).all()
    return request.app.state.templates.TemplateResponse(
        "admin/ai_generator.html", {"request": request, "user": user, "jobs": jobs, "topics": topics}
    )


@router.post("/admin/ai/generate")
async def start_generation(
    request: Request,
    topic: str = Form(...),
    category: str = Form("Ecommerce News"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    job = agent.start_job(db, topic, category)
    job_id = job.id

    def run_generation():
        thread_db = SessionLocal()
        try:
            return agent.generate_blog(thread_db, job_id, topic, category)
        finally:
            thread_db.close()

    try:
        blog = await asyncio.to_thread(run_generation)
        return RedirectResponse(f"/admin/blogs/{blog.id}?generated=1", status_code=303)
    except Exception as e:
        jobs = db.query(AIJob).order_by(AIJob.created_at.desc()).limit(20).all()
        topics = db.query(TopicSuggestion).filter(TopicSuggestion.used == False).limit(15).all()
        return request.app.state.templates.TemplateResponse(
            "admin/ai_generator.html",
            {"request": request, "user": user, "jobs": jobs, "topics": topics, "error": str(e)},
        )


@router.post("/admin/ai/suggest-topics")
async def suggest_topics(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    try:
        await asyncio.to_thread(agent.suggest_topics, db, 10)
    except Exception as e:
        return request.app.state.templates.TemplateResponse(
            "admin/ai_generator.html",
            {
                "request": request,
                "user": user,
                "jobs": db.query(AIJob).order_by(AIJob.created_at.desc()).limit(20).all(),
                "topics": [],
                "error": str(e),
            },
        )
    return RedirectResponse("/admin/ai?suggested=1", status_code=303)


@router.get("/admin/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    wp_status = await publisher.test_connection() if publisher.is_configured() else {"ok": False, "error": "Not configured"}
    return request.app.state.templates.TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "user": user,
            "wp_configured": publisher.is_configured(),
            "wp_status": wp_status,
            "openai_configured": agent.is_configured(),
        },
    )
