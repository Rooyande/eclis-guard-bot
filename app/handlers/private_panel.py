from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import OWNER_ID
from app.db import db
from app.filters import IsOwner, IsAdminOrOwner
from app.keyboards import owner_panel, admin_panel, confirm_keyboard
from app.states import OwnerStates, AdminStates

router = Router()


# ---------- Helpers ----------

async def _format_user(bot, user_id: int) -> str:
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


def _get_ctx_chat_id(data: dict) -> int | None:
    return data.get("active_chat_id")


async def _require_ctx(cb: CallbackQuery, state: FSMContext) -> int | None:
    data = await state.get_data()
    chat_id = _get_ctx_chat_id(data)
    if not chat_id:
        await cb.message.answer("اول Target (گروه/کانال) رو انتخاب کن. روی 🎯 Select Group/Channel بزن.")
        return None
    return int(chat_id)


# ---------- START / PANEL ----------

@router.message(F.chat.type == "private", F.text == "/start")
async def start_private(message: Message, state: FSMContext):
    if message.from_user.id == OWNER_ID:
        data = await state.get_data()
        await message.answer("Owner Panel", reply_markup=owner_panel(_get_ctx_chat_id(data)))
        return

    if await db.is_admin(message.from_user.id):
        data = await state.get_data()
        await message.answer("Admin Panel", reply_markup=admin_panel(_get_ctx_chat_id(data)))
        return

    await message.answer("You are not authorized.")


@router.message(F.chat.type == "private", F.text == "/admin")
async def owner_open_admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        await message.answer("You are not authorized.")
        return
    data = await state.get_data()
    await message.answer("Admin Panel", reply_markup=admin_panel(_get_ctx_chat_id(data)))


# ---------- CONTEXT: SELECT GROUP/CHANNEL ----------

@router.callback_query(IsAdminOrOwner(), F.data == "ctx:select")
async def ctx_select(cb: CallbackQuery, state: FSMContext):
    await cb.answer()  # important: answer immediately

    groups = await db.list_groups()
    if not groups:
        await cb.message.answer(
            "هیچ Group/Channel تو DB نیست.\n"
            "اول ربات رو به گروه/کانال اضافه کن تا تو جدول groups ثبت بشه."
        )
        return

    kb = InlineKeyboardBuilder()
    for chat_id, title, chat_type in groups[:50]:
        t = title or "-"
        kb.button(text=f"{t} ({chat_type})", callback_data=f"ctx:set:{chat_id}")
    kb.button(text="Close", callback_data="cancel")
    kb.adjust(1)

    await cb.message.answer("Target رو انتخاب کن:", reply_markup=kb.as_markup())


@router.callback_query(IsAdminOrOwner(), F.data.startswith("ctx:set:"))
async def ctx_set(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    try:
        _, _, chat_id_str = cb.data.split(":")
        chat_id = int(chat_id_str)
    except Exception:
        await cb.message.answer("Bad data.")
        return

    await state.update_data(active_chat_id=chat_id)

    if cb.from_user.id == OWNER_ID:
        await cb.message.answer(f"✅ Target set: {chat_id}", reply_markup=owner_panel(chat_id))
    else:
        await cb.message.answer(f"✅ Target set: {chat_id}", reply_markup=admin_panel(chat_id))


# ---------- OWNER: ADD ADMIN ----------

@router.callback_query(IsOwner(), F.data == "owner:add_admin")
async def owner_add_admin(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(OwnerStates.waiting_for_admin_id)
    await cb.message.answer("Send numeric user_id to add as Admin:")


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
    await cb.answer()
    data = await state.get_data()
    user_id = data.get("user_id")
    await db.add_admin(user_id)
    await state.clear()
    await cb.message.answer(f"User {user_id} added as Admin.")


# ---------- ADMIN/OWNER: ADD SAFE USER (TARGET) ----------

@router.callback_query(IsAdminOrOwner(), F.data == "admin:add_safe")
async def admin_add_safe(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return

    await state.set_state(AdminStates.waiting_for_safe_user_id)
    await cb.message.answer("Send numeric user_id to add as SAFE (for Target):")


@router.message(IsAdminOrOwner(), AdminStates.waiting_for_safe_user_id)
async def admin_receive_safe_user(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("ID must be numeric.")
        return

    data = await state.get_data()
    chat_id = _get_ctx_chat_id(data)
    if not chat_id:
        await message.answer("Target انتخاب نشده.")
        return

    user_id = int(message.text)
    await state.update_data(user_id=user_id)
    await message.answer(
        f"Add user `{user_id}` to SAFE list for `{chat_id}`?",
        reply_markup=confirm_keyboard("add_safe"),
    )


@router.callback_query(IsAdminOrOwner(), F.data == "confirm:add_safe")
async def admin_confirm_add_safe(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    user_id = data.get("user_id")
    chat_id = _get_ctx_chat_id(data)

    await db.add_safe(user_id, chat_id=int(chat_id))
    await state.clear()
    await cb.message.answer(f"✅ User {user_id} added to SAFE for {chat_id}.")


# ---------- REMOVE SAFE USER (TARGET) ----------

@router.callback_query(IsAdminOrOwner(), F.data == "admin:remove_safe")
async def remove_safe_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return

    safe_ids = await db.list_safe(chat_id)
    if not safe_ids:
        await cb.message.answer("SAFE list (Target) خالیه.")
        return

    kb = InlineKeyboardBuilder()
    for uid in safe_ids[:30]:
        kb.button(text=f"Remove {uid}", callback_data=f"safe:rm:{uid}")
    kb.button(text="Close", callback_data="cancel")
    kb.adjust(1)

    await cb.message.answer("کدوم کاربر از SAFE حذف بشه؟", reply_markup=kb.as_markup())


@router.callback_query(IsAdminOrOwner(), F.data.startswith("safe:rm:"))
async def do_remove_safe(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return

    try:
        user_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.message.answer("Bad data.")
        return

    await db.remove_safe(user_id, chat_id=chat_id)
    await cb.message.answer(f"✅ Removed {user_id} from SAFE for {chat_id}.")


# ---------- UNBAN MENUS (TARGET + GLOBAL) ----------

@router.callback_query(IsAdminOrOwner(), F.data.in_({"admin:unban", "owner:unban"}))
async def unban_menu_target(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return

    bans = await db.list_bans(chat_id)
    if not bans:
        await cb.message.answer("⛔ Ban list (Target) is empty.")
        return

    kb = InlineKeyboardBuilder()
    for (u, g) in bans[:30]:
        kb.button(text=f"Unban {u}", callback_data=f"do_unban:{u}:{chat_id}")
    kb.button(text="Close", callback_data="cancel")
    kb.adjust(1)
    await cb.message.answer("Select a ban to remove (Target):", reply_markup=kb.as_markup())


@router.callback_query(IsAdminOrOwner(), F.data.in_({"admin:unban_global", "owner:unban_global"}))
async def unban_menu_global(cb: CallbackQuery):
    await cb.answer()

    bans = await db.list_bans(None)
    if not bans:
        await cb.message.answer("⛔ Global ban list is empty.")
        return

    kb = InlineKeyboardBuilder()
    for (u, _) in bans[:30]:
        kb.button(text=f"Global Unban {u}", callback_data=f"do_unban_global:{u}")
    kb.button(text="Close", callback_data="cancel")
    kb.adjust(1)
    await cb.message.answer("Select a global ban to remove:", reply_markup=kb.as_markup())


@router.callback_query(IsAdminOrOwner(), F.data.startswith("do_unban:"))
async def do_unban(cb: CallbackQuery):
    await cb.answer()

    try:
        _, u_str, g_str = cb.data.split(":")
        user_id = int(u_str)
        group_id = int(g_str)
    except Exception:
        await cb.message.answer("Bad data.")
        return

    await db.remove_ban(user_id, group_id)

    unban_ok = False
    unban_err = None
    try:
        await cb.bot.unban_chat_member(chat_id=group_id, user_id=user_id, only_if_banned=True)
        unban_ok = True
    except Exception as e:
        unban_err = str(e)

    if unban_ok:
        await cb.message.answer(f"✅ Unbanned {user_id} in {group_id}.")
    else:
        await cb.message.answer(
            f"⚠️ Removed from DB but Telegram unban failed.\n"
            f"user_id={user_id} group_id={group_id}\n\nError:\n{unban_err}"
        )


@router.callback_query(IsAdminOrOwner(), F.data.startswith("do_unban_global:"))
async def do_unban_global(cb: CallbackQuery):
    await cb.answer()
    try:
        user_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.message.answer("Bad data.")
        return

    await db.remove_ban(user_id, None)
    await cb.message.answer(f"✅ Global unbanned {user_id} (DB).")


# ---------- LISTS (TARGET + GLOBAL) ----------

@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:lists", "admin:lists"}))
async def show_lists_target(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return

    safe_ids = await db.list_safe(chat_id)
    admin_ids = await db.list_admins()
    bans = await db.list_bans(chat_id)
    groups = await db.list_groups()

    lines = [f"📋 Lists (Target={chat_id})\n"]

    lines.append(f"✅ SAFE users: {len(safe_ids)}")
    for uid in safe_ids[:30]:
        lines.append(await _format_user(cb.bot, uid))
    if len(safe_ids) > 30:
        lines.append("...")

    lines.append("")
    lines.append(f"🛡️ Admins: {len(admin_ids)}")
    for uid in admin_ids[:30]:
        lines.append(await _format_user(cb.bot, uid))
    if len(admin_ids) > 30:
        lines.append("...")

    lines.append("")
    lines.append(f"⛔ Bans: {len(bans)}")
    for (u, _) in bans[:30]:
        lines.append(f"{u} @ {chat_id}")
    if len(bans) > 30:
        lines.append("...")

    lines.append("")
    lines.append(f"👥 Groups: {len(groups)}")
    for (gid, title, tp) in groups[:30]:
        lines.append(f"{gid} | {title or '-'} | {tp}")

    await cb.message.answer("\n".join(lines))


@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:lists_global", "admin:lists_global"}))
async def show_lists_global(cb: CallbackQuery):
    await cb.answer()

    safe_ids = await db.list_safe(None)
    bans = await db.list_bans(None)

    lines = ["📋 Lists (GLOBAL)\n"]

    lines.append(f"✅ GLOBAL SAFE: {len(safe_ids)}")
    for uid in safe_ids[:30]:
        lines.append(await _format_user(cb.bot, uid))
    if len(safe_ids) > 30:
        lines.append("...")

    lines.append("")
    lines.append(f"⛔ GLOBAL BANS: {len(bans)}")
    for (u, _) in bans[:30]:
        lines.append(str(u))
    if len(bans) > 30:
        lines.append("...")

    await cb.message.answer("\n".join(lines))


# ---------- FOLDERS / LINKS / CLONE (placeholder handlers for now) ----------

@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:folders", "admin:folders"}))
async def folders_placeholder(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return
    await cb.message.answer("📂 Folders: زیرساخت DB آماده شد. UI کاملش مرحله بعد.")


@router.callback_query(IsAdminOrOwner(), F.data.in_({"owner:links", "admin:links"}))
async def links_placeholder(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chat_id = await _require_ctx(cb, state)
    if not chat_id:
        return
    await cb.message.answer("🔗 Links: زیرساخت DB آماده شد. UI کاملش مرحله بعد.")


@router.callback_query(IsAdminOrOwner(), F.data == "clone:menu")
async def clone_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    src_chat_id = await _require_ctx(cb, state)
    if not src_chat_id:
        return

    await state.set_state(OwnerStates.waiting_for_clone_target_ids)
    await cb.message.answer(
        f"🧬 Clone from {src_chat_id}\n"
        "Send target chat_ids separated by space (example: `-1001 -1002 -1003`)"
    )


@router.message(IsAdminOrOwner(), OwnerStates.waiting_for_clone_target_ids)
async def clone_receive_targets(message: Message, state: FSMContext):
    data = await state.get_data()
    src_chat_id = data.get("active_chat_id")
    if not src_chat_id:
        await message.answer("Target (source) انتخاب نشده.")
        return

    parts = (message.text or "").split()
    targets = []
    for p in parts:
        try:
            targets.append(int(p))
        except Exception:
            pass

    if not targets:
        await message.answer("هیچ chat_id معتبری پیدا نشد.")
        return

    for dst in targets:
        await db.clone_group_data(int(src_chat_id), int(dst))

    await state.clear()
    await message.answer(f"✅ Cloned data from {src_chat_id} to {len(targets)} target(s).")


# ---------- CANCEL ----------
@router.callback_query(F.data == "cancel")
async def cancel_action(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer("Action cancelled.")
