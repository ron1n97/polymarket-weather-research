# Polymarket Temperature Markets — Research

## Источник данных и механика резолюции

- **Данные:** Weather Underground (Wunderground), исторический максимум за день
- **Станции:** Аэропортовые метеостанции (ICAO-коды)
- **Точность:** Целые градусы (дробные не учитываются)
- **Торговый дедлайн:** 12:00 UTC в день резолюции (одинаково для всех городов)
- **Данные для резолюции:** полный местный день в часовом поясе города (Wunderground финализирует после окончания суток)
- **Settlement on-chain:** происходит после финализации данных, может быть через несколько часов после 12:00 UTC
- **Ревизии после финализации:** не учитываются
- **On-chain оракул:** `0x69c47De9D4D3Dad79590d61b9e05918E03775f24`
- **Формат:** мультиисход по диапазонам (например, 18°C / 19°C / 20°C и выше)

URL-паттерн данных: `wunderground.com/history/daily/[страна]/[город]/[ICAO]`

---

## Все 39 городов по часовым поясам

| UTC offset | Города | Кол-во |
|------------|--------|--------|
| UTC+12/13 | Wellington | 1 |
| UTC+9 | Tokyo (RJTT), Seoul (RKSI) | 2 |
| UTC+8 | Beijing (ZBAA), Shanghai (ZSPD), Shenzhen (ZGSZ), Chongqing (ZUCK), Wuhan (ZHHH), Chengdu (ZUUU), Hong Kong, Taipei (RCTP), Singapore (WSSS), Kuala Lumpur (WMKK) | 10 |
| UTC+5:30 | Lucknow (VILK) | 1 |
| UTC+3 | Istanbul (LTFM), Ankara (LTAC), Moscow (UUWW) | 3 |
| UTC+2/3 | Tel Aviv (LLBG) | 1 |
| UTC+1/2 | Paris (LFPG), Madrid (LEMD), Amsterdam (EHAM), Milan (LIMC), Munich (EDDM), Warsaw (EPWA) | 6 |
| UTC+0/1 | London (EGLC) | 1 |
| UTC-3 | Sao Paulo (SBGR), Buenos Aires (SAEZ) | 2 |
| UTC-5/4 | New York (KLGA), Miami (KMIA), Atlanta (KATL), Toronto (CYYZ) | 4 |
| UTC-6/5 | Chicago (KORD), Houston (KHOU), Dallas (KDAL), Mexico City (MMMX) | 4 |
| UTC-7/6 | Denver (KBKF) | 1 |
| UTC-8/7 | Los Angeles (KLAX), San Francisco (KSFO), Seattle (KSEA) | 3 |

**Итого: 39 городов**

---

## Сколько городов доступно в день

- Теоретически все 39, но Polymarket открывает **~20–35 рынков на конкретный день**
- Ставки нужно делать **до 12:00 UTC**
- Реалистичный охват при полной модели: **20–30 городов в день**

### Информационное преимущество по часовым поясам

Торговый дедлайн 12:00 UTC — одинаковый для всех. Но объём доступной информации на момент ставки сильно различается:

| Группа | 12:00 UTC = местное время | Что уже известно |
|--------|--------------------------|-----------------|
| Tokyo, Seoul (UTC+9) | 21:00 | Почти весь день прошёл, пик виден |
| UTC+8 кластер (10 городов) | 20:00 | То же, большое преимущество |
| Европа UTC+1/2 | 13:00–14:00 | Половина дня, пик ещё впереди |
| London (UTC+0/1) | 12:00–13:00 | Начало дня |
| Dallas, Houston (UTC-5/6) | 06:00–07:00 | Утро, пик не наступил — чистый прогноз |
| LA, SF, Seattle (UTC-7/8) | 04:00–05:00 | Глубокая ночь — максимально неопределённо |

**Вывод:** UTC+8/+9 города (Tokyo, Seoul, вся Азия) — наиболее выгодны с точки зрения информации на момент ставки.

---

## Приоритеты для ML-модели

### 1. UTC+8 кластер (10 городов) — высший приоритет
Beijing, Shanghai, Shenzhen, Chongqing, Wuhan, Chengdu, Hong Kong, Taipei, Singapore, Kuala Lumpur

Один регион → одна региональная модель покрывает всё. Самый большой пул взаимосвязанных рынков.

### 2. Европа UTC+1/2 (6 городов)
Paris, Madrid, Amsterdam, Milan, Munich, Warsaw

Хорошие исторические данные, предсказуемый климат.

### 3. США Восток + Центр (8 городов)
NYC, Miami, Atlanta, Toronto, Chicago, Houston, Dallas, Mexico City

NOAA данные отличного качества, высокая ликвидность рынков.

---

## Заметки

- Denver использует **KBKF** (Buckley Space Force Base), не KDEN
- Часть рынков (Tokyo, Istanbul, Tel Aviv, Moscow) резолвится через **NOAA/weather.gov**, не Wunderground
- Hong Kong использует **HK Observatory** (нет единого ICAO)
- США и Великобритания используют **°F**, остальные **°C**
