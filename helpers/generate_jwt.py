"""
Local dev helper — generates a short-lived JWT signed with the same key
as the backend, useful for manual API testing.

Usage:
    cd helpers/
    python generate_jwt.py
"""
import datetime
import yaml
import jwt

with open("../vars.yaml", "r") as file:
    config = yaml.safe_load(file)

SECRET_KEY = config.get("JWT_SECRET")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET not set in vars.yaml")

print(f"Using JWT_SECRET from vars.yaml (first 8 chars): {SECRET_KEY[:8]}...")


def generate_token(email: str = "singularis", hours: int = 48) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub":  email,
        "iat":  now,
        "exp":  now + datetime.timedelta(hours=hours),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    print(f"Decoded payload: {decoded}")
    return token


if __name__ == "__main__":
    token = generate_token()
    print(f"\nToken:\n{token}")
