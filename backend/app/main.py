from fastapi import FastAPI

from app.domains.conversations.router import router as conversations_router

app = FastAPI(
    title="B-gent API",
    version="1.0.0",
    description="B-gent Backend API",
)

app.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])