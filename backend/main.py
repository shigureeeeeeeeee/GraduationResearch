import json

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from discussion import generate_discussion
from llm_service import generate_advice
from prompts import get_prompts
from schemas import AdviceRequest, LogEntry, PromptsConfig
from storage import (
    append_log,
    read_logs,
    reset_prompt_overrides,
    save_prompt_overrides,
)


load_dotenv()

app = FastAPI(title="プログラミング学習支援システム API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/advice")
async def get_advice(req: AdviceRequest):
    return generate_advice(req)


@app.post("/api/group-discussion")
def run_group_discussion(req: AdviceRequest):
    return {"turns": list(generate_discussion(req))}


@app.post("/api/group-discussion/stream")
def stream_group_discussion(req: AdviceRequest):
    async def generate():
        for turn in generate_discussion(req):
            yield json.dumps(turn, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/api/config/prompts")
async def get_prompts_config():
    return get_prompts()


@app.post("/api/config/prompts")
async def update_prompts_config(config: PromptsConfig):
    save_prompt_overrides(config.model_dump())
    return {"status": "ok"}


@app.post("/api/config/prompts/reset")
async def reset_prompts_config():
    reset_prompt_overrides()
    return {"status": "ok", "message": "デフォルトにリセットしました"}


@app.post("/api/log")
async def save_log(entry: LogEntry):
    append_log(entry)
    return {"status": "ok"}


@app.get("/api/log/export")
async def export_log():
    return read_logs()


@app.get("/")
def root():
    return {"status": "ok", "message": "プログラミング学習支援システム API"}
