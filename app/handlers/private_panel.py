from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import OWNER_ID
from app.db import db
from app.filters import IsOwner, IsAdminOrOwner
from app.keyboards import owner_panel, admin_panel, confirm_keyboard
from app.states import OwnerStates, AdminStates

router = Router()


# ---------- Helpers ----------

async def _format_user(bot, user_id: int) -> str:
    """
    Returns: "123456 | First Last (@username)" or fallback "123456"
    Note: bot.get_chat(user_id) may fail if bot can't access that user.
    """
    try:
        chat = await bot.get_chat(user_id)
        name = (chat.full_name or "").strip()
        username = getattr(chat, "username", None)
        if username:
            if name:
                return f"{user_id} | {name} (@{username})"
            return f"{user_id} | (@{username})"
        if name:
            return f"{user_id} | {name}"
        return str(user_id)
    except Exception:
        return str(user_id)


# ---------- START / PANEL ----------

@router.message(F.chat.type == "private", F.text == "/start")
async def start_private(message: Message):
    # Owner sees owner panel by default
    if message.from_user.id == OWNER_ID:
        await message.answer("Owner Panel", reply_markup=owner_panel())
        return

    if await db.is_admin(message.from_user.id):
        await message.answer("Admin Panel", reply_markup=admin_panel())
        return

    await message.answer("You are not authorized.")


# Owner can open admin panel explicitly
@router.message(F.chat.type == "private", F.text == "/admin")
async def owner_open_admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("You are not authorized.")
        return
    await message.answer("Admin Panel", reply_markup=admin_panel())


# ---------- OWNER: ADD ADMIN ----------

@router.callback_query(IsOwner(), F.data == "owner:add_admin")
async def owner_add_admin(cb: CallbackQuery, state: FSMContext):
    await state.set_state(OwnerStates.waiting_for_admin_id)
    await cb.message.answer("Send numeric user_id to add as Admin:")
    await cb.answer()


@router.message(IsOwner(), OwnerStates.waiting_for_admin_id)
async def owner_receive_admin_id(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("ID must be numeric.")
        return

    user_id = int(message.text)
    await state.update_data(user_id=user_id)

    await message.answer(
        f"Add user `{user_id}` as Admin?",
        reply_markup=confirm_keyboard("add_admin"),
    )


@router.callback_query(IsOwner(), F.data == "confirm:add_admin")
async def owner_confirm_add_admin(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    await db.add_admin(user_id)
    await state.clear()

    await cb.message.answer(f"User {user_id} added as Admin.")
    await cb.answer()


# ---------- ADMIN/OWNER: ADD SAFE USER ----------

@router.callback_query(IsAdminOrOwner(), F.data == "admin:add_safe")
async def admin_add_safe(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_safe_user_id)
    await cb.message.answer("Send numeric user_id to add as SAFE:")
    await cb.answer()


@router.message(IsAdminOrOwner(), AdminStates.waiting_for_safe_user_id)
async def admin_receive_safe_user(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("ID must be numeric.")
        return

    user_id = int(message.text)
    await state.update_data(user_id=user_id)

    await message.answer(
        f"Add user `{user_id}` to SAFE list?",
        reply_markup=confirm_keyboard("add_safe"),
    )


@router.callback_query(IsAdminOrOwner(), F.data == "confirm:add_safe")
async def admin_confirm_add_safe(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")

    await db.add_safe(user_id)
    await state.clear()

    await cb.message.answer(f"User {user_id} added to SAFE list.")
    await cb.answer()


# ---------- LISTS (ADMIN + OWNER) ----------

@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:lists", "admin:lists"}))
async def show_lists(cb: CallbackQuery):
    safe_ids = await db.list_safe()
    admin_ids = await db.list_admins()
    bans = await db.list_bans()
    groups = await db.list_groups()

    lines = []
    lines.append("📋 Lists\n")

    lines.append(f"✅ SAFE users: {len(safe_ids)}")
    if safe_ids:
        formatted = []
        for uid in safe_ids[:30]:
            formatted.append(await _format_user(cb.bot, uid))
        lines.extend(formatted)
        if len(safe_ids) > 30:
            lines.append("...")

    lines.append("")
    lines.append(f"🛡️ Admins: {len(admin_ids)}")
    if admin_ids:
        formatted = []
        for uid in admin_ids[:30]:
            formatted.append(await _format_user(cb.bot, uid))
        lines.extend(formatted)
        if len(admin_ids) > 30:
            lines.append("...")

    lines.append("")
    lines.append(f"⛔ Bans: {len(bans)}")
    if bans:
        # Keep it compact: "user_id @ group_id"
        for (u, g) in bans[:30]:
            lines.append(f"{u} @ {g}")
        if len(bans) > 30:
            lines.append("...")

    lines.append("")
    lines.append(f"👥 Groups: {len(groups)}")
    if groups:
        for (gid, title) in groups[:30]:
            lines.append(f"{gid} | {title or '-'}")
        if len(groups) > 30:
            lines.append("...")

    await cb.message.answer("\n".join(lines))
    await cb.answer()


# ---------- FOLDERS (NOT IMPLEMENTED YET) ----------

@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:folders", "admin:folders"}))
async def folders_placeholder(cb: CallbackQuery):
    await cb.message.answer("📂 Folders: هنوز پیاده‌سازی نشده. (مرحله بعد)")
    await cb.answer()


# ---------- CANCEL ----------

@router.callback_query(F.data == "cancel")
async def cancel_action(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Action cancelled.")
    await cb.answer()
