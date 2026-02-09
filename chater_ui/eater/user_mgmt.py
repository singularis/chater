import logging
import os
import requests
from flask import jsonify

from .proto import add_friend_pb2, get_friends_pb2, share_food_pb2

logger = logging.getLogger(__name__)

# Default to internal k8s service name in chater-ui namespace
AUTOCOMPLETE_SERVICE_URL = os.getenv("AUTOCOMPLETE_SERVICE_URL", "http://eater-users-service")

def update_user_nickname(request, user_email):
    """
    Proxy the nickname update request to the eater_user/autocomplete service.
    """
    try:
        # validate request
        data = request.get_json()
        if not data or "nickname" not in data:
             return jsonify({"error": "Nickname is required"}), 400
        
        nickname = data["nickname"]
        
        # Call internal service
        url = f"{AUTOCOMPLETE_SERVICE_URL}/autocomplete/update_nickname"
        headers = {
            # Use the same token or just trust internal network? 
            # The backend service expects @token_required wrapper which checks 'Authorization' header.
            # So we must forward the Authorization header.
            "Authorization": request.headers.get("Authorization"),
            "Content-Type": "application/json"
        }
        
        # We need to send valid JSON that matches what update_nickname_endpoint expects
        payload = {"nickname": nickname}
        
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        
        if resp.status_code == 200:
             return jsonify(resp.json()), 200
        else:
             logger.error(f"Failed to update nickname: {resp.status_code} {resp.text}")
             try:
                 return jsonify(resp.json()), resp.status_code
             except:
                 return jsonify({"error": "Failed to update nickname"}), resp.status_code

    except Exception as e:
        logger.exception(f"Error updating nickname for {user_email}: {e}")
        return jsonify({"error": "Internal Error"}), 500


def add_friend_request(request, user_email):
    """
    Proxy add friend request to eater-users service.
    Expects JSON { "email": "friend@email.com" }
    """
    try:
        data = request.get_json()
        if not data or "email" not in data:
            return jsonify({"error": "Friend email is required"}), 400
            
        friend_email = data["email"]
        
        # Create Protobuf request
        req = add_friend_pb2.AddFriendRequest()
        req.email = friend_email
        
        url = f"{AUTOCOMPLETE_SERVICE_URL}/autocomplete/addfriend"
        headers = {
            "Authorization": request.headers.get("Authorization"),
            "Content-Type": "application/x-protobuf"
        }
        
        resp = requests.post(url, data=req.SerializeToString(), headers=headers, timeout=5)
        
        if resp.status_code == 200:
            # Parse response
            res = add_friend_pb2.AddFriendResponse()
            res.ParseFromString(resp.content)
            return jsonify({"success": res.success}), 200
        else:
            logger.error(f"Failed to add friend: {resp.status_code} {resp.text}")
            try:
                # Try to parse JSON error if any (FastAPI returns JSON on error)
                return jsonify(resp.json()), resp.status_code
            except:
                return jsonify({"error": "Failed to add friend"}), resp.status_code
                
    except Exception as e:
        logger.exception(f"Error adding friend for {user_email}: {e}")
        return jsonify({"error": "Internal Error"}), 500


def get_friends_request(user_email, request):
    """
    Proxy get friends request to eater-users service.
    """
    try:
        url = f"{AUTOCOMPLETE_SERVICE_URL}/autocomplete/getfriend"
        headers = {
            "Authorization": request.headers.get("Authorization"),
        }
        
        resp = requests.get(url, headers=headers, timeout=5)
        
        if resp.status_code == 200:
            res = get_friends_pb2.GetFriendsResponse()
            res.ParseFromString(resp.content)
            
            friends = []
            for f in res.friends:
                friends.append({
                    "email": f.email,
                    "nickname": f.nickname
                })
            
            return jsonify({"count": res.count, "friends": friends}), 200
        else:
            logger.error(f"Failed to get friends: {resp.status_code} {resp.text}")
            return jsonify({"error": "Failed to get friends"}), resp.status_code

    except Exception as e:
        logger.exception(f"Error getting friends for {user_email}: {e}")
        return jsonify({"error": "Internal Error"}), 500


def share_food_request(request, user_email):
    """
    Proxy share food request to eater-users service.
    Expects JSON with time, to_email, percentage
    """
    try:
        data = request.get_json()
        required = ["time", "to_email", "percentage"]
        if not all(k in data for k in required):
            return jsonify({"error": "Missing required fields"}), 400
            
        req = share_food_pb2.ShareFoodRequest()
        req.time = int(data["time"])
        req.from_email = user_email
        req.to_email = data["to_email"]
        req.percentage = int(data["percentage"])
        
        url = f"{AUTOCOMPLETE_SERVICE_URL}/autocomplete/sharefood"
        headers = {
            "Authorization": request.headers.get("Authorization"),
            "Content-Type": "application/x-protobuf"
        }
        
        resp = requests.post(url, data=req.SerializeToString(), headers=headers, timeout=5)
        
        if resp.status_code == 200:
            # Response is empty protobuf on success?
            # Check autocomplete_service.py: returns empty protobuf
            return jsonify({"success": True}), 200
        else:
            logger.error(f"Failed to share food: {resp.status_code} {resp.text}")
            try:
                return jsonify(resp.json()), resp.status_code
            except:
                return jsonify({"error": "Failed to share food"}), resp.status_code

    except Exception as e:
        logger.exception(f"Error sharing food for {user_email}: {e}")
        return jsonify({"error": "Internal Error"}), 500
