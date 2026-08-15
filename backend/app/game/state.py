from pydantic import BaseModel
from typing import Optional

class Player(BaseModel):
    """
    Representa el estado y los datos de un jugador en el búnker.
    """
    name: str
    is_connected: bool = True
    role: Optional[str] = None
    
    # En el futuro, si el juego escala, aquí puedes añadir atributos como:
    # votes_received: int = 0
    # is_alive: bool = True