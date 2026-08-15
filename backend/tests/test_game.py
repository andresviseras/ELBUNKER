import pytest
from app.game.engine import BunkerEngine

def test_connect_first_player_becomes_host():
    """Prueba que el primer jugador en entrar recibe el rol de anfitrión."""
    game = BunkerEngine()
    player = game.connect_player("Andrés")
    
    assert player.name == "Andrés"
    assert player.is_connected is True
    assert game.host == "Andrés"
    assert "Andrés" in game.active_player_names

def test_disconnect_player_reassigns_host():
    """Prueba que si el anfitrión se desconecta, el control pasa a otro jugador."""
    game = BunkerEngine()
    game.connect_player("Andrés")
    game.connect_player("Aina")
    
    # Andrés es el host inicial
    assert game.host == "Andrés"
    
    # Simulamos que Andrés pierde la conexión
    game.disconnect_player("Andrés")
    
    # El estado del jugador cambia, pero no se borra de la memoria
    assert game.players["Andrés"].is_connected is False
    # Aina asume el control del búnker
    assert game.host == "Aina"

def test_voting_completion():
    """Prueba que el sistema detecta correctamente cuando todos han votado."""
    game = BunkerEngine()
    game.connect_player("Jugador1")
    game.connect_player("Jugador2")
    
    game.start_voting()
    
    is_complete_1 = game.submit_vote("Jugador1", ["Jugador2"])
    assert is_complete_1 is False  # Aún falta uno
    
    is_complete_2 = game.submit_vote("Jugador2", ["Jugador1"])
    assert is_complete_2 is True   # Todos han votado