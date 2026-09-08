import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BlogStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100), default="Admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Blog(Base):
    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    meta_title: Mapped[str] = mapped_column(String(500), default="")
    meta_description: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="Ecommerce News")
    tags: Mapped[str] = mapped_column(Text, default="")
    featured_image_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[BlogStatus] = mapped_column(Enum(BlogStatus), default=BlogStatus.DRAFT)
    wp_post_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wp_post_url: Mapped[str] = mapped_column(String(500), default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ai_topic: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    author = relationship("User", backref="blogs")
    ai_jobs = relationship("AIJob", back_populates="blog", cascade="all, delete-orphan")


class AIJobStatus(str, enum.Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    OUTLINING = "outlining"
    WRITING = "writing"
    SEO_OPTIMIZING = "seo_optimizing"
    COMPLETED = "completed"
    FAILED = "failed"


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blog_id: Mapped[int | None] = mapped_column(ForeignKey("blogs.id"), nullable=True)
    topic: Mapped[str] = mapped_column(Text)
    status: Mapped[AIJobStatus] = mapped_column(Enum(AIJobStatus), default=AIJobStatus.PENDING)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String(200), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    outline: Mapped[str] = mapped_column(Text, default="")
    research_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    blog = relationship("Blog", back_populates="ai_jobs")


class TopicSuggestion(Base):
    __tablename__ = "topic_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100))
    keywords: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
