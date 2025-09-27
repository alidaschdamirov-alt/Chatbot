import base64
from pathlib import Path

def analyze_calendar_image_openai(png_path: Path, api_key: str, model="gpt-4o-mini") -> str:
    if not api_key:
        return "ℹ️ Анализ отключён: OPENAI_API_KEY не задан."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        b64 = base64.b64encode(png_path.read_bytes()).decode()

        system_msg = (
            "Ты — макроаналитик. Дай краткий анализ экономкалендаря: "
            "1) ключевые релизы, 2) импликации для решения ФРС по ставке, "
            "3) влияние на BTC/крипту, 4) на индекс доллара (DXY), 5) на акции (S&P/Nasdaq), 6) риски."
        )
        user_msg = (
            "Формат ответа:\n"
            "• Ключевые релизы\n• Ставка ФРС\n• BTC/крипто\n• DXY\n• Акции\n• Риски"
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": [
                    {"type": "text", "text": user_msg},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}" }},
                ]}
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"⚠️ Ошибка анализа: {e}"
