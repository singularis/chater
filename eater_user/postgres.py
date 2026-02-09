import os

from databases import Database

POSTGRES_USER = os.getenv("POSTGRES_USER", "eater")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_DB = os.getenv("POSTGRES_DB", "eater")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

ASYNC_DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

database = Database(ASYNC_DATABASE_URL)


async def test_database_connection():
    try:
        await database.connect()
        result = await database.fetch_one("SELECT 1 as test")
        await database.disconnect()
        return bool(result)
    except Exception:
        return False



async def ensure_nickname_column():
    try:
        query = """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user' AND column_name='nickname') THEN
                ALTER TABLE "user" ADD COLUMN nickname TEXT;
            END IF;
        END
        $$;
        """
        # Note: 'database.execute' might handle the DO block or we might need simple ALTER with exception catch
        # simpler approach:
        try:
             await database.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS nickname TEXT')
        except Exception:
             pass # Ignore if exists or other error (persist anyway)
    except Exception:
        pass


async def update_nickname(user_email: str, nickname: str):
    query = 'UPDATE "user" SET nickname = :nickname WHERE email = :user_email'
    await database.execute(query, values={"nickname": nickname, "user_email": user_email})


async def get_nickname(user_email: str):
    try:
        # Case insensitive match for email
        query = 'SELECT nickname FROM "user" WHERE lower(email) = lower(:user_email)'
        row = await database.fetch_one(query, values={"user_email": user_email})
        if row and row["nickname"]:
            return row["nickname"]
        return None
    except Exception:
        return None


async def autocomplete_query(query: str, limit: int, user_email: str):
    try:
        query = query.strip()[:100]
        if len(query) < 2:
            return []

        # Update search to include nickname
        search_query = """
            SELECT email, nickname, register_date, last_activity
            FROM "user" 
            WHERE (email ILIKE :like_query OR nickname ILIKE :like_query)
            AND email != :user_email
            ORDER BY 
                CASE 
                    WHEN nickname ILIKE :starts_with THEN 0
                    WHEN email ILIKE :starts_with THEN 1
                    WHEN nickname ILIKE :domain_query THEN 2
                    WHEN email ILIKE :domain_query THEN 3
                    ELSE 4
                END,
                length(email),
                email
            LIMIT :limit
        """

        like_query = f"%{query}%"
        starts_with_query = f"{query}%"
        domain_query = f"%@{query}%"

        results = await database.fetch_all(
            search_query,
            values={
                "like_query": like_query,
                "starts_with": starts_with_query,
                "domain_query": domain_query,
                "limit": limit,
                "user_email": user_email,
            },
        )

        users = []
        for row in results:
            user = {
                "email": row["email"],
                "nickname": row["nickname"], # Add nickname to result
                "register_date": (
                    row["register_date"].isoformat() if row["register_date"] else None
                ),
                "last_activity": (
                    row["last_activity"].isoformat() if row["last_activity"] else None
                ),
            }
            users.append(user)
        return users
    except Exception:
        raise


async def get_food_record_by_time(time: int, user_email: str):
    try:
        query = """
            SELECT dish_name, estimated_avg_calories, ingredients, total_avg_weight, contains, health_rating, food_health_level, image_id
            FROM public.dishes_day
            WHERE time = :time AND user_email = :user_email
            LIMIT 1
        """
        row = await database.fetch_one(
            query, values={"time": time, "user_email": user_email}
        )
        if not row:
            return None
        return {
            "dish_name": row["dish_name"],
            "estimated_avg_calories": row["estimated_avg_calories"],
            "ingredients": row["ingredients"],
            "total_avg_weight": row["total_avg_weight"],
            "contains": row["contains"],
            "health_rating": row["health_rating"],
            "food_health_level": row["food_health_level"],
            "image_id": row["image_id"],
        }
    except Exception:
        return None


# MARK: - Chess Games Functions


async def record_chess_game(player_email: str, opponent_email: str, result: str, timestamp: int):
    """
    Record a chess game for both players
    result: "win", "loss", or "draw"
    """
    try:
        # Record game for player
        query_player = """
        INSERT INTO chess_games (player_email, opponent_email, result, timestamp)
        VALUES (:player_email, :opponent_email, :result, :timestamp)
        """
        await database.execute(query_player, values={
            "player_email": player_email,
            "opponent_email": opponent_email,
            "result": result,
            "timestamp": timestamp
        })
        
        # Record mirror game for opponent
        opponent_result = "loss" if result == "win" else ("win" if result == "loss" else "draw")
        query_opponent = """
        INSERT INTO chess_games (player_email, opponent_email, result, timestamp)
        VALUES (:player_email, :opponent_email, :result, :timestamp)
        """
        await database.execute(query_opponent, values={
            "player_email": opponent_email,
            "opponent_email": player_email,
            "result": opponent_result,
            "timestamp": timestamp
        })
        
        return True
    except Exception:
        return False


async def get_chess_stats(user_email: str, opponent_email: str = None):
    """Get chess statistics for a user against specific opponent or overall"""
    try:
        if opponent_email:
            # Get stats against specific opponent
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE result = 'win') as wins,
                COUNT(*) FILTER (WHERE result = 'loss') as losses,
                COUNT(*) FILTER (WHERE result = 'draw') as draws,
                MAX(timestamp) as last_game_timestamp
            FROM chess_games
            WHERE player_email = :user_email AND opponent_email = :opponent_email
            """
            row = await database.fetch_one(query, values={
                "user_email": user_email,
                "opponent_email": opponent_email
            })
        else:
            # Get overall stats (last opponent)
            query_last = """
            SELECT opponent_email, timestamp
            FROM chess_games
            WHERE player_email = :user_email
            ORDER BY timestamp DESC
            LIMIT 1
            """
            last_game = await database.fetch_one(query_last, values={"user_email": user_email})
            
            if not last_game:
                return None
            
            opponent_email = last_game["opponent_email"]
            
            # Get stats against last opponent
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE result = 'win') as wins,
                COUNT(*) FILTER (WHERE result = 'loss') as losses,
                COUNT(*) FILTER (WHERE result = 'draw') as draws,
                MAX(timestamp) as last_game_timestamp
            FROM chess_games
            WHERE player_email = :user_email AND opponent_email = :opponent_email
            """
            row = await database.fetch_one(query, values={
                "user_email": user_email,
                "opponent_email": opponent_email
            })
        
        if row:
            wins = row["wins"] or 0
            losses = row["losses"] or 0
            
            # Get opponent nickname
            opponent_nickname = await get_nickname(opponent_email)
            opponent_name = opponent_nickname if opponent_nickname else opponent_email
            
            # Format last game date
            import datetime
            last_timestamp = row["last_game_timestamp"]
            last_date = ""
            if last_timestamp:
                dt = datetime.datetime.fromtimestamp(last_timestamp / 1000, tz=datetime.timezone.utc)
                last_date = dt.strftime("%Y-%m-%d")
            
            return {
                "score": f"{wins}:{losses}",
                "opponent_name": opponent_name,
                "opponent_email": opponent_email,
                "last_game_date": last_date
            }
        
        return None
    except Exception:
        return None
