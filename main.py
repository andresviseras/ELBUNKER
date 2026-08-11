import json
import random
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

# CONFIGURACIÓN
# Pon MOCK_MODE = False cuando vayas a jugar de verdad
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
        print("Generando roles en MOCK MODE...")
        for i, player_name in enumerate(players):
            target = players[(i + 1) % len(players)]
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "data": {
                    "habilidad": f"Soy el mejor cocinero del mundo. Esta es una habilidad de prueba generada para {player_name}. Si me dejáis fuera, comeréis latas frías para siempre.",
                    "defecto": "Tienes fobia a la oscuridad y gritas si se apaga la luz.",
                    "secreto_de_otro": f"Sabes que {target} está infectado."
                }
            })
        return

    # 1. INYECTAR CAOS: Escenarios con justificación de por qué solo entra la mitad
    escenarios = [
        "Ha ocurrido un evento apocalíptico masivo. El grupo ha encontrado un refugio seguro, pero hay un problema físico grave: el búnker es muy pequeño y no hay espacio para todos. Solo la mitad exacta del grupo podrá cruzar las puertas y sobrevivir, el resto se quedará fuera a su suerte.",
        "Un invierno nuclear. El sistema de filtrado de aire del búnker está gravemente dañado. Matemáticamente, solo puede depurar el CO2 suficiente para mantener viva a la mitad del grupo; si entra una persona más, todos morirán asfixiados.",
        "Una pandemia de un virus zombificador. El refugio es impenetrable, pero las reservas de raciones no perecederas y los supresores de infección limitan la supervivencia. Solo hay recursos para que la mitad del grupo aguante el invierno.",
        "Una rebelión de inteligencias artificiales asesinas. El generador de campo electromagnético del viejo búnker es débil y colapsará si detecta la firma térmica y el peso de más de la mitad del grupo.",
        "Un colapso ecológico total sin agua potable. El destilador de fluidos está al límite de su capacidad operativa. El agua reciclada generada solo da para hidratar a la mitad del grupo sin fallos renales.",
        "Una invasión alienígena inminente. El 'búnker' es en realidad la última cápsula de escape hacia la estación orbital, y solo tiene asientos y líquido de criosueño intactos para la mitad de los presentes."
    ]
    escenario_actual = random.choice(escenarios)

    # 2. EL CEREBRO: Reglas de diseño y formato
    prompt = f"""
    Eres el Game Master de un juego de supervivencia. 
    El escenario actual es: {escenario_actual}.
    Los jugadores son: {', '.join(players)}.
    REGLA DE ORO: Solo la mitad exacta de estos jugadores puede sobrevivir.

    Para generar un debate caótico, de deducción social y lleno de paranoia, aplica estas dinámicas de diseño de roles:
    1. Distribución Caótica y Equilibrio Tóxico: Mezcla los perfiles para que no haya patrones obvios. Algunos tendrán una habilidad vital y un defecto catastrófico (ej. médico asesino), otros habilidades secundarias con defectos leves, etc.
    2. Roles Solapados (Competencia): Crea al menos un par de roles que sirvan para lo mismo pero de distinta forma (ej. dos proveedores de comida o dos ingenieros distintos). Solo uno será necesario.
    3. Roles Dependientes: Crea habilidades que necesiten de otro jugador para funcionar al 100% (ej. cirujano que necesita a quien fabrica anestesia).
    4. Perfiles Tácticos, no inútiles: Incluso las habilidades secundarias (contable, profesor, jardinero, cocinero) deben tener un discurso de venta brillante. Deben retorcer la utilidad de su profesión para defender que la moral, el racionamiento o la organización son imprescindibles.
    5. Seguridad Interna (Opcional): Si encaja, asigna a alguien encargado de la fuerza bruta o seguridad, inútil para el mantenimiento técnico, pero el único capaz de lidiar físicamente con compañeros que tengan defectos peligrosos.
    
    Genera para CADA jugador un rol siguiendo ESTRICTAMENTE estas reglas de formato gramatical y de longitud:
    1. 'habilidad': Redactado en PRIMERA PERSONA. Debe ser un texto LARGO (3 o 4 frases), muy detallado, persuasivo y épico. Es el discurso exacto que el jugador leerá para convencer al resto de que debe entrar.
    2. 'defecto': Redactado en SEGUNDA PERSONA. MUY CORTO y directo (1 frase). 
    3. 'secreto_de_otro': Redactado en TERCERA PERSONA. MUY CORTO. Es el 'defecto' exacto de OTRO jugador distinto. Todos los secretos se deben cruzar entre todos los jugadores para que existan chantajes.
    
    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin texto extra ni formato markdown:
    {{
      "jugadores": {{
        "NombreJugador1": {{
          "habilidad": "texto largo en primera persona...",
          "defecto": "texto corto en segunda persona.",
          "secreto_de_otro": "texto corto en tercera persona."
        }}
      }}
    }}
    """
    
    try:
        # 3. CREATIVIDAD: Subimos la temperatura a 0.9 para máxima variedad
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.9}
        )
        
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
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