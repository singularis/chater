# Chess Sync TODO

## ⚠️ Known Issue: Chess Games Not Syncing Between Players

**Status:** Partially working - local counting works, but cross-player sync broken

**Last Updated:** 2026-02-02

### Current Behavior:
- ✅ Local game recording works correctly
- ✅ Total wins counter increments properly
- ✅ League promotions work
- ✅ Reset functionality works
- ❌ **Games don't appear on opponent's device**
- ❌ **Backend sync not working properly**

### What's Implemented:
1. **iOS App (`ActivitiesView.swift`):**
   - Records games locally with `chessTotalWins` and `chessOpponents` JSON
   - Sends game to backend via `GRPCService().recordChessGame()`
   - Loads data from backend on app open via `syncChessDataFromBackend()`
   - League system (Wooden → Bronze → Silver → Gold → Diamond → Grandmaster)

2. **Backend (`autocomplete_service.py`):**
   - `POST /autocomplete/record_chess_game` - records game for both players
   - `GET /autocomplete/get_all_chess_data` - returns total wins + all opponents
   - WebSocket notification to opponent when game is recorded
   - Database table `chess_games` with player/opponent emails

3. **Database (`postgres.py`):**
   - `record_chess_game()` - inserts game for both player and opponent
   - `get_chess_stats()` - fetches win/loss/draw counts
   - Mirror games: player wins → opponent loses (and vice versa)

### Problem:
**Backend is empty** - games are not being persisted to database, or sync is failing silently.

### To Debug Tomorrow:
1. **Check if backend is running:**
   ```bash
   cd /Users/iva/Documents/Eateria/chater_new/eater_user
   # Check if service is up
   curl http://localhost:8000/health
   ```

2. **Check database:**
   ```sql
   SELECT * FROM chess_games ORDER BY timestamp DESC LIMIT 10;
   ```

3. **Test backend endpoint directly:**
   ```bash
   curl -X POST http://localhost:8000/autocomplete/record_chess_game \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "player_email": "iva@example.com",
       "opponent_email": "dante@example.com", 
       "result": "win",
       "timestamp": 1706904000000
     }'
   ```

4. **Check Xcode logs for errors:**
   - Look for `❌` or `⚠️` in console
   - Check if `Backend sync successful` appears
   - Verify `syncChessDataFromBackend()` is called

5. **Verify WebSocket connection:**
   - Check if opponent is connected to WebSocket
   - Look for "chess_game_update" notifications in logs

### Potential Fixes:
1. **Backend not running** → Start eater_user service
2. **Database connection issue** → Check postgres connection
3. **Auth token invalid** → Verify Bearer token is sent
4. **Network error** → Check iOS network permissions
5. **WebSocket not connected** → Opponent needs to be online

### Files to Check:
- `/Users/iva/Documents/Eateria/eater/eater/Services/GRPCService+Chess.swift` - iOS API calls
- `/Users/iva/Documents/Eateria/chater_new/eater_user/autocomplete_service.py` - Backend endpoints
- `/Users/iva/Documents/Eateria/chater_new/eater_user/postgres.py` - Database logic
- `/Users/iva/Documents/Eateria/eater/eater/Views/ActivitiesView.swift` - UI logic

### Quick Test Plan:
1. Player 1 (Iva) records a win against Player 2 (Dante)
2. Check Xcode logs on Iva's device - should see `✅ Backend sync successful`
3. Player 2 (Dante) opens Activities
4. Check Xcode logs on Dante's device - should see `🎮 Backend has data, updating from backend`
5. Verify Dante sees the game with updated score

### Temporary Workaround:
Currently games only sync when:
- Backend has data AND
- User opens Activities view

**Not real-time** - requires app restart/view refresh to see opponent's games.

---

## Related Issues:
- Backend sync initially overwrote local data with zeros (FIXED)
- League promotions now show correctly with 2-second delay (FIXED)
- Reset button now preserves other activities correctly (FIXED)
