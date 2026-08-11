import os
import json
import random
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

# CONFIGURACIÓN
# Cambia a True SOLO si quieres probar en tu ordenador sin usar la API.
# Déjalo en False para subir a Render.
MOCK_MODE = False

# Sistema de seguridad: lee la clave desde las Variables de Entorno de Render
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# Usamos el modelo más avanzado recomendado para razonamiento complejo
model = genai.GenerativeModel('gemini-3.5-flash')

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
            "explicacion": "Esta es la explicación generada de prueba. La estrategia ganadora era la A."
        }
        for i, player_name in enumerate(players):
            target = players[(i + 1) % len(players)]
            await game.send_personal(player_name, {
                "type": "role_reveal",
                "data": {
                    "rol": "Especialista de Prueba",
                    "habilidad": f"Sé exactamente cómo hacer funcionar el búnker. (Mock {player_name})",
                    "defecto": "Tienes ataques de pánico repentinos.",
                    "secreto_de_otro": f"Sabes que {target} roba raciones de agua por la noche."
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
    Eres el Game Master implacable de un juego de deducción social y supervivencia extrema. 
    El escenario actual de crisis es: {escenario_actual}.
    Los jugadores son: {', '.join(players)}.
    REGLA DE ORO: Matemáticamente, solo la mitad exacta de estos jugadores puede sobrevivir en el búnker.

    Tu objetivo es generar un debate brutal, estratégico y lleno de paranoia. Diseña los roles aplicando esta lógica de juego:

    1. UTILIDAD TANGIBLE Y ESTRATEGIAS DIVERGENTES: Todos los roles deben aportar un beneficio físico y crítico (nada de roles inútiles), pero con distintos grados de prioridad o reemplazabilidad. Sus habilidades deben proponer DIFERENTES estrategias de supervivencia (ej. atrincheramiento agrícola a largo plazo, militarización agresiva, reparaciones para un escape rápido, dependencia tecnológica, etc.). El grupo tendrá que discutir qué plan de supervivencia adoptar.
    2. DEFECTOS ALEATORIOS E IMPREDECIBLES: Rompe cualquier patrón lógico. La gravedad del defecto NO debe depender de lo imprescindible que sea el rol. Un jugador vital puede tener un defecto oscurísimo y catastrófico, o simplemente una fobia ridícula e inofensiva. Genera rarezas y defectos extremos de forma totalmente impredecible.
    3. CHANTAJE ASIMÉTRICO (CLAVE): Para equilibrar los debates, los jugadores con los roles más "prescindibles", de nicho o reemplazables DEBEN ser los que reciban en sus secretos las bombas nucleares (los defectos más graves, oscuros y peligrosos de los jugadores más importantes). Dales a los débiles el conocimiento para extorsionar a los fuertes.
    4. SINERGIAS COMPLICADAS: Crea dependencias cruzadas y combinaciones de roles que parezcan la salvación absoluta, pero que puedan esconder una trampa condicional o mortal si se eligen juntos. Esto no tiene por que suceder siempre.

    Genera para CADA jugador un rol siguiendo ESTRICTAMENTE estas reglas de formato gramatical y longitud:
    1. 'rol': El título oficial y técnico del cargo (ej. 'Ingeniero de Sistemas', 'Especialista en Cultivos', 'Guardia Táctico').
    2. 'habilidad': PRIMERA PERSONA. DIRECTA Y CONTUNDENTE (máximo 2 frases). Simple de entender pero detallando exactamente su aportación TANGIBLE.
    3. 'defecto': SEGUNDA PERSONA. MUY CORTO y directo (1 frase). 
    4. 'secreto_de_otro': TERCERA PERSONA. MUY CORTO. Es el 'defecto' de OTRO jugador distinto. Cruza todos los secretos para tejer la red de extorsión.

    Finalmente, diseña la SOLUCIÓN IDEAL SECRETA. Elige exactamente a la mitad de los jugadores que conforman la combinación viable real, determinando qué estrategia era la ganadora y por qué las demás opciones o sinergias obvias eran trampas mortales.

    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin formato markdown ni texto extra al inicio o final:
    {{
      "jugadores": {{
        "NombreJugador1": {{
          "rol": "Título del cargo",
          "habilidad": "Texto en primera persona...",
          "defecto": "Texto en segunda persona...",
          "secreto_de_otro": "Texto en tercera persona..."
        }}
      }},
      "veredicto_ia": {{
        "supervivientes_ideales": ["Nombre1", "Nombre2"],
        "explicacion": "Justificación de qué estrategia era la correcta y por qué esta combinación de jugadores es la única viable."
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
        await game.broadcast({"type": "error", "message": "Fallo en el Game Master. La IA no ha respondido correctamente, intentadlo de nuevo."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)