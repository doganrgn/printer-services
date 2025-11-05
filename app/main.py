# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import os
from app.core.printer_manager import PrinterManager




# 1) FastAPI instance
app = FastAPI(
    title="Printer Service API",
    version="1.0.0",
    description="USB / Ethernet bağlantılı fiş yazıcısı için API servisi",
)

from app.ui.routes import router as ui_router
app.include_router(ui_router)

# 2) CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3) Router'ı bağla (app tanımlandıktan SONRA)
from app.api.routes import router as api_router
app.include_router(api_router)

# 4) Loglar
os.makedirs("app/logs", exist_ok=True)
logger.add("app/logs/logs.json", rotation="1 MB", serialize=True)

# 5) Basit test endpoint
@app.get("/")
def root():
    return {"message": "Printer Service is running"}

# 6) Local çalıştırma
if __name__ == "__main__":
    import uvicorn
    print("Sunucu başlatılıyor...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=3000, reload=True)

# --- APP STATE: PrinterManager (startup/shutdown) ---
@app.on_event("startup")
async def on_startup():
    app.state.manager = PrinterManager()       # type: ignore[attr-defined]

@app.on_event("shutdown")
async def on_shutdown():
    mgr: PrinterManager = app.state.manager    # type: ignore[attr-defined]
    await mgr.stop()