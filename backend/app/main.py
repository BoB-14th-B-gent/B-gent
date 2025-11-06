from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.domains.conversations.router import router as conversations_router
from app.domains.messages.router import router as messages_router
from app.domains.triggers.router import router as triggers_router
from app.domains.evidences.router import router as evidences_router
from app.domains.agent.router import router as agent_router

app = FastAPI(title="B-gent API", version="1.0.0", description="B-gent Backend API",)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
app.include_router(messages_router, prefix="/conversations", tags=["Messages"])
app.include_router(triggers_router, prefix="/triggers", tags=["Triggers"])
app.include_router(evidences_router, prefix="/evidences", tags=["Evidences"])
app.include_router(agent_router, prefix="/agent", tags=["Agent"])