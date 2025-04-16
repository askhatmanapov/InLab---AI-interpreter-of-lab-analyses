import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)
import phonenumbers
import time
import os
import re
import threading
import hashlib
from fastapi import FastAPI, Request
import uvicorn
from decouple import config
# --- Database and other imports ---
from database import (
    get_db_connection, 
    initialize_db, 
    register_user, 
    add_points, 
    get_points, 
    user_exists, 
    add_user_language, 
    get_user_language, 
    record_timestamp, 
    store_invoice_in_db, 
    get_invoice_from_db,
    set_user_state,
    get_user_state,
    read_name,
    get_name,
    read_phone_number
)
from pdf_analysis import handle_pdf_analysis
from translations import translations
from payment import generate_payment_link

# ---------------------------------------
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = FastAPI()
initialize_db()
user_data = {}
user_data_lock = threading.Lock()
languages = {
    '🇬🇧 English': 'en',
    '🇷🇺 Русский': 'ru',
    '🇰🇿 Қазақша': 'kz'
}

# ---------------------------------------
# Helper functions
# ---------------------------------------
def send_message(user_id, message_key, reply_markup=None, parse_mode=None, disable_web_page_preview=None, **kwargs):
    user_language = get_user_language(user_id) 
    message = translations[user_language][message_key]
    return bot.send_message(user_id, message, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview, **kwargs)
def send_localized_message(user_id, message_key, reply_markup=None, **kwargs):
    user_language = get_user_language(user_id)
    message_template = translations[user_language].get(message_key, "Translation missing!")
    message = message_template.format(**kwargs) 
    return bot.send_message(user_id, message, reply_markup=reply_markup)
def language_selection_menu():
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for language in languages.keys():
        markup.add(KeyboardButton(language))
    return markup
def is_valid_name(name):
    return re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿА-Яа-яЁёҐґЇїІіЄє' -]+$", name.strip())

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    inline_markup = InlineKeyboardMarkup()
    for name, code in languages.items():
        inline_markup.add(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
    bot.send_message(
        message.chat.id, 
        "Please, choose the language:\n"
        "Пожалуйста, выберите язык:\n"
        "Өтініш, тілді таңдаңыз:", 
        reply_markup=inline_markup
    )

@bot.message_handler(func=lambda message: message.text in ["/register", "📝Register", "📝Регистрация", "📝Тіркелу"])
def ask_for_registration_info(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    user_exist = user_exists(user_id)
    user_language = get_user_language(user_id)
    if user_exist and user_exist['name'] and user_exist['phone_number'] and user_exist['user_state'] == 0:
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton(text=translations[user_language]['menu']))
        send_message(message.chat.id, 'already_register', reply_markup=markup)
    else:
        remove_markup = telebot.types.ReplyKeyboardRemove()
        set_user_state(user_id, 1)
        send_message(message.chat.id, 'ask_name', reply_markup=remove_markup, parse_mode='HTML')  

def process_name_step(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    if message.text == '/cancel':
        cancel_registration(user_id)
        set_user_state(user_id, 0)
        return
    
    name = message.text.strip()
    if not is_valid_name(name):
        send_message(message.chat.id, 'invalid_name')
        return

    start_timer(user_id, 300, cancel_registration)

    read_name(user_id, name)
    set_user_state(user_id, 2)
    send_message(message.chat.id, 'ask_phone', reply_markup=None, parse_mode='HTML')
        
def process_phone_number_step(message): 
    bot.send_chat_action(message.chat.id, 'typing') 
    user_id = message.from_user.id
    user_language = get_user_language(user_id)
    if message.text == '/cancel':
        cancel_registration(user_id)
        set_user_state(user_id, 0)
        return
    try:
        phone_number = phonenumbers.parse(message.text, None)
        if not phonenumbers.is_valid_number(phone_number):
            raise ValueError("Invalid phone number.")
        formatted_phone_number = phonenumbers.format_number(phone_number, phonenumbers.PhoneNumberFormat.E164)
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        send_message(message.chat.id, 'invalid_phone')
        return
    
    read_phone_number(user_id, formatted_phone_number)
    name = get_name(user_id)
    set_user_state(user_id, 3)
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(KeyboardButton(text=translations[user_language]['correct']))
    send_localized_message(message.chat.id, 'confirmation', name=name, formatted_phone_number=formatted_phone_number, reply_markup=markup)

def finalize_registration(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    bot.send_chat_action(message.chat.id, 'typing')
    record_timestamp(user_id)
    points_to_add = 500
    user_language = get_user_language(user_id)
    user_response = message.text.lower()
    correct_confirmation = translations[user_language]['correct'].lower().strip()
    if user_response == correct_confirmation:
        try:
            cancel_timer(user_id)
            register_user(user_id=user_id, points_to_add=points_to_add)
            set_user_state(user_id, 0)
            markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton(text=translations[user_language]['analyse']))

            send_message(chat_id, 'thanks_register', reply_markup=markup)
        except Exception as e:
            markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton(text=translations[user_language]['correct']))
            send_message(chat_id, 'final_confirmation', reply_markup=markup)
            return

    elif message.text == '/cancel':
        cancel_registration(user_id)
        set_user_state(user_id, 0)

    else:
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton(text=translations[user_language]['correct']))
        send_message(chat_id, 'final_confirmation', reply_markup=markup)

def cancel_registration(user_id):
    state = get_user_state(user_id)
    if state == 0:
        pass
    else:
        bot.send_chat_action(user_id, 'typing')
        set_user_state(user_id, 0)
        cancel_timer(user_id)
        record_timestamp(user_id)
        user_language = get_user_language(user_id)
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton(text=translations[user_language]['register']))
        markup.add(KeyboardButton(text=translations[user_language]['menu']))
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE user_points SET name = NULL, phone_number = NULL WHERE user_id = %s", (user_id,))
        conn.commit()
        c.close()
        conn.close()
        send_message(user_id, 'cancel_register', reply_markup=markup)

def start_timer(user_id, duration_seconds, callback):
    try:
        # print(user_id)
        if user_id in user_data:
            user_data[user_id].cancel()
            del user_data[user_id]
            # print(f"Deleted timer {user_id}")
        timer = threading.Timer(duration_seconds, callback, args=(user_id,))
        # print(f"Started timer {user_id}")
        user_data[user_id] = timer
        timer.start()
    except Exception as e:
        print(f"Error starting timer for user {user_id}: {e}")

def cancel_timer(user_id):
    try:
        if user_id in user_data:
            user_data[user_id].cancel()
            del user_data[user_id]
    except Exception as e:
        print(f"Error canceling timer for user {user_id}: {e}")

@bot.message_handler(commands=['language'])
def language_command(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    markup = language_selection_menu()
    bot.send_message(message.chat.id, "Please, choose the language:\nПожалуйста, выберите язык:\nӨтініш, тілді таңдаңыз:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["🇬🇧 English", "🇷🇺 Русский", "🇰🇿 Қазақша"])
def handle_language_change(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    language_code = languages.get(message.text, 'en')
    add_user_language(message.from_user.id, language_code)
    send_message(message.chat.id, 'language_set')
    show_menu(message)
# ---------------------------------------
# /analyse, /menu, /payment, /info, etc.
# ---------------------------------------
@bot.message_handler(func=lambda message: message.text in ["/analyse", "🔬 Analysis", "🔬 Анализировать", "🔬 Талдау"])
def analyze_pdf(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    user_language = get_user_language(user_id)

    inline_markup = InlineKeyboardMarkup()
    inline_markup.row(InlineKeyboardButton(translations[user_language]['Send_photo'], callback_data="analyse_1"))
    inline_markup.row(InlineKeyboardButton(translations[user_language]['Send_pdf_ios'], callback_data="analyse_2"))
    inline_markup.row(InlineKeyboardButton(translations[user_language]['Send_pdf_android'], callback_data="analyse_3"))
    inline_markup.row(InlineKeyboardButton(translations[user_language]['Send_screenshot'], callback_data="analyse_4"))


    send_message(message.chat.id, 'analysis_explained', reply_markup=inline_markup, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text in [trans['info'] for trans in translations.values()])
def show_info(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    points = get_points(user_id)
    send_localized_message(message.chat.id, 'info_message', points=points)

@bot.message_handler(func=lambda message: message.text in ["/menu", "🔗Menu", "🔗Меню", "🔗Мәзір"])
def show_menu(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    user_language = get_user_language(user_id)

    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        KeyboardButton(text=translations[user_language]['analyse']),
        KeyboardButton(text=translations[user_language]['payment']),
        KeyboardButton(text=translations[user_language]['instruction']),
        KeyboardButton(text=translations[user_language]['info']),
    ]
    markup.add(*buttons)
    send_message(message.chat.id, 'menu_text', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["/payment", "💰 Top up balance", "💰 Пополнить баланс", "💰 Баланс толтыру"])
def handle_payment(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    user_language = get_user_language(user_id)

    products = [
        {
            "name": translations[user_language]['product_500']['name'],
            "price": translations[user_language]['product_500']['price'],
            "callback_data": "product_500"
        },
        {
            "name": translations[user_language]['product_1000']['name'],
            "price": translations[user_language]['product_1000']['price'],
            "callback_data": "product_1000"
        }
    ]

    inline_markup = InlineKeyboardMarkup()
    for product in products:
        btn_text = f"{product['name']} - {product['price']}"
        button = InlineKeyboardButton(text=btn_text, callback_data=product['callback_data'])
        inline_markup.add(button)

    send_message(
        message.chat.id,
        'payment_text',
        reply_markup=inline_markup,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@bot.message_handler(func=lambda message: message.text in [trans['instruction'] for trans in translations.values()])
def show_help(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    send_message(message.chat.id, 'help_text')
group_handled = set()

@bot.message_handler(content_types=['document'])
def document_handler(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    remove_markup = ReplyKeyboardRemove()
    if message.media_group_id:
        if message.media_group_id not in group_handled:
            group_handled.add(message.media_group_id)
            send_message(message.chat.id, 'send_one', reply_markup=remove_markup)
    else:
        if message.document.mime_type == 'application/pdf':
            handle_pdf_analysis(bot, message)
        else:
            send_message(message.chat.id, 'send_pdf', reply_markup=remove_markup)

@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    record_timestamp(user_id)
    if message.media_group_id:
        if message.media_group_id not in group_handled:
            group_handled.add(message.media_group_id)
            remove_markup = ReplyKeyboardRemove()
            send_message(message.chat.id, 'send_one', reply_markup=remove_markup)
    else:
        handle_pdf_analysis(bot, message)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    if state == 1:
        process_name_step(message)
    elif state == 2:
        process_phone_number_step(message)
    elif state == 3:
        finalize_registration(message)
    else:
        user_language = get_user_language(user_id)
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton(text=translations[user_language]['menu']))
        send_message(message.chat.id, 'please_follow', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    record_timestamp(user_id)
    user_language = get_user_language(user_id)

    if call.data.startswith("product_"):
        product_id = call.data.split("_")[1]
        products = {
            "500": {"points": 500, "price": 500},
            "1000": {"points": 1000, "price": 990},
        }
        product = products.get(product_id)
        if product:
            title = translations[user_language]['product_title'].format(points=product['points'])
            description = translations[user_language]['product_title']
            timestamp = int(time.time()) % 10000000000
            invoice_id = timestamp

            store_invoice_in_db(invoice_id, user_id, product_id, product["points"], product["price"])

            payment_link = generate_payment_link(
                merchant_login=config("MERCHANT_LOGIN"),
                merchant_password_1=config("MERCHANT_PASSWORD_1"),
                cost=product['price'],
                number=invoice_id,
                description=description
            )
            inline_markup = InlineKeyboardMarkup()
            pay_button = InlineKeyboardButton(
                text="Нажмите, чтобы оплатить через защищенное окно оплаты",
                url=payment_link
            )
            inline_markup.add(pay_button)
            bot.send_message(
                call.message.chat.id,
                "Пожалуйста, нажмите кнопку ниже, чтобы перейти к оплате:",
                reply_markup=inline_markup
            )
            bot.answer_callback_query(call.id, text="Link generated!")
        else:
            bot.answer_callback_query(call.id, "An error occurred, please try again.")

    elif call.data.startswith("specialist_"):
        specialist_name = call.data.split("_", 1)[1]
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT d.name, d.position, d.phone, d.medical_center, d.address, d.price, d.link
            FROM doctors d
            INNER JOIN specialists s ON d.position = s.name
            WHERE s.name = %s
        """, (specialist_name,))
        rows = c.fetchall()
        c.close()
        conn.close()

        if rows:
            response = f"<b>Doctors for {specialist_name}:</b>\n"
            for row in rows:
                doctor_name = row[0]
                position = row[1]
                phone = row[2]
                medical_center = row[3]
                address = row[4]
                price = row[5]
                link = row[6]
                response += (
                    f"<b>Medical Center:</b> {medical_center}\n"
                    f"<b>Name:</b> {doctor_name}\n"
                    f"<b>Position:</b> {position}\n"
                    f"<b>Phone:</b> {phone}\n"
                    f"<b>Price:</b> {price} тг\n"
                    f"<b>Address:</b> <a href='{link}'>{address}</a>\n\n"
                )
        else:
            response = f"<b>No doctors found for {specialist_name}.</b>"

        bot.send_message(
            call.message.chat.id,
            response,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        bot.answer_callback_query(call.id)
    
    elif call.data.startswith("analyse_"):
        youtube_urls = {
            "analyse_1": "https://youtube.com/shorts/PTQ42gA6Wa0",
            "analyse_2": "https://youtube.com/shorts/W6hkqV9pqoM",
            "analyse_3": "https://youtube.com/shorts/ocUCgwgs4sw",
            "analyse_4": "https://youtube.com/shorts/7q21k8ipDvY",
        }
        
        # Retrieve the corresponding URL
        selected_url = youtube_urls.get(call.data, None)
        
        if selected_url:
            bot.send_message(call.message.chat.id, selected_url, disable_web_page_preview=False)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "An error occurred, please try again.")
    
    elif call.data.startswith("lang_"):
        language_code = call.data.split("_")[1]
        add_user_language(user_id, language_code)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        user_exist = user_exists(user_id)
        if user_exist and user_exist['name'] and user_exist['phone_number'] and user_exist['user_state'] == 0:
            # Already registered
            markup = telebot.types.ReplyKeyboardMarkup(
                one_time_keyboard=True, resize_keyboard=True
            )
            markup.add(KeyboardButton(text=translations[language_code]['analyse']))
            send_message(
                call.message.chat.id, 
                'welcome_back', 
                reply_markup=markup
            )
        else:
            # Not registered
            markup = telebot.types.ReplyKeyboardMarkup(
                one_time_keyboard=True, resize_keyboard=True
            )
            markup.add(KeyboardButton(text=translations[language_code]['register']))
            markup.add(KeyboardButton(text=translations[language_code]['menu']))
            send_message(
                call.message.chat.id, 
                'welcome_register', 
                reply_markup=markup
            )

        # We also need to answer the callback so the "Loading..." disappears
        bot.answer_callback_query(call.id)

        return
    
    else:
        bot.answer_callback_query(call.id, "Unknown action.")

# ---------------------------------------
# PAYMENT NOTIFICATION ENDPOINT
# ---------------------------------------
@app.api_route("/api/bot/payment", methods=["GET", "POST"])
async def handle_payment_notification(request: Request):
    data = dict(request.query_params)
    signature = data.get("SignatureValue")
    inv_id = data.get("InvId")
    out_sum = data.get("OutSum")

    try:
        inv_id = int(inv_id)
    except (ValueError, TypeError):
        return {"status": "fail", "reason": "Invalid InvId"}

    expected_signature = hashlib.md5(
        f"{out_sum}:{inv_id}:{os.getenv('MERCHANT_PASSWORD_2')}".encode('utf-8')
    ).hexdigest()

    if signature.lower() != expected_signature.lower():
        return {"status": "fail", "reason": "Invalid signature"}

    invoice = get_invoice_from_db(inv_id)
    if not invoice:
        return {"status": "fail", "reason": "Invoice not found"}
    user_id, points, processed = invoice
    if processed:
        return {"status": "success", "reason": "Already processed"}

    try:
        add_points(user_id, points)
    except Exception:
        return {"status": "fail", "reason": "Failed to add points"}

    try:
        user_language = get_user_language(user_id)
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton(text=translations[user_language]['analyse']))
        send_localized_message(user_id, 'successful_payment', points_based_on_product_id=points, reply_markup=markup)
    except Exception:
        return {"status": "fail", "reason": "Failed to send message"}

    # Mark as processed
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE invoices SET processed = TRUE WHERE invoice_id = %s", (inv_id,))
    conn.commit()
    c.close()
    conn.close()

    return {"status": "success"}
    
# ---------------------------------------
# TELEGRAM WEBHOOK
# ---------------------------------------
@app.post("/webhook/{secret_token}")
async def telegram_webhook(request: Request, secret_token: str):
    EXPECTED_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "SOME_RANDOM_SECRET")
    if secret_token != EXPECTED_SECRET:
        return {"status": "fail", "reason": "Invalid secret token"}

    body = await request.json()
    update = telebot.types.Update.de_json(body)
    bot.process_new_updates([update])
    return {"status": "ok"}

# ---------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------
if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)