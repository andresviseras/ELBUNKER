import random
from typing import Dict, List, Optional, Any
# Importamos el modelo de datos desde el nuevo archivo state.py
from app.game.state import Player

class BunkerEngine:
    def __init__(self):
        # Diccionario para mantener a los jugadores (conectados y desconectados)
        self.players: Dict[str, Player] = {}
        self.host: Optional[str] = None
        
        # Variables de estado del juego
        self.game_phase: str = "lobby"
        self.player_roles: Dict[str, Dict] = {}
        self.current_scenario: str = ""
        self.game_language: str = "en"
        
        # Variables del sistema de votación
        self.votes: Dict[str, List[str]] = {}
        self.tie_breaker_active: bool = False
        self.tied_candidates: List[str] = []
        self.survivors_so_far: List[str] = []
        self.spots_left_in_tie: int = 0
        
        # Variables de veredicto
        self.secret_verdict: Optional[Dict] = None
        self.final_results: Optional[Dict] = None

    @property
    def active_player_names(self) -> List[str]:
        """Devuelve solo los nombres de los jugadores que tienen conexión activa."""
        return [name for name, p in self.players.items() if p.is_connected]

    def connect_player(self, name: str) -> Player:
        """Registra un nuevo jugador o reconecta a uno existente."""
        if name in self.players:
            self.players[name].is_connected = True
        else:
            self.players[name] = Player(name=name)
            
        # Si no hay host, el primero en entrar (o reconectarse) asume el rol
        if not self.host:
            self.host = name
            
        return self.players[name]

    def disconnect_player(self, name: str) -> None:
        """Marca a un jugador como desconectado y reasigna el host si es necesario."""
        if name in self.players:
            self.players[name].is_connected = False
            
        # Si el host se cae, pasamos el control al siguiente jugador activo
        if name == self.host:
            active = self.active_player_names
            self.host = active[0] if active else None

    def start_game(self, scenario: str, language: str) -> None:
        """Configura los datos iniciales de la partida."""
        self.current_scenario = scenario
        self.game_language = language
        self.game_phase = "playing"

    def set_ai_roles(self, roles: Dict[str, Dict], secret_verdict: Dict) -> None:
        """Almacena la configuración generada por el LLM."""
        self.player_roles = roles
        self.secret_verdict = secret_verdict

    def start_voting(self) -> Dict[str, Any]:
        """Prepara el estado para una ronda de votación y devuelve los datos para el frontend."""
        self.game_phase = "voting"
        self.votes = {}
        self.tie_breaker_active = False
        self.tied_candidates = []
        self.survivors_so_far = []
        
        votes_allowed = max(1, len(self.players) // 3)
        return {
            "votes_allowed": votes_allowed,
            "candidates": [{"name": p, "role": self.player_roles[p]["role"]} for p in self.players if p in self.player_roles]
        }

    def submit_vote(self, voter_name: str, voted_for: List[str]) -> bool:
        """
        Registra los votos de un jugador (evitando el autovoto).
        Retorna True si ya han votado todos los jugadores.
        """
        if voter_name in voted_for:
            voted_for.remove(voter_name)
            
        self.votes[voter_name] = voted_for
        
        # Consideramos la votación completa cuando tenemos los votos de todos los registrados
        return len(self.votes) >= len(self.players)

    def process_votes(self) -> Dict[str, Any]:
        """
        Procesa el conteo de votos, maneja desempates y resuelve aleatoriamente si es necesario.
        Retorna un diccionario indicando la siguiente acción que debe ejecutar el router.
        """
        vote_counts = {p: 0 for p in self.players.keys()}
        for voter, votes in self.votes.items():
            for vote in votes:
                if vote in vote_counts:
                    vote_counts[vote] += 1
                    
        required_survivors = len(self.players) // 2
        
        if self.tie_breaker_active:
            # Procesar la ronda de desempate
            tie_vote_counts = {p: vote_counts.get(p, 0) for p in self.tied_candidates}
            sorted_tie = sorted(tie_vote_counts.items(), key=lambda x: x[1], reverse=True)
            
            score_at_cutoff = sorted_tie[self.spots_left_in_tie - 1][1]
            winners_this_round = [c[0] for c in sorted_tie if c[1] > score_at_cutoff]
            new_tied = [c[0] for c in sorted_tie if c[1] == score_at_cutoff]
            
            self.survivors_so_far.extend(winners_this_round)
            remaining_spots = self.spots_left_in_tie - len(winners_this_round)
            
            # Resolver un segundo empate mediante aleatoriedad
            if remaining_spots > 0 and len(new_tied) > remaining_spots:
                random_winners = random.sample(new_tied, remaining_spots)
                self.survivors_so_far.extend(random_winners)
            elif remaining_spots > 0 and len(new_tied) == remaining_spots:
                self.survivors_so_far.extend(new_tied)
                
            return {
                "action": "verdict",
                "winners": self.survivors_so_far
            }

        # Conteo de la fase normal
        sorted_candidates = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        score_at_cutoff = sorted_candidates[required_survivors - 1][1]
        
        winners = [c[0] for c in sorted_candidates if c[1] > score_at_cutoff]
        tied = [c[0] for c in sorted_candidates if c[1] == score_at_cutoff]
        
        remaining_spots = required_survivors - len(winners)
        
        if len(tied) > remaining_spots:
            # Activar fase de desempate
            self.tie_breaker_active = True
            self.tied_candidates = tied
            self.survivors_so_far = winners
            self.spots_left_in_tie = remaining_spots
            self.votes = {} 
            
            return {
                "action": "tie_breaker",
                "tied_candidates": [{"name": p, "role": self.player_roles[p]["role"]} for p in tied],
                "votes_allowed": remaining_spots
            }
        else:
            # Victoria directa sin empates
            winners.extend(tied)
            return {
                "action": "verdict",
                "winners": winners
            }

    def get_full_state(self) -> Dict[str, Any]:
        """
        Genera una 'fotografía' del estado actual.
        Útil para resincronizar clientes tras una reconexión.
        """
        return {
            "game_phase": self.game_phase,
            "host": self.host,
            "players": list(self.players.keys()),
            "active_players": self.active_player_names,
            "tie_breaker_active": self.tie_breaker_active,
            "current_scenario": self.current_scenario
        }

# Instancia global del juego
game_engine = BunkerEngine()