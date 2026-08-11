import json
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

# CONFIGURACIÓN 
# MOCK_MODE en True no gasta créditos y responde al instante (para probar la web)
# Ponlo en False cuando vayas a jugar de verdad.
MOCK_MODE = True
genai.configure(api_key="TU_API_KEY_AQUI")
model = genai.GenerativeModel('gemini-1.5-flash')

app = FastAPI()

class GameManager:
    def __init__(self):
        self.active_players: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, name: str):
        await websocket.accept()
        self.active_players[name] = websocket

    def disconnect(self, name: str):
        if name in self.active_players:
            del self.active_players[name]

    async def broadcast(self, message: dict):
        for connection in self.active_players.values():
            await connection.send_json(message)

    async def send_personal(self, name: str, message: dict):
        if name in self.active_players:
            await self.active_players[name].send_json(message)

game = GameManager()

@app.get("/")
async def get_index():
    return FileResponse("index.html")

@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await game.connect(websocket, player_name)
    
    players_list = list(game.active_players.keys())
    await game.broadcast({"type": "lobby_update", "players": players_list})
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("action") == "start_game":
                await game.broadcast({"type": "game_starting"})
                await generate_and_distribute_roles(list(game.active_players.keys()))
                
    except WebSocketDisconnect:
        game.disconnect(player_name)
        await game.broadcast({"type": "lobby_update", "players": list(game.active_players.keys())})

async def generate_and_distribute_roles(players: list):
    if len(players) < 2:
        return
        
    # MODO PRUEBAS: Datos falsos sin gastar API
    if MOCK_MODE:
        for i, player_name in enumerate(players):
            target = players[(i + 1) % len(players)]
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "data": {
                    "habilidad": f"Cocinero experto (Habilidad de prueba para {player_name})",
                    "defecto": "Te robas la comida mientras todos duermen.",
                    "secreto_de_otro": f"Sabes que {target} está infectado."
                }
            })
        return

    # MODO REAL: Llama a Gemini
    prompt = f"""
    Eres el Game Master de un juego de supervivencia en un búnker. 
    Solo la mitad sobrevivirá. 
    Los jugadores son: {', '.join(players)}.
    
    Genera para CADA jugador:
    1. Una 'habilidad' vital (trabajo o capacidad imprescindible).
    2. Un 'defecto' fatal oculto (rasgo oscuro o problema grave).
    3. Un 'secreto' que conoce: el defecto fatal de OTRO jugador distinto. Asegurate que los secretos se crucen entre ellos y nadie tenga su propio secreto.
    
    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin texto extra ni formato markdown:
    {{
      "jugadores": {{
        "NombreJugador1": {{
          "habilidad": "texto",
          "defecto": "texto",
          "secreto_de_otro": "Sabes que NombreJugador2 hace X..."
        }}
      }}
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        for player_name, role_data in data["jugadores"].items():
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "data": role_data
            })
    except Exception as e:
        print("Error en IA:", e)
        await game.broadcast({"type": "error", "message": "Fallo en la matriz. Intentadlo de nuevo."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)