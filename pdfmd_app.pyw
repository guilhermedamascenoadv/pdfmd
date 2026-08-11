"""Lancador do aplicativo pdfmd (PDF -> Markdown).

Garante que o Tesseract instalado via micromamba seja encontrado mesmo quando
o programa e aberto pelo menu Iniciar, onde o PATH pode nao estar carregado.
"""
import os
import sys
from pathlib import Path

FERRAMENTAS = Path(__file__).resolve().parent.parent
TESS_BIN = FERRAMENTAS / "ocr-env" / "Library" / "bin"
TESSDATA = FERRAMENTAS / "ocr-env" / "share" / "tessdata"

if TESS_BIN.is_dir():
    os.environ["PATH"] = str(TESS_BIN) + os.pathsep + os.environ.get("PATH", "")
if TESSDATA.is_dir():
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA)


def main() -> None:
    from pdfmd.app_gui import PdfMdApp

    app = PdfMdApp()
    icone = Path(__file__).resolve().parent / "pdfmd.ico"
    if icone.exists():
        try:
            app.iconbitmap(str(icone))
        except Exception:
            pass
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Sem console para mostrar o erro: exibe numa caixa de dialogo.
        import traceback
        import tkinter.messagebox as mb

        mb.showerror("pdfmd", traceback.format_exc())
        sys.exit(1)
