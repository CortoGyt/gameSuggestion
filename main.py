from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import recommendations, users, games, ratings, health
import uvicorn

app = FastAPI(
    title="Game Suggestion API",
    description="Système de reccomendation de jeu via un RAG",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(recommendations.router, prefix="/api/v1", tags=["recommendations"])
app.include_router(users.router, prefix="/api/v1", tags=["utilisateur"])
app.include_router(games.router, prefix="/api/v1", tags=["jeux"])
app.include_router(ratings.router, prefix="/api/v1", tags=["note"])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)