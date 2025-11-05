 
# -*- coding: utf-8 -*-
import asyncio
import socket
from typing import Optional
from escpos.printer import Network  # python-escpos
from PIL import Image

class LanPrinter:
    """
    Basit LAN yazıcı sargısı (9100/TCP). python-escpos.Network kullanır.
    """
    def __init__(self, host: str, port: int = 9100, timeout: float = 5.0) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._printer: Optional[Network] = None
        self.connected: bool = False

    async def connect(self) -> None:
        # önce sokete bağlanmayı dener (hızlı doğrulama)
        try:
            await asyncio.wait_for(self._probe(), timeout=self.timeout + 1)
        except Exception as e:
            raise ConnectionError(f"LAN connect failed: {e}")

        # başarılıysa escpos printer oluştur
        self._printer = Network(self.host, port=self.port, timeout=self.timeout)
        self.connected = True

    async def _probe(self) -> None:
        loop = asyncio.get_running_loop()
        def _probe_block():
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                return
        await loop.run_in_executor(None, _probe_block)

    async def disconnect(self) -> None:
        # python-escpos Network nesnesinde close yok; GC’ya bırakacağız
        self._printer = None
        self.connected = False
        await asyncio.sleep(0)

    async def print_text(self, text: str) -> None:
        if not (self._printer and self.connected):
            raise RuntimeError("NOT_CONNECTED")
        loop = asyncio.get_running_loop()
        def _do():
            # UTF-8 doğrudan sorun çıkarırsa codepage ayarı gerekebilir;
            # ilk denemede bu basit yaklaşım çoğu yazıcıda çalışır.
            self._printer.text(text + "\n")
            try:
                self._printer.cut()
            except Exception:
                pass
        await loop.run_in_executor(None, _do)

    async def print_image(self, image_path: str) -> None:
        if not (self._printer and self.connected):
            raise RuntimeError("NOT_CONNECTED")
        loop = asyncio.get_running_loop()
        def _do():
            img = Image.open(image_path)
            # python-escpos kendi içinde yeniden ölçekler/monokroma çevirir
            self._printer.image(img)
            try:
                self._printer.cut()
            except Exception:
                pass
        await loop.run_in_executor(None, _do)
