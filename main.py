import os
import json
import random
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from typing import Dict, List, Optional
# Make sure to run: pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # In production (Render), if dotenv is missing, it will gracefully ignore this 
    # and read directly from the Render Environment Variables dashboard.
    pass 

# CONFIGURATION
# Set to True ONLY for local testing without using API quota.
# Keep as False for production deployment.
MOCK_MODE = False

# Security: Read the key from environment variables
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key and not MOCK_MODE:
    print("WARNING: GEMINI_API_KEY is missing!")

genai.configure(api_key=api_key)

# Using the recommended model for complex reasoning
model = genai.GenerativeModel('gemini-3.5-flash') # Updated to a standard naming convention if applicable, or keep 3.5 if using preview

app = FastAPI()

class GameManager:
    """
    Manages WebSocket connections, game state, and player sessions.
    """
    def __init__(self):
        self.active_players: Dict[str, WebSocket] = {}
        self.host: Optional[str] = None
        self.secret_verdict: Optional[Dict] = None
        
        # State management for reconnections
        self.game_phase: str = "lobby"  # Phases: 'lobby', 'playing', 'verdict'
        self.player_roles: Dict[str, Dict] = {}
        self.current_scenario: str = ""

    async def connect(self, websocket: WebSocket, name: str) -> None:
        """Accepts a new connection and assigns host if necessary."""
        await websocket.accept()
        self.active_players[name] = websocket
        
        if not self.host:
            self.host = name

    def disconnect(self, name: str) -> None:
        """Removes a player from active connections and reassigns host if needed."""
        if name in self.active_players:
            del self.active_players[name]
        
        if name == self.host:
            self.host = list(self.active_players.keys())[0] if self.active_players else None

    async def broadcast(self, message: dict) -> None:
        """Sends a message to all connected players."""
        for connection in self.active_players.values():
            try:
                await connection.send_json(message)
            except Exception:
                pass # Handle broken pipes silently

    async def send_personal(self, name: str, message: dict) -> None:
        """Sends a message to a specific player."""
        if name in self.active_players:
            try:
                await self.active_players[name].send_json(message)
            except Exception:
                pass


# Initialize the global game manager
game = GameManager()

@app.get("/")
async def get_index():
    return FileResponse("index.html")

@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await game.connect(websocket, player_name)
    
    # RECONNECTION LOGIC: Check if game is already running
    if game.game_phase == "playing" and player_name in game.player_roles:
        await game.send_personal(player_name, {
            "type": "role_reveal",
            "scenario": game.current_scenario,
            "data": game.player_roles[player_name]
        })
    elif game.game_phase == "verdict" and game.secret_verdict:
        await game.send_personal(player_name, {
            "type": "show_verdict", 
            "data": game.secret_verdict
        })
    
    # Always update the lobby for everyone
    await game.broadcast({
        "type": "lobby_update", 
        "players": list(game.active_players.keys()),
        "host": game.host
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            # Restrict game control actions to the host
            if player_name == game.host:
                if msg.get("action") == "start_game":
                    chosen_scenario = msg.get("scenario", "Default scenario")
                    game_language = msg.get("language", "en") # Receives language from frontend
                    
                    game.current_scenario = chosen_scenario
                    game.game_phase = "playing"
                    
                    await game.broadcast({"type": "game_starting"})
                    await generate_and_distribute_roles(
                        list(game.active_players.keys()), 
                        chosen_scenario, 
                        game_language
                    )

                if msg.get("action") == "reveal_verdict":
                    if game.secret_verdict:
                        game.game_phase = "verdict"
                        await game.broadcast({
                            "type": "show_verdict", 
                            "data": game.secret_verdict
                        })
                
    except WebSocketDisconnect:
        game.disconnect(player_name)
        await game.broadcast({
            "type": "lobby_update", 
            "players": list(game.active_players.keys()),
            "host": game.host
        })

async def generate_and_distribute_roles(players: List[str], current_scenario: str, language: str) -> None:
    """
    Calls the Gemini API to generate roles based on the scenario and language,
    then distributes them to the active players.
    """
    if len(players) < 2:
        return
        
    if MOCK_MODE:
        print(f"Generating roles in MOCK MODE... (Language: {language})")
        game.secret_verdict = {
            "ideal_survivors": [players[0], players[1]],
            "explanation": "This is a mock explanation. The winning strategy was A."
        }
        game.player_roles = {}
        for i, player_name in enumerate(players):
            target = players[(i + 1) % len(players)]
            role_data = {
                "role": "Test Specialist",
                "skill": f"I know exactly how to run the bunker. (Mock {player_name})",
                "flaw": "You have sudden panic attacks.",
                "secret_of_another": f"You know that {target} steals water at night."
            }
            game.player_roles[player_name] = role_data
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "scenario": current_scenario,
                "data": role_data
            })
        return

    # Shuffle players to randomize the secret/flaw chain
    shuffled_players = players.copy()
    random.shuffle(shuffled_players)
    
    prompt = f"""
    LANGUAGE REQUIREMENT: You MUST generate all the output text (roles, skills, flaws, secrets, explanation, and verdict) entirely in this language: {language}.

    You are the ruthless Game Master of a social deduction and extreme survival game. 
    The current crisis scenario is: {current_scenario}.
    The players are: {', '.join(shuffled_players)}.
    GOLDEN RULE: Mathematically, exactly HALF of these players can survive in the bunker. (IMPORTANT: If the total number of players is odd, you MUST round down).

    Your goal is to generate a brutal, strategic, and paranoid debate. Design the roles applying this logic:

    1. REAL UTILITY & HYBRID ROLES: All roles must be vital and unquestionable. FORBIDDEN to invent niche or ultra-specific roles that seem useless on their own. MANDATORY: Encourage HYBRID OR MULTI-DISCIPLINARY ROLES (e.g., a botanist who generates FOOD and purifies OXYGEN). This forces capabilities to overlap, making the group debate who is more expendable. Explain the direct utility without fluff.
    2. FUTURE FLAWS (THE LATENT DANGER): Flaws MUST NOT be things that have already happened. They must be catastrophic actions, diseases, or betrayals that WILL happen once inside the bunker. IMPORTANT: Disconnect utility from severity. STRICT PROHIBITION OF CLICHÉS: Do not limit yourself to 'psychotic breaks', 'stealing medicine', or 'opening the airlock'. Invent creative threats (rare phobias, contagious diseases, political blackmail, sabotage due to panic, etc.).
    3. AT LEAST ONE LETHAL THREAT: Among all players, there MUST ALWAYS be at least one flaw that is a direct death threat to the group (e.g., asymptomatic carrier of a plague, an infiltrated spy, a serial killer).
    4. NEUTRALIZATION INTERACTIONS (OCCASIONAL): OCCASIONALLY, design roles so that one player's skill interacts with another's flaw. If a skill neutralizes a flaw, the EXACT MECHANISM must be explicitly written in the 'skill' text.
    5. CIRCULAR BLACKMAIL NETWORK (NO COUPLES): It is FORBIDDEN to cross secrets mutually (If A knows B's secret, B cannot know A's). You must create a circular extortion chain (A knows B, B knows C, C knows D...). IMPORTANT: Disconnect neutralizations from secrets. A player CANNOT receive the secret of the person their skill neutralizes.

    Generate a role for EACH player strictly following this format:
    1. 'role': The official job title.
    2. 'skill': FIRST PERSON. CONCISE (MAX 3 SHORT SENTENCES). Explain the vital utility.
    3. 'flaw': SECOND PERSON. VERY SHORT (1 sentence). Written in FUTURE or CONDITIONAL tense.
    4. 'secret_of_another': THIRD PERSON. VERY SHORT. Must explicitly include the real name of the player who owns the flaw to maintain the circular chain.

    Finally, design the SECRET IDEAL SOLUTION. Choose exactly half of the players that make up the viable combination. Explain the winning strategy. If the strategy implies long-term survival, the chosen team MUST collectively cover all basic needs.
    
    Return ONLY a valid JSON with this exact structure, with no markdown formatting or extra text:
    {{
      "players": {{
        "PlayerName1": {{
          "role": "Job title",
          "skill": "First person text...",
          "flaw": "Second person future text...",
          "secret_of_another": "Third person text..."
        }}
      }},
      "ai_verdict": {{
        "ideal_survivors": ["Name1", "Name2"],
        "explanation": "Detailed explanation of the solution."
      }}
    }}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.9})
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        # Save state in memory for reconnections
        game.secret_verdict = data.get("ai_verdict")
        game.player_roles = data.get("players", {})
        
        for player_name, role_data in game.player_roles.items():
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "scenario": current_scenario,
                "data": role_data
            })
    except Exception as e:
        print("AI Error:", e)
        await game.broadcast({"type": "error", "message": "Game Master failure. The AI did not respond correctly, please try again."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)