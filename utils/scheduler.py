"""
Scheduler for birthday reminders and advertisement delivery.

- Birthday congratulations: sent at 6:00 AM user's local time on the birthday
- Gift reminders: sent 1 week before + on the birthday morning
- Advertisements: sent to all users when created
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from database import controller as db

logger = logging.getLogger(__name__)


async def check_birthdays(bot):
    """Check for birthdays and send notifications."""
    today = date.today()
    one_week = today + timedelta(days=config.GIFT_REMINDER_DAYS_BEFORE)

    users = db.get_all_users()
    for user in users:
        user_tz = pytz.timezone(user.get("timezone") or "UTC")
        user_now = datetime.now(user_tz)

        # Only send at the configured notification hour
        if user_now.hour != config.NOTIFICATION_HOUR:
            continue

        birthdays = db.get_birthdays(user["telegram_id"])
        for b in birthdays:
            parts = b["date_of_birth"].split("-")
            if len(parts) != 3:
                continue
            month, day = int(parts[1]), int(parts[2])

            # Check if birthday is today
            if today.month == month and today.day == day:
                congrats = b.get("congratulation_text") or f"Happy Birthday to {b['full_name']}!"
                try:
                    await bot.send_message(
                        user["telegram_id"],
                        f"Today is {b['full_name']}'s birthday!\n\n{congrats}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send birthday notification to {user['telegram_id']}: {e}")

                # Gift reminder on birthday
                if b["gift_required"]:
                    try:
                        await bot.send_message(
                            user["telegram_id"],
                            f"Reminder: You planned to get a gift for {b['full_name']}!"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send gift reminder to {user['telegram_id']}: {e}")

            # Check if birthday is in 1 week (gift reminder)
            if b["gift_required"] and one_week.month == month and one_week.day == day:
                try:
                    await bot.send_message(
                        user["telegram_id"],
                        f"Reminder: {b['full_name']}'s birthday is in {config.GIFT_REMINDER_DAYS_BEFORE} days! "
                        f"Don't forget to get a gift!"
                    )
                except Exception as e:
                    logger.error(f"Failed to send week-before reminder to {user['telegram_id']}: {e}")


async def send_pending_ads(bot):
    """Send any pending advertisements to all users."""
    ads = db.get_pending_ads()
    if not ads:
        return

    users = db.get_all_users()
    for ad in ads:
        for user in users:
            try:
                await bot.send_message(user["telegram_id"], ad["message"])
            except Exception as e:
                logger.error(f"Failed to send ad to {user['telegram_id']}: {e}")
        db.mark_ad_sent(ad["id"], ad["_db"])
        logger.info(f"Ad #{ad['id']} sent to {len(users)} users")


def setup_scheduler(bot) -> AsyncIOScheduler:
    """Set up and return the APScheduler instance."""
    scheduler = AsyncIOScheduler()

    # Check birthdays every hour (to handle different timezones)
    scheduler.add_job(
        check_birthdays, "interval", hours=1,
        args=[bot], id="check_birthdays",
    )

    # Check for pending ads every 30 seconds
    scheduler.add_job(
        send_pending_ads, "interval", seconds=30,
        args=[bot], id="send_ads",
    )

    return scheduler
