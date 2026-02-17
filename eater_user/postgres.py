import os
import logging

from databases import Database

logger = logging.getLogger(__name__)

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


async def nickname_is_taken(nickname: str, exclude_email: str) -> bool:
    """True if another user (different email) already has this nickname (case-insensitive)."""
    try:
        query = '''
            SELECT 1 FROM "user"
            WHERE lower(trim(nickname)) = lower(:nickname)
            AND lower(email) != lower(:exclude_email)
            AND nickname IS NOT NULL AND trim(nickname) != ''
            LIMIT 1
        '''
        row = await database.fetch_one(
            query,
            values={"nickname": nickname.strip(), "exclude_email": exclude_email}
        )
        return row is not None
    except Exception:
        return False


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
    Record a chess game for both players.
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
            "timestamp": timestamp,
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
            "timestamp": timestamp,
        })

        return True
    except Exception as e:
        logger.exception("record_chess_game failed: %s", e)
        return False


async def get_chess_stats(user_email: str, opponent_email: str = None):
    """Get chess statistics for a user against specific opponent or last opponent."""
    try:
        if opponent_email:
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
                "opponent_email": opponent_email,
            })
        else:
            # Find last opponent
            query_last = """
            SELECT opponent_email, timestamp
            FROM chess_games
            WHERE player_email = :user_email
            ORDER BY timestamp DESC
            LIMIT 1
            """
            last_game = await database.fetch_one(query_last, values={
                "user_email": user_email,
            })

            if not last_game:
                return None

            opponent_email = last_game["opponent_email"]

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
                "opponent_email": opponent_email,
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
                "last_game_date": last_date,
                "wins": wins,
                "losses": losses,
            }

        return None
    except Exception as e:
        logger.exception("get_chess_stats failed: %s", e)
        return None


async def get_all_chess_data(user_email: str):
    """Return total_wins, total_losses, total_draws, and detailed opponents data.
    Each opponent entry includes score and game history with date/time.
    Returns default structure when no data exists."""
    try:
        import datetime as _dt

        # Total stats for user
        total_row = await database.fetch_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE result = 'win') as total_wins,
                COUNT(*) FILTER (WHERE result = 'loss') as total_losses,
                COUNT(*) FILTER (WHERE result = 'draw') as total_draws
            FROM chess_games
            WHERE player_email = :user_email
            """,
            values={"user_email": user_email},
        )
        total_wins = int(total_row["total_wins"] or 0) if total_row else 0
        total_losses = int(total_row["total_losses"] or 0) if total_row else 0
        total_draws = int(total_row["total_draws"] or 0) if total_row else 0

        # Per-opponent breakdown with score
        opp_rows = await database.fetch_all(
            """
            SELECT
                opponent_email,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as my_wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as opponent_wins,
                SUM(CASE WHEN result = 'draw' THEN 1 ELSE 0 END) as draws,
                MAX(timestamp) as last_game_timestamp
            FROM chess_games
            WHERE player_email = :user_email
            GROUP BY opponent_email
            ORDER BY MAX(timestamp) DESC
            """,
            values={"user_email": user_email},
        )

        # Fetch individual game history for each opponent
        game_rows = await database.fetch_all(
            """
            SELECT opponent_email, result, timestamp
            FROM chess_games
            WHERE player_email = :user_email
            ORDER BY timestamp DESC
            """,
            values={"user_email": user_email},
        )

        # Group games by opponent
        games_by_opponent = {}
        for g in game_rows:
            opp = g["opponent_email"]
            ts = g["timestamp"]
            dt = _dt.datetime.fromtimestamp(ts / 1000, tz=_dt.timezone.utc)
            game_entry = {
                "result": g["result"],
                "timestamp": ts,
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M"),
            }
            games_by_opponent.setdefault(opp, []).append(game_entry)

        # Build opponents dict with score + history
        opponents = {}
        for r in opp_rows:
            opp_email = r["opponent_email"]
            my_wins = int(r["my_wins"] or 0)
            opp_wins = int(r["opponent_wins"] or 0)
            draws = int(r["draws"] or 0)

            # Get opponent nickname
            opp_nickname = await get_nickname(opp_email)

            last_ts = r["last_game_timestamp"]
            last_date = ""
            if last_ts:
                dt = _dt.datetime.fromtimestamp(last_ts / 1000, tz=_dt.timezone.utc)
                last_date = dt.strftime("%Y-%m-%d")

            opponents[opp_email] = {
                "score": f"{my_wins}:{opp_wins}",
                "wins": my_wins,
                "losses": opp_wins,
                "draws": draws,
                "nickname": opp_nickname or opp_email,
                "last_game_date": last_date,
                "games": games_by_opponent.get(opp_email, []),
            }

        return {
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_draws": total_draws,
            "opponents": opponents,
        }
    except Exception as e:
        logger.exception("get_all_chess_data failed: %s", e)
        return {"total_wins": 0, "total_losses": 0, "total_draws": 0, "opponents": {}}


async def get_chess_history(user_email: str, limit: int = 50, offset: int = 0):
    """Return paginated game history for a user, newest first.
    Each entry: {opponent_email, opponent_nickname, result, date, time, timestamp}."""
    try:
        import datetime as _dt

        rows = await database.fetch_all(
            """
            SELECT opponent_email, result, timestamp
            FROM chess_games
            WHERE player_email = :user_email
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
            """,
            values={"user_email": user_email, "limit": limit, "offset": offset},
        )

        total_row = await database.fetch_one(
            "SELECT COUNT(*) as total FROM chess_games WHERE player_email = :user_email",
            values={"user_email": user_email},
        )
        total = int(total_row["total"] or 0) if total_row else 0

        games = []
        for r in rows:
            ts = r["timestamp"]
            dt = _dt.datetime.fromtimestamp(ts / 1000, tz=_dt.timezone.utc)
            opp_nickname = await get_nickname(r["opponent_email"])
            games.append({
                "opponent_email": r["opponent_email"],
                "opponent_nickname": opp_nickname or r["opponent_email"],
                "result": r["result"],
                "timestamp": ts,
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M"),
            })

        return {"games": games, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception("get_chess_history failed: %s", e)
        return {"games": [], "total": 0, "limit": limit, "offset": offset}
