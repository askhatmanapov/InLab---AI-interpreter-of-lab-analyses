import telebot
import io
import fitz #Import PyMuPDF
import openai
import tiktoken
import re
from decouple import config
import json
import bleach
import gc

TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN")
GOOGLE_CLOUD_CREDENTIALS = config("GOOGLE_CLOUD_CREDENTIALS")
OPENAI_API_KEY = config("OPENAI_API_KEY")

from google.cloud import vision
from database import subtract_points, get_points, get_user_language, record_timestamp, get_all_specialists, increment_rec_count
from translations import translations
from telebot.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton

client = vision.ImageAnnotatorClient.from_service_account_json(GOOGLE_CLOUD_CREDENTIALS)
openai.api_key = OPENAI_API_KEY
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
MAX_MESSAGE_LENGTH = 4096
DIRECT_THRESHOLD = 10000 
PRESUM_THRESHOLD = 40000
CHUNK_TOKEN_LIMIT = 8000 

languages = {
    '🇬🇧 English': 'en',
    '🇷🇺 Русский': 'ru',
    '🇰🇿 Қазақша': 'kz'
}

def send_message(user_id, message_key, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    user_language = get_user_language(user_id) 
    message = translations[user_language][message_key]
    return bot.send_message(user_id, message, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
def send_localized_message(user_id, message_key, reply_markup=None, **kwargs):
    user_language = get_user_language(user_id)
    message_template = translations[user_language].get(message_key, "Translation missing!")
    message = message_template.format(**kwargs) 
    return bot.send_message(user_id, message, reply_markup=reply_markup)
def sanitize_html(html_text):
    allowed_tags = ['b', 'i', 'u', 'a']
    allowed_attributes = {'a': ['href']}
    html_text = html_text.replace('<sup>', '^').replace('</sup>', '')
    html_text = html_text.replace('<br>', '\n')
    sanitized_text = bleach.clean(html_text, tags=allowed_tags, attributes=allowed_attributes)
    return sanitized_text

def is_main_bot():
    if config('IS_MAIN_BOT') == 'True':
        return True
    return False


def handle_pdf_analysis(bot, message):
    user_id = message.from_user.id
    record_timestamp(user_id) 
    if message.document:
        if message.document.file_size > 20*1024*1024:
            send_message(message.chat.id, 'too_large', parse_mode="HTML")
            return
        # Download the PDF file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Load PDF file
        pdf_stream = io.BytesIO(downloaded_file)
        # pdf_reader = PdfReader(pdf_stream)
        pdf_reader = fitz.open("pdf", pdf_stream.getvalue())
        total_pages = len(pdf_reader)
        required_points = total_pages * 50

        # Check if the user has enough points for the entire document
        if get_points(message.from_user.id) < required_points:
            user_id = message.from_user.id
            user_language = get_user_language(user_id)
            record_timestamp(user_id)
            insufficient_points = get_points(user_id)
            additional_points = required_points - insufficient_points
            markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton(text=translations[user_language]['payment']))
            if is_main_bot():
                send_localized_message(message.chat.id, 'insufficient', required_points=required_points, insufficient_points=insufficient_points, additional_points=additional_points, reply_markup=markup)
            else:
                send_localized_message(message.chat.id, 'premium', required_points=required_points, insufficient_points=insufficient_points, additional_points=additional_points, reply_markup=markup)
            return
        markup_remove = ReplyKeyboardRemove()
        
        progress_message = send_message(message.chat.id, 'data_analyzing', reply_markup=markup_remove)
        bot.send_chat_action(user_id, 'typing')
        user_id = message.from_user.id
        user_language = get_user_language(user_id)
        language = translations[user_language]['for_gpt']

        combined_text = ""
        for page_num in range(total_pages):
            bot.send_chat_action(user_id, 'typing')
            page = pdf_reader[page_num]
            page_text = page.get_text("text")
            image_texts = []
            
            for idx, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                base_image = pdf_reader.extract_image(xref)
                image_bytes = base_image["image"]
                image_data = vision.Image(content=image_bytes)
                response = client.text_detection(image=image_data)
                vision_text = response.text_annotations[0].description.strip() if response.text_annotations else ''
                image_texts.append(vision_text)
                del base_image, image_bytes, image_data, response, vision_text
                gc.collect()
            combined_text += page_text + "\n" + "\n".join(image_texts) + "\n"
            del page, page_text, image_texts
            gc.collect()
        pdf_reader.close()
        del pdf_reader
        del pdf_stream
        gc.collect()

        def estimate_token_count(text, model_name=" "):
            bot.send_chat_action(user_id, 'typing')
            try:
                encoding = tiktoken.encoding_for_model(model_name)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
            # print(f"Token number: {len(encoding.encode(text))}")
            return len(encoding.encode(text))

        def split_text_into_chunks(text, max_tokens, model_name=" "):
            encoding = tiktoken.encoding_for_model(model_name)
            tokens = encoding.encode(text)
            chunks = []
            for i in range(0, len(tokens), max_tokens):
                chunk_tokens = tokens[i:i+max_tokens]
                chunk_text = encoding.decode(chunk_tokens)
                chunks.append(chunk_text)
            return chunks
        def pre_summarize_text(text, language):
            bot.send_chat_action(user_id, 'typing')
            # print("Going through")
            prompt = (
                
            )
            response = openai.ChatCompletion.create(
                model=" ",
                messages=[
                    {"role": "system", "content": " "},
                    {"role": "user", "content": prompt}
                ],
                reasoning_effort=" "
            )
            # 
            return response.choices[0].message['content'].strip()
        
        token_count = estimate_token_count(combined_text, model_name=" ")
        
        if token_count <= DIRECT_THRESHOLD:
            aggregated_text = combined_text
            # print("Sending direct to ")
        elif token_count <= PRESUM_THRESHOLD:
            # print("Sending to ")
            aggregated_text = pre_summarize_text(combined_text, language)
        else:
            # print("Sending to ")
            chunks = split_text_into_chunks(combined_text, CHUNK_TOKEN_LIMIT, model_name=" ")
            pre_summaries = [pre_summarize_text(chunk, language) for chunk in chunks]
            aggregated_text = "\n".join(pre_summaries)
        
        specialists = get_all_specialists()
        specialists_str = ', '.join(specialists)
        final_prompt = (
            
        )
        
        while True:
            bot.send_chat_action(user_id, 'typing')
            try:
                final_response = openai.ChatCompletion.create(
                    model=" ",
                    messages=[
                        {"role": "system", "content": (
                            
                        )},
                        {"role": "user", "content": final_prompt}
                    ],
                    temperature,
                    top_p
                )
                response_text = final_response.choices[0].message['content'].strip()
                # print("GPT Response:\n", response_text)
            except openai.error.OpenAIError as e:
                print(f"OpenAI API error: {e}")
                send_message(user_id, "error_api", parse_mode="HTML")
                return
            except Exception as e:
                print(f"Unexpected error during OpenAI call: {e}")
                send_message(user_id, "error_generic", parse_mode="HTML")
                return
            json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                # print("Extracted JSON:\n", json_str)
                try:
                    json_str = json_str.replace('\\\\\n', '\\\\n')
                    data = json.loads(json_str)
                    update_specialist_recommendations([s.capitalize() for s in data['specialists']])
                    # print(repr(json_str))
                    break
                except Exception as e:
                    print("Error parsing JSON:", e)
                    print(repr(json_str))
            else:
                print("JSON extraction failed, full response:", response_text)
                continue
        # print("doing clean up")
        del combined_text
        del aggregated_text
        try: 
            del pre_summaries
        except: 
            pass
        try: 
            del chunks
        except: 
            pass
        del final_prompt
        del final_response
        del response_text
        del json_str
        # print("Aggregated arrays deleted")
        gc.collect()
        signature = translations[user_language]['signature']
        final_response_text = data['interpretation'] + signature
        bot.delete_message(chat_id=progress_message.chat.id, message_id=progress_message.message_id)
        final_response_chunks = [final_response_text[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(final_response_text), MAX_MESSAGE_LENGTH)]
        # print("Sending response")
        for chunk in final_response_chunks:
            try:
                chunk = sanitize_html(chunk)
                bot.send_chat_action(user_id, 'typing')
                if data['specialists']:
                    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
                    for specialist in [s.capitalize() for s in data['specialists']]:
                        button = telebot.types.InlineKeyboardButton(
                            text=specialist,
                            callback_data=f"specialist_{specialist}"
                        )
                        markup.add(button)
                    try:
                        bot.send_message(message.chat.id, chunk, reply_markup=markup, parse_mode="HTML")
                    except Exception as e:
                        print(f"Telegram send_message error:\n{e}")
                else:
                    bot.send_message(message.chat.id, chunk, parse_mode="HTML")
            except Exception as e:
                print(f"Error sending message to user {user_id}: {e}")
        subtract_points(message.from_user.id, required_points)
        del data
        del specialists_str
        del specialists
        del final_response_chunks
        gc.collect()
        current_points = get_points(user_id)
        markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        buttons = [
            KeyboardButton(text=translations[user_language]['analyse']),
            KeyboardButton(text=translations[user_language]['payment']),
            KeyboardButton(text=translations[user_language]['instruction']),
            KeyboardButton(text=translations[user_language]['info'])
        ]
        markup.add(*buttons)
        send_localized_message(message.chat.id, 'last_message', required_points=required_points, current_points=current_points, reply_markup=markup)

    elif message.photo:
        photo_file_id = message.photo[-1].file_id
        photo_info = bot.get_file(photo_file_id)
        downloaded_photo = bot.download_file(photo_info.file_path)
        required_points = 50

        if get_points(message.from_user.id) < required_points:
            user_id = message.from_user.id
            user_language = get_user_language(user_id)
            record_timestamp(user_id)
            insufficient_points = get_points(user_id)
            additional_points = required_points - insufficient_points
            markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            if is_main_bot():
                send_localized_message(message.chat.id, 'insufficient', required_points=required_points, insufficient_points=insufficient_points, additional_points=additional_points, reply_markup=markup)
            else:
                send_localized_message(message.chat.id, 'premium', required_points=required_points, insufficient_points=insufficient_points, additional_points=additional_points, reply_markup=markup)
            return
        markup_remove = ReplyKeyboardRemove()
        
        progress_message = send_message(message.chat.id, 'data_analyzing', reply_markup=markup_remove)
        bot.send_chat_action(user_id, 'typing')

        image_data = vision.Image(content=downloaded_photo)
        response = client.text_detection(image=image_data)
        combined_text = response.text_annotations[0].description.strip() if response.text_annotations else ''
        del image_data, response
        gc.collect()
        user_id = message.from_user.id
        user_language = get_user_language(user_id)
        language = translations[user_language]['for_gpt']
        specialists = get_all_specialists()
        specialists_str = ', '.join(specialists)

        while True: 
            bot.send_chat_action(user_id, 'typing')
            openai_prompt = (
                
            )
            # Send the prompt to OpenAI
            try:
                # print("Interpreting using")
                openai_response = openai.ChatCompletion.create(
                    model=" ",
                    messages=[
                        {"role": "system", "content": (
                           
                        )},
                        {"role": "user", "content": openai_prompt}
                    ],
                    temperature,
                    top_p
                )
                response_text = openai_response.choices[0].message['content'].strip()
                
            except openai.error.OpenAIError as e:
                print(f"OpenAI API error: {e}")
                send_message(user_id, "error_api", parse_mode="HTML")
                return
            except Exception as e:
                print(f"Unexpected error during OpenAI call: {e}")
                send_message(user_id, "error_generic", parse_mode="HTML")
                return
            json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                # print("Extracted JSON:\n", json_str)
                try:
                    json_str = json_str.replace('\\\\\n', '\\\\n')
                    data = json.loads(json_str)
                    update_specialist_recommendations([s.capitalize() for s in data['specialists']])
                    # print(repr(json_str))
                    break
                except Exception as e:
                    print("Error parsing JSON:", e)
                    print(repr(json_str))
            else:
                print("JSON extraction failed, full response:", response_text)
                continue
        
        del combined_text
        del openai_prompt
        del openai_response
        del response_text
        del json_str
        # print("Combined text deleted")
        gc.collect()
        signature = translations[user_language]['signature']
        final_response_text = data['interpretation'] + signature
        bot.delete_message(chat_id=progress_message.chat.id, message_id=progress_message.message_id)
        final_response_chunks = [final_response_text[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(final_response_text), MAX_MESSAGE_LENGTH)]
        
        for chunk in final_response_chunks:
            try:
                chunk = sanitize_html(chunk)
                bot.send_chat_action(user_id, 'typing')
                if data['specialists']:
                    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
                    for specialist in [s.capitalize() for s in data['specialists']]:
                        button = telebot.types.InlineKeyboardButton(
                            text=specialist,
                            callback_data=f"specialist_{specialist}"
                        )
                        markup.add(button)
                    try:
                        bot.send_message(message.chat.id, chunk, reply_markup=markup, parse_mode="HTML")
                    except Exception as e:
                        print(f"Telegram send_message error:\n{e}")
                else:
                    bot.send_message(message.chat.id, chunk, parse_mode="HTML")
            except Exception as e:
                print(f"Error sending message to user {user_id}: {e}")
        subtract_points(message.from_user.id, 50)
        del data
        del specialists_str
        del specialists
        del final_response_chunks
        gc.collect()
        current_points = get_points(user_id)
        markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        buttons = [
            KeyboardButton(text=translations[user_language]['analyse']),
            KeyboardButton(text=translations[user_language]['payment']),
            KeyboardButton(text=translations[user_language]['instruction']),
            KeyboardButton(text=translations[user_language]['info'])
        ]
        markup.add(*buttons)
        send_localized_message(message.chat.id, 'last_message', required_points=required_points, current_points=current_points, reply_markup=markup)

    else:
        send_message(message.chat.id, 'send_pdf')

def update_specialist_recommendations(specialists):
    for specialist in specialists:
        increment_rec_count(specialist)
