import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

# Importamos el router y la configuración
from app.api.websockets import router as ws_router
from app.core.config import settings

app = FastAPI(title="El Búnker del Caos - API")

# Incluimos las rutas de WebSockets
app.include_router(ws_router)

# Ruta temporal para servir tu index.html.
# Ajusta la ruta del archivo dependiendo de dónde coloques el frontend.
@app.get("/")
async def get_index():
    # Asume que ejecutas el código desde la carpeta /backend
    html_path = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")
    return FileResponse(html_path)

if __name__ == "__main__":
    # settings.PORT usará 8000 en local y el puerto dinámico en Render
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)