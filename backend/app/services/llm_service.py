import json
from google import genai
from google.genai import types
from app.core.config import settings

# Instanciamos el cliente con la API key centralizada
client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

async def generate_and_distribute_roles(players: list[str], current_scenario: str, language: str) -> dict:
    """
    Se comunica con Gemini para generar los roles de forma asíncrona.
    Retorna el diccionario con los datos o None si falla.
    """
    if not client:
        return None

    prompt = f"""
    LANGUAGE REQUIREMENT: You MUST generate all the output text entirely in this language: {language}.
    You are the ruthless Game Master of a social deduction and extreme survival game. 
    The current crisis scenario is: {current_scenario}.
    The players are: {', '.join(players)}.
    GOLDEN RULE: Mathematically, exactly HALF of these players can survive in the bunker. (IMPORTANT: If the total number of players is odd, you MUST round down).

    Your goal is to generate a brutal, strategic, and paranoid debate. Design the roles applying this logic:

    1. REAL UTILITY & HYBRID ROLES: All roles must be vital and unquestionable. FORBIDDEN to invent niche or ultra-specific roles that seem useless on their own. MANDATORY: Encourage HYBRID OR MULTI-DISCIPLINARY ROLES (e.g., a botanist who generates FOOD and purifies OXYGEN). This forces capabilities to overlap, making the group debate who is more expendable. Explain the direct utility without fluff.
    2. FUTURE FLAWS (THE LATENT DANGER): Flaws MUST NOT be things that have already happened. They must be catastrophic actions, diseases, or betrayals that WILL happen once inside the bunker. IMPORTANT: Disconnect utility from severity. STRICT PROHIBITION OF CLICHÉS: Do not limit yourself to 'psychotic breaks', 'stealing medicine', or 'opening the airlock'. Invent creative threats (rare phobias, contagious diseases, political blackmail, sabotage due to panic, etc.).
    3. AT LEAST ONE LETHAL THREAT: Among all players, there MUST ALWAYS be at least one flaw that is a direct death threat to the group (e.g., asymptomatic carrier of a plague, an infiltrated spy, a serial killer).
    4. NEUTRALIZATION INTERACTIONS (OCCASIONAL): OCCASIONALLY, design roles so that one player's skill interacts with another's flaw. If a skill neutralizes or detonates a flaw, the EXACT MECHANISM must be explicitly written in the 'skill' text without revealing any secret.
    5. CIRCULAR BLACKMAIL NETWORK (NO COUPLES): It is FORBIDDEN to cross secrets mutually (If A knows B's secret, B cannot know A's). You must create a circular extortion chain (A knows B, B knows C, C knows D...). IMPORTANT: Disconnect neutralizations from secrets. A player CANNOT receive the secret of the person their skill neutralizes.

    Generate a role for EACH player strictly following this format:
    1. 'role': The official job title.
    2. 'skill': FIRST PERSON. CONCISE (MAX 3 SHORT SENTENCES). Explain the vital utility.
    3. 'flaw': SECOND PERSON. VERY SHORT (1 sentence). Written in FUTURE or CONDITIONAL tense.
    4. 'secret_of_another': THIRD PERSON. VERY SHORT. Must explicitly include the real name of the player who owns the flaw to maintain the circular chain.

    Finally, design the SECRET IDEAL SOLUTION. Choose exactly half of the players that make up the viable combination. Explain the winning strategy. If the strategy implies long-term survival, the chosen team MUST collectively cover all basic needs.
    
    CRITICAL FORMATTING RULE: 
    - All text values inside the JSON MUST be written in a single continuous line. 
    - STRICTLY FORBIDDEN: Do NOT use unescaped double quotes, and do NOT use physical line breaks or newline characters (\\n) inside the text strings. Keep every description as a single paragraph.
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
        chat = client.aio.chats.create(
            model='gemini-3.5-flash',
            config=types.GenerateContentConfig(
                temperature=0.9,
                response_mime_type="application/json" 
            )
        )
        response = await chat.send_message(prompt)
        
        raw_json = response.text
        
        # Limpieza de seguridad por si la IA escupe backticks de Markdown
        if raw_json.startswith("```json"):
            raw_json = raw_json.replace("```json", "").replace("```", "").strip()
            
        return json.loads(raw_json)
        
    except json.JSONDecodeError as e:
        # Si la IA rompe el JSON, no crasheamos. Imprimimos el error para debugear.
        print("\n--- ERROR DE SINTAXIS JSON EN LA IA ---")
        print(f"Detalle del error: {e}")
        print(f"Texto crudo devuelto:\n{raw_json}")
        print("---------------------------------------\n")
        return None
    except Exception as e:
        print(f"AI Error general: {e}")
        return None

async def generate_final_verdict(game_language: str, current_scenario: str, player_roles: dict, ideal_survivors: list, chosen_survivors: list) -> dict:
    """
    Genera el veredicto final comparando la decisión de los jugadores con la de la IA.
    """
    if not client:
        return None

    prompt = f"""
    LANGUAGE REQUIREMENT: You MUST generate all output entirely in this language: {game_language}.
    You are the Game Master. 
    Scenario: {current_scenario}
    Players and Roles: {json.dumps(player_roles, ensure_ascii=False)}
    Your Original Ideal Team: {ideal_survivors}
    The players ignored your logic. They voted and forced THIS team into the bunker: {chosen_survivors}.
    
    Write a brutally honest, dramatic narrative. 
    1. Explain exactly what happens to the players' chosen team inside the bunker. Detail how their specific flaws ruin their survival. (Or if they somehow survive, make it clear it is a miserable existence).
    2. Arrogantly remind them why YOUR ideal team ({ideal_survivors}) was the logically superior choice based on their specific skills and flaws.
    
    Return ONLY a valid JSON with this exact structure, with no markdown formatting or extra text:
    {{
      "player_outcome": "Narrative of what happens to the voted team...",
      "ai_smackdown": "Your arrogant explanation of why your original team was better..."
    }}
    """
    
    try:
        # Aplicamos también la corrección aquí
        chat = client.aio.chats.create(
            model='gemini-3.5-flash',
            config=types.GenerateContentConfig(
                temperature=0.9,
                response_mime_type="application/json"
            )
        )
        response = await chat.send_message(prompt)
        
        return json.loads(response.text)
        
    except Exception as e:
        print(f"AI Error (Verdict): {e}")
        return None