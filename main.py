"""
Main entry point for Birthday Bot.
Starts the Telegram bot (aiogram) and web server (aiohttp) together.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiohttp import web

import config
from handlers.bot import router
from utils.scheduler import setup_scheduler
from web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Please set it in .env file.")
        return

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Set up scheduler
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    # Set up web app
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Web server started on http://0.0.0.0:8080")

    # Start bot polling
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
