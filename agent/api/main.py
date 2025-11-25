from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .router import router as agent_router

app = FastAPI(title="Agent API", version="1.0.0")

origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router, prefix="/agent", tags=["Agent"])
