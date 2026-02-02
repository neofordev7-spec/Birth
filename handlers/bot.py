"""
Telegram bot handlers using aiogram.
Provides /start, /help, /webapp commands and handles web app data.
"""

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

import config
from database import controller as db

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    db.upsert_user(
        telegram_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
    )

    # Mark as admin if in config
    if user.id in config.ADMIN_IDS:
        db.set_admin(user.id, True)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Open Birthday Manager",
            web_app=WebAppInfo(url=config.WEBAPP_URL)
        )],
    ])

    await message.answer(
        "Welcome to Birthday Bot!\n\n"
        "I help you remember birthdays and send congratulations on time.\n\n"
        "Use the button below to open the web app, or use these commands:\n"
        "/birthdays - Open birthday manager\n"
        "/congrats - Manage congratulation texts\n"
        "/help - Show help",
        reply_markup=keyboard,
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "Birthday Bot Help\n\n"
        "/start - Start the bot\n"
        "/birthdays - Open birthday manager\n"
        "/congrats - Manage congratulation texts\n"
        "/stats - View your statistics\n"
        "/help - Show this help\n\n"
        "You'll receive reminders:\n"
        "- 1 week before a birthday (if gift needed)\n"
        "- On the birthday morning at 6:00 AM"
    )
    if db.is_admin(message.from_user.id):
        text += (
            "\n\nAdmin commands:\n"
            "/admin - Open admin panel\n"
            "/broadcast - Send message to all users"
        )
    await message.answer(text)


@router.message(Command("birthdays"))
async def cmd_birthdays(message: types.Message):
    url = f"{config.WEBAPP_URL}/birthdays?user_id={message.from_user.id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Manage Birthdays", web_app=WebAppInfo(url=url))],
    ])
    await message.answer("Open the birthday manager:", reply_markup=keyboard)


@router.message(Command("congrats"))
async def cmd_congrats(message: types.Message):
    url = f"{config.WEBAPP_URL}/congrats?user_id={message.from_user.id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Manage Texts", web_app=WebAppInfo(url=url))],
    ])
    await message.answer("Open congratulation text manager:", reply_markup=keyboard)


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    stats = db.get_user_stats(message.from_user.id)
    text = (
        f"Your Statistics\n\n"
        f"Total birthdays: {stats['total']}\n"
        f"Gifts needed: {stats['gifts_needed']}\n"
    )
    if stats["nearest"]:
        text += f"Nearest birthday: {stats['nearest']['full_name']} ({stats['nearest_date']})\n"
    if stats["nearest_gift"]:
        text += f"Nearest gift birthday: {stats['nearest_gift']['full_name']} ({stats['nearest_gift_date']})\n"
    await message.answer(text)


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not db.is_admin(message.from_user.id):
        await message.answer("You don't have admin access.")
        return
    url = f"{config.WEBAPP_URL}/admin?user_id={message.from_user.id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Open Admin Panel", web_app=WebAppInfo(url=url))],
    ])
    await message.answer("Open the admin panel:", reply_markup=keyboard)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if not db.is_admin(message.from_user.id):
        await message.answer("You don't have admin access.")
        return
    # Extract message text after /broadcast
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Usage: /broadcast Your message here")
        return
    ad_id = db.add_advertisement(message.from_user.id, text)
    await message.answer(f"Advertisement #{ad_id} created. It will be sent to all users shortly.")
