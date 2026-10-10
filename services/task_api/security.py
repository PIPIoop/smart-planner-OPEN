from __future__ import annotations

import hashlib
import hmac


def derive_user_access_token(service_token: str, user_id: str) -> str:
    return hmac.new(
        service_token.encode("utf-8"),
        f"smart-planner-user:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()