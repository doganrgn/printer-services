# app/core/printer_manager.py
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

# Pillow görüntü desteği
from PIL import Image

# ESC/POS
from escpos import printer as escpos_printer

# ------- Job modeli -------
@dataclass
class PrintJob:
    id: str
    kind: str  # "text" | "image"
    payload: Dict[str, Any]

import uuid, time

class PrinterManager:
    """
    Modlar:
      - dummy: gerçek cihaz yok, sadece log ve başarı döner
      - usb:   python-escpos ile USB
      - lan:   (opsiyonel) IP:9100 raw soket (sonra ekleyebiliriz)
    Kuyruk:
      - enqueue_* -> asyncio.Queue -> worker tek kanal üzerinden cihaza yazar
    """
    def __init__(self) -> None:
        self._mode: str = "dummy"
        self._connected: bool = True   # dummy modda True say
        self._device: Optional[Any] = None  # Usb() örneği
        self._queue: asyncio.Queue[PrintJob] = asyncio.Queue()
        self._jobs: Dict[str, PrintJob] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()  # cihaz erişimini serialize et
        self._start_worker()

    # ---------- lifecycle ----------
    def _start_worker(self):
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._worker_loop(), name="printer_worker")

    async def stop(self):
        # worker'ı nazikçe durdur
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        # cihazı kapat
        await self._close_device()

    # ---------- public API ----------
    def status(self) -> Dict[str, Any]:
        return {
            "mode": self._mode,
            "connected": bool(self._connected),
            "queue_size": self._queue.qsize(),
        }

    async def connect(self, mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        mode:
          - "dummy" → params yok
          - "usb"   → params: vendor_id, product_id (hex veya int), out_ep?, in_ep?
        """
        mode = (mode or "").lower().strip()
        if mode not in ("dummy", "usb", "lan"):
            return {"status": "error", "error": "INVALID_MODE"}

        async with self._lock:
            # önce eski cihazı kapat
            await self._close_device()

            if mode == "dummy":
                self._mode = "dummy"
                self._connected = True
                self._device = None
                logger.info("Connected in DUMMY mode")
                return {"status": "ok", "mode": "dummy"}

            if mode == "usb":
                # VID/PID al
                try:
                    vid = params.get("vendor_id")
                    pid = params.get("product_id")
                    if isinstance(vid, str):
                        vid = int(vid, 16) if vid.startswith(("0x", "0X")) else int(vid)
                    if isinstance(pid, str):
                        pid = int(pid, 16) if pid.startswith(("0x", "0X")) else int(pid)
                    if not (isinstance(vid, int) and isinstance(pid, int)):
                        return {"status": "error", "error": "MISSING_VID_PID"}
                except Exception:
                    return {"status": "error", "error": "BAD_VID_PID"}

                out_ep = params.get("out_ep")  # çoğunlukla gerekmez
                in_ep  = params.get("in_ep")

                try:
                    # Not: python-escpos Usb, endpoint'leri otomatik bulur (çoğu cihazda yeterli)
                    dev = escpos_printer.Usb(vid, pid, out_ep=out_ep, in_ep=in_ep, timeout=0, profile="TM-T88")  # profile opsiyonel
                    # Temel bir komut deneyip bağlantıyı doğrulayalım:
                    dev._raw(b"\x1b@")  # init
                    self._device = dev
                    self._mode = "usb"
                    self._connected = True
                    logger.info(f"Connected to USB printer VID={hex(vid)} PID={hex(pid)}")
                    return {"status": "ok", "mode": "usb", "vid": hex(vid), "pid": hex(pid)}
                except Exception as e:
                    logger.exception("USB connect failed")
                    self._mode = "usb"
                    self._connected = False
                    self._device = None
                    return {"status": "error", "error": "USB_OPEN_FAILED", "detail": str(e)}

            if mode == "lan":
                # LAN backend’i sonra ekleyeceğiz; şimdilik yer tutucu
                self._mode = "lan"
                self._connected = False
                self._device = None
                return {"status": "error", "error": "LAN_NOT_IMPLEMENTED_YET"}

        return {"status": "error", "error": "UNEXPECTED"}

    async def enqueue_print_text(self, text: str, lang: str = "tr") -> str:
        if not self._connected:
            raise RuntimeError("PRINTER_NOT_CONNECTED")
        jid = self._new_job_id()
        job = PrintJob(id=jid, kind="text", payload={"text": text, "lang": lang})
        self._jobs[jid] = job
        await self._queue.put(job)
        return jid

    async def enqueue_print_image(self, path: str) -> str:
        if not self._connected:
            raise RuntimeError("PRINTER_NOT_CONNECTED")
        jid = self._new_job_id()
        job = PrintJob(id=jid, kind="image", payload={"path": path})
        self._jobs[jid] = job
        await self._queue.put(job)
        return jid

    async def requeue(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        # Orijinal payload ile yeni job oluştur
        jid = self._new_job_id()
        clone = PrintJob(id=jid, kind=job.kind, payload=job.payload.copy())
        self._jobs[jid] = clone
        await self._queue.put(clone)
        return True

    # ---------- iç işler ----------
    async def _worker_loop(self):
        while True:
            try:
                job = await self._queue.get()
                try:
                    if job.kind == "text":
                        await self._do_print_text(job.payload["text"], job.payload.get("lang", "tr"))
                    elif job.kind == "image":
                        await self._do_print_image(job.payload["path"])
                    else:
                        logger.warning(f"Unknown job kind: {job.kind}")
                except Exception as e:
                    logger.exception(f"Job failed: {job.id} {e}")
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("worker_loop error")
                await asyncio.sleep(0.2)

    async def _do_print_text(self, text: str, lang: str):
        async with self._lock:
            if self._mode == "dummy":
                logger.info(f"[DUMMY] PRINT TEXT: {text!r}")
                return

            if self._mode == "usb":
                if not self._device:
                    raise RuntimeError("USB device missing")
                dev = self._device
                # Türkçe karakterler: en stabil → cp857 (veya cp1254). 
                # python-escpos'da codepage ayarı:
                try:
                    dev.set(align="left")
                    # Türkçe için çoğunlukla CP857 işe yarar:
                    dev._raw(b"\x1b\x74\x13")  # Select code page 19 (CP857) - bazı profillerde farklılık olabilir
                except Exception:
                    pass
                # Yazdır
                dev.text(text + "\n")
                # Kes (varsa)
                try:
                    dev.cut()
                except Exception:
                    pass
                return

            if self._mode == "lan":
                # LAN raw (9100) sonra eklenecek
                raise RuntimeError("LAN backend not ready")

    async def _do_print_image(self, path: str):
        async with self._lock:
            if self._mode == "dummy":
                logger.info(f"[DUMMY] PRINT IMAGE: {path}")
                return

            if self._mode == "usb":
                if not self._device:
                    raise RuntimeError("USB device missing")
                dev = self._device
                img = Image.open(Path(path)).convert("L")   # grayscale
                # Gerekirse yeniden boyutlandır (termal başlık genişliği ~ 384 px / 576 px)
                # img = img.resize((384, int(img.height * 384 / img.width)))
                dev.image(img)
                try:
                    dev.cut()
                except Exception:
                    pass
                return

            if self._mode == "lan":
                raise RuntimeError("LAN backend not ready")

    async def _close_device(self):
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        if self._mode != "dummy":
            self._connected = False

    def _new_job_id(self) -> str:
        return f"{uuid.uuid4()}"
