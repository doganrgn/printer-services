# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from fastapi import UploadFile, File
import os

from app.core.job_store import job_store


router = APIRouter()

# --- Şemalar ---
class ConnectPayload(BaseModel):
    mode: str  # "dummy" | "lan" | "usb"
    params: dict = {}

class TextPayload(BaseModel):
    text: str
    lang: str = "tr"

# --- Uçlar ---
@router.get("/status")
def get_status(request: Request):
    mgr = request.app.state.manager
    return mgr.status()

@router.post("/connect")
async def post_connect(request: Request, payload: ConnectPayload):
    mgr = request.app.state.manager
    result = await mgr.connect(payload.mode, payload.params)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/print/text")
async def post_print_text(request: Request, payload: TextPayload):
    mgr = request.app.state.manager
    try:
        jobid = await mgr.enqueue_print_text(payload.text, lang=payload.lang)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    # 🔽 yeni: UI log/reprint için kayıt
    job_store.add("text", {
        "text": payload.text,
        "lang": payload.lang,
        "cut": False,        # varsa cut vb. alanları da ekle
    }, meta={"queue_jobid": jobid})

    
    return {"status": "queued", "jobid": jobid}

@router.post("/reprint")
async def post_reprint(request: Request, jobid: str):
    mgr = request.app.state.manager
    ok = await mgr.requeue(jobid)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"status": "requeued", "jobid": jobid}

@router.post("/print/image")
async def post_print_image(request: Request, file: UploadFile = File(...)):
    # yükleme klasörü
    os.makedirs("data/uploads", exist_ok=True)
    dest_path = os.path.join("data", "uploads", file.filename)
    # dosyayı kaydet
    with open(dest_path, "wb") as f:
        f.write(await file.read())
    # kuyruğa at
    mgr = request.app.state.manager
    try:
        jobid = await mgr.enqueue_print_image(dest_path)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    # 🔽 yeni: UI log/reprint için kayıt
    job_store.add("file", {
        "filename": file.filename,
        "path": dest_path,
        "cut": False,        # gerekiyorsa gönder
    }, meta={"queue_jobid": jobid})
    return {"status": "queued", "jobid": jobid, "file": file.filename}

from fastapi.responses import StreamingResponse, JSONResponse
import json
import io
from typing import List

@router.get("/logs")
def get_logs(limit: int = 200, format: str = "json"):
    log_path = "app/logs/logs.json"
    if not os.path.exists(log_path):
        return [] if format == "json" else StreamingResponse(io.StringIO(""), media_type="text/csv")

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    # Loguru 'serialize=True' olduğu için her satır bir JSON objesi
    lines = lines[-limit:] if limit > 0 else lines
    records: List[dict] = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except Exception:
            continue

    if format.lower() == "csv":
        # CSV üret
        if not records:
            return StreamingResponse(io.StringIO(""), media_type="text/csv")
        # başlıklar: unique key set
        keys = set()
        for r in records:
            keys.update(r.keys())
        keys = list(keys)

        buf = io.StringIO()
        # header
        buf.write(",".join(keys) + "\n")
        # rows
        for r in records:
            row = []
            for k in keys:
                v = r.get(k, "")
                # JSON iç içe ise düz yaz
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                # virgül ve satır sonlarını kaçır
                s = str(v).replace("\n", " ").replace("\r", " ").replace(",", ";")
                row.append(s)
            buf.write(",".join(row) + "\n")
        buf.seek(0)
        headers = {"Content-Disposition": "attachment; filename=logs.csv"}
        return StreamingResponse(buf, headers=headers, media_type="text/csv")

    # JSON modu
    return JSONResponse(records)

@router.get("/health")
def health(request: Request):
    mgr = request.app.state.manager
    st = mgr.status()
    return {
        "ok": True,
        "connected": st["connected"],
        "mode": st["mode"],
        "queue_size": st["queue_size"]
    }
