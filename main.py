import os
import json
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from typing import Dict, List, Optional
from google import genai
from google.genai import types

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass 

MOCK_MODE = False

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

app = FastAPI()

class GameManager:
    def __init__(self):
        self.active_players: Dict[str, WebSocket] = {}
        self.host: Optional[str] = None
        
        # State management variables
        self.game_phase: str = "lobby"
        self.player_roles: Dict[str, Dict] = {}
        self.current_scenario: str = ""
        self.game_language: str = "en"
        
        # Voting system variables
        self.votes: Dict[str, List[str]] = {}
        self.tie_breaker_active: bool = False
        self.tied_candidates: List[str] = []
        self.survivors_so_far: List[str] = []
        self.spots_left_in_tie: int = 0
        
        # Verdict variables
        self.secret_verdict: Optional[Dict] = None
        self.final_results: Optional[Dict] = None

    async def connect(self, websocket: WebSocket, name: str) -> None:
        await websocket.accept()
        self.active_players[name] = websocket
        if not self.host:
            self.host = name

    def disconnect(self, name: str) -> None:
        if name in self.active_players:
            del self.active_players[name]
        if name == self.host:
            self.host = list(self.active_players.keys())[0] if self.active_players else None

    async def broadcast(self, message: dict) -> None:
        for connection in self.active_players.values():
            try:
                await connection.send_json(message)
            except Exception:
                pass

    async def send_personal(self, name: str, message: dict) -> None:
        if name in self.active_players:
            try:
                await self.active_players[name].send_json(message)
            except Exception:
                pass

    async def process_votes(self) -> None:
        """Counts votes, handles tie-breakers, and resolves stalemates randomly if necessary."""
        # Initialize all players with 0 votes to guarantee they appear in the ranking
        vote_counts = {p: 0 for p in self.active_players.keys()}
        for voter, votes in self.votes.items():
            for vote in votes:
                if vote in vote_counts:
                    vote_counts[vote] += 1
                    
        required_survivors = len(self.active_players) // 2
        
        if self.tie_breaker_active:
            # Filter the votes to count only those for the tied candidates
            tie_vote_counts = {p: vote_counts.get(p, 0) for p in self.tied_candidates}
            sorted_tie = sorted(tie_vote_counts.items(), key=lambda x: x[1], reverse=True)
            
            score_at_cutoff = sorted_tie[self.spots_left_in_tie - 1][1]
            winners_this_round = [c[0] for c in sorted_tie if c[1] > score_at_cutoff]
            new_tied = [c[0] for c in sorted_tie if c[1] == score_at_cutoff]
            
            self.survivors_so_far.extend(winners_this_round)
            remaining_spots = self.spots_left_in_tie - len(winners_this_round)
            
            # Resolve second tie via randomness
            if remaining_spots > 0 and len(new_tied) > remaining_spots:
                random_winners = random.sample(new_tied, remaining_spots)
                self.survivors_so_far.extend(random_winners)
            elif remaining_spots > 0 and len(new_tied) == remaining_spots:
                self.survivors_so_far.extend(new_tied)
                
            await generate_final_verdict(self.survivors_so_far)
            return

        # Normal Phase Counting
        sorted_candidates = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        score_at_cutoff = sorted_candidates[required_survivors - 1][1]
        
        winners = [c[0] for c in sorted_candidates if c[1] > score_at_cutoff]
        tied = [c[0] for c in sorted_candidates if c[1] == score_at_cutoff]
        
        remaining_spots = required_survivors - len(winners)
        
        if len(tied) > remaining_spots:
            # Activate Tie-Breaker Phase
            self.tie_breaker_active = True
            self.tied_candidates = tied
            self.survivors_so_far = winners
            self.spots_left_in_tie = remaining_spots
            self.votes = {} 
            
            await self.broadcast({
                "type": "tie_breaker",
                "tied_candidates": [{"name": p, "role": self.player_roles[p]["role"]} for p in tied],
                "votes_allowed": remaining_spots
            })
        else:
            # Direct victory without ties
            winners.extend(tied)
            await generate_final_verdict(winners)


game = GameManager()

@app.get("/")
async def get_index():
    return FileResponse("index.html")

@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await game.connect(websocket, player_name)
    
    # Reconnection handling logic based on phases
    if game.game_phase == "playing" and player_name in game.player_roles:
        await game.send_personal(player_name, {
            "type": "role_reveal",
            "scenario": game.current_scenario,
            "data": game.player_roles[player_name]
        })
    elif game.game_phase == "voting":
        votes_allowed = game.spots_left_in_tie if game.tie_breaker_active else max(1, len(game.active_players) // 3)
        candidates_list = game.tied_candidates if game.tie_breaker_active else list(game.active_players.keys())
        candidates = [{"name": p, "role": game.player_roles[p]["role"]} for p in candidates_list if p in game.player_roles]
        
        await game.send_personal(player_name, {
            "type": "tie_breaker" if game.tie_breaker_active else "start_voting",
            "candidates": candidates,
            "votes_allowed": votes_allowed,
            "has_voted": player_name in game.votes
        })
    elif game.game_phase == "verdict" and game.final_results:
        await game.send_personal(player_name, {
            "type": "show_verdict", 
            "data": game.final_results
        })
    
    await game.broadcast({
        "type": "lobby_update", 
        "players": list(game.active_players.keys()),
        "host": game.host
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            # --- HOST ACTIONS ---
            if player_name == game.host:
                if msg.get("action") == "start_game":
                    game.current_scenario = msg.get("scenario", "Default scenario")
                    game.game_language = msg.get("language", "en")
                    game.game_phase = "playing"
                    
                    await game.broadcast({"type": "game_starting"})
                    await generate_and_distribute_roles(
                        list(game.active_players.keys()), 
                        game.current_scenario, 
                        game.game_language
                    )

                if msg.get("action") == "start_voting":
                    game.game_phase = "voting"
                    game.votes = {}
                    game.tie_breaker_active = False
                    
                    # 1/3 of players logic (Minimum 1 vote)
                    votes_allowed = max(1, len(game.active_players) // 3)
                    candidates = [{"name": p, "role": game.player_roles[p]["role"]} for p in game.active_players if p in game.player_roles]
                    
                    await game.broadcast({
                        "type": "start_voting",
                        "candidates": candidates,
                        "votes_allowed": votes_allowed
                    })
            
            # --- PLAYER ACTIONS ---
            if msg.get("action") == "submit_votes":
                voted_for = msg.get("votes", [])
                
                # Prevent cheating / self-voting
                if player_name in voted_for:
                    voted_for.remove(player_name)
                    
                game.votes[player_name] = voted_for
                
                # Trigger counting if everyone has voted
                if len(game.votes) >= len(game.active_players):
                    await game.process_votes()
                else:
                    await game.broadcast({
                        "type": "vote_update", 
                        "voted_count": len(game.votes), 
                        "total": len(game.active_players)
                    })
                
    except WebSocketDisconnect:
        game.disconnect(player_name)
        await game.broadcast({
            "type": "lobby_update", 
            "players": list(game.active_players.keys()),
            "host": game.host
        })

async def generate_and_distribute_roles(players: List[str], current_scenario: str, language: str) -> None:
    if len(players) < 2:
        return
        
    if MOCK_MODE or not client:
        game.secret_verdict = {
            "ideal_survivors": [players[0], players[1]] if len(players) >= 2 else players,
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
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
            )
        )
        
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        game.secret_verdict = data.get("ai_verdict")
        game.player_roles = data.get("players", {})
        
        for player_name, role_data in game.player_roles.items():
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "scenario": current_scenario,
                "data": role_data
            })
    except Exception as e:
        print("AI Error (Roles):", e)
        await game.broadcast({"type": "error", "message": "Game Master failure. The AI did not respond correctly, please try again."})

async def generate_final_verdict(chosen_survivors: List[str]) -> None:
    """Uses LLM Memory to evaluate the players' voted team against the AI's original ideal team."""
    game.game_phase = "verdict"
    await game.broadcast({"type": "generating_verdict"})
    
    if MOCK_MODE or not client:
        final_data = {
            "player_survivors": chosen_survivors,
            "player_outcome": "The players died horribly because this is a mock mode outcome.",
            "ai_smackdown": "I told you so. My team was statistically flawless.",
            "ai_ideal_survivors": game.secret_verdict["ideal_survivors"] if game.secret_verdict else [],
            "ai_explanation": game.secret_verdict["explanation"] if game.secret_verdict else ""
        }
        game.final_results = final_data
        await game.broadcast({"type": "show_verdict", "data": final_data})
        return

    prompt = f"""
    LANGUAGE REQUIREMENT: You MUST generate all output entirely in this language: {game.game_language}.
    
    You are the Game Master. 
    Scenario: {game.current_scenario}
    Players and Roles: {json.dumps(game.player_roles, ensure_ascii=False)}
    Your Original Ideal Team: {game.secret_verdict['ideal_survivors']}
    
    The players ignored your logic. They voted and forced THIS team into the bunker: {chosen_survivors}.
    
    Write a brutally honest, dramatic narrative. 
    1. Explain exactly what happens to the players' chosen team inside the bunker. Detail how their specific flaws ruin their survival. (Or if they somehow survive, make it clear it is a miserable existence).
    2. Arrogantly remind them why YOUR ideal team ({game.secret_verdict['ideal_survivors']}) was the logically superior choice based on their specific skills and flaws.
    
    Return ONLY a valid JSON with this exact structure, with no markdown formatting or extra text:
    {{
      "player_outcome": "Narrative of what happens to the voted team...",
      "ai_smackdown": "Your arrogant explanation of why your original team was better..."
    }}
    """
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.9)
        )
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        final_data = {
            "player_survivors": chosen_survivors,
            "player_outcome": data.get("player_outcome", ""),
            "ai_smackdown": data.get("ai_smackdown", ""),
            "ai_ideal_survivors": game.secret_verdict["ideal_survivors"],
            "ai_explanation": game.secret_verdict["explanation"]
        }
        
        # Save final state for reconnections
        game.final_results = final_data
        await game.broadcast({"type": "show_verdict", "data": final_data})
        
    except Exception as e:
        print("AI Error (Verdict):", e)
        await game.broadcast({"type": "error", "message": "Failed to generate the final outcome narrative."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)