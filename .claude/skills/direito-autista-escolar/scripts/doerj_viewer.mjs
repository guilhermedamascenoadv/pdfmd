// Abre o visualizador do Diário Oficial do RJ (IOERJ) num Chromium sem interface e salva o PDF da edição.
// Uso: node doerj_viewer.mjs "<mostra_edicao.php?session=...>" saida.pdf
// As requisições do navegador são baixadas pelo Node (que confia em NODE_EXTRA_CA_CERTS),
// mantendo a verificação TLS ativa — não desligue a verificação de certificados.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import fs from 'fs';
const [,, path, out] = process.argv;
const url = 'https://www.ioerj.com.br/portal/modules/conteudoonline/' + path;
const b = await chromium.launch();
const ctx = await b.newContext({ proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined });
await ctx.route('**/*', async route => {
  const u = route.request().url();
  if (/google-analytics|googletagmanager/.test(u)) return route.abort();
  try {
    const r = await route.fetch();
    const ct = r.headers()['content-type'] || '';
    if (/pdf/.test(ct) && out) fs.writeFileSync(out, await r.body());
    await route.fulfill({ response: r });
  } catch (e) { await route.abort(); }
});
const p = await ctx.newPage();
await p.goto(url, { waitUntil: 'networkidle', timeout: 120000 });
console.log('paginas:', await p.evaluate(() => window.PDFViewerApplication && PDFViewerApplication.pagesCount));
await b.close();
