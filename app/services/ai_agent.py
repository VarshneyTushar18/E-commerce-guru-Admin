"""AI Blog Agent — text + image generation for Indian ecommerce blogs."""

import base64
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from sqlalchemy.orm import Session

from app.auth import slugify
from app.config import settings
from app.models import AIJob, AIJobStatus, Blog, BlogStatus, TopicSuggestion

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

INDIAN_ECOMMERCE_CONTEXT = """
You are an expert content writer for Ecommerce Guru (ecomm-guru.com).
Audience: Amazon India, Flipkart, Meesho sellers, D2C founders, GST/compliance seekers.
Write clear English with Indian context (GST, INR, Flipkart, Amazon.in, Shiprocket, UPI).
Use HTML: <h2>, <h3>, <p>, <ul>, <li>, <strong>, <figure>, <img>, <figcaption>. No H1 title in content.
"""

TOPIC_CATEGORIES = [
    "Amazon FBA India",
    "Flipkart Selling",
    "D2C & Brand Building",
    "GST & Compliance",
    "Digital Marketing",
    "Logistics & Fulfillment",
    "Marketplace Trends",
    "Social Commerce",
    "Festive Season Selling",
    "Business Tips",
]


class BlogAgent:
    def __init__(self):
        self._last_image_error = ""

    def _build_client(self):
        if not settings.openai_api_key:
            return None, settings.openai_model

        base_url = settings.openai_base_url.strip() if settings.openai_base_url else None
        if not base_url and settings.openai_api_key.startswith("sk-or-"):
            base_url = "https://openrouter.ai/api/v1"

        kwargs = {"api_key": settings.openai_api_key}
        if base_url:
            kwargs["base_url"] = base_url

        model = settings.openai_model
        if settings.openai_api_key.startswith("sk-or-") and "/" not in model:
            model = f"openai/{model}"

        return OpenAI(**kwargs), model

    def _image_client(self) -> OpenAI | None:
        """Images API needs OpenAI directly (not OpenRouter)."""
        if not settings.openai_api_key or settings.openai_api_key.startswith("sk-or-"):
            return None
        return OpenAI(api_key=settings.openai_api_key)

    @property
    def client(self):
        client, _ = self._build_client()
        return client

    @property
    def model(self):
        _, model = self._build_client()
        return model

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    def _friendly_error(self, exc: Exception) -> str:
        msg = str(exc)
        if "402" in msg or "credits" in msg.lower():
            return (
                "API credits too low. Check your OpenAI/OpenRouter billing, "
                "or use a cheaper model in .env (gpt-4o-mini)."
            )
        if "rate_limit" in msg.lower() or "429" in msg:
            return "Rate limited by OpenAI. Wait a minute and try again."
        if "billing" in msg.lower() or "insufficient" in msg.lower():
            return "OpenAI billing issue for images. Check platform.openai.com billing."
        return msg

    def _chat(self, system: str, user: str, json_mode: bool = False, max_tokens: int = 4000) -> str:
        client, model = self._build_client()
        if not client:
            raise ValueError("OPENAI_API_KEY not configured. Add it to your .env file.")

        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            raise ValueError(self._friendly_error(e)) from e

    def _update_job(self, db: Session, job: AIJob, status: AIJobStatus, progress: int, step: str):
        job.status = status
        job.progress = progress
        job.current_step = step
        db.commit()

    def generate_image(self, prompt: str, filename_prefix: str = "blog") -> str | None:
        """Generate image with OpenAI Images API, save locally, return /static/uploads/... URL."""
        client = self._image_client()
        if not client:
            return None

        safe_prompt = (
            f"Professional blog photo for Indian ecommerce website. "
            f"{prompt}. Photorealistic, clean, modern, no text, no logos, no watermarks."
        )
        try:
            result = client.images.generate(
                model="gpt-image-1",
                prompt=safe_prompt[:1000],
                size="1024x1024",
                n=1,
            )
            item = result.data[0]
            b64 = getattr(item, "b64_json", None)
            if not b64 and getattr(item, "url", None):
                import httpx
                resp = httpx.get(item.url, timeout=60)
                resp.raise_for_status()
                raw = resp.content
            elif b64:
                raw = base64.b64decode(b64)
            else:
                return None

            name = f"{filename_prefix}-{uuid.uuid4().hex[:10]}.png"
            path = UPLOAD_DIR / name
            path.write_bytes(raw)
            return f"/static/uploads/{name}"
        except Exception as e:
            # Surface last image error for debugging / job notes
            self._last_image_error = self._friendly_error(e)
            return None

    def attach_images_to_blog(self, db: Session, blog: Blog) -> Blog:
        """Generate featured + inline images for an existing blog."""
        self._last_image_error = ""
        featured_prompt = f"Hero image for blog: {blog.title}. Indian ecommerce context."
        featured_url = self.generate_image(featured_prompt, filename_prefix=f"feat-{blog.slug[:30]}") or ""
        if not featured_url and self._last_image_error:
            raise ValueError(f"Image generation failed: {self._last_image_error}")

        inline_prompts = [
            f"Supporting visual for section of article: {blog.title}",
            f"Indian online sellers and marketplace advertising scene for: {blog.title}",
        ]
        inline_urls: list[str] = []
        for i, ip in enumerate(inline_prompts):
            url = self.generate_image(ip, filename_prefix=f"inline-{i}-{blog.slug[:20]}")
            if url:
                inline_urls.append(url)

        content = blog.content or ""
        # Strip previous generated figures to avoid duplicates
        content = re.sub(r"<figure\b[^>]*>.*?</figure>", "", content, flags=re.IGNORECASE | re.DOTALL)
        if inline_urls:
            content = self._insert_inline_images(content, inline_urls, inline_prompts)
        if featured_url:
            content = (
                f'<figure class="featured-image" style="margin:0 0 1.5rem">'
                f'<img src="{featured_url}" alt="{blog.title}" style="width:100%;height:auto;border-radius:8px" />'
                f"</figure>\n"
                + content
            )

        blog.featured_image_url = featured_url
        blog.content = content
        db.commit()
        db.refresh(blog)
        return blog

    def _insert_inline_images(self, content: str, image_urls: list[str], alts: list[str]) -> str:
        if not image_urls:
            return content
        parts = re.split(r"(<h2\b[^>]*>.*?</h2>)", content, flags=re.IGNORECASE | re.DOTALL)
        out: list[str] = []
        inserted = 0
        h2_count = 0
        for part in parts:
            out.append(part)
            if re.match(r"<h2\b", part or "", flags=re.IGNORECASE):
                h2_count += 1
                # Insert after 1st and 3rd H2
                if h2_count in (1, 3) and inserted < len(image_urls):
                    url = image_urls[inserted]
                    alt = alts[inserted] if inserted < len(alts) else "Ecommerce illustration"
                    out.append(
                        f'\n<figure class="blog-image" style="margin:1.5rem 0">'
                        f'<img src="{url}" alt="{alt}" style="width:100%;height:auto;border-radius:8px" />'
                        f"<figcaption style=\"font-size:0.875rem;color:#666;margin-top:0.5rem\">{alt}</figcaption>"
                        f"</figure>\n"
                    )
                    inserted += 1
        return "".join(out)

    def suggest_topics(self, db: Session, count: int = 10) -> list[TopicSuggestion]:
        prompt = f"""Generate {count} high-value blog topic ideas for Indian ecommerce sellers.
Return JSON: {{"topics": [{{"title": "...", "category": "...", "keywords": "kw1, kw2, kw3", "priority": 1-10}}]}}
Categories: {', '.join(TOPIC_CATEGORIES)}
Make topics timely (2025-2026) and search-intent driven."""

        raw = self._chat(INDIAN_ECOMMERCE_CONTEXT, prompt, json_mode=True, max_tokens=1000)
        data = json.loads(raw)
        suggestions = []
        for t in data.get("topics", []):
            s = TopicSuggestion(
                title=t["title"],
                category=t.get("category", "Ecommerce News"),
                keywords=t.get("keywords", ""),
                priority=t.get("priority", 5),
            )
            db.add(s)
            suggestions.append(s)
        db.commit()
        return suggestions

    def generate_blog(self, db: Session, job_id: int, topic: str, category: str = "Ecommerce News") -> Blog:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            raise ValueError("AI job not found")

        try:
            self._update_job(db, job, AIJobStatus.WRITING, 15, "Writing full blog")
            prompt = f"""Write a complete SEO blog for Indian ecommerce sellers.

Topic: {topic}
Category: {category}

Return JSON with this exact structure:
{{
  "title": "SEO title under 60 chars",
  "excerpt": "2-3 sentence excerpt",
  "meta_title": "meta title under 60 chars",
  "meta_description": "meta description under 155 chars",
  "keywords": "8-12 comma-separated keywords",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "slug": "url-friendly-slug",
  "content": "<full HTML article>",
  "featured_image_prompt": "short visual description for hero image",
  "inline_image_prompts": [
    "visual description for section image 1",
    "visual description for section image 2"
  ]
}}

Content requirements:
- 1800-2200 words
- Intro, 5-6 H2 sections with H3s where useful, FAQ (5 Qs), Conclusion with CTA
- Indian examples: Flipkart, Amazon.in, Meesho, GST, INR, Shiprocket, Razorpay
- Bullet lists and actionable tips
- HTML only with h2/h3/p/ul/li/strong — no H1, no markdown, no img tags yet
- Image prompts: photorealistic Indian ecommerce scenes, no text/logos
"""
            raw = self._chat(INDIAN_ECOMMERCE_CONTEXT, prompt, json_mode=True, max_tokens=4500)
            data = json.loads(raw)

            title = data.get("title") or topic
            slug = data.get("slug") or slugify(title)
            content = data.get("content", "")
            excerpt = data.get("excerpt", "")

            # Generate images
            self._update_job(db, job, AIJobStatus.WRITING, 55, "Generating blog images")
            featured_url = ""
            featured_prompt = data.get("featured_image_prompt") or f"Indian ecommerce seller working on laptop about {topic}"
            featured_url = self.generate_image(featured_prompt, filename_prefix=f"feat-{slugify(slug)[:30]}") or ""
            if not featured_url:
                err = getattr(self, "_last_image_error", "") or "unknown image API error"
                raise ValueError(f"Image generation failed: {err}")

            inline_prompts = data.get("inline_image_prompts") or []
            if not isinstance(inline_prompts, list):
                inline_prompts = []
            inline_prompts = [str(p) for p in inline_prompts[:2]]
            while len(inline_prompts) < 2:
                inline_prompts.append(f"Indian online marketplace selling scene related to {topic}")

            inline_urls: list[str] = []
            for i, ip in enumerate(inline_prompts):
                self._update_job(db, job, AIJobStatus.WRITING, 55 + i * 15, f"Generating image {i + 2}/3")
                url = self.generate_image(ip, filename_prefix=f"inline-{i}-{slugify(slug)[:20]}")
                if url:
                    inline_urls.append(url)

            if inline_urls:
                content = self._insert_inline_images(content, inline_urls, inline_prompts)

            if featured_url:
                content = (
                    f'<figure class="featured-image" style="margin:0 0 1.5rem">'
                    f'<img src="{featured_url}" alt="{title}" style="width:100%;height:auto;border-radius:8px" />'
                    f"</figure>\n"
                    + content
                )

            self._update_job(db, job, AIJobStatus.SEO_OPTIMIZING, 90, "Saving blog")
            word_count = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", content)))

            base_slug = slug
            counter = 1
            while db.query(Blog).filter(Blog.slug == slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1

            blog = Blog(
                title=title,
                slug=slug,
                excerpt=excerpt,
                content=content,
                meta_title=data.get("meta_title") or title,
                meta_description=data.get("meta_description", ""),
                keywords=data.get("keywords", ""),
                category=category,
                tags=", ".join(data.get("tags", [])),
                featured_image_url=featured_url,
                status=BlogStatus.REVIEW,
                word_count=word_count,
                ai_topic=topic,
            )
            db.add(blog)
            db.flush()

            job.blog_id = blog.id
            job.outline = json.dumps({"title": title, "slug": slug, "images": [featured_url, *inline_urls]})
            job.research_notes = data.get("keywords", "")
            job.status = AIJobStatus.COMPLETED
            job.progress = 100
            job.current_step = "Completed"
            job.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(blog)
            return blog

        except Exception as e:
            job.status = AIJobStatus.FAILED
            job.error_message = self._friendly_error(e)
            job.current_step = "Failed"
            db.commit()
            raise ValueError(self._friendly_error(e)) from e

    def start_job(self, db: Session, topic: str, category: str = "Ecommerce News") -> AIJob:
        job = AIJob(topic=topic, status=AIJobStatus.PENDING, current_step="Queued")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


agent = BlogAgent()
