#!/usr/bin/env python3
# Telegram Bot — aiogram v3 template
# Replace BOT_TOKEN and customize handlers

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

logging.basicConfig(level=logging.INFO)
bot = Bot(token="YOUR_BOT_TOKEN")
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(f"Hello, {message.from_user.first_name}!")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer("Commands:\n/start — start\n/help — help")

@dp.message()
async def echo(message: types.Message):
    await message.answer(f"You said: {message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
