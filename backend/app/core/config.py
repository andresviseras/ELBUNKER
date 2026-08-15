from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # La API Key es obligatoria. Si no está en el .env o en Render, la app no arranca.
    GEMINI_API_KEY: str
    
    # Render asigna dinámicamente un puerto a través de esta variable.
    # Le damos 8000 por defecto para que funcione en tu máquina local.
    PORT: int = 8000

    class Config:
        env_file = ".env"
        # Ignora variables extra en el entorno que no hayamos definido aquí
        extra = "ignore" 

# Instanciamos la configuración para importarla desde cualquier parte
settings = Settings()