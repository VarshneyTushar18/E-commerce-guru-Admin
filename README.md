# Ecomm Guru Blog Admin

AI-powered admin panel to generate and publish Indian ecommerce blogs to [ecomm-guru.com](https://www.ecomm-guru.com).

## Stack

- **FastAPI** — backend + admin UI
- **SQLAlchemy + SQLite** — database (swap to PostgreSQL in production)
- **OpenAI GPT-4o** — multi-step AI blog agent
- **WordPress REST API** — publish to ecomm-guru.com

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate     # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env — add your OPENAI_API_KEY and WordPress credentials

# 4. Seed topic suggestions
python seed.py

# 5. Run the server
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000** — login with credentials from `.env` (default: `admin@ecomm-guru.com` / `admin123`).

## AI Agent Pipeline

1. **Research** — keywords, search intent, Indian marketplace context
2. **Outline** — 8-12 H2 sections + FAQ structure
3. **Write** — 2500+ word HTML article with Flipkart/Amazon/Meesho examples
4. **SEO** — meta title, description, keywords, slug optimization
5. **Review & Publish** — you review in admin, one-click publish to WordPress

## WordPress Setup

1. Log into ecomm-guru.com WordPress admin
2. Go to **Users → Profile → Application Passwords**
3. Create a new application password
4. Add to `.env`:
   ```
   WP_USERNAME=your-username
   WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

## Project Structure

```
app/
  main.py              # FastAPI app entry
  models.py            # Blog, AIJob, TopicSuggestion models
  auth.py              # Session auth
  config.py            # Settings from .env
  services/
    ai_agent.py        # Multi-step AI blog generator
    wordpress.py       # WordPress REST API publisher
  routers/
    admin.py           # Admin routes
  templates/           # Jinja2 admin UI
```
