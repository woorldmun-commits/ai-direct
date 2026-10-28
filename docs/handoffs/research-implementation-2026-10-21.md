# Применение исследования Rekvero — 21 октября 2026

## scope и revision

Реализовать рабочий цикл рекомендаций/замеров, приоритеты, улучшение импорта, недельный отчёт на сайте и безопасный контекст стратегии. Root — единственный writer; существующие изменения других задач сохранены. Базовый HEAD: `24106520ce168943355f628cd8e8ff936b218b0b`; изменения не закоммичены. Точные hashes проверенных исходников и артефактов — в receipts ниже.

## claims

- fact: worker runner запускает существующий замер по закрывшемуся периоду и ежедневную синхронизацию явно подключённых аккаунтов при активном доступе. Задачи не дублируются на один cutoff.
- fact: паспорт и раздел «Эффект» показывают периоды, ожидание/пропуск/результат и сопоставимые Value. Дата следующей проверки не переносится каждый день в будущее.
- fact: первый экран показывает серверные top-3 и область последнего аудита, с источниками и ограничениями.
- fact: CSV сначала проходит серверный preview без записи; подтверждение повторяет проверки; изменение формы сбрасывает preview. Статусы qCPL и пользовательская декларация полноты объяснены.
- fact: раздел «Отчёты» (`/workspace?view=reports&workspace=ws_N`) показывает последние 7 закрытых календарных дней МСК, события решений и ограничения; TXT скачивается дополнительно. Предварительный расход помечается partial, строгий qCPL не разблокируется.
- fact: стратегия Campaigns.get сохраняется в неизменяемом snapshot; новые findings с safety_policy@2 не предлагают ручную ставку на неизвестной/несовместимой стратегии.
- fact: главная объясняет задачу проверки расходов, ведёт к регистрации и содержит явно синтетический пример CPA с формулой.
- fact: подготовлен [протокол клиентского пилота](../PILOT_PROTOCOL.md).
- hypothesis: начальный сегмент — специалисты/небольшие агентства. Полезность и готовность платить не доказаны тестами.
- unavailable: клиентские интервью, фактический пилот, выбор CRM на их основании и реальные внешние ответы Яндекса.

## changed_files

Backend: `app/api/{recommendation_flow,workspace_insights,serialize}.py`, `app/insights/{lead_import,report}.py`, `app/audit/{policy,persist,templates}.py`, `app/sources/direct.py`, `app/sync/{snapshot,store}.py`, `app/worker/{runner,sync,audit}.py`, `db/schema.sql`, миграция 0009 и её released hash.

Frontend — только `designe 1.0`: workspace page/passport, components/workspace(actions,insights,measurement,weekly-report,midnight-shell), lib(insights-contract,pilot-contract,workspace-path,value), landing/app page; соответствующие проверки и локальная synthetic fixture. Тестовая БД получила отдельное имя на процесс, чтобы параллельные проверки не сбрасывали друг другу данные.

Контракты: [insights](workspace-insights-contract.md), [решения](recommendation-flow-contract.md).

## checks и evidence

| Проверка | Результат | Протокол |
|---|---|---|
| Весь backend pytest |1705 passed, exit 0|[backend receipt](../../results/recommendations-20261020/backend-receipt.json)|
| Финальные тексты report.py |38 passed, exit 0|[focused receipt](../../results/recommendations-20261020/report-final-receipt.json)|
| Frontend contracts/render/lint |exit 0|[frontend receipt](../../results/recommendations-20261020/frontend-receipt.json)|
| Production frontend build |exit 0, TypeScript passed|BUILD_ID hash и команда в frontend receipt|
| Браузер, реальные локальные HTTP/БД |PASS, synthetic data|[checks](../../results/recommendations-20261020/browser/checks.json)|
| Независимый source/evidence review |bounded PASS|[review](../../results/recommendations-20261020/review.md)|

Raw artifact hashes — [inventory](../../results/recommendations-20261020/artifact-sha256.json). Полный backend receipt предшествует финальным двум изменениям; focused receipt содержит актуальные hashes этих двух файлов. Это явное дополнение, а не утверждение, что прежние hashes совпадают с новой версией.

## not_checked, risks, owner_action

Реальные платежи отключены по прямому выбору владельца. Отчёт читается на сайте; внешняя рассылка не добавлена по его уточнению. Изменения рекламы автоматически не выполняются.

Сверка факта изменения настроек в Директе ещё unavailable: отметка manual не подтверждается статистическим сравнением. Наблюдаемый результат не засчитывается в подтверждённую экономию. CRM-коннектор выбирать после клиентского исследования; выдуманного клиента/кейса нет.

Перед выпуском применить 0009 через существующий migration runner и проверить роли/worker в целевой среде. Новое поле читается runtime; запуск кода без миграции приведёт к ошибке SQL. Production, deployment и реальные данные этим заданием не затрагивались; выпуск требует человеческого решения. Открытых дефектов в проверенном scope не осталось.
