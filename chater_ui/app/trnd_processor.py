import logging
import os
from datetime import datetime, timezone
from io import BytesIO

import redis
from local_models_helper import LocalModelService
from werkzeug.wrappers import Request

from eater.getter_eater import get_recommendation
from eater.proto import get_recomendation_pb2

logger = logging.getLogger(__name__)
redis_client = redis.StrictRedis(host=os.getenv("REDIS_ENDPOINT"), port=6379, db=0)

IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"
KEY_PREFIX = "_dev:" if IS_DEV else ""

# Cache expiry: 12 hours (in seconds)
RECOMMENDATION_CACHE_TTL = 12 * 60 * 60


def _get_recommendation_cache_key(user_email: str) -> str:
    """Generate Redis cache key for user recommendations (daily)."""
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{KEY_PREFIX}recommendation_cache:{user_email}:{current_date}"


def get_cached_recommendation(user_email: str) -> bytes | None:
    """
    Get cached recommendation from Redis.
    Returns the cached protobuf bytes if found, None otherwise.
    """
    try:
        cache_key = _get_recommendation_cache_key(user_email)
        cached_data = redis_client.get(cache_key)
        if cached_data:
            logger.info("Cache hit for recommendation, user: %s", user_email)
            return cached_data
        logger.debug("Cache miss for recommendation, user: %s", user_email)
        return None
    except Exception as e:
        logger.error(
            "Error reading recommendation cache for user %s: %s", user_email, e
        )
        return None


def cache_recommendation(user_email: str, recommendation_data: bytes) -> bool:
    """
    Store recommendation in Redis cache.
    Returns True if successful, False otherwise.
    """
    try:
        cache_key = _get_recommendation_cache_key(user_email)
        redis_client.setex(cache_key, RECOMMENDATION_CACHE_TTL, recommendation_data)
        logger.info("Cached recommendation for user: %s", user_email)
        return True
    except Exception as e:
        logger.error("Error caching recommendation for user %s: %s", user_email, e)
        return False


def invalidate_recommendation_cache(user_email: str) -> bool:
    """
    Invalidate (delete) cached recommendation for a user.
    Call this when user adds new food to trigger fresh recommendations.
    """
    try:
        cache_key = _get_recommendation_cache_key(user_email)
        redis_client.delete(cache_key)
        logger.debug("Invalidated recommendation cache for user: %s", user_email)
        return True
    except Exception as e:
        logger.error(
            "Error invalidating recommendation cache for user %s: %s", user_email, e
        )
        return False


def _generate_and_cache_recommendation_background(user_email: str):
    """
    Background task to generate recommendation and cache it.
    This runs after successful photo processing so recommendation is ready instantly.
    """

    local_model_service = LocalModelService()

    try:
        logger.info(
            "Starting background recommendation generation for user: %s", user_email
        )
        # DON'T invalidate old cache - keep it available until new one is ready
        # This allows users to see old recommendation instantly while new one generates

        # Create a mock request with protobuf data for 7 days
        proto_request = get_recomendation_pb2.RecommendationRequest()
        proto_request.days = 7
        proto_data = proto_request.SerializeToString()

        # Create a mock request object
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/protobuf",
            "CONTENT_LENGTH": str(len(proto_data)),
            "wsgi.input": BytesIO(proto_data),
        }
        mock_request = Request(environ)

        # Generate fresh recommendation
        recommendation_result = get_recommendation(
            request=mock_request,
            user_email=user_email,
            local_model_service=local_model_service,
        )

        if recommendation_result and isinstance(recommendation_result, tuple):
            data, status_code, *_ = recommendation_result
            if status_code == 200 and data:
                # Replace old cache with new recommendation
                cache_recommendation(user_email, data)
                logger.info(
                    "Background recommendation updated in cache for user: %s",
                    user_email,
                )
            else:
                logger.warning(
                    "Background recommendation generation returned non-200 "
                    "for user %s: %s",
                    user_email,
                    status_code,
                )
        else:
            logger.warning(
                "Background recommendation generation returned no result "
                "for user %s",
                user_email,
            )
    except Exception as e:
        logger.exception(
            "Background recommendation generation failed for user %s: %s", user_email, e
        )
