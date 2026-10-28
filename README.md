# INROU

Актуальные исходники сервиса анализа Яндекс Директа и Метрики. Основной репозиторий: [woorldmun-commits/inrou](https://github.com/woorldmun-commits/inrou).

## Состав проекта

| Путь | Назначение |
|---|---|
| `designe 1.0/` | Единственный активный frontend: Next.js, публичные страницы, демо, регистрация и рабочий кабинет |
| `backend/app/` | FastAPI, авторизация, изоляция workspace, источники, анализ, очередь, измерения и биллинг |
| `backend/tests/`, `backend/evals/` | Тесты и контрольные наборы методик |
| `backend/migrations/`, `backend/db/` | Полная история миграций и эталон схемы |
| `deploy/`, `Dockerfile`, `render.yaml`, `compose.yaml` | Развёртывание и эксплуатация |
| `.github/workflows/` | Проверки backend/frontend, зависимостей и секретов |
| `docs/` | Действующие спецификации, контракты и инструкции |
| `docs/project-agents/`, `.claude/agents/` | Рабочие профили команды разработки и правила независимой проверки |

Имя папки `designe 1.0` сохранено: на него ссылаются Docker и CI. Это рабочий frontend, а не архив версии 1.0. Папки `components/reference` и `components/midnight` содержат используемые формы и стили; их названия не означают отдельные версии сайта.

## Проверка frontend

```sh
cd "designe 1.0"
npm ci
npm run lint
npm run test:pilot
npm run test:ix
npm run test:remediation
npm run test:deep-audit
npm run build
```

Полный набор проверок и настройка тестового PostgreSQL описаны в [.github/workflows/ci.yml](.github/workflows/ci.yml) и [.github/workflows/inrou-launch.yml](.github/workflows/inrou-launch.yml).

## Текущее состояние

[Демо](https://inrou-pilot.onrender.com/demo/overview) доступно. Email/OAuth, реальные источники и фоновые процессы требуют конфигурации и внешней приёмки; наличие кода не означает, что они включены.

Перед открытием регистрации прочитайте [статус выпуска](docs/RELEASE_STATUS.md), [инструкцию развёртывания](deploy/README.md) и [email launch](docs/EMAIL-LAUNCH.md). Карта актуальных документов — [docs/README.md](docs/README.md).

Старые реализации интерфейса, брендовые варианты и промежуточные отчёты удалены из текущего дерева. Их можно восстановить через историю Git. Выпущенные миграции и редакции юридических документов сохраняются для существующих данных и записей согласий.
