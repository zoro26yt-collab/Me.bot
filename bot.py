import os
import logging
import re
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

SYSTEM_PROMPT = """أنت مساعد ذكاء اصطناعي متطور. تجيب بدقة ووضوح واحترافية.
تدعم العربية والإنجليزية وجميع اللغات. أجب بنفس لغة المستخدم."""

client = OpenAI(api_key=OPENAI_API_KEY)

user_histories: dict[int, list] = {}
MAX_HISTORY = 20

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

SOCIAL_MEDIA_PATTERNS = [
    r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/',
    r'(https?://)?(www\.)?instagram\.com/',
    r'(https?://)?(www\.)?tiktok\.com/',
    r'(https?://)?(www\.)?twitter\.com/',
    r'(https?://)?(www\.)?x\.com/',
    r'(https?://)?(www\.)?facebook\.com/',
    r'(https?://)?(www\.)?fb\.watch/',
]

def is_social_media_link(text: str) -> bool:
    for pattern in SOCIAL_MEDIA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def extract_url(text: str) -> str | None:
    url_pattern = r'https?://[^\s]+'
    match = re.search(url_pattern, text)
    return match.group(0) if match else None

async def download_video(url: str, update: Update) -> bool:
    ydl_opts = {
        'format': 'best[filesize<50M]/best',
        'outtmpl': '/tmp/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'max_filesize': 50 * 1024 * 1024,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            title = info.get('title', 'فيديو')
            with open(filename, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"📥 {title}",
                    supports_streaming=True
                )
            os.remove(filename)
            return True
    except Exception as e:
        logging.error(f"خطأ في التحميل: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_histories[update.effective_user.id] = []
    await update.message.reply_text(
        f"مرحباً {user}! 👋\n\n"
        "أنا بوت ذكاء اصطناعي متكامل يمكنني:\n\n"
        "🤖 الإجابة على أي سؤال\n"
        "📥 تحميل فيديوهات من:\n"
        "   • يوتيوب\n"
        "   • تيك توك\n"
        "   • إنستغرام\n"
        "   • تويتر/X\n"
        "   • فيسبوك\n\n"
        "فقط أرسل رابط أو اسألني أي شيء! 🚀\n\n"
        "الأوامر:\n"
        "/start - بدء جديد\n"
        "/clear - مسح المحادثة\n"
        "/help - المساعدة"
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_user.id] = []
    await update.message.reply_text("✅ تم مسح تاريخ المحادثة!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 كيفية الاستخدام:\n\n"
        "🔹 للمحادثة: اكتب أي سؤال\n"
        "🔹 للتحميل: أرسل رابط الفيديو مباشرة\n\n"
        "⚠️ ملاحظات التحميل:\n"
        "• الحجم الأقصى 50MB\n"
        "• بعض المقاطع الخاصة لا يمكن تحميلها\n"
        "• يوتيوب قد يكون محدوداً أحياناً"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if is_social_media_link(text):
        url = extract_url(text)
        if url:
            await update.message.reply_text("⏳ جاري التحميل... انتظر قليلاً")
            success = await download_video(url, update)
            if not success:
                await update.message.reply_text(
                    "❌ لم أتمكن من تحميل هذا المقطع.\n"
                    "الأسباب المحتملة:\n"
                    "• الفيديو خاص\n"
                    "• الحجم أكبر من 50MB\n"
                    "• الرابط غير صحيح"
                )
            return
    await update.message.chat.send_action("typing")
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": "user", "content": text})
    if len(user_histories[user_id]) > MAX_HISTORY:
        user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *user_histories[user_id]
            ],
            max_tokens=1000
        )
        reply = response.choices[0].message.content
        user_histories[user_id].append({"role": "assistant", "content": reply})
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(reply[i:i+4096])
        else:
            await update.message.reply_text(reply)
    except Exception as e:
        logging.error(f"خطأ: {e}")
        await update.message.reply_text("⚠️ حدث خطأ، حاول مرة أخرى.")

def main():
    print("🤖 البوت يعمل...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
