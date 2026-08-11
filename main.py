import json
import random
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

# CONFIGURACIÓN
# Pon MOCK_MODE = False cuando subas el juego de verdad
MOCK_MODE = False
genai.configure(api_key="TU_API_KEY_AQUI")
model = genai.GenerativeModel('gemini-1.5-flash')

app = FastAPI()

class GameManager:
    def __init__(self):
        self.active_players: dict[str, WebSocket] = {}
        self.host: str = None  # El líder de la sala
        self.veredicto_secreto = None

    async def connect(self, websocket: WebSocket, name: str):
        await websocket.accept()
        self.active_players[name] = websocket
        
        # El primero en entrar se convierte en el host
        if not self.host:
            self.host = name

    def disconnect(self, name: str):
        if name in self.active_players:
            del self.active_players[name]
        
        # Si el host se desconecta, pasamos el liderazgo al siguiente (si hay)
        if name == self.host:
            if self.active_players:
                self.host = list(self.active_players.keys())[0]
            else:
                self.host = None

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
    
    # Enviamos a todos la lista actualizada Y quién es el host
    await game.broadcast({
        "type": "lobby_update", 
        "players": list(game.active_players.keys()),
        "host": game.host
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            # Solo el host puede ejecutar las acciones de control
            if player_name == game.host:
                if msg.get("action") == "start_game":
                    await game.broadcast({"type": "game_starting"})
                    await generate_and_distribute_roles(list(game.active_players.keys()))
                    
                if msg.get("action") == "reveal_verdict":
                    if game.veredicto_secreto:
                        await game.broadcast({
                            "type": "show_verdict", 
                            "data": game.veredicto_secreto
                        })
                
    except WebSocketDisconnect:
        game.disconnect(player_name)
        await game.broadcast({
            "type": "lobby_update", 
            "players": list(game.active_players.keys()),
            "host": game.host
        })

async def generate_and_distribute_roles(players: list):
    if len(players) < 2:
        return
        
    if MOCK_MODE:
        print("Generando roles en MOCK MODE...")
        game.veredicto_secreto = {
            "supervivientes_ideales": ["Jugador de Prueba 1", "Jugador de Prueba 2"],
            "explicacion": "Esta es la explicación generada de prueba. El médico debía salvarse y el infectado debía morir."
        }
        for i, player_name in enumerate(players):
            target = players[(i + 1) % len(players)]
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "data": {
                    "habilidad": f"Soy un ingeniero eléctrico vital. (Mock {player_name})",
                    "defecto": "Tienes ataques de pánico.",
                    "secreto_de_otro": f"Sabes que {target} roba comida por la noche."
                }
            })
        return

    escenarios = [
        "Ha ocurrido un evento apocalíptico masivo. El grupo ha encontrado un refugio seguro, pero el búnker es muy pequeño y no hay espacio para todos. Solo la mitad exacta del grupo podrá cruzar las puertas.",
        "Un invierno nuclear. El sistema de filtrado de aire está gravemente dañado y solo puede depurar el CO2 para mantener viva a la mitad del grupo; si entra una persona más, moriréis asfixiados.",
        "Una pandemia de un virus zombificador. Las reservas de raciones y supresores de infección limitan la supervivencia a exactamente la mitad del grupo.",
        "Una rebelión de inteligencias artificiales. El generador del viejo búnker es débil y colapsará si detecta el peso y calor de más de la mitad de vosotros.",
        "Un colapso ecológico sin agua. El destilador está al límite de su capacidad y el agua reciclada solo da para hidratar a la mitad del grupo sin provocar fallos renales.",
        "Una invasión alienígena inminente. El refugio es en realidad la última cápsula de escape orbital, y solo tiene líquido de criosueño para la mitad."
    ]
    escenario_actual = random.choice(escenarios)

    prompt = f"""
    Eres el Game Master de un juego de supervivencia. 
    El escenario actual es: {escenario_actual}.
    Los jugadores son: {', '.join(players)}.
    REGLA DE ORO: Solo la mitad exacta de estos jugadores puede sobrevivir.

    Aplica estas dinámicas de diseño de roles:
    1. Distribución Caótica y Equilibrio Tóxico: Mezcla perfiles. Algunos tendrán habilidad vital y defecto catastrófico, otros habilidades secundarias con defectos leves.
    2. Roles Solapados (Competencia): Crea roles que sirvan para lo mismo pero de distinta forma (ej. dos proveedores de recursos distintos).
    3. Roles Dependientes: Crea habilidades que necesiten de otro jugador para funcionar.
    4. Perfiles Tácticos: Las habilidades secundarias (contable, profesor, jardinero) deben tener un discurso de venta brillante.
    5. Seguridad Interna: Si encaja, asigna a alguien encargado de la fuerza física, el único capaz de lidiar con compañeros peligrosos.
    
    Genera para CADA jugador un rol siguiendo ESTRICTAMENTE estas reglas:
    1. 'habilidad': PRIMERA PERSONA. LARGO (3 o 4 frases), muy detallado y persuasivo.
    2. 'defecto': SEGUNDA PERSONA. MUY CORTO y directo (1 frase). 
    3. 'secreto_de_otro': TERCERA PERSONA. MUY CORTO. Es el 'defecto' de OTRO jugador distinto. (Cruza todos los secretos).
    
    Además, diseña la SOLUCIÓN IDEAL eligiendo exactamente a la mitad de los jugadores que garantizan la supervivencia a largo plazo.

    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin texto extra ni formato markdown:
    {{
      "jugadores": {{
        "NombreJugador1": {{
          "habilidad": "texto largo en primera persona...",
          "defecto": "texto corto en segunda persona...",
          "secreto_de_otro": "texto corto en tercera persona..."
        }}
      }},
      "veredicto_ia": {{
        "supervivientes_ideales": ["Nombre1", "Nombre2"],
        "explicacion": "Una justificación dramática y detallada de por qué esta combinación era la correcta."
      }}
    }}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.9})
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        # Guardamos la solución correcta en la memoria del servidor
        game.veredicto_secreto = data.get("veredicto_ia")
        
        for player_name, role_data in data["jugadores"].items():
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "data": role_data
            })
    except Exception as e:
        print("Error en IA:", e)
        await game.broadcast({"type": "error", "message": "Fallo en el Game Master. Intentadlo de nuevo."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)