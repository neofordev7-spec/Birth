"""
Web application server using aiohttp for the Telegram Web App.
Serves birthday management, congratulation texts, and admin features.
"""

import csv
import io
import os
import json
import calendar
from datetime import date, datetime

from aiohttp import web

import config
from database import controller as db

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _render(template_name: str, **kwargs) -> web.Response:
    """Simple template renderer that replaces {{ key }} placeholders."""
    path = os.path.join(TEMPLATE_DIR, template_name)
    with open(path, "r") as f:
        html = f.read()
    for key, value in kwargs.items():
        html = html.replace("{{ " + key + " }}", str(value))
    return web.Response(text=html, content_type="text/html")


def _get_user_id(request: web.Request) -> int:
    """Extract user_id from query params or header."""
    uid = request.query.get("user_id") or request.headers.get("X-User-Id", "0")
    return int(uid)


# ── Birthday Routes ──────────────────────────────────────────────

async def index(request: web.Request) -> web.Response:
    return _render("index.html")


async def birthdays_page(request: web.Request) -> web.Response:
    return _render("birthdays.html")


async def api_birthdays_list(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    birthdays = db.get_birthdays(user_id)
    clean = [{k: v for k, v in b.items() if k != "_db"} for b in birthdays]
    return web.json_response(clean)


async def api_birthday_create(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    data = await request.json()
    required = ["full_name", "date_of_birth"]
    for field in required:
        if not data.get(field):
            return web.json_response({"error": f"{field} is required"}, status=400)
    bid = db.add_birthday(
        user_id=user_id,
        full_name=data["full_name"],
        date_of_birth=data["date_of_birth"],
        relationship=data.get("relationship", "friend"),
        gift_required=bool(data.get("gift_required", False)),
        congratulation_text=data.get("congratulation_text", ""),
        notes=data.get("notes", ""),
    )
    return web.json_response({"id": bid, "status": "created"})


async def api_birthday_get(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    birthday_id = int(request.match_info["id"])
    rec = db.get_birthday_by_id(birthday_id, user_id)
    if not rec:
        return web.json_response({"error": "not found"}, status=404)
    clean = {k: v for k, v in rec.items() if k != "_db"}
    return web.json_response(clean)


async def api_birthday_update(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    birthday_id = int(request.match_info["id"])
    data = await request.json()
    ok = db.update_birthday(birthday_id, user_id, **data)
    if not ok:
        return web.json_response({"error": "not found or no changes"}, status=404)
    return web.json_response({"status": "updated"})


async def api_birthday_delete(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    birthday_id = int(request.match_info["id"])
    ok = db.delete_birthday(birthday_id, user_id)
    if not ok:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"status": "deleted"})


async def api_birthday_search(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    query = request.query.get("q", "")
    results = db.search_birthdays(user_id, query)
    clean = [{k: v for k, v in b.items() if k != "_db"} for b in results]
    return web.json_response(clean)


async def api_birthday_stats(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    stats = db.get_user_stats(user_id)
    # Clean nested dicts
    for key in ("nearest", "nearest_gift"):
        if stats[key]:
            stats[key] = {k: v for k, v in stats[key].items() if k != "_db"}
    return web.json_response(stats)


async def api_birthday_export_csv(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    birthdays = db.get_birthdays(user_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Full Name", "Date of Birth", "Relationship", "Gift Required", "Congratulation Text", "Notes"])
    for b in birthdays:
        writer.writerow([
            b["full_name"], b["date_of_birth"], b["relationship"],
            "Yes" if b["gift_required"] else "No",
            b["congratulation_text"], b["notes"],
        ])
    return web.Response(
        text=output.getvalue(),
        content_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=birthdays.csv"},
    )


async def api_birthday_calendar(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    month = int(request.query.get("month", date.today().month))
    year = int(request.query.get("year", date.today().year))
    birthdays = db.get_birthdays(user_id)
    month_birthdays = []
    for b in birthdays:
        parts = b["date_of_birth"].split("-")
        if len(parts) == 3 and int(parts[1]) == month:
            clean = {k: v for k, v in b.items() if k != "_db"}
            clean["day"] = int(parts[2])
            month_birthdays.append(clean)
    cal = calendar.monthcalendar(year, month)
    return web.json_response({
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "weeks": cal,
        "birthdays": month_birthdays,
    })


# ── Congratulation Text Routes ───────────────────────────────────

async def congrats_page(request: web.Request) -> web.Response:
    return _render("congrats.html")


async def api_congrats_list(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    texts = db.get_congrats_texts(user_id)
    clean = [{k: v for k, v in t.items() if k != "_db"} for t in texts]
    return web.json_response(clean)


async def api_congrats_create(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    data = await request.json()
    if not data.get("body"):
        return web.json_response({"error": "body is required"}, status=400)
    cid = db.add_congrats_text(user_id, data.get("title", ""), data["body"])
    return web.json_response({"id": cid, "status": "created"})


async def api_congrats_get(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    text_id = int(request.match_info["id"])
    rec = db.get_congrats_text_by_id(text_id, user_id)
    if not rec:
        return web.json_response({"error": "not found"}, status=404)
    clean = {k: v for k, v in rec.items() if k != "_db"}
    return web.json_response(clean)


async def api_congrats_update(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    text_id = int(request.match_info["id"])
    data = await request.json()
    ok = db.update_congrats_text(text_id, user_id, **data)
    if not ok:
        return web.json_response({"error": "not found or no changes"}, status=404)
    return web.json_response({"status": "updated"})


async def api_congrats_delete(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    text_id = int(request.match_info["id"])
    ok = db.delete_congrats_text(text_id, user_id)
    if not ok:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"status": "deleted"})


async def api_congrats_search(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    query = request.query.get("q", "")
    results = db.search_congrats_texts(user_id, query)
    clean = [{k: v for k, v in t.items() if k != "_db"} for t in results]
    return web.json_response(clean)


# ── Admin Routes ─────────────────────────────────────────────────

async def admin_page(request: web.Request) -> web.Response:
    return _render("admin.html")


async def api_admin_stats(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not db.is_admin(user_id):
        return web.json_response({"error": "forbidden"}, status=403)
    stats = db.get_admin_stats()
    for key in ("nearest", "nearest_gift"):
        if stats[key]:
            stats[key] = {k: v for k, v in stats[key].items() if k != "_db"}
    return web.json_response(stats)


async def api_admin_all_birthdays(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not db.is_admin(user_id):
        return web.json_response({"error": "forbidden"}, status=403)
    birthdays = db.get_all_birthdays()
    clean = [{k: v for k, v in b.items() if k != "_db"} for b in birthdays]
    return web.json_response(clean)


async def api_admin_export_csv(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not db.is_admin(user_id):
        return web.json_response({"error": "forbidden"}, status=403)
    birthdays = db.get_all_birthdays()
    users = {u["telegram_id"]: u for u in db.get_all_users()}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User Name", "Telegram ID", "Full Name", "Date of Birth",
                      "Relationship", "Gift Required", "Congratulation Text", "Notes"])
    for b in birthdays:
        user = users.get(b["user_id"], {})
        writer.writerow([
            user.get("full_name", "Unknown"), b["user_id"],
            b["full_name"], b["date_of_birth"], b["relationship"],
            "Yes" if b["gift_required"] else "No",
            b["congratulation_text"], b["notes"],
        ])
    return web.Response(
        text=output.getvalue(),
        content_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=all_birthdays.csv"},
    )


async def api_admin_calendar(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not db.is_admin(user_id):
        return web.json_response({"error": "forbidden"}, status=403)
    month = int(request.query.get("month", date.today().month))
    year = int(request.query.get("year", date.today().year))
    birthdays = db.get_all_birthdays()
    month_birthdays = []
    for b in birthdays:
        parts = b["date_of_birth"].split("-")
        if len(parts) == 3 and int(parts[1]) == month:
            clean = {k: v for k, v in b.items() if k != "_db"}
            clean["day"] = int(parts[2])
            month_birthdays.append(clean)
    cal = calendar.monthcalendar(year, month)
    return web.json_response({
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "weeks": cal,
        "birthdays": month_birthdays,
    })


async def api_admin_create_ad(request: web.Request) -> web.Response:
    user_id = _get_user_id(request)
    if not db.is_admin(user_id):
        return web.json_response({"error": "forbidden"}, status=403)
    data = await request.json()
    if not data.get("message"):
        return web.json_response({"error": "message is required"}, status=400)
    aid = db.add_advertisement(user_id, data["message"])
    return web.json_response({"id": aid, "status": "created"})


def create_app() -> web.Application:
    app = web.Application()

    # Pages
    app.router.add_get("/", index)
    app.router.add_get("/birthdays", birthdays_page)
    app.router.add_get("/congrats", congrats_page)
    app.router.add_get("/admin", admin_page)

    # Birthday API
    app.router.add_get("/api/birthdays", api_birthdays_list)
    app.router.add_post("/api/birthdays", api_birthday_create)
    app.router.add_get("/api/birthdays/search", api_birthday_search)
    app.router.add_get("/api/birthdays/stats", api_birthday_stats)
    app.router.add_get("/api/birthdays/export", api_birthday_export_csv)
    app.router.add_get("/api/birthdays/calendar", api_birthday_calendar)
    app.router.add_get("/api/birthdays/{id}", api_birthday_get)
    app.router.add_put("/api/birthdays/{id}", api_birthday_update)
    app.router.add_delete("/api/birthdays/{id}", api_birthday_delete)

    # Congratulation texts API
    app.router.add_get("/api/congrats", api_congrats_list)
    app.router.add_post("/api/congrats", api_congrats_create)
    app.router.add_get("/api/congrats/search", api_congrats_search)
    app.router.add_get("/api/congrats/{id}", api_congrats_get)
    app.router.add_put("/api/congrats/{id}", api_congrats_update)
    app.router.add_delete("/api/congrats/{id}", api_congrats_delete)

    # Admin API
    app.router.add_get("/api/admin/stats", api_admin_stats)
    app.router.add_get("/api/admin/birthdays", api_admin_all_birthdays)
    app.router.add_get("/api/admin/export", api_admin_export_csv)
    app.router.add_get("/api/admin/calendar", api_admin_calendar)
    app.router.add_post("/api/admin/ads", api_admin_create_ad)

    # Static files
    if os.path.isdir(STATIC_DIR):
        app.router.add_static("/static", STATIC_DIR)

    return app
