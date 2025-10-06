# Escala da Mesa de Som (Django)

Sistema simples e tradicional para organizar a **escala de operadores da mesa de som** em cultos, com interface web e exportações em **Excel (.xlsx)** e **Calendário (.ics)**. Focado em clareza, previsibilidade e controle — sem modismos desnecessários.

> **Tecnologias-chave:** Django 5.1, DRF, Celery, Redis, Postgres, HTMX, Alpine.js, Tailwind (CDN).

---

## Sumário

- [Escala da Mesa de Som (Django)](#escala-da-mesa-de-som-django)
  - [Sumário](#sumário)
  - [Visão Geral](#visão-geral)
  - [Arquitetura \& Pastas](#arquitetura--pastas)
  - [Requisitos](#requisitos)
  - [Configuração (Desenvolvimento)](#configuração-desenvolvimento)
    - [Variáveis de Ambiente](#variáveis-de-ambiente)
    - [Subindo com Docker Compose](#subindo-com-docker-compose)
    - [Primeiros Passos](#primeiros-passos)
  - [Acesso \& Fluxo de Uso](#acesso--fluxo-de-uso)
  - [RBAC (Papéis e Permissões)](#rbac-papéis-e-permissões)
  - [Tarefas Assíncronas (Celery)](#tarefas-assíncronas-celery)
  - [API HTTP (DRF)](#api-http-drf)
  - [Exportações](#exportações)
  - [Comandos Makefile](#comandos-makefile)
  - [Testes, Lint e Formatação](#testes-lint-e-formatação)
  - [Produção (Gunicorn + Nginx)](#produção-gunicorn--nginx)
  - [Internacionalização \& Fuso](#internacionalização--fuso)
  - [Resolução de Problemas](#resolução-de-problemas)
  - [The Unlicense](#the-unlicense)

---

## Visão Geral

- Calendário mensal com serviços de **domingo (manhã/noite)** e **extras**.
- Sugestões automáticas de escala com base em disponibilidade e limite mensal por membro.
- Confirmação, troca e adição de atribuições diretamente no card (HTMX).
- Exportações: **Excel (.xlsx)** e **iCalendar (.ics)**.
- Tarefas agendadas (Celery Beat) para:
  - Gerar rascunho mensal (mês seguinte) em dia/hora definidos.
  - Enviar lembretes diários para confirmados na próxima semana.
- Auditoria de alterações (criação/edição/exclusão).
- Papéis pré-definidos: **Admin**, **Coordinator**, **Operator**.

---

## Arquitetura & Pastas

```
backend/
core/                # projeto Django (settings, urls, wsgi/asgi, celery)
scheduling/          # app de domínio
domain/            # models, forms, repositories, signals
services/          # regras de negócio (calendar, suggestion, exporters, audit)
ui/                # views e templates (HTMX/Alpine)
api/v1/            # endpoints DRF
management/        # comandos (seed, roles, triggers, generate)
migrations/        # migrações Django
```

- **Postgres** armazena os dados.
- **Redis** atua como broker/result backend do Celery.
- **HTMX/Alpine** simplificam as interações no front sem SPA complexa.

---

## Requisitos

- Docker e Docker Compose
- Make (opcional, mas recomendado)
- (Sem Docker) Python 3.12+, Postgres 16+, Redis 7+

---

## Configuração (Desenvolvimento)

### Variáveis de Ambiente

Crie um `.env` na raiz (lado do `docker-compose.yml`):

```env
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=troque-por-uma-chave-segura
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
TIME_ZONE=America/Sao_Paulo

DEFAULT_MORNING_TIME=09:00
DEFAULT_EVENING_TIME=18:00
DEFAULT_MONTHLY_LIMIT=2

COUNT_EXTRA_IN_LAST_SERVED=false
SUGGEST_FOR_EXTRA=false

POSTGRES_DB=sound_schedule
POSTGRES_USER=sound_user
POSTGRES_PASSWORD=sound_pass
POSTGRES_HOST=db
POSTGRES_PORT=5432

REDIS_URL=redis://redis:6379/0

# Geração automática do rascunho do mês seguinte (dia/hora locais)
SCHEDULE_GENERATION_DAY=25
SCHEDULE_GENERATION_HOUR=12

# Email (em dev, console backend)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=escala@igreja.local
````

> Opcional (para export .ics): no código, `CALENDAR_LOCATION` é lido via `getattr(settings, ...)`. Se desejar, defina essa **constante** diretamente em `core/settings.py`.

### Subindo com Docker Compose

```bash
make build
make up
make migrate
make superuser         # crie seu login de admin
make seed              # carrega dados demo (admin:admin e alguns membros)
```

* Web: [http://localhost:8000](http://localhost:8000)
* Admin: [http://localhost:8000/admin](http://localhost:8000/admin)

> O `docker-compose.yml` já define **perfis** de desenvolvimento para `web`, `worker` e `beat`.

### Primeiros Passos

1. Acesse o **Admin** e entre com o superusuário criado.
2. (Opcional) Rode `make seed` para carregar membros e disponibilidades padrão.
3. Acesse a **tela Calendário**, selecione o mês e clique em **Gerar sugestões**.

---

## Acesso & Fluxo de Uso

* A UI (calendário, membros) exige autenticação.
* Na tela do **Calendário**:

  * Navegue entre meses; gere serviços e sugestões.
  * Nos cards, confirme, troque membro ou adicione.
  * Exportações no menu **Exportar**: **Excel** e **ICS**.

Atalhos (listados na tela):
`←/→` navega • `T` hoje • `G` gerar • `X` Excel • `I` ICS • `A` extra

---

## RBAC (Papéis e Permissões)

Comando para criar/atualizar grupos e permissões:

```bash
make migrate
python backend/manage.py create_roles
```

Papéis:

* **Admin**: todas as permissões.
* **Coordinator**: CRUD de membros, disponibilidades, serviços e atribuições; leitura de auditoria e mês.
* **Operator**: leitura geral + pode confirmar/substituir atribuições.

> Grupos definidos em `scheduling/management/commands/create_roles.py`.

---

## Tarefas Assíncronas (Celery)

Serviços:

* **Worker**: processa filas.
* **Beat**: agenda:

  * `monthly_draft_generation`: cria rascunho do mês seguinte (dia/hora em `.env`).
  * `daily_reminder`: notifica confirmados nos próximos 7 dias.

Atalhos de teste:

```bash
make trigger-monthly
make trigger-daily
make notify-month year=2025 month=10
```

Ou via management command:

```bash
python backend/manage.py trigger_task monthly_draft
python backend/manage.py trigger_task daily_reminder
python backend/manage.py trigger_task notify_month --year=2025 --month=10
```

---

## API HTTP (DRF)

Todas as rotas exigem autenticação.

* **POST** `/api/v1/schedule/generate`
  Gera serviços (se faltando) e sugestões para `year`/`month` da query/body.
  Query/body aceitam `year|ano` e `month|mes`.

* **GET** `/api/v1/schedule/<year>/<month>`
  Retorna lista de serviços (com assignments). Suporta `limit` e `offset`.

* **GET** `/api/v1/export/xlsx?ano=YYYY&mes=MM`
  Download Excel.

* **GET** `/api/v1/export/ics?ano=YYYY&mes=MM`
  Download ICS.

Exemplo:

```bash
curl -u user:pass -X POST 'http://localhost:8000/api/v1/schedule/generate?ano=2025&mes=10'
curl -u user:pass 'http://localhost:8000/api/v1/schedule/2025/10'
```

---

## Exportações

* **Excel (.xlsx)**

  * Aba principal: linhas por serviço (Data, Hora, Tipo, Rótulo, Membros).
  * Aba “Cultos (Resumo)”: domingos do mês com manhã/noite.
* **ICS (.ics)**

  * Cada serviço vira um evento com duração padrão (definida por `ICS_EVENT_DURATION_MINUTES`, se configurada).
  * Se membros tiverem e-mail, entram como `ATTENDEE`.
  * Campo `summary`: `Tipo [ - Rótulo ] — Nomes`.

> Horários e datas respeitam `TIME_ZONE` (padrão: `America/Sao_Paulo`).

---

## Comandos Makefile

Principais:

```bash
make up            # sobe serviços (dev)
make down          # derruba
make build         # build das imagens
make logs          # logs -f
make migrate       # migrações
make superuser     # cria superuser
make seed          # dados demo
make test          # pytest
make lint          # ruff
make fmt           # black

# Exemplos úteis
make gen year=2025 month=10           # gera (commit) sugestões para um mês
make notify-month year=2025 month=10  # dispara notificação
```

---

## Testes, Lint e Formatação

```bash
make test     # pytest (usa settings core)
make lint     # ruff
make fmt      # black
```

> Observação: Nos testes, importe modelos de `scheduling.domain.models`.

---

## Produção (Gunicorn + Nginx)

* Imagem base preparada; use `GUNICORN=1` para o `entrypoint.sh` iniciar Gunicorn.
* Perfil `nginx` no `docker-compose.yml` (prod).

Passos gerais:

1. Ajuste `.env`: `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, e-mail real, banco/redis gerenciados.
2. `collectstatic` é chamado no entrypoint (ignora erro em dev).
3. Configure **backup** regular do Postgres.

---

## Internacionalização & Fuso

* `LANGUAGE_CODE = "pt-br"` e `TIME_ZONE` definido via `.env`.
* Nomes de meses em PT-BR são tratados no front e nos exports; mantenha `TIME_ZONE` coerente com sua igreja.

---

## Resolução de Problemas

* **Conexão Postgres falhou**
  Verifique serviço `db` no Compose e credenciais no `.env`.

* **Redis indisponível / Celery não consome**
  Cheque o serviço `redis` e URLs (`REDIS_URL`); garanta que `worker` e `beat` estão ativos.

* **Conflitos de migração**
  Rode `make migrate`. Para criar migrações novas: `make mm` (ou `make mm-app app=scheduling`).

* **Erro de duplicidade de serviço**
  Cada `(date, time)` é único. Ajuste no formulário/hora.

---

## The Unlicense

Leia mais em [UNLICENSE](UNLICENSE)
