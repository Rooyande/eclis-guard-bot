from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import OWNER_ID
from app.db import db
from app.filters import IsOwner, IsAdminOrOwner
from app.keyboards import owner_panel, admin_panel, confirm_keyboard
from app.states import OwnerStates, AdminStates

router = Router()


# ---------- START / PANEL ----------

@router.message(F.chat.type == "private", F.text == "/start")
async def start_private(message: Message):
    if message.from_user.id == OWNER_ID:
        await message.answer("Owner Panel", reply_markup=owner_panel())
        return

    if await db.is_admin(message.from_user.id):
        await message.answer("Admin Panel", reply_markup=admin_panel())
        return

    await message.answer("You are not authorized.")


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

def _chunk_lines(lines: list[str], limit: int = 60) -> list[str]:
    if not lines:
        return []
    out = []
    for i in range(0, len(lines), limit):
        out.append("\n".join(lines[i:i + limit]))
    return out


@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:lists", "admin:lists"}))
async def show_lists(cb: CallbackQuery):
    safe_ids = await db.list_safe()
    admin_ids = await db.list_admins()
    bans = await db.list_bans()
    groups = await db.list_groups()

    text = []
    text.append("📋 Lists\n")

    text.append(f"✅ SAFE users: {len(safe_ids)}")
    if safe_ids:
        preview = ", ".join(str(x) for x in safe_ids[:30])
        text.append(f"{preview}{' ...' if len(safe_ids) > 30 else ''}")
    text.append("")

    text.append(f"🛡️ Admins: {len(admin_ids)}")
    if admin_ids:
        preview = ", ".join(str(x) for x in admin_ids[:30])
        text.append(f"{preview}{' ...' if len(admin_ids) > 30 else ''}")
    text.append("")

    text.append(f"⛔ Bans: {len(bans)}")
    if bans:
        preview_pairs = [f"{u}@{g}" for (u, g) in bans[:20]]
        text.append(", ".join(preview_pairs) + (" ..." if len(bans) > 20 else ""))
    text.append("")

    text.append(f"👥 Groups: {len(groups)}")
    if groups:
        preview_groups = [f"{gid} | {title or '-'}" for (gid, title) in groups[:20]]
        text.append("\n".join(preview_groups) + ("\n..." if len(groups) > 20 else ""))

    await cb.message.answer("\n".join(text))
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
