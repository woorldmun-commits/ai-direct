# API-контракт frontend ↔ backend — v1.0

Слой между бэкендом и фронтендом. Описывает **бизнес-сущности**, а не таблицы: фронтенд не знает про `issues`,
`findings`, `snapshots` и `recommendation_events`. Схема БД может меняться — контракт нет (только новой версией).

**Контракт v1.0 — только то, что продукт обещает сейчас** ([STRATEGY.md](STRATEGY.md),
[VERSION_SCOPE.md](VERSION_SCOPE.md)): чтение данных, аудит по трём правилам, рекомендации с доказательствами, решение
человека, ручное выполнение, сверка по данным Директа и замер эффекта. **AdPilot v1.0 не изменяет рекламные
кабинеты:** запросов, пишущих в Директ или Метрику, в контракте нет — изменения вносит человек вручную. Исполнение через
Direct API и «Спросить AI» — v1.1 ([API_CONTRACT_EXECUTION.md](API_CONTRACT_EXECUTION.md),
[EXECUTION_SAFETY.md](EXECUTION_SAFETY.md)).

Источники правды (контракт их не переопределяет): `Value` — `app/contract.py`, DATA_MODEL.md §5; уровни действия —
`app/audit/policy.py`; exposure — ECONOMICS.md; объяснения — AI_GOVERNANCE.md; жизненный цикл — DATA_MODEL.md §8.3.

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
  «Изменяющие» — меняют данные AdPilot (решение, настройки, команда), а не рекламный кабинет.
- **`Idempotency-Key`** (UUID) — **обязателен** для биллинга (§13); для остальных `POST` — по желанию. Тот же ключ и
  тело → тот же ответ без повторного действия; тот же ключ и другое тело → `409 idempotency_conflict`. Ключ живёт 24 часа.
- **`X-Request-Id`** — в каждом ответе; клиент может прислать свой (UUID). Он же в теле ошибки (§12).
- В ответах нет: OAuth-токенов, хэшей кодов и сессий, `snapshot_id`, внутренних id таблиц, текстов поисковых запросов.
- Фронтенд **не считает** бизнес-значения и не решает, какие действия разрешены: показывает `allowed_actions` и
  `Value` как пришли. Суммы, проценты и знак «≈» получаются из полей, а не вычисляются.
- **Совместимость:** клиент игнорирует незнакомые поля. Новые значения перечислений (статусы v1.1) приходят только
  клиенту, который заявил поддержку контракта v1.1 (API_CONTRACT_EXECUTION.md §1).

## 2. `Value` — любое число

```json
{"amount": "12500.00", "unit": "rub", "calculation_type": "estimated",
 "source": "yandex_direct+yandex_metrika", "period": {"from": "2026-09-22", "to": "2026-09-28"},
 "data_status": "complete", "data_sufficiency": "sufficient",
 "formula": "(cpa - target_cpa) * conversions", "rule_version": "high_cpa_target@1", "unavailable_reason": null}
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
| `unavailable_reason` | код или `null` | почему числа нет — только и обязательно при `unavailable` |

Названия — как в `app/contract.py`: `Value` бэкенда без `snapshot_id` и с `period` вместо `period_from`/`period_to`.
**Инварианты (проверяет бэкенд):** `unavailable` ⇔ `insufficient` ⇔ `amount = null` ⇔ `unavailable_reason` не `null`;
`estimated` ⇒ `formula` не пустая.

`unavailable_reason` — закрытый список, сверен с `Reason` правил (`rules/domain.py`); тексты — словарь фронтенда:
`source_missing` (источник не подключён или не отдал данные) · `no_conversions` (нет конверсий) · `history_insufficient`
(мало истории для сравнения) · `volume_insufficient` (мало расхода, кликов, конверсий) · `no_forecast` (нет обоснованной
формулы прогноза — «проверить») · `no_data` (нет значений; так же отдаются записи до миграции 0004 без причины).

| `calculation_type` | Показ (обязательно для фронтенда) |
|---|---|
| `actual` | `18 400 ₽` — без «≈» |
| `estimated` | `≈ 12 500 ₽`, формула — в подсказке «Как посчитано» |
| `unavailable` | «Недостаточно данных» + текст причины по `unavailable_reason` — **без числа, нуля или прочерка** |

`data_status = partial` → «данные за последние дни могут уточниться». Тип TypeScript не даёт скомпилировать ошибку:
`amount: string` только в `actual | estimated`; `amount: null` и `unavailable_reason` — только в `unavailable`.

## 3. Жизненный цикл рекомендации

Состояние — **один основной `status`** и независимые поля выполнения, сверки и замера. `status` отвечает за
решение человека, `execution_mode` — за то, что фактически произошло с действием.

### 3.1 `status` — 6 значений

| `status` | В UI | Смысл |
|---|---|---|
| `new` | Новая | создана, пользователь ещё не открывал |
| `requires_decision` | Требует решения | просмотрена, ждёт решения человека |
| `accepted` | Принята к выполнению | человек согласился и сделает изменение в кабинете сам; сервер зафиксировал `before_state` |
| `applied` | по `execution_mode` (§3.3) | выполнено пользователем вручную или проверено («Проверил») |
| `postponed` | Отложена | «Позже» до `postponed_until`, затем снова `requires_decision` |
| `rejected` | Отклонена | «Не буду» с причиной (§4.1) |

```
new ──view──▶ requires_decision ──accept──▶ accepted ──mark_done_manually──▶ applied (manual)
                 │   ▲                         │                                │
                 │   └──(дата)── postponed ◀───┤ postpone                      ├─ сверка по данным Директа (чтение)
                 ├──▶ postponed                 └──▶ rejected (reason)          └─ +7 дней ─▶ measurement
                 ├──▶ rejected (reason)
                 ├──mark_done_manually──▶ applied (manual)   уже сделал, без отдельного «Принять»
                 └──check──────────────▶ applied (none)     «Проверил» — только inspect_only
```

### 3.2 Поля выполнения

| Поле | Значения | |
|---|---|---|
| `execution_mode` | `manual` · `none` · `null` | `null` — пока ничего не выполнено; `manual` — пользователь **заявил**, что сделал сам (это не факт исполнения); `none` — исполнять было нечего («Проверил») |
| `verification_status` | `not_required` · `pending` · `confirmed` · `not_confirmed` · `null` | подтверждено ли ручное изменение по данным Директа (§6.1) |
| `measurement` | объект или `null` | результат замера через 7 дней (§7), не статус |

| Сценарий | `status` | `execution_mode` | `verification_status` |
|---|---|---|---|
| Принята, ещё не выполнена | `accepted` | `null` | `null` |
| Выполнено вручную, до сверки | `applied` | `manual` | `pending` |
| Выполнено вручную, сверка нашла изменение | `applied` | `manual` | `confirmed` |
| Выполнено вручную, изменения нет | `applied` | `manual` | `not_confirmed` |
| «Проверил» (рекомендация «проверить») | `applied` | `none` | `not_required` |

### 3.3 Подписи результата в UI

Слово «Применена» для `applied` не показывается. Текст — из `execution_mode` и `verification_status`:

| Поля | Текст |
|---|---|
| `status = accepted` | «Принята к выполнению. Внесите изменение в кабинете Директа и отметьте „Выполнено“» |
| `manual` + `before_state.reliability = reduced` | к тексту сверки: «Исходное состояние зафиксировано в момент отметки — сверка менее надёжна» |
| `manual` + `pending` | «Выполнено вручную пользователем. Результат изменения пока не подтверждён» |
| `manual` + `confirmed` | «Выполнено вручную. Изменение подтверждено по данным Директа» |
| `manual` + `not_confirmed` | «Выполнено вручную. Выполнение не подтверждено» |
| `none` | «Проверено» |

## 4. Действия пользователя и `allowed_actions`

`action_level` назначает политика безопасности (`safety_policy@N`, только понижает уровень правила):
`inspect_only` («Проверить») < `review` («Проверьте перед изменением») < `change` («Можно изменить»). Уровень `change`
значит «изменение допустимо, человек вносит его сам», а не «AdPilot применит».

| Действие | Переход | Право (§10) | Условия |
|---|---|---|---|
| `view` | `new → requires_decision` | любой с доступом | идемпотентно; фронтенд шлёт при открытии паспорта |
| `accept` | `requires_decision → accepted` | decide | `review` / `change`; сервер читает параметры объекта и фиксирует `before_state` (§6.1) |
| `mark_done_manually` | `requires_decision` / `accepted` → `applied` (`manual`) | decide | `review` / `change` |
| `check` | `requires_decision → applied` (`none`) | decide | только `inspect_only` |
| `postpone` | `requires_decision` / `accepted` → `postponed` | decide | `until`: от завтра до +90 дней |
| `reject` | `requires_decision` / `accepted` → `rejected` | decide | `review` / `change`; `reason` обязателен (§4.1) |

`postponed` можно решить раньше даты: из него доступны те же действия, что из `requires_decision`. Неполные данные
(`data_status = partial`) действия v1.0 не блокируют — все они ручные; в паспорте видна пометка, что данные уточняются.

**`allowed_actions` считает только бэкенд** — из роли, `status`, `action_level` и `access` (§8). Фронтенд рисует
кнопки только из `allowed_actions`; недоступные — из `blocked_actions` с причиной:

```json
"allowed_actions": ["accept", "mark_done_manually", "postpone", "reject"],
"blocked_actions": []
```

| `reason` | Текст для пользователя |
|---|---|
| `role_forbidden` | «Ваша роль не позволяет это действие» |
| `access_inactive` | «Подписка закончилась — прошлые данные доступны только для чтения» |

### 4.1 Причина отклонения

`reject` требует `reason` из закрытого списка — это метрика пилота «причины отклонений» и сигнал качества правила
(AI_GOVERNANCE.md §5):

| `reason` | В UI |
|---|---|
| `wrong_data` | Неверные данные |
| `irrelevant_rule` | Правило не подходит для этой кампании |
| `not_enough_context` | Недостаточно контекста для решения |
| `too_risky` | Слишком рискованно |
| `other` | Другое |

`comment` — до 500 символов, обязателен при `other`, иначе по желанию. В LLM и уведомления не уходит.

## 5. `Recommendation` — проблема, доказательства, действие

`id` — **стабильный** на весь жизненный цикл. Аудит может пересчитать цифры и действие («−15%» → «−25%») — это новая
**версия**, `version_id`; UI показывает последнюю. Решение (`accept`, `mark_done_manually`, `check`) относится к
конкретной версии: устарела — `409 version_outdated`, нужно новое решение.

Рекомендации v1.0 дают **ровно три правила** (STRATEGY.md, PRD §4): нулевые конверсии (`zero_conv_campaign`), высокий
CPA (`high_cpa`: `high_cpa_target@N` / `high_cpa_baseline@N`), площадки РСЯ без конверсий. Рычаги — не только ставка:
цель CPA, качество конверсий и целей, исключение площадок, корректировки, контроль изменений (ARCHITECTURE.md §4.1).

### `RecommendationListItem` — `GET /workspaces/{ws}/recommendations`

```json
{"id": "rec_8f2c1", "version_id": "rv_77a01", "title": "CPA 4 820 ₽ выше целевого 3 000 ₽ · кампания 51234567",
 "ad_account": {"id": "acc_2", "login": "client-login"}, "object": {"type": "campaign", "id": "51234567", "name": null},
 "status": "new", "execution_mode": null, "verification_status": null, "action_level": "review",
 "action": {"type": "lower_cpa", "strategy": "unknown", "execution": "manual", "levers": [
   {"strategy": "manual", "lever": "decrease_bid", "change_pct": "-15.00"},
   {"strategy": "auto", "lever": "lower_target_cpa", "change_pct": null},
   {"strategy": "auto", "lever": "check_conversion_goals", "change_pct": null}]},
 "exposure": "Value", "exposure_overlap": "Value", "can_save": "Value", "data_status": "complete",
 "data_sufficiency": "sufficient", "period": {"from": "2026-09-22", "to": "2026-09-28"},
 "computed_at": "2026-10-01T07:01:54+03:00", "created_at": "2026-09-29T07:02:11+03:00", "updated_at": "…"}
```

**v1.0 отдаёт только активные** (`app/api/active.py`, то же определение у «Сегодня»): проблема открыта; кабинет выбран и
вошёл в **последний** аудит (исключённый из него — ни в списке, ни в итоге, ни в счётчиках); текущий вывод — из этого
аудита или аудит удержал проблему «недостаточно данных» (`data_sufficiency = insufficient`; `exposure`, `can_save`,
`exposure_overlap` — `unavailable` с причиной; `action_level = inspect_only`; в итог не входит — `coverage.unavailable`);
нет решения человека (`postponed` — до `until`). `filter` по статусам — неделя 4. Параметры: `ad_account`, `limit`
(1–100, по умолчанию 50), `cursor`. Ответ: `{"items": [...], "next_cursor": "…" | null}`. Порядок — по `exposure.amount` по убыванию, `unavailable` — в конце. `computed_at` — когда посчитана текущая версия.

### `Recommendation` (паспорт) — `GET /workspaces/{ws}/recommendations/{id}`

```json
{"id": "rec_8f2c1", "version_id": "rv_77a01", "title": "…", "ad_account": {…}, "object": {…}, "status": "new",
 "postponed_until": null, "action_level": "review", "allowed_actions": ["accept", "mark_done_manually", "postpone",
 "reject"], "blocked_actions": [], "exposure": "Value", "exposure_overlap": "Value", "can_save": "Value",
 "explanation": {"text": "CPA кампании — 2 500 ₽, это на 25% выше целевого…", "source": "template"},
 "action": "как в списке", "candidate_action": {"type": "decrease_bid", "change_pct": -15},
 "evidence": {"facts": {"cost": "Value", "conversions": "Value", "cpa": "Value"}, "meta": {}, "rule_version": "…"},
 "safety": {"safety_policy": "safety_policy@1", "candidate_level": "change", "policy_reasons": ["strategy_unknown"],
            "data_status": "complete"}, "limitations": ["strategy_unknown"],
 "execution": {"execution_mode": null, "verification_status": null, "accepted_at": null, "done_at": null,
               "before_state": null, "verification_checked_at": null}, "decision": null, "measurement": null,
 "history": [{"event": "created", "at": "…", "actor": "system"}], "computed_at": "…", "created_at": "…"}
```

- `candidate_action` — кандидат правила как есть (только для «Откуда это число?»); человеку показывается `action`.
- **Паспорт** (PRD §5, «Почему AdPilot так считает?»): проблема — `title`, `ad_account`, `object`; данные —
  `evidence.facts`; период и источник — в каждом `Value`; расчёт — `formula`; причина — `explanation`; что изменить
  вручную — `action`; эффект — `can_save`; ограничения — `limitations`; безопасность — `safety`; решение и результат —
  `decision`, `history`, `execution`, `measurement`.
- `title` — код из вывода (семейство + объект + ключевая цифра), не LLM. `object.name` — **nullable**: названий
  кампаний в схеме нет — `null` (UI показывает id); в LLM имена не уходят никогда.
- `status` v1.0 — из существующих событий: `new` · `postponed` · `rejected` · `applied`; `requires_decision` /
  `accepted` — неделя 4. `execution_mode`, `verification_status` — **nullable**, в v1.0 всегда `null` (неделя 4).
- `exposure` (UI «Расход с признаками неэффективности ≈») — `estimated` (или `unavailable` у удержанной); в БД —
  `findings.lost`. `exposure_overlap` — `Value`: часть суммы карточки, уже учтённая другой карточкой (разложение
  `exposure_total@1`), Σ (`exposure` − `exposure_overlap`) по активным = `exposure.total` «Сегодня»; `> 0` — отметка
  «частично учтено в другой карточке». `can_save` («Можно сэкономить ≈») — своей формулой; нет обоснованной (проверить,
  площадки РСЯ — нет модели перераспределения бюджета) — `unavailable` (`no_forecast`), не копия `exposure`.
- `explanation.text` — готовый текст (`llm` или `template`); все числа в нём — из `evidence`, каждое утверждение
  опирается на факт (AI_GOVERNANCE.md §2). Это единственная AI-функция v1.0; общего чата нет.
- `action` — **что человек делает в кабинете сам**, согласованное с `action_level` (`app/audit/present.py`), а не
  кандидат правила (он остаётся в БД); `execution` всегда `manual`. Неизвестная/старая форма → `action: null` (лог
  сервера), список не падает. Четыре формы, дискриминатор `type`:

  | `type` | Когда | Параметры |
  |---|---|---|
  | `investigate` | любой кандидат на `inspect_only` | `topic` (семейство); `checks[]`: `conversion_goals` · `strategy` · `search_queries_negative_keywords` · `network_placements`; `suggest`: `set_target_cpa` · `null`; `placements`: `[{id, name}]` (у `zero_conv_placements`) · `null` |
  | `lower_cpa` | `decrease_bid` на `review`/`change`, стратегия не известна как ручная | `strategy`: `unknown` · `manual` · `auto`; `levers[]`: `{strategy, lever, change_pct}` — `decrease_bid` (ручные ставки, `change_pct` < 0) · `lower_target_cpa` · `check_conversion_goals` (автостратегия, `change_pct: null`) |
  | `decrease_bid` | только известная ручная стратегия и `change` (в v1.0 не бывает: стратегия неизвестна) | `change_pct` — строка-число < 0 |
  | `exclude_placements` | `zero_conv_placements` на `review` | `placements_count`; `placements[]`: `{id, name}` |

  `placements[].id` — непрозрачный id площадки; `name` — домен или id приложения после санитизации (не ПД, в LLM не
  уходит), `null` — имя недоступно.
- `execution.before_state` — исходное состояние объекта для сверки (§6.1): `{"captured_at": "accept",
  "reliability": "normal", "read_at": "…", "parameters": {"bid": "Value"}}`. `captured_at`: `accept` · 
  `mark_done_manually`; `reliability`: `normal` · `reduced` (снято при отметке без `accept`). Не прочитано — `null`.
- `decision` — последнее решение человека: `{"event": "rejected", "reason": "too_risky", "comment": "…", "at": "…",
  "actor": {…}}` или `null`. `comment` видят только участники той же организации.
- `safety.policy_reasons` — почему уровень ниже, чем просило правило: `data_sufficiency_low` /
  `data_sufficiency_medium`, `strategy_unknown`, `data_partial`.
- `history[].event` — события DATA_MODEL.md §8.3 v1.0 (`created`, `seen_again`, `viewed`, `delivered`, `accepted`,
  `postponed`, `rejected`, `recommendation_checked`, `manual_claimed`, `verification_confirmed`,
  `verification_not_confirmed`, `measured`, `measurement_skipped`). `actor`: `system` или
  `{"user_id": "u_…", "name": "…"}` — имя только участникам той же организации.

## 6. Решение — `POST /workspaces/{ws}/recommendations/{id}/actions`

Фронтенд отправляет **действие**, а не новый статус. Статус вычисляет бэкенд. Ни одно действие не обращается к
Директу на запись.

```json
{"action": "accept", "version_id": "rv_77a01"}
{"action": "postpone", "version_id": "rv_77a01", "until": "2026-10-09"}
{"action": "reject", "version_id": "rv_77a01", "reason": "irrelevant_rule", "comment": "Кампания сезонная"}
```

`action` — §4; `version_id` — версия, на которую смотрел пользователь, обязательна; `until` — только и обязательно для
`postpone`; `reason` — только и обязательно для `reject` (§4.1), `comment` — только для `reject`. Время события и
`execution_date` (день выполнения в поясе данных, у `mark_done_manually`) задаёт **сервер**: от него зависят окна замера.

Ответ: `200` — обновлённая `Recommendation`. Повтор действия, уже ставшего текущим состоянием (двойной клик), → `200`
без новой записи.

Проверки по порядку: (1) доступ к workspace → иначе `404`; (2) формат → `400 invalid_request` (в т. ч. `reason` вне
списка, `other` без `comment`); (3) `version_id` последний → `409 version_outdated` (в ответе актуальная
рекомендация); (4) переход допустим из текущего `status` → `409 invalid_transition`; (5) действие в
`allowed_actions` → иначе `422 action_unavailable` с `reason` из §4 (`role_forbidden` → `403 forbidden_role`).

### 6.1 Сверка ручного выполнения (только чтение)

**Исходное состояние фиксируется при `accept`:** сервер читает параметры объекта из Директа (`Campaigns.get` и
аналогичные `*.get` по типу действия: цель CPA, ставка, исключённые площадки, статус показов) и сохраняет их как
`before_state` в событии `accepted`. Без `accept` (сразу `mark_done_manually`) `before_state` читается при отметке с
`reliability = reduced`: «до» уже может содержать изменение — сверка менее надёжна, это видно в UI (§3.3).
После `mark_done_manually` синхронизация снова **читает** параметры и сравнивает с `before_state` и ожидаемым
направлением:

| Результат чтения | `verification_status` | Событие |
|---|---|---|
| параметр изменён в ожидаемую сторону | `confirmed` | `verification_confirmed` |
| параметр не изменён | `not_confirmed` | `verification_not_confirmed` |
| чтение недоступно, нет `before_state`, тип действия не сверяется | остаётся `pending` | — |

Пока сверка не подтвердила изменение, AdPilot не утверждает, что оно сделано. Сколько синхронизаций ждать до
`not_confirmed` — открытый вопрос (DATA_MODEL.md §11).

## 7. `measurement` — результат замера

```json
{"status": "measured", "verdict": "effect", "method": "uncontrolled_before_after",
 "windows": {"before": {"from": "2026-09-17", "to": "2026-09-23"}, "after": {"from": "2026-09-25", "to": "2026-10-01"}},
 "before": {"cpa": "Value", "conversions": "Value"}, "after": {"cpa": "Value", "conversions": "Value"},
 "saved": "Value", "counts_in_saved_total": true}
```

- `status`: `pending` (окно «после» ещё идёт) · `measured` · `skipped` (подписка или подключение неактивны). Замер
  создаётся только после `applied` с `execution_mode = manual`; у `none`, `accepted`, `rejected`, `postponed` его нет.
- `method`: в v1.0 только `uncontrolled_before_after`; `matched_control`, `experiment` зарезервированы. Подпись под
  «Сэкономлено ≈»: «Расчётный эффект · Сравнение 7 дней до и после без контрольной группы».
- `verdict`: `effect` · `no_effect` · `not_confirmed` (CPA снизился, но конверсий меньше) · `insufficient`.
- `saved` есть **только при `verdict = effect`** и всегда `estimated` с формулой.
- `counts_in_saved_total` — входит ли `saved` в «Сэкономлено ≈»: `true` только при `manual` +
  `verification_status = confirmed`. Неподтверждённое ручное выполнение показывает наблюдаемый эффект, но в
  «Сэкономлено» не входит.
- Проблема, ушедшая сама (без действий), в «Сэкономлено» не входит. «Возвращено» и «заработано» не пишем.

## 8. Экраны

### `GET /workspaces/{ws}/today` — «Сегодня»

```json
{
  "last_audit_at": "2026-10-02T07:01:54+03:00", "data_status": "complete",
  "audit_scope": {"rules": ["high_cpa_target@1", "zero_conv_campaign@1", "zero_conv_placements@1"],
                  "period": {"from": "2026-09-25", "to": "2026-10-01"}, "ad_accounts": {"checked": 2, "excluded": 0},
                  "campaigns": 14},
  "spent": "Value",
  "exposure": {"total": "Value", "overlap": "Value", "version": "exposure_total@1", "formula": "Σ по кабинетам max(...)",
               "components": [{"issue_type": "high_cpa", "amount": "Value"}],
               "coverage": {"included": 3, "unavailable": 1}},
  "counts": {"active": 4}, "top": ["RecommendationListItem — до 3"],
  "data_freshness": {"last_snapshot_at": "…",
                     "yandex_direct": {"status": "connected", "data_to": "2026-10-01", "last_success_at": "…"},
                     "yandex_metrika": {"status": "permission_missing", "data_to": null, "last_success_at": null}}
}
```

- `exposure` — «Расход с признаками неэффективности ≈ N ₽» по активным рекомендациям (§5, то же определение, что у
  списка). **Не сумма карточек:** `total` считает `audit/exposure.py` по объединению
  затронутого расхода (ECONOMICS.md); `components` — по типам проблем, `overlap` — сколько вычтено как пересечение,
  `version` и `formula` — как посчитано. Пояснение в UI: «Оценка расходов, по которым система обнаружила признаки
  неэффективности. Одна и та же сумма учитывается в итоге только один раз». `coverage` — карточки без числа вне итога.
- `audit_scope` — что проверил последний аудит («Проблем не найдено — вот что проверено»): `rules` — правила@версии,
  `period` — окно оценки (7 дней до последнего полного дня данных), `ad_accounts` — кабинеты в аудите и исключённые
  (нет доступа или снимка), `campaigns` — кампании со статистикой в окне. Аудита не было — `null`.
- `spent` — `actual`: расход этих кампаний за `audit_scope.period` по данным Директа; снимков нет — `unavailable`.
- `counts.active` — активные рекомендации; `top` — до 3: по уровню действия, затем exposure и уверенности.
- `data_freshness.*`: `status` — DATA_MODEL.md §8.1 (`null` — источник не подключён), `data_to` — последний день в
  снимках, `last_success_at` — последний успешный запрос к API источника.
- `last_audit_at = null` → аудита ещё не было: экран «Подключите Директ», без нулей и демо-цифр (период — сегодня МСК).
- `data_status = partial`, если `partial` у `spent` или у exposure хоть одной активной карточки.

**Появится на неделе 4 вместе с событиями v1.0** (решения §6, сверка, замер), сейчас не отдаётся: `counts` по статусам
(`new`, `requires_decision`, `accepted`, `postponed`), `recent_actions` (`[{recommendation_id, title, event, at}]`),
`saved` (только замеры с `counts_in_saved_total = true`; нет — `unavailable`, не `0`). Позже, отдельным изменением
контракта: `access` — с биллингом (§13): `free_audit` (один бесплатный аудит, решения доступны) · `paid` · `inactive`
(прошлые данные только для чтения); `can_save` итогом (тем же способом, что `exposure`), `conversions`, `changes`.

### `GET /workspaces/{ws}/analytics` — «Аналитика»

Параметры: `from`, `to` (≤ 90 дней), `group` (`day` · `campaign`), `ad_account` (по умолчанию — все в анализе).
Ответ: итоги и ряды — расход, клики, конверсии, CPA, CTR (каждое — `Value`), изменения к прошлому периоду, exposure и
экономия, строки по кампаниям. Выручка и ROI — только при подключённом источнике, иначе `unavailable`. Не BI.

### Подключения и импорт данных — «Настройки → Интеграции»

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/workspaces/{ws}/integrations` | статусы подключений и кабинетов (ниже) |
| POST | `/workspaces/{ws}/integrations/{provider}/connect` | `provider`: `yandex_direct` · `yandex_metrika` → `{redirect_url}` на Yandex OAuth; state привязан к workspace и пользователю |
| GET | `/integrations/{provider}/callback` | возврат с OAuth: state сверяется до обращения к Яндексу, затем редирект в кабинет |
| POST | `/workspaces/{ws}/integrations/{provider}/disconnect` | отключить: токен удаляется, синхронизация останавливается |
| PATCH | `/workspaces/{ws}/integrations/ad-accounts/{id}` | `{selected}` — включить кабинет в анализ |
| GET · PUT | `/workspaces/{ws}/integrations/yandex_metrika/goals` | цели счётчика для выбора (ранжированные, ARCHITECTURE.md §2.8) · выбранные цели |

```json
{"items": [{"provider": "yandex_direct", "status": "connected", "account": "client-login",
            "last_success_at": "…", "data_to": "2026-10-01", "error_code": null,
            "ad_accounts": [{"id": "acc_2", "login": "client-login", "selected": true, "status": "active"}]}]}
```

- `status` — DATA_MODEL.md §8.1. Подключать и отключать — owner/admin (§10).
- **Только чтение.** Директ запрашивается со scope `direct:api` (отдельного scope только для чтения у Директа нет), но
  v1.0 вызывает только методы чтения: Reports, `Campaigns.get` и аналогичные `*.get`; Метрика — `metrika:read`. Поле
  `write_access` и проверка права записи — v1.1 (API_CONTRACT_EXECUTION.md §6).
- Подключений Директа и кабинетов в workspace может быть несколько; сверх лимита `max_ad_accounts` → `422
  action_unavailable` с `entitlement_exceeded`. Workspace организации-агентства подключает Директ только после
  подтверждения мандата клиента (`POST /workspaces/{ws}/legal/agency-client-mandate` `{version}`, LEGAL.md); без него
  → `422 acceptance_required`.
- Импорт офлайн-конверсий и квалификации лидов (CSV) — v1.0.x / v1.1 (VERSION_SCOPE.md), в контракте v1.0 его нет.

## 9. Объяснение — без общего чата

AI в v1.0 — только `explanation` рекомендации (§5): утверждения → доказательства, непрозрачные ссылки вместо ID
Яндекса (AI_GOVERNANCE.md §2). Эндпоинта вопросов к AI нет; «Спросить AI» — v1.1.

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

| Роль | Смотреть | decide (`accept`, `mark_done_manually`, `check`, `postpone`, `reject`) | Команда, интеграции, биллинг |
|---|---|---|---|
| org `owner` | все ws | да | да |
| org `admin` | все ws | да | да (кроме удаления организации) |
| org `member` | только ws со своей ролью | по `ws_role` | нет |
| ws `approver` | да | да | нет |
| ws `analyst` | да | да | нет |
| ws `viewer` | да (`view`) | нет | нет |

В v1.0 права `approver` и `analyst` совпадают; различаться они будут в v1.1 — правами approve и execute для API-исполнения
(API_CONTRACT_EXECUTION.md §7). Роли заводятся сейчас, чтобы команда агентства не перестраивалась при переходе.

Управление — только `owner` / `admin`: `GET/POST /organizations/{org}/invitations`;
`PATCH/DELETE /organizations/{org}/members/{user}` (`org_role`; удаление снимает и все ws-роли; последнего `owner`
удалить или понизить нельзя — `409 last_owner`; назначать, менять и удалять `owner` может только `owner`);
`GET /workspaces/{ws}/members`, `PUT/DELETE /workspaces/{ws}/members/{user}` `{ws_role}` — только для участника той же
организации, иначе `404`.

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
  подключение Директа и Метрики (§8), не вход.
- Законность входа по SMS (ч. 10 ст. 8 149-ФЗ) — открытый пункт LEGAL.md; до заключения юриста регистрация на HOLD.

## 12. Ошибки

```json
{"error": {"code": "action_unavailable", "reason": "role_forbidden",
           "message": "Ваша роль не позволяет это действие", "request_id": "3f1c…"}}
```

| HTTP | `code` | Когда |
|---|---|---|
| 400 | `invalid_request` | тело не по схеме, лишние поля, `until` вне диапазона, `reason` вне списка, неверный формат номера |
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

`GET /organizations/{org}/billing` — тариф, статус подписки, дата следующего списания, лимиты и использование (PRD §7).
`POST …/billing/checkout`, `…/billing/cancel`, `…/billing/payment-method/refuse` — с `Idempotency-Key`. Отказ от способа
оплаты — отдельно от отмены подписки: списаний с отозванного способа больше нет (LEGAL.md, 376-ФЗ).

## 14. Чего нет в v1.0

- **Записи в кабинеты через API** → v1.1 ([API_CONTRACT_EXECUTION.md](API_CONTRACT_EXECUTION.md)): предпросмотр,
  `approve`, `apply`, `cancel`, `rollback`, кворум по риску, `execution_mode = api`, `execution_status`,
  `rollback_status`, `write_access`, статусы `approved` / `failed` / `cancelled`, «Применить одним кликом».
- **AI-чата** → v1.1 (только чтение); автономных агентов нет. Автоматизации, Outcome Graph, CRM, VK Реклама → v2.0.
