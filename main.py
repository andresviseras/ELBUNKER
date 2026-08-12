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
                    escenario_elegido = msg.get("escenario")
                    await game.broadcast({"type": "game_starting"})
                    await generate_and_distribute_roles(list(game.active_players.keys()), escenario_elegido)

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

async def generate_and_distribute_roles(players: list, escenario_actual: str):
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

    """escenarios = [
        "Ha ocurrido un evento apocalíptico masivo. El grupo ha encontrado un refugio seguro, pero el búnker es muy pequeño y no hay espacio para todos. Solo la mitad exacta del grupo podrá cruzar las puertas.",
        "Un invierno nuclear. El sistema de filtrado de aire está gravemente dañado y solo puede depurar el CO2 para mantener viva a la mitad del grupo; si entra una persona más, moriréis asfixiados.",
        "Una pandemia de un virus zombificador. Las reservas de raciones y supresores de infección limitan la supervivencia a exactamente la mitad del grupo.",
        "Una rebelión de inteligencias artificiales. El generador del viejo búnker es débil y colapsará si detecta el peso y calor de más de la mitad de vosotros.",
        "Un colapso ecológico sin agua. El destilador está al límite de su capacidad y el agua reciclada solo da para hidratar a la mitad del grupo sin provocar fallos renales.",
    ]
    escenario_actual = random.choice(escenarios)
"""
    prompt = f"""
    Eres el Game Master implacable de un juego de deducción social y supervivencia extrema. 
    El escenario actual de crisis es: {escenario_actual}.
    Los jugadores son: {', '.join(players)}.
    REGLA DE ORO: Matemáticamente, solo la mitad exacta de estos jugadores puede sobrevivir en el búnker. (IMPORTANTE: Si el número total de jugadores es impar, redondea la cifra obligatoriamente hacia abajo.)

    Tu objetivo es generar un debate brutal, estratégico y lleno de paranoia. Diseña los roles aplicando esta lógica de juego:

    1. HABILIDADES CONCISAS Y DIRECTAS: Todos los roles deben aportar beneficios físicos y críticos claros, pero sin florituras. Cero relleno literario. Directo al grano.
    2. DEFECTOS FUTUROS (EL PELIGRO LATENTE): Los defectos NO deben ser cosas que ya han pasado. Deben ser acciones catastróficas, enfermedades o traiciones que HARÁN o que PASARÁN de forma inevitable UNA VEZ estén dentro del búnker (ej. "Si te dejan entrar, sabotearás...", "Cuando lleves un mes dentro, te volverás loco y..."). IMPORTANTE: Desvincula la utilidad de la gravedad. Un rol vital puede tener un defecto inofensivo, y un rol mediocre puede ser la mayor amenaza. ¡Rompe los patrones! Vincula la gravedad de manera impredecible, siempre aleatorio. PROHIBICIÓN ESTRICTA DE CLICHÉS: No uses 'brotes psicóticos', 'robar medicinas/comida', 'cajas fuertes biométricas' ni 'abrir compuertas a la radiación'. Oblígate a inventar amenazas creativas, bizarras o de ciencia ficción dura.
    3. AL MENOS UN PELIGRO LETAL EXTREMO: Entre todos los jugadores, SIEMPRE debe haber al menos un defecto que sea una amenaza de muerte directa para el grupo (un asesino en serie oculto, un psicópata, un traidor que abrirá las puertas al enemigo, o un infectado en fase terminal).
    4. INTERACCIONES DE NEUTRALIZACIÓN O DETONACIÓN (SOLO OCASIONALES): DE FORMA OCASIONAL (no en todos los jugadores, solo en unos pocos para añadir estrategia), diseña roles para que la habilidad de un jugador interactúe con el defecto de otro. Puede ser para bien o para mal.
        Si decides que la habilidad de un jugador neutraliza el defecto de otro, el MECANISMO EXACTO de esa neutralización DEBE estar escrito explícitamente en el texto de su 'habilidad'. Por ejemplo: si el defecto de A es "robar", la habilidad de B debe mencionar literalmente que "almacena los recursos en una bóveda de contención magnética inexpugnable". No inventes soluciones en el veredicto final que no estén respaldadas palabra por palabra en los textos de los jugadores.
    5. RED DE CHANTAJE CIRCULAR (CERO PAREJAS Y CERO SALVADORES): Está PROHIBIDO cruzar secretos mutuamente (Si A sabe el de B, B no puede saber el de A). Debes crear una cadena de extorsión (A sabe de B, B sabe de C, C sabe de D...). IMPORTANTE: DESVINCULA las neutralizaciones de los secretos. Está ESTRICTAMENTE PROHIBIDO que un jugador reciba el secreto de la misma persona a la que su habilidad puede neutralizar. El conocimiento del defecto y la capacidad de contrarrestarlo deben caer obligatoriamente en jugadores distintos para forzar el chantaje a tres bandas y evitar alianzas fáciles.

    Genera para CADA jugador un rol siguiendo ESTRICTAMENTE estas reglas de formato gramatical y longitud:
    1. 'rol': El título oficial y técnico del cargo (ej. 'Ingeniero de Sistemas').
    2. 'habilidad': PRIMERA PERSONA. CONCISA Y AL GRANO (MÁXIMO 3 ORACIONES). Explica tu utilidad vital y, si corresponde a una neutralización, describe tu herramienta física o mecanismo de seguridad específico. Ni una palabra de más.
    3. 'defecto': SEGUNDA PERSONA. MUY CORTO (1 frase). Redactado en FUTURO o CONDICIONAL sobre lo que harás o te pasará dentro.
    4. 'secreto_de_otro': TERCERA PERSONA. MUY CORTO. Es el 'defecto' de OTRO jugador distinto, respetando estrictamente la cadena circular.

    Finalmente, diseña la SOLUCIÓN IDEAL SECRETA. Elige exactamente a la mitad de los jugadores que conforman la combinación viable real, explicando cómo las interacciones entre ellos neutralizan los peligros o por qué las opciones descartadas eran trampas mortales.

    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin formato markdown ni texto extra al inicio o final:
    {{
      "jugadores": {{
        "NombreJugador1": {{
          "rol": "Título del cargo",
          "habilidad": "Texto en primera persona...",
          "defecto": "Texto en segunda persona en futuro...",
          "secreto_de_otro": "Texto en tercera persona..."
        }}
      }},
      "veredicto_ia": {{
        "supervivientes_ideales": ["Nombre1", "Nombre2"],
        "explicacion": "Explicación detallada de la solución."
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
                "escenario": escenario_actual,
                "data": role_data
            })
    except Exception as e:
        print("Error en IA:", e)
        await game.broadcast({"type": "error", "message": "Fallo en el Game Master. La IA no ha respondido correctamente, intentadlo de nuevo."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
