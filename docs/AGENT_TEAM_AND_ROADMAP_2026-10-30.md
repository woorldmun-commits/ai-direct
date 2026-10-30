# INROU · единая команда агентов и план доводки · 30.10.2026

> **Рабочий статус:** отдельная feature-ветка для review. Не production-release; не запуск AI по клиентским данным. Основание — прямой аудит репозитория `woorldmun-commits/inrou` на `a90b7ea6`, сравнение с `inrou-deploy` и docs/RELEASE_STATUS.md. Действующий Render — только демо. Вопросы владельца, юридические и live API допуска не подменять тестами.

## А. Две разные команды

**Команда разработки (IDE): 14 профилей = 1 главный проверяющий + 13 специализированных.** Это файлы `.claude/agents/inrou/*.md`; профиль без вызова инструмента — НЕ работающий сотрудник, фоновый процесс, модель или самостоятельный Codex. Ни один не управляет рекламой.

| № | IDE-профиль | Кто за что отвечает | Режим |
|---:|---|---|---|
| 0 | inrou-supervisor | Главный Evidence Supervisor: независимая приёмка и veto; не пишет код | read-only |
| 1 | inrou-backend-metrics | Метрики, правила, Decimal, экономические выводы, история рекомендаций | scoped writer |
| 2 | inrou-integrations-data | OAuth, API Директа/Метрики, snapshots, очереди | scoped writer |
| 3 | inrou-frontend | Midnight Sapphire, UX, mobile, UI states, графики | scoped writer |
| 4 | inrou-seo | SEO+GEO, robots/sitemap, metadata/schema/индексация | scoped writer |
| 5 | inrou-security | RLS, сессии, секреты, privacy, разграничение ролей | review-only |
| 6 | inrou-legal | Законность и реестр обещаний; только черновики для юриста | limited docs |
| 7 | inrou-qa | Негативные тесты, E2E, регрессия | scoped writer tests |
| 8 | inrou-data-contract-qa | Сверка от API до чисел графика, null/0/валюта/периоды | read-only |
| 9 | inrou-runtime-reliability | Очереди, uptime, backup/restore, mail, ретраи | read-only |
| 10 | inrou-product | Продукт, тарифы, стратегия, пилотная экономика | limited docs |
| 11 | inrou-release-ops | CI, Docker, deploy, rollback, мониторинг | scoped writer |
| 12 | inrou-finance-audit | **Новый** независимый аудитор CPA/CAC/ROAS/прибыли и причинного эффекта | read-only |
| 13 | inrou-ai-safety | **Новый** независимый AI auditor: источники, prompt injection, budget, tool/LLM safety | read-only |

**Команда продукта для клиентов: целевая структура из 21 роли = 1 Chief Analyst + 20 специалистов.** Это *архитектурные роли* из `backend/app/intelligence/agent_control.py`, а не 21 запущенная нейросеть. В этой ветке добавлен ограниченный, read-only Chief dispatcher и структурные диагностики на запечатанных снимках. Фоновые AI/LLM, массовая оркестрация, live CRM/queries/CRO и независимая сертификация источника ещё не реализованы. См. `CHIEF_EIGHT_SPECIALISTS_2026-10-30.md`.

| № | Код роли | Ответственность | Актуальный статус |
|---:|---|---|---|
| 0 | chief_analyst | Ограниченный on-demand read-only dispatcher; не автономный LLM | on_demand_read_only |
| 1 | data_health | Достоверность, полнота, актуальность, валюта источников | foundation_only |
| 2 | direct_performance | CPA и расход, конверсии, расходы без результата, правила | foundation_only |
| 3 | conversion_attribution | Сопоставление целей, счётчика, атрибуции, досчёта | foundation_only |
| 4 | finance | CPA, ROAS, CAC, маржа; не выдумывать выручку | foundation_only |
| 5 | industry | Универсальный профиль ниши, проверенные отраслевые знания | foundation_only |
| 6 | root_cause | Арифметическая декомпозиция, гипотезы причин (не causal proof) | foundation_only |
| 7 | opportunity | Возможности роста и очередь гипотез | planned |
| 8 | budget | Сценарии бюджетирования, без действий в Директе | planned |
| 9 | creative | Анализ и генерация гипотез текстов/креативов из подтверждённого брифа | planned |
| 10 | experiment | Планирование A/B, guardrails, критерии подтверждения эффекта | planned |
| 13 | lead_quality | Проверяет долю квалифицированных лидов, если данные доступны | on_demand_read_only |
| 14 | tracking_integrity | Выявляет отсутствие совместимых конверсий/неполные настройки | on_demand_read_only |
| 15 | search_intent | Нужен безопасный источник тематик поисковых запросов | planned |
| 16 | landing_cro | Нужны реальные этапы воронки посадочной страницы | planned |
| 17 | anomaly_sentinel | Кандидат на изменение расходов по полным дням, не причинный вывод | on_demand_read_only |
| 18 | customer_value | CRM cohorts/повторные продажи не подключены | planned |
| 19 | knowledge_steward | Проверяет модель ниши и версию источников | on_demand_read_only |
| 20 | recommendation_challenger | Блокирует неподтверждённые изменения и причинные обещания | on_demand_read_only |
| 11 | evidence_verifier | Структурная независимая проверка источника/формул/снимка | foundation_only (offline) |
| 12 | risk_guardian | Безопасность действий, совместимость стратегий, policy gates | foundation_only (policy) |

`foundation_only` означает, что существует полезный код для этой задачи; это **не работающий автономный агент**.

\n> **Актуализация:** роли 13–20 добавлены в новой ветке; ограничения и код реализации описаны в `CHIEF_EIGHT_SPECIALISTS_2026-10-30.md`. До подключения источников три новые роли возвращают `unavailable`, а не рекламные советы.\n\n## Б. Кто проверяет кого — обязательно

1. Data Health проверяет source status/snapshot/currency/period/goal. При missing/partial/stale запрет категоричных решений.
2. Direct Performance / Finance / другие специалисты формируют **только структурированные кандидаты** со ссылками на records. Тексты LLM не меняют числа и status.
3. Evidence Verifier отдельно сравнивает конкретные `Value` и IDs с **доверенным манифестом**. Результат существующего `app.agents.supervisor.verify` — сверка структуры, **не доказательство аутентичности**.
4. Risk Guardian отдельно оценивает риск, auto strategy, ограничение действия и право клиента; у него нет права изменять кабинет.
5. Chief Analyst получает только проверенные структурированные данные, выносит конфликт на ручную проверку. Одно мнение двух моделей не является независимым доказательством.
6. Human Control: вся реальная реклама редактируется человеком отдельно. Никакой agent не может использовать approve как разрешение на provider write.

В новом модуле `review_handoff` намеренно **не возвращает разрешение на публикацию/изменения**. Максимум — `REVIEW_REQUIRED`. Два отдельных submissions НЕ гарантируют, что reviewers были независимыми людьми или моделями. Это только offline preflight до появления доверенных service identities и настоящих worker jobs.

**Универсальные метки:** `actual`, `estimated`, `unavailable`; `partial` и `stale` не повышать до `complete`. Нет данных — нет вывода. Любая сумма должна иметь валюту, период, formula, snapshot ID и проверяемый источник. По умолчанию LLM на реальных данных выключен. Запрет клиентских названий кампаний, токенов, ПД и поисковых запросов в prompts.

## В. Что менять дальше — конкретная очередь PR

| Этап | Ответственные | Что реализовать | Критерий приёмки |
|---|---|---|---|
| P0.1 | integration + security + QA | Реальный email→trial→Direct/Метрика OAuth→счётчик/цель→первый sync→audit, два отдельных workspace | Два настоящих тестовых клиента, tenant isolation, реальные источники, отсутствие cross-account |
| P0.2 | release-ops + legal + runtime reliability | РФ инфраструктура и DPA/approval, постоянное хранение, backup/restore, SMTP/Unisender, очереди, runbooks | External sign-off, real restore, живые процессы с алертами |
| P0.3 | backend + data contract QA + finance audit | Сверка источников, snapshot/amount/goal/attribution, полные источники и версии | Независимые API-образцы, золотые тесты, отсутствие NULL→0 и двойного счёта |
| P1.1 | backend + AI safety + evidence supervisor | Persisted analysis runs/agent tasks, trusted scoped evidence, quotas, idempotency, timeout/kill switch | Негативные тесты на spoofed evidence, prompt injection, cross-tenant и exhausted budget |
| P1.2 | finance + performance + industry | Финансовая и отраслевая интерпретация с недоступными данными, архивом и профилем клиента | Нулевые выдуманные суммы, все claim IDs разрешены, undefined revenue скрыта |
| P1.3 | root cause + experiment + finance audit | Гипотезы причин, сравнение периодов, осторожный замер результата | Нет причинной экономии без дизайна исследования и подтверждения выполнения |
| P1.4 | runtime reliability + product | Email/внутренний digest, аномалии, дедуп, ретраи, настройка уведомлений | Event→queue→provider→delivery/retry доказаны, privacy-safe payload |
| P2.1 | frontend + data contract QA + design QA | Единый Midnight Sapphire: все public/auth/workspace states и графики, light/dark/mobile | Реальный API для графиков; полноразмерные эталоны утверждены; browser/a11y/visual checks |
| P2.2 | SEO + product + legal | SEO/GEO: индексируемая методология, schemas, content claims registry, Яндекс Вебмастер | Production domain, robots/sitemap/canonical validated, no fake testimonials |
| P2.3 | product + finance audit + legal | Экономика SaaS: 7 дней trial, 3 тарифа, биллинг, retention, conversion funnels | Продажи только после юридической и платёжной end-to-end приёмки |

Эти пункты **не объявлены выполненными** из-за появления файлов-ролей. Каждый следующий PR требует отдельной реализации и тестов.

## Г. Проверка перед принятием изменений

- `cd backend && python -m pytest tests/test_agent_supervisor.py tests/test_agent_control.py -q`.
- `cd backend && python -m pytest -q` — полный backend; `ruff check .`.
- `cd 'designe 1.0' && npm ci && npm run lint && npm run build` — если менялся frontend.
- В GitHub Actions: все необходимые job PASS **на конкретном SHA**, не на предыдущем.
- Ревью независимых `inrou-finance-audit` и `inrou-ai-safety`, затем `inrou-supervisor`. До настоящего независимого прогона ни один профиль не заявлять фактически вызванным.
- Результат выпуска: `source SHA`, `changed_files`, `tests`, `not_checked`, `remaining blockers`, `explicit owner approval`.

## Д. Границы этого первого PR

В текущую ветку добавлены роли проекта, offline reference registry, структурный preflight и негативные тесты. **Не подключены** внешние LLM, новые фоновые воркеры, CRM, VK Ads, Auto-execution, деньги, публичная регистрация и новые тарифы. Production на Render не обновляется; основная `main` не затрагивается.

Критический разрыв в текущих инструкциях: пользовательский принцип входа — **email + пароль, Yandex ID не нужен для логина**; исторические документы и код местами допускают Yandex ID. Решение вынести в отдельный PR после аудита обратной совместимости с действующими записями пользователей. Аналогично название бренда (inrou/INROU) сверить с утверждённой визуальной системой, не менять во всех текстах вслепую.
