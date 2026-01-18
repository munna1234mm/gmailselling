
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler
import database as db
import json
import os
import logging
from dotenv import load_dotenv

load_dotenv()
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

# States for Settings & Withdraw
SET_PAYMENT = 1
ENTER_PAYMENT_VALUE = 2
WITHDRAW_AMOUNT = 3

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logging.info(f"Start command received from user {update.effective_user.id}")
        user = update.effective_user
        args = context.args
        referrer_id = None
        
        if args and args[0].isdigit():
            referrer_id = int(args[0])
            if referrer_id == user.id:
                referrer_id = None
                
        is_new = await db.add_user(user.id, user.full_name, referrer_id)
        
        if is_new:
            # Notify Admins
            admins = await db.get_admins()
            if admins:
                admin_bot = Bot(token=ADMIN_BOT_TOKEN)
                for admin_id in admins:
                    try:
                        await admin_bot.send_message(admin_id, f"👤 *New Member Joined*\nName: {user.full_name}\nID: `{user.id}`", parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Failed to notify admin {admin_id}: {e}")

        keyboard = [
            ["➕ Register a new account", "📋 My accounts"],
            ["💰 Balance", "👥 My referrals"],
            ["⚙️ Settings", "💬 Help"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"👋 Hello {user.first_name}!\n"
            "Welcome to the Gmail Selling Bot.\n"
            "Select an option below to get started.",
            reply_markup=reply_markup
        )
        logging.info(f"Start reply sent to {user.id}")
    except Exception as e:
        logging.error(f"Error in start command: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again later.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        user_id = update.effective_user.id
        logging.info(f"Message received from {user_id}: {text}")
        
        if text == "➕ Register a new account":
            await register_account(update, context)
            
        elif text == "💰 Balance":
            balance, hold = await db.get_user_balance(user_id)
            keyboard = []
            if balance > 0.0:
                keyboard.append([InlineKeyboardButton("💸 Withdraw", callback_data="withdraw_start")])
                
            await update.message.reply_text(
                f"💰 *Wallet Balance*\n\n"
                f"✅ Available: ${balance:.2f}\n"
                f"⏳ Hold: ${hold:.2f}\n\n"
                "Funds in 'Hold' will be moved to 'Available' after admin approval (approx. 24h).",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
        elif text == "📋 My accounts":
            history = await db.get_user_history_list(user_id)
            if not history:
                await update.message.reply_text("You haven't sold any accounts yet.")
            else:
                msg = "📋 *My Last 10 Accounts:*\n\n"
                for email, password, date, status in history:
                    status_icon = "✅" if status == 'sold' else "⏳" if status == 'submitted' else "❌"
                    msg += f"{status_icon} `{email}`\n"
                await update.message.reply_text(msg, parse_mode="Markdown")
                
        elif text == "👥 My referrals":
            count = await db.get_referral_stats(user_id)
            bonus = await db.get_referral_bonus()
            bot_username = context.bot.username
            link = f"https://t.me/{bot_username}?start={user_id}"
            await update.message.reply_text(
                f"👥 *My Referrals*\n\n"
                f"💰 *Commission per Sale:* ${bonus:.2f}\n"
                f"👥 Total Referrals: {count}\n\n"
                f"🔗 *Your Referral Link:*\n`{link}`",
                parse_mode="Markdown"
            )
            
        elif text == "💬 Help":
            await update.message.reply_text("Contact @developermunna for support.")
            
        elif text == "⚙️ Settings":
            await settings_menu(update, context)

    except Exception as e:
        logging.error(f"Error in handle_message: {e}", exc_info=True)
        await update.message.reply_text("An error occurred processing your request.")

# --- Withdraw Flow ---
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    # Check if payment info exists
    pay_info = await db.get_payment_info(user_id)
    if not pay_info:
        await query.message.reply_text("⚠️ You have not set a payment method yet.\nPlease go to ⚙️ Settings > Payment Methods and save one first.")
        return ConversationHandler.END
        
    balance, _ = await db.get_user_balance(user_id)
    if balance < 0.50:
         await query.message.reply_text(f"⚠️ Minimum withdrawal is $0.50. You have ${balance:.2f}.")
         return ConversationHandler.END

    methods_str = ", ".join(pay_info.keys())
    await query.message.reply_text(
        f"💸 *Withdraw Request*\n\n"
        f"Available: ${balance:.2f}\n"
        f"Saved Methods: {methods_str}\n\n"
        "Enter the amount you want to withdraw (e.g. 5.00):",
        parse_mode="Markdown"
    )
    return WITHDRAW_AMOUNT

async def withdraw_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a number (e.g. 5.50) or /cancel.")
        return WITHDRAW_AMOUNT
        
    if amount <= 0:
         await update.message.reply_text("❌ Amount must be greater than 0.")
         return WITHDRAW_AMOUNT

    pay_info = await db.get_payment_info(user_id)
    details = json.dumps(pay_info)
    
    success, msg = await db.create_withdrawal(user_id, amount, "Manual", details)
    if success:
        await update.message.reply_text(f"✅ Withdrawal request of ${amount:.2f} submitted successfully!")
        
        # Notify Admins
        admins = await db.get_admins()
        if admins:
            admin_bot = Bot(token=ADMIN_BOT_TOKEN)
            for admin_id in admins:
                try:
                    await admin_bot.send_message(
                        admin_id, 
                        f"💸 *New Withdrawal Request*\n"
                        f"User ID: `{user_id}`\n"
                        f"Amount: `${amount:.2f}`",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.error(f"Failed to notify admin {admin_id}: {e}")
    else:
        await update.message.reply_text(f"❌ Error: {msg}")
        
    return ConversationHandler.END

# --- Settings Flow ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 Payment Methods", callback_data="settings_payment")],
        [InlineKeyboardButton("🌐 Language", callback_data="settings_language")],
        [InlineKeyboardButton("🚫 Close", callback_data="close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text("⚙️ *Settings*", reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text("⚙️ *Settings*", reply_markup=reply_markup, parse_mode="Markdown")

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "settings_payment":
        keyboard = [
            [InlineKeyboardButton("Binance UID", callback_data="pay_Binance")],
            [InlineKeyboardButton("Bkash", callback_data="pay_Bkash")],
            [InlineKeyboardButton("Nagad", callback_data="pay_Nagad")],
            [InlineKeyboardButton("Rocket", callback_data="pay_Rocket")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        user_id = query.from_user.id
        info = await db.get_payment_info(user_id)
        info_str = "\n".join([f"• {k}: `{v}`" for k,v in info.items()]) if info else "No methods set."
        
        await query.edit_message_text(
            f"💳 *Payment Methods*\n\nYour saved methods:\n{info_str}\n\nSelect a method to add/edit:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return SET_PAYMENT
        
    elif data == "settings_language":
         keyboard = [
            [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"), InlineKeyboardButton("🇧🇩 Bangla", callback_data="lang_bn")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
        ]
         await query.edit_message_text("🌐 Select Language:", reply_markup=InlineKeyboardMarkup(keyboard))
         
    elif data.startswith("lang_"):
        await query.edit_message_text("✅ Language set (Saved).")
        # Placeholder
        
    elif data == "settings_back":
        await settings_menu(update, context)
        return ConversationHandler.END
        
    elif data == "close":
        await query.delete_message()
        return ConversationHandler.END

async def payment_method_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data['payment_method'] = method
    
    label = "UID" if method == "Binance" else "Number"
    
    await query.edit_message_text(f"Enter your *{method} {label}*:")
    return ENTER_PAYMENT_VALUE

async def save_payment_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text
    method = context.user_data.get('payment_method')
    user_id = update.effective_user.id
    
    await db.update_payment_info(user_id, {method: value})
    
    await update.message.reply_text(f"✅ Saved {method}: `{value}`", parse_mode="Markdown")
    
    keyboard = [
        [InlineKeyboardButton("💳 Payment Methods", callback_data="settings_payment")],
        [InlineKeyboardButton("🌐 Language", callback_data="settings_language")],
        [InlineKeyboardButton("🚫 Close", callback_data="close")]
    ]
    await update.message.reply_text("⚙️ *Settings*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ConversationHandler.END

async def register_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    account = await db.get_available_account(user_id)
    
    if not account:
        await update.message.reply_text("⚠️ No accounts available. Please try again later.")
        return

    acc_id, email, password, first, last = account
    price = await db.get_price()
    recovery = await db.get_recovery_email()
    # first, last = await db.get_names() # Removed global names

    
    # Explicit instruction
    if recovery and recovery != "None":
        recovery_section = (
            f"\n🛡️ **Recovery Email:** `{recovery}`\n"
            "⚠️ *You MUST set this email as the recovery email for the account!*"
        )
    else:
        recovery_section = ""
    
    message = (
        f"Register account using the specified data and get ${price}\n\n"
        f"First name: `{first}`\n"
        f"Last name: `{last}`\n"
        f"Email: `{email}`\n"
        f"Password: `{password}`\n"
        f"{recovery_section}\n\n"
        "🔒 Be sure to use the specified data."
    )
    
    keyboard = [
        [InlineKeyboardButton("✔️ Done", callback_data="done")],
        [InlineKeyboardButton("🚫 Cancel registration", callback_data="cancel")],
        [InlineKeyboardButton("❓ How to create account", callback_data="help_create")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "done":
        try:
             success, msg, acc_info = await db.mark_account_submitted(user_id)
             if success:
                price = msg
                id_val, email, password, f, l = acc_info
                
                await query.edit_message_text(
                    f"✅ Account submitted for approval! You earned ${price} (Hold).\n"
                    "Admin will verify within 24 hours.\n"
                    "Check 'My accounts' for status."
                )
                
                # Notify Admins
                admins = await db.get_admins()
                if admins:
                    admin_bot = Bot(token=ADMIN_BOT_TOKEN)
                    for admin_id in admins:
                        try:
                             # Note: Admin needs to have started Admin Bot (or have chatted with it)? 
                             # YES. But here we are using ADMIN_BOT_TOKEN.
                             # If we use ADMIN_BOT_TOKEN, we are the Admin Bot.
                             # Can Admin Bot message the Admin? YES, because Admin started Admin Bot.
                             await admin_bot.send_message(admin_id, f"📥 *New Account Submitted*\nUser: `{user_id}`\nEmail: `{email}`", parse_mode="Markdown")
                        except Exception as e:
                            logging.error(f"Failed to notify admin {admin_id}: {e}")
             else:
                await query.edit_message_text(f"❌ Error: {msg}")
        except AttributeError:
             await query.edit_message_text("❌ System error.")

    elif data == "cancel":
        await db.cancel_registration(user_id)
        await query.edit_message_text("🚫 Registration cancelled. Account released.")

    elif data == "help_create":
        await query.message.reply_text("Go to gmail.com, click Create Account, use the provided email and password. Use a clean IP.")
        
    elif data == "close":
        await query.delete_message()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("An internal error occurred. Admin has been notified.")
        except:
             pass # If we can't reply, simple log is enough

def get_user_handler():
    cancel_handler = CommandHandler("cancel", cancel)
    
    # Settings Conversation
    conv_settings = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_callback, pattern="^settings_payment$")],
        states={
            SET_PAYMENT: [CallbackQueryHandler(payment_method_choice, pattern="^pay_")],
            ENTER_PAYMENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_payment_value)]
        },
        fallbacks=[cancel_handler, CallbackQueryHandler(settings_callback, pattern="^settings_back$"), CallbackQueryHandler(settings_callback, pattern="^close$")]
    )
    
    # Withdraw Conversation
    conv_withdraw = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw_start$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_process)]
        },
        fallbacks=[cancel_handler]
    )

    return [
        CommandHandler("start", start),
        conv_settings,
        conv_withdraw,
        
        CallbackQueryHandler(settings_callback, pattern="^settings_"),
        CallbackQueryHandler(settings_callback, pattern="^close$"),
        
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        CallbackQueryHandler(button_handler)
    ]
