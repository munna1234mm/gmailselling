
import asyncio
import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application
import database as db
import admin_bot
import user_bot

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)

async def main():
    # Initialize Database
    # Start Keep Alive Server (For Render/Railway)
    import keep_alive
    keep_alive.keep_alive()

    await db.init_db()
    print("Database initialized.")

    # Create Applications
    admin_token = os.getenv("ADMIN_BOT_TOKEN")
    user_token = os.getenv("USER_BOT_TOKEN")

    if not admin_token or not user_token:
        print("Error: Bot tokens not found in .env")
        return

    # Set connection timeouts to be more generous
    admin_app = Application.builder().token(admin_token).read_timeout(30).write_timeout(30).build()
    user_app = Application.builder().token(user_token).read_timeout(30).write_timeout(30).build()

    # Add Handlers
    admin_app.add_handlers(admin_bot.get_admin_handler())
    user_app.add_handlers(user_bot.get_user_handler())
    user_app.add_error_handler(user_bot.error_handler)

    # Run both apps
    async with admin_app:
        await admin_app.start()
        await admin_app.bot.delete_webhook(drop_pending_updates=True) # Ensure clean slate
        await admin_app.updater.start_polling()
        
        async with user_app:
            await user_app.start()
            await user_app.bot.delete_webhook(drop_pending_updates=True) # Ensure clean slate
            await user_app.updater.start_polling()
            
            print("✅ Bots started successfully. Press Ctrl+C to stop.")
            
            # Keep the application running
            try:
                stop_signal = asyncio.Event()
                await stop_signal.wait()
            except asyncio.CancelledError:
                print("Stopping bots...")
            finally:
                await user_app.updater.stop()
                await user_app.stop()
        
        await admin_app.updater.stop()
        await admin_app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
