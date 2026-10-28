# Ручные решения и паспорт рекомендации

API `/api/v1/workspaces/ws_N/recommendations/rec_N`: GET выдаёт текущий finding `version_id`, последнее событие `state_version`, evidence с Value, action, object, explanation, history и latest_measurement. Доступ ограничен членством и RLS. Чтение не означает право изменять решения.

POST `/decisions`: action reject/postpone/check, expected_version_id, expected_state_version и UUID idempotency_key. Reject требует reason wrong_data/irrelevant_rule/not_enough_context/too_risky/other; other требует comment до 500 символов. Postpone требует until от завтра до 90 дней по МСК. Check доступен inspect_only и не создаёт замер.

POST `/manual-execution`: expected_version_id, expected_state_version, idempotency_key. Записывает заявление человека о ручном выполнении, без обращения к Direct API. Создаётся существующий done и замер через DB trigger. Роли: owner/admin/approver/analyst; нужны active workspace, действующий оплаченный период, актуальные аудит и состояние.

Обе мутации возвращают стабильную квитанцию recommendation_id/event_id/version_id/state_version/status/execution_mode/verification_status. Повтор ключа с тем же actor, операцией и каноническим телом возвращает прежнюю квитанцию; изменение запроса — 409. Проверки новой версии и состояния идут после восстановления квитанции. Сериализация совпадает с audit worker: workspace_shared → audit_exclusive, транзакция запроса.

POST `/verification` проверяет членство, роль, версии и возвращает 503 verification_unavailable без записи. Автоматической сверки нет. Ручное выполнение не считается подтверждённой экономией; result.counted_in_saved_total=false. Старое закрытие по замеру сохраняет статус applied.

Тесты: `backend/tests/test_api_recommendation_flow.py`. Браузерный паспорт проверяет вложенные Value и тип действия до показа инструкций; решение отправляется через закрытый same-origin BFF с CSRF, ограниченным телом и no-store.


## Дополнение 21 октября 2026

GET `/workspaces/ws_N/recommendation-activity?cursor=N&limit=20`: решения своего workspace, сортировка по последнему событию; cursor — ID последнего события предыдущей страницы, `1..2^63-1`, limit `1..50`. Возвращает `items` с безопасным кратким представлением, `measurement` и `next_cursor`. Пустая история возвращает пустой список. Права чтения берутся из CurrentWorkspace/RLS.

`latest_measurement` дополнен `reason` и `next_check_on`; status остаётся pending/complete/skipped. Итог содержит before/after как Value и наблюдаемый verdict, `counted_in_saved_total=false`. Автоматическая сверка изменения в Директе по-прежнему не реализована и не подменяется статистическим замером.

Worker runner теперь запускает существующий run_measurement для закрывшихся окон. Ежедневное чтение ставится только для явно подключённых к runner аккаунтов, при активном доступе и без дублирования задач на один cutoff по МСК. HTTP-записи в рекламные системы не добавлены.

Миграция `0009_campaign_strategies`: нормализованная стратегия хранится вместе с неизменяемым snapshot. Новые findings используют safety_policy@2; неизвестная стратегия или несовместимый рычаг понижает изменение до inspect_only. Историческая decide@safety_policy@1 оставлена для воспроизводимости. На автоматической стратегии кандидат decrease_bid не превращается в неутверждённое изменение целевой CPA.
