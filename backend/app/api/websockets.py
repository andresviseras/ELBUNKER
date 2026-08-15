import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict

# Importamos las piezas que hemos construido
from app.game.engine import game_engine
from app.services.llm_service import generate_and_distribute_roles, generate_final_verdict

router = APIRouter()

# Solo guarda las conexiones de red activas
active_connections: Dict[str, WebSocket] = {}

async def broadcast(message: dict) -> None:
    """Envía un mensaje a todos los jugadores actualmente conectados."""
    for connection in active_connections.values():
        try:
            await connection.send_json(message)
        except Exception:
            pass

async def send_personal(player_name: str, message: dict) -> None:
    """Envía un mensaje privado a un único jugador."""
    if player_name in active_connections:
        try:
            await active_connections[player_name].send_json(message)
        except Exception:
            pass

@router.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await websocket.accept()
    active_connections[player_name] = websocket
    
    # 1. Conectamos al jugador en el motor de juego
    game_engine.connect_player(player_name)
    
    # 2. Lógica de reconexión (le enviamos la pantalla en la que estaba el juego)
    if game_engine.game_phase == "playing" and player_name in game_engine.player_roles:
        await send_personal(player_name, {
            "type": "role_reveal",
            "scenario": game_engine.current_scenario,
            "data": game_engine.player_roles[player_name]
        })
    elif game_engine.game_phase == "voting":
        votes_allowed = game_engine.spots_left_in_tie if game_engine.tie_breaker_active else max(1, len(game_engine.players) // 3)
        candidates_list = game_engine.tied_candidates if game_engine.tie_breaker_active else list(game_engine.players.keys())
        candidates = [{"name": p, "role": game_engine.player_roles[p]["role"]} for p in candidates_list if p in game_engine.player_roles]
        
        await send_personal(player_name, {
            "type": "tie_breaker" if game_engine.tie_breaker_active else "start_voting",
            "candidates": candidates,
            "votes_allowed": votes_allowed,
            "has_voted": player_name in game_engine.votes
        })
    elif game_engine.game_phase == "verdict" and game_engine.final_results:
        await send_personal(player_name, {
            "type": "show_verdict", 
            "data": game_engine.final_results
        })

    # Avisamos a todos de que alguien entró/volvió
    await broadcast({
        "type": "lobby_update", 
        "players": list(game_engine.players.keys()),
        "active_players": game_engine.active_player_names,
        "host": game_engine.host
    })
    
    try:
        while True:
            # 3. Esperamos mensajes del frontend
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")
            
            # --- ACCIONES DEL HOST ---
            if player_name == game_engine.host:
                if action == "start_game":
                    scenario = msg.get("scenario", "Default scenario")
                    language = msg.get("language", "en")
                    
                    # Actualizamos estado en el motor
                    game_engine.start_game(scenario, language)
                    await broadcast({"type": "game_starting"})
                    
                    # Llamamos a Gemini (asíncrono, sin bloquear)
                    ai_data = await generate_and_distribute_roles(
                        game_engine.active_player_names, 
                        scenario, 
                        language
                    )
                    
                    if ai_data:
                        game_engine.set_ai_roles(ai_data.get("players", {}), ai_data.get("ai_verdict", {}))
                        for p_name, role_data in game_engine.player_roles.items():
                            await send_personal(p_name, {
                                "type": "role_reveal",
                                "scenario": scenario,
                                "data": role_data
                            })
                    else:
                        await broadcast({"type": "error", "message": "Fallo en el Game Master de IA."})

                elif action == "start_voting":
                    voting_data = game_engine.start_voting()
                    await broadcast({
                        "type": "start_voting",
                        **voting_data
                    })
            
            # --- ACCIONES DE CUALQUIER JUGADOR ---
            if action == "submit_votes":
                voted_for = msg.get("votes", [])
                
                # El motor registra el voto y nos dice si ya votaron todos
                is_complete = game_engine.submit_vote(player_name, voted_for)
                
                if is_complete:
                    # Todos votaron, el motor calcula el resultado
                    result = game_engine.process_votes()
                    
                    if result["action"] == "tie_breaker":
                        await broadcast({
                            "type": "tie_breaker",
                            "tied_candidates": result["tied_candidates"],
                            "votes_allowed": result["votes_allowed"]
                        })
                    elif result["action"] == "verdict":
                        await broadcast({"type": "generating_verdict"})
                        winners = result["winners"]
                        
                        # Llamamos a Gemini para el final
                        final_data = await generate_final_verdict(
                            game_engine.game_language,
                            game_engine.current_scenario,
                            game_engine.player_roles,
                            game_engine.secret_verdict.get("ideal_survivors", []),
                            winners
                        )
                        
                        if final_data:
                            final_data["player_survivors"] = winners
                            game_engine.final_results = final_data
                            game_engine.game_phase = "verdict"
                            await broadcast({"type": "show_verdict", "data": final_data})
                        else:
                            await broadcast({"type": "error", "message": "Fallo al generar el veredicto final."})
                else:
                    # Faltan votos, actualizamos contador
                    await broadcast({
                        "type": "vote_update", 
                        "voted_count": len(game_engine.votes), 
                        "total": len(game_engine.players)
                    })

    except WebSocketDisconnect:
        # 4. Manejo de desconexiones
        if player_name in active_connections:
            del active_connections[player_name]
            
        game_engine.disconnect_player(player_name)
        
        await broadcast({
            "type": "lobby_update", 
            "players": list(game_engine.players.keys()),
            "active_players": game_engine.active_player_names,
            "host": game_engine.host
        })