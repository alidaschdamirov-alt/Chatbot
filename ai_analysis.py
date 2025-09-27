# ai_analysis.py
import base64
from pathlib import Path

EXTRACTION_SYSTEM_PROMPT = (
    "Ты — строгий экстрактор табличных данных со скриншотов экономического календаря. "
    "Твоя задача — ТОЛЬКО считать значения, которые видны на изображении, без догадок и внешних знаний. "
    "Нужны столбцы: Показатель | Факт | Прогноз | Предыдущий. "
    "Синонимы столбцов на русском/английском могут быть: "
    "Факт=Актуальное=Actual, Прогноз=Forecast=Ожидания, Предыдущий=Previous=Prior. "
    "В таблицу попадают ТОЛЬКО те строки, где хотя бы одно из чисел (факт/прогноз/предыдущее) явно различимо. "
    "Не добавляй комментарии, не делай выводы, не пиши ничего кроме таблицы. "
    "Если ни одной строки извлечь нельзя, ответь строго: Нет распознаваемых показателей на скриншоте."
)

EXTRACTION_USER_PROMPT = (
    "Извлеки из изображения таблицу показателей ровно в формате Markdown:\n\n"
    "| Показатель | Факт | Прогноз | Предыдущий |\n"
    "|---|---:|---:|---:|\n"
    "<СТРОКИ>\n\n"
    "Требования:\n"
    "• Значения пиши как на скриншоте (включая знаки %, k, m и т.п.).\n"
    "• Не придумывай отсутствующие данные — оставляй пустую ячейку, если число не видно.\n"
    "• Не добавляй текст до или после таблицы.\n"
    "• Максимум 20 строк.\n"
)

def analyze_calendar_image_openai(
    png_path: Path,
    api_key: str,
    model: str = "gpt-5",
) -> str:
    """
    Возвращает ТОЛЬКО Markdown-таблицу с колонками:
    | Показатель | Факт | Прогноз | Предыдущий |
    Либо строку 'Нет распознаваемых показателей на скриншоте.' если извлечь нечего.
    """
    if not api_key:
        return "ℹ️ Анализ отключён: OPENAI_API_KEY не задан."

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        b64 = base64.b64encode(png_path.read_bytes()).decode()

        resp = client.chat.completions.create(
            model=model,  # модель с поддержкой vision (напр., gpt-4o-mini)
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
            
            max_completion_tokens=1000,
        )

        content = (resp.choices[0].message.content or "").strip()

        # Страховка: если модель внезапно добавила лишний текст — оставим только блок таблицы.
        if "Нет распознаваемых показателей" in content:
            return "Нет распознаваемых показателей на скриншоте."
        if "|" in content:
            # Попробуем вырезать часть с Markdown-таблицей
            lines = [ln for ln in content.splitlines() if ln.strip()]
            # Найти шапку таблицы
            try:
                start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("|") and "Показатель" in ln)
                # Найти минимум строк после шапки (разделитель --- должен быть)
                # Обрежем всё, что идёт после последней строки, начинающейся с "|"
                end = start
                while end < len(lines) and lines[end].strip().startswith("|"):
                    end += 1
                table = "\n".join(lines[start:end]).strip()
                if table.count("|") >= 8:  # грубая проверка, что таблица не пустая
                    return table
            except StopIteration:
                pass

        # Если не похоже на таблицу — вернём fallback
        return "Нет распознаваемых показателей на скриншоте."
    except Exception as e:
        return f"⚠️ Ошибка анализа: {e}"
