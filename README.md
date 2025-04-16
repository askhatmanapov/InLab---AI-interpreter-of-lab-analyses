# 🧬 InLab – AI interpreter of lab analyses

**InLab** is a multilingual AI-powered lab result interpreter built for clinicians and patients. It reads lab reports (PDFs, images, or photos), processes them through OCR and GPT models, and returns structured interpretations in natural language — directly within Telegram or integrated lab workflows.

## 🚀 Live Use

- 🏥 Deployed in multiple Kazakhstani clinics
- 🤖 Telegram bot with 400+ active users
- 🌐 Web-based platform integration in progress

---

## 💡 Features

- 📄 PDF and image analysis via Google Vision OCR
- 🤖 GPT-based medical interpretation (OpenAI GPT-4o)
- 🗣️ Supports English, Russian, and Kazakh
- 📋 Point-based usage system with integrated Robokassa payments
- 🔁 Recommends medical specialists based on findings
- 🔐 Secure, token-controlled API webhook support

---

## 🛠 Tech Stack

- **Frontend**: Telegram Bot API (custom UI), Vue.js (WIP)
- **Backend**: Python, FastAPI, Telebot
- **AI/ML**: OpenAI GPT-4o, Google Vision OCR, Tiktoken
- **Database**: PostgreSQL
- **Payments**: Robokassa Integration
- **Languages**: HTML parsing for GPT-safe formatting (Telegram)

---

## 📦 Key Modules

- `bot.py`: Telegram bot logic and message routing
- `pdf_analysis.py`: OCR + GPT-4-based interpretation of lab reports
- `database.py`: PostgreSQL interactions (user states, payments, invoices)
- `payment.py`: Secure Robokassa integration and invoice validation
- `translations.py`: Internationalization strings (KZ, RU, EN)

---

## 📷 Sample Use Case

1. User sends lab PDF or photo
2. InLab interprets and formats result
3. Interpretation is sent in Telegram with inline buttons for specialist follow-up
4. Points are deducted, and session is logged

---

## 📈 Future Work

- Web-based portal for lab integration (via API)
- QR-coded reports with embedded result links
- Physician-facing dashboards
- Scalable multi-tenant deployment

---

## 👨‍💻 Author

**Askhat Manapov**  
Lead Developer – InLab  
📧 askhat.manapov@nu.edu.kz 

---

## 🔐 Disclaimer

❗❗ The interpretation provided by the Inlab platform is not and cannot be considered a diagnosis, which only a qualified doctor can determine.
