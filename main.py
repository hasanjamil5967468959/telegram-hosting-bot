import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import io
import random

from flask import Flask
from threading import Thread

# ===== FLASK KEEP-ALIVE SERVER =====
app = Flask('')

@app.route('/')
def home():
    return """
<div style="font-family: Arial; padding: 20px;">
    <h1>🤖 Hosting Bot</h1>
    <p>✅ Bot is running</p>
    <p>Made with ❤️</p>
</div>
"""

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🌐 Flask Keep-Alive server started.")

# ===== BOT CONFIGURATION (Environment Variables) =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN environment variable not set!")
    print("⚠️  Set BOT_TOKEN in Render Environment Variables")
    sys.exit(1)

OWNER_ID = int(os.environ.get('OWNER_ID', '7274423729'))
ADMIN_ID = OWNER_ID
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@rudrohasan5967468959')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/carrompoolhack00')

# ==================== SAMBANOVA AI CONFIGURATION ====================
SAMBA_API_KEY = os.environ.get('SAMBA_API_KEY', '')
if not SAMBA_API_KEY:
    print("⚠️  WARNING: SAMBA_API_KEY not set. AI features will not work.")
SAMBA_URL = "https://api.sambanova.ai/v1/chat/completions"

AVAILABLE_MODELS = {
    'llama': 'Meta-Llama-3.3-70B-Instruct',
    'deepseek': 'DeepSeek-V3.1',
    'minimax': 'MiniMax-M2.7',
    'gpt-oss': 'gpt-oss-120b'
}
DEFAULT_MODEL = 'llama'
global_model = DEFAULT_MODEL
# =====================================================================

# ===== DIRECTORY SETUP (Render-compatible) =====
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# ===== USER LIMITS =====
FREE_USER_LIMIT = 4
SUBSCRIBED_USER_LIMIT = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# ===== CREATE DIRECTORIES =====
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# ===== PERSISTENT UPTIME =====
PERSISTENT_START_FILE = os.path.join(IROTECH_DIR, 'bot_start_time.txt')

def get_persistent_start_time():
    if os.path.exists(PERSISTENT_START_FILE):
        try:
            with open(PERSISTENT_START_FILE, 'r') as f:
                timestamp = f.read().strip()
                return datetime.fromisoformat(timestamp)
        except Exception as e:
            logging.error(f"Failed to read persistent start time: {e}")
    now = datetime.now()
    try:
        with open(PERSISTENT_START_FILE, 'w') as f:
            f.write(now.isoformat())
    except Exception as e:
        logging.error(f"Failed to write persistent start time: {e}")
    return now

BOT_START_TIME = get_persistent_start_time()

# ===== BOT INITIALIZATION =====
bot = telebot.TeleBot(BOT_TOKEN)

# ===== DATA STORAGE =====
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
user_clones = {}
banned_users = set()
user_limits = {}
mandatory_channels = {}
github_data = {}
auto_recovery_last_restart = {}

# ===== LOGGING SETUP =====
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== DATABASE LOCK =====
DB_LOCK = threading.Lock()

# ===== KEYBOARD LAYOUTS =====
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["🤖 Contact Bot", "📞 Contact Owner"],
    ["📦 Manual Install"],
    ["📦 Pkg Install", "🤖 AI Agent"],
    ["🐙 GitHub Deploy"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcasts"],
    ["🔒 Lock Bot", "🏢 Run All Scripts"],
    ["👑 Admin Panel", "🤖 Contact Bot"],
    ["📢 Channel Add", "🛠️ Mandatory Install"],
    ["👥 User Management", "⚙️ Settings"],
    ["🔄 Restart", "⏹ Stop"],
    ["📦 Pkg Install", "🤖 AI Agent"],
    ["🐙 GitHub Deploy"],
    ["📤 Updates Channel", "📞 Contact Owner"]
]

# ===== DATABASE FUNCTIONS =====
def init_db():
    logger.info(f"🗄️ Initializing Database: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS clone_bots
                     (user_id INTEGER PRIMARY KEY, bot_username TEXT, token TEXT, create_time TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, file_id TEXT, file_name TEXT, file_type TEXT,
            file_size INTEGER, user_name TEXT, user_username TEXT,
            timestamp TEXT, extra_info TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mandatory_channels
                     (channel_id TEXT PRIMARY KEY,
                      channel_username TEXT,
                      channel_name TEXT,
                      added_by INTEGER,
                      added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS install_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      module_name TEXT,
                      package_name TEXT,
                      status TEXT,
                      log TEXT,
                      install_date TEXT)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
             c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("📥 Loading Data From Database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry date format for user {user_id}: {expiry}. Skipping.")

        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id, file_limit FROM user_limits')
        for user_id, file_limit in c.fetchall():
            user_limits[user_id] = file_limit

        c.execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels')
        for channel_id, channel_username, channel_name in c.fetchall():
            mandatory_channels[channel_id] = {
                'username': channel_username,
                'name': channel_name
            }

        c.execute('SELECT user_id, bot_username, token, create_time FROM clone_bots')
        for user_id, bot_username, token, create_time in c.fetchall():
            try:
                user_clones[user_id] = {
                    'bot_username': bot_username,
                    'token': token,
                    'create_time': datetime.fromisoformat(create_time)
                }
                logger.info(f"✅ Loaded clone bot @{bot_username} for user {user_id}")
            except ValueError:
                logger.warning(f"⚠️ Invalid Create_Time Format For Clone Bot For User: {user_id}")

        conn.close()
        logger.info(f"✅ Data Loaded: 👥 {len(active_users)} Users, 💳 {len(user_subscriptions)} Subscriptions, 👑 {len(admin_ids)} Admins, 🤖 {len(user_clones)} Clones.")
    except Exception as e:
        logger.error(f"❌ Error Data: {e}", exc_info=True)

# ===== CLONE BOT FUNCTIONS =====
def save_clone_info(user_id, bot_username, token):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO clone_bots (user_id, bot_username, token, create_time) VALUES (?, ?, ?, ?)',
                      (user_id, bot_username, token, datetime.now().isoformat()))
            conn.commit()
            user_clones[user_id] = {
                'bot_username': bot_username,
                'token': token,
                'create_time': datetime.now()
            }
            logger.info(f"✅ Saved Clone Bot @{bot_username} For User {user_id}")
        except Exception as e:
            logger.error(f"❌ Error Saving Clone Bot {user_id}: {e}", exc_info=True)
        finally:
            conn.close()

def remove_clone_info(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM clone_bots WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_clones:
                del user_clones[user_id]
            logger.info(f"🗑️ Removed Clone Bot For User {user_id}")
        except Exception as e:
            logger.error(f"❌ Error removing clone bot for {user_id}: {e}", exc_info=True)
        finally:
            conn.close()

# ===== MANDATORY CHANNELS FUNCTIONS =====
def is_user_member(user_id, channel_id):
    try:
        chat_member = bot.get_chat_member(channel_id, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking channel membership for {user_id} in {channel_id}: {e}")
        return False

def check_mandatory_subscription(user_id):
    if not mandatory_channels:
        return True, []
    not_joined = []
    for channel_id, channel_info in mandatory_channels.items():
        if not is_user_member(user_id, channel_id):
            not_joined.append((channel_id, channel_info))
    if not_joined:
        return False, not_joined
    return True, []

def save_mandatory_channel(channel_id, channel_username, channel_name, added_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            added_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_username, channel_name, added_by, added_date) VALUES (?, ?, ?, ?, ?)',
                      (channel_id, channel_username, channel_name, added_by, added_date))
            conn.commit()
            mandatory_channels[channel_id] = {
                'username': channel_username,
                'name': channel_name
            }
            logger.info(f"Saved mandatory channel: {channel_name} ({channel_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Error saving channel: {e}", exc_info=True)
            return False
        finally:
            conn.close()

def remove_mandatory_channel_db(channel_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (channel_id,))
            conn.commit()
            if channel_id in mandatory_channels:
                del mandatory_channels[channel_id]
            logger.info(f"Removed mandatory channel: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error removing channel: {e}", exc_info=True)
            return False
        finally:
            conn.close()

def create_mandatory_channels_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Channel', callback_data='add_mandatory_channel'),
        types.InlineKeyboardButton('➖ Remove Channel', callback_data='remove_mandatory_channel')
    )
    markup.row(types.InlineKeyboardButton('📋 List Channels', callback_data='list_mandatory_channels'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_check_message(not_joined_channels):
    message = "📢 **Important: Join Our Channels First:**\n\n"
    markup = types.InlineKeyboardMarkup()
    for channel_id, channel_info in not_joined_channels:
        channel_username = channel_info.get('username', '')
        channel_name = channel_info.get('name', 'Channel')
        if channel_username:
            channel_link = f"https://t.me/{channel_username.replace('@', '')}"
        else:
            channel_link = f"https://t.me/c/{channel_id.replace('-100', '')}"
        message += f"• {channel_name}\n"
        markup.add(types.InlineKeyboardButton(f"Join", url=channel_link))
    markup.add(types.InlineKeyboardButton("✅ Verify", callback_data='check_subscription_status'))
    return message, markup

# ===== USER MANAGEMENT DB FUNCTIONS =====
def is_user_banned(user_id):
    return user_id in banned_users

def ban_user_db(user_id, reason, banned_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            ban_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, ban_date) VALUES (?, ?, ?, ?)',
                      (user_id, reason, banned_by, ban_date))
            conn.commit()
            banned_users.add(user_id)
            logger.warning(f"User {user_id} banned by {banned_by}. Reason: {reason}")
            return True
        except Exception as e:
            logger.error(f"❌ Error banning user {user_id}: {e}", exc_info=True)
            return False
        finally:
            conn.close()

def unban_user_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
            conn.commit()
            banned_users.discard(user_id)
            logger.info(f"User {user_id} unbanned")
            return True
        except Exception as e:
            logger.error(f"❌ Error unbanning user {user_id}: {e}", exc_info=True)
            return False
        finally:
            conn.close()

def set_user_limit_db(user_id, limit, set_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            set_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO user_limits (user_id, file_limit, set_by, set_date) VALUES (?, ?, ?, ?)',
                      (user_id, limit, set_by, set_date))
            conn.commit()
            user_limits[user_id] = limit
            logger.info(f"Set file limit {limit} for user {user_id} by {set_by}")
            return True
        except Exception as e:
            logger.error(f"❌ Error setting limit for user {user_id}: {e}", exc_info=True)
            return False
        finally:
            conn.close()

def remove_user_limit_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_limits WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_limits:
                del user_limits[user_id]
            logger.info(f"Removed custom limit for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error removing limit for user {user_id}: {e}", exc_info=True)
            return False
        finally:
            conn.close()

# ===== INITIALIZE DATABASE AND LOAD DATA =====
init_db()
load_data()

# ===== USER FOLDER MANAGEMENT =====
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

# ===== USER FILE LIMIT =====
def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in user_limits: return user_limits[user_id]
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

# ===== USER FILE COUNT =====
def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

# ===== CHECK IF BOT IS RUNNING =====
def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                logger.warning(f"⚠️ Process {script_info['process'].pid} for {script_key} found in memory but not running/zombie. Cleaning up.")
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except Exception as log_e:
                        logger.error(f"❌ Error closing log file during zombie cleanup {script_key}: {log_e}")
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            logger.warning(f"⚠️ Process for {script_key} not found (NoSuchProcess). Cleaning up.")
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                     script_info['log_file'].close()
                except Exception as log_e:
                     logger.error(f"❌ Error closing log file during cleanup of non-existent process {script_key}: {log_e}")
            if script_key in bot_scripts:
                 del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"❌ Error checking process status for {script_key}: {e}", exc_info=True)
            return False
    return False

# ===== KILL PROCESS TREE =====
def kill_process_tree(process_info):
    pid = None
    log_file_closed = False
    script_key = process_info.get('script_key', 'N/A')

    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
                log_file_closed = True
                logger.info(f"📜 Closed Log File For {script_key}")
            except Exception as log_e:
                logger.error(f"❌ Error Closing Log File For {script_key}: {log_e}")

        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
           pid = process.pid
           if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    logger.info(f"🔪 Attempting To Kill Process Tree For {script_key} (PID: {pid}, Children: {[c.pid for c in children]})")

                    for child in children:
                        try:
                            child.terminate()
                            logger.info(f"🔪 Terminated Child Process {child.pid} For {script_key}")
                        except psutil.NoSuchProcess:
                            logger.warning(f"⚠️ Child Process {child.pid} For {script_key} Already Gone.")
                        except Exception as e:
                            logger.error(f"❌ Error Terminating Child {child.pid} For {script_key}: {e}")
                            try: child.kill(); logger.info(f"💀 Killed Child Process {child.pid} For {script_key}")
                            except Exception as e2: logger.error(f"❌ Failed To Kill Child {child.pid}: {e2}")

                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        logger.warning(f"⚠️ Child process {p.pid} for {script_key} still alive. Killing.")
                        try: p.kill()
                        except Exception as e: logger.error(f"❌ Failed to kill child {p.pid} for {script_key} after wait: {e}")

                    try:
                        parent.terminate()
                        logger.info(f"🔪 Terminated parent process {pid} for {script_key}")
                        try: parent.wait(timeout=1)
                        except psutil.TimeoutExpired:
                            logger.warning(f"⚠️ Parent process {pid} for {script_key} did not terminate. Killing.")
                            parent.kill()
                            logger.info(f"💀 Killed parent process {pid} for {script_key}")
                    except psutil.NoSuchProcess:
                        logger.warning(f"⚠️ Parent process {pid} for {script_key} already gone.")
                    except Exception as e:
                        logger.error(f"❌ Error terminating parent {pid} for {script_key}: {e}. Trying kill...")
                        try: parent.kill(); logger.info(f"💀 Killed parent process {pid} for {script_key}")
                        except Exception as e2: logger.error(f"❌ Failed to kill parent {pid} for {script_key}: {e2}")

                except psutil.NoSuchProcess:
                    logger.warning(f"⚠️ Process {pid or 'N/A'} for {script_key} not found during kill. Already terminated?")
           else: logger.error(f"❌ Process PID is None for {script_key}.")
        elif log_file_closed: logger.warning(f"⚠️ Process object missing for {script_key}, but log file closed.")
        else: logger.error(f"❌ Process object missing for {script_key}, and no log file. Cannot kill.")
    except Exception as e:
        logger.error(f"❌ Unexpected error killing process tree for PID {pid or 'N/A'} ({script_key}): {e}", exc_info=True)

# ===== PYTHON MODULES MAPPING =====
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'tgcrypto': 'tgcrypto',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'pillow': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'django': 'Django',
    'sqlalchemy': 'SQLAlchemy',
    'asyncio': None, 'json': None, 'datetime': None, 'os': None, 'sys': None,
    're': None, 'time': None, 'math': None, 'random': None, 'logging': None,
    'threading': None, 'subprocess': None, 'zipfile': None, 'tempfile': None,
    'shutil': None, 'sqlite3': None, 'psutil': 'psutil', 'atexit': None
}

def save_install_log(user_id, module_name, package_name, status, log):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            install_date = datetime.now().isoformat()
            c.execute('INSERT INTO install_logs (user_id, module_name, package_name, status, log, install_date) VALUES (?, ?, ?, ?, ?, ?)',
                      (user_id, module_name, package_name, status, log, install_date))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error saving install log: {e}", exc_info=True)
        finally:
            conn.close()

def attempt_install_pip(module_name, message, manual_request=False):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        return False, "Core module"
    try:
        if manual_request:
            bot.reply_to(message, f"🔧 Manual Installation\n📦 Requested For `{module_name}` -> `{package_name}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"🐍 Module `{module_name}` not found. Installing...", parse_mode='Markdown')

        command = [sys.executable, '-m', 'pip', 'install', package_name]
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')

        if result.returncode == 0:
            log_msg = f"Installed {package_name}."
            logger.info(log_msg)
            bot.reply_to(message, f"✅ Package `{package_name}` Installed Successfully", parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, package_name, "success", log_msg)
            return True, log_msg
        else:
            error_msg = f"❌ Failed to install `{package_name}` for `{module_name}`.\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (truncated)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, package_name, "failed", error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"❌ Error installing `{package_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        save_install_log(message.from_user.id, module_name, package_name, "error", error_msg)
        return False, error_msg

def attempt_install_npm(module_name, user_folder, message, manual_request=False):
    try:
        if manual_request:
            bot.reply_to(message, f"🔧 Manual Node package installation requested for `{module_name}`...", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"🟠 Node package `{module_name}` not found. Installing locally...", parse_mode='Markdown')

        command = ['npm', 'install', module_name]
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')

        if result.returncode == 0:
            log_msg = f"Installed {module_name}."
            logger.info(log_msg)
            bot.reply_to(message, f"✅ Node package `{module_name}` installed locally.", parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, module_name, "success", log_msg)
            return True, log_msg
        else:
            error_msg = f"❌ Failed to install Node package `{module_name}`.\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (truncated)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            save_install_log(message.from_user.id, module_name, module_name, "failed", error_msg)
            return False, error_msg
    except FileNotFoundError:
         error_msg = "❌ Error: 'npm' not found."
         logger.error(error_msg)
         bot.reply_to(message, error_msg)
         save_install_log(message.from_user.id, module_name, module_name, "error", error_msg)
         return False, error_msg
    except Exception as e:
        error_msg = f"❌ Error installing Node package `{module_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        save_install_log(message.from_user.id, module_name, module_name, "error", error_msg)
        return False, error_msg

# ===== RUN PYTHON SCRIPT =====
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"🐍 Attempt {attempt} to run Python script: {script_path} (Key: {script_key})")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"⚠️ File not found.")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        logger.info(f"📦 Detected missing Python module: {module_name}")
                        _pip_ok, _pip_log = attempt_install_pip(module_name, message_obj_for_reply)
                        if _pip_ok:
                            bot.reply_to(message_obj_for_reply, f"✅ Install successful. Retrying '{file_name}'...")
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Install failed. Cannot run '{file_name}'.")
                            return
                    else:
                         error_summary = stderr[:500]
                         bot.reply_to(message_obj_for_reply, f"⚠️ Error in script pre-check for '{file_name}':\n```\n{error_summary}\n```", parse_mode='Markdown')
                         return
            except subprocess.TimeoutExpired:
                logger.info("⏱️ Python Pre-check timed out. Killing check process.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                 logger.error(f"❌ Python interpreter not found: {sys.executable}")
                 bot.reply_to(message_obj_for_reply, f"❌ Error: Python interpreter not found.")
                 return
            except Exception as e:
                 logger.error(f"❌ Error in Python pre-check for {script_key}: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"⚠️ Unexpected error in script pre-check: {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     check_proc.kill(); check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
             logger.error(f"❌ Failed to open log file '{log_file_path}': {e}", exc_info=True)
             bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
             return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"✅ Started Python process {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ Python script '{file_name}' started! (PID: {process.pid})")
        except FileNotFoundError:
             logger.error(f"❌ Python interpreter not found for long run {script_key}")
             bot.reply_to(message_obj_for_reply, f"❌ Error: Python interpreter not found.")
             if log_file and not log_file.closed: log_file.close()
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ Error starting Python script '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Unexpected error running Python script '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

# ===== RUN JAVASCRIPT SCRIPT =====
def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"📜 Attempt {attempt} to run JS script: {script_path} (Key: {script_key})")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"⚠️ File not found.")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if attempt == 1:
            check_command = ['node', script_path]
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                             _npm_ok, _npm_log = attempt_install_npm(module_name, user_folder, message_obj_for_reply)
                             if _npm_ok:
                                 bot.reply_to(message_obj_for_reply, f"✅ NPM Install successful. Retrying '{file_name}'...")
                                 time.sleep(2)
                                 threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                 return
                             else:
                                 bot.reply_to(message_obj_for_reply, f"❌ NPM Install failed. Cannot run '{file_name}'.")
                                 return
                    error_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"⚠️ Error in JS script pre-check for '{file_name}':\n```\n{error_summary}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                logger.info("⏱️ JS Pre-check timed out. Killing check process.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                 error_msg = "❌ Error: 'node' not found."
                 logger.error(error_msg)
                 bot.reply_to(message_obj_for_reply, error_msg)
                 return
            except Exception as e:
                 logger.error(f"❌ Error in JS pre-check for {script_key}: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"⚠️ Unexpected error in JS pre-check: {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     check_proc.kill(); check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"❌ Failed to open log file '{log_file_path}': {e}", exc_info=True)
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"✅ Started JS process {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ JS script '{file_name}' started! (PID: {process.pid})")
        except FileNotFoundError:
             error_msg = "❌ Error: 'node' not found for long run."
             logger.error(error_msg)
             if log_file and not log_file.closed: log_file.close()
             bot.reply_to(message_obj_for_reply, error_msg)
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ Error starting JS script '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Unexpected error running JS script '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

# ===== SAVE USER FILE =====
def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
            logger.info(f"💾 Saved file '{file_name}' ({file_type}) for user {user_id}")
        except Exception as e: logger.error(f"❌ Error saving file for {user_id}, {file_name}: {e}", exc_info=True)
        finally: conn.close()

# ===== REMOVE USER FILE =====
def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
            logger.info(f"🗑️ Removed file '{file_name}' for user {user_id} from DB")
        except Exception as e: logger.error(f"❌ Error removing file for {user_id}, {file_name}: {e}", exc_info=True)
        finally: conn.close()

# ===== ADD ACTIVE USER =====
def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
        except Exception as e: logger.error(f"❌ Error adding active user {user_id}: {e}", exc_info=True)
        finally: conn.close()

# ===== SAVE SUBSCRIPTION =====
def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
            logger.info(f"💳 Saved subscription for {user_id}, expiry {expiry_str}")
        except Exception as e: logger.error(f"❌ Error saving subscription for {user_id}: {e}", exc_info=True)
        finally: conn.close()

# ===== REMOVE SUBSCRIPTION =====
def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions: del user_subscriptions[user_id]
            logger.info(f"🗑️ Removed subscription for {user_id} from DB")
        except Exception as e: logger.error(f"❌ Error removing subscription for {user_id}: {e}", exc_info=True)
        finally: conn.close()

# ===== ADD ADMIN =====
def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id)
            logger.info(f"👑 Added admin {admin_id} to DB")
        except Exception as e: logger.error(f"❌ Error adding admin {admin_id}: {e}", exc_info=True)
        finally: conn.close()

# ===== REMOVE ADMIN =====
def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        logger.warning("⚠️ Attempted to remove OWNER_ID from admins.")
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        removed = False
        try:
            c.execute('SELECT 1 FROM admins WHERE user_id = ?', (admin_id,))
            if c.fetchone():
                c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
                conn.commit()
                removed = c.rowcount > 0
                if removed: admin_ids.discard(admin_id); logger.info(f"🗑️ Removed admin {admin_id} from DB")
            else:
                logger.warning(f"⚠️ Admin {admin_id} not found in DB.")
                admin_ids.discard(admin_id)
            return removed
        except Exception as e: logger.error(f"❌ Error removing admin {admin_id}: {e}", exc_info=True); return False
        finally: conn.close()

# ===== CREATE KEYBOARDS =====
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🤖 AI Fix", callback_data=f'aifix_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔙 Back", callback_data='check_files')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🏢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🤖 AI Fix", callback_data=f'aifix_{script_owner_id}_{file_name}')
        )
        markup.row(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_user_management_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('🚫 Ban User', callback_data='ban_user'),
        types.InlineKeyboardButton('✅ Unban User', callback_data='unban_user')
    )
    markup.row(
        types.InlineKeyboardButton('📊 User Info', callback_data='user_info'),
        types.InlineKeyboardButton('👥 All Users', callback_data='all_users')
    )
    markup.row(
        types.InlineKeyboardButton('🔧 Set User Limit', callback_data='set_user_limit'),
        types.InlineKeyboardButton('🗑️ Remove User Limit', callback_data='remove_user_limit')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_admin_settings_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📊 System Info', callback_data='system_info'),
        types.InlineKeyboardButton('📈 Bot Performance', callback_data='bot_performance')
    )
    markup.row(
        types.InlineKeyboardButton('🧹 Cleanup Files', callback_data='cleanup_files'),
        types.InlineKeyboardButton('📋 Installation Logs', callback_data='install_logs')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription')
    )
    markup.row(
        types.InlineKeyboardButton('📋 List Subscriptions', callback_data='list_subscriptions')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    return markup

# ===== HANDLE ZIP FILE =====
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        logger.info(f"📦 Temp dir for zip: {temp_dir}")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file: new_file.write(downloaded_file_content)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not member_path.startswith(os.path.abspath(temp_dir)):
                    raise zipfile.BadZipFile(f"⚠️ Zip has unsafe path: {member.filename}")
            zip_ref.extractall(temp_dir)
            logger.info(f"📂 Extracted zip to {temp_dir}")

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            logger.info(f"📦 requirements.txt found, installing: {req_path}")
            bot.reply_to(message, f"⚠️ Installing Python deps from `{req_file}`...")
            try:
                command = [sys.executable, '-m', 'pip', 'install', '-r', req_path]
                result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
                logger.info(f"✅ pip install from requirements.txt OK.")
                bot.reply_to(message, f"✅ Python deps from `{req_file}` installed.")
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ Failed to install Python deps from `{req_file}`.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (truncated)"
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 error_msg = f"❌ Unexpected error installing Python deps: {e}"
                 logger.error(error_msg, exc_info=True); bot.reply_to(message, error_msg); return

        if pkg_json:
            logger.info(f"📦 package.json found, npm install in: {temp_dir}")
            bot.reply_to(message, f"⚠️ Installing Node deps from `{pkg_json}`...")
            try:
                command = ['npm', 'install']
                result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=temp_dir, encoding='utf-8', errors='ignore')
                logger.info(f"✅ npm install OK.")
                bot.reply_to(message, f"✅ Node deps from `{pkg_json}` installed.")
            except FileNotFoundError:
                bot.reply_to(message, "❌ 'npm' not found. Cannot install Node deps."); return
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ Failed to install Node deps from `{pkg_json}`.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (truncated)"
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 error_msg = f"❌ Unexpected error installing Node deps: {e}"
                 logger.error(error_msg, exc_info=True); bot.reply_to(message, error_msg); return

        main_script_name = None; file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']; preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        for p in preferred_py:
            if p in py_files: main_script_name = p; file_type = 'py'; break
        if not main_script_name:
             for p in preferred_js:
                 if p in js_files: main_script_name = p; file_type = 'js'; break
        if not main_script_name:
            if py_files: main_script_name = py_files[0]; file_type = 'py'
            elif js_files: main_script_name = js_files[0]; file_type = 'js'
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` script found in archive!"); return

        logger.info(f"📁 Moving extracted files from {temp_dir} to {user_folder}")
        moved_count = 0
        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path): shutil.rmtree(dest_path)
            elif os.path.exists(dest_path): os.remove(dest_path)
            shutil.move(src_path, dest_path); moved_count +=1
        logger.info(f"✅ Moved {moved_count} items to {user_folder}")

        save_user_file(user_id, main_script_name, file_type)
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Files extracted. Starting main script: `{main_script_name}`...", parse_mode='Markdown')

        if file_type == 'py':
             threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
             threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()

    except zipfile.BadZipFile as e:
        logger.error(f"❌ Bad zip file from {user_id}: {e}")
        bot.reply_to(message, f"❌ Error: Invalid/corrupted ZIP. {e}")
    except Exception as e:
        logger.error(f"❌ Error processing zip for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir); logger.info(f"🧹 Cleaned temp dir: {temp_dir}")
            except Exception as e: logger.error(f"❌ Failed to clean temp dir {temp_dir}: {e}", exc_info=True)

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Error processing JS file {file_name}: {e}", exc_info=True)
        bot.reply_to(message, f"⚠️ Error processing JS file: {str(e)}")

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Error processing Python file {file_name}: {e}", exc_info=True)
        bot.reply_to(message, f"⚠️ Error processing Python file: {str(e)}")

def create_bot_clone(user_id, token, bot_username):
    try:
        clone_dir = os.path.join(BASE_DIR, f'clone_{user_id}')
        os.makedirs(clone_dir, exist_ok=True)
        current_file = __file__
        clone_file = os.path.join(clone_dir, 'bot.py')
        with open(current_file, 'r', encoding='utf-8') as f:
            script_content = f.read()
        script_content = script_content.replace(BOT_TOKEN, token)
        script_content = script_content.replace(str(OWNER_ID), str(user_id))
        script_content = script_content.replace(str(ADMIN_ID), str(user_id))
        with open(clone_file, 'w', encoding='utf-8') as f:
            f.write(script_content)
        clone_process = subprocess.Popen(
            [sys.executable, clone_file],
            cwd=clone_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE
        )
        save_clone_info(user_id, bot_username, token)
        logger.info(f"✅ Bot clone created for user {user_id}, bot @{bot_username}")
        return True
    except Exception as e:
        logger.error(f"❌ Error creating bot clone: {e}")
        return False

# ===== LOGIC FUNCTIONS =====
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_last_name = message.from_user.last_name or ""
    user_username = message.from_user.username

    if is_user_banned(user_id):
        bot.send_message(chat_id, "❌ You are banned from using this bot.")
        return

    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, sub_markup = create_subscription_check_message(not_joined)
        bot.send_message(chat_id, subscription_message, reply_markup=sub_markup, parse_mode='Markdown')
        return

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked by admin. Try later.")
        return

    user_bio = "Could not fetch bio"
    try: user_bio = bot.get_chat(user_id).bio or "No bio"
    except Exception: pass

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = (f"👋 **New User Alert!**\n\n"
                                  f"👤 **Name:** {user_name} {user_last_name}\n"
                                  f"📱 **Username:** @{user_username or 'N/A'}\n"
                                  f"🆔 **User ID:** `{user_id}`\n"
                                  f"📝 **Bio:** {user_bio}")
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
        except Exception as e: logger.error(f"❌ Failed to notify owner: {e}")

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "⚜️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "💎 Premium"
            days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⌛ Expires in: {days_left} days"
        else:
            user_status = "🆓 Free User"
            remove_subscription_db(user_id)
    else:
        user_status = "🆓 Free User"

    full_name = user_name
    if user_last_name:
        full_name += f" {user_last_name}"

    welcome_msg_text = (f"┌──────────────────────┐\n"
                        f"│👋 Welcome, {full_name}!\n"
                        f"├──────────────────────┤\n"
                        f"│👤 Your User ID: `{user_id}`\n"
                        f"│🔰 Your Status: {user_status}{expiry_info}\n"
                        f"│📁 Files Uploaded: {current_files} / {limit_str}\n\n"
                        f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                        f"   Upload single scripts or `.zip` archives.\n\n"
                        f"👇 Use buttons or type commands.")
    
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    try:
        bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Error sending welcome to {user_id}: {e}", exc_info=True)

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
    bot.reply_to(message, "📢 Visit our Updates Channel:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, sub_markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=sub_markup, parse_mode='Markdown')
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked by admin, cannot accept files.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached. Delete files first.")
        return
    bot.reply_to(message, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, "📂 Your files:\n\n(No files uploaded yet)")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🏢 Active" if is_running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    bot.reply_to(message, "📂 Your files:\nClick to manage.", reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time_ping = time.time()
    wait_msg = bot.reply_to(message, "⏱️ Testing speed...")
    try:
        response_time = round((time.time() - start_time_ping) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID: user_level = "👑 Owner"
        elif user_id in admin_ids: user_level = "⚜️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "💎 Premium"
        else: user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n"
                     f"⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"👤 Your Level: {user_level}")
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"❌ Error during speed test: {e}", exc_info=True)
        bot.edit_message_text("❌ Error during speed test.", chat_id, wait_msg.message_id)
        
def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "📞 Click to Contact Owner:", reply_markup=markup)

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files_records = sum(len(files) for files in user_files.values())
    running_bots_count = 0
    for script_key_iter, script_info_iter in list(bot_scripts.items()):
        s_owner_id, _ = script_key_iter.split('_', 1)
        if is_bot_running(int(s_owner_id), script_info_iter['file_name']):
            running_bots_count += 1

    stats_msg = (f"📊 Bot Live Statistics:\n\n"
                 f"👥 Total Users: {total_users}\n"
                 f"🚫 Banned Users: {len(banned_users)}\n"
                 f"📂 Total File Records: {total_files_records}\n"
                 f"🏢 Total Active Bots: {running_bots_count}\n"
                 f"🤖 Clone Bots: {len(user_clones)}")
    bot.reply_to(message, stats_msg)

def _logic_subscriptions(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    markup = create_subscription_panel()
    bot.reply_to(message, "💳 **Subscription Management**\n\nManage user subscriptions here.", reply_markup=markup, parse_mode='Markdown')

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    msg = bot.reply_to(message, "📢 Send message to broadcast to all active users.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    lock_emoji = "🔒" if bot_locked else "✅"
    bot.reply_to(message, f"{lock_emoji} Bot has been {status}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "👑 Admin Panel\nManage admins.", reply_markup=create_admin_panel())

def _logic_run_all_scripts(message):
    admin_user_id = message.from_user.id
    admin_chat_id = message.chat.id

    if admin_user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return

    bot.reply_to(message, "🏢 Starting process to Run All Scripts. This may take a while...")
    logger.info(f"👑 Admin {admin_user_id} initiated 'run all scripts' from chat {admin_chat_id}.")

    started_count = 0; attempted_users = 0; skipped_files = 0; error_files_details = []
    all_user_files_snapshot = dict(user_files)

    for target_user_id, files_for_user in all_user_files_snapshot.items():
        if not files_for_user: continue
        attempted_users += 1
        user_folder = get_user_folder(target_user_id)

        for file_name, file_type in files_for_user:
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    try:
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(file_path, target_user_id, user_folder, file_name, message)).start()
                            started_count += 1
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(file_path, target_user_id, user_folder, file_name, message)).start()
                            started_count += 1
                        else:
                            skipped_files += 1
                        time.sleep(0.7)
                    except Exception as e:
                        logger.error(f"❌ Error queueing start for '{file_name}': {e}")
                        skipped_files += 1
                else:
                    skipped_files += 1

    summary_msg = (f"🏢 All Users' Scripts - Processing Complete:\n\n"
                   f"✅ Attempted to start: {started_count} scripts.\n"
                   f"👥 Users processed: {attempted_users}.\n")
    if skipped_files > 0:
        summary_msg += f"⚠️ Skipped/Error files: {skipped_files}\n"

    bot.reply_to(message, summary_msg, parse_mode='Markdown')

def _logic_clone_bot(message):
    user_id = message.from_user.id
    clone_text = f"🤖 Clone Bot Service\n\n"
    clone_text += f"📊 Total Clones: {len(user_clones)}\n\n"
    clone_text += f"🎯 Features in your clone:\n"
    clone_text += f"• 📁 Unlimited file hosting\n"
    clone_text += f"• 🛡️ Security scanning\n"
    clone_text += f"• 💾 File hosting\n"
    clone_text += f"• ⚡ Auto-restart\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("🚀 Clone", callback_data="clone_create"),
        types.InlineKeyboardButton("🗑️ Remove", callback_data="clone_remove")
    )
    bot.reply_to(message, clone_text, reply_markup=markup, parse_mode="Markdown")

def _logic_manual_install(message):
    manual_install_module_init(message)

def _logic_user_management(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "👥 User Management\nManage users, set limits, ban/unban.", reply_markup=create_user_management_menu())

def _logic_admin_settings(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "⚙️ Admin Settings\nSystem information and management.", reply_markup=create_admin_settings_menu())

def _logic_manage_mandatory_channels(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "📢 Manage Mandatory Channels\nUse the buttons below:", reply_markup=create_mandatory_channels_menu())

def _logic_admin_install(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    msg = bot.reply_to(message, "🛠️ Admin Module Installation\nSend user ID and module name (e.g., `12345678 requests`)\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_admin_install)

def process_admin_install(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Installation cancelled.")
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: `user_id module_name`\nExample: `12345678 requests`")
            return
        user_id = int(parts[0])
        module_name = ' '.join(parts[1:])
        if module_name.lower().startswith('npm:'):
            module_name = module_name[4:].strip()
            user_folder = get_user_folder(user_id)
            success, log = attempt_install_npm(module_name, user_folder, message, manual_request=True)
        else:
            success, log = attempt_install_pip(module_name, message, manual_request=True)
        if success:
            try:
                bot.send_message(user_id, f"📦 Admin installed module `{module_name}` for you.")
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error in admin install: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ===== MANUAL INSTALL FLOW =====
def manual_install_module_init(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked by admin. Try later.")
        return
    msg = bot.reply_to(message, "📦 Send module name to install (e.g., `requests` or `pillow`)\nFor Node.js: `npm:module_name`\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_manual_install_module)

def process_manual_install_module(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Installation cancelled.")
        return
    module_name = message.text.strip()
    if module_name.lower().startswith('npm:'):
        module_name = module_name[4:].strip()
        user_folder = get_user_folder(user_id)
        success, log = attempt_install_npm(module_name, user_folder, message, manual_request=True)
    else:
        success, log = attempt_install_pip(module_name, message, manual_request=True)

# ===== SUBSCRIPTION CHECK ADAPTER =====
def check_subscription_and_continue(message=None, call=None):
    try:
        if message is not None: user_id = message.from_user.id
        elif call is not None: user_id = call.from_user.id
        else: return True
    except Exception:
        return True
    if is_user_banned(user_id):
        if message is not None: bot.reply_to(message, "❌ You are banned from using this bot.")
        else:
            try: bot.answer_callback_query(call.id, "❌ You are banned.", show_alert=True)
            except Exception: pass
        return False
    if user_id in admin_ids: return True
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if is_subscribed: return True
    subscription_message, sub_markup = create_subscription_check_message(not_joined)
    if message is not None:
        bot.reply_to(message, subscription_message, reply_markup=sub_markup, parse_mode='Markdown')
    else:
        try: bot.answer_callback_query(call.id)
        except Exception: pass
        try: bot.send_message(call.message.chat.id, subscription_message, reply_markup=sub_markup, parse_mode='Markdown')
        except Exception: pass
    return False

# ===== STYLISH TEXT HELPER =====
def stylish_text(text: str) -> str:
    text = re.sub(r'</?code>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text

# ===== PENDING UPLOAD =====
def add_pending_upload(user_id, file_id, file_name, file_type, file_size, user_name, user_username, extra_info=""):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            timestamp = datetime.now().isoformat()
            c.execute('''INSERT INTO pending_uploads 
                         (user_id, file_id, file_name, file_type, file_size, user_name, user_username, timestamp, extra_info)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, file_id, file_name, file_type, file_size, user_name, user_username, timestamp, extra_info))
            conn.commit()
            return c.lastrowid
        except Exception as e:
            logger.error(f"Error adding pending upload: {e}")
            return None
        finally:
            conn.close()

def get_pending_upload(upload_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT id, user_id, file_id, file_name, file_type, file_size, user_name, user_username, extra_info FROM pending_uploads WHERE id = ?', (upload_id,))
            row = c.fetchone()
            if row:
                return {'id': row[0], 'user_id': row[1], 'file_id': row[2], 'file_name': row[3],
                        'file_type': row[4], 'file_size': row[5], 'user_name': row[6], 'user_username': row[7], 'extra_info': row[8]}
            return None
        except Exception as e:
            logger.error(f"Error getting pending upload: {e}")
            return None
        finally:
            conn.close()

def delete_pending_upload(upload_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM pending_uploads WHERE id = ?', (upload_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting pending upload: {e}")
            return False
        finally:
            conn.close()

def process_approved_file(upload_id, admin_chat_id, user_message_obj=None):
    pending = get_pending_upload(upload_id)
    if not pending:
        bot.send_message(admin_chat_id, "❌ Pending upload not found.")
        return False
    user_id = pending['user_id']
    file_id = pending['file_id']
    file_name = pending['file_name']
    file_ext = os.path.splitext(file_name)[1].lower()
    file_type = pending['file_type']
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        bot.send_message(admin_chat_id, f"⚠️ User limit reached. Cannot approve.")
        delete_pending_upload(upload_id)
        return False
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        if file_ext == '.zip':
            temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
            zip_path = os.path.join(temp_dir, file_name)
            with open(zip_path, 'wb') as f:
                f.write(downloaded)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(temp_dir)
            extracted = os.listdir(temp_dir)
            py_files = [f for f in extracted if f.endswith('.py')]
            js_files = [f for f in extracted if f.endswith('.js')]
            req_file = 'requirements.txt' if 'requirements.txt' in extracted else None
            pkg_json = 'package.json' if 'package.json' in extracted else None
            if req_file:
                try:
                    subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', os.path.join(temp_dir, req_file)], check=True, capture_output=True)
                except Exception as e:
                    bot.send_message(admin_chat_id, f"❌ Python deps failed: {e}")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    delete_pending_upload(upload_id)
                    return False
            if pkg_json:
                try:
                    subprocess.run(['npm', 'install'], cwd=temp_dir, check=True, capture_output=True)
                except Exception as e:
                    bot.send_message(admin_chat_id, f"❌ Node deps failed: {e}")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    delete_pending_upload(upload_id)
                    return False
            main_script = None
            for p in ['main.py', 'bot.py', 'app.py']:
                if p in py_files:
                    main_script = p
                    file_type = 'py'
                    break
            if not main_script:
                for p in ['index.js', 'main.js', 'bot.js', 'app.js']:
                    if p in js_files:
                        main_script = p
                        file_type = 'js'
                        break
            if not main_script and py_files:
                main_script = py_files[0]
                file_type = 'py'
            elif not main_script and js_files:
                main_script = js_files[0]
                file_type = 'js'
            if not main_script:
                bot.send_message(admin_chat_id, "❌ No .py or .js script found in zip.")
                shutil.rmtree(temp_dir, ignore_errors=True)
                delete_pending_upload(upload_id)
                return False
            for item in os.listdir(temp_dir):
                src = os.path.join(temp_dir, item)
                dst = os.path.join(user_folder, item)
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                elif os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)
            shutil.rmtree(temp_dir, ignore_errors=True)
            save_user_file(user_id, main_script, file_type)
            script_path = os.path.join(user_folder, main_script)
            if file_type == 'py':
                threading.Thread(target=run_script, args=(script_path, user_id, user_folder, main_script, user_message_obj)).start()
            else:
                threading.Thread(target=run_js_script, args=(script_path, user_id, user_folder, main_script, user_message_obj)).start()
            bot.send_message(admin_chat_id, f"✅ Approved and started: {main_script}")
            return True
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded)
            save_user_file(user_id, file_name, file_type)
            if file_type == 'py':
                threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, user_message_obj)).start()
            else:
                threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, user_message_obj)).start()
            bot.send_message(admin_chat_id, f"✅ Approved and started: {file_name}")
            return True
    except Exception as e:
        logger.error(f"Error in process_approved_file: {e}", exc_info=True)
        bot.send_message(admin_chat_id, f"❌ Error: {e}")
        return False
    finally:
        delete_pending_upload(upload_id)

# ===== CALLBACK HANDLERS =====
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_upload_') or call.data.startswith('reject_upload_'))
def handle_approval_callback(call):
    if not check_subscription_and_continue(None, call): return
    admin_id = call.from_user.id
    if admin_id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Only admins can approve/reject.", show_alert=True)
        return
    upload_id = int(call.data.split('_')[-1])
    pending = get_pending_upload(upload_id)
    if not pending:
        bot.answer_callback_query(call.id, "⚠️ Upload no longer exists.", show_alert=True)
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except: pass
        return
    user_id = pending['user_id']
    file_name = pending['file_name']
    if call.data.startswith('approve_upload_'):
        bot.answer_callback_query(call.id, "✅ Approving and starting...")
        success = process_approved_file(upload_id, admin_chat_id=call.message.chat.id, user_message_obj=call.message)
        if success:
            try: bot.send_message(user_id, f"✅ Your file {file_name} has been approved and is now running.")
            except Exception as e: logger.error(f"Could not notify user {user_id}: {e}")
            try:
                bot.edit_message_caption(caption=(call.message.caption or "") + "\n\n✅ APPROVED",
                    chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except: pass
        else:
            bot.send_message(call.message.chat.id, f"❌ Failed to process file for user {user_id}.")
    else:
        bot.answer_callback_query(call.id, "❌ Rejected.")
        delete_pending_upload(upload_id)
        try: bot.send_message(user_id, f"❌ Your file {file_name} was rejected by admin.")
        except Exception as e: logger.error(f"Could not notify user {user_id}: {e}")
        try:
            bot.edit_message_caption(caption=(call.message.caption or "") + "\n\n❌ REJECTED",
                chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except: pass

# ===== GITHUB DEPLOY =====
def parse_github_url(url):
    url = re.sub(r'\.git$', '', url)
    if 'github.com' not in url:
        raise ValueError("Not a valid GitHub URL")
    parts = url.split('github.com/')[-1].split('/')
    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL format")
    owner = parts[0]
    repo = parts[1]
    branch = 'main'
    if len(parts) >= 4 and parts[2] == 'tree':
        branch = parts[3]
    return owner, repo, branch

def download_github_repo(owner, repo, branch, token=None):
    url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'
    resp = requests.get(url, headers=headers, stream=True)
    if resp.status_code == 404:
        raise Exception("Repository or branch not found")
    if resp.status_code == 401:
        raise Exception("Invalid or missing access token (private repo)")
    if resp.status_code != 200:
        raise Exception(f"GitHub API error: {resp.status_code}")
    content_length = resp.headers.get('content-length')
    if content_length and int(content_length) > 20 * 1024 * 1024:
        raise Exception("Repository ZIP exceeds 20MB limit")
    return resp.content

def _logic_github_deploy(message):
    if not check_subscription_and_continue(message):
        return
    user_id = message.from_user.id
    if get_user_file_count(user_id) >= get_user_file_limit(user_id):
        bot.reply_to(message, "⚠️ You have reached your file limit.")
        return
    github_data[user_id] = {'step': 'url'}
    bot.reply_to(message, "📦 Send me the GitHub repository URL.\nExample: https://github.com/user/repo\n\nSend /cancel to abort.")

@bot.message_handler(func=lambda m: m.from_user.id in github_data and github_data[m.from_user.id]['step'] == 'url')
def github_get_url(message):
    if not check_subscription_and_continue(message):
        return
    user_id = message.from_user.id
    if message.text and message.text.lower() == '/cancel':
        del github_data[user_id]
        bot.reply_to(message, "❌ GitHub deploy cancelled.")
        return
    url = message.text.strip()
    try:
        owner, repo, branch = parse_github_url(url)
    except Exception as e:
        bot.reply_to(message, f"❌ Invalid GitHub URL: {e}")
        return
    github_data[user_id]['url'] = url
    github_data[user_id]['owner'] = owner
    github_data[user_id]['repo'] = repo
    github_data[user_id]['branch'] = branch
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔒 Private", callback_data=f"github_private_{user_id}"),
        types.InlineKeyboardButton("🌐 Public", callback_data=f"github_public_{user_id}")
    )
    bot.reply_to(message, "Is this a private repository?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('github_private_') or call.data.startswith('github_public_'))
def github_repo_type(call):
    user_id = int(call.data.split('_')[-1])
    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "Not for you", show_alert=True)
        return
    if user_id not in github_data:
        bot.answer_callback_query(call.id, "Session expired", show_alert=True)
        return
    if call.data.startswith('github_private_'):
        github_data[user_id]['step'] = 'token'
        bot.edit_message_text("🔒 Send your GitHub personal access token (with `repo` scope).\nSend /cancel to abort.",
                              call.message.chat.id, call.message.message_id)
    else:
        github_data[user_id]['token'] = None
        _process_github_download(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.from_user.id in github_data and github_data[m.from_user.id].get('step') == 'token')
def github_get_token(message):
    if not check_subscription_and_continue(message):
        return
    user_id = message.from_user.id
    if message.text and message.text.lower() == '/cancel':
        del github_data[user_id]
        bot.reply_to(message, "❌ GitHub deploy cancelled.")
        return
    token = message.text.strip()
    github_data[user_id]['token'] = token
    _process_github_download(message.chat.id, user_id)

def _process_github_download(chat_id, user_id):
    data = github_data.get(user_id)
    if not data:
        bot.send_message(chat_id, "Session expired. Start again.")
        return
    url = data['url']
    owner = data['owner']
    repo = data['repo']
    branch = data['branch']
    token = data.get('token')
    
    msg = bot.send_message(chat_id, "📥 Downloading repo...")
    try:
        zip_content = download_github_repo(owner, repo, branch, token)
        bot.edit_message_text("✅ Downloaded successfully. Submitting for admin approval...", chat_id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Download failed: {e}", chat_id, msg.message_id)
        del github_data[user_id]
        return
    
    file_name = f"{repo}_{branch}.zip"
    try:
        sent = bot.send_document(chat_id, io.BytesIO(zip_content), visible_file_name=file_name, caption="🔔 Submitting for admin approval...")
        file_id = sent.document.file_id
        file_size = sent.document.file_size
        user_name = bot.get_chat(user_id).first_name
        user_username = bot.get_chat(user_id).username or "No username"
        extra_info = f"GitHub URL: {url}\nToken: {token if token else 'Not required (public repo)'}"
        upload_id = add_pending_upload(
            user_id=user_id, file_id=file_id, file_name=file_name, file_type='zip',
            file_size=file_size, user_name=user_name, user_username=user_username, extra_info=extra_info
        )
        if not upload_id:
            bot.send_message(chat_id, "❌ Internal error, try again later.")
            return
        for admin_id in admin_ids:
            try:
                caption = (f"📥 New GitHub repo requires approval\n"
                           f"👤 User: {user_name} (@{user_username})\n"
                           f"🆔 User ID: {user_id}\n"
                           f"📦 Repo URL: {url}\n"
                           f"📄 File: {file_name}\n"
                           f"📏 Size: {file_size // 1024} KB\n"
                           f"🆔 Upload ID: {upload_id}")
                sent_admin = bot.send_document(admin_id, file_id, caption=caption)
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_upload_{upload_id}"),
                    types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_upload_{upload_id}")
                )
                bot.edit_message_reply_markup(admin_id, sent_admin.message_id, reply_markup=markup)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        bot.send_message(chat_id, f"✅ GitHub repository submitted for admin approval.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Failed to submit: {e}")
    finally:
        del github_data[user_id]

# ===== RECOMMENDED INSTALL =====
def _logic_recommended_install(message):
    if not check_subscription_and_continue(message):
        return
    text = "📦 Popular Packages\n\nSend Me The Package Name.\n\nExample:\n• Requests\n• Numpy\n• Flask \n• Pillow \n• Git Clone"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Install Recommended", callback_data="install_recommended"))
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_install"))
    bot.reply_to(message, text, reply_markup=markup)
    bot.register_next_step_handler(message, process_manual_package_install)

def process_manual_package_install(message):
    if not check_subscription_and_continue(message):
        return
    text = message.text.strip()
    if text.lower() == '/cancel':
        bot.reply_to(message, "Installation cancelled.")
    else:
        bot.reply_to(message, f"📦 Installing {text}...")
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', text], capture_output=True, text=True)
            if result.returncode == 0:
                bot.send_message(message.chat.id, f"✅ Successfully installed {text}")
            else:
                error_msg = result.stderr[:500]
                bot.send_message(message.chat.id, f"❌ Failed to install {text}\nError: {error_msg}")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "install_recommended")
def install_recommended_callback(call):
    if not check_subscription_and_continue(None, call):
        return
    bot.answer_callback_query(call.id, "Installing recommended packages...")
    recommended = ["pip", "setuptools", "wheel", "requests", "numpy", "pandas", "flask", "aiohttp", "pyrogram", "python-dotenv", "beautifulsoup4", "lxml", "pillow", "matplotlib", "scipy", "scikit-learn", "pytest"]
    bot.send_message(call.message.chat.id, f"🚀 Installing {len(recommended)} packages... Please wait.")
    success = 0
    failed = 0
    for pkg in recommended:
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg], capture_output=True, text=True)
            if result.returncode == 0:
                success += 1
            else:
                failed += 1
        except:
            failed += 1
        time.sleep(0.5)
    bot.send_message(call.message.chat.id, f"✅ Done.\n✅ Success: {success}\n❌ Failed: {failed}")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_install")
def cancel_install_callback(call):
    bot.answer_callback_query(call.id, "Cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ===== AI ASSISTANT =====
def call_sambanova_sync(message: str, model_name: str) -> str:
    headers = {
        'Authorization': f'Bearer {SAMBA_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': 'You are a helpful AI assistant.'},
            {'role': 'user', 'content': message}
        ],
        'temperature': 0.7,
        'max_tokens': 500,
        'top_p': 0.95
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(SAMBA_URL, headers=headers, json=payload, timeout=30)
            if response.status_code == 429:
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
                continue
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return f"⚠️ API error {response.status_code}: {response.text[:200]}"
        except Exception as e:
            if attempt == max_retries - 1:
                return f"❌ Network error: {str(e)}"
            time.sleep(2 ** attempt)
    return "❌ Max retries exceeded."

def auto_fix_modules_from_text(user_id: int, text: str, chat_id: int):
    missing_modules = set()
    matches = re.findall(r"ModuleNotFoundError: No module named '(.+?)'", text)
    matches.extend(re.findall(r"ImportError: No module named '(.+?)'", text))
    matches.extend(re.findall(r"No module named '(.+?)'", text))
    for mod in matches:
        mod = mod.strip().strip("'\"")
        if mod and not mod.startswith('.') and mod not in ['sys', 'os', 're', 'time', 'json', 'datetime']:
            missing_modules.add(mod)
    if not missing_modules:
        bot.send_message(chat_id, "ℹ️ No missing modules found. Ask me anything!")
        return
    bot.send_message(chat_id, f"🔍 Detected: {', '.join(missing_modules)}\n\n🔧 Installing...")
    installed = 0; failed = 0; results = []
    for mod in missing_modules:
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', mod], capture_output=True, text=True)
            if result.returncode == 0:
                installed += 1
                results.append(f"✅ {mod}")
            else:
                failed += 1
                results.append(f"❌ {mod}")
        except Exception as e:
            failed += 1
            results.append(f"❌ {mod} - {str(e)}")
        time.sleep(0.5)
    summary = f"🔧 Auto-fix completed:\n" + "\n".join(results) + f"\n\n✅ Installed: {installed}\n❌ Failed: {failed}"
    bot.send_message(chat_id, summary)

def get_bot_help_text() -> str:
    return "🤖 AI Assistant Help\n\nJust send me any message and I'll respond using AI!"

def handle_deepseek_chat(message):
    if not check_subscription_and_continue(message):
        return
    if not message.text:
        bot.reply_to(message, "Please send a text message.")
        bot.register_next_step_handler(message, handle_deepseek_chat)
        return
    user_text = message.text.strip()
    if user_text.lower() == '/cancel':
        bot.reply_to(message, "AI Agent mode cancelled.")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    error_patterns = ['ModuleNotFoundError', 'ImportError', 'No module named', 'module not found']
    if any(pattern in user_text for pattern in error_patterns):
        bot.send_chat_action(chat_id, 'typing')
        auto_fix_modules_from_text(user_id, user_text, chat_id)
        bot.register_next_step_handler(message, handle_deepseek_chat)
        return
    
    bot.send_chat_action(chat_id, 'typing')
    thinking_msg = bot.reply_to(message, "🤔 Thinking...")
    model_full = AVAILABLE_MODELS[global_model]
    response = call_sambanova_sync(user_text, model_full)
    if len(response) > 4000:
        response = response[:4000] + "... (truncated)"
    try:
        bot.edit_message_text(response, chat_id, thinking_msg.message_id)
    except Exception as e:
        logger.error(f"AI response edit failed: {e}")
    bot.register_next_step_handler(message, handle_deepseek_chat)

def _logic_ai_assistant(message):
    if not check_subscription_and_continue(message):
        return
    welcome_text = "🤖 AI Agent Online\n\nAsk me anything! Send your message."
    bot.reply_to(message, welcome_text, parse_mode="Markdown")
    bot.register_next_step_handler(message, handle_deepseek_chat)

# ===== AI FIX =====
def ai_fix_script(owner_id, file_name, chat_id, message_id):
    folder = get_user_folder(owner_id)
    log_path = os.path.join(folder, f"{os.path.splitext(file_name)[0]}.log")
    if not os.path.exists(log_path):
        bot.send_message(chat_id, f"No log file found for {file_name}.")
        return
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        log_content = f.read()
    missing_modules = set()
    matches = re.findall(r"ModuleNotFoundError: No module named '(.+?)'", log_content)
    matches.extend(re.findall(r"ImportError: No module named '(.+?)'", log_content))
    for mod in matches:
        mod = mod.strip().strip("'\"")
        missing_modules.add(mod)
    if not missing_modules:
        bot.send_message(chat_id, f"✅ No missing modules in {file_name}.")
        return
    installed = 0; failed = 0; results = []
    for mod in missing_modules:
        bot.send_message(chat_id, f"📦 Installing {mod}...")
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', mod], capture_output=True, text=True)
            if result.returncode == 0:
                installed += 1; results.append(f"✅ {mod}")
            else:
                failed += 1; results.append(f"❌ {mod}")
        except Exception as e:
            failed += 1; results.append(f"❌ {mod} - {str(e)}")
        time.sleep(0.5)
    summary = f"🔧 AI Fix completed for {file_name}:\n" + "\n".join(results) + f"\n\n✅ Installed: {installed}\n❌ Failed: {failed}"
    bot.send_message(chat_id, summary)

@bot.callback_query_handler(func=lambda call: call.data.startswith('aifix_'))
def ai_fix_callback(call):
    if not check_subscription_and_continue(None, call):
        return
    try:
        _, owner_id_str, file_name = call.data.split('_', 2)
        owner_id = int(owner_id_str)
        if call.from_user.id != owner_id and call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "AI Fix running...")
        threading.Thread(target=ai_fix_script, args=(owner_id, file_name, call.message.chat.id, call.message.message_id)).start()
    except Exception as e:
        logger.error(f"AI Fix error: {e}")
        bot.answer_callback_query(call.id, f"Error: {e}", show_alert=True)

# ===== MODEL SELECTION =====
def create_model_selection_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    for model_key in AVAILABLE_MODELS:
        markup.add(types.InlineKeyboardButton(f"{model_key.upper()}", callback_data=f"setmodel_{model_key}"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
    return markup

@bot.message_handler(commands=['model'])
def cmd_show_model(message):
    if not check_subscription_and_continue(message): return
    bot.reply_to(message, f"🧠 Current AI model: *{global_model}*", parse_mode="Markdown")

@bot.message_handler(commands=['setmodel'])
def cmd_set_model(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "⛔ Only admins can change the AI model.")
        return
    markup = create_model_selection_markup()
    bot.reply_to(message, "Select a new AI model:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setmodel_'))
def set_model_callback(call):
    user_id = call.from_user.id
    if user_id not in admin_ids:
        bot.answer_callback_query(call.id, "Not authorized.", show_alert=True)
        return
    model_key = call.data.split('_')[1]
    if model_key in AVAILABLE_MODELS:
        global global_model
        global_model = model_key
        bot.answer_callback_query(call.id, f"✅ Model changed to {model_key.upper()}")
        bot.edit_message_text(f"✅ AI model changed to *{model_key}*", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Invalid model.", show_alert=True)

# ===== BAN/UNBAN =====
@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    if user_id not in admin_ids and user_id != OWNER_ID:
        bot.reply_to(message, "⚠️ Admin only command.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /ban user_id")
        return
    try:
        target_id = int(parts[1])
    except:
        bot.reply_to(message, "Invalid user ID.")
        return
    if target_id in admin_ids or target_id == OWNER_ID:
        bot.reply_to(message, "❌ Cannot ban an admin or owner.")
        return
    if ban_user_db(target_id, 'Banned via /ban command', message.from_user.id):
        bot.reply_to(message, f"✅ User {target_id} banned.")
        try: bot.send_message(target_id, "🚫 You have been banned.")
        except: pass
    else:
        bot.reply_to(message, f"❌ Failed to ban user {target_id}.")

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    if user_id not in admin_ids and user_id != OWNER_ID:
        bot.reply_to(message, "⚠️ Admin only command.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /unban user_id")
        return
    try:
        target_id = int(parts[1])
    except:
        bot.reply_to(message, "Invalid user ID.")
        return
    if unban_user_db(target_id):
        bot.reply_to(message, f"✅ User {target_id} unbanned.")
        try: bot.send_message(target_id, "✅ You have been unbanned.")
        except: pass
    else:
        bot.reply_to(message, f"❌ User {target_id} was not banned.")

@bot.message_handler(commands=['stop'])
def cmd_stop_all(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    if user_id not in admin_ids and user_id != OWNER_ID:
        bot.reply_to(message, "⚠️ Admin only command.")
        return
    running = list(bot_scripts.items())
    if not running:
        bot.reply_to(message, "ℹ️ No scripts running.")
        return
    stopped = 0
    for key, info in running:
        try:
            kill_process_tree(info)
            stopped += 1
        except Exception as e:
            logger.error(f"Failed to stop {key}: {e}")
    bot_scripts.clear()
    bot.reply_to(message, f"✅ Stopped {stopped} running script(s).")

def _logic_stop_my_scripts(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    files = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "📂 You have no uploaded files to stop.")
        return
    stopped = 0
    for file_name, ftype in files:
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
            stopped += 1
            time.sleep(0.2)
    bot.reply_to(message, f"⏹ Stopped {stopped} of your script(s).")

def _logic_restart_my_scripts(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    files = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "📂 You have no uploaded files to restart.")
        return
    bot.reply_to(message, "🔄 Restarting all your scripts...")
    stopped = 0; started = 0
    for file_name, ftype in files:
        script_key = f"{user_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
            stopped += 1
            time.sleep(0.3)
    for file_name, ftype in files:
        folder = get_user_folder(user_id)
        script_path = os.path.join(folder, file_name)
        if not os.path.exists(script_path):
            continue
        if ftype == 'py':
            threading.Thread(target=run_script, args=(script_path, user_id, folder, file_name, message)).start()
        elif ftype == 'js':
            threading.Thread(target=run_js_script, args=(script_path, user_id, folder, file_name, message)).start()
        else:
            continue
        started += 1
        time.sleep(0.5)
    bot.send_message(message.chat.id, f"✅ Restarted {started} of your script(s). (Stopped {stopped} before restart)")

# ===== AUTO-RECOVERY =====
class _RecoveryMsg:
    def __init__(self, chat_id):
        self.chat = type('Chat', (), {'id': chat_id})()
        self.message_id = None

def auto_recovery_worker():
    while True:
        time.sleep(30)
        try:
            current_time = time.time()
            for script_key, info in list(bot_scripts.items()):
                try:
                    proc = info.get('process')
                    if not proc or not hasattr(proc, 'pid'):
                        continue
                    pid = proc.pid
                    if not pid:
                        continue
                    try:
                        p = psutil.Process(pid)
                        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                            raise psutil.NoSuchProcess(pid)
                    except psutil.NoSuchProcess:
                        last = auto_recovery_last_restart.get(script_key, 0)
                        if current_time - last < 60:
                            continue
                        auto_recovery_last_restart[script_key] = current_time
                        owner_id = info.get('script_owner_id')
                        file_name = info.get('file_name')
                        chat_id = info.get('chat_id')
                        file_type = info.get('type')
                        user_folder = info.get('user_folder')
                        if not owner_id or not file_name:
                            continue
                        logger.info(f"Auto-recovery: Restarting {script_key}")
                        if chat_id:
                            try: bot.send_message(chat_id, f"🔄 Auto-Recovery: {file_name} crashed and is being restarted...")
                            except: pass
                        if 'log_file' in info and hasattr(info['log_file'], 'close') and not info['log_file'].closed:
                            try: info['log_file'].close()
                            except: pass
                        del bot_scripts[script_key]
                        script_path = os.path.join(user_folder, file_name)
                        if not os.path.exists(script_path):
                            continue
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(script_path, owner_id, user_folder, file_name, _RecoveryMsg(chat_id))).start()
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(script_path, owner_id, user_folder, file_name, _RecoveryMsg(chat_id))).start()
                except Exception as e:
                    logger.error(f"Auto-recovery error for {script_key}: {e}")
        except Exception as e:
            logger.error(f"Auto-recovery worker error: {e}")

# ===== RESTART COMMAND =====
@bot.message_handler(commands=['restart'])
def cmd_restart_all(message):
    if not check_subscription_and_continue(message): return
    user_id = message.from_user.id
    if user_id in admin_ids or user_id == OWNER_ID:
        running_scripts = []
        for key, info in list(bot_scripts.items()):
            try:
                parts = key.split('_', 1)
                if len(parts) == 2:
                    owner_id = int(parts[0])
                    file_name = parts[1]
                    ftype = None
                    if owner_id in user_files:
                        for fname, ft in user_files[owner_id]:
                            if fname == file_name:
                                ftype = ft
                                break
                    if ftype:
                        running_scripts.append((owner_id, file_name, ftype))
            except Exception as e:
                logger.error(f"Error capturing script {key}: {e}")
        if not running_scripts:
            bot.reply_to(message, "ℹ️ No scripts running.")
            return
        stopped = 0
        for key, info in list(bot_scripts.items()):
            try:
                kill_process_tree(info)
                stopped += 1
            except Exception as e:
                logger.error(f"Failed to stop {key}: {e}")
        bot_scripts.clear()
        bot.reply_to(message, f"🔄 Stopped {stopped} script(s). Now restarting...")
        started = 0
        for owner_id, file_name, ftype in running_scripts:
            folder = get_user_folder(owner_id)
            script_path = os.path.join(folder, file_name)
            if not os.path.exists(script_path):
                continue
            if ftype == 'py':
                threading.Thread(target=run_script, args=(script_path, owner_id, folder, file_name, message)).start()
            elif ftype == 'js':
                threading.Thread(target=run_js_script, args=(script_path, owner_id, folder, file_name, message)).start()
            else:
                continue
            started += 1
            time.sleep(0.5)
        bot.send_message(message.chat.id, f"✅ Restarted {started} script(s).")
        return
    _logic_restart_my_scripts(message)

# ===== MESSAGE HANDLERS =====
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message): _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_show_status(message): _logic_statistics(message)

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions,
    "📢 Broadcasts": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🏢 Run All Scripts": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "🤖 Contact Bot": _logic_clone_bot,
    "👥 User Management": _logic_user_management,
    "⚙️ Settings": _logic_admin_settings,
    "📢 Channel Add": _logic_manage_mandatory_channels,
    "🛠️ Mandatory Install": _logic_admin_install,
    "📦 Manual Install": _logic_manual_install,
    "📦 Pkg Install": _logic_recommended_install,
    "🤖 AI Agent": _logic_ai_assistant,
    "🐙 GitHub Deploy": _logic_github_deploy,
    "🔄 Restart": _logic_restart_my_scripts,
    "⏹ Stop": _logic_stop_my_scripts
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func: logic_func(message)

@bot.message_handler(commands=['updateschannel'])
def command_updates_channel(message): _logic_updates_channel(message)
@bot.message_handler(commands=['uploadfile'])
def command_upload_file(message): _logic_upload_file(message)
@bot.message_handler(commands=['checkfiles'])
def command_check_files(message): _logic_check_files(message)
@bot.message_handler(commands=['botspeed'])
def command_bot_speed(message): _logic_bot_speed(message)
@bot.message_handler(commands=['contactowner'])
def command_contact_owner(message): _logic_contact_owner(message)
@bot.message_handler(commands=['statistics'])
def command_statistics(message): _logic_statistics(message)
@bot.message_handler(commands=['subscriptions'])
def command_subscriptions(message): _logic_subscriptions(message)
@bot.message_handler(commands=['broadcast'])
def command_broadcast(message): _logic_broadcast_init(message)
@bot.message_handler(commands=['lockbot'])
def command_lock_bot(message): _logic_toggle_lock_bot(message)
@bot.message_handler(commands=['adminpanel'])
def command_admin_panel(message): _logic_admin_panel(message)
@bot.message_handler(commands=['runallscripts'])
def command_run_all_scripts(message): _logic_run_all_scripts(message)
@bot.message_handler(commands=['clonebot'])
def command_clone_bot(message): _logic_clone_bot(message)
@bot.message_handler(commands=['usermanagement'])
def command_user_management(message): _logic_user_management(message)
@bot.message_handler(commands=['adminsettings'])
def command_admin_settings(message): _logic_admin_settings(message)
@bot.message_handler(commands=['managechannels'])
def command_manage_channels(message): _logic_manage_mandatory_channels(message)
@bot.message_handler(commands=['manualinstall'])
def command_manual_install(message): _logic_manual_install(message)
@bot.message_handler(commands=['admininstall'])
def command_admin_install(message): _logic_admin_install(message)

@bot.message_handler(commands=['ping'])
def ping(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return
    start_ping_time = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start_ping_time) * 1000, 2)
    bot.edit_message_text(f"Pong! Latency: {latency} ms", message.chat.id, msg.message_id)

@bot.message_handler(commands=['githubdeploy'])
def command_github_deploy(message): _logic_github_deploy(message)
@bot.message_handler(commands=['pkginstall'])
def command_pkg_install(message): _logic_recommended_install(message)
@bot.message_handler(commands=['aiagent'])
def command_ai_agent(message): _logic_ai_assistant(message)

# ===== FILE UPLOAD HANDLER =====
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document
    logger.info(f"📎 Doc from {user_id}: {doc.file_name}")

    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if not is_subscribed and user_id not in admin_ids:
        subscription_message, sub_markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=sub_markup, parse_mode='Markdown')
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked.")
        return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        bot.reply_to(message, f"⚠️ File limit reached ({current_files}/{file_limit}).")
        return
    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "❌ No file name.")
        return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only `.py`, `.js`, `.zip` allowed.")
        return
    max_file_size = 20 * 1024 * 1024
    if doc.file_size > max_file_size:
        bot.reply_to(message, f"⚠️ File too large (Max 20MB).")
        return
    try:
        try:
            bot.forward_message(OWNER_ID, chat_id, message.message_id)
        except Exception as e: logger.error(f"Forward failed: {e}")

        download_wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        bot.edit_message_text(f"✅ Downloaded `{file_name}`. Processing...", chat_id, download_wait_msg.message_id)
        user_folder = get_user_folder(user_id)
        if file_ext == '.zip':
            handle_zip_file(downloaded_file_content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f: f.write(downloaded_file_content)
            if file_ext == '.js': handle_js_file(file_path, user_id, user_folder, file_name, message)
            elif file_ext == '.py': handle_py_file(file_path, user_id, user_folder, file_name, message)
    except Exception as e:
        logger.error(f"❌ General error handling file: {e}", exc_info=True)
        bot.reply_to(message, f"⚠️ Error: {str(e)}")

# ===== MAIN CALLBACK HANDLER =====
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"📞 Callback: User={user_id}, Data='{data}'")

    if is_user_banned(user_id) and data not in ['back_to_main']:
        bot.answer_callback_query(call.id, "❌ You are banned.", show_alert=True)
        return

    if data not in ['check_subscription_status', 'back_to_main', 'manual_install']:
        is_subscribed, not_joined = check_mandatory_subscription(user_id)
        if not is_subscribed and user_id not in admin_ids:
            subscription_message, sub_markup = create_subscription_check_message(not_joined)
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_text(subscription_message, call.message.chat.id, call.message.message_id, reply_markup=sub_markup, parse_mode='Markdown')
            except Exception:
                bot.send_message(call.message.chat.id, subscription_message, reply_markup=sub_markup, parse_mode='Markdown')
            return

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked.", show_alert=True)
        return
    try:
        if data == 'check_files': check_files_callback(call)
        elif data.startswith('file_'): file_control_callback(call)
        elif data.startswith('start_'): start_bot_callback(call)
        elif data.startswith('stop_'): stop_bot_callback(call)
        elif data.startswith('restart_'): restart_bot_callback(call)
        elif data.startswith('delete_'): delete_bot_callback(call)
        elif data.startswith('logs_'): logs_bot_callback(call)
        elif data == 'back_to_main': back_to_main_callback(call)
        elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast': handle_cancel_broadcast(call)
        elif data == 'add_admin': owner_required_callback(call, add_admin_init_callback)
        elif data == 'remove_admin': owner_required_callback(call, remove_admin_init_callback)
        elif data == 'list_admins': admin_required_callback(call, list_admins_callback)
        elif data == 'add_subscription': admin_required_callback(call, add_subscription_init_callback)
        elif data == 'remove_subscription': admin_required_callback(call, remove_subscription_init_callback)
        elif data == 'list_subscriptions': admin_required_callback(call, list_subscriptions_callback)
        elif data == 'clone_create': clone_create_callback(call)
        elif data == 'clone_remove': clone_remove_callback(call)
        elif data == 'clone_remove_confirm': clone_remove_confirm_callback(call)
        elif data == 'manual_install': manual_install_callback(call)
        elif data == 'check_subscription': admin_required_callback(call, check_subscription_init_callback)
        elif data == 'user_management': admin_required_callback(call, user_management_callback)
        elif data == 'ban_user': admin_required_callback(call, ban_user_callback)
        elif data == 'unban_user': admin_required_callback(call, unban_user_callback)
        elif data == 'user_info': admin_required_callback(call, user_info_callback)
        elif data == 'all_users': admin_required_callback(call, all_users_callback)
        elif data == 'set_user_limit': admin_required_callback(call, set_user_limit_callback)
        elif data == 'remove_user_limit': admin_required_callback(call, remove_user_limit_callback)
        elif data == 'admin_settings': admin_required_callback(call, admin_settings_callback)
        elif data == 'system_info': admin_required_callback(call, system_info_callback)
        elif data == 'bot_performance': admin_required_callback(call, bot_performance_callback)
        elif data == 'cleanup_files': admin_required_callback(call, cleanup_files_callback)
        elif data == 'install_logs': admin_required_callback(call, install_logs_callback)
        elif data == 'admin_install': admin_required_callback(call, admin_install_callback)
        elif data == 'manage_mandatory_channels': admin_required_callback(call, manage_mandatory_channels_callback)
        elif data == 'add_mandatory_channel': admin_required_callback(call, add_mandatory_channel_callback)
        elif data == 'remove_mandatory_channel': admin_required_callback(call, remove_mandatory_channel_callback)
        elif data == 'list_mandatory_channels': admin_required_callback(call, list_mandatory_channels_callback)
        elif data.startswith('remove_channel_'): admin_required_callback(call, process_remove_channel)
        elif data.startswith('users_page_'): handle_users_page(call)
        elif data == 'check_subscription_status': check_subscription_status_callback(call)
        elif data == 'noop': bot.answer_callback_query(call.id)
        elif data == 'recommended_install': _logic_recommended_install(call.message); bot.answer_callback_query(call.id)
        elif data == 'ai_assistant': _logic_ai_assistant(call.message); bot.answer_callback_query(call.id)
        elif data == 'github_deploy': _logic_github_deploy(call.message); bot.answer_callback_query(call.id)
        elif data == 'change_ai_model': admin_required_callback(call, change_ai_model_callback)
        else:
            bot.answer_callback_query(call.id, "❓ Unknown action.")
    except Exception as e:
        logger.error(f"❌ Error handling callback '{data}': {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)
        except: pass

def admin_required_callback(call, func_to_run):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
        return
    func_to_run(call)

def owner_required_callback(call, func_to_run):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "👑 Owner required.", show_alert=True)
        return
    func_to_run(call)

def change_ai_model_callback(call):
    bot.answer_callback_query(call.id)
    markup = create_model_selection_markup()
    bot.edit_message_text("Select a new AI model:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def check_files_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.answer_callback_query(call.id, "📂 No files.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
            bot.edit_message_text("📂 Your files:\n\n(No files)", chat_id, call.message.message_id, reply_markup=markup)
        except Exception: pass
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🏢 Active" if is_running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 Your files:\nClick to manage.", chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        if "not modified" not in str(e): logger.error(f"Error: {e}")

def file_control_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⛔ Only your own files.", show_alert=True)
            check_files_callback(call)
            return
        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "❓ File not found.", show_alert=True)
            check_files_callback(call)
            return
        bot.answer_callback_query(call.id)
        is_running = is_bot_running(script_owner_id, file_name)
        status_text = '🏢 Active' if is_running else '🔴 Stopped'
        file_type = next((f[1] for f in user_files_list if f[0] == file_name), '?')
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_running),
                parse_mode='Markdown'
            )
        except Exception as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"Error in file_control_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def start_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⛔ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "❓ File not found.", show_alert=True); check_files_callback(call); return
        file_type = file_info[1]
        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            remove_user_file_db(script_owner_id, file_name); check_files_callback(call); return
        if is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, "⚠️ Already running.", show_alert=True)
            try: bot.edit_message_reply_markup(chat_id_for_reply, call.message.message_id, reply_markup=create_control_buttons(script_owner_id, file_name, True))
            except: pass
            return
        bot.answer_callback_query(call.id, f"⏳ Starting {file_name}...")
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
             bot.send_message(chat_id_for_reply, f"❌ Unknown type '{file_type}'."); return
        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, file_name)
        status_text = '🏢 Active' if is_now_running else '🟡 Starting'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running), parse_mode='Markdown'
            )
        except Exception as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"Error in start_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⛔ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "❓ File not found.", show_alert=True); check_files_callback(call); return
        file_type = file_info[1]
        script_key = f"{script_owner_id}_{file_name}"
        if not is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, f"🛑 Already stopped.", show_alert=True)
            try:
                 bot.edit_message_text(
                     f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: 🔴 Stopped",
                     chat_id_for_reply, call.message.message_id,
                     reply_markup=create_control_buttons(script_owner_id, file_name, False), parse_mode='Markdown')
            except: pass
            return
        bot.answer_callback_query(call.id, f"⏳ Stopping {file_name}...")
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: 🔴 Stopped",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, False), parse_mode='Markdown'
            )
        except Exception as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"Error in stop_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⛔ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "❓ File not found.", show_alert=True); check_files_callback(call); return
        file_type = file_info[1]; user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name); script_key = f"{script_owner_id}_{file_name}"
        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            remove_user_file_db(script_owner_id, file_name)
            if script_key in bot_scripts: del bot_scripts[script_key]
            check_files_callback(call); return
        bot.answer_callback_query(call.id, f"🔄 Restarting {file_name}...")
        if is_bot_running(script_owner_id, file_name):
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(1.5)
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
             bot.send_message(chat_id_for_reply, f"❌ Unknown type."); return
        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, file_name)
        status_text = '🏢 Active' if is_now_running else '🟡 Starting'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running), parse_mode='Markdown'
            )
        except Exception as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"Error in restart_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⛔ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "❓ File not found.", show_alert=True); check_files_callback(call); return
        bot.answer_callback_query(call.id, f"🗑️ Deleting {file_name}...")
        script_key = f"{script_owner_id}_{file_name}"
        if is_bot_running(script_owner_id, file_name):
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(0.5)
        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        deleted_disk = []
        if os.path.exists(file_path):
            try: os.remove(file_path); deleted_disk.append(file_name)
            except OSError as e: logger.error(f"Error deleting {file_path}: {e}")
        if os.path.exists(log_path):
            try: os.remove(log_path); deleted_disk.append(os.path.basename(log_path))
            except OSError as e: logger.error(f"Error deleting log {log_path}: {e}")
        remove_user_file_db(script_owner_id, file_name)
        deleted_str = ", ".join(f"`{f}`" for f in deleted_disk) if deleted_disk else "files"
        try:
            bot.edit_message_text(
                f"🗑️ Record `{file_name}` (User `{script_owner_id}`) and {deleted_str} deleted!",
                chat_id_for_reply, call.message.message_id, reply_markup=None, parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing msg: {e}")
            bot.send_message(chat_id_for_reply, f"✅ Record `{file_name}` deleted.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in delete_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⛔ Permission denied.", show_alert=True); return
        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "❓ File not found.", show_alert=True); check_files_callback(call); return
        user_folder = get_user_folder(script_owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, f"📜 No logs for '{file_name}'.", show_alert=True); return
        bot.answer_callback_query(call.id)
        try:
            log_content = ""; file_size = os.path.getsize(log_path)
            max_log_kb = 100; max_tg_msg = 4096
            if file_size == 0: log_content = "(Log empty)"
            elif file_size > max_log_kb * 1024:
                 with open(log_path, 'rb') as f: f.seek(-max_log_kb * 1024, os.SEEK_END); log_bytes = f.read()
                 log_content = f"(Last {max_log_kb} KB)\n...\n" + log_bytes.decode('utf-8', errors='ignore')
            else:
                 with open(log_path, 'r', encoding='utf-8', errors='ignore') as f: log_content = f.read()
            if len(log_content) > max_tg_msg:
                log_content = log_content[-max_tg_msg:]
            if not log_content.strip(): log_content = "(No content)"
            bot.send_message(chat_id_for_reply, f"📜 Logs for `{file_name}` (User `{script_owner_id}`):\n```\n{log_content}\n```", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error reading log: {e}")
            bot.send_message(chat_id_for_reply, f"⚠️ Error reading log.")
    except Exception as e:
        logger.error(f"Error in logs_bot_callback: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def back_to_main_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    user_name = call.from_user.first_name
    if user_id == OWNER_ID: user_status = "👑 Owner"
    elif user_id in admin_ids: user_status = "⚜️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "💎 Premium"
            days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⌛ Expires in: {days_left} days"
        else:
            user_status = "🆓 Free User"
            remove_subscription_db(user_id)
    else: user_status = "🆓 Free User"
    main_menu_text = f"Welcome, {user_name}!\n\n🆔 ID: {user_id}\n🔰 Status: {user_status}{expiry_info}\n📁 Files: {current_files}/{limit_str}"
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(main_menu_text, chat_id, call.message.message_id, parse_mode='Markdown')
    except Exception as e:
        if "not modified" not in str(e): logger.error(f"Error: {e}")

def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids: bot.reply_to(message, "⛔ Not authorized."); return
    if message.text and message.text.lower() == '/cancel': bot.reply_to(message, "❌ Broadcast cancelled."); return
    broadcast_content = message.text
    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_broadcast_{message.message_id}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast"))
    preview_text = broadcast_content[:1000].strip() if broadcast_content else "(Media)"
    bot.reply_to(message, f"📢 Confirm Broadcast:\n\n```\n{preview_text}\n```\nTo {target_count} users.", reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if user_id not in admin_ids: bot.answer_callback_query(call.id, "⛔ Admin only.", show_alert=True); return
    try:
        original_message = call.message.reply_to_message
        if not original_message: raise ValueError("No original message.")
        broadcast_text = original_message.text if original_message.text else None
        if not broadcast_text: raise ValueError("No text to broadcast.")
        bot.answer_callback_query(call.id, "📢 Starting broadcast...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...", chat_id, call.message.message_id, reply_markup=None)
        threading.Thread(target=execute_broadcast, args=(broadcast_text, None, None, None, chat_id)).start()
    except ValueError as ve:
        bot.edit_message_text(f"❌ {ve}", chat_id, call.message.message_id, reply_markup=None)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        bot.edit_message_text("❌ Error.", chat_id, call.message.message_id, reply_markup=None)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "📢 Cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

def execute_broadcast(broadcast_text, photo_id, video_id, caption, admin_chat_id):
    sent_count = 0; failed_count = 0; blocked_count = 0
    start_exec_time = time.time()
    users_to_broadcast = list(active_users); total_users = len(users_to_broadcast)
    batch_size = 25; delay_batches = 1.5
    for i, user_id_bc in enumerate(users_to_broadcast):
        try:
            if broadcast_text: bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
            sent_count += 1
        except telebot.apihelper.ApiTelegramException as e:
            err_desc = str(e).lower()
            if any(s in err_desc for s in ["blocked", "deactivated", "not found", "kicked"]):
                blocked_count += 1
            elif "flood control" in err_desc:
                time.sleep(5)
                try:
                    bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
                    sent_count += 1
                except: failed_count += 1
            else: failed_count += 1
        except Exception as e: failed_count += 1
        if (i + 1) % batch_size == 0 and i < total_users - 1:
            time.sleep(delay_batches)
        elif i % 5 == 0: time.sleep(0.2)
    duration = round(time.time() - start_exec_time, 2)
    result_msg = f"📢 Broadcast Complete!\n\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}\n🚫 Blocked: {blocked_count}\n🎯 Targets: {total_users}\n⏱️ {duration}s"
    try: bot.send_message(admin_chat_id, result_msg)
    except: pass

# ===== ADMIN PANEL CALLBACKS =====
def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔢 Enter User ID to promote to Admin.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    owner_id_check = message.from_user.id
    if owner_id_check != OWNER_ID: bot.reply_to(message, "👑 Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id <= 0: raise ValueError("ID must be positive")
        if new_admin_id == OWNER_ID: bot.reply_to(message, "👑 Already owner."); return
        if new_admin_id in admin_ids: bot.reply_to(message, f"👑 Already admin."); return
        add_admin_db(new_admin_id)
        bot.reply_to(message, f"✅ User `{new_admin_id}` promoted to Admin.")
        try: bot.send_message(new_admin_id, "👑 Congrats! You are now an Admin.")
        except: pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid ID.")
        msg = bot.send_message(message.chat.id, "🔢 Enter User ID to promote or /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔢 Enter User ID of Admin to remove.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    owner_id_check = message.from_user.id
    if owner_id_check != OWNER_ID: bot.reply_to(message, "👑 Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove <= 0: raise ValueError("ID must be positive")
        if admin_id_remove == OWNER_ID: bot.reply_to(message, "👑 Cannot remove self."); return
        if admin_id_remove not in admin_ids: bot.reply_to(message, "❌ Not admin."); return
        if remove_admin_db(admin_id_remove):
            bot.reply_to(message, f"✅ Admin `{admin_id_remove}` removed.")
            try: bot.send_message(admin_id_remove, "👑 You are no longer Admin.")
            except: pass
        else: bot.reply_to(message, f"❌ Failed to remove.")
    except ValueError:
        bot.reply_to(message, "❌ Invalid ID.")
        msg = bot.send_message(message.chat.id, "🔢 Enter Admin ID to remove or /cancel.")
        bot.register_next_step_handler(msg, process_remove_admin_id)

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    try:
        admin_list_str = ""
        for aid in sorted(list(admin_ids)):
            if aid == OWNER_ID:
                admin_list_str += f"👑 `{aid}` (Owner)\n"
            else:
                admin_list_str += f"👤 `{aid}`\n"
        if not admin_list_str: admin_list_str = "😕 No admins!"
        bot.edit_message_text(f"👑 **Current Admins:**\n\n{admin_list_str}", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e: logger.error(f"Error: {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔢 Enter User ID & days\nExample: `123456789 30`\n/cancel", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⛔ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError("Format")
        sub_user_id = int(parts[0].strip()); days = int(parts[1].strip())
        if sub_user_id <= 0 or days <= 0: raise ValueError("Positive")
        current_expiry = user_subscriptions.get(sub_user_id, {}).get('expiry')
        start_date_new_sub = datetime.now()
        if current_expiry and current_expiry > start_date_new_sub: start_date_new_sub = current_expiry
        new_expiry = start_date_new_sub + timedelta(days=days)
        save_subscription(sub_user_id, new_expiry)
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` added {days} days.\nNew expiry: {new_expiry:%Y-%m-%d}")
        try: bot.send_message(sub_user_id, f"💎 Sub activated for {days} days! Expires: {new_expiry:%Y-%m-%d}.")
        except: pass
    except ValueError:
        bot.reply_to(message, f"❌ Invalid. Format: `ID days` or /cancel.")
        msg = bot.send_message(message.chat.id, "🔢 Enter User ID & days, or /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription_details)

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔢 Enter User ID to remove\n/cancel")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⛔ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        sub_user_id_remove = int(message.text.strip())
        if sub_user_id_remove <= 0: raise ValueError("Positive")
        if sub_user_id_remove not in user_subscriptions:
            bot.reply_to(message, f"ℹ️ User has no active sub."); return
        remove_subscription_db(sub_user_id_remove)
        bot.reply_to(message, f"✅ Sub removed.")
        try: bot.send_message(sub_user_id_remove, "❌ Your subscription removed.")
        except: pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid ID.")
        msg = bot.send_message(message.chat.id, "🔢 Enter User ID or /cancel.")
        bot.register_next_step_handler(msg, process_remove_subscription_id)

def list_subscriptions_callback(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⛔ Admin only.", show_alert=True)
        return
    if not user_subscriptions:
        bot.edit_message_text("😕 No active subscriptions.", call.message.chat.id, call.message.message_id, reply_markup=create_subscription_panel())
        return
    subs_text = "**💳 Active Subscriptions:**\n\n"
    for user_id, sub_info in list(user_subscriptions.items())[:20]:
        expiry = sub_info.get('expiry')
        if expiry:
            days_left = (expiry - datetime.now()).days if expiry > datetime.now() else 0
            status = "🏢 Active" if expiry > datetime.now() else "🔴 Expired"
            subs_text += f"🆔 User {user_id}\n🏢 Status: {status}\n⏳ Expires: {expiry.strftime('%Y-%m-%d')} ({days_left} days)\n\n"
    if len(user_subscriptions) > 20:
        subs_text += f"\n... and {len(user_subscriptions) - 20} more"
    bot.edit_message_text(subs_text, call.message.chat.id, call.message.message_id, reply_markup=create_subscription_panel(), parse_mode='Markdown')

def manual_install_callback(call):
    bot.answer_callback_query(call.id)
    manual_install_module_init(call.message)

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to check sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        sub_user_id_check = int(message.text.strip())
        if sub_user_id_check <= 0: raise ValueError("Positive")
        if sub_user_id_check in user_subscriptions:
            expiry_dt = user_subscriptions[sub_user_id_check].get('expiry')
            if expiry_dt:
                if expiry_dt > datetime.now():
                    days_left = (expiry_dt - datetime.now()).days
                    bot.reply_to(message, f"✅ User `{sub_user_id_check}` active sub.\nExpires: {expiry_dt:%Y-%m-%d} ({days_left} days left).")
                else:
                    bot.reply_to(message, f"⚠️ User expired sub (On: {expiry_dt:%Y-%m-%d}).")
                    remove_subscription_db(sub_user_id_check)
            else: bot.reply_to(message, f"⚠️ Expiry missing.")
        else: bot.reply_to(message, f"ℹ️ No active sub record.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID or /cancel.")
        bot.register_next_step_handler(msg, process_check_subscription_id)

# ===== USER MANAGEMENT CALLBACKS =====
def user_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👥 User Management\nSelect action:", call.message.chat.id, call.message.message_id, reply_markup=create_user_management_menu())
    except Exception as e: logger.error(f"Error: {e}")

def ban_user_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🚫 Enter User ID to ban and reason (e.g., `12345678 Spamming`)\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_ban_user)

def process_ban_user(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Ban cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) < 2: bot.reply_to(message, "⚠️ Format: `user_id reason`"); return
        user_id = int(parts[0]); reason = ' '.join(parts[1:])
        if user_id <= 0: raise ValueError("Positive")
        if user_id == OWNER_ID: bot.reply_to(message, "⚠️ Cannot ban owner."); return
        if user_id in admin_ids: bot.reply_to(message, "⚠️ Cannot ban admin."); return
        if ban_user_db(user_id, reason, admin_id):
            bot.reply_to(message, f"✅ User `{user_id}` banned.\nReason: {reason}")
            for file_name, _ in user_files.get(user_id, []):
                script_key = f"{user_id}_{file_name}"
                if script_key in bot_scripts:
                    kill_process_tree(bot_scripts[script_key])
                    del bot_scripts[script_key]
            try: bot.send_message(user_id, f"🚫 You have been banned.\nReason: {reason}")
            except: pass
        else: bot.reply_to(message, "❌ Failed to ban.")
    except ValueError: bot.reply_to(message, "⚠️ Invalid user ID.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

def unban_user_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "✅ Enter User ID to unban\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_unban_user)

def process_unban_user(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Unban cancelled."); return
    try:
        user_id = int(message.text.strip())
        if user_id <= 0: raise ValueError("Positive")
        if user_id not in banned_users:
            bot.reply_to(message, f"ℹ️ User `{user_id}` is not banned."); return
        if unban_user_db(user_id):
            bot.reply_to(message, f"✅ User `{user_id}` unbanned.")
            try: bot.send_message(user_id, "✅ Your ban has been lifted.")
            except: pass
        else: bot.reply_to(message, "❌ Failed to unban.")
    except ValueError: bot.reply_to(message, "⚠️ Invalid user ID.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

def user_info_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👤 Enter User ID to get info\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_user_info)

def process_user_info(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        user_id = int(message.text.strip())
        if user_id <= 0: raise ValueError("Positive")
        info_parts = []
        info_parts.append(f"👤 **User ID:** `{user_id}`")
        if user_id == OWNER_ID: info_parts.append("👑 **Status:** Owner")
        elif user_id in admin_ids: info_parts.append("🛡️ **Status:** Admin")
        elif user_id in banned_users: info_parts.append("🚫 **Status:** Banned")
        elif user_id in user_subscriptions:
            expiry = user_subscriptions[user_id].get('expiry')
            if expiry and expiry > datetime.now():
                days_left = (expiry - datetime.now()).days
                info_parts.append(f"⭐ **Status:** Premium ({days_left} days)")
            else: info_parts.append("🆓 **Status:** Free (Expired)")
        else: info_parts.append("🆓 **Status:** Free User")
        file_count = get_user_file_count(user_id)
        file_limit = get_user_file_limit(user_id)
        info_parts.append(f"📁 **Files:** {file_count}/{file_limit if file_limit != float('inf') else 'Unlimited'}")
        if user_id in user_limits: info_parts.append(f"⚙️ **Custom Limit:** {user_limits[user_id]}")
        running_scripts = 0
        for file_name, _ in user_files.get(user_id, []):
            if is_bot_running(user_id, file_name): running_scripts += 1
        info_parts.append(f"🤖 **Running Scripts:** {running_scripts}")
        if user_id in active_users: info_parts.append("🏢 **Status:** Active")
        bot.reply_to(message, "\n".join(info_parts), parse_mode='Markdown')
    except ValueError: bot.reply_to(message, "⚠️ Invalid user ID.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

def all_users_callback(call):
    bot.answer_callback_query(call.id)
    try:
        if not active_users:
            bot.edit_message_text("👥 No active users yet.", call.message.chat.id, call.message.message_id); return
        users_list = list(active_users)
        chunk_size = 20
        total_pages = (len(users_list) + chunk_size - 1) // chunk_size
        display_users_list(call.message.chat.id, call.message.message_id, users_list, 0, total_pages, chunk_size)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def display_users_list(chat_id, message_id, users_list, page, total_pages, chunk_size):
    start_idx = page * chunk_size
    end_idx = min(start_idx + chunk_size, len(users_list))
    user_chunk = users_list[start_idx:end_idx]
    message_text = f"👥 **Active Users** (Page {page + 1}/{total_pages})\n\n"
    for i, user_id in enumerate(user_chunk, start=start_idx + 1):
        if user_id == OWNER_ID: status = "👑"
        elif user_id in admin_ids: status = "🛡️"
        elif user_id in banned_users: status = "🚫"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): status = "⭐"
        else: status = "🆓"
        message_text += f"{i}. `{user_id}` {status}\n"
    markup = types.InlineKeyboardMarkup(row_width=3)
    if total_pages > 1:
        page_buttons = []
        if page > 0: page_buttons.append(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"users_page_{page-1}"))
        page_buttons.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1: page_buttons.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"users_page_{page+1}"))
        markup.row(*page_buttons)
    markup.row(types.InlineKeyboardButton("🔙 Back", callback_data='user_management'))
    try: bot.edit_message_text(message_text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception as e: logger.error(f"Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('users_page_'))
def handle_users_page(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    try:
        page = int(call.data.split('_')[2])
        users_list = list(active_users)
        chunk_size = 20
        total_pages = (len(users_list) + chunk_size - 1) // chunk_size
        if 0 <= page < total_pages:
            bot.answer_callback_query(call.id)
            display_users_list(call.message.chat.id, call.message.message_id, users_list, page, total_pages, chunk_size)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

def set_user_limit_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔧 Enter User ID and new limit (e.g., `12345678 50`)\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_set_user_limit)

def process_set_user_limit(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError("Format: user_id limit")
        user_id = int(parts[0]); limit = int(parts[1])
        if user_id <= 0 or limit <= 0: raise ValueError("Positive")
        if set_user_limit_db(user_id, limit, admin_id):
            bot.reply_to(message, f"✅ Set file limit {limit} for user `{user_id}`")
            try: bot.send_message(user_id, f"⚙️ Your file upload limit has been set to {limit}")
            except: pass
        else: bot.reply_to(message, "❌ Failed.")
    except ValueError as e: bot.reply_to(message, f"⚠️ {e}")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

def remove_user_limit_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🗑️ Enter User ID to remove custom limit\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_remove_user_limit)

def process_remove_user_limit(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    try:
        user_id = int(message.text.strip())
        if user_id <= 0: raise ValueError("Positive")
        if user_id not in user_limits:
            bot.reply_to(message, f"ℹ️ User has no custom limit."); return
        if remove_user_limit_db(user_id):
            bot.reply_to(message, f"✅ Removed custom limit.")
            try: bot.send_message(user_id, "⚙️ Your custom file limit has been removed")
            except: pass
        else: bot.reply_to(message, "❌ Failed.")
    except ValueError: bot.reply_to(message, "⚠️ Invalid user ID.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ===== ADMIN SETTINGS CALLBACKS =====
def admin_settings_callback(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("⚙️ Admin Settings\nSelect action:", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())
    except Exception as e: logger.error(f"Error: {e}")

def system_info_callback(call):
    bot.answer_callback_query(call.id)
    try:
        import platform
        info_parts = []
        info_parts.append("🤖 **Bot Information:**")
        info_parts.append(f"• Python: {platform.python_version()}")
        info_parts.append(f"• Platform: {platform.platform()}")
        info_parts.append("\n💻 **System Information:**")
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            info_parts.append(f"• CPU: {cpu_percent}%")
            info_parts.append(f"• Memory: {memory.percent}% ({memory.used//1024//1024}MB/{memory.total//1024//1024}MB)")
            info_parts.append(f"• Disk: {disk.percent}%")
        except Exception as e: info_parts.append(f"• Error: {str(e)}")
        info_parts.append("\n📊 **Bot Statistics:**")
        info_parts.append(f"• Active Users: {len(active_users)}")
        info_parts.append(f"• Running Scripts: {len(bot_scripts)}")
        info_parts.append(f"• Total Files: {sum(len(files) for files in user_files.values())}")
        info_parts.append(f"• Status: {'🔒 Locked' if bot_locked else '🔓 Unlocked'}")
        bot.edit_message_text("\n".join(info_parts), call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def bot_performance_callback(call):
    bot.answer_callback_query(call.id)
    try:
        running_scripts = len(bot_scripts)
        total_files = sum(len(files) for files in user_files.values())
        performance_parts = ["📈 **Bot Performance Metrics:**"]
        performance_parts.append(f"• Running Scripts: {running_scripts}")
        performance_parts.append(f"• Total Scripts: {total_files}")
        uptime_pct = (running_scripts / total_files * 100) if total_files > 0 else 0.0
        performance_parts.append(f"• Uptime: {uptime_pct:.1f}%")
        try:
            bot_process = psutil.Process()
            memory_usage = bot_process.memory_info().rss / 1024 / 1024
            cpu_usage = bot_process.cpu_percent(interval=0.5)
            performance_parts.append(f"\n💾 **Resource Usage:**")
            performance_parts.append(f"• Memory: {memory_usage:.1f} MB")
            performance_parts.append(f"• CPU: {cpu_usage:.1f}%")
        except: pass
        performance_parts.append(f"\n🗄️ **Database:**")
        performance_parts.append(f"• Active Users: {len(active_users)}")
        performance_parts.append(f"• Subscriptions: {len(user_subscriptions)}")
        performance_parts.append(f"• Banned Users: {len(banned_users)}")
        bot.edit_message_text("\n".join(performance_parts), call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def cleanup_files_callback(call):
    bot.answer_callback_query(call.id, "🧹 Cleaning up...")
    try:
        cleaned_dirs = 0; cleaned_files = 0
        for user_dir in os.listdir(UPLOAD_BOTS_DIR):
            user_path = os.path.join(UPLOAD_BOTS_DIR, user_dir)
            if os.path.isdir(user_path):
                if not os.listdir(user_path):
                    try: os.rmdir(user_path); cleaned_dirs += 1
                    except: pass
                else:
                    for file_name in os.listdir(user_path):
                        if file_name.endswith('.log'):
                            file_path = os.path.join(user_path, file_name)
                            try:
                                file_age = time.time() - os.path.getmtime(file_path)
                                if file_age > 7 * 24 * 3600:
                                    os.remove(file_path); cleaned_files += 1
                            except: pass
        result_msg = f"🧹 **Cleanup Complete:**\n• Empty dirs removed: {cleaned_dirs}\n• Old logs cleared: {cleaned_files}"
        bot.edit_message_text(result_msg, call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.edit_message_text(f"❌ Error: {str(e)}", call.message.chat.id, call.message.message_id)

def install_logs_callback(call):
    bot.answer_callback_query(call.id)
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute('SELECT user_id, module_name, package_name, status, install_date FROM install_logs ORDER BY install_date DESC LIMIT 20')
            logs = c.fetchall()
            conn.close()
        if not logs:
            bot.edit_message_text("📋 **No installation logs**", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())
            return
        log_text = "📋 **Recent Installation Logs:**\n\n"
        for user_id, module_name, package_name, status, install_date in logs:
            status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
            log_text += f"{status_icon} `{user_id}`: {module_name} -> {package_name}\n"
            log_text += f"   📅 {install_date[:19]}\n\n"
        bot.edit_message_text(log_text, call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def admin_install_callback(call):
    bot.answer_callback_query(call.id)
    _logic_admin_install(call.message)

# ===== MANDATORY CHANNELS CALLBACKS =====
def manage_mandatory_channels_callback(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("📢 Manage Mandatory Channels\nChoose action:", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())
    except Exception as e: logger.error(f"Error: {e}")

def add_mandatory_channel_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Send channel ID or username (e.g., @channel or -1001234567890)\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_add_channel)

def process_add_channel(message):
    admin_id = message.from_user.id
    if admin_id not in admin_ids: bot.reply_to(message, "⚠️ Not authorized."); return
    if message.text and message.text.lower() == '/cancel': bot.reply_to(message, "❌ Cancelled."); return
    channel_identifier = message.text.strip()
    try:
        chat = bot.get_chat(channel_identifier)
        channel_id = str(chat.id)
        channel_username = f"@{chat.username}" if chat.username else ""
        channel_name = chat.title
        try:
            bot_member = bot.get_chat_member(channel_id, bot.get_me().id)
            if bot_member.status not in ['administrator', 'creator']:
                bot.reply_to(message, f"❌ Bot must be admin in the channel!")
                return
        except:
            bot.reply_to(message, f"❌ Bot cannot access the channel!")
            return
        if save_mandatory_channel(channel_id, channel_username, channel_name, admin_id):
            bot.reply_to(message, f"✅ Mandatory Channel Added:\n**{channel_name}**\n{channel_username or channel_id}")
        else:
            bot.reply_to(message, "❌ Failed to add channel.")
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

def remove_mandatory_channel_callback(call):
    if not mandatory_channels:
        bot.answer_callback_query(call.id, "❌ No mandatory channels.", show_alert=True); return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    for channel_id, channel_info in mandatory_channels.items():
        channel_name = channel_info.get('name', 'Unknown')
        markup.add(types.InlineKeyboardButton(f"🗑️ {channel_name}", callback_data=f'remove_channel_{channel_id}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='manage_mandatory_channels'))
    try: bot.edit_message_text("📢 Choose channel to delete:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e: logger.error(f"Error: {e}")

def process_remove_channel(call):
    channel_id = call.data.replace('remove_channel_', '')
    if channel_id in mandatory_channels:
        channel_name = mandatory_channels[channel_id].get('name', 'Unknown')
        if remove_mandatory_channel_db(channel_id):
            bot.answer_callback_query(call.id, f"✅ Deleted: {channel_name}")
            try:
                bot.edit_message_text(f"✅ Mandatory channel deleted: **{channel_name}**", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu(), parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Failed.", show_alert=True)
    else: bot.answer_callback_query(call.id, "❌ Not found.", show_alert=True)

def list_mandatory_channels_callback(call):
    bot.answer_callback_query(call.id)
    if not mandatory_channels:
        message_text = "📢 **No mandatory channels**"
    else:
        message_text = "📢 **Mandatory Channels:**\n\n"
        for channel_id, channel_info in mandatory_channels.items():
            channel_name = channel_info.get('name', 'Unknown')
            channel_username = channel_info.get('username', 'No username')
            message_text += f"• **{channel_name}**\n  {channel_username or channel_id}\n\n"
    try: bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu(), parse_mode='Markdown')
    except Exception as e: logger.error(f"Error: {e}")

def check_subscription_status_callback(call):
    user_id = call.from_user.id
    is_subscribed, not_joined = check_mandatory_subscription(user_id)
    if is_subscribed or user_id in admin_ids:
        bot.answer_callback_query(call.id, "✅ You are subscribed!", show_alert=True)
        try: _logic_send_welcome(call.message)
        except: back_to_main_callback(call)
    else:
        bot.answer_callback_query(call.id, "❌ Not joined all channels!", show_alert=True)
        subscription_message, markup = create_subscription_check_message(not_joined)
        try:
            bot.edit_message_text(subscription_message, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        except: pass

# ===== CLONE CALLBACKS =====
def clone_create_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_main"))
    bot.edit_message_text(
        f"🚀 **Clone Bot**\n\nSend your bot token from @BotFather\nFormat: `1234567890:ABCdefGHi`",
        chat_id, message_id, reply_markup=markup, parse_mode="Markdown"
    )
    bot.register_next_step_handler_by_chat_id(chat_id, lambda msg: handle_token_input(msg, chat_id, message_id))
    bot.answer_callback_query(call.id)

def clone_remove_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    if user_id not in user_clones:
        bot.answer_callback_query(call.id, f"⚠️ No Clone bot found.", show_alert=True); return
    bot_username = user_clones[user_id]['bot_username']
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("✅ Remove", callback_data="clone_remove_confirm"), types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_main"))
    bot.edit_message_text(
        f"🗑️ **Remove Clone Bot**\n\n⚠️ Remove your clone bot?\n\n🤖 Bot: @{bot_username}",
        chat_id, message_id, reply_markup=markup, parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

def clone_remove_confirm_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    if user_id not in user_clones:
        bot.answer_callback_query(call.id, f"⚠️ No clone bot found.", show_alert=True); return
    bot_username = user_clones[user_id]['bot_username']
    clone_dir = os.path.join(BASE_DIR, f'clone_{user_id}')
    if os.path.exists(clone_dir):
        try: shutil.rmtree(clone_dir)
        except Exception as e: logger.error(f"Error removing clone dir: {e}")
    remove_clone_info(user_id)
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"✅ **Clone Bot Removed!**\n\n🤖 Bot: @{bot_username}\n🗑️ Successfully removed",
        chat_id, message_id, reply_markup=None, parse_mode="Markdown"
    )

def handle_token_input(message, original_chat_id, original_message_id):
    user_id = message.from_user.id
    if message.text == '/cancel':
        _logic_clone_bot(message); return
    token = message.text.strip()
    if not token or len(token) < 35 or ':' not in token:
        bot.reply_to(message, "❌ Invalid bot token!", parse_mode="Markdown"); return
    processing_msg = bot.reply_to(message, "🔄 Creating your bot clone...")
    try:
        test_bot = telebot.TeleBot(token)
        bot_info = test_bot.get_me()
        bot.edit_message_text(f"✅ Token validated!\n\nBot: @{bot_info.username}\nCreating...", processing_msg.chat.id, processing_msg.message_id)
        clone_success = create_bot_clone(user_id, token, bot_info.username)
        if clone_success:
            success_msg = f"**🎉 Bot Clone Created!**\n\n🤖 **Bot:** @{bot_info.username}\n🚀 **Status:** Running"
            bot.edit_message_text(success_msg, processing_msg.chat.id, processing_msg.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text("❌ Failed to create clone.", processing_msg.chat.id, processing_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Failed: `{str(e)}`", processing_msg.chat.id, processing_msg.message_id, parse_mode="Markdown")

# ===== CLEANUP =====
def cleanup():
    logger.warning("🧹 Shutdown. Cleaning up processes...")
    script_keys_to_stop = list(bot_scripts.keys())
    if not script_keys_to_stop: return
    for key in script_keys_to_stop:
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
atexit.register(cleanup)

# ===== MAIN =====
if __name__ == '__main__':
    logger.info("="*40 + "\n🚀 Bot Starting...\n" + f"🐍 Python: {sys.version.split()[0]}\n👑 Owner ID: {OWNER_ID}\n")
    logger.info("🔄 Starting auto-recovery worker...")
    recovery_thread = threading.Thread(target=auto_recovery_worker, daemon=True)
    recovery_thread.start()
    keep_alive()
    logger.info("🔄 Starting polling...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.critical(f"❌ Polling error: {e}", exc_info=True)
            time.sleep(30)
        finally:
            time.sleep(1)