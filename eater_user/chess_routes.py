"""Chess read-only endpoints: get stats, get all data. Recording is via app + Kafka + eater."""
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from common import token_required
from postgres import database, get_chess_stats
from proto import chess_game_pb2

logger = logging.getLogger("autocomplete_service")

router = APIRouter(prefix="/autocomplete", tags=["chess"])


@router.post("/get_chess_stats")
@token_required
async def get_chess_stats_endpoint(request: Request, user_email: str):
    try:
        logger.debug(f"/autocomplete/get_chess_stats: start for user={user_email}")
        body = await request.body()
        if not body:
            logger.warning("/autocomplete/get_chess_stats: empty body")
            raise HTTPException(status_code=400, detail="Request body required")

        try:
            data = json.loads(body)
            request_email = data.get("user_email", "").strip()
            opponent_email = data.get("opponent_email", "").strip() if "opponent_email" in data else None
            logger.debug(f"/autocomplete/get_chess_stats: parsed JSON request")
        except Exception:
            try:
                stats_request = chess_game_pb2.GetChessStatsRequest()
                stats_request.ParseFromString(body)
                request_email = stats_request.user_email.strip()
                opponent_email = stats_request.opponent_email.strip() if stats_request.opponent_email else None
                logger.debug(f"/autocomplete/get_chess_stats: parsed protobuf request")
            except Exception:
                logger.exception("/autocomplete/get_chess_stats: failed to parse body")
                raise HTTPException(status_code=400, detail="Invalid request format")

        if request_email != user_email:
            logger.warning(f"/autocomplete/get_chess_stats: request_email != token user ({request_email} != {user_email})")
            raise HTTPException(status_code=403, detail="Cannot get stats for another user")

        stats = await get_chess_stats(user_email, opponent_email)

        response_data = {
            "score": stats["score"] if stats else "0:0",
            "opponent_name": stats["opponent_name"] if stats else "",
            "last_game_date": stats["last_game_date"] if stats else ""
        }

        logger.info(f"/autocomplete/get_chess_stats: success - score={response_data['score']}")
        return response_data

    except HTTPException:
        raise
    except Exception:
        logger.exception("/autocomplete/get_chess_stats: unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/get_all_chess_data")
@token_required
async def get_all_chess_data_endpoint(request: Request, user_email: str):
    """Get all chess data: total wins and scores with all opponents"""
    try:
        logger.debug(f"/autocomplete/get_all_chess_data: start for user={user_email}")

        query_total = """
        SELECT COUNT(*) FILTER (WHERE result = 'win') as total_wins
        FROM chess_games
        WHERE player_email = :user_email
        """
        total_row = await database.fetch_one(query_total, values={"user_email": user_email})
        total_wins = total_row["total_wins"] if total_row else 0

        query_opponents = """
        SELECT
            opponent_email,
            COUNT(*) FILTER (WHERE result = 'win') as wins,
            COUNT(*) FILTER (WHERE result = 'loss') as losses
        FROM chess_games
        WHERE player_email = :user_email
        GROUP BY opponent_email
        """
        opponent_rows = await database.fetch_all(query_opponents, values={"user_email": user_email})

        opponents = {}
        for row in opponent_rows:
            opponents[row["opponent_email"]] = f"{row['wins']}:{row['losses']}"

        response_data = {
            "total_wins": total_wins,
            "opponents": opponents
        }

        logger.info(f"/autocomplete/get_all_chess_data: success - total_wins={total_wins}, opponents={len(opponents)}")
        return response_data

    except HTTPException:
        raise
    except Exception:
        logger.exception("/autocomplete/get_all_chess_data: unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")
