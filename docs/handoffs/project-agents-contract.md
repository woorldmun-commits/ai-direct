# Контракт project-agent evidence gate

## Поставка

`backend/app/agents/supervisor.py`, `__main__.py`; профили — `docs/project-agents/`.
Работает offline: `cd backend; python -m app.agents verify CLAIMS.json --evidence TRUSTED.json`.
Код выхода 0 только для PASS, иначе 1. Ошибка схемы/чтения даёт BLOCKED без эха входа.

## Граница доверия

Manifest передаёт интегратор/проверяющий из независимо проверенного источника, а не автор claims. CLI не аутентифицирует файл, не обращается к БД, не проверяет подлинность подписи и не доказывает неизменяемость записей. `authenticity_verified:false` всегда присутствует. Для живой интеграции требуется экспорт под RLS из доверенного backend и проверка snapshot/hash относительно БД; это отдельная работа, не реализованный HTTP API. Нельзя считать произвольный JSON «доказательством из кабинета».

## Схема

Manifest: `schema_version:1`, `synthetic:boolean`, `workspace_id:positive int`, ISO `period_from/period_to`, `max_age_seconds:1..2678400`, `evidence:[]` (не более 1000).
Submission: `schema_version:1`, `synthetic:boolean`, `claims:[]` (не более 1000).

Каждая запись/claim:

- `id`: уникальная локальная ссылка evidence;
- `workspace_id`, `metric`, `source_id`: отдельный ID записи источника;
- `source_version`: неизменяемая версия записи/снимка;
- `source_sha256`: нижнерегистровый SHA256 проверенного источника;
- `captured_at`: ISO datetime с timezone;
- `value`: действующий `app.contract.Value`, включая amount/unit/source/period/calculation_type/data_status/data_sufficiency/snapshot_id/rule_version/formula/reason.

Неизвестные поля запрещены. Идентификаторы ограничены 100 ASCII-символами; никаких названий кампаний, текстов запросов, логинов, токенов. Каждый файл ≤1MB. Повторяющиеся JSON-ключи отвергаются; float-amount запрещён действующим Value. Формулы — строки-идентификаторы происхождения; gate их никогда не исполняет. Никаких eval/exec/SQL/сети.

Exact equality сравнивает **всю** запись и Value. Другой источник, workspace, период, единицы или версия не проходят даже при одинаковой сумме. Пустые claims/неизвестный evidence, отсутствующие данные, старый/будущий captured_at блокируют; partial требует доработки. `estimated` проходит только как `estimated` с той же формулой. Дубли ID запрещены. При смешанных проблемах NEEDS_WORK имеет приоритет; причины BLOCKED остаются в issues.

Ответ: schema_version/status/synthetic/checked_claims/issues со стабильными кодами и индексом claim. Числа клиента, пути и тексты входов не выводятся. Время проверки берётся системное; программный параметр now предназначен для воспроизводимых тестов.

## Что проверяет человек

Настоящую принадлежность источника и прав доступа, неизменяемость записи, корректность расчёта и причинной интерпретации, свободный текст, дизайн, законность и допустимость публикации. Политика max_age задаётся интегратором по задаче, а не автором claims. Старый период сам по себе не означает устаревший источник: актуальность определяется временем получения и выбранной политикой.

## Проверки и ограничения

`python -m pytest tests/test_agent_supervisor.py -q` — синтетические позитивные/негативные примеры, scope/source/period/unit/value/version/hash, partial/unavailable, freshness, размер и секреты в invalid-input output. Тесты не доказывают безопасность всей системы и не меняют три правила аудита. Новых LLM, фоновых задач и подключений нет.

## Изолированная проверка поставки

В Python 3.11 окружении основного проекта, cwd изолированного worktree/backend: `python -m pytest tests/test_agent_supervisor.py tests/test_evals.py -q` → **76 passed** (22 supervisor + 54 existing evals). Проверены также успешный CLI на синтетических данных и invalid-input без эха содержимого. Полный backend-набор и интеграция после переноса — ответственность интегратора; не объявлены пройденными этой проверкой.

Хеши проверенного кода SHA256:

- `backend/app/agents/__init__.py`: `d20616ccf08f05042da80402000e6050b7b47b0ef64a0ae31ed0b80c9556dfd1`
- `backend/app/agents/__main__.py`: `b21723fd737f508bcb612eca16ef0df00740db0fa338c982e2a88950d56e373c`
- `backend/app/agents/supervisor.py`: `7b9f38a1c6c222e6cb92fa0ff3c0f63acaf588c15156bcbddb500b91b731958b`
- `backend/tests/test_agent_supervisor.py`: `6622b1c14d6ce3f9ff32952367ce95ac04f266204ae5c2378cba8c094d401a05`
