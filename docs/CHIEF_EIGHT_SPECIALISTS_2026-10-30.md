# INROU — Chief Analyst и восемь новых специализированных ролей

**Состояние:** feature branch `codex/inrou-chief-eight-specialists-2026-10-30` поверх чернового PR #24. Не production-автономность. Внешняя LLM, публикация утверждений, запись в кабинеты и фоновые задачи **выключены**.

## Количество и управление

**21 продуктовая роль: 1 Chief Analyst + 20 специалистов.** Среди 20: 3 проверяющих/охранных роли (Evidence Verifier, Risk Guardian, Recommendation Challenger). **14 IDE-профилей разработки** существуют отдельно и не являются клиентскими runtime-агентами.

Главный координатор `chief_analyst` — **read-only on-demand диагностический маршрут**, а не запущенный на 24/7 LLM supervisor. Вход: `GET /api/v1/workspaces/ws_<id>/intelligence/chief-analyst?days=7|30`. Запрос проходит штатную сессию, workspace RLS, законный доступ к анализу, `INROU_INTELLIGENCE_ENABLED` и `INROU_INTELLIGENCE_REAL_DATA_APPROVED`; снимает доверенные данные с sealed snapshot. Без доступных реальных данных возвращается `available:false`, а не искусственная аналитика.

### Роутинг и ограничения

| Роль | Источник | Что реально выполняет сейчас | Не делает |
|---|---|---|---|
| Tracking Integrity | Метрики источника + conversion_definition | Проверяет наличие/полноту счётчиков и конверсий; ставит ограничения на уверенность | Не объявляет, что тег на сайте исправен |
| Anomaly Sentinel | 6+ целых последних дней снимка | Находит **только кандидат** на крупное изменение расходов по сравнению медиан | Не доказывает статистическую аномалию или причину |
| Lead Quality | Явные leads и qualified_leads из допустимого Result | Вычисляет долю квалифицированных лидов, если оба числа представлены | Не путает лид с оплатой/продажей; при отсутствии CRM не считает |
| Knowledge Steward | Версионированная модель отрасли + профиль | Проверяет, что модель известна и имеет ссылки на источники; неизвестная ниша — fallback | Не придумывает «рыночный CPA» |
| Search Intent | Отчёт поисковых запросов/тематик (нет в текущих snapshots) | Честный unavailable до подключения безопасного источника | Не читает и не отправляет поисковые фразы в LLM |
| Landing CRO | Проверенные этапы посадочной воронки (нет в snapshots) | Честный unavailable до источника | Не объявляет высокий bounce плохой рекламой |
| Customer Value | CRM/когорты/возвраты/выручка (нет) | Честный unavailable до источника | Не придумывает LTV/CAC/profit |
| Recommendation Challenger | Все доступные диагностические evidence и blockers | Всегда блокирует автоматическую публикацию и рекламные действия, перечисляет отсутствующие проверки | Не одобряет сам себе независимость и причинный эффект |

## Что значит «настроены»

1. Все восемь внесены в реестр `backend/app/intelligence/agent_control.py` и в check на циклы/записи.
2. `backend/app/intelligence/specialist_runtime.py` реализует on-demand локальные обработчики, маршрут `chief_analyze`, закрытый список из восьми ролей и детерминированные reason codes.
3. Контекст берётся только из серверных `AnalysisResult` и sealed snapshots; есть повторная сверка provenance и сумм перед использованием дневных рядов.
4. Выводы не уходят в сторонний LLM; не создаются новые рекомендации, расходы, рекламные изменения или уведомления.
5. Результат `review_required` значит «ожидает настоящей проверки», **не** «агенты успешно пересмотрели каждый вывод».
6. Тесты: `backend/tests/test_specialist_runtime.py`, `backend/tests/test_chief_analyst_api.py` и `backend/tests/test_agent_control.py`.

## Roadmap до полноценной автоматизации

**P0:** поддерживаемая РФ production среда и документы, подтверждение email, настоящий OAuth Direct+Метрика, корретные objectives; RLS и тест двух клиентов. Без этих условий real data OFF.

**P1:** durable orchestration: `agent_runs`/`agent_tasks` с workspace, version, idempotency, retry policy и quota; independent evidence-bound outputs; reviewer service identities; source hashes, tool budget и kill-switch. Model integration (если разрешён) получает только разрешённые агрегаты. Это отдельное изменение, не реализовано одним файлом с роутером.

**P2:** подключить достоверный отчёт поисковых запросов с privacy/allowlist, реальные метрики посадочных страниц из Метрики, CRM-cohort/value с согласием и договором, связывание событий без PII в LLM. Только после этого включать Search Intent, Landing CRO и Customer Value как полноценные анализаторы.

**P3:** использовать результаты Chief в кабинете INROU после дизайн/financial/legal приёмки; графики должны принимать даты и метрики из одного source snapshot, не рисовать отсутствующие точки, не обещать эффект до проверки. Измерения и действия строго после human approval.

## Гейты и антирегрессия

- Unknown `--`, `None` и пропуск дня никогда не становятся `0`.
- Для уровня «факт» нужны scope, source, unit, period, snapshot, compatible conversion definitions, Decimal; прогноз/гипотеза маркируются.
- Пересчёт по одному backend и «два одинаковых submission» не доказательство независимости.
- Любое некорректное/устаревшее поле → unavailable/blocked. Never auto-write advertising.
- Exact commit CI + два workspace + live API acceptance только после подключения инфраструктуры и разрешения владельца.

Документ не разрешает считать восемь ролей автономными агентами и не заменяет ревью специалистов по безопасности/финансам.
