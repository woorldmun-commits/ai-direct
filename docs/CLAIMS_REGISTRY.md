# Rekvero — claims registry

14.10.2026 · **REVIEW REQUIRED**. Release: dirty main после `a86b5413`. Reviewer не назначен; `last verified` ниже означает проверку размещения/кода, не юридическое утверждение. Реестр стартовый, не исчерпывающий аудит всей рекламы/презентаций.

| Claim text | Placement | Evidence | Status | Reviewer | Last verified | Affected release |
|---|---|---|---|---|---|---|
| «Демонстрационные тарифы из референса. Оплата пока недоступна» | `frontend/components/reference/landing.tsx:25` | CTA demo-auth; production payment provider не найден в проверенном app | DEMO ONLY | Не назначен | 14.10.2026 source | RF-0 / current |
| «7 дней», «2 990 ₽», годовой «−20%», «28 704 ₽» | `frontend/components/reference/landing.tsx:27` | Синтетические условия UI, нет утверждённого тарифа/налогов | DEMO ONLY; нельзя публиковать как реальный тариф | Продукт + юрист | 14.10.2026 source | current |
| «AI-директор», «Мониторинг 24/7» | `frontend/components/reference/landing.tsx:28` | Production LLM/SLA не подтверждены | REVIEW REQUIRED; нужен proof или ограничение формулировки | Продукт | 14.10.2026 source | current |
| VK/Telegram/Avito campaign metrics | `frontend/components/reference/landing.tsx:59` | Синтетические rows, пометка demo; реальные API adapters не подтверждены | DEMO ONLY | Продукт | 14.10.2026 source | current |
| «Обычно несколько минут» | `frontend/components/landing/bottom.tsx:125` | Benchmark живых аккаунтов не предоставлен | UNVERIFIED; убрать перед реальной публикацией либо дать evidence | Продукт | 14.10.2026 source | shared component |
| «Входите по номеру телефона… OAuth… отключить в любой момент» | `frontend/components/landing/bottom.tsx:105` | SMS default legal HOLD; текущий entry UI демонстрационный email | UNVERIFIED для текущего публичного потока | Backend + продукт | 14.10.2026 source | shared component |
| «Условия … в Договоре-оферте» | `frontend/components/landing/bottom.tsx:92` | `/legal/offer` содержит статус, утверждённого текста нет | FAIL для утверждения о действующих условиях | Продукт + юрист | 14.10.2026 source | shared component |
| Estimated spend и эффект «до/после» | `frontend/lib/site.ts:12`, `:17` | Backend Value/formula; demo fixtures отдельно; causal effect не доказан | PARTIAL; сохранять estimated/source/period и оговорку методики | Аналитик + QA | 14.10.2026 source | current |
| «Юридические документы не утверждены» | `/legal`, footer | В repo только placeholders, approval не предоставлен | VERIFIED STATUS ONLY; не compliance | Владелец + юрист | 14.10.2026 source | Local RF-1 |

Не добавлять отзывы, проценты экономии или гарантии из макета как реальные факты. Для утверждения требуются доказательство, ответственный reviewer, дата, scope и затрагиваемый release; changes в claims требуют повторной проверки. Перед production нужен полный census по реально отображаемым routes, SEO/metadata, сообщениям, email и рекламным материалам.
