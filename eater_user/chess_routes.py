"""Chess game endpoints: record game, get stats, get all data."""
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from common import token_required
from connection_manager import manager, safe_send_websocket_message
from postgres import database, get_chess_stats, record_chess_game
from proto import chess_game_pb2

logger = logging.getLogger("autocomplete_service")

router = APIRouter(prefix="/autocomplete", tags=["chess"])


@router.post("/record_chess_game")
@token_required
async def record_chess_game_endpoint(request: Request, user_email: str):
    try:
        logger.debug(f"/autocomplete/record_chess_game: start for user={user_email}")
        body = await request.body()
        if not body:
            logger.warning("/autocomplete/record_chess_game: empty body")
            raise HTTPException(status_code=400, detail="Request body required")

        try:
            data = json.loads(body)
            player_email = data.get("player_email", "").strip()
            opponent_email = data.get("opponent_email", "").strip()
            result = data.get("result", "").strip()
            timestamp = int(data.get("timestamp", 0))
            logger.debug(f"/autocomplete/record_chess_game: parsed JSON request")
        except Exception:
            try:
                chess_request = chess_game_pb2.RecordChessGameRequest()
                chess_request.ParseFromString(body)
                player_email = chess_request.player_email.strip()
                opponent_email = chess_request.opponent_email.strip()
                result = chess_request.result.strip()
                timestamp = int(chess_request.timestamp)
                logger.debug(f"/autocomplete/record_chess_game: parsed protobuf request")
            except Exception:
                logger.exception("/autocomplete/record_chess_game: failed to parse body")
                raise HTTPException(status_code=400, detail="Invalid request format")

        logger.debug(f"/autocomplete/record_chess_game: parsed request - player={player_email}, opponent={opponent_email}, result={result}")

        if not player_email or not opponent_email:
            logger.warning("/autocomplete/record_chess_game: missing player_email or opponent_email")
            raise HTTPException(status_code=400, detail="Both player_email and opponent_email are required")

        if player_email != user_email:
            logger.warning(f"/autocomplete/record_chess_game: player_email != token user ({player_email} != {user_email})")
            raise HTTPException(status_code=403, detail="Cannot record game for another user")

        if result not in ["win", "loss", "draw"]:
            logger.warning(f"/autocomplete/record_chess_game: invalid result={result}")
            raise HTTPException(status_code=400, detail="result must be 'win', 'loss', or 'draw'")

        success = await record_chess_game(player_email, opponent_email, result, timestamp)

        if not success:
            logger.error("/autocomplete/record_chess_game: failed to record game")
            raise HTTPException(status_code=500, detail="Failed to record chess game")

        player_stats = await get_chess_stats(player_email, opponent_email)
        opponent_stats = await get_chess_stats(opponent_email, player_email)

        if opponent_email in manager.user_connections:
            opponent_ws = manager.user_connections[opponent_email]
            notification = {
                "type": "chess_game_update",
                "player_email": player_email,
                "result": result,
                "score": opponent_stats["score"] if opponent_stats else "0:0"
            }
            await safe_send_websocket_message(opponent_ws, notification)
            logger.info(f"/autocomplete/record_chess_game: sent WebSocket notification to {opponent_email}")

        response_data = {
            "success": True,
            "player_wins": player_stats.get("wins", 0) if player_stats else 0,
            "player_losses": player_stats.get("losses", 0) if player_stats else 0,
            "opponent_wins": opponent_stats.get("wins", 0) if opponent_stats else 0,
            "opponent_losses": opponent_stats.get("losses", 0) if opponent_stats else 0
        }

        logger.info(f"/autocomplete/record_chess_game: success - player={player_stats['score'] if player_stats else '0:0'}, opponent={opponent_stats['score'] if opponent_stats else '0:0'}")
        return response_data

    except HTTPException:
        raise
    except Exception:
        logger.exception("/autocomplete/record_chess_game: unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")


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
