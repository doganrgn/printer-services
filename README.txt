# Printer Service API
FastAPI tabanlı fiş yazıcı servisi (USB / Dummy backend)

## Kurulum
1. Python 3.11 kurulu olmalı.
2. Sanal ortam oluştur:
   python -m venv .venv
   .venv\Scripts\activate
3. Bağımlılıkları yükle:
   pip install -r requirements.txt
4. Sunucuyu başlat:
   uvicorn app.main:app --port 3000 --reload

## Test
- Dummy mod: POST /connect {"mode":"dummy","params":{}}
- USB mod: POST /connect {"mode":"usb","params":{"vendor_id":"0xXXXX","product_id":"0xYYYY"}}
- Web arayüzü: http://localhost:3000/ui
