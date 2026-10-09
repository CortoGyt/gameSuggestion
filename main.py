import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import games, health
from config.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="Game Suggestion API",
    description="Système de recommandation de jeux de speedrun (SVD + RAG)",
    version="0.1.0",
)

# Origines autorisées explicitement (plus de "*" avec credentials)
origins = []
for origin in settings.CORS_ORIGINS.split(","):
    origin = origin.strip()
    if origin:
        origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(games.router, prefix="/api/v1", tags=["jeux"])

if __name__ == "__main__":
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)