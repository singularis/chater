import logging

import common
from user import set_user_language

from .proto import set_language_pb2 as pb2

logger = logging.getLogger(__name__)


def set_language_handler(request, user_email):
    response = pb2.SetLanguageResponse()
    try:
        req = pb2.SetLanguageRequest()
        req.ParseFromString(request.data)
        language_code = (getattr(req, "language_code", "") or "").strip().lower()
        if not language_code:
            language_code = "en"

        set_user_language(user_email, language_code)
        try:
            common.redis_client.setex(
                f"{common.KEY_PREFIX}user_language:{user_email}", 7 * 24 * 3600, language_code
            )
        except Exception:
            pass
        response.success = True
        return (
            response.SerializeToString(),
            200,
            {"Content-Type": "application/grpc+proto"},
        )
    except Exception as e:
        logger.error(f"Error in set_language for user {user_email}: {e}")
        response.success = False
        return (
            response.SerializeToString(),
            500,
            {"Content-Type": "application/grpc+proto"},
        )
