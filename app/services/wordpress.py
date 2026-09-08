"""WordPress REST API integration for ecomm-guru.com"""

import base64
import mimetypes
import re
from datetime import datetime
from pathlib import Path

import httpx

from app.config import settings
from app.models import Blog, BlogStatus

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"

# Categories used by ecomm-guru.com homepage widgets
WP_CAT_ECOMMERCE_GURU = 1
WP_CAT_FEATURED_BLOG = 543
WP_CAT_TRENDING_BLOGS = 546
WP_CAT_ECOMMERCE_NEWS = 103
WP_CAT_DAILY_DOSE = 544
WP_CAT_BUSINESS_TIPS = 407
WP_CAT_DIGITAL_MARKETING = 303
WP_CAT_AMAZON = 484

CATEGORY_MAP = {
    "Amazon FBA India": [WP_CAT_AMAZON, WP_CAT_ECOMMERCE_NEWS],
    "Flipkart Selling": [WP_CAT_ECOMMERCE_NEWS, 506],  # Flipkart
    "D2C & Brand Building": [WP_CAT_BUSINESS_TIPS, 102],  # Online Business
    "GST & Compliance": [WP_CAT_ECOMMERCE_NEWS, WP_CAT_BUSINESS_TIPS],
    "Digital Marketing": [WP_CAT_DIGITAL_MARKETING, 99],
    "Logistics & Fulfillment": [104, 473],
    "Marketplace Trends": [WP_CAT_ECOMMERCE_NEWS, 545],
    "Social Commerce": [120, WP_CAT_DIGITAL_MARKETING],
    "Festive Season Selling": [WP_CAT_ECOMMERCE_NEWS, WP_CAT_BUSINESS_TIPS],
    "Business Tips": [WP_CAT_BUSINESS_TIPS, 559],
    "Ecommerce News": [WP_CAT_ECOMMERCE_NEWS],
}


class WordPressPublisher:
    def _auth_header(self) -> str | None:
        if not settings.wp_username or not settings.wp_app_password:
            return None
        creds = f"{settings.wp_username}:{settings.wp_app_password}"
        return base64.b64encode(creds.encode()).decode()

    @property
    def base_url(self) -> str:
        return settings.wp_site_url.rstrip("/")

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/wp-json/wp/v2"

    def is_configured(self) -> bool:
        return bool(self._auth_header())

    def _headers(self) -> dict:
        auth = self._auth_header()
        if not auth:
            raise ValueError("WordPress not configured")
        return {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "User-Agent": "EcommGuruAdmin/1.0",
        }

    def _auth_only_headers(self) -> dict:
        auth = self._auth_header()
        if not auth:
            raise ValueError("WordPress not configured")
        return {
            "Authorization": f"Basic {auth}",
            "User-Agent": "EcommGuruAdmin/1.0",
        }

    async def test_connection(self) -> dict:
        if not self.is_configured():
            return {"ok": False, "error": "WordPress credentials not configured in .env"}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                r = await client.get(
                    f"{self.api_url}/posts",
                    headers=self._headers(),
                    params={"status": "draft", "per_page": 1, "context": "edit"},
                )
                if r.status_code == 200:
                    return {
                        "ok": True,
                        "user": settings.wp_username,
                        "id": None,
                        "note": "Authenticated — can read/create posts",
                    }
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    def resolve_category_ids(self, category_name: str) -> list[int]:
        """Homepage shows latest posts + Featured/Trending widgets by category."""
        ids = {
            WP_CAT_ECOMMERCE_GURU,   # main brand / latest carousel
            WP_CAT_FEATURED_BLOG,    # Featured Blog section
            WP_CAT_TRENDING_BLOGS,   # Trending Blogs section
            WP_CAT_DAILY_DOSE,       # Daily Ecommerce Dose
        }
        for cid in CATEGORY_MAP.get(category_name, [WP_CAT_ECOMMERCE_NEWS]):
            ids.add(cid)
        return sorted(ids)

    async def get_categories(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(f"{self.api_url}/categories?per_page=100")
            if r.status_code == 200:
                return [{"id": c["id"], "name": c["name"], "slug": c["slug"]} for c in r.json()]
        return []

    async def upload_media(self, client: httpx.AsyncClient, local_url: str, title: str = "") -> dict | None:
        """Upload a local /static/uploads file to WordPress media library (multipart)."""
        if not local_url.startswith("/static/"):
            return None
        path = STATIC_ROOT / local_url.replace("/static/", "", 1)
        if not path.exists():
            return None

        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        filename = path.name
        # Host WAF blocks raw binary media upload; multipart works.
        files = {"file": (filename, path.read_bytes(), mime)}
        r = await client.post(
            f"{self.api_url}/media",
            headers=self._auth_only_headers(),
            files=files,
        )
        if r.status_code not in (200, 201):
            return None
        body = r.json()
        return {
            "id": body.get("id"),
            "url": body.get("source_url") or (body.get("guid") or {}).get("rendered", ""),
        }

    async def publish(self, blog: Blog) -> dict:
        if not self.is_configured():
            raise ValueError("WordPress not configured. Set WP_USERNAME and WP_APP_PASSWORD in .env")

        content = blog.content
        featured_media_id = None
        categories = self.resolve_category_ids(blog.category or "Ecommerce News")

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            # Upload featured + inline local images, rewrite URLs
            local_urls = re.findall(r'src="(/static/uploads/[^"]+)"', content)
            if blog.featured_image_url and blog.featured_image_url not in local_urls:
                local_urls.insert(0, blog.featured_image_url)

            seen = set()
            for local_url in local_urls:
                if local_url in seen:
                    continue
                seen.add(local_url)
                uploaded = await self.upload_media(client, local_url, title=blog.title)
                if not uploaded or not uploaded.get("url"):
                    continue
                content = content.replace(local_url, uploaded["url"])
                if local_url == blog.featured_image_url:
                    featured_media_id = uploaded.get("id")
                    blog.featured_image_url = uploaded["url"]

            payload = {
                "title": blog.title,
                "content": content,
                "excerpt": blog.excerpt,
                "status": "publish",
                "slug": blog.slug,
                "format": "standard",
                "categories": categories,
                "sticky": True,
            }
            if featured_media_id:
                payload["featured_media"] = featured_media_id

            if blog.wp_post_id:
                r = await client.post(
                    f"{self.api_url}/posts/{blog.wp_post_id}",
                    headers=self._headers(),
                    json=payload,
                )
            else:
                r = await client.post(
                    f"{self.api_url}/posts",
                    headers=self._headers(),
                    json=payload,
                )

            if r.status_code not in (200, 201):
                raise ValueError(f"WordPress publish failed: HTTP {r.status_code} — {r.text[:300]}")

            data = r.json()
            blog.content = content
            return {
                "wp_post_id": data["id"],
                "wp_post_url": data.get("link", ""),
                "status": data.get("status"),
                "categories": data.get("categories", categories),
            }

    async def fetch_posts(self, per_page: int = 50, max_pages: int = 5, statuses: str = "publish,draft,pending,private") -> list[dict]:
        """Pull posts from WordPress for admin sync."""
        if not self.is_configured():
            raise ValueError("WordPress not configured")

        posts: list[dict] = []
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for page in range(1, max_pages + 1):
                r = await client.get(
                    f"{self.api_url}/posts",
                    headers=self._headers(),
                    params={
                        "per_page": per_page,
                        "page": page,
                        "status": statuses,
                        "context": "edit",
                        "_embed": "1",
                        "orderby": "date",
                        "order": "desc",
                    },
                )
                if r.status_code == 400 and "rest_post_invalid_page_number" in r.text:
                    break
                if r.status_code != 200:
                    raise ValueError(f"WordPress sync failed: HTTP {r.status_code} — {r.text[:200]}")
                batch = r.json()
                if not batch:
                    break
                posts.extend(batch)
                total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
                if page >= total_pages:
                    break
        return posts

    def _strip_html(self, html: str) -> str:
        return re.sub(r"<[^>]+>", " ", html or "")

    def upsert_synced_post(self, db, post: dict) -> Blog:
        """Create or update local Blog from a WordPress post payload."""
        from html import unescape

        from app.auth import slugify
        from sqlalchemy.orm import Session

        assert isinstance(db, Session)

        wp_id = post.get("id")
        title = unescape(post.get("title", {}).get("raw") or post.get("title", {}).get("rendered") or "Untitled")
        content = post.get("content", {}).get("raw") or post.get("content", {}).get("rendered") or ""
        excerpt_raw = post.get("excerpt", {}).get("raw") or post.get("excerpt", {}).get("rendered") or ""
        excerpt = self._strip_html(unescape(excerpt_raw)).strip()
        slug = post.get("slug") or slugify(title)
        link = post.get("link") or ""
        wp_status = post.get("status", "publish")

        featured = ""
        featured_media = post.get("featured_media")
        # Prefer featured image from embedded if present
        embedded = post.get("_embedded") or {}
        media = (embedded.get("wp:featuredmedia") or [None])[0]
        if media and media.get("source_url"):
            featured = media["source_url"]

        word_count = len(re.findall(r"\w+", self._strip_html(content)))

        if wp_status == "publish":
            status = BlogStatus.PUBLISHED
        elif wp_status in ("draft", "pending", "private"):
            status = BlogStatus.DRAFT
        else:
            status = BlogStatus.REVIEW

        blog = db.query(Blog).filter(Blog.wp_post_id == wp_id).first()
        if not blog:
            # Avoid slug collision with local-only posts
            existing_slug = db.query(Blog).filter(Blog.slug == slug, Blog.wp_post_id.is_(None)).first()
            if existing_slug or db.query(Blog).filter(Blog.slug == slug).first():
                # If same slug already linked to this wp id handled above; else uniquify
                other = db.query(Blog).filter(Blog.slug == slug).first()
                if other and other.wp_post_id != wp_id:
                    slug = f"{slug}-wp-{wp_id}"

            blog = Blog(
                title=title,
                slug=slug,
                content=content,
                excerpt=excerpt[:1000],
                meta_title=title[:500],
                meta_description=excerpt[:500],
                category="Ecommerce News",
                featured_image_url=featured,
                status=status,
                word_count=word_count,
                wp_post_id=wp_id,
                wp_post_url=link,
                published_at=datetime.utcnow() if status == BlogStatus.PUBLISHED else None,
                ai_topic="Synced from WordPress",
            )
            db.add(blog)
        else:
            blog.title = title
            blog.slug = slug
            blog.content = content
            blog.excerpt = excerpt[:1000]
            blog.meta_title = title[:500]
            blog.meta_description = excerpt[:500]
            blog.word_count = word_count
            blog.wp_post_url = link
            blog.status = status
            if featured:
                blog.featured_image_url = featured
            if status == BlogStatus.PUBLISHED and not blog.published_at:
                blog.published_at = datetime.utcnow()

        return blog

    async def sync_to_database(self, db, limit: int = 100) -> dict:
        posts = await self.fetch_posts(per_page=50, max_pages=max(1, (limit + 49) // 50))
        created = updated = 0
        for post in posts[:limit]:
            wp_id = post.get("id")
            existed = db.query(Blog).filter(Blog.wp_post_id == wp_id).first() is not None
            self.upsert_synced_post(db, post)
            if existed:
                updated += 1
            else:
                created += 1
        db.commit()
        return {"created": created, "updated": updated, "total": created + updated}

    async def update_remote(self, blog: Blog) -> dict:
        """Push local edits to WordPress (create or update)."""
        if not blog.wp_post_id:
            return await self.publish(blog)

        payload = {
            "title": blog.title,
            "content": blog.content,
            "excerpt": blog.excerpt,
            "slug": blog.slug,
            "status": "publish" if blog.status == BlogStatus.PUBLISHED else "draft",
            "format": "standard",
        }
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.post(
                f"{self.api_url}/posts/{blog.wp_post_id}",
                headers=self._headers(),
                json=payload,
            )
            if r.status_code not in (200, 201):
                raise ValueError(f"WordPress update failed: HTTP {r.status_code} — {r.text[:300]}")
            data = r.json()
            blog.wp_post_url = data.get("link", blog.wp_post_url)
            return {"wp_post_id": data["id"], "wp_post_url": blog.wp_post_url}

    async def trash_remote(self, wp_post_id: int) -> bool:
        """Remove a post from the live site.

        LiteSpeed on ecomm-guru.com blocks HTTP DELETE (403), and this WP
        install rejects status=trash via REST (WooCommerce status enum).
        Fallback: set status to draft so the post disappears from the public site.
        """
        if not wp_post_id:
            return False
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # 1) Prefer trash if the API allows it
            r = await client.post(
                f"{self.api_url}/posts/{wp_post_id}",
                headers=self._headers(),
                json={"status": "trash"},
            )
            if r.status_code in (200, 201):
                return True

            # 2) Hard delete (usually blocked by host WAF)
            r2 = await client.delete(
                f"{self.api_url}/posts/{wp_post_id}?force=true",
                headers=self._headers(),
            )
            if r2.status_code in (200, 201):
                return True

            # 3) Unpublish — works on this host (same as manual draft)
            r3 = await client.post(
                f"{self.api_url}/posts/{wp_post_id}",
                headers=self._headers(),
                json={"status": "draft"},
            )
            if r3.status_code in (200, 201):
                return True

            raise ValueError(
                f"WordPress remove failed: trash={r.status_code}, "
                f"delete={r2.status_code}, draft={r3.status_code} — {r3.text[:200]}"
            )

    def mark_published(self, blog: Blog, result: dict):
        blog.wp_post_id = result["wp_post_id"]
        blog.wp_post_url = result.get("wp_post_url", "")
        blog.status = BlogStatus.PUBLISHED
        blog.published_at = datetime.utcnow()


publisher = WordPressPublisher()
