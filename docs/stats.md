# Статистика Хранителя — контракт для сайта

Модуль: `khranitel.stats`. Данные на диске: `data/stats.json`.

## Публичный JSON

```python
from khranitel import stats
payload = stats.export_public()
```

Форма:

```json
{
  "version": 1,
  "plays_total": 42,
  "tales": {
    "primer": {
      "plays": 12,
      "variants": {"default": 8, "alt": 4},
      "endings": {"village": 5, "talk": 3},
      "choices": {
        "default": {"crossroads|Свернуть в лес": 7}
      },
      "seen_choices": {
        "default": ["crossroads|Свернуть в лес", "forest|Заговорить"]
      }
    }
  }
}
```

## Картинки

- `stats.render_overview_image()` → PNG (частота историй)
- `stats.render_tale_image(slug, adventures, title)` → PNG (концовки и полнота)

На сайте можно строить свои диаграммы из `export_public()`; PNG — готовая карточка для Телеграма.
