import base64
from pathlib import Path

EXTRACTION_SYSTEM_PROMPT = (
    "Ты — строгий экстрактор табличных данных со скриншотов экономического календаря. "
    "Твоя задача — ТОЛЬКО извлечь видимые на изображении значения без догадок и без внешних знаний. "
    "Нужны столбцы: Дата | Показатель | Факт | Прогноз | Предыдущий. "
    "Синонимы столбцов: Факт=Actual=Актуальное, Прогноз=Forecast=Ожидания, Предыдущий=Previous=Prior. "
    "Включай только те строки, где есть хотя бы одно число (факт/прогноз/предыдущий). "
    "Если ни одной строки извлечь нельзя, верни текст: Нет распознаваемых показателей на скриншоте. "
    "Никаких комментариев или выводов, только таблица."
)

EXTRACTION_USER_PROMPT = (
    "Извлеки данные в формате Markdown:\n\n"
    "Дата | Показатель | Факт | Прогноз | Предыдущий |\n"
    "|---|---:|---:|---:|\n"
    "<СТРОКИ>\n\n"
    "Требования:\n"
    "• Пиши ровно как на скриншоте (проценты, знаки, k, m).\n"
    "• Если ячейка пустая — оставляй пустой столбец.\n"
    "• Не добавляй текст до и после таблицы.\n"
    "• Максимум 20 строк."
)

def analyze_calendar_image_openai(
    png_path: Path,
    api_key: str,
    model: str = "gpt-5",
) -> str:
    if not api_key:
        return "ℹ️ Анализ отключён: OPENAI_API_KEY не задан."

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        b64 = base64.b64encode(png_path.read_bytes()).decode()

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                },
            ],
            
            max_completion_tokens=800,
        )

        content = (resp.choices[0].message.content or "").strip()

        if "Нет распознаваемых показателей" in content:
            return "Нет распознаваемых показателей на скриншоте."

        # Вырезаем только блок таблицы
        lines = [ln for ln in content.splitlines() if ln.strip()]
        table_lines = [ln for ln in lines if ln.strip().startswith("|")]
        if table_lines:
            return "\n".join(table_lines)
        return "Нет распознаваемых показателей на скриншоте."
    except Exception as e:
        return f"⚠️ Ошибка анализа: {e}"
