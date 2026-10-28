---
name: inrou-backend-integration
description: Use when connecting the INROU frontend to the existing backend API or changing API contracts, without breaking module boundaries.
---

1. Сначала читай существующий API (`backend/app/api/`) и контракт `backend/app/contract.py` (`Value`); не придумывай эндпоинты и поля.
2. Деньги — `Decimal`, рубли с двумя знаками; на фронте не пересчитывай суммы, показывай то, что отдал бэкенд. Неизвестное — «Недостаточно данных» и что подключить, не 0.
3. Границы: `rules/` и `audit/` не импортируют `ai/` (есть тест). В LLM — только обезличенные агрегаты.
4. Мутации: проверка авторизации/роли, валидация на границе, идемпотентность. Снимки и доказательная цепочка append-only.
5. Секреты и OAuth-токены — только env, не в коде и не в логах.
6. Изменение контракта = тест + обновление `docs/`. Проверка: `cd backend && .venv/Scripts/python.exe -m pytest`.
