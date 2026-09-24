"""Decrypts a founder's stored OAuth token (Component 14 stores the ciphertext; nothing else
should touch it directly). Used by anything that calls out as the founder: email, calendar,
and eventually the real X/LinkedIn posting providers."""
import json

from sqlalchemy.orm import Session

from ..models import OAuthToken
from ..settings import settings
from .billing_oauth import cipher


def access_token(db: Session, founder_id, platform: str) -> str | None:
    tok = db.get(OAuthToken, (founder_id, platform))
    if not tok:
        return None
    payload = json.loads(cipher(settings.token_encryption_key).decrypt(tok.ciphertext))
    return payload.get("access_token")
