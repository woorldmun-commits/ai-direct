# AdPilot Intelligence 2.0 — Gap report (STEP 1)

Дата: 2026-10-07 · ветка `feat/intelligence-v2` · основа: аудит кода, документации, схемы БД/тестов/приватности (только чтение).
Тесты на момент аудита: **1517 passed, 0 failed** (`backend`, pytest, ~87 с).

Шкала: **CRITICAL** — ломает принцип истины или даёт ложную рекомендацию · **HIGH** — блокирует v2-фундамент или пилот · **MEDIUM** — долг, который v2 обязан закрыть · **LOW** — косметика.

---

## 0. Итог в пяти строках

1. Детерминированное ядро v1 уже близко к v2-фундаменту: `Value`, версионированные правила, `safety_policy@1` (только понижает, закреплено в БД), `exposure_total@1` без двойного учёта, неизменяемый 37-дневный снимок, методы замера, шаблоны-фолбэк, 30 golden-кейсов. **Переписывать не нужно — надстраивать.**
2. Главная ошибка истины: конверсии берутся из отчёта Директа с фиксированными целями и атрибуцией, но **все правила подписывают их как `yandex_metrika`**.
3. `high_cpa` не учитывает дозачёт конверсий за последние 3 дня → CPA завышается → возможна ложная рекомендация «снизить ставку» (ровно пример §79).
4. LLM-слоя, Agent Registry, MetricDefinition, Capability Resolver, feature flags в коде **нет**; 13 из 22 сущностей §99 отсутствуют, 9 — частично.
5. Вся документация на `main` описывает v1.0 («ровно три правила», «AI только объясняет», YandexGPT в РФ) и противоречит решениям v2; параллельно висит неслитая ветка `docs/truth-first-v1-scope`.

---

## 1. Критические исправления (§133 ТЗ) — фактическое состояние

| # | Требование ТЗ | Состояние в коде | Уровень |
|---|---|---|---|
| 1 | Source of Truth (§49–50) | Данные конверсий — из Direct Reports API с `Goals` + `AttributionModels` (`sources/direct.py:210-212`), хранятся как `yandex_direct` (`sync/store.py:112`). Но правила и замер помечают их `yandex_metrika`, CPA — `yandex_direct+yandex_metrika`: `rules/high_cpa.py:73,99,100,103`, `zero_conv_campaign.py:50,67,113`, `zero_conv_placements.py:69,141`, `audit/measurement.py:53,84`. Противоречит `docs/PRD.md:140`. **Уточнение к §50:** смешения «правило A → Direct, B → Metrika» нет — все правила ошибаются одинаково. | **CRITICAL** |
| 1a | Цели и модель атрибуции в evidence | `load_view` проверяет только `conversion_definition IS NOT NULL` (`sync/store.py:146`); какие цели/атрибуция — в evidence не попадает. Judge-проверки 5–6 (§15) сравнивать нечем. | HIGH |
| 2 | MetricDefinition (§48) | Нет. Источник захардкожен в каждом правиле; `rules/domain.py:15` — `Source` Literal. Ближайший аналог — `snapshots.conversion_definition`. | HIGH |
| 3 | Data sufficiency → Safety (§51) | **Посылка §51 устарела:** уровень качества данных уже ограничивает действие (`audit/policy.py:32,52`, `safety_policy@1`, проверка в БД `schema.sql:751`). Устарел только комментарий `rules/high_cpa.py:26-27` и `docs/PRD.md:263`. **Реальная дыра:** `high_cpa` и политика игнорируют `partial`-дни дозачёта (`sync/snapshot.py:20`, `PARTIAL_DAYS = 3`); у zero-conv правил это уже учтено. Сбои источников и устаревший sync в Safety не поступают. | **CRITICAL** (partial-дни) |
| 4 | Capability Resolver (§52–53) | `high_cpa_target` выдаёт `decrease_bid` с рассчитанным % (`high_cpa.py:106-107`); политика ограничивает до `review` (`policy.py:33,53`), `present.py:97-101` переводит в рычаги по стратегии. Но сохранённый текст объяснения всё равно «снизить ставку на N%» (`audit/templates.py:30-33`) — в т.ч. на автостратегиях. Матрица стратегий уже есть — `STRATEGY_ACTIONS` (`sources/campaigns.py:58-68`), но используется только e2e-скриптом и тестами; стратегия не сохраняется в снимок → невоспроизводимо. | HIGH |
| 5 | Causality (§17–18) | Нет claim types / causal status. Есть `calculation_type` (`actual/estimated/unavailable`) в `Value`. | HIGH (для пилота — контракт) |
| 6 | No AI confidence | Субъективного `confidence` в бэкенде **нет**. «Уверенность» — только в PRD и текстах лендинга; в схеме — `data_quality` (`schema.sql:739`). | LOW |
| 7 | Rules registry ↔ docs | В коде 4 версии в 3 семействах: `high_cpa_target@1`, `high_cpa_baseline@1`, `zero_conv_campaign@1`, `zero_conv_placements@1` (за env `DIRECT_PLACEMENTS_REPORT`). В docs встречаются несуществующие `high_cpa@3`, `high_cpa_target@3`; три разных словаря `action_type`. | MEDIUM |
| 8 | Evals (§119–121) | 30 golden JSON-кейсов, 3 семейства, ~6 из 15 категорий (clean, obvious, insufficient, partial, auto strategy, network; overlap и no-action — частично). Нет: subtle, attribution conflict, search, device, geo, funnel, opportunity; нет agent/claim evals. | MEDIUM |

## 2. Прочие находки

### Данные / missing → zero (§78)
- **MEDIUM** `sync/parse.py:127-128`: `--` в колонках конверсий Директа → `0`; конверсии по целям суммируются без объявленной формулы.
- **MEDIUM** `sync/metrika_parse.py:91`: пустой ответ Метрики → `0` по каждой цели и дню.
- LOW (латентно, сейчас недостижимо): `or Decimal(0)` в `high_cpa.py:23`, `zero_conv_placements.py:51`, `measurement.py:83`.
- **MEDIUM** Три несовместимых словаря достаточности: `low/medium/high` (`rules/domain.py:16`), бинарный `sufficient/insufficient` по факту наличия числа (`contract.py:36`, `audit/values.py:136`), и §19 (`insufficient/low/medium/high` + причина).

### База данных (§99)
- Есть частично: `audit_runs`→analysis_run · `findings`→evidence_bundle/action_candidate · `explanations`→agent_run (только provider/model/prompt_hash) · `measurements`, `recommendation_results`→measurement_run/outcome · `workspace_settings`→business_context · `snapshots.conversion_definition`→metric_definition.
- Нет: agent_registry, agent_task, agent_finding, claim, claim_evidence, hypothesis, opportunity, action_capability, platform_capability, knowledge_pack, knowledge_version, analysis_plan, experiment, source_of_truth (часть может жить в коде с `@версией`, см. вопрос 3).
- **HIGH** Словарь v1 зашит в CHECK-ограничения: источники (`schema.sql:30`), двухуровневая достаточность (`:33`), уровни действий `inspect_only/review/change` (`:746`), источники/уровни `stat_rows` (`:560-561`, одна размерность на строку, нет device/network/ad). Нужны расширяющие миграции.
- Правила миграций для v2: новый `versions/NNNN` + та же правка в `db/schema.sql` + строка в `released.txt`; файлы заморожены sha256 и LF; CHECK можно только расширять (строки append-only); каждая новая workspace-таблица — с RLS (`test_rls`). Старые findings не переписываются → исправление источника = **новые версии правил `@2`**, API читает обе метки.
- **HIGH (152-ФЗ)** Тест удаления workspace сверяет рукописный список таблиц (`tests/test_lifecycle.py:221-224`) — новые таблицы агентов/claims с клиентскими данными могут пережить удаление. Тест должен брать список из каталога БД.

### API / UI
- 5 read-only GET-эндпоинтов. Нет: деталей рекомендации и evidence, действий-решений (accept/reject/postpone), эффекта/замера, data health. Без действий-решений Decision/Outcome Memory не получит данных. Изоляция workspace надёжная (сессия → роль → RLS, пул отказывается от ролей с обходом RLS).

### Безопасность / LLM-граница (§56, §95, §115–116)
- Шифрование токенов (AES-GCM, ротация) и секреты через env — в порядке. Хардкода секретов нет.
- **HIGH** Роль приложения читает таблицы без RLS по всем тенантам (`users.email`, логины) и по умолчанию получает SELECT/INSERT на новые таблицы. Для v2: LLM без доступа к БД (по решению), глобальные реестры — не писать ролью приложения.
- **HIGH (юр.)** `ARCHITECTURE.md:53`, `PRD.md:452`, `LEGAL.md:24,71` обосновывают дизайн LLM внутри РФ (YandexGPT). Anthropic как primary = трансграничная передача + возможные ограничения условий API Яндекса на передачу данных третьим лицам. Нужно заключение юриста до отправки любых клиентских агрегатов в Claude.
- Точки prompt injection: санированные тексты запросов (очищены от ПД, но не от инструкций), имена площадок в `findings.evidence_meta`, комментарии пользователя при отклонении, логины аккаунтов. Теста «тексты запросов не попадают в промпт» нет, хотя `ARCHITECTURE.md:125` его обещает.
- **MEDIUM** Тест границ модулей покрывает только `rules/` (`tests/test_rule_high_cpa.py:252-268`), не `audit/`, хотя CLAUDE.md утверждает обратное.

### Снимки и история (§64–66)
- 37-дневный снимок, конвейер allowlist → sanitize → normalize → sealed snapshot, запрет хранения сырых ответов, 60-дневная ретенция запросов — реализованы и покрыты тестами.
- История 90/180 дней возможна (снимки не удаляются), но рост ничем не ограничен — нужна политика до включения feature store.
- Контекст стратегии/возможностей кампании запрашивается «вживую» и не сохраняется → рекомендация невоспроизводима.

### Feature flags
- Реестра нет; три разрозненных env-флага (`API_HSTS`, `PHONE_AUTH_ENABLED`, `DIRECT_PLACEMENTS_REPORT`). Минимально: один `app/flags.py` в том же стиле + фиксация набора флагов в каждом analysis run.

### Документация
- Все docs на `main` = v1.0: `STRATEGY.md:19-27`, `VERSION_SCOPE.md:35,84,86,104-105`, `AI_GOVERNANCE.md:11` (запрещает слово «агент»), `ARCHITECTURE.md:53`, `PRD.md:452`. Код и docs расходятся: `safety_policy@2` объявлен обязательным, но не реализован; `backend/app/ai/` описан как существующий, но его нет; `confidence` vs `data_quality`.
- Неслитая ветка `docs/truth-first-v1-scope` (e735b13, 10 документов): меню «Анализ/Рекомендации/Эффект/Подключения/Настройки» = §101 ТЗ, но в её roadmap «v2» = CRM — конфликт с «Intelligence 2.0».
- Лимит 500 строк: `PRD.md`, `ARCHITECTURE.md` (498), `API_CONTRACT.md` (500) — v2-материал только заменой или в новые документы.
- Иерархия документов §132 уже есть (`VERSION_SCOPE.md:5-24`) — сохранить.

### Само ТЗ (что требует решения)
- §94 — пустой блок «Каждый Agent Run фиксирует:» → предлагаю поля из §97 + решения по LLM (provider/model/model_version/prompt_version/knowledge_pack_version/agent_version/input_bundle_hash/output_hash).
- Каталоги детекторов §67–76 и §77 расходятся в именах (напр. `creative_fatigue` vs `creative_fatigue_signal`, `spend_anomaly` vs `anomaly_cost`, `zero_conversion_placement` vs существующий `zero_conv_placements`; для `zero_conv_campaign` слота нет).
- Дубли: §46 ≡ §80, §81 ≡ §106, §89 ≈ §125, §90 ≈ §126; два разных release gate §120 и §141 → предлагаю один = объединение обоих.
- Уровни §19/§20 (`no_action`, `change_candidate`) ≠ CHECK в БД (`change`) → миграция.

---

## 3. Что переиспользуем как фундамент v2

| Компонент v2 | Берём из v1 | Что добавить |
|---|---|---|
| Evidence Contract | `contract.py` `Value`, `Fact`/`Finding`/`NotEnoughData` | claim type, causal status, 4-уровневая sufficiency с причиной, ссылки на MetricDefinition |
| Rule Engine | `rules/` + реестр `RULES` (версии `@N`) | `@2` с источником через MetricDefinition; правило отдаёт факты достаточности, не уровень действия |
| Safety Engine | `audit/policy.py` `safety_policy@1` (только понижает, БД-гарантия) | `@2`: partial-дни, свежесть/сбой источника, capability, стратегия |
| Exposure Engine | `exposure_total@1` | без изменений к пилоту |
| Snapshot / Fact Engine | 37-дневный sealed snapshot | сохранять стратегию кампании и определение конверсий в снимок |
| Capability Resolver | `STRATEGY_ACTIONS` (`sources/campaigns.py:58-68`) | подключить к конвейеру, версия `capabilities@N`, provider matrix Direct+Metrika |
| Measurement | `audit/measurement.py`, методики `@1–@3`, guard на смену определения | — |
| LLM fallback | `audit/templates.py` | исправить текст «снизить ставку на N%» |
| Evals | `backend/evals/cases/*` (30) | категории §119, кейсы пилота (анонимизированные) |

---

## 4. Предлагаемый план P0 (до пилота 13.10) — на утверждение

Каждый пункт — отдельный PR в `feat/intelligence-v2`, тесты до кода, флаги по умолчанию как в решениях.

1. **PR-1 «Truth fixes»** — MetricDefinition (код, `@1`) для cost/clicks/conversions/CPA/CR с `source_of_truth=yandex_direct`, goals + attribution; правила `@2` берут источник из неё; цели/атрибуция в evidence; `safety_policy@2` (partial-дни, свежесть, сбой источника); `--`/пустая Метрика → `unavailable`, не 0; текст шаблона без «на N%» при автостратегии; тест границ для `audit/`; `app/flags.py`. *Проверка:* новые тесты красные → зелёные, 1517 старых зелёные, golden-кейсы partial/auto strategy.
2. **PR-2 «v2 contracts + DB»** — `intelligence/contracts/` (DataSufficiency 4 уровня + причина, ActionLevel §20, ClaimType §17, CausalStatus §18, EvidenceBundle, AgentFinding §60), Capability Resolver поверх `STRATEGY_ACTIONS` + сохранение стратегии в снимок, Analysis Run/Plan (расширение `audit_runs`), Agent Registry (код), расширяющие миграции CHECK, тест удаления по каталогу БД. *Проверка:* `test_rls`, миграционный тест каталога, контракт-тесты.
3. **PR-3 «Docs v2»** (параллельно) — переписать STRATEGY, VERSION_SCOPE; новые INTELLIGENCE_V2, SOURCE_OF_TRUTH, EVIDENCE_CONTRACT, ACTION_CAPABILITIES, AGENT_REGISTRY; точечно ARCHITECTURE, AI_GOVERNANCE, DATA_MODEL, PRD, LEGAL, CLAUDE.md, `_docs/*`.
4. **PR-4 «LLM gateway + Evidence Judge (code-first)»** — `intelligence/llm/` (gateway, providers/anthropic, fallback), Judge как детерминированные проверки 1–11 §15; `chief_analyst=false` на пилоте. *Можно сдвинуть за 13.10 без ущерба пилоту.*

Оценка: PR-1 и PR-2 — реалистично к 13.10; PR-3 — параллельно; PR-4 — на грани, на пилоте выключен флагом. Внешний блокер пилота — одобрение доступа к Direct API (не код).

После пилота: Chief Analyst, специалисты (Search → RSYA → Anomaly → Budget → Funnel → Device/Geo/Time), Root Cause, Opportunity, Outcome/Decision Memory, API действий-решений, остальные 6 документов §131.

---

## 5. Решения владельца по итогам аудита (2026-10-07)

1. Ветка `docs/truth-first-v1-scope` отдельно не мержится: её содержание (меню §101, сегменты, TRUTH FIRST) переносится в v2-документы в PR-3, «v2 = CRM» убирается.
2. Уровни §19/§20 вводятся сейчас расширяющей миграцией БД (старые строки читаются как есть).
3. Реестры (MetricDefinition, Source of Truth, Capabilities, Agent Registry, Knowledge Packs) — в коде с `@версией`; набор версий фиксируется в analysis run. Таблицы — позже, если понадобится.
4. На пилоте LLM выключен флагом до письменного заключения юриста о трансграничной передаче; объяснения — детерминированные шаблоны. Вопрос юристу отправляется сейчас.
