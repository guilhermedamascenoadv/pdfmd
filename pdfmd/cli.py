"""Command-line interface for pdfmd.

Fast, local, privacy-first PDF → Markdown converter with table and math-aware
conversion (LaTeX-style equations, Unicode math, and text tables rendered as
Markdown).

Usage (basic):

  pdfmd input.pdf
  pdfmd input.pdf -o notes.md
  pdfmd *.pdf --ocr auto --stats

All processing happens locally. No uploads, no telemetry, no tracking.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

from .models import Options
from .pipeline import pdf_to_markdown


# ---------------------------------------------------------------------------
# Colour handling
# ---------------------------------------------------------------------------


@dataclass
class _Colors:
    ok: str
    warn: str
    err: str
    info: str
    reset: str


def _make_colors(enable: bool) -> _Colors:
    if not enable:
        return _Colors("", "", "", "", "")
    return _Colors(
        ok="\033[32m",      # green
        warn="\033[33m",    # yellow
        err="\033[31m",     # red
        info="\033[36m",    # cyan
        reset="\033[0m",
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    description = (
        "Converte arquivos PDF em Markdown limpo, pronto para o Obsidian, com "
        "conversão sensível a tabelas e equações.\n"
        "Roda totalmente offline: sem uploads, sem telemetria, sem dependências de nuvem."
    )

    epilog = r"""
Exemplos:

  # Conversão básica (grava input.md ao lado do PDF)
  pdfmd report.pdf

  # Escolher um arquivo de saída explícito
  pdfmd report.pdf -o report_notes.md

  # Detectar páginas digitalizadas automaticamente e aplicar OCR quando necessário
  pdfmd scan.pdf --ocr auto

  # Forçar OCR via Tesseract e exportar imagens das páginas
  pdfmd book_scan.pdf --ocr tesseract --export-images

  # Apenas prévia (primeiras páginas) com estatísticas
  pdfmd long_paper.pdf --preview-only --stats

  # Converter vários PDFs em lote para uma pasta
  pdfmd *.pdf --ocr auto -o out_md/

  # Modo silencioso, não interativo (bom para scripts)
  pdfmd confidential.pdf --ocr auto --no-progress --quiet

Tabelas e equações:

  • Tabelas em texto são detectadas e renderizadas como tabelas Markdown
    no formato GitHub.
  • Notação matemática Unicode comum, letras gregas, subscritos e
    sobrescritos são normalizados para equações em estilo LaTeX, para que
    expressões como E = mc², x₁₀², α + β³ sobrevivam à conversão como
    equações em vez de texto quebrado.
  • Equações em estilo LaTeX já presentes no PDF são preservadas e não
    são escapadas como texto Markdown comum.

Notas de segurança:

  • Todo o processamento acontece na sua máquina.
  • Senhas são lidas de forma interativa (sem eco na tela), nunca são
    registradas em log e nunca são enviadas a outros processos via
    argumentos de linha de comando.
  • Os arquivos Markdown de saída são gravados sem criptografia; proteja-os
    de acordo com os requisitos de segurança do seu ambiente.
"""

    parser = argparse.ArgumentParser(
        prog="pdfmd",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "inputs",
        metavar="INPUT_PDF",
        nargs="*",  # CHANGED: '*' allows zero inputs (was '+')
        help="Caminho(s) do(s) PDF(s) de entrada. Você pode passar vários PDFs.",
    )

    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT",
        help=(
            "Caminho de saída. Para uma única entrada, é um arquivo .md.\n"
            "Para múltiplas entradas, é tratado como um diretório de saída."
        ),
    )

    parser.add_argument(
        "--ocr",
        choices=["off", "auto", "tesseract", "ocrmypdf"],
        default="off",
        help=(
            "Modo de OCR (padrão: off):\n"
            "  off        — usa apenas o texto nativo\n"
            "  auto       — detecta páginas digitalizadas e aplica OCR quando necessário\n"
            "  tesseract  — força OCR via Tesseract em todas as páginas\n"
            "  ocrmypdf   — usa o OCRmyPDF para layout de alta fidelidade"
        ),
    )

    parser.add_argument(
        "--lang",
        default="eng",
        help=(
            "Código(s) de idioma do Tesseract para o OCR (padrão: eng).\n"
            "Use um código de idioma do Tesseract, ex.: 'deu' para alemão,\n"
            "'fra' para francês, 'jpn' para japonês.\n"
            "Combine com '+' para vários: 'eng+fra'.\n"
            "Usado apenas quando --ocr não é 'off'."
        ),
    )

    parser.add_argument(
        "--export-images",
        action="store_true",
        help="Exporta as imagens para uma pasta _assets/ e adiciona as referências no Markdown.",
    )

    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insere marcadores de quebra de página '---' entre as páginas na saída.",
    )

    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Processa apenas as primeiras páginas (útil para inspeção rápida).",
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Desativa a barra de progresso no terminal.",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suprime mensagens que não sejam de erro; mostra apenas erros.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Aumenta a verbosidade. Use -v para mais logs, -vv para detalhe de depuração.",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help=(
            "Após a conversão, imprime estatísticas básicas "
            "(palavras, títulos, tabelas, listas)."
        ),
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Desativa a saída colorida.",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Imprime a versão e sai.",
    )

    return parser


# ---------------------------------------------------------------------------
# Options helper
# ---------------------------------------------------------------------------


def _make_options(args: argparse.Namespace) -> Options:
    opts = Options()

    # Extraction / OCR
    opts.ocr_mode = args.ocr
    opts.ocr_lang = args.lang or "eng"
    opts.preview_only = bool(args.preview_only)

    # Rendering / output
    opts.insert_page_breaks = bool(args.page_breaks)
    opts.export_images = bool(args.export_images)

    # Transform heuristics remain at their defaults; they can be exposed later.
    return opts


# ---------------------------------------------------------------------------
# Progress bar with ETA
# ---------------------------------------------------------------------------


def _make_progress_cb(
    file_label: str,
    colors: _Colors,
    args: argparse.Namespace,
) -> Callable[[int, int], None]:
    start = time.time()

    def progress_cb(done: int, total: int) -> None:
        if args.no_progress or args.quiet:
            return

        # In the pipeline, progress_cb is called with (pct, 100) where pct is 0—100.
        if total == 100 and 0 <= done <= 100:
            pct = int(done)
        else:
            pct = int(done * 100 / total) if total > 0 else 0
        pct = max(0, min(100, pct))

        elapsed = time.time() - start
        eta_str = "Tempo restante: --"
        if pct > 0 and elapsed > 0:
            remaining = elapsed * (100 - pct) / pct
            if remaining < 90:
                eta_str = f"Tempo restante: {int(remaining)}s"
            else:
                eta_str = f"Tempo restante: {int(remaining // 60)}m"

        bar_width = 24
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        line = f"\r{colors.info}[{bar}] {pct:3d}% {eta_str}  {file_label}{colors.reset}"
        sys.stderr.write(line)
        sys.stderr.flush()

        if pct >= 100:
            sys.stderr.write("\n")
            sys.stderr.flush()

    return progress_cb


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


@dataclass
class ConversionStats:
    words: int
    headings: int
    tables: int
    lists: int


def _is_table_header_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and len(s) > 3


def _is_table_sep_line(line: str) -> bool:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    inner = s.strip("|").replace("-", "").replace(":", "").strip()
    return inner == ""


def _compute_stats(md_path: Path) -> ConversionStats:
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return ConversionStats(words=0, headings=0, tables=0, lists=0)

    lines = text.splitlines()

    # Simple word count
    words = len(re.findall(r"\w+", text))

    # Headings: lines starting with '#'
    headings = sum(1 for ln in lines if ln.lstrip().startswith("#"))

    # Lists: lines starting with -, *, +
    lists = sum(
        1
        for ln in lines
        if ln.lstrip().startswith("- ")
        or ln.lstrip().startswith("* ")
        or ln.lstrip().startswith("+ ")
    )

    # Tables: header + separator pairs
    tables = 0
    i = 0
    n = len(lines)
    while i < n - 1:
        if _is_table_header_line(lines[i]) and _is_table_sep_line(lines[i + 1]):
            tables += 1
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                i += 1
            continue
        i += 1

    return ConversionStats(words=words, headings=headings, tables=tables, lists=lists)


def _print_stats(path: Path, stats: ConversionStats, colors: _Colors) -> None:
    sys.stderr.write(
        f"{colors.info}Estatísticas de {path.name}:{colors.reset}\n"
        f"  Palavras:  {stats.words}\n"
        f"  Títulos:   {stats.headings}\n"
        f"  Tabelas:   {stats.tables}\n"
        f"  Listas:    {stats.lists}\n"
    )
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Core conversion for a single file
# ---------------------------------------------------------------------------


def _run_single(
    inp: Path,
    outp: Path,
    opts: Options,
    args: argparse.Namespace,
    colors: _Colors,
) -> bool:
    """Run conversion for one input/output pair.

    Returns True on success, False on failure.
    """
    if not inp.is_file():
        if not args.quiet:
            sys.stderr.write(
                f"{colors.err}Erro:{colors.reset} arquivo de entrada não encontrado: {inp}\n"
            )
        return False

    if not args.quiet:
        sys.stderr.write(
            f"{colors.info}Convertendo{colors.reset} {inp} "
            f"→ {colors.ok}{outp}{colors.reset}\n"
        )
        sys.stderr.flush()

    # Decide logging callback based on verbosity / quiet
    if args.quiet:
        log_cb: Optional[Callable[[str], None]] = None
    elif args.verbose >= 1:
        def log_cb(msg: str) -> None:
            sys.stderr.write(f"{colors.info}{msg}{colors.reset}\n")
    else:
        log_cb = None

    progress_cb = _make_progress_cb(inp.name, colors, args)

    password: Optional[str] = None  # kept local, never persisted

    def run_once(pdf_password: Optional[str]) -> None:
        pdf_to_markdown(
            str(inp),
            str(outp),
            opts,
            progress_cb=progress_cb,
            log_cb=log_cb,
            pdf_password=pdf_password,
        )

    try:
        # First attempt with no password (or whatever we have)
        run_once(password)
        return True

    except Exception as exc:
        # Look for password / encryption related errors
        lower = str(exc).lower()
        # Portuguese entries match pdfmd's own messages (extract.py); the
        # English ones still catch errors raised by PyMuPDF itself.
        password_keywords = [
            "senha necessária",
            "senha do pdf incorreta",
            "descriptografar",
            "criptografado",
            "password required",
            "password is required",
            "incorrect pdf password",
            "wrong password",
            "cannot decrypt",
            "encrypted",
        ]
        needs_password = any(kw in lower for kw in password_keywords)

        if not needs_password:
            if not args.quiet:
                sys.stderr.write(f"{colors.err}Erro:{colors.reset} {exc}\n")
                if args.verbose >= 2:
                    traceback.print_exc(file=sys.stderr)
            return False

        # Encrypted PDF, interactive password prompt required.
        if not sys.stdin.isatty():
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Erro:{colors.reset} "
                    "o PDF é protegido por senha e a entrada interativa não está disponível.\n"
                )
            return False

        try:
            password = getpass.getpass(
                "O PDF é protegido por senha. Digite a senha (a entrada ficará oculta): "
            )
        except Exception as e_input:
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Erro ao ler a senha:{colors.reset} {e_input}\n"
                )
            return False

        if not password:
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.warn}Nenhuma senha informada; pulando o arquivo.{colors.reset}\n"
                )
            return False

        try:
            run_once(password)
            return True
        except Exception as exc2:
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Erro após a tentativa com senha:{colors.reset} {exc2}\n"
                )
                if args.verbose >= 2:
                    traceback.print_exc(file=sys.stderr)
            return False

    finally:
        # Best-effort hygiene: drop any reference to the password.
        password = None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Version info - CHECK THIS FIRST before requiring inputs
    try:
        from . import __version__ as _VERSION
    except Exception:
        _VERSION = "unknown"

    if args.version:
        print(f"pdfmd {_VERSION}")
        return 0

    # NOW check if inputs were provided
    if not args.inputs:
        parser.print_help()
        return 1

    # Colour configuration
    enable_color = sys.stderr.isatty() and not args.no_color
    colors = _make_colors(enable_color)

    if args.quiet:
        # Quiet suppresses verbosity
        args.verbose = 0

    opts = _make_options(args)

    # Prepare inputs
    inputs: List[Path] = [Path(p).expanduser() for p in args.inputs]

    # Interpret output argument
    out_arg = Path(args.output).expanduser() if args.output else None
    multiple = len(inputs) > 1

    if multiple and out_arg is not None and out_arg.exists() and not out_arg.is_dir():
        sys.stderr.write(
            f"{colors.err}Erro:{colors.reset} ao converter várias entradas, "
            f"--output deve ser um diretório.\n"
        )
        return 1

    if multiple and out_arg is not None and not out_arg.exists():
        try:
            out_arg.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            sys.stderr.write(
                f"{colors.err}Erro ao criar o diretório de saída:{colors.reset} {exc}\n"
            )
            return 1

    successes = 0
    failures = 0

    for inp in inputs:
        if not inp.is_file():
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Erro:{colors.reset} arquivo de entrada não encontrado: {inp}\n"
                )
            failures += 1
            continue

        if out_arg is None:
            outp = inp.with_suffix(".md")
        else:
            if multiple or out_arg.is_dir():
                outp = out_arg / (inp.stem + ".md")
            else:
                outp = out_arg

        ok = _run_single(inp, outp, opts, args, colors)

        if ok:
            successes += 1
            if args.stats:
                stats = _compute_stats(outp)
                _print_stats(outp, stats, colors)
        else:
            failures += 1

    if not args.quiet:
        if failures == 0:
            sys.stderr.write(
                f"{colors.ok}Concluído.{colors.reset} "
                f"{successes} arquivo(s) convertido(s) com sucesso.\n"
            )
        else:
            sys.stderr.write(
                f"{colors.err}Finalizado com erros.{colors.reset} "
                f"{successes} com sucesso, {failures} com falha.\n"
            )
        sys.stderr.flush()

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())