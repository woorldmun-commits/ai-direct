# API-контракт frontend ↔ backend — v1.0

Слой между бэкендом и фронтендом. Описывает **бизнес-сущности**, а не таблицы: фронтенд не знает про `issues`,
`findings`, `snapshots` и `recommendation_events`. Схема БД может меняться — контракт нет (только новой версией).

Основа — [PRD.md](PRD.md) v1.0: 4 раздела кабинета (Сегодня · Рекомендации · Аналитика · Настройки), «Спросить AI»,
применение через Direct API после одобрения, агентства и роли. Источники правды, которые контракт отражает и не
переопределяет: `Value` — `backend/app/contract.py` и DATA_MODEL.md §5; уровни действия — `app/audit/policy.py`;
жизненный цикл рекомендации — DATA_MODEL.md §8.3.

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

  Деньги никогда не JSON-number: без потери точности `Decimal`. Отрицательных сумм потерь, «можно сэкономить» и
  «сэкономлено» нет (CHECK в БД).
- **Аутентификация** — сессия в httpOnly cookie (§11). Сессия определяет пользователя, но не workspace.
- **Workspace — в пути:** `/api/v1/workspaces/{workspace_id}/…`. Бэкенд проверяет членство пользователя в организации
  workspace на каждом запросе. Нет доступа или нет workspace → `404`, а не `403`: существование чужих данных не
  раскрывается — тело и время ответа такие же, как у несуществующего id. Это же действует для вложенных объектов.
- Изменяющие запросы — только с `Origin` нашего сайта и cookie `SameSite=Lax`; иначе `403 csrf_rejected`.
- **`Idempotency-Key`** (UUID) — **обязателен** для `approve`, `apply`, `rollback`, `cancel` и всех запросов биллинга;
  для остальных `POST` — по желанию. Повтор с тем же ключом и тем же телом → тот же ответ без повторного действия;
  с тем же ключом и другим телом → `409 idempotency_conflict`. Ключ живёт 24 часа.
- **`X-Request-Id`** — в каждом ответе; клиент может прислать свой (UUID), иначе бэкенд генерирует. Он же в теле
  ошибки (§12) — по нему поддержка находит запрос в логах.
- В ответах нет: OAuth-токенов, хэшей паролей, `snapshot_id`, внутренних id таблиц, текстов поисковых запросов.
- Фронтенд **не считает** бизнес-значения и не решает, какие действия разрешены: показывает `allowed_actions` и
  `Value` как пришли. Суммы, проценты и знак «≈» получаются из полей, а не вычисляются.

## 2. `Value` — любое число

```json
{
  "amount": "12500.00",
  "unit": "rub",
  "calculation_type": "estimated",
  "source": "yandex_direct+yandex_metrika",
  "period": {"from": "2026-09-22", "to": "2026-09-28"},
  "data_status": "complete",
  "data_sufficiency": "sufficient",
  "formula": "(cpa - target_cpa) * conversions",
  "rule_version": "high_cpa_target@1"
}
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
| `formula` | строка или `null` | |
| `rule_version` | `имя@N` или `null` | |

Названия — те же, что в `app/contract.py`. Это `Value` бэкенда без `snapshot_id` и с `period` вместо
`period_from` / `period_to`.

**Инварианты (проверяет бэкенд):** `calculation_type = unavailable` ⇔ `data_sufficiency = insufficient` ⇔
`amount = null`; `calculation_type = estimated` ⇒ `formula` не пустая.

**Как показывать (обязательно для фронтенда):**

| `calculation_type` | Показ |
|---|---|
| `actual` | `18 400 ₽` — без «≈» |
| `estimated` | `≈ 12 500 ₽`, формула — в подсказке «Как посчитано» |
| `unavailable` | «Недостаточно данных» — **никакого числа, нуля или прочерка вместо числа** |

`data_status = partial` → пометка «данные за последние дни могут уточниться». Тип в TypeScript строится так, чтобы
ошибку нельзя было скомпилировать: `amount: string` только в ветках `actual | estimated`, `amount: null` — в `unavailable`.

## 3. Жизненный цикл рекомендации

Состояние рекомендации — **один основной `status`** и независимые поля исполнения, проверки, отката и замера.
`status` отвечает за жизненный цикл, `execution_mode` — за то, что фактически произошло с действием.

### 3.1 `status` — 8 значений (PRD §5)

| `status` | В UI | Смысл |
|---|---|---|
| `new` | Новая | создана, пользователь ещё не открывал |
| `requires_decision` | Требует решения | просмотрена или доставлена, активна, ждёт решения человека; у агентства — в т. ч. одобрения нужной роли |
| `approved` | Одобрена | одобрена конкретная версия действия, исполнение ещё не завершено |
| `applied` | по `execution_mode` (§3.3) | действие завершено: применено через API, выполнено вручную или проверено |
| `postponed` | Отложена | «Позже» до `postponed_until`, затем снова `requires_decision` |
| `rejected` | Отклонена | «Не буду» |
| `failed` | Не выполнена | AdPilot пытался применить через API, исполнение не завершилось успехом |
| `cancelled` | Отменена | одобрена, но исполнение отменено до его начала |

```
new ──▶ requires_decision ──▶ approved ──▶ applied
             │      ▲             │  └──▶ failed
             │      │             └──▶ cancelled
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
| `rollback_status` | `not_requested` · `pending` · `succeeded` · `failed` | откат после `applied` через API; **не статус рекомендации** |
| `measurement` | объект или `null` | результат замера через 7 дней (§7), не статус |

Допустимые сочетания для `status = applied`:

| Сценарий | `execution_mode` | `execution_status` | `verification_status` |
|---|---|---|---|
| Применено через API | `api` | `succeeded` | `confirmed` (AdPilot перечитал объект после изменения) |
| Выполнено вручную, до сверки | `manual` | `claimed_manual` | `pending` |
| Выполнено вручную, сверка нашла изменение | `manual` | `claimed_manual` | `confirmed` |
| Выполнено вручную, изменения нет | `manual` | `claimed_manual` | `not_confirmed` |
| «Проверил» (рекомендация «проверить») | `none` | `not_started` | `not_required` |

Факт исполнения через API фиксируется явно (`api` + `succeeded`) и не выводится из `status`.

### 3.3 Подписи результата в UI

Слово «Применена» для `applied` не показывается. Текст — из `execution_mode` и `verification_status`:

| Поля | Текст |
|---|---|
| `api` | «Применено» |
| `manual` + `pending` | «Выполнено вручную пользователем. Результат изменения пока не подтверждён» |
| `manual` + `confirmed` | «Выполнено вручную. Изменение подтверждено по данным Директа» |
| `manual` + `not_confirmed` | «Выполнено вручную. Выполнение не подтверждено» |
| `none` | «Проверено» |
| `rollback_status = succeeded` | дополнительно: «Изменение отменено (откат)» |

Сверка ручного выполнения требует синхронизации текущих параметров затронутого объекта из Директа (ставка, бюджет и
т. п. — по типу действия; ARCHITECTURE.md §4.2). Пока её нет, ручное выполнение остаётся `verification_status = pending`;
автоматически «подтверждённым» оно не становится никогда.

## 4. Действия пользователя и `allowed_actions`

`action_level` назначает политика безопасности (`safety_policy@N`, только понижает уровень правила):
`inspect_only` («Проверить») < `review` («Проверьте перед изменением») < `change` («Можно изменить»).

| Действие | Переход | Кто (роль, §10) | Условия |
|---|---|---|---|
| `view` | `new → requires_decision` | любой участник | идемпотентно; фронтенд шлёт при открытии паспорта |
| `postpone` | `requires_decision → postponed` | decide | `until`: от завтра до +90 дней |
| `reject` | `requires_decision → rejected` | decide | `review` / `change` |
| `check` | `requires_decision → applied` (`none`) | decide | только `inspect_only` |
| `mark_done_manually` | `requires_decision → applied` (`manual`) | decide | `review` / `change` |
| `approve` | `requires_decision → approved` | approve | `change`; данные полные; есть право записи в Директ |
| `apply` | `approved → applied` / `failed` | execute | `approval_mode = two_step`; одобренная версия всё ещё последняя |
| `approve_and_apply` | `requires_decision → approved → applied` / `failed` | approve **и** execute | `approval_mode = single_step` (SMB, «Применить»); условия `approve` |
| `cancel` | `approved → cancelled` | approve | исполнение ещё не начато |
| `rollback` | `rollback_status: not_requested → pending → …` | execute | `applied` через API, изменение технически откатываемо |

`postponed` можно решить раньше даты: из `postponed` доступны те же действия, что из `requires_decision`.

**`allowed_actions` считает только бэкенд**, минимум из: роли пользователя, `status`, `action_level`, `approval_mode`
workspace, полноты данных (`data_status`), права записи в Директ (`write_access`) и лимитов тарифа. Фронтенд рисует
кнопки только из `allowed_actions`; недоступные — из `blocked_actions` с причиной, чтобы честно объяснить «почему нельзя»:

```json
"allowed_actions": ["mark_done_manually", "postpone", "reject"],
"blocked_actions": [{"action": "approve_and_apply", "reason": "data_partial"}]
```

| `reason` | Текст для пользователя |
|---|---|
| `data_partial` | «Данные за последние дни ещё уточняются — применить через API пока нельзя. Можно проверить или выполнить вручную» |
| `write_access_missing` | «Нет прав на изменение рекламного кабинета — выполните вручную или выдайте доступ» |
| `level_not_change` | «Рекомендация требует проверки — автоматическое применение недоступно» |
| `role_forbidden` | «Ваша роль не позволяет это действие» |
| `entitlement_exceeded` | «Недоступно на текущем тарифе» |
| `not_reversible` | «Это изменение нельзя откатить автоматически» |

**Критическое правило:** при `data_status != complete` действия `approve`, `apply`, `approve_and_apply` всегда в
`blocked_actions` с `data_partial` — вместо них «Проверить вручную» / «Выполнить вручную». Кнопки «Применить через API»
на неполных данных нет.

## 5. `Recommendation` — проблема, доказательства, действие

`id` — **стабильный** идентификатор на весь жизненный цикл. Каждый аудит может пересчитать цифры и действие (было
«−15%», стало «−25%») — это новая **версия**, `version_id`. UI показывает последнюю. Одобрение и ручное выполнение
относятся к конкретной версии: устарела — `409 version_outdated`, нужно новое решение.

### `RecommendationListItem` — `GET /workspaces/{ws}/recommendations`

```json
{
  "id": "rec_8f2c1", "version_id": "rv_77a01", "title": "CPA выше целевого",
  "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
  "action_level": "change", "status": "requires_decision", "execution_mode": null, "verification_status": null,
  "losses": "Value", "can_save": "Value", "data_status": "complete",
  "period": {"from": "2026-09-22", "to": "2026-09-28"},
  "created_at": "2026-09-29T07:02:11+03:00", "updated_at": "2026-10-01T07:01:54+03:00"
}
```

Фильтры раздела «Рекомендации» → параметр `filter`: `all` · `new` · `requires_decision` · `done` (`applied`) ·
`postponed` · `rejected`; по умолчанию `requires_decision` + `new`. Плюс `limit` (1–100, по умолчанию 50), `cursor`.
Ответ: `{"items": [...], "next_cursor": "…" | null}`. Порядок задаёт бэкенд: активные сначала, внутри — по
`losses.amount` по убыванию, `unavailable` — в конце. Поля `severity` нет: бэкенд её не считает.

### `Recommendation` (паспорт) — `GET /workspaces/{ws}/recommendations/{id}`

```json
{
  "id": "rec_8f2c1",
  "version_id": "rv_77a01",
  "title": "CPA выше целевого",
  "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
  "status": "requires_decision",
  "postponed_until": null,
  "action_level": "change",
  "allowed_actions": ["approve_and_apply", "mark_done_manually", "postpone", "reject"],
  "blocked_actions": [],
  "losses": "Value",
  "can_save": "Value",
  "explanation": {"text": "CPA кампании — 2 500 ₽, это на 25% выше целевого…", "source": "template"},
  "action": {"type": "decrease_bid", "change_pct": "-15.00", "reversible": true},
  "evidence": {
    "facts": {"cost": "Value", "conversions": "Value", "cpa": "Value", "cpc": "Value", "cvr": "Value"},
    "meta": {"baseline_data_quality": "high"},
    "rule_version": "high_cpa_target@1"
  },
  "safety": {"safety_policy": "safety_policy@2", "candidate_level": "change", "policy_reasons": [], "data_status": "complete"},
  "limitations": ["strategy_unknown"],
  "execution": {"execution_mode": null, "execution_status": "not_started", "verification_status": "not_required",
                "rollback_status": "not_requested", "approved_by": null, "approved_at": null, "applied_at": null, "error_code": null},
  "measurement": null,
  "history": [{"event": "created", "at": "2026-09-29T07:02:11+03:00", "actor": "system"},
              {"event": "seen_again", "at": "2026-10-01T07:01:54+03:00", "actor": "system"}],
  "created_at": "2026-09-29T07:02:11+03:00"
}
```

- **Паспорт** (PRD §5): проблема — `title`, `object`; фактические данные — `evidence.facts`; период и источник —
  в каждом `Value`; расчёт — `formula`; причина — `explanation`; действие — `action`; потенциальный эффект — `can_save`;
  ограничения — `limitations`; проверка безопасности — `safety`; решение пользователя и результат — `history`,
  `execution`, `measurement`.
- `losses` (UI «Потери ≈») — оценка неэффективного расхода за период. `can_save` (UI «Можно сэкономить ≈») — прогноз
  эффекта действия, **своей формулой**; нет обоснованной формулы (например, рекомендация «проверить») —
  `unavailable`, а не копия `losses`.
- `explanation.text` — готовый текст (`llm` или `template`). Все числа в нём взяты из `evidence`: LLM чисел не вводит.
- `action` — то, что выдало правило: `type`, параметры типа (`decrease_bid` → `change_pct`), `reversible`.
  Текущей и новой ставки здесь нет — они в предпросмотре (§6.1), прочитанные из Директа в момент запроса.
- `safety.policy_reasons` объясняют, почему уровень ниже, чем просило правило: `data_sufficiency_low` /
  `data_sufficiency_medium`, `strategy_unknown`, `data_partial`.
- `history[].event` — фактические события (DATA_MODEL.md §8.3): `created`, `seen_again`, `viewed`, `delivered`, `postponed`,
  `rejected`, `recommendation_checked`, `manual_claimed`, `approved`, `execution_started`, `execution_succeeded`,
  `execution_failed`, `cancelled`, `rollback_requested`, `rollback_succeeded`, `rollback_failed`,
  `verification_confirmed`, `verification_not_confirmed`, `measured`, `measurement_skipped`. `actor`: `system` или
  `{"user_id": "u_…", "name": "…"}` — имя только участникам той же организации.
- `object.name` — название кампании для пользователя. В LLM оно не уходит (ARCHITECTURE.md §6).

## 6. Действия — `POST /workspaces/{ws}/recommendations/{id}/actions`

Фронтенд отправляет **действие**, а не новый статус. Статус вычисляет бэкенд.

```json
{"action": "approve_and_apply", "version_id": "rv_77a01", "preview_id": "pv_3c9"}
{"action": "mark_done_manually", "version_id": "rv_77a01"}
{"action": "postpone", "version_id": "rv_77a01", "until": "2026-10-09"}
{"action": "reject", "version_id": "rv_77a01", "comment": "Кампания сезонная"}
```

| Поле | |
|---|---|
| `action` | §4 |
| `version_id` | версия, на которую смотрел пользователь; обязательна |
| `preview_id` | для `approve`, `approve_and_apply`: какой предпросмотр видел пользователь (§6.1); обязателен |
| `until` | только для `postpone`, обязательна |
| `comment` | только для `reject`, необязательна, до 500 символов. В LLM и уведомления не уходит |

Время события и `execution_date` (день выполнения в поясе данных) задаёт **сервер**: от этого дня зависят окна замера.

Ответ: `200` — обновлённая `Recommendation`. Для `apply` / `approve_and_apply` / `rollback` исполнение асинхронное:
`202` и `execution_status = pending`; итог — опросом `GET` той же рекомендации (или событием в UI). Повтор действия,
уже ставшего текущим состоянием (двойной клик), → `200` без новой записи.

Проверки по порядку: (1) workspace доступен пользователю → иначе `404`; (2) формат → `400 invalid_request`;
(3) `version_id` последний → `409 version_outdated` (в ответе актуальная рекомендация); (4) переход допустим из
текущего `status` → `409 invalid_transition`; (5) действие в `allowed_actions` → иначе `422 action_unavailable`
с `reason` из §4 (`role_forbidden` → `403 forbidden_role`).

### 6.1 Предпросмотр — `POST /workspaces/{ws}/recommendations/{id}/preview`

Читает текущие параметры объекта из Директа и показывает «Было → Станет» до одобрения. Без записи в Директ.

```json
{
  "preview_id": "pv_3c9",
  "version_id": "rv_77a01",
  "changes": [
    {"object": {"type": "campaign", "id": "51234567"}, "parameter": "daily_budget",
     "before": "Value", "after": "Value"}
  ],
  "reversible": true,
  "expires_at": "2026-10-02T09:45:00+03:00"
}
```

`before` — `actual`, прочитано из Директа сейчас; `after` — результат действия. Предпросмотр живёт 30 минут. Если к
моменту исполнения параметры в Директе изменились относительно `before`, исполнение не начинается:
`execution_status = failed`, `error_code = state_changed` — человек одобрял другое.

## 7. `measurement` — результат замера

```json
{
  "status": "measured",
  "verdict": "effect",
  "windows": {"before": {"from": "2026-09-17", "to": "2026-09-23"}, "after": {"from": "2026-09-25", "to": "2026-10-01"}},
  "before": {"cpa": "Value", "conversions": "Value"},
  "after": {"cpa": "Value", "conversions": "Value"},
  "saved": "Value",
  "counts_in_saved_total": true
}
```

- `status`: `pending` (окно «после» ещё идёт) · `measured` · `skipped` (подписка или подключение неактивны). Замер
  создаётся только после `applied` с `execution_mode = api | manual`; у `none`, `rejected`, `postponed` его нет.
- `verdict`: `effect` · `no_effect` · `not_confirmed` (CPA снизился, но конверсий меньше) · `insufficient`.
- `saved` есть **только при `verdict = effect`** и всегда `estimated` с формулой.
- `counts_in_saved_total` — входит ли `saved` в «Сэкономлено ≈». `true` только если исполнение подтверждено фактом:
  `api` + `succeeded` или `manual` + `verification_status = confirmed`. Неподтверждённое ручное выполнение
  показывает наблюдаемый эффект, но в «Сэкономлено» не входит. Откат после `applied` → `false`.
- Проблема, которая ушла сама (в следующем аудите без действий), — признак проблемы, не статус рекомендации; в
  «Сэкономлено» не входит. «Возвращено» и «заработано» не пишем.

## 8. Экраны

### `GET /workspaces/{ws}/today` — «Сегодня»

```json
{
  "access": "paid",
  "today": "2026-10-02",
  "last_audit_at": "2026-10-02T07:01:54+03:00",
  "spent": "Value",
  "losses": "Value",
  "losses_coverage": {"included": 3, "unavailable": 1},
  "can_save": "Value",
  "saved": "Value",
  "conversions": "Value",
  "counts": {"new": 2, "requires_decision": 3, "approved": 0, "postponed": 1},
  "top": ["RecommendationListItem — до 5"],
  "recent_actions": [{"recommendation_id": "rec_8f2c1", "title": "CPA выше целевого", "event": "execution_succeeded", "at": "…"}],
  "changes": {"period": {"from": "2026-09-30", "to": "2026-10-01"}, "spent_delta_pct": "Value", "conversions_delta_pct": "Value", "cpa_delta_pct": "Value"},
  "data_freshness": {
    "yandex_direct": {"status": "connected", "data_to": "2026-10-01"},
    "yandex_metrika": {"status": "permission_missing", "data_to": null}
  }
}
```

- `losses` / `can_save` — суммы по активным рекомендациям последнего аудита. Сумма оценок — тоже оценка
  (`estimated`). **Один рекламный объект входит в сумму один раз**, даже если по нему несколько рекомендаций — бэкенд
  не допускает двойного счёта. `losses_coverage` — сколько рекомендаций без числа в сумму не попали.
- `saved` — только замеры с `counts_in_saved_total = true`. Пока таких нет — `unavailable`, а не `0`.
- `last_audit_at = null` → аудита ещё не было: экран «Подключите Директ», без нулей и демо-цифр.

| `access` | Что видит пользователь |
|---|---|
| `free_audit` | Результат одного бесплатного аудита. Действия, кроме API-исполнения, доступны. Плашка: «Мониторинг продолжится после подключения тарифа» |
| `paid` | Всё по тарифу |
| `inactive` | Подписка закончилась: прошлые данные — только чтение, новых аудитов, исполнений и замеров нет |

### `GET /workspaces/{ws}/analytics` — «Аналитика»

Параметры: `from`, `to` (не больше 90 дней), `group` (`day` · `campaign`). Ответ: итоги и ряды — расход, клики,
конверсии, CPA, CTR (каждое — `Value`), изменения расходов к предыдущему периоду, выявленные потери и возможности
экономии, строки по кампаниям. Выручка и ROI — только при подключённом источнике и достаточности данных, иначе
`unavailable`. Аналитика не BI: произвольных измерений и конструктора отчётов нет.

### `GET /workspaces/{ws}/integrations` — «Настройки → Интеграции»

```json
{"items": [{"provider": "yandex_direct", "status": "connected", "account": "client-login",
            "write_access": "granted", "last_success_at": "…", "data_to": "2026-10-01", "error_code": null}]}
```

`status` — DATA_MODEL.md §8.1. `write_access`: `granted` · `denied` · `unknown` — есть ли право менять кампании;
от него зависит `write_access_missing` в §4. `error_code` — код без ПД.

## 9. «Спросить AI» — `POST /workspaces/{ws}/ai/ask`

```json
{"question": "Почему сегодня выросли потери?",
 "context": {"screen": "today", "recommendation_id": null, "period": {"from": "2026-09-25", "to": "2026-10-01"}}}
```

`screen`: `today` · `recommendations` · `recommendation` · `analytics`. Ответ:

```json
{"answer": "Потери выросли на ≈ 4 200 ₽ в основном из-за кампании «Поиск — Москва»…",
 "citations": [{"recommendation_id": "rec_8f2c1", "facts": ["losses", "cpa"]}],
 "data_sufficiency": "sufficient"}
```

- AI отвечает только по данным workspace: рекомендации, их доказательства, замеры, агрегаты аналитики за период.
  Каждое число ответа есть в цитируемых данных (та же проверка чисел, что у объяснений) — иначе ответ отбрасывается.
- Данных нет → `data_sufficiency = insufficient` и прямой ответ «Недостаточно данных» с тем, что подключить.
- Истории вопросов и ответов в кабинете нет: она не хранится как пользовательские данные, текст вопроса не пишется в обычные логи приложения. Хранятся только технические метаданные (время, экран, исход) — ARCHITECTURE.md §2.5. В LLM уходят агрегаты без названий кампаний и текстов запросов.
- Лимит — по тарифу и `429 rate_limited`.

## 10. Организация, команда, роли

`GET /me` — пользователь, организации и workspace с ролью:

```json
{"user": {"id": "u_1", "email": "owner@example.ru", "email_verified": true},
 "organizations": [{"id": "org_1", "name": "Агентство", "kind": "agency", "role": "admin",
   "workspaces": [{"id": "ws_1", "name": "Клиент А"}, {"id": "ws_2", "name": "Клиент Б"}]}]}
```

Агентство переключает клиентов сменой `{workspace_id}` в пути — скрытого «активного workspace» в сессии нет.

| Роль | Смотреть | decide (`view`, `postpone`, `reject`, `check`, `mark_done_manually`) | approve (`approve`, `cancel`) | execute (`apply`, `rollback`) | Команда, интеграции, биллинг |
|---|---|---|---|---|---|
| `owner` | да | да | да | да | да |
| `admin` | да | да | да | да | да (кроме удаления организации) |
| `approver` | да | да | да | да | нет |
| `analyst` | да | да | нет | да | нет |
| `viewer` | да | только `view` | нет | нет | нет |

**`approve` ≠ `execute`.** Роль без права approve не может создать одобрение; право execute позволяет исполнить или откатить только уже одобренную версию действия (analyst исполняет одобренное, но не одобряет).

`approval_mode` workspace: `single_step` (по умолчанию для `kind = business`: одна кнопка «Применить» = `approve_and_apply`) или `two_step` (по умолчанию для `agency`: одобряет approve-роль, исполняет роль с правом execute).

Команда: `GET/POST /organizations/{org}/invitations`, `PATCH/DELETE /organizations/{org}/members/{user}` — только
`owner` / `admin`. Последнего `owner` удалить или понизить нельзя (`409 last_owner`).

## 11. Регистрация и вход

| Метод | Путь | Тело / ответ |
|---|---|---|
| POST | `/auth/signup` | `{email, password, accepted: {offer: "2026-10-01", pd_consent: "2026-10-01", marketing?: "…"}}` → `201`, письмо подтверждения |
| POST | `/auth/verify-email` | `{token}` → `200` |
| POST | `/auth/login` | `{email, password}` → `200` + cookie сессии |
| POST | `/auth/logout` | → `204` |
| POST | `/auth/password-reset` | `{email}` → **всегда `202`**: существование email не раскрывается |
| POST | `/auth/password-reset/confirm` | `{token, password}` → `200`, все сессии пользователя отзываются |

- Без принятой оферты (`accepted.offer` — текущая версия) пользователь не создаётся: `422 acceptance_required`.
- Пароль — не короче 10 символов. Неверный email или пароль — один ответ `401 invalid_credentials`.
- До подтверждения email — вход разрешён, подключение Директа и оплата — нет (`403 email_not_verified`).
- Ограничение попыток: вход и сброс — 5 за 15 минут на email и 20 на IP → `429 rate_limited` + `Retry-After`.
- Яндекс OAuth — только подключение Директа и Метрики (`/workspaces/{ws}/integrations/{provider}/connect`), не вход.
- Соответствие ст. 10 149-ФЗ — открытый риск (PRD §10 №13, LEGAL.md).

## 12. Ошибки

```json
{"error": {"code": "action_unavailable", "reason": "data_partial",
           "message": "Данные за последние дни ещё уточняются — применить через API пока нельзя.",
           "request_id": "3f1c…"}}
```

| HTTP | `code` | Когда |
|---|---|---|
| 400 | `invalid_request` | тело не по схеме, лишние поля, `until` вне диапазона |
| 401 | `unauthenticated` / `invalid_credentials` | нет сессии / неверный email или пароль |
| 403 | `csrf_rejected` · `forbidden_role` · `access_denied` · `email_not_verified` | чужой `Origin` · роль · `access` (например, `inactive`) · email не подтверждён |
| 404 | `not_found` | нет объекта или нет доступа к workspace |
| 409 | `version_outdated` · `invalid_transition` · `idempotency_conflict` · `last_owner` | |
| 410 | `workspace_deleted` | workspace в удалении |
| 422 | `action_unavailable` (+ `reason`, §4) · `acceptance_required` | |
| 429 | `rate_limited` | + заголовок `Retry-After` |
| 500 | `internal` | без деталей и стека; `request_id` есть всегда |

`message` — текст для пользователя на русском. Логику фронтенд строит по `code` и `reason`.

## 13. Биллинг (кратко)

`GET /organizations/{org}/billing` — тариф, статус подписки, дата следующего списания, лимиты и использование
(`{"limits": {"max_workspaces": 10, "max_members": 5, …}, "usage": {"workspaces": 3, "members": 2, …}}` — PRD §7).
`POST …/billing/checkout`, `POST …/billing/cancel`, `POST …/billing/payment-method/refuse` — с `Idempotency-Key`.
Отказ от способа оплаты — отдельно от отмены подписки: подписка может продолжиться с ручной оплатой, списаний с
отозванного способа больше нет (LEGAL.md, 376-ФЗ).

## 14. Чего нет в v1.0

Автоматизации по заранее одобренным правилам (режимы безопасности, PRD §6 — v2.0); ограничения доступа участника
агентства к отдельным клиентам (роль действует на все workspace организации); CRM и VK Реклама.
