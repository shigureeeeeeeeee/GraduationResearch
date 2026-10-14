import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from schemas import PromptsConfig
from ventilation_content import public_config
from ventilation_engine import simulate
from ventilation_models import AdviceRequest, SessionLog, SimulationRequest
import ventilation_service as service

router = APIRouter(prefix="/api/ventilation", tags=["ventilation"])


@router.get("/config")
def config():
    return public_config()


@router.post("/simulate")
def run_simulation(req: SimulationRequest):
    return simulate(req.program, req.steps, req.task_id, req.baseline)


@router.post("/advice")
def advice(req: AdviceRequest):
    return service.generate_advice(req)


@router.post("/group-discussion/stream")
def discussion(req: AdviceRequest):
    def stream():
        for turn in service.generate_discussion(req):
            yield json.dumps(turn, ensure_ascii=False) + "\n"
    # A sync iterator is consumed in a worker thread, so slow local LLM calls
    # do not block simulations or health checks on the event loop.
    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/config/prompts")
def get_prompts():
    return service.get_prompts()


@router.post("/config/prompts")
def save_prompts(config: PromptsConfig):
    service.save_prompts(config)
    return {"status": "ok"}


@router.post("/config/prompts/reset")
def reset_prompts():
    service.reset_prompts()
    return {"status": "ok"}


@router.post("/log")
def save_log(entry: SessionLog):
    record = service.append_log(entry)
    return {"status": "ok", "timestamp": record["timestamp"]}


@router.get("/log/export")
def export_logs():
    return service.read_logs()
