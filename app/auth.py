import re
import unicodedata

import bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import settings

serializer = URLSafeTimedSerializer(settings.secret_key)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def decode_session_token(token: str, max_age: int = 86400 * 7) -> int | None:
    try:
        data = serializer.loads(token, max_age=max_age)
        return data.get("user_id")
    except BadSignature:
        return None


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")
