"""Auto-teste dos botoes novos: Limpar campos e Enviar para o Obsidian.

Roda sem abrir janela visivel e sem chamar o Claude Code de verdade: o
subprocess.run que dispararia a CLI headless e trocado por um duble (stub)
que simula sucesso. `app.after` tambem e trocado por uma fila que so roda
os callbacks no fim (sem mainloop de verdade, os callbacks do worker em
outra thread nao podem tocar o Tk direto). Falha com AssertionError se algo
quebrar.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pdfmd.app_gui as gui
from pdfmd.app_gui import PdfMdApp

app = PdfMdApp()
app.withdraw()  # nao mostra a janela

# sem mainloop rodando, callbacks agendados por thread de fundo (self.after)
# nao podem tocar o Tk direto; enfileira e drena no thread principal depois
# do join, em vez de deixar o worker chamar Tk pela metade.
tarefas_after: list[tuple] = []
app.after = lambda ms, func=None, *args: tarefas_after.append((func, args)) if func else None


def _drenar_after() -> None:
    while tarefas_after:
        func, args = tarefas_after.pop(0)
        func(*args)


# ---------------------------------------------------------------- Limpar campos
app.in_path_var.set(r"D:\algum\processo.pdf")
app.out_path_var.set(r"D:\algum\processo.md")
app._input_paths = [r"D:\algum\processo.pdf"]
app._last_output_path = r"D:\algum\processo.md"

app._limpar_campos()
assert app.in_path_var.get() == "", "campo de entrada nao esvaziou"
assert app.out_path_var.get() == "", "campo de saida nao esvaziou"
assert app._input_paths == [], "lista interna de entradas nao esvaziou"
assert app._last_output_path is None, "ultima saida nao foi esquecida"
print("[ok] Limpar campos esvazia os dois campos e o estado interno")

# ------------------------------------------------------- Enviar para o Obsidian
gui.messagebox.showinfo = lambda *a, **k: None
gui.messagebox.showwarning = lambda *a, **k: None
gui.messagebox.showerror = lambda *a, **k: None

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    vault = tmp / "vault"
    vault.mkdir()
    app.obsidian_dir_var.set(str(vault))

    md = tmp / "0000923-55.2026.8.05.0113.md"
    md.write_text("# Peca de teste\n", encoding="utf-8")
    app._last_output_path = str(md)

    assert app._markdowns_gerados() == [md], "nao localizou o markdown unico"

    # caso 1: sem 'claude' no PATH -> avisa e nao dispara worker
    with patch.object(gui.shutil, "which", return_value=None):
        app._enviar_obsidian()
    assert app._obsidian_worker is None, "nao deveria iniciar worker sem o CLI"
    print("[ok] sem CLI 'claude' no PATH, avisa e nao tenta enviar")

    # caso 2: com 'claude' no PATH -> dispara 'claude -p --permission-mode
    # acceptEdits <prompt>' headless, um subprocess por arquivo, sem copiar
    # o markdown cru (quem decide caminho/estrutura e a skill, nao o app)
    chamadas = []

    def fake_run(cmd, **kwargs):
        chamadas.append((cmd, kwargs))

        class FakeResult:
            returncode = 0
            stdout = "OK (simulado)"
            stderr = ""

        return FakeResult()

    with patch.object(gui.shutil, "which", return_value="claude"), \
         patch.object(gui.subprocess, "run", side_effect=fake_run):
        app._enviar_obsidian()
        app._obsidian_worker.join(timeout=5)
    _drenar_after()

    assert len(chamadas) == 1, f"esperava 1 chamada ao claude, veio {len(chamadas)}"
    cmd, kwargs = chamadas[0]
    assert cmd[0] == "claude"
    assert "-p" in cmd and "--permission-mode" in cmd and "acceptEdits" in cmd
    assert str(md) in cmd[-1], "prompt nao referencia o markdown de origem"
    assert str(vault) in cmd[-1], "prompt nao referencia o vault"
    assert kwargs.get("cwd") == str(vault), "nao rodou com cwd no vault"
    assert not (vault / md.name).exists(), "app nao deve copiar o arquivo cru"
    assert str(app.obsidian_btn["state"]) == "normal", "botao deveria reabilitar apos concluir"
    print("[ok] aciona 'claude -p --permission-mode acceptEdits' com cwd no vault, sem copia crua")

    # caso 3: lote (pasta de saida com varios .md) -> uma chamada por arquivo
    lote = tmp / "lote"
    lote.mkdir()
    for nome in ("a.md", "b.md"):
        (lote / nome).write_text(f"# {nome}\n", encoding="utf-8")
    (lote / "ignorar.txt").write_text("nao e markdown", encoding="utf-8")
    app._last_output_path = str(lote)

    achados = [p.name for p in app._markdowns_gerados()]
    assert achados == ["a.md", "b.md"], f"lote errado: {achados}"

    chamadas.clear()
    with patch.object(gui.shutil, "which", return_value="claude"), \
         patch.object(gui.subprocess, "run", side_effect=fake_run):
        app._enviar_obsidian()
        app._obsidian_worker.join(timeout=5)
    _drenar_after()
    assert len(chamadas) == 2, f"esperava 1 chamada por arquivo do lote, veio {len(chamadas)}"
    print("[ok] lote dispara uma chamada headless por markdown e ignora .txt")

    # caso 4: nada convertido ainda
    app._last_output_path = None
    app.out_path_var.set("")
    assert app._markdowns_gerados() == [], "deveria nao achar nada"
    print("[ok] sem conversao, nao ha o que enviar (avisa em vez de quebrar)")

    # caso 5: a pasta escolhida (o vault) fica memorizada na configuracao
    assert app.obsidian_dir_var.get() == str(vault), "pasta do vault nao foi memorizada"
    print("[ok] pasta do vault fica memorizada entre usos")

app.destroy()
print("\nTODOS OS TESTES PASSARAM")
