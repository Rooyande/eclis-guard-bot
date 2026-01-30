from aiogram import Router, F
from aiogram.types import Message

from app.db import db

router = Router()

# هر بار تو گروه اینو بزنید، گروه داخل DB ثبت/آپدیت میشه
@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "/register")
async def register_group(message: Message):
    await db.upsert_group(
        chat_id=message.chat.id,
        title=message.chat.title,
        chat_type=message.chat.type,
    )
    await message.reply(f"✅ Registered: {message.chat.id} | {message.chat.title}")
