# RUNBOOK — US Deal Hunter V1

Guia operacional mínimo para rodar o pipeline, publicar e atualizar o site.

## 1. Pré-requisitos

- Python com o venv do projeto: `.venv\Scripts\python.exe` (Windows).
- Dependências: `requirements.txt` (`.venv\Scripts\pip.exe install -r requirements.txt`).
- Arquivo `.env` na raiz, copiado de `.env.example`:
  - `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`: obrigatórios **para publicar** no Telegram.
  - `AMAZON_*`: opcionais. Sem credenciais (ou ainda sem aprovação da Amazon
    Creators API) o caminho V1 é **demo** ou **curated**.
  - `.env` nunca é commitado. Em Windows rode os comandos a partir de um terminal
    com o `.env` carregado, ou exporte as variáveis antes.

## 2. Comandos

```powershell
# dry-run (nunca publica, nenhum canal)
.\.venv\Scripts\python.exe run.py --keywords "gaming mouse" --dry-run

# modo demo, sem publicação
.\.venv\Scripts\python.exe run.py --keywords "gaming mouse" --demo

# publicar no modo demo (Telegram + canal WEBSITE)
.\.venv\Scripts\python.exe run.py --keywords "gaming mouse" --demo --publish-demo

# publicar ofertas curadas (arquivo verificado)
.\.venv\Scripts\python.exe run.py --curated-file data/curated_deals.json

# exportar o site (SQLite -> site/deals.json)
.\.venv\Scripts\python.exe export_site.py --db data/deal_hunter.db --out site/deals.json

# servir o site localmente (fetch não funciona em file://)
.\.venv\Scripts\python.exe -m http.server 8000 --directory site
```

O resumo do run imprime uma linha por canal; o site aparece em
`Website published: X/Y`.

## 3. Ordem operacional (rotina diária)

1. **Rodar o pipeline** — `run.py`. Na primeira execução após uma atualização o
   runner migra `data/deal_hunter.db` (backup automático em `data/backups/`).
2. **Exportar o site** — `export_site.py` (lê o banco já migrado).
3. **Commitar** apenas `site/deals.json`.
4. **Push** para o repositório.
5. **Ativar o GitHub Pages manualmente**: `Settings -> Pages -> branch`
   (sem GitHub Actions).

## 4. Notas importantes

- O export **exige o banco já migrado**: a coluna `channel` só existe a partir
  do schema 5 (rodar o pipeline faz a migração).
- O export projeta **somente o canal `WEBSITE`**; publicações só de Telegram
  nunca aparecem no site.
- Re-export é **full-replace atômico**: o arquivo é reescrito por inteiro, deals
  que sumiram do banco saem do `site/deals.json`.
- O canal WEBSITE publica sempre que o Telegram publica (mesmo gate, mesmo
  cooldown de 24h por canal). Em `--dry-run` nenhum canal publica.

## 5. Bloqueios externos (V1)

- **Amazon Creators API**: credenciais/aprovação pendente. Demo e curado são o
  caminho oficial do V1; não bloqueia o lançamento.
- **GitHub Pages**: ativação é configuração manual (passo 5), não há automação.
- **Telegram real**: usa o `.env` local; o token nunca entra no repositório.

## 6. Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```