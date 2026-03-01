import json
import os
from functools import wraps

import jwt
from fastapi import HTTPException, Request

SECRET_KEY = os.getenv("JWT_SECRET")



def get_jwt_secret_key():
    """
    Returns the JWT secret key from the JWT_SECRET environment variable.
    The key must be ≥32 bytes (enforced at issuance time by chater-auth).
    """
    if not SECRET_KEY:
        raise ValueError("JWT_SECRET environment variable not set")
    return SECRET_KEY


def verify_jwt_token(token: str):
    jwt_secret = get_jwt_secret_key()
    try:
        return jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise


def validate_jwt_token(auth_header: str) -> str:
    if not auth_header:
        raise HTTPException(status_code=401, detail="Token is missing")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")

    try:
        token = auth_header.split(" ")[1]
        payload = verify_jwt_token(token)
        user_email = (
            payload.get("sub") or payload.get("email") or payload.get("user_email")
        )
        if not user_email:
            raise HTTPException(status_code=401, detail="Invalid token - no email")

        return user_email

    except HTTPException:
        raise
    except:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    return validate_jwt_token(auth_header)


def token_required(f):
    async def wrapper(request: Request):
        auth_header = request.headers.get("Authorization")
        user_email = validate_jwt_token(auth_header)

        return await f(request, user_email)

    return wrapper


async def validate_websocket_token(websocket, auth_data: str) -> str:
    try:
        auth_message = json.loads(auth_data)
        if auth_message.get("type") != "auth":
            await websocket.send_text(json.dumps({"error": "Authentication required"}))
            await websocket.close()
            return None

        token = auth_message.get("token")
        if not token:
            await websocket.send_text(json.dumps({"error": "Token required"}))
            await websocket.close()
            return None

        try:
            payload = verify_jwt_token(token)
            user_email = (
                payload.get("sub") or payload.get("email") or payload.get("user_email")
            )
            if not user_email:
                await websocket.send_text(
                    json.dumps({"error": "Invalid token - no email"})
                )
                await websocket.close()
                return None

            return user_email

        except:
            await websocket.send_text(json.dumps({"error": "Invalid token"}))
            await websocket.close()
            return None

    except:
        await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
        await websocket.close()
        return None
