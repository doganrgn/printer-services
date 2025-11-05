# app/ui/routes.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.core.job_store import job_store

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui", tags=["webui"])

@router.get("", response_class=HTMLResponse)
async def ui_home(request: Request):
    return templates.TemplateResponse("ui.html", {"request": request})

@router.get("/partials/status", response_class=HTMLResponse)
async def ui_status_partial(request: Request):
    status = {"service": "ok"}
    mgr = getattr(request.app.state, "manager", None)
    try:
        # PrinterManager.status() varsa kullan:
        if mgr and hasattr(mgr, "status"):
            s = await mgr.status() if callable(mgr.status) else mgr.status
            if isinstance(s, dict):
                status.update(s)
    except Exception:
        pass

    return HTMLResponse(
        f"""
        <div class="card">
          <div><strong>Servis:</strong> {status.get('service')}</div>
          <div><strong>Printer:</strong> {status.get('printer','-')}</div>
        </div>
        """
    )

@router.get("/partials/jobs", response_class=HTMLResponse)
async def ui_jobs_partial():
    rows = job_store.list_recent(limit=100)

    def fmt(ts: float):
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    trs = []
    for r in rows:
        p = r.get("payload", {})
        if r.get("type") == "text":
            summary = (p.get("text") or "")[:90].replace("<", "&lt;")
        else:
            summary = f"{p.get('filename')} (cut={p.get('cut')})"
        trs.append(
            f"""<tr>
                  <td>{fmt(r.get('ts', 0))}</td>
                  <td>{r.get('type')}</td>
                  <td style="max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{summary}</td>
                  <td>
                    <form hx-post="/ui/actions/reprint/{r['id']}" hx-target="#toast" hx-swap="innerHTML">
                      <button type="submit">Reprint</button>
                    </form>
                  </td>
                </tr>"""
        )
    html = f"""
    <table class="tbl">
      <thead><tr><th>Zaman</th><th>Tür</th><th>Özet</th><th></th></tr></thead>
      <tbody>{''.join(trs) or '<tr><td colspan="4">Kayıt yok</td></tr>'}</tbody>
    </table>
    """
    return HTMLResponse(html)

@router.post("/actions/reprint/{job_id}")
async def ui_reprint(job_id: str, request: Request):
    rec = job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")

    mgr = getattr(request.app.state, "manager", None)
    if mgr is None:
        raise HTTPException(status_code=500, detail="Manager not ready")

    jtype = rec.get("type")
    payload = rec.get("payload") or {}

    # PrinterManager API'ni bu çağrılara uyarla (imzalar sende farklı olabilir)
    if jtype == "text":
        ok = await mgr.print_text(  # type: ignore[attr-defined]
            text=payload.get("text", ""),
            encoding=payload.get("encoding"),
            wrap=payload.get("wrap"),
            cut=payload.get("cut", False),
            qr=payload.get("qr"),
        )
        if ok:
            job_store.add("text", payload, meta={"reprint_of": job_id})
            return PlainTextResponse("Yeniden yazdırıldı.")
        raise HTTPException(status_code=502, detail="Yazdırma hatası")

    elif jtype == "file":
        fpath = payload.get("path")
        from pathlib import Path as _P
        if not fpath or not _P(fpath).exists():
            raise HTTPException(status_code=410, detail="Kaynak dosya artık yok")
        ok = await mgr.print_file(_P(fpath), cut=payload.get("cut", False))  # type: ignore[attr-defined]
        if ok:
            job_store.add("file", payload, meta={"reprint_of": job_id})
            return PlainTextResponse("Dosya yeniden yazdırıldı.")
        raise HTTPException(status_code=502, detail="Yazdırma hatası")

    else:
        raise HTTPException(status_code=400, detail="Bilinmeyen job türü")
