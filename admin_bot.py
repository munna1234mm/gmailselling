
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler, CallbackQueryHandler
import database as db
import json
from dotenv import load_dotenv

load_dotenv()
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")

# States
ADDING_ACCOUNTS = 1
SETTING_PRICE = 2
SETTING_REF_BONUS = 3
BROADCAST_MSG = 4
DM_USER_ID = 5
DM_MSG = 6
SETTING_RECOVERY = 7
SETTING_NAMES = 8

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Register as admin
    await db.add_admin(user_id)
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Accounts", callback_data="add_accounts")],
        [InlineKeyboardButton("⏳ Pending Approvals", callback_data="approvals")],
        [InlineKeyboardButton("💰 Pending Withdrawals", callback_data="withdrawals")], 
        [InlineKeyboardButton("💵 Set Price", callback_data="set_price"), InlineKeyboardButton("🎁 Set Ref Bonus", callback_data="set_ref_bonus")],
        [InlineKeyboardButton("📧 Set Recovery Email", callback_data="set_recovery"), InlineKeyboardButton("📝 Set Names", callback_data="set_names")], 
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast"), InlineKeyboardButton("✉️ DM User", callback_data="dm_user")], 
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "👨‍💼 *Admin Panel*"
    
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except:
             await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    available, sold, users = await db.get_stats()
    price = await db.get_price()
    ref_bonus = await db.get_referral_bonus()
    recovery = await db.get_recovery_email()
    first, last = await db.get_names()
    
    text = (
        f"📊 *Statistics*\n\n"
        f"✅ Available Accounts: {available}\n"
        f"💰 Sold Accounts: {sold}\n"
        f"👥 Total Users: {users}\n"
        f"💵 Current Price: ${price}\n"
        f"🎁 Referral Bonus: ${ref_bonus}\n"
        f"📧 Recovery Email: `{recovery}`\n"
        f"📝 Names: `{first} {last}`"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

# --- Names Flow ---
async def names_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    first, last = await db.get_names()
    await query.edit_message_text(
        f"Current: First=`{first}`, Last=`{last}`\n\n"
        "Send new names in format: `Firstname Lastname`\n"
        "Example: `John Smith`\n"
        "Type `Any Any` to reset.",
        parse_mode="Markdown"
    )
    return SETTING_NAMES

async def set_names_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("❌ Invalid format. Use `Firstname Lastname` (space separated).")
        return SETTING_NAMES
        
    first, last = parts
    await db.set_names(first, last)
    await update.message.reply_text(f"✅ Names updated to: First=`{first}`, Last=`{last}`", parse_mode="Markdown")
    await start(update, context)
    return ConversationHandler.END

# --- Recovery Email Flow ---
async def recovery_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = await db.get_recovery_email()
    await query.edit_message_text(
        f"Current Recovery Email: `{current}`\n\n"
        "Send me the new Recovery Email (or type 'None' to remove):",
        parse_mode="Markdown"
    )
    return SETTING_RECOVERY

async def set_recovery_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    await db.set_recovery_email(text)
    await update.message.reply_text(f"✅ Recovery Email updated to `{text}`", parse_mode="Markdown")
    await start(update, context)
    return ConversationHandler.END

# --- Broadcast Flow ---
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📢 *Broadcast*\n\nEnter the message you want to send to ALL users:", parse_mode="Markdown")
    return BROADCAST_MSG

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    users = await db.get_all_users()
    
    user_bot = Bot(token=USER_BOT_TOKEN)
    count = 0
    
    status_msg = await update.message.reply_text(f"⏳ Sending to {len(users)} users...")
    
    for uid in users:
        try:
            await user_bot.send_message(uid, f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            count += 1
        except Exception as e:
            logging.error(f"Failed to broadcast to {uid}: {e}")
            pass # Blocked or error
            
    await status_msg.edit_text(f"✅ Broadcast sent to {count} users.")
    await start(update, context)
    return ConversationHandler.END

# --- DM User Flow ---
async def dm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✉️ *DM User*\n\nEnter the User ID you want to message:", parse_mode="Markdown")
    return DM_USER_ID

async def dm_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Invalid ID. Enter numbers only.")
        return DM_USER_ID
        
    context.user_data['dm_target'] = int(text)
    await update.message.reply_text(f"📝 Enter message for User `{text}`:", parse_mode="Markdown")
    return DM_MSG

async def dm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    target_id = context.user_data.get('dm_target')
    
    user_bot = Bot(token=USER_BOT_TOKEN)
    try:
        await user_bot.send_message(target_id, f"📩 *Message from Admin*\n\n{text}", parse_mode="Markdown")
        await update.message.reply_text(f"✅ Message sent to `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send: {e}")
        
    await start(update, context)
    return ConversationHandler.END

# --- Withdrawals Flow ---
async def view_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    withdrawals = await db.get_pending_withdrawals()
    
    if not withdrawals:
        await query.edit_message_text(
            "✅ No pending withdrawals.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]])
        )
        return

    wid, user_id, amount, method, details, date = withdrawals[0]
    
    try:
        det_json = json.loads(details)
        det_str = "\n".join([f"{k}: {v}" for k,v in det_json.items()])
    except:
        det_str = details

    keyboard = [
        [InlineKeyboardButton("✅ Paid", callback_data=f"pay_{wid}"), InlineKeyboardButton("❌ Reject", callback_data=f"rejectpay_{wid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ]
    
    await query.edit_message_text(
        f"💰 *Pending Withdrawal ({len(withdrawals)} left)*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"💸 Amount: `${amount:.2f}`\n"
        f"💳 Method: `{method}`\n"
        f"📋 Details:\n`{det_str}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_withdrawal_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, wid = data.split("_")
    
    status = 'paid' if action == 'pay' else 'rejected'
    
    success, user_id = await db.mark_withdrawal(wid, status)
    
    if success:
         await query.message.reply_text(f"Action {status.upper()} performed on Withdrawal {wid}.")
         msg = "✅ Your withdrawal request has been PAID!" if status == 'paid' else "❌ Your withdrawal request was REJECTED and funds refunded."
         try:
             user_bot = Bot(token=USER_BOT_TOKEN)
             await user_bot.send_message(user_id, msg)
         except Exception as e:
             logging.error(f"Failed to notify user {user_id}: {e}")
    
    await view_withdrawals(update, context)

# --- Approvals Flow ---
async def view_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    approvals = await db.get_pending_approvals()
    
    if not approvals:
        await query.edit_message_text(
            "✅ No pending approvals.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]])
        )
        return

    acc_id, email, password, user_id = approvals[0]
    
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{acc_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{acc_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ]
    
    await query.edit_message_text(
        f"⏳ *Pending Approval ({len(approvals)} left)*\n\n"
        f"📧 Email: `{email}`\n"
        f"🔑 Pass: `{password}`\n"
        f"👤 User ID: `{user_id}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_approval_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, acc_id = data.split("_")
    
    user_bot = Bot(token=USER_BOT_TOKEN)
    
    if action == "approve":
        success, user_id = await db.approve_account(acc_id)
        if success:
             await query.message.reply_text(f"✅ Account {acc_id} Approved.")
             try:
                 await user_bot.send_message(user_id, "✅ Your account submission has been APPROVED! Funds moved to Available Balance.")
             except Exception as e:
                 logging.error(f"Failed to notify user {user_id}: {e}")
                 
    elif action == "reject":
        success, user_id = await db.reject_account(acc_id)
        if success:
            await query.message.reply_text(f"❌ Account {acc_id} Rejected.")
            try:
                 await user_bot.send_message(user_id, "❌ Your account submission was REJECTED.")
            except Exception as e:
                 logging.error(f"Failed to notify user {user_id}: {e}")

    await view_approvals(update, context)

# --- Add Accounts Flow ---
async def add_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Send me the accounts in `email:password` format.\n"
        "Or `email:password:firstname:lastname` to assign specific names.\n"
        "You can send a list or a file.\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    return ADDING_ACCOUNTS

async def add_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    count = 0
    failed = 0
    
    lines = text.split('\n')
    for line in lines:
        if ':' in line:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                email = parts[0].strip()
                password = parts[1].strip()
                first = parts[2].strip() if len(parts) > 2 else "Any"
                last = parts[3].strip() if len(parts) > 3 else "Any"
                
                if await db.add_account(email, password, first, last):
                    count += 1
                else:
                    failed += 1
    
    await update.message.reply_text(f"✅ Added {count} accounts.\n❌ Failed/Duplicate: {failed}")
    await start(update, context)
    return ConversationHandler.END

async def add_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    content = await file.download_as_bytearray()
    text = content.decode('utf-8')
    
    count = 0
    failed = 0
    
    lines = text.split('\n')
    for line in lines:
        if ':' in line:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                email = parts[0].strip()
                password = parts[1].strip()
                first = parts[2].strip() if len(parts) > 2 else "Any"
                last = parts[3].strip() if len(parts) > 3 else "Any"
                
                if await db.add_account(email, password, first, last):
                    count += 1
                else:
                    failed += 1
                
    await update.message.reply_text(f"✅ (File) Added {count} accounts.\n❌ Failed/Duplicate: {failed}")
    await start(update, context)
    return ConversationHandler.END

# --- Set Price & Bonus Flow ---
async def price_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = await db.get_price()
    await query.edit_message_text(
        f"Current price: ${current}\nSend me the new price (e.g. 0.25):",
        parse_mode="Markdown"
    )
    return SETTING_PRICE

async def set_price_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        price = float(text)
        await db.set_price(price)
        await update.message.reply_text(f"✅ Price updated to ${price}")
        await start(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")
        return SETTING_PRICE

async def ref_bonus_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = await db.get_referral_bonus()
    await query.edit_message_text(
        f"Current Referral Bonus: ${current}\nSend me the new bonus amount (e.g. 0.05):",
        parse_mode="Markdown"
    )
    return SETTING_REF_BONUS

async def set_ref_bonus_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        price = float(text)
        await db.set_referral_bonus(price)
        await update.message.reply_text(f"✅ Referral Bonus updated to ${price}")
        await start(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")
        return SETTING_REF_BONUS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action cancelled.")
    await start(update, context)
    return ConversationHandler.END

def get_admin_handler():
    cancel_handler = CommandHandler("cancel", cancel)
    start_handler = CommandHandler("start", start)

    conv_add = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start_callback, pattern="^add_accounts$")],
        states={
            ADDING_ACCOUNTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_accounts),
                MessageHandler(filters.Document.ALL, add_file)
            ]
        },
        fallbacks=[cancel_handler, start_handler]
    )
    
    conv_price = ConversationHandler(
        entry_points=[CallbackQueryHandler(price_start_callback, pattern="^set_price$")],
        states={
            SETTING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price_val)]
        },
        fallbacks=[cancel_handler, start_handler]
    )
    
    conv_ref = ConversationHandler(
        entry_points=[CallbackQueryHandler(ref_bonus_start_callback, pattern="^set_ref_bonus$")],
        states={
            SETTING_REF_BONUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_ref_bonus_val)]
        },
        fallbacks=[cancel_handler, start_handler]
    )
    
    conv_rec = ConversationHandler(
        entry_points=[CallbackQueryHandler(recovery_start_callback, pattern="^set_recovery$")],
        states={
            SETTING_RECOVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_recovery_val)]
        },
        fallbacks=[cancel_handler, start_handler]
    )
    
    conv_names = ConversationHandler(
        entry_points=[CallbackQueryHandler(names_start_callback, pattern="^set_names$")],
        states={
            SETTING_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_names_val)]
        },
        fallbacks=[cancel_handler, start_handler]
    )
    
    conv_broad = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^broadcast$")],
        states={
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)]
        },
        fallbacks=[cancel_handler, start_handler]
    )
    
    conv_dm = ConversationHandler(
        entry_points=[CallbackQueryHandler(dm_start, pattern="^dm_user$")],
        states={
            DM_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, dm_get_id)],
            DM_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, dm_send)]
        },
        fallbacks=[cancel_handler, start_handler]
    )

    return [
        start_handler,
        conv_add,
        conv_price,
        conv_ref,
        conv_rec,
        conv_names,
        conv_broad,
        conv_dm,
        CallbackQueryHandler(stats, pattern="^stats$"),
        CallbackQueryHandler(view_approvals, pattern="^approvals$"),
        CallbackQueryHandler(handle_approval_action, pattern="^(approve|reject)_"),
        CallbackQueryHandler(view_withdrawals, pattern="^withdrawals$"),
        CallbackQueryHandler(handle_withdrawal_action, pattern="^(pay|rejectpay)_"),
        CallbackQueryHandler(back_home, pattern="^back_home$")
    ]
