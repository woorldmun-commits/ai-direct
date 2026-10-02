# API-контракт исполнения — v1.1 (Deferred to v1.1 — не реализуется и не обещается в v1.0)

> **Статус: Deferred to v1.1.** Всё в этом файле — спроектированная, но отложенная модель записи в рекламные кабинеты.
> В v1.0 AdPilot не изменяет рекламные кабинеты; контракт v1.0 — [API_CONTRACT.md](API_CONTRACT.md). Решения
> D5–D8 (риск, кворум, capability, предусловие, откат) не отменены: они перенесены сюда и в
> [EXECUTION_SAFETY.md](EXECUTION_SAFETY.md) как дизайн v1.1 (решение владельца 2026-10-02, [STRATEGY.md](STRATEGY.md),
> [VERSION_SCOPE.md](VERSION_SCOPE.md)). Первые действия v1.1 — 1–2 обратимых действия низкого/среднего риска.
>
> Здесь — только то, что v1.1 **добавляет** к v1.0. Общие правила, `Value`, паспорт рекомендации, замер, экраны,
> вход, ошибки и биллинг — в API_CONTRACT.md и здесь не повторяются.

## 1. Совместимость с v1.0

v1.1 расширяет контракт v1.0 без ломки:

- **Ничего не удаляется и не переименовывается.** Статусы v1.0 (`new`, `requires_decision`, `accepted`, `applied`,
  `postponed`, `rejected`), действия (`view`, `accept`, `mark_done_manually`, `check`, `postpone`, `reject` с
  `reason`), поля и события сохраняют смысл.
- **`accepted` остаётся ручным путём:** «принята к выполнению» — человек меняет кабинет сам, со сверкой
  (API_CONTRACT.md §6.1). API-путь — отдельная ветка через `approved`.
- **Добавляются:** статусы `approved`, `failed`, `cancelled`; значение `execution_mode = api`; поля
  `execution_status`, `rollback_status`, `risk`, `approvals`; действия `approve`, `apply`, `approve_and_apply`,
  `cancel`, `rollback`; эндпоинт предпросмотра; `write_access` у подключения; `approval_policy` в настройках.
- **Новые значения перечислений** приходят только клиенту, заявившему контракт v1.1 (заголовок
  `X-Contract-Version: 1.1`), и только в workspace, где тариф разрешает `api_execution`. Клиент v1.0 их не получает:
  рекомендация в `approved` / `failed` / `cancelled` для него выглядит как `requires_decision` без кнопок API —
  **открытый вопрос** §10, п. 1.
- Замер, «Сэкономлено» и сверка ручного выполнения работают одинаково для обоих путей.

## 2. Статусы и поля исполнения

| `status` (добавлено) | В UI | Смысл |
|---|---|---|
| `approved` | Одобрена | набран кворум одобрений (§4) для конкретной версии и состояния объекта, исполнение не завершено |
| `failed` | Не выполнена | исполнение через API не завершилось успехом |
| `cancelled` | Отменена | одобрена, но исполнение отменено до его начала |

```
                     ┌──accept──▶ accepted ──mark_done_manually──▶ applied (manual)      [v1.0, без изменений]
new ──▶ requires_decision ──(кворум approve)──▶ approved ──apply──▶ applied (api)
             │   ▲  ▲          ▲                    │  ├──▶ failed
             │   │  │          └─ approve из accepted (передумал выполнять вручную)
             │   │  └─ state_changed · approval_expired · новая версия
             │   │                                  └──▶ cancelled
             ├──▶ postponed ─(дата)┘
             └──▶ rejected (reason)
```

| Поле (добавлено) | Значения | |
|---|---|---|
| `execution_mode` | + `api` | применено через Direct API |
| `execution_status` | `not_started` · `pending` · `succeeded` · `failed` · `claimed_manual` | `claimed_manual` — у ручного пути v1.0 |
| `rollback_status` | `not_requested` · `pending` · `succeeded` · `failed` · `blocked` | откат после `applied` через API (§5.2); **не статус рекомендации** |

| Сценарий `status = applied` | `execution_mode` | `execution_status` | `verification_status` |
|---|---|---|---|
| Применено через API | `api` | `succeeded` | `confirmed` (AdPilot перечитал объект после изменения) |
| Выполнено вручную (v1.0) | `manual` | `claimed_manual` | `pending` / `confirmed` / `not_confirmed` |
| «Проверил» (v1.0) | `none` | `not_started` | `not_required` |

Подписи в UI (дополнение к API_CONTRACT.md §3.3): `api` — «Применено»; `rollback_status = succeeded` — «Изменение
отменено (откат)»; `blocked` — текст `state_changed_since_execution` (§3).

## 3. Действия и `allowed_actions`

`risk_level` (`low` · `medium` · `high` · `critical`; `null` у `inspect_only`) назначает `risk_policy@N` —
EXECUTION_SAFETY.md §3.

| Действие | Переход | Право | Условия |
|---|---|---|---|
| `approve` | `requires_decision` / `accepted` → тот же (k из N) или `approved` | approve | `change`; данные полные; capability поддержана; есть право записи; `preview_id` |
| `apply` | `approved → applied` / `failed` | execute | кворум не истёк; одобренная версия последняя |
| `approve_and_apply` | `requires_decision → approved → applied` / `failed` | approve **и** execute | одобрение пользователя **завершает** кворум; условия `approve` |
| `cancel` | `approved → cancelled` | approve | исполнение ещё не начато |
| `rollback` | `rollback_status → pending → …` | approve | гейт отката §5.2; последней версии вывода **не** требует |

- **`Idempotency-Key` обязателен** для `approve`, `apply`, `approve_and_apply`, `rollback`, `cancel`.
- `apply` / `approve_and_apply` / `rollback` асинхронны: `202` и `execution_status` (или `rollback_status`) =
  `pending`; итог — опросом `GET` рекомендации.
- Дополнительные проверки к API_CONTRACT.md §6: `version_id` последний — кроме `rollback` (аудит создаёт новые версии,
  откат от них не зависит); для `approve*` предпросмотр не истёк и его `precondition_hash` совпадает с уже данными
  одобрениями → иначе `422 action_unavailable` с `state_changed`.
- **Критическое правило:** при `data_status != complete` действия `approve`, `apply`, `approve_and_apply` всегда в
  `blocked_actions` с `data_partial` — вместо них ручной путь v1.0.

`allowed_actions` считает бэкенд из роли, `status`, `action_level`, `risk_level` и `approval_policy`, полноты данных,
capability, `write_access`, уже данных одобрений и лимитов тарифа. Причины в `blocked_actions` (добавлено к v1.0):

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
| `not_reversible` | «Это изменение нельзя откатить автоматически» |
| `entitlement_exceeded` | «Недоступно на текущем тарифе» |

`state_changed`, `approval_expired`, `capability_unsupported` приходят и как `execution.error_code`, если условие
обнаружено воркером перед записью; `state_changed_since_execution` — как `execution.rollback_reason`.

## 4. Кворум одобрений

Требуемое число **разных** одобривших — из `approval_policy` workspace по `risk_level` (по умолчанию medium = 1,
high = 1, critical = 2; меняет owner/admin, снизить critical до 1 — только owner). Засчитываются одобрения той же версии
(`version_id`) с тем же `precondition_hash` (§5.1), не старше 24 часов. Кворум набран → `approved`. Одобрение
завершает кворум и у пользователя есть execute → кнопка «Применить» (`approve_and_apply`); иначе — `approve`, затем
`apply`. Откат — одно одобрение независимо от риска. До кворума — `requires_decision` с отметкой «одобрено 1 из 2».

Дополнительные поля паспорта `Recommendation`:

```json
"risk": {"risk_level": "critical", "risk_policy": "risk_policy@1", "required_approvals": 2},
"approvals": [{"user": {"user_id": "u_2", "name": "…"}, "at": "…", "expires_at": "…"}],
"execution": {"execution_mode": null, "execution_status": "not_started", "verification_status": "not_required",
              "rollback_status": "not_requested", "rollback_until": null, "rollback_reason": null,
              "approved_at": null, "applied_at": null, "error_code": null}
```

`approvals` — одобрения текущей версии, засчитываемые в кворум; `history[].event` дополняется `approval_granted`,
`approved`, `execution_*`, `cancelled`, `rollback_*` (DATA_MODEL.md §8.3, раздел v1.1). В `RecommendationListItem`
добавляется `risk_level`; в `today.counts` — `approved`.

## 5. Предпросмотр и откат

### 5.1 Предпросмотр — `POST /workspaces/{ws}/recommendations/{id}/preview`

Читает текущие параметры объекта из Директа, проверяет capability и показывает «Было → Станет». Без записи в Директ.

```json
{"preview_id": "pv_3c9", "version_id": "rv_77a01",
 "changes": [{"object": {"type": "campaign", "id": "51234567"}, "parameter": "daily_budget", "before": "Value", "after": "Value"}],
 "reversible": true, "risk_level": "critical", "required_approvals": 2, "precondition_hash": "sha256:9b1e…",
 "approvals": [{"user": {"user_id": "u_2", "name": "…"}, "at": "…", "expires_at": "…"}],
 "expires_at": "2026-10-02T09:45:00+03:00"}
```

- `before` — `actual`, прочитано из Директа сейчас; `after` — результат действия. Предпросмотр живёт 30 минут.
- `precondition_hash` — хэш ожидаемого состояния (объект, параметр, текущее значение, действие, целевое значение).
  Повторный предпросмотр при том же текущем значении даёт тот же хэш. `approvals` — уже данные одобрения с этим хэшем.
- Действие не поддерживается для типа кампании/стратегии, поле неизменяемо или объект архивирован → `422
  action_unavailable` с `capability_unsupported`.
- Перед записью воркер перечитывает объект: значение изменилось → записи нет, `execution.error_code = state_changed`,
  рекомендация снова `requires_decision`. Одобрение действует 24 ч, истёкшее в кворум не входит (`approval_expired`).
- Тело `approve` / `approve_and_apply`: `{"action": "approve_and_apply", "version_id": "rv_77a01", "preview_id": "pv_3c9"}`
  — `preview_id` обязателен, из него берётся `precondition_hash`.

### 5.2 Откат

`{"action": "rollback", "version_id": "…"}` с `Idempotency-Key` → `202`, `rollback_status = pending`; одно одобрение.
Гейт (EXECUTION_SAFETY.md §7; последней версии вывода **не** требует): успешное исполнение через API · не прошло 7 дней
(`execution.rollback_until`) · текущее значение == `applied_value` · право approve · подключение `connected` и
`write_access = granted` · capability поддерживает обратное изменение. Равно → возвращает прежнее (`succeeded`); не
равно → записи нет, `blocked`, `rollback_reason = state_changed_since_execution` с текущим значением в тексте.

### 5.3 Замер

Замер создаётся и после `applied` с `execution_mode = api`. `counts_in_saved_total = true` также при `api` +
`succeeded`; успешный откат → `false`.

## 6. Право записи у подключения

`GET /workspaces/{ws}/integrations` дополняется `"write_access": "granted" | "denied" | "unknown"` у подключения
Директа: может ли этот токен менять кампании аккаунта (права в Директе зависят от роли пользователя Яндекса, например
представитель «только чтение»). Определяется по ответу API на запись; от него зависит `write_access_missing` (§3).

## 7. Роли: approve и execute

| Роль | approve (`approve`, `cancel`, `rollback`) | execute (`apply`) |
|---|---|---|
| org `owner` / `admin` | да | да |
| org `member` | по `ws_role` | по `ws_role` |
| ws `approver` | да | да |
| ws `analyst` | нет | только одобренного |
| ws `viewer` | нет | нет |

**`approve` ≠ `execute`.** Без права approve одобрение не создать; execute исполняет только уже одобренную версию.
`PATCH /workspaces/{ws}/settings` `{approval_policy}` — owner/admin; снизить `critical` до 1 — только owner
(`403 forbidden_role`), изменение пишется в журнал.

## 8. «Спросить AI» — `POST /workspaces/{ws}/ai/ask` (только чтение)

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
  шаблонный ответ, собранный кодом. Правила валидации — AI_GOVERNANCE.md §2.
- ID в ответе — наши (`rec_…`), не ID Яндекса: в LLM уходят непрозрачные ссылки, обратная подстановка — на сервере.
- **Только чтение.** У модели нет инструментов записи. Просьба «снизь ставку» → ссылка на существующую рекомендацию
  или «такой рекомендации нет»; изменение — только обычным потоком рекомендации.
- Данных нет → `data_sufficiency = insufficient` и «Недостаточно данных» с тем, что подключить.
- Истории вопросов и ответов в кабинете нет: текст вопроса не пишется в обычные логи, хранятся только технические
  метаданные (время, экран, исход) — ARCHITECTURE.md §2.5. Лимит — по тарифу (`ask_ai`) и `429 rate_limited`.

## 9. Доступ по тарифу

`access = free_audit` — API-исполнение недоступно; `inactive` — новых исполнений нет. Откат после окончания подписки —
открытый вопрос EXECUTION_SAFETY.md §11, п. 7.

## 10. Открытые вопросы

1. Как клиент v1.0 видит рекомендацию в статусе v1.1, если в одной организации работают разные версии фронтенда, — или
   переключать контракт для всей организации сразу.
2. `approve` из `accepted`: сбрасывает ли он `execution.before_state` ручного пути (предпросмотр читает объект заново).
3. Остальные — EXECUTION_SAFETY.md §11, AI_GOVERNANCE.md §6.
