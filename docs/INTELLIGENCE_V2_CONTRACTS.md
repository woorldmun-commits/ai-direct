# Intelligence 2.0 — контракты, зафиксированные до PR-2

Статус: решение владельца, 2026-10-08. Дополняет `INTELLIGENCE_V2_GAP_REPORT.md`. Полные документы v2 (§131 ТЗ) — PR-3; здесь только то, что нужно знать до начала PR-2.

## 1. §94 ТЗ — что фиксирует каждый Agent Run

В ТЗ блок «Каждый Agent Run фиксирует:» был пустым. Каноническое содержание:

**Идентификация:** `run_id`, `workspace_id`, `analysis_run_id`, `started_at`, `completed_at`, `status`, `agent_version`, `rule_version`, `release_id`.

**Исполнение LLM:** `provider`, `model`, `model_version`, `prompt_version`, `prompt_hash`, `knowledge_pack_version`, `knowledge_pack_hash`. Одной версии недостаточно: содержимое промпта или пакета знаний не должно меняться внутри версии незаметно, поэтому хранится ещё и хеш.

**Происхождение входа:** `input_bundle_hash`, `source_snapshot_ids`, `metric_versions`, `business_context_version`.

**Выполнение:** `analysis_plan_id`, `capabilities_used`, `tools_used`, `latency_ms`.

**Результат:** `output_hash`, `decision_count`, `recommendation_count`, `explanation_count`.

**Безопасность и воспроизводимость:** `data_status`, `data_sufficiency`, `refusal_reason`, `error_code`.

Правила:
- Каждый запуск воспроизводим по указанным снимкам, версиям и метаданным неизменяемого входного пакета.
- Сырые ответы провайдера не сохраняются, если политика хранения данных прямо не разрешает.
- Запуск пишется и тогда, когда LLM выключен (флаг `llm_enabled=false`): `provider`/`model*`/`prompt*` пусты, путь — детерминированный шаблон. Пустое поле означает «не применялось», а не нуль.
- Запись append-only.

## 2. Metric Registry v2 — единый контракт истины для аналитики

Реестр — один источник определений метрик для правил, Capability Resolver, API/дашборда и LLM. Никто не считает метрику «по-своему».

Структура определения:

| Поле | Смысл |
|---|---|
| `metric_id`, `version` | идентификатор и версия на каждую метрику (`cpa@N`), версии пишутся в `analysis_run` |
| `owner` | команда/модуль, отвечающий за определение |
| `allowed_sources` | допустимые источники **получения** числа |
| `measurement_source` | кто **измерил** (для конверсий, CPA, CR — Яндекс Метрика; для расхода, кликов, показов — Директ) |
| `required_fields` | поля, без которых метрика не считается |
| `minimum_data` | минимум данных, чтобы число вообще считалось (это не уровень достаточности для действия — его решает Safety) |
| `formula` | точная формула, `Decimal`, округление |
| `attribution` | модель атрибуции и цели (`ConversionDefinition`) |
| `channel_scope` | `search`, `network` (РСЯ) и т.д.; поиск и сеть в один KPI не смешиваются |
| `calculation_type`, `value_type` | `actual` / `calculated` / `estimated` / `unavailable` |
| `unavailable_reasons` | закрытый список причин «нет данных» |

Уточнение к примеру из обсуждения: для CPA `allowed_sources = yandex_direct` (получение), а `measurement_source = yandex_metrika`, не `direct`. Это то самое разделение, которое закреплено в PR-1; нарушать его нельзя.

Текущее состояние: `backend/app/intelligence/metrics/definitions.py` (`metric_definitions@1`, PR-1) уже содержит источник получения, `measurement_source`, формулу, атрибуцию и семантику пустой ячейки. В PR-2 добавляются `owner`, `required_fields`, `minimum_data`, `channel_scope`, `value_type`, `unavailable_reasons`, версия на метрику. Реестр остаётся в коде с `@версией`; набор версий фиксируется в `analysis_run`.

## 3. Capability Resolver

Отвечает не на вопрос «что хочет сделать AI», а на вопрос «что система вправе утверждать и делать при текущих данных».

Вход: подключённые источники (Директ, Метрика), определение конверсий, стратегии кампаний, наличие выручки, права записи. Выход — статус по каждой возможности:

`supported` · `partial` · `unsupported` · `unknown` (по §110 ТЗ; `unknown` в рекомендациях не используется).

Пример для Директ + Метрика без выручки: CPA — supported; выручка, ROAS — unsupported; анализ запросов — partial; анализ площадок — supported; эксперимент — unsupported. LLM получает этот набор как факт и не может «догадаться», что ROAS есть. Источник матрицы стратегий — существующий `STRATEGY_ACTIONS` (`sources/campaigns.py`).

## 4. Цепочка Observation → Finding → Decision → Action → Outcome

Будущий Decision Ledger — не журнал решений, а цепочка из пяти разных сущностей:

1. **Observation** — наблюдаемый факт («CPA вырос на 42%»).
2. **Finding** — подтверждённая детерминированным правилом находка.
3. **Decision** — решение человека по рекомендации (принято, отклонено, отложено + причина).
4. **Action** — что реально сделано и подтверждено ли.
5. **Outcome** — измеренный результат после действия.

Обучающим сигналом становится только Outcome. Рекомендация не считается успешной оттого, что система её предложила или человек её принял. Обучение влияет на ранжирование и приоритеты, но никогда не меняет факты и пороги правил (§91 ТЗ).

## 5. Границы PR-2

PR-2 создаёт каркас, а не «весь Intelligence».

**Входит:** контракты v2 (достаточность на 4 уровня с причиной, уровни действий §20, типы утверждений §17, статус причинности §18, Evidence Bundle, формат AgentFinding §60), Metric Registry v2, Capability Resolver поверх `STRATEGY_ACTIONS`, `analysis_run`/`analysis_plan` (расширение `audit_runs`), Agent Registry в коде, поля Agent Run из §1, расширяющие миграции CHECK, тест удаления workspace по каталогу БД, подача `DataHealth` в `safety_policy@2`.

**Не входит:** Chief Analyst, специалисты, Root Cause, Opportunity, LLM-шлюз и Judge (PR-4), документы v2 (PR-3), пакет adversarial evals (отдельный PR после PR-2).
