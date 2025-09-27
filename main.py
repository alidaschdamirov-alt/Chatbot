import asyncio
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import ApplicationBuilder
from settings import settings
from idempotency import remember_update
from bot_handlers import register_handlers

app = FastAPI(title="TG Webhook • Macro Calendar")
application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
register_handlers(application)

@app.on_event("startup")
async def startup():
    await application.initialize()
    await application.start()

@app.on_event("shutdown")
async def shutdown():
    await application.stop()
    await application.shutdown()

@app.get("/")
def healthcheck():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    if settings.WEBHOOK_SECRET:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != settings.WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="bad secret token")
    data = await request.json()
    update = Update.de_json(data, application.bot)
    if not remember_update(update.update_id):
        return {"ok": True}
    asyncio.create_task(application.process_update(update))
    return {"ok": True}
