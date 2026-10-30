"""Source-reviewed process models, not market benchmarks or validated audiences."""
from copy import deepcopy

VERSION = 'starter-2026-10-29'
_SOURCES = {
    'cosmetology': [('Яндекс Метрика: CRM', 'https://yandex.ru/support/metrica/ru/crm/about'),
                    ('Битрикс24: этапы воронки', 'https://www.bitrix24.ru/journal/kak-nastroit-voronku-prodazh/')],
    'manufacturing': [('Яндекс Метрика: CRM', 'https://yandex.ru/support/metrica/ru/crm/about'),
                      ('Битрикс24: этапы воронки', 'https://www.bitrix24.ru/journal/kak-nastroit-voronku-prodazh/')],
    'ecommerce': [('Яндекс Метрика: ecommerce', 'https://yandex.ru/support/metrica/ru/ecommerce/data'),
                  ('Shopify: order statuses', 'https://help.shopify.com/en/manual/fulfillment/managing-orders/order-status')],
    'services': [('Битрикс24: этапы воронки', 'https://www.bitrix24.ru/journal/kak-nastroit-voronku-prodazh/'),
                 ('Яндекс Метрика: CRM', 'https://yandex.ru/support/metrica/ru/crm/about')],
    'real_estate': [('Битрикс24: CRM для девелоперов', 'https://www.bitrix24.ru/journal/crm-dlya-developerov/'),
                    ('Битрикс24: недвижимость', 'https://helpdesk.bitrix24.ru/open/14111144/')],
    'automotive': [('1С:Автосервис', 'https://solutions.1c.ru/catalog/autoservice/features'),
                   ('1С-Рарус: продажа автомобиля', 'https://rarus.ru/kb/samouchitel-alfa-avto/prodazha-avtomobilya-prinyatogo-na-komissiyu-v-alfa-avto-avtosalon-avtoservis-avtozapchasti-korp-redaktsiya-6/')],
    'b2b': [('Битрикс24: этапы воронки', 'https://www.bitrix24.ru/journal/kak-nastroit-voronku-prodazh/'),
            ('Яндекс Метрика: CRM', 'https://yandex.ru/support/metrica/ru/crm/about')],
}
_PROFILES = {
    'cosmetology': ('Косметология', ['обращение', 'квалификация', 'запись', 'визит', 'оплата', 'повтор'],
                    'Гипотеза процесса: запись не равна визиту или оплате. Нужны услуга, география, отмены и загрузка; медицинские рекламные требования проверяются отдельно.',
                    ['Выбор конкретной услуги в доступном регионе', 'Повторный визит по подтверждённой потребности']),
    'manufacturing': ('Производство и заводы', ['запрос', 'квалификация', 'техническое соответствие', 'КП', 'договор', 'оплата'],
                      'Гипотеза процесса: редкий запрос может иметь высокую ценность; незрелый договор не доказывает убыток. Нужны спецификация, партия, маржа и стадия закупки.',
                      ['Техническая задача и соответствие спецификации', 'Закупка и сравнение условий поставки']),
    'ecommerce': ('Интернет-магазины', ['заказ', 'оплата', 'доставка', 'отмена', 'возврат'],
                  'Подтверждение заказа в ecommerce не доказывает оплату; возвраты и себестоимость нужны для прибыли.',
                  ['Товарное намерение', 'Повторная покупка']),
    'services': ('Услуги населению', ['обращение', 'квалификация', 'запись', 'визит', 'оплата'],
                 'Запись не означает визит или оплату; высокий CPL без качества и продаж не основание отключения.',
                 ['Нужна услуга в регионе', 'Срочная потребность']),
    'real_estate': ('Недвижимость', ['интерес', 'квалификация', 'показ', 'бронь', 'сделка'],
                    'Бронь не равна сделке; незрелая когорта не доказывает убыток. Модель застройщика не универсальна.',
                    ['Поиск объекта', 'Сравнение предложений']),
    'automotive': ('Автомобильная сфера', ['обращение', 'запись', 'заказ-наряд', 'оплата'],
                   'Продажа автомобиля, запчасти и ремонт имеют разную экономику. Закрытый наряд не доказывает оплату.',
                   ['Потребность в ремонте', 'Поиск товара или автомобиля']),
    'b2b': ('B2B и сложные услуги', ['квалификация', 'встреча', 'КП', 'договор', 'оплата'],
            'Это пример процесса; короткий период без сделок не доказывает убыток при длинном цикле.',
            ['Задача организации', 'Сравнение подрядчиков']),
}


def industries():
    return [{'code': code, 'name': name, 'version': VERSION, 'review_status': 'process_hypothesis' if code in ('cosmetology', 'manufacturing') else 'source_reviewed',
             'reviewed_at': '2026-10-21', 'reviewer': 'codex-source-review',
             'sources': [{'title': title, 'url': url} for title, url in _SOURCES[code]],
             'purchase_stages': stages, 'limitations': [limitation, 'Модель процесса требует подтверждения бизнесом; рыночных средних нет.']}
            for code, (name, stages, limitation, _) in _PROFILES.items()]


def discover_audiences(profile):
    fields = profile['fields']
    code = fields['industry_code']
    known = _PROFILES.get(code)
    names = known[3] if known else ['Потребность в продукте']
    sources = [{'title': t, 'url': u} for t, u in _SOURCES.get(code, [])]
    limitation = known[2] if known else 'Отрасль не определена: используется универсальная гипотеза без отраслевой статистики.'
    return {'segments': [
        {'id': f'{code}-{i}', 'name': name, 'intent': name, 'status': 'hypothesis',
         'profile_revision': profile['revision'], 'needs': list(fields['products']),
         'objections': ['Требуют исследования у клиентов'], 'channels': [],
         'geography': list(fields['geography']), 'source_refs': deepcopy(sources),
         'missing_inputs': ['Исследование потребностей', 'Результат эксперимента', 'Качество и зрелость конверсий'],
         'test_plan': 'Согласовать отдельный эксперимент, контроль, срок и критерии; реклама автоматически не запускается.',
         'success_metric': fields['conversion_definition']}
        for i, name in enumerate(names, 1)],
        'limitations': [limitation, 'Источники описывают процессы, а не эффективность сегмента. Подтверждение пользователя не делает аудиторию validated.']}
