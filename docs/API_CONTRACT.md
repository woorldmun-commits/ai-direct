# API-контракт frontend ↔ backend — v1.0

Слой между бэкендом и фронтендом. Описывает **бизнес-сущности**, а не таблицы: фронтенд не знает про `issues`,
`findings`, `snapshots` и `recommendation_events`. Схема БД может меняться — контракт нет (только новой версией).

Основа — [PRD.md](PRD.md) v1.0 и [VERSION_SCOPE.md](VERSION_SCOPE.md): 4 раздела кабинета (Сегодня · Рекомендации ·
Аналитика · Настройки), «Спросить AI», применение через Direct API после одобрения, агентства и роли. Источники
правды, которые контракт отражает и не переопределяет: `Value` — `backend/app/contract.py` и DATA_MODEL.md §5; уровни
действия — `app/audit/policy.py`; риск, capability, предусловие и откат — EXECUTION_SAFETY.md; exposure —
ECONOMICS.md; AI — AI_GOVERNANCE.md; жизненный цикл рекомендации — DATA_MODEL.md §8.3.

## 1. Общие правила

- Базовый путь `/api/v1`. JSON, UTF-8. Даты — `YYYY-MM-DD`, моменты — ISO 8601 с поясом (`2026-10-02T09:15:00+03:00`).
- **Типы чисел:**

  | Что | JSON-тип | Пример |
  |---|---|---|
  | Деньги, дробные величины, проценты | строка-число | `"12500.00"`, `"-15.00"` |
  | Любое бизнес-значение с источником | `Value` (§2) | |
  | Идентификаторы (наши и Директа) | строка | `"51234567"`, `"rec_8f2c1"` |
  | Количества, `limit`, счётчики | целое число | `3` |
  | Флаги | boolean | |

  Деньги никогда не JSON-number: без потери точности `Decimal`. Отрицательных сумм exposure, «можно сэкономить» и
  «сэкономлено» нет (CHECK в БД).
- **Аутентификация** — сессия в httpOnly cookie (§11). Сессия определяет пользователя, но не workspace.
- **Workspace — в пути:** `/api/v1/workspaces/{workspace_id}/…`. Бэкенд на каждом запросе проверяет доступ (§10):
  owner/admin организации или `ws_role` в этом workspace. Нет доступа или нет workspace → `404`, а не `403`:
  существование чужих данных не раскрывается — тело и время ответа как у несуществующего id. Так же для вложенных
  объектов. Второй барьер — RLS в БД (DATA_MODEL.md §9.5).
- Изменяющие запросы — только с `Origin` нашего сайта и cookie `SameSite=Lax`; иначе `403 csrf_rejected`.
- **`Idempotency-Key`** (UUID) — **обязателен** для `approve`, `apply`, `approve_and_apply`, `rollback`, `cancel` и
  биллинга; для остальных `POST` — по желанию. Тот же ключ и тело → тот же ответ без повторного действия; тот же ключ
  и другое тело → `409 idempotency_conflict`. Ключ живёт 24 часа.
- **`X-Request-Id`** — в каждом ответе; клиент может прислать свой (UUID). Он же в теле ошибки (§12).
- В ответах нет: OAuth-токенов, хэшей кодов и сессий, `snapshot_id`, внутренних id таблиц, текстов поисковых запросов.
- Фронтенд **не считает** бизнес-значения и не решает, какие действия разрешены: показывает `allowed_actions` и
  `Value` как пришли. Суммы, проценты и знак «≈» получаются из полей, а не вычисляются.

## 2. `Value` — любое число

```json
{"amount": "12500.00", "unit": "rub", "calculation_type": "estimated",
 "source": "yandex_direct+yandex_metrika", "period": {"from": "2026-09-22", "to": "2026-09-28"},
 "data_status": "complete", "data_sufficiency": "sufficient",
 "formula": "(cpa - target_cpa) * conversions", "rule_version": "high_cpa_target@1"}
```

| Поле | Значения | |
|---|---|---|
| `amount` | строка-число или `null` | |
| `unit` | `rub` · `count` · `pct` | |
| `calculation_type` | `actual` · `estimated` · `unavailable` | |
| `source` | `yandex_direct` · `yandex_metrika` · `user_input`, через `+` | из чего посчитано |
| `period` | `{from, to}` | период данных |
| `data_status` | `complete` · `partial` | `partial` — в периоде есть дни, которые источник ещё может пересчитать |
| `data_sufficiency` | `sufficient` · `insufficient` | |
| `formula` · `rule_version` | строка или `null` · `имя@N` или `null` | как посчитано и каким правилом |

Названия — как в `app/contract.py`: `Value` бэкенда без `snapshot_id` и с `period` вместо `period_from`/`period_to`.
**Инварианты (проверяет бэкенд):** `unavailable` ⇔ `insufficient` ⇔ `amount = null`; `estimated` ⇒ `formula` не пустая.

| `calculation_type` | Показ (обязательно для фронтенда) |
|---|---|
| `actual` | `18 400 ₽` — без «≈» |
| `estimated` | `≈ 12 500 ₽`, формула — в подсказке «Как посчитано» |
| `unavailable` | «Недостаточно данных» — **никакого числа, нуля или прочерка вместо числа** |

`data_status = partial` → пометка «данные за последние дни могут уточниться». Тип в TypeScript строится так, чтобы
ошибку нельзя было скомпилировать: `amount: string` только в ветках `actual | estimated`, `amount: null` — в `unavailable`.

## 3. Жизненный цикл рекомендации

Состояние — **один основной `status`** и независимые поля исполнения, проверки, отката и замера. `status` отвечает за
жизненный цикл, `execution_mode` — за то, что фактически произошло с действием.

### 3.1 `status` — 8 значений (PRD §5)

| `status` | В UI | Смысл |
|---|---|---|
| `new` | Новая | создана, пользователь ещё не открывал |
| `requires_decision` | Требует решения | ждёт решения человека, в т. ч. недостающих одобрений («одобрено 1 из 2») |
| `approved` | Одобрена | набран кворум одобрений (§4.1) для конкретной версии и состояния объекта, исполнение не завершено |
| `applied` | по `execution_mode` (§3.3) | действие завершено: применено через API, выполнено вручную или проверено |
| `postponed` | Отложена | «Позже» до `postponed_until`, затем снова `requires_decision` |
| `rejected` | Отклонена | «Не буду» |
| `failed` | Не выполнена | исполнение через API не завершилось успехом |
| `cancelled` | Отменена | одобрена, но исполнение отменено до его начала |

```
new ──▶ requires_decision ──(кворум)──▶ approved ──▶ applied
             │   ▲  ▲                      │  ├──▶ failed
             │   │  └─ state_changed · approval_expired · новая версия
             │   │                         └──▶ cancelled
             ├──▶ postponed ─(дата)┘
             ├──▶ rejected
             └──▶ applied            (вручную или «Проверил» — без approved)
```

### 3.2 Поля исполнения

| Поле | Значения | |
|---|---|---|
| `execution_mode` | `api` · `manual` · `none` · `null` | `null` — пока ничего не исполнялось; `none` — исполнять было нечего («Проверил») |
| `execution_status` | `not_started` · `pending` · `succeeded` · `failed` · `claimed_manual` | `claimed_manual` — пользователь **заявил**, что сделал сам; это не факт исполнения |
| `verification_status` | `not_required` · `pending` · `confirmed` · `not_confirmed` | подтверждено ли изменение по данным Директа |
| `rollback_status` | `not_requested` · `pending` · `succeeded` · `failed` · `blocked` | откат после `applied` через API (§6.2); **не статус рекомендации** |
| `measurement` | объект или `null` | результат замера через 7 дней (§7), не статус |

| Сценарий `status = applied` | `execution_mode` | `execution_status` | `verification_status` |
|---|---|---|---|
| Применено через API | `api` | `succeeded` | `confirmed` (AdPilot перечитал объект после изменения) |
| Выполнено вручную, до сверки | `manual` | `claimed_manual` | `pending` |
| Выполнено вручную, сверка нашла изменение | `manual` | `claimed_manual` | `confirmed` |
| Выполнено вручную, изменения нет | `manual` | `claimed_manual` | `not_confirmed` |
| «Проверил» (рекомендация «проверить») | `none` | `not_started` | `not_required` |

### 3.3 Подписи результата в UI

Слово «Применена» для `applied` не показывается. Текст — из `execution_mode` и `verification_status`:

| Поля | Текст |
|---|---|
| `api` | «Применено» |
| `manual` + `pending` | «Выполнено вручную пользователем. Результат изменения пока не подтверждён» |
| `manual` + `confirmed` | «Выполнено вручную. Изменение подтверждено по данным Директа» |
| `manual` + `not_confirmed` | «Выполнено вручную. Выполнение не подтверждено» |
| `none` | «Проверено» |
| `rollback_status = succeeded` / `blocked` | дополнительно: «Изменение отменено (откат)» / текст `state_changed_since_execution` (§4) |

Сверка ручного выполнения — по синхронизации параметров объекта (ARCHITECTURE.md §4.2); до неё остаётся `pending`.

## 4. Действия пользователя и `allowed_actions`

`action_level` назначает политика безопасности (`safety_policy@N`, только понижает уровень правила):
`inspect_only` («Проверить») < `review` («Проверьте перед изменением») < `change` («Можно изменить»).
`risk_level` (`low` · `medium` · `high` · `critical`; `null` у `inspect_only`) назначает `risk_policy@N` —
EXECUTION_SAFETY.md.

| Действие | Переход | Право (§10) | Условия |
|---|---|---|---|
| `view` | `new → requires_decision` | любой с доступом | идемпотентно; фронтенд шлёт при открытии паспорта |
| `postpone` | `→ postponed` | decide | `until`: от завтра до +90 дней |
| `reject` | `→ rejected` | decide | `review` / `change` |
| `check` | `→ applied` (`none`) | decide | только `inspect_only` |
| `mark_done_manually` | `→ applied` (`manual`) | decide | `review` / `change` |
| `approve` | `requires_decision` → тот же (k из N) или `approved` | approve | `change`; данные полные; capability поддержана; есть право записи; `preview_id` |
| `apply` | `approved → applied` / `failed` | execute | кворум не истёк; одобренная версия последняя |
| `approve_and_apply` | `requires_decision → approved → applied` / `failed` | approve **и** execute | одобрение пользователя **завершает** кворум; условия `approve` |
| `cancel` | `approved → cancelled` | approve | исполнение ещё не начато |
| `rollback` | `rollback_status → pending → …` | approve | гейт отката §6.2; последней версии вывода **не** требует |

`postponed` можно решить раньше даты: из него доступны те же действия, что из `requires_decision`.

### 4.1 Кворум одобрений

Требуемое число **разных** одобривших — из `approval_policy` workspace по `risk_level` (по умолчанию medium = 1,
high = 1, critical = 2; меняет owner/admin, снизить critical до 1 — только owner). Засчитываются одобрения той же версии
(`version_id`) с тем же `precondition_hash` (§6.1), не старше 24 часов. Кворум набран → `approved`. Одобрение
завершает кворум и у пользователя есть execute → кнопка «Применить» (`approve_and_apply`); иначе — `approve`, затем
`apply`. Откат — одно одобрение независимо от риска.

**`allowed_actions` считает только бэкенд** — из роли, `status`, `action_level`, `risk_level` и `approval_policy`,
полноты данных, capability, права записи в Директ (`write_access`), уже данных одобрений и лимитов тарифа. Фронтенд
рисует кнопки только из `allowed_actions`; недоступные — из `blocked_actions` с причиной:

```json
"allowed_actions": ["mark_done_manually", "postpone", "reject"],
"blocked_actions": [{"action": "approve_and_apply", "reason": "data_partial"}]
```

| `reason` | Текст для пользователя |
|---|---|
| `data_partial` | «Данные за последние дни ещё уточняются — применить через API пока нельзя. Можно проверить или выполнить вручную» |
| `write_access_missing` | «Нет прав на изменение рекламного кабинета — выполните вручную или выдайте доступ» |
| `capability_unsupported` | «AdPilot не умеет безопасно применить это изменение для такой кампании — выполните вручную» |
| `level_not_change` | «Рекомендация требует проверки — автоматическое применение недоступно» |
| `second_approval_required` | «Нужно второе одобрение: критичное изменение» (по умолчанию два одобрения — только `critical`) |
| `same_approver` | «Второе одобрение должен дать другой участник» |
| `state_changed` | «Параметр в Директе изменился после предпросмотра — нужны новый предпросмотр и одобрение» |
| `approval_expired` | «Одобрение старше 24 часов — одобрите заново» |
| `state_changed_since_execution` | «С момента применения параметр изменился (сейчас X). Откат перезаписал бы более новое изменение — проверьте вручную» |
| `role_forbidden` | «Ваша роль не позволяет это действие» |
| `entitlement_exceeded` | «Недоступно на текущем тарифе» |
| `not_reversible` | «Это изменение нельзя откатить автоматически» |

`state_changed`, `approval_expired`, `capability_unsupported` приходят и как `execution.error_code`, если условие
обнаружено воркером перед записью; `state_changed_since_execution` — как `execution.rollback_reason`.

**Критическое правило:** при `data_status != complete` действия `approve`, `apply`, `approve_and_apply` всегда в
`blocked_actions` с `data_partial` — вместо них «Проверить вручную» / «Выполнить вручную».

## 5. `Recommendation` — проблема, доказательства, действие

`id` — **стабильный** на весь жизненный цикл. Аудит может пересчитать цифры и действие («−15%» → «−25%») — это новая
**версия**, `version_id`; UI показывает последнюю. Одобрение и ручное выполнение относятся к конкретной версии:
устарела — `409 version_outdated`, нужно новое решение.

### `RecommendationListItem` — `GET /workspaces/{ws}/recommendations`

```json
{"id": "rec_8f2c1", "version_id": "rv_77a01", "title": "CPA выше целевого", "ad_account": {"id": "acc_2", "login": "client-login"},
 "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
 "action_level": "change", "risk_level": "high", "status": "requires_decision", "execution_mode": null, "verification_status": null,
 "exposure": "Value", "exposure_overlap": false, "can_save": "Value", "data_status": "complete",
 "period": {"from": "2026-09-22", "to": "2026-09-28"},
 "created_at": "2026-09-29T07:02:11+03:00", "updated_at": "2026-10-01T07:01:54+03:00"}
```

`filter`: `all` · `new` · `requires_decision` · `done` (`applied`) · `postponed` · `rejected`; по умолчанию
`requires_decision` + `new`. Плюс `ad_account` (id кабинета), `limit` (1–100, по умолчанию 50), `cursor`. Ответ:
`{"items": [...], "next_cursor": "…" | null}`. Порядок задаёт бэкенд: активные сначала, внутри — по `exposure.amount`
по убыванию, `unavailable` — в конце. Поля `severity` нет.

### `Recommendation` (паспорт) — `GET /workspaces/{ws}/recommendations/{id}`

```json
{
  "id": "rec_8f2c1", "version_id": "rv_77a01", "title": "CPA выше целевого", "ad_account": {"id": "acc_2", "login": "client-login"},
  "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
  "status": "requires_decision", "postponed_until": null, "action_level": "change",
  "allowed_actions": ["approve", "mark_done_manually", "postpone", "reject"],
  "blocked_actions": [{"action": "approve_and_apply", "reason": "second_approval_required"}],
  "exposure": "Value", "exposure_overlap": false, "can_save": "Value",
  "explanation": {"text": "CPA кампании — 2 500 ₽, это на 25% выше целевого…", "source": "template"},
  "action": {"type": "decrease_bid", "change_pct": "-30.00", "reversible": true},
  "risk": {"risk_level": "critical", "risk_policy": "risk_policy@1", "required_approvals": 2}, "approvals": [],
  "evidence": {"facts": {"cost": "Value", "conversions": "Value", "cpa": "Value", "cpc": "Value", "cvr": "Value"},
               "meta": {"baseline_data_quality": "high"}, "rule_version": "high_cpa_target@1"},
  "safety": {"safety_policy": "safety_policy@2", "candidate_level": "change", "policy_reasons": [], "data_status": "complete"},
  "limitations": ["strategy_unknown"], "execution": {"execution_mode": null, "execution_status": "not_started", "verification_status": "not_required",
                "rollback_status": "not_requested", "rollback_until": null, "rollback_reason": null,
                "approved_at": null, "applied_at": null, "error_code": null},
  "measurement": null, "history": [{"event": "created", "at": "2026-09-29T07:02:11+03:00", "actor": "system"}],
  "created_at": "2026-09-29T07:02:11+03:00"
}
```

- **Паспорт** (PRD §5): проблема — `title`, `ad_account`, `object`; данные — `evidence.facts`; период и источник — в
  каждом `Value`; расчёт — `formula`; причина — `explanation`; действие — `action`, его риск — `risk`; эффект —
  `can_save`; ограничения — `limitations`; безопасность — `safety`; решение и результат — `approvals`, `history`,
  `execution`, `measurement`.
- `exposure` (UI «Расход с признаками неэффективности ≈») — всегда `estimated`; в БД это `findings.lost`.
  `exposure_overlap = true` — часть суммы уже учтена в другой карточке, в итог «Сегодня» она входит один раз
  (ECONOMICS.md). `can_save` («Можно сэкономить ≈») — прогноз эффекта **своей формулой**; нет обоснованной формулы
  (например, «проверить») — `unavailable`, а не копия `exposure`.
- `approvals` — одобрения текущей версии, засчитываемые в кворум (§4.1); `risk.required_approvals` — сколько нужно.
- `explanation.text` — готовый текст (`llm` или `template`); все числа в нём — из `evidence` (AI_GOVERNANCE.md).
  `action` — то, что выдало правило (`type`, параметры, `reversible`); текущее и новое значение — в предпросмотре (§6.1).
- `safety.policy_reasons` — почему уровень ниже, чем просило правило: `data_sufficiency_low` /
  `data_sufficiency_medium`, `strategy_unknown`, `data_partial`, `capability_unsupported`.
- `history[].event` — события DATA_MODEL.md §8.3 (`created`, `seen_again`, `viewed`, `delivered`, `postponed`,
  `rejected`, `recommendation_checked`, `manual_claimed`, `approval_granted`, `approved`, `execution_*`, `cancelled`,
  `rollback_*`, `verification_*`, `measured`, `measurement_skipped`). `actor`: `system` или
  `{"user_id": "u_…", "name": "…"}` — имя только участникам той же организации.
- `object.name` — название кампании для пользователя. В LLM оно не уходит (AI_GOVERNANCE.md).

## 6. Действия — `POST /workspaces/{ws}/recommendations/{id}/actions`

Фронтенд отправляет **действие**, а не новый статус. Статус вычисляет бэкенд.

```json
{"action": "approve_and_apply", "version_id": "rv_77a01", "preview_id": "pv_3c9"}
{"action": "postpone", "version_id": "rv_77a01", "until": "2026-10-09"}
```

`action` — §4; `version_id` — версия, на которую смотрел пользователь, обязательна; `preview_id` — для `approve`,
`approve_and_apply`: какой предпросмотр видел пользователь, обязателен (из него берётся `precondition_hash`); `until` —
только и обязательно для `postpone`; `comment` — только для `reject`, до 500 символов, в LLM и уведомления не уходит.
Время события и `execution_date` (день выполнения в поясе данных) задаёт **сервер**: от него зависят окна замера.

Ответ: `200` — обновлённая `Recommendation`. `apply` / `approve_and_apply` / `rollback` асинхронны: `202` и
`execution_status` (или `rollback_status`) = `pending`; итог — опросом `GET` той же рекомендации. Повтор действия, уже
ставшего текущим состоянием (двойной клик), → `200` без новой записи.

Проверки по порядку: (1) доступ к workspace → иначе `404`; (2) формат → `400 invalid_request`; (3) `version_id`
последний (кроме `rollback`: аудит создаёт новые версии, откат от них не зависит) → `409 version_outdated` (в ответе актуальная рекомендация); (4) переход допустим из текущего `status` →
`409 invalid_transition`; (5) действие в `allowed_actions` → иначе `422 action_unavailable` с `reason` из §4
(`role_forbidden` → `403 forbidden_role`); (6) для `approve*`: предпросмотр не истёк и его `precondition_hash` совпадает
с уже данными одобрениями → иначе `422 action_unavailable` с `state_changed`.

### 6.1 Предпросмотр — `POST /workspaces/{ws}/recommendations/{id}/preview`

Читает текущие параметры объекта из Директа, проверяет capability и показывает «Было → Станет». Без записи в Директ.

```json
{
  "preview_id": "pv_3c9", "version_id": "rv_77a01",
  "changes": [{"object": {"type": "campaign", "id": "51234567"}, "parameter": "daily_budget",
               "before": "Value", "after": "Value"}],
  "reversible": true, "risk_level": "critical", "required_approvals": 2,
  "precondition_hash": "sha256:9b1e…",
  "approvals": [{"user": {"user_id": "u_2", "name": "…"}, "at": "…", "expires_at": "…"}],
  "expires_at": "2026-10-02T09:45:00+03:00"
}
```

- `before` — `actual`, прочитано из Директа сейчас; `after` — результат действия. Предпросмотр живёт 30 минут.
- `precondition_hash` — хэш ожидаемого состояния (объект, параметр, текущее значение, действие, целевое значение).
  Повторный предпросмотр при том же текущем значении даёт тот же хэш. `approvals` — уже данные одобрения с этим хэшем.
- Действие не поддерживается для типа кампании/стратегии, поле неизменяемо или объект архивирован → `422
  action_unavailable` с `capability_unsupported`.
- Перед записью воркер перечитывает объект: значение изменилось → записи нет, `execution.error_code = state_changed`,
  рекомендация снова `requires_decision`. Одобрение действует 24 ч, истёкшее в кворум не входит (`approval_expired`).

### 6.2 Откат

`{"action": "rollback", "version_id": "…"}` с `Idempotency-Key` → `202`, `rollback_status = pending`; одно одобрение.
Гейт (EXECUTION_SAFETY.md §7; последней версии вывода **не** требует): успешное исполнение через API · не прошло 7 дней
(`execution.rollback_until`) · текущее значение == `applied_value` · право approve · подключение `connected` и
`write_access = granted` · capability поддерживает обратное изменение. Равно → возвращает прежнее (`succeeded`); не
равно → записи нет, `blocked`, `rollback_reason = state_changed_since_execution` с текущим значением в тексте.

## 7. `measurement` — результат замера

```json
{"status": "measured", "verdict": "effect", "method": "uncontrolled_before_after",
 "windows": {"before": {"from": "2026-09-17", "to": "2026-09-23"}, "after": {"from": "2026-09-25", "to": "2026-10-01"}},
 "before": {"cpa": "Value", "conversions": "Value"}, "after": {"cpa": "Value", "conversions": "Value"},
 "saved": "Value", "counts_in_saved_total": true}
```

- `status`: `pending` (окно «после» ещё идёт) · `measured` · `skipped` (подписка или подключение неактивны). Замер
  создаётся только после `applied` с `execution_mode = api | manual`; у `none`, `rejected`, `postponed` его нет.
- `method`: в v1.0 только `uncontrolled_before_after`; `matched_control`, `experiment` зарезервированы. Подпись под
  «Сэкономлено ≈»: «Расчётный эффект · Сравнение 7 дней до и после без контрольной группы».
- `verdict`: `effect` · `no_effect` · `not_confirmed` (CPA снизился, но конверсий меньше) · `insufficient`.
- `saved` есть **только при `verdict = effect`** и всегда `estimated` с формулой.
- `counts_in_saved_total` — входит ли `saved` в «Сэкономлено ≈»: `true` только при `api` + `succeeded` или
  `manual` + `verification_status = confirmed`. Неподтверждённое ручное выполнение показывает наблюдаемый эффект, но в
  «Сэкономлено» не входит. Успешный откат → `false`.
- Проблема, ушедшая сама (без действий), в «Сэкономлено» не входит. «Возвращено» и «заработано» не пишем.

## 8. Экраны

### `GET /workspaces/{ws}/today` — «Сегодня»

```json
{
  "access": "paid", "today": "2026-10-02", "last_audit_at": "2026-10-02T07:01:54+03:00", "spent": "Value",
  "exposure": {"total": "Value", "overlap": "Value", "version": "exposure_total@1", "formula": "Σ по кабинетам max(...)",
               "components": [{"issue_type": "high_cpa", "amount": "Value"}],
               "coverage": {"included": 3, "unavailable": 1}},
  "can_save": {"total": "Value", "overlap": "Value", "components": [], "coverage": {"included": 2, "unavailable": 2}},
  "saved": "Value", "conversions": "Value", "counts": {"new": 2, "requires_decision": 3, "approved": 0, "postponed": 1},
  "top": ["RecommendationListItem — до 5"],
  "recent_actions": [{"recommendation_id": "rec_8f2c1", "title": "CPA выше целевого", "event": "execution_succeeded", "at": "…"}],
  "changes": {"period": {"from": "2026-09-30", "to": "2026-10-01"}, "spent_delta_pct": "Value", "conversions_delta_pct": "Value", "cpa_delta_pct": "Value"},
  "data_freshness": {"yandex_direct": {"status": "connected", "data_to": "2026-10-01"},
                     "yandex_metrika": {"status": "permission_missing", "data_to": null}}
}
```

- `exposure` — «Расход с признаками неэффективности ≈ N ₽» по активным рекомендациям последних аудитов всех кабинетов
  workspace, включённых в анализ. **Не сумма карточек:** `total` считает `audit/exposure.py` по объединению
  затронутого расхода (ECONOMICS.md); `components` — по типам проблем, `overlap` — сколько вычтено как пересечение,
  `version` и `formula` — как посчитано. Пояснение в UI: «Оценка расходов, по которым система обнаружила признаки
  неэффективности. Одна и та же сумма учитывается в итоге только один раз». `coverage` — сколько рекомендаций без
  числа в итог не попали. `can_save` — тем же способом.
- `saved` — только замеры с `counts_in_saved_total = true`. Пока таких нет — `unavailable`, а не `0`.
- `last_audit_at = null` → аудита ещё не было: экран «Подключите Директ», без нулей и демо-цифр.

`access`: `free_audit` — результат одного бесплатного аудита, действия кроме API-исполнения доступны, плашка «Мониторинг
продолжится после подключения тарифа» · `paid` — всё по тарифу · `inactive` — подписка закончилась: прошлые данные
только для чтения, новых аудитов, исполнений и замеров нет.

### `GET /workspaces/{ws}/analytics` — «Аналитика»

Параметры: `from`, `to` (не больше 90 дней), `group` (`day` · `campaign`), `ad_account` (по умолчанию — все включённые
в анализ). Ответ: итоги и ряды — расход, клики, конверсии, CPA, CTR (каждое — `Value`), изменения к предыдущему
периоду, exposure и возможности экономии, строки по кампаниям. Выручка и ROI — только при подключённом источнике и
достаточности данных, иначе `unavailable`. Аналитика не BI: произвольных измерений и конструктора отчётов нет.

### `GET /workspaces/{ws}/integrations` — «Настройки → Интеграции»

```json
{"items": [{"provider": "yandex_direct", "status": "connected", "account": "client-login", "write_access": "granted",
            "last_success_at": "…", "data_to": "2026-10-01", "error_code": null,
            "ad_accounts": [{"id": "acc_2", "login": "client-login", "selected": true, "status": "active"}]}]}
```

`status` — DATA_MODEL.md §8.1. `write_access`: `granted` · `denied` · `unknown`; от него зависит `write_access_missing`
(§4). Подключений Директа и кабинетов в workspace может быть несколько: `PATCH …/integrations/ad-accounts/{id}`
`{selected}` включает кабинет в анализ; сверх лимита `max_ad_accounts` → `422 action_unavailable` с
`entitlement_exceeded`. Workspace организации-агентства подключает Директ только после подтверждения мандата клиента
(`POST /workspaces/{ws}/legal/agency-client-mandate` `{version}`, LEGAL.md); без него → `422 acceptance_required`.

## 9. «Спросить AI» — `POST /workspaces/{ws}/ai/ask`

```json
{"question": "Почему вырос расход с признаками неэффективности?",
 "context": {"screen": "today", "recommendation_id": null, "period": {"from": "2026-09-25", "to": "2026-10-01"}}}
```

`screen`: `today` · `recommendations` · `recommendation` · `analytics`. Ответ:

```json
{"summary": "Рост ≈ 4 200 ₽ в основном по одной кампании…",
 "claims": [{"text": "Расход с признаками неэффективности вырос ≈ на 4 200 ₽", "evidence_ids": ["e1"]},
            {"text": "CPA кампании выше целевого на 25%", "evidence_ids": ["e2", "e3"]}],
 "evidence": [{"id": "e1", "kind": "metric_change", "fact": "exposure_delta", "value": "4200.00"},
              {"id": "e2", "kind": "metric_change", "recommendation_id": "rec_8f2c1", "fact": "cpa"},
              {"id": "e3", "kind": "finding", "recommendation_id": "rec_8f2c1", "fact": "cpa_vs_target_pct", "value": "25"}],
 "data_sufficiency": "sufficient"}
```

- Ответ — `summary` и `claims`; каждое утверждение ссылается на факты `evidence`, числа утверждения — в цитируемых
  фактах. Утверждение без доказательства отбрасывается; не осталось ни одного или отброшено утверждение `summary` —
  шаблонный ответ, собранный кодом. Правила валидации — AI_GOVERNANCE.md.
- ID в ответе — наши (`rec_…`, ссылки на объекты рекомендаций), не ID Яндекса: в LLM уходят непрозрачные ссылки,
  обратная подстановка — на сервере после валидации.
- **Только чтение.** У модели нет инструментов записи. Просьба «снизь ставку» → ссылка на существующую рекомендацию
  или «такой рекомендации нет»; исполнение — только через обычный поток рекомендации (§6).
- Данных нет → `data_sufficiency = insufficient` и прямой ответ «Недостаточно данных» с тем, что подключить.
- Истории вопросов и ответов в кабинете нет: текст вопроса не пишется в обычные логи, хранятся только технические
  метаданные (время, экран, исход) — ARCHITECTURE.md §2.5. Лимит — по тарифу и `429 rate_limited`.

## 10. Организация, команда, роли

`GET /me` — пользователь, организации и доступные workspace с ролями:

```json
{"user": {"id": "u_1", "phone": "+7 ••• ••• 12 34", "email": null},
 "organizations": [{"id": "org_1", "name": "Агентство", "kind": "agency", "org_role": "member",
   "workspaces": [{"id": "ws_1", "name": "Клиент А", "ws_role": "approver"},
                  {"id": "ws_2", "name": "Клиент Б", "ws_role": "viewer"}]}]}
```

`owner` / `admin` получают все workspace организации с `ws_role: null` (полные права по `org_role`); `member` — только
те, где есть `ws_role`. Агентство переключает клиентов сменой `{workspace_id}` в пути — «активного workspace» в сессии нет.

| Роль | Смотреть | decide (`view`, `postpone`, `reject`, `check`, `mark_done_manually`) | approve (`approve`, `cancel`, `rollback`) | execute (`apply`) | Команда, интеграции, биллинг |
|---|---|---|---|---|---|
| org `owner` | все ws | да | да | да | да |
| org `admin` | все ws | да | да | да | да (кроме удаления организации) |
| org `member` | только ws со своей ролью | по `ws_role` | по `ws_role` | по `ws_role` | нет |
| ws `approver` | да | да | да | да | нет |
| ws `analyst` | да | да | нет | только одобренного | нет |
| ws `viewer` | да | только `view` | нет | нет | нет |

**`approve` ≠ `execute`.** Без права approve одобрение не создать; execute исполняет только уже одобренную версию.

Управление — только `owner` / `admin`: `GET/POST /organizations/{org}/invitations`;
`PATCH/DELETE /organizations/{org}/members/{user}` (`org_role`; удаление снимает и все ws-роли; последнего `owner`
удалить или понизить нельзя — `409 last_owner`; назначать, менять и удалять `owner` может только `owner`); `GET /workspaces/{ws}/members`,
`PUT/DELETE /workspaces/{ws}/members/{user}` `{ws_role}` — только для участника той же организации, иначе `404`.
`PATCH /workspaces/{ws}/settings` `{approval_policy}` — owner/admin; снизить `critical` до 1 — только owner
(`403 forbidden_role`), изменение пишется в журнал.

## 11. Вход по номеру телефона

| Метод | Путь | Тело / ответ |
|---|---|---|
| POST | `/auth/code/request` | `{phone}` → **всегда `202`** с одинаковым телом: зарегистрирован ли номер, не раскрывается |
| POST | `/auth/code/verify` | `{phone, code, accepted?: {offer, pd_consent, marketing?}}` → `200` + cookie сессии |
| POST | `/auth/logout` | → `204` |

- `phone` — российский мобильный, нормализуется в E.164 (`+7…`); иной формат → `400 invalid_request`. Код — 6 цифр,
  SMS российского провайдера, живёт 5 минут, одноразовый, до 5 попыток ввода.
- Лимиты: повторный код не чаще 1 раза в 60 с; 5 кодов в час на номер и 20 на IP → `429 rate_limited` + `Retry-After`.
- Неверный, истёкший, использованный или исчерпавший попытки код — один ответ `401 invalid_code`.
- Регистрация и вход — один поток. Номер новый и `accepted` без текущих версий `offer` и `pd_consent` →
  `422 acceptance_required` (код не гасится, пока не истёк); пользователь создаётся только вместе с принятием
  (`legal_acceptances` с хэшем текста, языком, IP и user agent).
- Пароля и входа по email нет; email — необязательный контакт для чеков (`PATCH /me` `{email}`). Яндекс OAuth — только
  подключение Директа и Метрики (`/workspaces/{ws}/integrations/{provider}/connect`), не вход.
- Законность входа по SMS (ст. 10 149-ФЗ) — открытый пункт LEGAL.md; до заключения юриста регистрация на HOLD.

## 12. Ошибки

```json
{"error": {"code": "action_unavailable", "reason": "data_partial",
           "message": "Данные за последние дни ещё уточняются — применить через API пока нельзя.", "request_id": "3f1c…"}}
```

| HTTP | `code` | Когда |
|---|---|---|
| 400 | `invalid_request` | тело не по схеме, лишние поля, `until` вне диапазона, неверный формат номера |
| 401 | `unauthenticated` · `invalid_code` | нет сессии · код не принят |
| 403 | `csrf_rejected` · `forbidden_role` · `access_denied` | чужой `Origin` · роль · `access` (например, `inactive`) |
| 404 | `not_found` | нет объекта или нет доступа к workspace |
| 409 | `version_outdated` · `invalid_transition` · `idempotency_conflict` · `last_owner` | |
| 410 | `workspace_deleted` | workspace в удалении |
| 422 | `action_unavailable` (+ `reason`, §4) · `acceptance_required` | |
| 429 | `rate_limited` | + заголовок `Retry-After` |
| 500 | `internal` | без деталей и стека; `request_id` есть всегда |

`message` — текст для пользователя на русском. Логику фронтенд строит по `code` и `reason`.

## 13. Биллинг (кратко)

`GET /organizations/{org}/billing` — тариф, статус подписки, дата следующего списания, лимиты и использование
(`{"limits": {"max_workspaces": 10, "max_members": 5, …}, "usage": {…}}` — PRD §7).
`POST …/billing/checkout`, `POST …/billing/cancel`, `POST …/billing/payment-method/refuse` — с `Idempotency-Key`.
Отказ от способа оплаты — отдельно от отмены подписки: подписка может продолжиться с ручной оплатой, списаний с отозванного способа больше нет (LEGAL.md, 376-ФЗ).

## 14. Чего нет в v1.0

Автоматизации по заранее одобренным правилам (режимы безопасности — v2.0); создания действия из «Спросить AI» и кросс-аккаунтного портфеля агентства (v1.1); CRM и VK Реклама (v2.0). Полный список — [VERSION_SCOPE.md](VERSION_SCOPE.md).
