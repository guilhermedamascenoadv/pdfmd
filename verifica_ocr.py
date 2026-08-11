"""Prova que o OCR funciona no ambiente criado pelo lancador do aplicativo.

Simula o pior caso: variaveis de ambiente do usuario AUSENTES (como se o menu
Iniciar nao tivesse propagado nada). Se passar assim, passa sempre.
"""
import os
import sys
from pathlib import Path

# --- sabota o ambiente de proposito ---
os.environ.pop("TESSDATA_PREFIX", None)
os.environ["PATH"] = r"C:\Windows\system32;C:\Windows"

import pytesseract

# confirma que, SEM o lancador, o tesseract realmente nao seria achado
try:
    pytesseract.get_tesseract_version()
    print("AVISO: tesseract achado mesmo com PATH limpo (teste menos rigoroso)")
except Exception:
    print("[ok] com PATH limpo o tesseract NAO e encontrado, como esperado")

# --- carrega o lancador do app, que deve consertar o ambiente ---
sys.path.insert(0, str(Path.home() / "Ferramentas" / "pdfmd"))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "pdfmd_app", Path.home() / "Ferramentas" / "pdfmd" / "pdfmd_app.pyw"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

versao = pytesseract.get_tesseract_version()
idiomas = pytesseract.get_languages()
assert "por" in idiomas, "portugues ausente!"
print(f"[ok] apos o lancador: tesseract {versao}, 'por' disponivel ({len(idiomas)} idiomas)")

# --- conversao real de ponta a ponta, igual ao que o app faz ---
from pdfmd.models import Options
from pdfmd.pipeline import pdf_to_markdown

pdf = Path(__file__).parent / "scan_teste.pdf"
saida = Path(__file__).parent / "app_ocr.md"
opts = Options()
opts.ocr_mode = "auto"
opts.ocr_lang = "por"

pdf_to_markdown(str(pdf), str(saida), opts)
texto = saida.read_text(encoding="utf-8").strip()
assert "EXTRAJUDICIAL" in texto.upper(), f"OCR nao extraiu o esperado: {texto[:200]}"
print("[ok] conversao com OCR concluida no ambiente do app")
print("--- texto extraido ---")
print(texto)
