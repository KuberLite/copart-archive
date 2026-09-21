# copart-archive

Архив фотографий лотов Copart.

- `archive/cases/COPART/<дата>/` — исходные таблицы аукционов (RAW, не изменяются)
- `archive/photos/<ПОВРЕЖДЕНИЕ>/<МАРКА>/<ГОД>/<МОДЕЛЬ>/COPART_<лот>/` — фото + `metadata.json`

## Установка

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```
