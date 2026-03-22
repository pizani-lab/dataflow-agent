<div align="center">

# ⚡ DataFlow Agent

**Pipeline orquestrador onde agentes LLM decidem autonomamente como processar, limpar e carregar dados.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.1-092E20?logo=django&logoColor=white)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Claude API](https://img.shields.io/badge/Claude_API-Tool_Use-D97757?logo=anthropic&logoColor=white)](https://docs.anthropic.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Demonstração](#-demonstração) • [Arquitetura](#-arquitetura) • [Quick Start](#-quick-start) • [Como Funciona](#-como-funciona) • [API Reference](#-api-reference) • [Roadmap](#-roadmap)

</div>

---

## 📌 Sobre

O **DataFlow Agent** é um sistema inteligente de processamento de dados que utiliza a Claude API com **tool use** para criar um agente autônomo capaz de:

- **Classificar** automaticamente o schema de qualquer dataset (CSV, JSON)
- **Analisar** a qualidade dos dados (nulos, duplicatas, outliers, tipos inconsistentes)
- **Planejar** transformações com base nos problemas encontrados
- **Executar** o plano de limpeza e transformação de forma autônoma
- **Validar** o resultado final com score de qualidade

Cada decisão do agente é registrada com seu raciocínio completo, criando um log auditável de todo o processo — do dado bruto ao dado limpo.

---

## 🎬 Demonstração

<div align="center">

### Pipeline List → Detail → Agent Reasoning Log

</div>

```
┌─────────────────────────────────────────────────────────┐
│  ⚡ DataFlow Agent                     sistema operacional │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Pipelines Ativos: 2    Execuções: 22    Tokens: 51k   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Pipeline de Vendas            Sucesso   Ativo  │    │
│  │  1 fonte · 8 execuções · 18/03 10:30       →    │    │
│  ├─────────────────────────────────────────────────┤    │
│  │  Pipeline de Logs              Sucesso   Ativo  │    │
│  │  1 fonte · 14 execuções · 10/03 09:00      →    │    │
│  ├─────────────────────────────────────────────────┤    │
│  │  Pipeline de Clientes                  Rascunho │    │
│  │  0 fontes · 0 execuções · 21/03 14:00      →    │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  DataFlow Agent v1.0 · Django + Celery + Claude API     │
└─────────────────────────────────────────────────────────┘
```

---

## 🏗 Arquitetura

```
                    ┌──────────────┐
                    │  Upload/API  │
                    │   Webhook    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Django API  │  REST endpoints + validação
                    │    (DRF)     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ Celery Task  │  Orquestração assíncrona
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │     🧠 Agente LLM      │
              │   Claude API Tool Use   │
              │                         │
              │  1. detect_schema       │
              │  2. assess_quality      │
              │  3. plan_transformation │
              │  4. execute_transform   │
              │  5. validate_output     │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │      PostgreSQL         │
              │  bronze → silver → gold │
              │  + logs de raciocínio   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │    React Dashboard      │
              │  Recharts · Real-time   │
              └─────────────────────────┘
```

### Fluxo do Agente (Agentic Loop)

O agente opera em um **loop autônomo** — o LLM decide quais tools chamar e em que ordem, com base no contexto dos dados:

```
Usuário envia CSV
       │
       ▼
┌─ CLASSIFY ────────────────────────────────────┐
│  "Detectei CSV com 5 colunas: data, regiao,   │
│   produto, valor, quantidade. Schema de        │
│   vendas transacionais."                       │
│   → tool: detect_schema                        │
└───────────────────────────────────┬────────────┘
                                    ▼
┌─ QUALITY ─────────────────────────────────────┐
│  "2.1% nulos em 'regiao', 0.5% em 'valor'.    │
│   Sem duplicatas. Qualidade geral: BOA."       │
│   → tool: assess_quality                       │
└───────────────────────────────────┬────────────┘
                                    ▼
┌─ PLAN ────────────────────────────────────────┐
│  "Plano: 1) fill_nulls regiao, 2) drop_nulls  │
│   valor, 3) cast data→datetime"                │
│   → tool: plan_transformation                  │
└───────────────────────────────────┬────────────┘
                                    ▼
┌─ EXECUTE ─────────────────────────────────────┐
│  "✓ 324 nulos preenchidos, ✓ 40 linhas        │
│   removidas, ✓ tipos convertidos"              │
│   → tool: execute_transform (×3)               │
└───────────────────────────────────┬────────────┘
                                    ▼
┌─ VALIDATE ────────────────────────────────────┐
│  "15.380 linhas de saída. 0% nulos restantes.  │
│   Score: 92/100"                               │
│   → tool: validate_output                      │
└───────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/install/)
- Uma [API key da Anthropic](https://console.anthropic.com/)

### 1. Clone o repositório

```bash
git clone https://github.com/pizani/dataflow-agent.git
cd dataflow-agent
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` e adicione sua API key:

```env
ANTHROPIC_API_KEY=sk-ant-sua-chave-aqui
```

### 3. Suba os containers

```bash
docker compose up -d
```

### 4. Inicialize o banco e dados demo

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
docker compose exec backend python manage.py createsuperuser
```

### 5. Acesse

| Serviço       | URL                           |
|---------------|-------------------------------|
| Dashboard     | http://localhost:5173          |
| API (DRF)     | http://localhost:8000/api/     |
| Admin Django  | http://localhost:8000/admin/   |

### Teste rápido via CLI

```bash
# Com dados de exemplo embutidos
docker compose exec backend python manage.py run_agent --sample

# Com seu próprio arquivo
docker compose exec backend python manage.py run_agent --file /data/meu_arquivo.csv
```

---

## ⚙ Como Funciona

### Modelos de Dados

```
Pipeline             1 ──── N   DataSource
    │                            (file, api, webhook, db)
    │
    1
    │
    N
ProcessingRun        1 ──── N   AgentDecision
    │                            (classify, quality, plan, execute, validate)
    │
    1
    │
    1
QualityReport
    (score, nulls, duplicates, drift)
```

### Stack Técnica

| Camada           | Tecnologia              | Função                                    |
|------------------|------------------------|-------------------------------------------|
| **Backend**      | Django 5.1 + DRF       | API REST, autenticação, ORM               |
| **Async Tasks**  | Celery + Redis         | Processamento assíncrono com retry         |
| **Database**     | PostgreSQL 16          | Persistência + dados em camadas            |
| **Agente IA**    | Claude API (tool use)  | Decisões autônomas de processamento        |
| **Analytics**    | DuckDB                 | Queries analíticas locais                  |
| **Frontend**     | React 18 + Recharts    | Dashboard com timeline do agente           |
| **Infra**        | Docker Compose         | 5 serviços orquestrados                    |

### Estrutura do Projeto

```
dataflow-agent/
├── backend/
│   ├── config/                    # Settings, URLs, Celery config
│   │   ├── settings.py
│   │   ├── celery.py
│   │   └── urls.py
│   ├── dataflow/
│   │   ├── models.py              # 5 domain models
│   │   ├── admin.py               # Admin customizado
│   │   ├── agent/
│   │   │   ├── engine.py          # 🧠 Agentic loop (core)
│   │   │   └── tools.py           # 5 tools + handlers
│   │   ├── api/
│   │   │   ├── views.py           # ViewSets + actions
│   │   │   ├── serializers.py     # List/Detail serializers
│   │   │   └── urls.py            # Router config
│   │   ├── processing/
│   │   │   └── tasks.py           # Celery tasks
│   │   └── management/commands/
│   │       ├── seed_demo.py       # Dados demo
│   │       └── run_agent.py       # CLI para testes
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Dashboard completo
│   │   ├── hooks/useApi.js        # Data fetching
│   │   └── utils/formatters.js    # Helpers BR
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml             # 5 serviços
├── .env.example
└── README.md
```

---

## 📡 API Reference

### Pipelines

| Método | Endpoint                         | Descrição                     |
|--------|----------------------------------|-------------------------------|
| GET    | `/api/pipelines/`                | Listar pipelines              |
| POST   | `/api/pipelines/`                | Criar pipeline                |
| GET    | `/api/pipelines/{id}/`           | Detalhe com fontes e runs     |
| PUT    | `/api/pipelines/{id}/`           | Atualizar pipeline            |
| DELETE | `/api/pipelines/{id}/`           | Remover pipeline              |
| POST   | `/api/pipelines/{id}/upload/`    | Upload de arquivo + processar |
| POST   | `/api/pipelines/{id}/trigger/`   | Disparar execução manual      |
| GET    | `/api/pipelines/{id}/stats/`     | Estatísticas agregadas        |

### Processing Runs

| Método | Endpoint                         | Descrição                          |
|--------|----------------------------------|------------------------------------|
| GET    | `/api/runs/`                     | Listar runs (filtro: pipeline, status) |
| GET    | `/api/runs/{id}/`                | Detalhe com decisões e qualidade   |

### Decisões do Agente

| Método | Endpoint                         | Descrição                     |
|--------|----------------------------------|-------------------------------|
| GET    | `/api/decisions/`                | Listar decisões (filtro: run) |
| GET    | `/api/decisions/{id}/`           | Detalhe da decisão            |

### Exemplo: Upload e Processamento

```bash
# 1. Criar pipeline
curl -X POST http://localhost:8000/api/pipelines/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Vendas Q1", "description": "Dados de vendas do primeiro trimestre"}'

# 2. Upload de arquivo (dispara processamento automático)
curl -X POST http://localhost:8000/api/pipelines/{id}/upload/ \
  -F "file=@vendas_q1.csv" \
  -F "context=Dados de vendas com valores em BRL"

# 3. Acompanhar o run
curl http://localhost:8000/api/runs/{run_id}/
```

---

## 🔧 Desenvolvimento

### Sem Docker

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Celery (outro terminal)
celery -A config worker -l info

# Frontend (outro terminal)
cd frontend
npm install
npm run dev
```

### Testes

```bash
# Testar o agente via CLI
python manage.py run_agent --sample

# Rodar testes
python manage.py test
```

---

## 🗺 Roadmap

- [x] Agentic loop com Claude API tool use
- [x] 5 tools: schema detection, quality, planning, execution, validation
- [x] API REST com DRF (CRUD + upload + trigger)
- [x] Celery tasks com retry e error handling
- [x] Dashboard React com timeline do agente
- [x] Docker Compose (5 serviços)
- [x] CLI para testes rápidos
- [ ] Autenticação JWT
- [ ] Suporte a Parquet e Excel
- [ ] Webhook para notificações (Slack, Discord)
- [ ] Agendamento via Celery Beat com cron UI
- [ ] DuckDB para queries analíticas no dashboard
- [ ] Suporte a múltiplos LLM providers (fallback)
- [ ] Testes automatizados (pytest + factory_boy)

---

## 🤝 Contribuindo

1. Fork o repositório
2. Crie sua branch (`git checkout -b feature/minha-feature`)
3. Commit suas mudanças (`git commit -m 'feat: minha feature'`)
4. Push para a branch (`git push origin feature/minha-feature`)
5. Abra um Pull Request

---

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

<div align="center">

Desenvolvido por **Pizani** · 2026

Django · Celery · Claude API · React · PostgreSQL

</div>
