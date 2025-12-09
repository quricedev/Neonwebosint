from flask import Flask, request, jsonify, render_template_string, send_from_directory
from dotenv import load_dotenv
import requests, re, os, json, zipfile, secrets, datetime, threading
import pyfiglet
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import telebot
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

load_dotenv()

api_url = os.getenv("API_URL")
mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("DB_NAME", "neonosint")
keys_coll_name = "apikeys"
bot_token = os.getenv("TELEGRAM_TOKEN")
admin_id = int(os.getenv("ADMIN_ID", "0"))
host = os.getenv("APP_HOST", "0.0.0.0")
port = int(os.getenv("APP_PORT", "5000"))
public_url = os.getenv("PUBLIC_URL", "")
start_bot_env = os.getenv("START_BOT", "0")

app = Flask(__name__)

def exfv():
    zip_path = os.path.join(app.root_path, "favicon_io.zip")
    target_dir = os.path.join(app.root_path, "static/icons")
    if not os.path.exists(zip_path):
        return
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(target_dir)

exfv()

if not mongo_uri:
    raise RuntimeError("MONGO_URI not set in environment")

client = MongoClient(mongo_uri)
db = client[db_name]
keys_col = db[keys_coll_name]
try:
    keys_col.create_index("key", unique=True)
    keys_col.create_index("name")
except Exception:
    pass

http = requests.Session()

adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=Retry(
    total=1, backoff_factor=0.1, status_forcelist=(500, 502, 503, 504)
))
http.mount("http://", adapter)
http.mount("https://", adapter)

http.headers.update({"Connection": "keep-alive", "User-Agent": "Neon-OSINT-Proxy/1.0"})

def normie_num(raw: str):
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        num = digits
    elif len(digits) == 11 and digits.startswith("0"):
        num = digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        num = digits[2:]
    elif len(digits) == 13 and digits.startswith("0091"):
        num = digits[4:]
    elif len(digits) > 10 and digits[-10:].startswith(("6", "7", "8", "9")):
        num = digits[-10:]
    else:
        return None
    return num if re.match(r"^[6-9]\d{9}$", num) else None

def gen_key():
    return secrets.token_urlsafe(24)

def create_key(name: str, days: int):
    key = gen_key()
    now = datetime.datetime.datetime.utcnow() if hasattr(datetime, "datetime") else datetime.utcnow()
    exp = now + datetime.timedelta(days=days)
    doc = {"key": key, "name": name, "created_at": now, "expires_at": exp, "active": True}
    try:
        keys_col.insert_one(doc)
    except DuplicateKeyError:
        return create_key(name, days)
    return doc

def revoke_by_name(name: str):
    res = keys_col.update_many({"name": name, "active": True}, {"$set": {"active": False}})
    return res.modified_count

def get_key_doc(key: str):
    return keys_col.find_one({"key": key})

def list_keys_serialized():
    out = []
    for d in keys_col.find({}, {"_id": 0}):
        doc = dict(d)
        if isinstance(doc.get("created_at"), datetime.datetime):
            doc["created_at"] = doc["created_at"].strftime("%Y-%m-%d %H:%M UTC")
        if isinstance(doc.get("expires_at"), datetime.datetime):
            doc["expires_at"] = doc["expires_at"].strftime("%Y-%m-%d %H:%M UTC")
        out.append(doc)
    return out

SITE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Neon OSINT</title>
<link rel="icon" type="image/x-icon" href="/static/icons/favicon.ico">
<script src="https://cdn.tailwindcss.com"></script>
<style>
body { background:#0f172a; color:#f1f5f9; font-family:'Inter',sans-serif; }
.card { background:#1e293b; border-radius:1rem; padding:2rem; box-shadow:0 0 20px rgba(0,0,0,.3); border:2px solid transparent; animation: borderGlow 2s linear infinite; }
@keyframes borderGlow { 0% { border-color:#38bdf8; } 25% { border-color:#a855f7; } 50% { border-color:#22c55e; } 75% { border-color:#f97316; } 100% { border-color:#38bdf8; } }
.spinner { border:4px solid rgba(255,255,255,0.1); border-top:4px solid #38bdf8; border-radius:50%; width:40px; height:40px; animation: spin 1s linear infinite; margin:auto; }
@keyframes spin {from{transform:rotate(0deg);}to{transform:rotate(360deg);}}
button,input{outline:none;}
pre{background:#0f172a;padding:1rem;border-radius:.75rem;overflow-x:auto;color:#e2e8f0;}
</style>
</head>
<body class="flex flex-col items-center justify-center min-h-screen px-4">
  <h1 class="text-4xl font-bold mb-1 text-blue-400">NEON OSINT 🔍</h1>
  <h3 class="text-gray-400 mb-6 text-lg">Number to Information Tool</h3>
  <div class="card w-full max-w-lg">
    <form id="lookupForm" class="flex flex-col gap-4 mt-4">
      <input id="number" name="number" class="w-full p-3 rounded-lg bg-slate-700 text-white" placeholder="Enter Number. (Ex/~ +911234567890)" required>
      <button type="submit" class="bg-blue-600 hover:bg-blue-700 transition text-white font-semibold py-2 rounded-lg">Search</button>
    </form>
    <div id="loading" class="hidden mt-6 flex flex-col items-center gap-2">
      <div class="spinner"></div>
      <p class="text-gray-400">Fetching data Please wait...</p>
    </div>
    <div id="result" class="mt-6 hidden">
      <div class="flex justify-between items-center mb-2 gap-2">
        <h2 class="text-lg font-semibold">Result:</h2>
        <div class="flex gap-2">
          <button id="copyBtn" class="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-white text-sm hidden">Copy DATA</button>
          <button id="downloadBtn" class="bg-purple-600 hover:bg-purple-700 px-3 py-1 rounded text-white text-sm hidden">Download DATA</button>
        </div>
      </div>
      <pre id="output"></pre>
    </div>
  </div>
  <p class="mt-6 text-gray-500 text-sm">© Vishwas OSINT Tool™ </p>
<script>
const form=document.getElementById("lookupForm");
const output=document.getElementById("output");
const result=document.getElementById("result");
const copyBtn=document.getElementById("copyBtn");
const downloadBtn=document.getElementById("downloadBtn");
const loading=document.getElementById("loading");
form.addEventListener("submit",async(e)=>{
  e.preventDefault();
  const number=document.getElementById("number").value.trim();
  result.classList.add("hidden");
  loading.classList.remove("hidden");
  copyBtn.classList.add("hidden");
  downloadBtn.classList.add("hidden");
  try{
    const res=await fetch("/lookup",{
      method:"POST",
      headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body:`number=${encodeURIComponent(number)}`
    });
    const data=await res.json();
    const finalData={ "Details by":"Neon OSINT", ...data };
    const formatted=JSON.stringify(finalData,null,2);
    output.textContent=formatted;
    loading.classList.add("hidden");
    result.classList.remove("hidden");
    copyBtn.classList.remove("hidden");
    downloadBtn.classList.remove("hidden");
  }catch(err){
    output.textContent="Error fetching data.";
    loading.classList.add("hidden");
    result.classList.remove("hidden");
  }
});
copyBtn.addEventListener("click",()=>{
  navigator.clipboard.writeText(output.textContent)
    .then(()=>{
      copyBtn.textContent="Copied!";
      setTimeout(()=>copyBtn.textContent="Copy JSON",2000);
    });
});
downloadBtn.addEventListener("click",()=>{
  const blob=new Blob([output.textContent],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  const a=document.createElement("a");
  a.href=url; a.download="neon_osint_result.json";
  a.click(); URL.revokeObjectURL(url);
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(SITE_HTML)

@app.route("/lookup", methods=["POST"])
def lookup():
    raw = request.form.get("number", "")
    num = normie_num(raw)
    if not num:
        return jsonify({"error": "Invalid number format"}), 400
    if not api_url:
        return jsonify({"error": "API backend not configured"}), 500

    url = api_url.format(num=num)
    try:
        r = http.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Channel" in data:
            del data["Channel"]
        if (data is None) or (isinstance(data, dict) and not data) or (isinstance(data, list) and len(data) == 0):
            return jsonify({"error": "No data found"}), 404
        return jsonify(data)
    except requests.exceptions.Timeout:
        return jsonify({"error": "The Neon OSINT server may be busy. Please try again.."}), 504
    except requests.exceptions.RequestException:
        return jsonify({"error": "The Neon OSINT server may be busy. Please try again.."}), 504

@app.route("/number-to-info", methods=["GET"])
def number_to_info():
    key = request.args.get("apikey", "")
    raw_number = request.args.get("number", "")

    if not key:
        return jsonify({"error": "Missing apikey"}), 400
    if not raw_number:
        return jsonify({"error": "Missing number parameter"}), 400

    doc = get_key_doc(key)
    if not doc or not doc.get("active", False):
        return jsonify({"error": "Invalid or inactive API key"}), 401

    now = datetime.datetime.datetime.utcnow() if hasattr(datetime, "datetime") else datetime.utcnow()
    exp = doc.get("expires_at")
    if isinstance(exp, str):
        try:
            exp = datetime.datetime.fromisoformat(exp)
        except Exception:
            exp = None

    if exp and exp < now:
        keys_col.update_one({"key": key}, {"$set": {"active": False}})
        return jsonify({"error": "The api key is expired, DM @UseSir for new api key"}), 401

    # use raw_number directly for speed (no normalization)
    num = raw_number

    if not api_url:
        return jsonify({"error": "API backend not configured"}), 500

    url = api_url.format(num=num)
    try:
        r = http.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Channel" in data:
            del data["Channel"]
        if (data is None) or (isinstance(data, dict) and not data) or (isinstance(data, list) and len(data) == 0):
            return jsonify({"error": "No data found. Details By: @UseSir"}), 404

        if isinstance(data, dict):
            data_with_desc = dict(data)
            data_with_desc["Description"] = "Details By: @UseSir"
        else:
            data_with_desc = {"items": data, "Description": "Details By: @UseSir"}

        wrapped = {
            "Owner": "@UseSir",
            "data": data_with_desc
        }
        return jsonify(wrapped)
    except requests.exceptions.Timeout:
        return jsonify({"error": "Server is busy, please try again later. Details By: @UseSir"}), 504
    except requests.exceptions.RequestException:
        return jsonify({"error": "Upstream API error. Contact @UseSir for support."}), 502

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.root_path, "static/icons"), "favicon.ico", mimetype="image/vnd.microsoft.icon")

bot = None
if bot_token:
    bot = telebot.TeleBot(bot_token)

def is_admin(uid: int):
    return admin_id and uid == admin_id

def build_public_base():
    if public_url:
        return public_url.rstrip("/")
    if host in ("0.0.0.0", "127.0.0.1"):
        return f"http://localhost:{port}"
    return f"http://{host}:{port}"

if bot and public_url:
    @app.route(f"/telegram_webhook/{bot_token}", methods=["POST"])
    def telegram_webhook():
        json_data = request.get_json(force=True)
        if not json_data:
            return "", 400
        try:
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
        except Exception:
            pass
        return "", 200

if bot:
    @bot.message_handler(commands=['help'])
    def handle_help(message):
        bot.send_message(message.chat.id, "Commands:\n/genkey <name> <days>\n/list\n/rework <name>\n/delkey <key-or-name>\n/help")

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        bot.send_message(message.chat.id, "welcome @UseSir \nbot is Alice, Use /help for commands")

    @bot.message_handler(commands=['list'])
    def handle_list(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "Unauthorized.")
            return
        docs = list_keys_serialized()
        if not docs:
            bot.reply_to(message, "No keys found.")
            return
        lines = []
        for d in docs:
            lines.append(f"Name: {d.get('name')} | Key: `{d.get('key')}` | Expires: {d.get('expires_at')} | Active: {d.get('active')}")
        text = "\n".join(lines)
        chunk_size = 3500
        for i in range(0, len(text), chunk_size):
            bot.send_message(message.chat.id, text[i:i+chunk_size], parse_mode='Markdown')

    @bot.message_handler(commands=['genkey'])
    def handle_genkey(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "Unauthorized.")
            return
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "Usage: /genkey <name> <days>")
            return
        name = parts[1]
        try:
            days = int(parts[2])
        except ValueError:
            bot.reply_to(message, "Days must be an integer.")
            return
        doc = create_key(name, days)
        exp = doc.get("expires_at")
        exp_s = exp.strftime("%Y-%m-%d %H:%M UTC") if isinstance(exp, datetime.datetime) else str(exp)
        base = build_public_base()
        api_full = f"{base}/number-to-info?apikey={doc.get('key')}&number=<num>"
        example = f"{base}/number-to-info?apikey={doc.get('key')}&number=9123456789"
        msg = (
            f"Key generated for `{name}`\n\n"
            f"Key: `{doc.get('key')}`\n"
            f"Expires: {exp_s}\n\n"
            f"API Format:\n{api_full}\n\n"
            f"Example:\n{example}\n"
        )
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')

    @bot.message_handler(commands=['rework'])
    def handle_rework(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "Unauthorized.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /rework <name>")
            return
        name = parts[1]
        deactivated = revoke_by_name(name)
        doc = create_key(name, 30)
        exp = doc.get("expires_at")
        exp_s = exp.strftime("%Y-%m-%d %H:%M UTC") if isinstance(exp, datetime.datetime) else str(exp)
        base = build_public_base()
        api_example_link = f"{base}/number-to-info?apikey={doc.get('key')}&number=9123456789"
        curl_example = f"curl \"{base}/number-to-info?apikey={doc.get('key')}&number=9123456789\""
        msg = (
            f"Reworked `{name}`\n\n"
            f"Deactivated: {deactivated} key(s)\n"
            f"New Key: `{doc.get('key')}`\n"
            f"Expires: {exp_s}\n\n"
            f"API (GET): {api_example_link}\n\n"
            f"curl example:\n{curl_example}\n"
        )
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')

    @bot.message_handler(commands=['delkey'])
    def handle_delkey(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "Unauthorized.")
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "Usage: /delkey <key-or-name>")
            return
        target = parts[1].strip()
        res_key = keys_col.delete_one({"key": target})
        if res_key.deleted_count:
            bot.send_message(message.chat.id, f"Deleted key `{target}` (1 key removed).", parse_mode='Markdown')
            handle_list(message)
            return
        res_name = keys_col.delete_many({"name": target})
        if res_name.deleted_count:
            bot.send_message(message.chat.id, f"Deleted {res_name.deleted_count} key(s) with name `{target}`.", parse_mode='Markdown')
            handle_list(message)
        else:
            bot.send_message(message.chat.id, "No matching key or name found.", parse_mode='Markdown')

def start_bot_polling():
    if not bot:
        return
    def target():
        try:
            bot.polling(non_stop=True)
        except Exception:
            pass
    t = threading.Thread(target=target, daemon=True)
    t.start()

def set_webhook_if_configured():
    if not bot or not public_url:
        return
    webhook_url = f"{public_url.rstrip('/')}/telegram_webhook/{bot_token}"
    try:
        bot.remove_webhook()
        bot.set_webhook(webhook_url)
    except Exception:

        pass

if __name__ == "__main__":
    ascii_art = pyfiglet.figlet_format("INDia", font="isometric1")
    print(ascii_art)
    set_webhook_if_configured()
    if start_bot_env == "1":
        start_bot_polling()
    app.run(host=host, port=port, threaded=True)
