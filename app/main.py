import os
import time
import json
import threading
import multiprocessing as mp
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Estado global para demo (um job por pod)
STATE = {
    "running": False,
    "started_at": None,
    "ends_at": None,
    "mem_mib": 0,
    "cpu_workers": 0,
    "pid_workers": [],
    "note": "",
    "ticks": 0,
}

# Recursos do job
_mem_blocks: List[bytes] = []
_job_lock = threading.Lock()
_stop_evt_mp: Optional[mp.Event] = None
_procs: List[mp.Process] = []

def cpu_burn(stop_evt: mp.Event):
    x = 0
    while not stop_evt.is_set():
        x = (x * 3 + 1) % 10000019

def allocate_memory(mem_mib: int):
    """
    Aloca em blocos de 1MiB e mantém referência global para não ser coletado.
    """
    global _mem_blocks
    _mem_blocks = []
    block = b"x" * (1024 * 1024)

    for _ in range(mem_mib):
        _mem_blocks.append(block)

    # toca páginas
    for i in range(0, len(_mem_blocks), 64):
        _ = _mem_blocks[i][0]

def _set_state_running(mem_mib: int, cpu_workers: int, seconds: int, procs: List[mp.Process]):
    now = time.time()
    STATE.update({
        "running": True,
        "started_at": now,
        "ends_at": now + seconds,
        "mem_mib": mem_mib,
        "cpu_workers": cpu_workers,
        "pid_workers": [p.pid for p in procs],
        "note": "",
        "ticks": 0,
    })

def _set_state_stopped(note: str = ""):
    STATE["running"] = False
    STATE["ends_at"] = time.time()
    STATE["note"] = note

def stop_job(reason: str = "Parado"):
    global _mem_blocks, _stop_evt_mp, _procs

    with _job_lock:
        if not STATE["running"] and not _procs:
            _set_state_stopped("Já estava parado.")
            _mem_blocks = []
            return

        # sinaliza workers
        if _stop_evt_mp is not None:
            _stop_evt_mp.set()

        # finaliza processos
        for p in _procs:
            try:
                if p.is_alive():
                    p.terminate()
            except Exception:
                pass

        _procs = []
        _stop_evt_mp = None
        _mem_blocks = []

        _set_state_stopped(reason)

def start_job(mem_mib: int, cpu_workers: int, seconds: int) -> str:
    global _stop_evt_mp, _procs

    with _job_lock:
        if STATE["running"]:
            return "Já está rodando"

        # cria evento + processos
        _stop_evt_mp = mp.Event()
        procs: List[mp.Process] = []
        for _ in range(cpu_workers):
            p = mp.Process(target=cpu_burn, args=(_stop_evt_mp,), daemon=True)
            p.start()
            procs.append(p)

        _procs = procs
        _set_state_running(mem_mib, cpu_workers, seconds, procs)

        # memória em thread (pra não travar o server)
        def mem_thread():
            try:
                allocate_memory(mem_mib)
            except MemoryError:
                STATE["note"] = "MemoryError: limite de memória atingido (OOM possível)."
            except Exception as e:
                STATE["note"] = f"Erro ao alocar memória: {e}"

        threading.Thread(target=mem_thread, daemon=True).start()

        # timer para parar
        def stopper():
            time.sleep(seconds)
            # só para se ainda estiver rodando
            if STATE["running"]:
                stop_job("Tempo expirou")

        threading.Thread(target=stopper, daemon=True).start()
        return "Iniciado"

def status_payload():
    now = time.time()
    remaining = None
    if STATE["running"] and STATE["ends_at"]:
        remaining = max(0, int(STATE["ends_at"] - now))
        # se bateu 0, para
        if remaining == 0:
            stop_job("Tempo expirou")
    return {
        **STATE,
        "now": now,
        "remaining_seconds": remaining,
        "mem_blocks_mib": len(_mem_blocks),
    }

@app.get("/", response_class=HTMLResponse)
def index(req: Request):
    return templates.TemplateResponse("index.html", {"request": req})

@app.post("/api/start")
async def api_start(payload: dict):
    mem_mib = int(payload.get("mem_mib", 1900))
    cpu_workers = int(payload.get("cpu_workers", 2))
    seconds = int(payload.get("seconds", 120))

    # guardrails
    mem_mib = max(64, min(mem_mib, 3000))
    cpu_workers = max(1, min(cpu_workers, 32))
    seconds = max(5, min(seconds, 3600))

    msg = start_job(mem_mib, cpu_workers, seconds)
    return PlainTextResponse(msg)

@app.post("/api/stop")
async def api_stop():
    stop_job("Stop solicitado")
    return PlainTextResponse("Parado")

@app.get("/api/status")
async def api_status():
    return JSONResponse(status_payload())

@app.websocket("/ws")
async def ws_status(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            # incrementa "tick" só para efeito visual
            if STATE["running"]:
                STATE["ticks"] += 1

            await ws.send_text(json.dumps(status_payload()))
            await asyncio_sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception:
        # evita matar o pod por exceção no ws
        return

async def asyncio_sleep(seconds: float):
    # import local pra não poluir o topo
    import asyncio
    await asyncio.sleep(seconds)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
