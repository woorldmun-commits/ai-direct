# API-контракт frontend ↔ backend — v0.1

Слой между бэкендом и фронтендом. Описывает **бизнес-сущности**, а не таблицы: фронтенд не знает про `issues`,
`recommendations`, `snapshots` и `recommendation_events`. Схема БД может меняться — контракт нет (только новой версией).

Цикл, который покрывает v0.1: **бэкенд сообщает → пользователь принимает решение → бэкенд фиксирует событие → замер**.
Изменение кампаний через Direct API (`Campaigns.update`, одобрение, `applied`) сюда не входит — это v2.0, DATA_MODEL.md §8.3.

Источники правды, которые контракт отражает и не переопределяет: `Value` — `backend/app/contract.py` и DATA_MODEL.md §5;
уровни действия — `backend/app/audit/policy.py`; статусы и переходы — DATA_MODEL.md §8.3 и триггеры `db/schema.sql`.

## 1. Общие правила

- Базовый путь `/api/v1`. JSON, UTF-8. Даты — `YYYY-MM-DD`, моменты — ISO 8601 с поясом (`2026-10-02T09:15:00+03:00`).
- **Деньги и любые числа — строки** (`"12500.00"`), не JSON-number: без потери точности `Decimal`. Отрицательных сумм
  потерь, «можно вернуть» и «сэкономлено» нет (CHECK в БД).
- Аутентификация — сессия в httpOnly cookie (ARCHITECTURE.md §7.1). Workspace берётся из сессии, в URL его нет.
  Объект чужого workspace → `404`, а не `403`: существование чужих данных не раскрывается.
- Изменяющие запросы (`POST`) — только с `Origin` нашего сайта и cookie `SameSite=Lax`; иначе `403 csrf_rejected`.
- В ответах нет: OAuth-токенов, email, `snapshot_id`, внутренних id таблиц, текстов поисковых запросов.
- Фронтенд **не считает** бизнес-значения и не решает, какие действия разрешены: он показывает `allowed_events`
  и `Value` как пришли. Суммы, проценты и знак «≈» получаются из полей, а не вычисляются.

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

Названия — те же, что в `app/contract.py`: второго словаря (`factual`, `RUB`, `value`) не вводим, чтобы не было
перевода между слоями. Это `Value` из бэкенда без `snapshot_id` и с `period` вместо `period_from` / `period_to`.

**Инварианты (проверяет бэкенд при сборке ответа; фронтенд может на них полагаться):**
- `calculation_type = unavailable` ⇔ `data_sufficiency = insufficient` ⇔ `amount = null`.
- `calculation_type = estimated` ⇒ `formula` не пустая.

**Как показывать (обязательно для фронтенда):**

| `calculation_type` | Показ |
|---|---|
| `actual` | `18 400 ₽` — без «≈» |
| `estimated` | `≈ 12 500 ₽`, формула — в подсказке «Как посчитано» |
| `unavailable` | «Недостаточно данных» — **никакого числа, нуля или прочерка вместо числа** |

`data_status = partial` → пометка «данные за последние дни могут уточниться». Тип в TypeScript строится так, чтобы
ошибку нельзя было скомпилировать: `amount: string` только в ветках `actual | estimated`, `amount: null` — в `unavailable`.

## 3. Уровни действия и события пользователя

`action_level` назначает политика безопасности (`safety_policy@N`); она может только понизить уровень правила.

| `action_level` | Смысл для пользователя | Кнопки → события |
|---|---|---|
| `inspect_only` | «Проверить»: показываем проблему и факты, изменений не предлагаем | «Проверил» → `checked` · «Позже» → `postponed` |
| `review` | «Проверьте перед изменением» | «Я сделал это» → `done` · «Позже» → `postponed` · «Не буду» → `rejected` |
| `change` | «Можно изменить» | те же, что у `review` |

В MVP изменения выполняет человек в кабинете Директа, поэтому `change` и `review` отличаются формулировкой и
уверенностью, а не механикой. Кнопка называется «Я сделал это», а не «Выполнено»: бэкенд не может проверить изменение.

**Матрица допустимости (источник правды — бэкенд):**

| Событие | `inspect_only` | `review` / `change` |
|---|---|---|
| `checked` | да | **нет** → `422 event_not_allowed` |
| `done` | **нет** → `422 event_not_allowed` | да |
| `postponed` | да | да |
| `rejected` | **нет** → `422 event_not_allowed` | да |

`done` над `inspect_only` и `checked` над остальными отклоняет и триггер БД. `rejected` над `inspect_only` БД
пропускает — его отклоняет API (DATA_MODEL.md §8.3 не даёт «Не буду» для проверки: отказываться не от чего).

## 4. Статус проблемы

Статус выводится из последнего значимого события, отдельного поля в БД нет.

| `status` | Откуда | Кнопки |
|---|---|---|
| `new` | создана или вернулась из `postponed` после даты | по `action_level` |
| `postponed` | «Позже» до `postponed_until` | по `action_level` (можно решить раньше) |
| `checked` | «Проверил» | нет |
| `done` | «Я сделал это»; замер ещё не готов | нет |
| `rejected` | «Не буду» | нет |
| `measured` | итог замера после `done` — см. `/results` | нет |
| `resolved` | проблема исчезла в следующем аудите без действий пользователя | нет |

```
new ──▶ postponed ──(postponed_until)──▶ new
 ├──▶ checked                     (inspect_only)
 ├──▶ done ──(+7 дней)──▶ measured (review / change)
 ├──▶ rejected                    (review / change)
 └──▶ resolved                    (система)
```

Пользовательские события допустимы только из `new` и `postponed`; иначе `409 invalid_transition`. `rejected` не
закрывает проблему: пока она есть в аудитах, она остаётся в истории как отклонённая, но рекомендацию не повторяем.

## 5. `Finding` — проблема и её доказательства

`id` — **стабильный** идентификатор проблемы на весь её жизненный цикл. Каждый новый аудит может пересчитать цифры
и действие (было «−15%», стало «−25%») — это новая **версия**, `version_id`. UI всегда показывает последнюю версию.

### `FindingListItem` — `GET /findings`

```json
{
  "id": "rec_8f2c1",
  "version_id": "fv_77a01",
  "title": "CPA выше целевого",
  "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
  "action_level": "review",
  "status": "new",
  "lost": {"amount": "12500.00", "unit": "rub", "calculation_type": "estimated", "…": "Value"},
  "data_status": "complete",
  "period": {"from": "2026-09-22", "to": "2026-09-28"},
  "created_at": "2026-09-29T07:02:11+03:00",
  "updated_at": "2026-10-01T07:01:54+03:00"
}
```

Поля `severity` нет: бэкенд его не считает, а выдуманная шкала нарушила бы принцип «каждый вывод = источник + цифры».
Порядок задаёт бэкенд: открытые сначала, внутри — по `lost.amount` по убыванию, `unavailable` — в конце.

Параметры: `status` (через запятую, по умолчанию `new,postponed`), `limit` (1–100, по умолчанию 50), `cursor`.
Ответ: `{"items": [FindingListItem], "next_cursor": "…" | null}`.

### `Finding` — `GET /findings/{id}`

```json
{
  "id": "rec_8f2c1",
  "version_id": "fv_77a01",
  "title": "CPA выше целевого",
  "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
  "action_level": "review",
  "status": "new",
  "postponed_until": null,
  "allowed_events": ["done", "postponed", "rejected"],
  "lost": "Value",
  "recoverable": "Value",
  "explanation": {"text": "CPA кампании — 2 500 ₽, это на 25% выше целевого…", "source": "template"},
  "action": {"type": "decrease_bid", "change_pct": -15},
  "evidence": {
    "facts": {"cost": "Value", "conversions": "Value", "cpa": "Value"},
    "meta": {"baseline_data_quality": "high"},
    "rule_version": "high_cpa_target@1",
    "safety_policy": "safety_policy@1",
    "candidate_level": "change",
    "policy_reasons": ["strategy_unknown"]
  },
  "history": [
    {"event": "seen_again", "at": "2026-10-01T07:01:54+03:00", "actor": "system"}
  ],
  "created_at": "2026-09-29T07:02:11+03:00"
}
```

- `allowed_events` — готовый список для кнопок. Фронтенд рисует кнопки только из него и сам матрицу §3 не применяет.
- `lost` — сколько потеряно за период; `recoverable` — сколько можно вернуть. Оба — `Value`.
- `explanation.text` — готовый текст (`llm` или `template`). Все числа в нём взяты из `evidence`: LLM чисел не вводит.
- `action` — то, что выдало правило: `type` и параметры типа (`decrease_bid` → `change_pct`;
  `investigate_cpa_growth` → `suggest`). **Текущей и рекомендуемой ставки в v0.1 нет**: в снимке нет `Campaigns.get`
  со стратегией и ставками, а выдумывать их нельзя. Поля появятся, когда их начнёт отдавать бэкенд.
- `evidence.facts` — именованные `Value`, по ним можно воспроизвести вывод; `meta` — нечисловые доказательства.
- `candidate_level` и `policy_reasons` объясняют, почему уровень ниже, чем просило правило:
  `data_sufficiency_low` / `data_sufficiency_medium` — мало конверсий; `strategy_unknown` — стратегия кампании неизвестна.
- `object.name` — название кампании для пользователя. В LLM оно не уходит (CLAUDE.md, ARCHITECTURE.md §6).

## 6. `FindingEvent` — `POST /findings/{id}/events`

Фронтенд отправляет **событие**, а не новый статус. Статус вычисляет бэкенд.

```json
{"event": "done", "version_id": "fv_77a01"}
{"event": "postponed", "version_id": "fv_77a01", "until": "2026-10-09"}
{"event": "rejected", "version_id": "fv_77a01", "comment": "Кампания сезонная"}
```

| Поле | |
|---|---|
| `event` | `checked` · `done` · `postponed` · `rejected` |
| `version_id` | версия, на которую смотрел пользователь. Обязательна: «Я сделал это» относится к конкретному действию (−15% или −25%), именно его потом замеряем |
| `until` | только для `postponed`, обязательна: дата от завтра до +90 дней |
| `comment` | только для `rejected`, необязательна, до 500 символов. В LLM и уведомления не уходит |

Время события и `execution_date` (день выполнения в поясе данных) задаёт **сервер**. С клиента время не принимается:
от этого дня зависят окна замера (DATA_MODEL.md §4, `recommendation_events`).

Ответ `200` — обновлённый `Finding`. Повтор того же события, уже ставшего текущим статусом (двойной клик), → `200`
без новой записи.

Проверки по порядку:
1. Проблема принадлежит workspace сессии → иначе `404 not_found`.
2. Формат тела → иначе `400 invalid_request`.
3. `version_id` — последняя версия проблемы → иначе `409 version_outdated` (цифры обновились, нужно показать новые).
4. Текущий статус — `new` или `postponed` → иначе `409 invalid_transition`.
5. Событие допустимо для `action_level` (§3) → иначе `422 event_not_allowed`.

## 7. `DashboardSummary` — `GET /dashboard`

Главная страница одним запросом.

```json
{
  "access": "paid",
  "today": "2026-10-02",
  "last_audit_at": "2026-10-02T07:01:54+03:00",
  "money_at_risk": "Value",
  "money_at_risk_coverage": {"included": 3, "unavailable": 1},
  "findings_count": {"new": 3, "postponed": 1, "in_progress": 2},
  "top_findings": ["FindingListItem — до 5 штук"],
  "recent_changes": [
    {"finding_id": "rec_8f2c1", "title": "CPA выше целевого", "event": "done", "at": "2026-10-01T18:20:00+03:00"}
  ],
  "data_freshness": {
    "yandex_direct": {"status": "connected", "data_to": "2026-10-01"},
    "yandex_metrika": {"status": "permission_missing", "data_to": null}
  }
}
```

- `money_at_risk` — сумма `lost` открытых проблем последнего аудита. Сумма оценок — тоже оценка (`estimated`,
  формула `sum(lost)`). Если ни одна проблема не дала числа — `unavailable`. `money_at_risk_coverage` честно говорит,
  сколько проблем без числа в сумму не попали.
- `in_progress` — `done`, ещё не замеренные.
- Ни одной карточки вида «сэкономлено N ₽» на главной нет, пока результат не подтверждён замером: подтверждённые
  результаты — только в `/results`.
- `last_audit_at = null` → аудита ещё не было: экран «Подключите Директ», без нулей и демо-цифр.

### `access` — состояние продукта

| `access` | Что видит пользователь |
|---|---|
| `free_audit` | Результат одного бесплатного аудита. Кнопки событий доступны. Плашка: «Мониторинг продолжится после подключения тарифа». Ежедневного аудита, уведомлений и замеров нет — фронтенд не показывает их как работающие |
| `paid` | Всё из контракта |
| `inactive` | Подписка закончилась: прошлые данные — только чтение, новых аудитов и замеров нет (`measurement_skipped`) |

Бэкенд выводит `access` из подписки и бесплатного аудита; фронтенд по нему только выбирает экран.

## 8. `GET /results` — результаты и история

Итоги замеров и все решения пользователя. «История» живёт здесь, а не отдельной вкладкой.

```json
{
  "saved_total": "Value",
  "items": [
    {
      "finding_id": "rec_8f2c1",
      "title": "CPA выше целевого",
      "object": {"type": "campaign", "id": "51234567", "name": "Поиск — Москва"},
      "event": "done",
      "event_at": "2026-09-24T18:20:00+03:00",
      "action": {"type": "decrease_bid", "change_pct": -15},
      "measurement": {
        "status": "measured",
        "verdict": "effect",
        "windows": {"before": {"from": "2026-09-17", "to": "2026-09-23"}, "after": {"from": "2026-09-25", "to": "2026-10-01"}},
        "before": {"cpa": "Value", "conversions": "Value"},
        "after": {"cpa": "Value", "conversions": "Value"},
        "saved": "Value"
      }
    }
  ],
  "next_cursor": null
}
```

- `measurement.status`: `pending` (окно «после» ещё идёт) · `measured` · `skipped` (подписка или подключение
  неактивны). У `checked`, `rejected`, `postponed` поля `measurement` нет: изменений не было, замерять нечего.
- `verdict`: `effect` · `no_effect` · `not_confirmed` (CPA снизился, но конверсий меньше) · `insufficient`.
- `saved` есть **только при `verdict = effect`** и всегда `estimated` с формулой. «Возвращено» и «заработано» не пишем.
- `saved_total` — сумма `saved` только по `effect`. `resolved` (проблема ушла сама) в неё не входит.

## 9. `GET /integrations`

```json
{
  "items": [
    {
      "provider": "yandex_direct",
      "status": "connected",
      "account": "client-login",
      "last_success_at": "2026-10-02T06:58:00+03:00",
      "data_to": "2026-10-01",
      "error_code": null
    }
  ]
}
```

`status` — DATA_MODEL.md §8.1: `connected` · `api_error` · `token_expired` · `token_revoked` · `permission_missing` ·
`disconnected`. `error_code` — код без ПД. Подключение и отключение (OAuth) в v0.1 контракта не входят.

## 10. Ошибки

Единый формат:

```json
{"error": {"code": "event_not_allowed", "message": "Для проблемы «Проверить» можно отметить только «Проверил» или «Позже»."}}
```

| HTTP | `code` | Когда |
|---|---|---|
| 400 | `invalid_request` | тело не по схеме, лишние поля, `until` вне диапазона |
| 401 | `unauthenticated` | нет сессии или она истекла |
| 403 | `csrf_rejected` | `POST` с чужим `Origin` |
| 403 | `access_denied` | действие недоступно для `access` (например, `inactive`) |
| 404 | `not_found` | нет объекта или он чужого workspace |
| 409 | `version_outdated` | `version_id` устарел: в ответе — актуальный `Finding` |
| 409 | `invalid_transition` | статус уже не `new` / `postponed` |
| 422 | `event_not_allowed` | событие не разрешено для `action_level` |
| 500 | `internal` | без деталей и стека |

`message` — текст для пользователя на русском; фронтенд может показать его как есть. Логику фронтенд строит по `code`.

## 11. Чего нет в v0.1

- Изменения кампаний через Direct API, одобрения и откаты (`approved`, `applying`, `applied`) — v2.0.
- AI-чата и отдельной AI-вкладки: объяснение приходит в `Finding.explanation`.
- Текущей и рекомендуемой ставки в `action` — до появления `Campaigns.get` со стратегией в снимке.
- Регистрации и входа: это отдельный контракт. Его обязательное требование уже зафиксировано в бэкенде:
  форма согласия передаёт версии принятых документов, `sign_in(..., accepted={документ: версия})`; без оферты
  новый пользователь не создаётся.
