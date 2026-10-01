#!/bin/bash
# Baixa a Parte I (Poder Executivo) do Diário Oficial do RJ de uma data e converte para .md com o pdfmd.
# Uso: doerj_baixar.sh AAAAMMDD [pasta_saida]
# Requisitos: domínio www.ioerj.com.br liberado na rede; Playwright (Chromium); pdfmd instalado.
# Observação: a busca por palavra do site (busca_do.php) estava fora do ar em 01/10/2026; por isso o acesso é por data.
set -e
D=$1; OUT=${2:-.}; DIR=$(cd "$(dirname "$0")" && pwd)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
B=https://www.ioerj.com.br/portal/modules/conteudoonline
curl -sSL -m 60 -A "$UA" "$B/do_seleciona_edicao.php?data=$(printf "$D" | base64)" -o "$OUT/ed_$D.html"
L=$(python3 - "$OUT/ed_$D.html" <<'PY'
import re,sys
s=open(sys.argv[1],encoding='latin-1').read()
for m in re.finditer(r'href="(mostra_edicao\.php\?session=[^"]+)"[^>]*>(.*?)</a>',s,re.S):
    if 'Parte I (Poder Executivo)' in re.sub(r'<[^>]+>|\s+',' ',m.group(2)): print(m.group(1)); break
PY
)
[ -z "$L" ] && { echo "$D: sem Parte I (fim de semana/feriado?)"; exit 0; }
node "$DIR/doerj_viewer.mjs" "$L" "$OUT/doerj_$D.pdf"
PDFMD=$(command -v pdfmd || echo ~/pdfmd-venv/bin/pdfmd)
"$PDFMD" "$OUT/doerj_$D.pdf" -o "$OUT/doerj_$D.md" -q
echo "$D: $OUT/doerj_$D.md"
