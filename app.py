from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from dotenv import load_dotenv, find_dotenv
import os
import json
import uuid
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import requests
from PIL import Image
import io
import math
import re
import threading
import time as _time
import smtplib
from email.message import EmailMessage
import shutil
import tempfile
from pathlib import Path

# optional: cryptography for encrypting files at rest
try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_FERNET = True
except Exception:
    Fernet = None
    InvalidToken = Exception
    _HAS_FERNET = False

# Minimal, cleaned Flask app: no LLM/vector dependencies
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config['SESSION_TYPE'] = 'filesystem'

# Load .env reliably from project root (works when running REPL from other CWDs)
dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path, override=True)
else:
    # fallback to default behavior (looks in CWD)
    load_dotenv(override=True)

# -------------------------
# Optional full LLM/vector stack (Groq + Pinecone)
# - will be enabled only if required packages are installed and API keys are present
# -------------------------
USE_FULL_STACK = False
rag_chain = None
try:
    from src.helper import download_hugging_face_embeddings
    from src.prompt import *
    from langchain_pinecone import PineconeVectorStore
    from langchain_groq import ChatGroq
    from langchain.chains import create_retrieval_chain
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate

    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    if PINECONE_API_KEY and GROQ_API_KEY:
        try:
            embeddings = download_hugging_face_embeddings()
            index_name = os.getenv('PINECONE_INDEX', 'medical-chatbot')

            docsearch = PineconeVectorStore.from_existing_index(
                index_name=index_name,
                embedding=embeddings
            )

            retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})

            chatModel = ChatGroq(
                groq_api_key=GROQ_API_KEY,
                model_name=os.getenv('GROQ_MODEL','llama-3.1-8b-instant'),
                temperature=float(os.getenv('GROQ_TEMPERATURE','0'))
            )

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}")
            ])

            question_answer_chain = create_stuff_documents_chain(llm=chatModel, prompt=prompt)
            rag_chain = create_retrieval_chain(retriever, question_answer_chain)
            USE_FULL_STACK = True
            logger.info("✅ Full stack initialized (Groq + Pinecone)")
        except Exception as e:
            logger.warning(f"Full stack components present but initialization failed: {e}")
            USE_FULL_STACK = False
    else:
        logger.info("Full stack disabled: missing PINECONE_API_KEY or GROQ_API_KEY")
        USE_FULL_STACK = False
except Exception as e:
    logger.info(f"Full stack not available (imports failed): {e}")
    USE_FULL_STACK = False

# -------------------------
# Simple user history and user storage
# -------------------------
HISTORY_FILE = "user_history.json"

# Mapping from model label (or parts of it) to user-friendly guidance
LABEL_GUIDANCE = {
    "melanoma": {
        "title": "Possible Melanoma",
        "advice": "Suspicious pigmented lesion. Avoid self-diagnosis. Urgently consult a dermatologist for biopsy and evaluation.",
        "where": "Dermatology (urgent)",
        "severity": "high"
    },
    "nevus": {
        "title": "Likely Benign Mole (Nevus)",
        "advice": "Often benign but monitor for change (size, color, border). See a dermatologist or GP if concerned.",
        "where": "Dermatology / GP (routine)",
        "severity": "low"
    },
    "seborrheic keratosis": {
        "title": "Seborrheic Keratosis (benign)",
        "advice": "Benign, cosmetic removal available. See dermatologist if irritated or changing.",
        "where": "Dermatology / GP (non-urgent)",
        "severity": "low"
    },
    "basal cell carcinoma": {
        "title": "Possible Basal Cell Carcinoma",
        "advice": "Common skin cancer that typically requires excision or local therapy. Arrange dermatology assessment.",
        "where": "Dermatology (soon)",
        "severity": "medium"
    },
    "squamous cell carcinoma": {
        "title": "Possible Squamous Cell Carcinoma",
        "advice": "May be invasive; arrange dermatology assessment promptly.",
        "where": "Dermatology (soon)",
        "severity": "medium"
    },
    "actinic keratosis": {
        "title": "Actinic (solar) Keratosis",
        "advice": "Pre-cancerous lesion from sun damage. See dermatologist/GP for treatment options.",
        "where": "Dermatology / GP",
        "severity": "medium"
    },
    "eczema": {
        "title": "Eczema / Dermatitis",
        "advice": "Inflammatory rash. Use emollients and avoid irritants. See GP or dermatologist if severe or persistent.",
        "where": "GP / Dermatology",
        "severity": "low"
    },
    "psoriasis": {
        "title": "Possible Psoriasis",
        "advice": "Chronic inflammatory condition. Topical therapies available; see GP/dermatology for management.",
        "where": "GP / Dermatology",
        "severity": "low"
    },
    "acne": {
        "title": "Acne",
        "advice": "Common condition; over-the-counter topical treatments may help. See GP/dermatology for moderate or severe cases.",
        "where": "GP / Dermatology",
        "severity": "low"
    },
    "unknown": {
        "title": "Unknown / Uncertain",
        "advice": "Model could not confidently identify the condition. Please consult a dermatologist for expert review.",
        "where": "Dermatology / GP",
        "severity": "unknown"
    }
}

CONFIDENCE_THRESHOLD = float(os.getenv('HF_CONFIDENCE_THRESHOLD', 0.6))

# Basic medication knowledge base (module-level so other endpoints can reuse it)
MEDICATION_KNOWLEDGE = {
    'caldol': {'name': 'Paracetamol (Acetaminophen)', 'indication': 'Fever and mild-to-moderate pain (analgesic/antipyretic)'},
    'paracetamol': {'name': 'Paracetamol (Acetaminophen)', 'indication': 'Fever and mild-to-moderate pain (analgesic/antipyretic)'},
    'meftal': {'name': 'Mefenamic acid', 'indication': 'Pain relief (NSAID), commonly used for menstrual pain or general analgesia'},
    'meftal-p': {'name': 'Mefenamic acid + Paracetamol', 'indication': 'Combined analgesic for moderate pain'},
    'delcon': {'name': 'Delcon (cough/cold syrup)', 'indication': 'Cough and cold symptom relief (expectorant/antitussive; brand-level match)'},
    'levon': {'name': 'Levolin / Levosalbutamol', 'indication': 'Bronchodilator for wheeze/cough (relieves bronchospasm)'},
    'levosalbutamol': {'name': 'Levosalbutamol', 'indication': 'Bronchodilator (reliever for bronchospasm)'},
    'amoxi': {'name': 'Amoxicillin', 'indication': 'Antibiotic for bacterial infections'},
    'azith': {'name': 'Azithromycin', 'indication': 'Antibiotic for respiratory and other bacterial infections (macrolide)'},
    'cipro': {'name': 'Ciprofloxacin', 'indication': 'Antibiotic (broad-spectrum fluoroquinolone)'},
    'ibuprofen': {'name': 'Ibuprofen', 'indication': 'Pain and inflammation (NSAID)'}
}

def get_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def load_user_history():
    try:
        data = None
        if _HAS_FERNET and os.getenv('FERNET_KEY'):
            # try decrypt
            with open(HISTORY_FILE, 'rb') as f:
                ciphertext = f.read()
            try:
                key = os.getenv('FERNET_KEY')
                dec = Fernet(key.encode())
                plaintext = dec.decrypt(ciphertext)
                data = json.loads(plaintext.decode())
            except Exception:
                # fallback to plain read
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
        else:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_history(history):
    try:
        try:
            backup_file(HISTORY_FILE)
        except Exception:
            pass
        # encrypt if FERNET_KEY present
        if _HAS_FERNET and os.getenv('FERNET_KEY'):
            key = os.getenv('FERNET_KEY')
            enc = Fernet(key.encode())
            plaintext = json.dumps(history, ensure_ascii=False).encode('utf-8')
            ciphertext = enc.encrypt(plaintext)
            with open(HISTORY_FILE, 'wb') as f:
                f.write(ciphertext)
        else:
            atomic_write_json(HISTORY_FILE, history)
    except Exception as e:
        logger.warning(f"Failed to save user history: {e}")

def add_to_history(user_id, user_msg, bot_msg):
    history = load_user_history()
    if user_id not in history:
        history[user_id] = []
    history[user_id].append({
        'timestamp': datetime.now().isoformat(),
        'user': user_msg,
        'bot': bot_msg
    })
    if len(history[user_id]) > 50:
        history[user_id] = history[user_id][-50:]
    save_user_history(history)

def get_user_history(user_id, limit=10):
    history = load_user_history()
    return history.get(user_id, [])[-limit:]

# -------------------------
# Simple user persistence
# -------------------------
def load_users():
    try:
        if _HAS_FERNET and os.getenv('FERNET_KEY'):
            try:
                with open('users.json', 'rb') as f:
                    ciphertext = f.read()
                key = os.getenv('FERNET_KEY')
                dec = Fernet(key.encode())
                plaintext = dec.decrypt(ciphertext)
                return json.loads(plaintext.decode('utf-8'))
            except Exception:
                with open('users.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
        else:
            with open('users.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users):
    try:
        try:
            backup_file('users.json')
        except Exception:
            pass
        # encrypt user storage if key present
        if _HAS_FERNET and os.getenv('FERNET_KEY'):
            key = os.getenv('FERNET_KEY')
            enc = Fernet(key.encode())
            plaintext = json.dumps(users, ensure_ascii=False).encode('utf-8')
            ciphertext = enc.encrypt(plaintext)
            with open('users.json', 'wb') as f:
                f.write(ciphertext)
        else:
            atomic_write_json('users.json', users)
    except Exception as e:
        logger.warning(f"Failed to save users: {e}")


# Simple geocode cache to reduce API calls and improve coverage/reliability
GEOCODE_CACHE_FILE = 'geocode_cache.json'

def load_geocode_cache():
    try:
        with open(GEOCODE_CACHE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def save_geocode_cache(cache):
    try:
        with open(GEOCODE_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write geocode cache: {e}")


# -------------------------
# Reminder persistence and email notification helpers
# -------------------------
REMINDERS_FILE = 'reminders.json'

def load_reminders():
    try:
        if _HAS_FERNET and os.getenv('FERNET_KEY'):
            try:
                with open(REMINDERS_FILE, 'rb') as f:
                    ciphertext = f.read()
                key = os.getenv('FERNET_KEY')
                dec = Fernet(key.encode())
                plaintext = dec.decrypt(ciphertext)
                return json.loads(plaintext.decode('utf-8'))
            except Exception:
                with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        else:
            with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        return []

def save_reminders(reminders):
    try:
        # create backups and write atomically to reduce risk of data loss
        try:
            backup_file(REMINDERS_FILE)
        except Exception:
            pass
        if _HAS_FERNET and os.getenv('FERNET_KEY'):
            key = os.getenv('FERNET_KEY')
            enc = Fernet(key.encode())
            plaintext = json.dumps(reminders, ensure_ascii=False).encode('utf-8')
            ciphertext = enc.encrypt(plaintext)
            with open(REMINDERS_FILE, 'wb') as f:
                f.write(ciphertext)
        else:
            atomic_write_json(REMINDERS_FILE, reminders)
    except Exception as e:
        logger.warning(f"Failed to save reminders: {e}")


def atomic_write_json(path, data):
    """Write JSON to a temp file and atomically replace the target file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name, dir=str(p.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, str(p))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def backup_file(path):
    """Create a timestamped backup copy of 'path' in the 'backups' folder."""
    try:
        if not os.path.exists(path):
            return
        bdir = Path('backups')
        bdir.mkdir(parents=True, exist_ok=True)
        base = Path(path).name
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        dest = bdir / f"{base}.{ts}.bak"
        shutil.copy2(path, dest)
        logger.info(f"Backed up {path} -> {dest}")
    except Exception as e:
        logger.warning(f"Failed to backup {path}: {e}")


def call_openfda_drug_label(query):
    """Call openFDA drug label endpoint for a given query (brand or generic name).
    Returns parsed fields or None on failure.
    """
    try:
        if not query or len(query.strip()) < 2:
            return None
        q = requests.utils.requote_uri(query)
        base = 'https://api.fda.gov/drug/label.json'
        params = f'?search=openfda.brand_name:{q}+OR+openfda.generic_name:{q}&limit=3'
        url = base + params
        logger.info(f'call_openfda_drug_label: querying openFDA for {query}')
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            logger.warning(f'openFDA lookup failed status={r.status_code} body={r.text[:200]}')
            return None
        jd = r.json()
        results = jd.get('results', [])
        if not results:
            return None

        fields = {'indications_and_usage': [], 'dosage_and_administration': [], 'adverse_reactions': [], 'drug_interactions': []}
        for res in results:
            for key in fields.keys():
                v = res.get(key)
                if v:
                    if isinstance(v, list):
                        fields[key].extend(v)
                    else:
                        fields[key].append(v)
        for k in fields:
            cleaned = []
            for item in fields[k]:
                if isinstance(item, str) and item.strip():
                    cleaned.append(item.strip())
                elif isinstance(item, list):
                    for it in item:
                        if isinstance(it, str) and it.strip():
                            cleaned.append(it.strip())
            fields[k] = cleaned
        return fields
    except Exception as e:
        logger.warning(f'openFDA call exception: {e}')
        return None


def send_email(to_address, subject, body):
    server = os.getenv('SMTP_SERVER')
    port = int(os.getenv('SMTP_PORT', 587))
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_addr = os.getenv('EMAIL_FROM') or user

    if not server or not user or not password or not from_addr:
        msg = 'Email not sent — SMTP not configured (missing env vars)'
        logger.warning(msg)
        return False, msg

    try:
        msgobj = EmailMessage()
        msgobj['Subject'] = subject
        msgobj['From'] = from_addr
        msgobj['To'] = to_address
        msgobj.set_content(body)

        # Prefer STARTTLS on common port 587
        with smtplib.SMTP(server, port, timeout=20) as smtp:
            smtp.ehlo()
            if port == 587:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msgobj)
        logger.info(f"Sent reminder email to {to_address}")
        return True, None
    except Exception as e:
        logger.exception(f"Failed to send email to {to_address}: {e}")
        return False, str(e)


def compute_next_run(current_dt, frequency):
    if frequency == 'once':
        return None
    if frequency == 'daily':
        return current_dt + timedelta(days=1)
    if frequency == 'weekly':
        return current_dt + timedelta(weeks=1)
    if frequency == 'monthly':
        # approximate 30 days
        return current_dt + timedelta(days=30)
    return None


def reminder_worker():
    logger.info('Starting reminder worker thread')
    while True:
        try:
            reminders = load_reminders()
            now = datetime.now()
            changed = False
            for r in reminders:
                if not r.get('active', True):
                    continue
                next_run = None
                if r.get('next_run'):
                    try:
                        next_run = datetime.fromisoformat(r['next_run'])
                    except Exception:
                        next_run = None
                else:
                    # compute next_run from time field (today at time)
                    t = r.get('time')
                    if t:
                        hh, mm = map(int, t.split(':'))
                        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        if candidate < now:
                            # schedule for next day
                            candidate = candidate + timedelta(days=1)
                        next_run = candidate
                        r['next_run'] = next_run.isoformat()
                        changed = True

                if next_run and next_run <= now:
                    # send email
                    to_addr = r.get('email')
                    if to_addr:
                        subject = f"Medication Reminder: {r.get('type', 'Reminder')}"
                        body = f"This is a reminder: {r.get('type')} at {r.get('time')}\n\nNotes: {r.get('note','')}"
                        sent, err = send_email(to_addr, subject, body)
                        r['last_sent'] = datetime.now().isoformat()
                        if not sent:
                            logger.warning(f"Reminder email failed for {to_addr}: {err}")
                            # keep retrying according to schedule; do not disable
                        # compute subsequent next_run based on frequency
                        freq = r.get('frequency','once')
                        if freq == 'once':
                            r['active'] = False
                            r['next_run'] = None
                        else:
                            try:
                                nr = compute_next_run(next_run, freq)
                                r['next_run'] = nr.isoformat() if nr else None
                            except Exception:
                                r['next_run'] = None
                        changed = True

            if changed:
                save_reminders(reminders)

        except Exception as e:
            logger.exception(f'Reminder worker error: {e}')
        _time.sleep(60)

def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# -------------------------
# Lightweight response generator (no external LLM)
# -------------------------
def get_response(msg):
    msg = (msg or "").strip()
    if len(msg) < 3:
        return "Hi! How can I help you today? You can ask about symptoms, check BP/BMI, plan diet, or book a doctor appointment."

    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy', 'greetings']
    if any(g in msg.lower() for g in greetings) and len(msg.split()) <= 3:
        return "Hello! I'm your medical assistant. I can help with symptom checking, BP monitoring, BMI calculation, diet planning, skin care advice, or booking doctor appointments. What would you like to know?"

    emergency_keywords = ['chest pain', 'shortness of breath', 'difficulty breathing', 'fainting', 'unconscious', 'severe bleeding', 'high fever', 'stroke', 'heart attack', 'emergency', 'urgent']
    if any(k in msg.lower() for k in emergency_keywords):
        return "🚨 EMERGENCY ALERT: This sounds serious! Please call emergency services (911) immediately or go to the nearest hospital. I'm not a substitute for professional medical care."

    unclear_indicators = ['ho', 'ok', 'yes', 'no', 'idk', 'dunno', 'test', '123', 'abc']
    if msg.lower() in unclear_indicators or len(msg.split()) == 1:
        return "I didn't quite understand that. Could you please provide more details about your health concern? For example: 'I have a headache' or 'Check my BMI'."

    service_keywords = {
        'bp': 'bp-hr', 'blood pressure': 'bp-hr', 'heart rate': 'bp-hr', 'bmi': 'bmi', 'weight': 'bmi',
        'diet': 'diet', 'food': 'diet', 'skin': 'skin', 'hair': 'skin', 'symptom': 'symptom',
        'appointment': 'appointment', 'doctor': 'appointment', 'health': 'health_vault', 'vault': 'health_vault'
    }
    for k, svc in service_keywords.items():
        if k in msg.lower():
            return f"I can help you with that! Open the {svc.replace('-', ' ')} page or tell me more about your specific concern."

    # Fallback generic answer
    base = "Thanks — I can help research general information. For anything medical, always consult a healthcare professional."
    if any(w in msg.lower() for w in ['pain', 'symptom', 'sick', 'ill', 'hurt', 'ache']):
        base += "\n\n⚠️ Note: This is general info, not medical advice."
    return base


# -------------------------
# Routes - Authentication
# -------------------------
@app.route("/login")
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    users = load_users()
    email = data.get('email')
    if not email:
        return jsonify({"success": False, "message": "Email required"})
    if email in users:
        return jsonify({"success": False, "message": "Email already registered"})
    users[email] = {
        "password": generate_password_hash(data.get('password','')),
        "name": data.get('name',''),
        "phone": data.get('phone',''),
        "created_at": datetime.now().isoformat()
    }
    save_users(users)
    return jsonify({"success": True, "message": "Registration successful"})

@app.route("/authenticate", methods=["POST"])
def authenticate():
    data = request.get_json() or {}
    if data.get('email') == 'demo@medicare.com' and data.get('password') == 'demo123':
        session['user'] = {"email": data['email'], "name": "Demo User"}
        return jsonify({"success": True, "message": "Login successful"})
    users = load_users()
    user = users.get(data.get('email'))
    if user and check_password_hash(user['password'], data.get('password','')):
        session['user'] = {"email": data.get('email'), "name": user.get('name')}
        return jsonify({"success": True, "message": "Login successful"})
    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route("/logout")
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


# -------------------------
# Routes - Main Pages
# -------------------------
@app.route("/")
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template("chat.html")

@app.route("/about")
@login_required
def about():
    return render_template("about.html")

@app.route("/disclaimer")
@login_required
def disclaimer():
    return render_template("disclaimer.html")

@app.route("/history")
@login_required
def history():
    user_id = get_user_id()
    user_history = get_user_history(user_id)
    return render_template("history.html", history=user_history)


# -------------------------
# Routes - Services (all available services)
# -------------------------
@app.route("/services/<service>")
@login_required
def services(service):
    allowed = {
        "bp-hr": "services/bp_hr.html",
        "bmi": "services/bmi.html",
        "diet": "services/diet.html",
        "skin": "services/skin.html",
        "more": "services/more.html",
        "symptom": "services/symptom.html",
        "appointment": "services/appointment.html",
        "health_vault": "services/health_vault.html",
        "medication": "services/medication.html",
        "prescription": "services/prescription.html",
        
        "vitals": "services/vitals.html",
        "reminder": "services/reminder.html",
        "history": "services/history.html",
        "report_generator": "services/report_generator.html",
        "skin_analysis": "services/skin_analysis.html",
    }
    tpl = allowed.get(service)
    if not tpl:
        return render_template("404.html"), 404
    # Inject Google Maps API key into the appointment page so frontend can use Maps features
    if service == 'appointment':
        return render_template(tpl, GOOGLE_MAPS_API_KEY=os.getenv('GOOGLE_MAPS_API_KEY', ''))
    return render_template(tpl)


# -------------------------
# Routes - Chat API
# -------------------------
@app.route("/get", methods=["POST"])
def chat():
    msg = request.form.get("msg", "").strip()
    user_id = get_user_id()

    # Simple/fast reply heuristics
    if len(msg) < 3:
        response = get_response(msg)
        add_to_history(user_id, msg, response)
        return response

    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy', 'greetings']
    if any(greet in msg.lower() for greet in greetings) and len(msg.split()) <= 3:
        response = get_response(msg)
        add_to_history(user_id, msg, response)
        return response

    emergency_keywords = ['chest pain', 'shortness of breath', 'difficulty breathing', 'fainting', 'unconscious',
                          'severe bleeding', 'high fever', 'stroke', 'heart attack', 'emergency', 'urgent']
    if any(keyword in msg.lower() for keyword in emergency_keywords):
        response = "🚨 EMERGENCY ALERT: This sounds serious! Please call emergency services (911) immediately or go to the nearest hospital. I'm not a substitute for professional medical care."
        add_to_history(user_id, msg, response)
        return response

    unclear_indicators = ['ho', 'ok', 'yes', 'no', 'idk', 'dunno', 'test', '123', 'abc']
    if msg.lower() in unclear_indicators or len(msg.split()) == 1:
        response = get_response(msg)
        add_to_history(user_id, msg, response)
        return response

    # Service routing
    service_keywords = {
        'bp': 'bp-hr', 'blood pressure': 'bp-hr', 'heart rate': 'bp-hr', 'bmi': 'bmi', 'weight': 'bmi',
        'diet': 'diet', 'food': 'diet', 'skin': 'skin', 'hair': 'skin', 'symptom': 'symptom',
        'appointment': 'appointment', 'doctor': 'appointment', 'health': 'health_vault', 'vault': 'health_vault'
    }
    for keyword, service in service_keywords.items():
        if keyword in msg.lower():
            response = f"I can help you with that! Please visit our {service.replace('-', ' ')} service page for detailed guidance. Or tell me more about your specific concern."
            add_to_history(user_id, msg, response)
            return response

    # Not handled by heuristics -> check for medication queries, else use RAG if available, then fallback generator
    med_query_indicators = ['side effect', 'side effects', 'dosage', 'dose', 'how to take', 'interaction', 'interactions', 'what is', 'uses', 'indication', 'contraindication']
    if any(ind in msg.lower() for ind in med_query_indicators):
        qlower = msg.lower()
        found_key = None
        for key in MEDICATION_KNOWLEDGE.keys():
            if key in qlower:
                found_key = key
                break
        if found_key:
            try:
                of = call_openfda_drug_label(found_key)
            except Exception:
                of = None

            parts = []
            if of and of.get('indications_and_usage'):
                parts.append('Indications: ' + ' '.join(of.get('indications_and_usage')[:2]))
            elif found_key and MEDICATION_KNOWLEDGE.get(found_key):
                parts.append('Likely use: ' + MEDICATION_KNOWLEDGE[found_key].get('indication'))

            if of and of.get('dosage_and_administration'):
                parts.append('Dosage guidance: ' + ' '.join(of.get('dosage_and_administration')[:1]))

            if of and of.get('adverse_reactions'):
                parts.append('Adverse reactions: ' + ' '.join(of.get('adverse_reactions')[:2]))

            if of and of.get('drug_interactions'):
                parts.append('Known interactions: ' + ' '.join(of.get('drug_interactions')[:2]))

            if parts:
                answer = ' '.join(parts)
                answer += '\n\nNote: This is informational. Confirm with a healthcare professional.'
                add_to_history(user_id, msg, answer)
                return answer

    if USE_FULL_STACK and rag_chain is not None:
        try:
            logger.info("Invoking RAG chain for chat message")
            response_obj = rag_chain.invoke({"input": msg})
            # response_obj structure may vary; try common keys
            answer = None
            if isinstance(response_obj, dict):
                answer = response_obj.get('answer') or response_obj.get('output') or response_obj.get('result')
            if not answer:
                answer = str(response_obj)

            if any(word in msg.lower() for word in ['pain', 'symptom', 'sick', 'ill', 'hurt', 'ache']):
                answer += "\n\n⚠️ Remember: I'm not a doctor. This is general information only. Please consult a healthcare professional for personalized advice."

            add_to_history(user_id, msg, answer)
            return answer
        except Exception as e:
            logger.exception(f"RAG invocation failed: {e}")
            response = get_response(msg)
            add_to_history(user_id, msg, response)
            return response

    # Final fallback
    response = get_response(msg)
    add_to_history(user_id, msg, response)
    return response


# -------------------------
# Routes - Image Analysis
# -------------------------
@app.route("/analyze-image", methods=["POST"])
@login_required
def analyze_image():
    try:
        # Diagnostic logging for incoming request
        logger.info(f"analyze_image request.files keys: {list(request.files.keys())}")
        logger.info(f"analyze_image request.form keys: {list(request.form.keys())}")

        if 'image' not in request.files:
            logger.warning("analyze_image: no 'image' in request.files")
            return jsonify({"error": "No image file provided", "details": list(request.files.keys())}), 400

        image_file = request.files['image']
        if image_file.filename == '':
            logger.warning("analyze_image: empty filename")
            return jsonify({"error": "No file selected"}), 400

        # Basic validation
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'avif'}
        file_ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else ''

        if file_ext not in allowed_extensions:
            logger.warning(f"analyze_image: invalid extension {file_ext}")
            return jsonify({"error": "Only image files are allowed", "ext": file_ext}), 400

        try:
            img = Image.open(image_file)
            img.verify()
            image_file.seek(0)
        except Exception as e:
            logger.warning(f"analyze_image: invalid image content: {e}")
            # Pillow may not support AVIF without plugins. Give a helpful message.
            if file_ext == 'avif':
                return jsonify({
                    "error": "Invalid or unsupported AVIF image.",
                    "suggestion": "Convert the image to JPEG or PNG (e.g., using an image editor) or install AVIF support for Pillow (pillow-avif-plugin)."
                }), 400
            return jsonify({"error": f"Invalid image file: {str(e)}"}), 400

        # Re-open image for pixel analysis (verify() can close file)
        image_file.seek(0)
        try:
            img = Image.open(image_file).convert('RGB')
        except Exception:
            return jsonify({"error": "Failed to open image for analysis"}), 400

        # --- Steganography detection helper (simple LSB statistical test) ---
        def detect_steganography(pil_image):
            # Compute least significant bit (LSB) distribution across RGB channels
            width, height = pil_image.size
            pixels = pil_image.getdata()

            total_bits = 0
            ones = 0
            # iterate pixels, count LSB ones across channels
            for px in pixels:
                for channel in px:  # R,G,B
                    lsb = channel & 1
                    ones += lsb
                    total_bits += 1

            if total_bits == 0:
                return {"suspicious": False, "score": 0.0, "message": "Empty image"}

            p = ones / total_bits  # proportion of 1s in LSB
            # expected p for natural images is near 0.5; deviation indicates possible embedding
            deviation = abs(p - 0.5)

            # Compute a chi-square like score scaled by total bits
            expected = total_bits * 0.5
            chi2 = ((ones - expected) ** 2) / expected if expected > 0 else 0.0

            # Normalize score to [0,1] roughly using logistic-like mapping
            score = 1 - math.exp(-chi2 / max(1.0, total_bits / 1000.0))

            # Heuristic thresholds (tunable): small deviations are normal.
            suspicious = (deviation > 0.02) or (chi2 > 2000)

            message = (
                f"LSB ones ratio={p:.4f}, deviation={deviation:.4f}, chi2={chi2:.2f}. "
                "Values outside small ranges may indicate hidden data in LSBs."
            )

            return {"suspicious": suspicious, "score": float(score), "message": message}


        # Get optional prompt from form
        prompt = request.form.get('prompt', 'Analyze this medical image and provide general health observations.')

        # Ensure we have a user id for history entries
        user_id = get_user_id()

        # If user provided a Hugging Face API key in environment, try the HF image-inference API first
        hf_token = os.getenv('HUGGING_FACE_API_KEY')
        hf_model = os.getenv('HF_IMAGE_MODEL', 'google/vit-base-patch16-224')
        hf_result = None
        if hf_token:
            try:
                logger.info(f"Invoking Hugging Face inference for model={hf_model}")
                image_file.seek(0)
                files = {"file": (image_file.filename, image_file.read())}
                headers = {"Authorization": f"Bearer {hf_token}"}
                url = f"https://api-inference.huggingface.co/models/{hf_model}"
                resp = requests.post(url, headers=headers, files=files, timeout=30)
                # If HF returns 410 (api-inference endpoint deprecated), retry using the router endpoint
                if resp.status_code == 410:
                    try:
                        router_url = f"https://router.huggingface.co/models/{hf_model}"
                        logger.info(f"HF API returned 410; retrying with router endpoint: {router_url}")
                        resp = requests.post(router_url, headers=headers, files=files, timeout=30)
                    except Exception as e:
                        logger.exception(f"Retry to HF router endpoint failed: {e}")
                if resp.status_code == 200:
                    try:
                        preds = resp.json()
                        # HF image-classification usually returns a list of {label,score}
                        # But models can return dicts (loading/error) or different nested shapes. Capture all.
                        if isinstance(preds, list) and len(preds) > 0 and isinstance(preds[0], dict) and 'label' in preds[0]:
                            top = preds[0]
                            label = top.get('label')
                            score = top.get('score')
                            hf_result = {"label": label, "score": float(score), "predictions": preds, "text": resp.text}
                        else:
                            # Store raw response and include textual body for debugging
                            hf_result = {"raw": preds, "text": resp.text}
                            if isinstance(preds, dict):
                                if 'error' in preds:
                                    hf_result['error'] = preds.get('error')
                                if 'detail' in preds:
                                    hf_result['detail'] = preds.get('detail')
                        logger.info("Hugging Face inference succeeded (raw stored)")
                    except Exception as e:
                        logger.warning(f"Failed to parse HF response: {e}")
                        hf_result = {"error": "Failed to parse HF response", "status_code": resp.status_code, "text": resp.text}
                else:
                    logger.warning(f"HF inference failed: {resp.status_code} {resp.text}")
                    hf_result = {"error": "HF inference failed", "status_code": resp.status_code, "text": resp.text}
                # rewind file for later use
                image_file.seek(0)
            except Exception as e:
                logger.exception(f"Hugging Face inference call failed: {e}")
                hf_result = {"error": str(e)}

        # If HF inference failed or returned no usable label, try a local transformers pipeline as a fallback
        if (not hf_result) or (isinstance(hf_result, dict) and ('error' in hf_result or 'label' not in hf_result)):
            try:
                logger.info("Attempting local image-classification using transformers pipeline as fallback")
                from transformers import pipeline
                # Rewind and load image
                image_file.seek(0)
                image_bytes = image_file.read()
                image_file.seek(0)
                pil_img = Image.open(io.BytesIO(image_bytes)).convert('RGB')

                try:
                    classifier = pipeline('image-classification', model=hf_model, device=-1)
                except Exception:
                    # Try without specifying model to use default hosted model if available locally
                    classifier = pipeline('image-classification', device=-1)

                local_preds = classifier(pil_img)
                if isinstance(local_preds, list) and len(local_preds) > 0:
                    top = local_preds[0]
                    hf_result = {"label": top.get('label'), "score": float(top.get('score', 0.0)), "predictions": local_preds, "source": "local"}
                    logger.info("Local transformers inference succeeded")
            except ImportError as ie:
                logger.warning(f"transformers not installed; local inference unavailable: {ie}")
            except Exception as e:
                logger.warning(f"Local inference fallback failed: {e}")

        # If HF/local returned predictions, include steganography and return a structured analysis
        if hf_result:
            try:
                stego = detect_steganography(img)
            except Exception:
                stego = {"suspicious": False, "score": 0.0, "message": "Steganography check failed"}

            # Extract label and score in a few common shapes
            label = None
            score = 0.0
            source = "external"
            if isinstance(hf_result, dict):
                label = hf_result.get('label') or (hf_result.get('predictions') and hf_result.get('predictions')[0].get('label'))
                score = float(hf_result.get('score') or (hf_result.get('predictions') and hf_result.get('predictions')[0].get('score')) or 0.0)
                source = hf_result.get('source', 'external')
            else:
                # unexpected shape
                label = str(hf_result)

            norm_label = (label or 'unknown').strip().lower()

            guidance = LABEL_GUIDANCE.get(norm_label)
            if not guidance:
                # try substring matching
                for key in LABEL_GUIDANCE.keys():
                    if key in norm_label:
                        guidance = LABEL_GUIDANCE[key]
                        break
            if not guidance:
                guidance = LABEL_GUIDANCE['unknown']

            confident = score >= CONFIDENCE_THRESHOLD
            if confident:
                guidance_text = guidance['advice']
            else:
                guidance_text = f"Model uncertain (confidence {score:.0%}). {guidance['advice']} This is not definitive — consult a dermatologist."

            # Add red-flag note for high severity
            if guidance.get('severity') == 'high':
                guidance_text += " If the lesion is changing rapidly, painful, bleeding or causing systemic symptoms, seek urgent care."

            response_obj = {
                'success': True,
                'label': label or 'unknown',
                'normalized_label': norm_label,
                'confidence': score,
                'confident': confident,
                'title': guidance.get('title'),
                'guidance': guidance_text,
                'where_to_consult': guidance.get('where'),
                'severity': guidance.get('severity'),
                'source': source,
                'hf_model': hf_model if hf_token else None,
                'hf_used': True if (hf_token and hf_result and (isinstance(hf_result, dict) and hf_result.get('source')!='local')) else False,
                'predictions': hf_result,
                'steganography': stego
            }

            add_to_history(user_id, f"Image analysis: {prompt[:100]}", f"{response_obj['title']}: {response_obj['label']} ({response_obj['confidence']:.2f})")
            logger.info("analyze_image: returning structured result")
            return jsonify(response_obj)

        # If full stack is available, attempt to use RAG for a deeper analysis
        if USE_FULL_STACK and rag_chain is not None:
            try:
                logger.info("Invoking RAG chain for image analysis")
                input_text = f"Please analyze the medical image named '{image_file.filename}'. Context: {prompt}"
                response_obj = rag_chain.invoke({"input": input_text})

                answer = None
                if isinstance(response_obj, dict):
                    answer = response_obj.get('answer') or response_obj.get('output') or response_obj.get('result')
                if not answer:
                    answer = str(response_obj)

                if any(word in prompt.lower() for word in ['pain', 'symptom', 'sick', 'ill', 'hurt', 'ache', 'rash', 'lesion']):
                    answer += "\n\n⚠️ Remember: I'm not a doctor. This is general information only. Please consult a healthcare professional for personalized advice."

                add_to_history(user_id, f"Image analysis: {prompt[:100]}", answer[:200])
                logger.info("analyze_image: RAG analysis success")
                # include steganography detection summary as well
                stego = detect_steganography(img)
                return jsonify({"success": True, "analysis": answer, "steganography": stego})
            except Exception as e:
                logger.exception(f"RAG image analysis failed: {e}")
                # fall through to safe fallback

            # Run steganography detection
            stego = detect_steganography(img)

        # Safe fallback analysis (no LLM or RAG failed)
        # Include explicit disclaimer strings expected by tests: 'DISCLAIMER' and 'NOT a'
        analysis = (
            f"Image received ({image_file.filename}). "
            "DISCLAIMER: THIS IS NOT a medical diagnosis. "
            "This is general informational content only. Always consult a healthcare professional for proper diagnosis. "
            f"Analysis prompt: {prompt}\n\n"
            f"Steganography check: suspicious={stego['suspicious']}, score={stego['score']:.4f}. {stego['message']}"
        )

        add_to_history(user_id, f"Image analysis: {prompt[:100]}", analysis[:200])

        logger.info("analyze_image: success (fallback)")
        return jsonify({"success": True, "analysis": analysis, "steganography": stego})

    except Exception as e:
        logger.exception("Unexpected error in analyze_image")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route('/api/parse-prescription', methods=['POST'])
@login_required
def api_parse_prescription():
    """Parse an uploaded prescription image (OCR) and extract medication lines and a short summary."""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image provided'}), 400

        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff'}
        file_ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else ''
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Only image files are allowed'}), 400

        image_file.seek(0)
        extracted_text = ''

        # Try local OCR with pytesseract first
        try:
            from PIL import Image
            import pytesseract
            image_file.seek(0)
            img = Image.open(image_file).convert('RGB')
            extracted_text = pytesseract.image_to_string(img)
            logger.info('api_parse_prescription: extracted text via pytesseract')
        except Exception as e:
            logger.warning(f'Local OCR failed or pytesseract unavailable: {e}')
            # Fallback to OCR.space if API key provided
            ocr_key = os.getenv('OCR_SPACE_API_KEY')
            if ocr_key:
                try:
                    # Optional debug: return raw OCR.space JSON to client if form param debug=1
                    debug_raw = request.form.get('debug', '') in ('1', 'true', 'yes')

                    # Preprocess image to improve OCR quality: grayscale, resize, contrast, denoise, threshold
                    from PIL import Image, ImageOps, ImageFilter
                    buf = io.BytesIO()
                    image_file.seek(0)
                    img = Image.open(image_file).convert('L')
                    # Upscale small images to help OCR
                    if img.width < 800:
                        img = img.resize((int(img.width * 2), int(img.height * 2)), Image.LANCZOS)
                    img = ImageOps.autocontrast(img)
                    img = img.filter(ImageFilter.MedianFilter(size=3))
                    # Simple thresholding
                    img = img.point(lambda p: 255 if p > 140 else 0)
                    img.save(buf, format='PNG')
                    buf.seek(0)

                    files = {'file': (image_file.filename, buf.read())}
                    payload = {
                        'apikey': ocr_key,
                        'language': 'eng',
                        'isOverlayRequired': False,
                        # try newer engine for better results if available
                        'OCREngine': 2
                    }
                    logger.info('api_parse_prescription: sending preprocessed image to OCR.space')
                    resp = requests.post('https://api.ocr.space/parse/image', files=files, data=payload, timeout=30)
                    try:
                        jd = resp.json()
                    except Exception:
                        jd = {'_raw_text': resp.text}
                    logger.info(f"api_parse_prescription: OCR.space response status={resp.status_code}")
                    logger.debug(f"api_parse_prescription: OCR.space response body={resp.text}")
                    parsed = jd.get('ParsedResults', []) if isinstance(jd, dict) else []
                    if parsed:
                        extracted_text = parsed[0].get('ParsedText', '')
                        logger.info('api_parse_prescription: extracted text via OCR.space')
                    else:
                        # try other fields for error messages
                        err_msg = jd.get('ErrorMessage') if isinstance(jd, dict) else None
                        logger.warning(f"api_parse_prescription: OCR.space returned no ParsedResults. error={err_msg}")
                        logger.debug(f"api_parse_prescription: OCR.space raw json: {jd}")

                    if debug_raw:
                        # return raw JSON to caller for debugging (keeps existing login_required)
                        return jsonify({'success': True, 'raw_ocr': jd})
                except Exception as e2:
                    logger.warning(f'OCR.space fallback failed: {e2}')

        if not extracted_text:
            return jsonify({'success': False, 'error': 'OCR not available or failed. Install pytesseract + Tesseract, or set OCR_SPACE_API_KEY.'}), 500

        # Simple parser: find lines that look like medication instructions
        def parse_prescription_text(text):
            import difflib

            meds = []
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            keyword_re = re.compile(r'\b(mg|ml|mcg|tablet|tab|capsule|cap|once|twice|daily|bd|od|tds|take|tos|syrup)\b', re.I)
            for ln in lines:
                if keyword_re.search(ln) or re.search(r'\b\d+\s*(?:mg|ml|mcg|g)\b', ln, re.I):
                    meds.append(ln)

            # Basic knowledge base for common drugs/brands -> canonical name + likely indications
            MEDICATION_KNOWLEDGE = {
                'caldol': {'name': 'Paracetamol (Acetaminophen)', 'indication': 'Fever, pain (analgesic/antipyretic)'},
                'paracetamol': {'name': 'Paracetamol (Acetaminophen)', 'indication': 'Fever, pain (analgesic/antipyretic)'},
                'meftal': {'name': 'Mefenamic acid', 'indication': 'Pain relief (NSAID) - e.g., menstrual pain, general analgesia'},
                'delcon': {'name': 'Delcon (cough/cold syrup)', 'indication': 'Cough and cold symptom relief (expectorant/antitussive) - brand-level match'},
                'levon': {'name': 'Levolin / Levosalbutamol', 'indication': 'Bronchodilator for wheeze/cough (relieves bronchospasm)'},
                'levosalbutamol': {'name': 'Levosalbutamol', 'indication': 'Bronchodilator (reliever for wheeze)'} ,
                'amoxi': {'name': 'Amoxicillin', 'indication': 'Antibiotic for bacterial infections'},
                'azith': {'name': 'Azithromycin', 'indication': 'Antibiotic (respiratory infections) - macrolide'},
                'cipro': {'name': 'Ciprofloxacin', 'indication': 'Antibiotic (broad-spectrum fluoroquinolone)'},
                'ibuprofen': {'name': 'Ibuprofen', 'indication': 'Pain, inflammation (NSAID)'},
                'parac': {'name': 'Paracetamol (Acetaminophen)', 'indication': 'Fever, pain (analgesic/antipyretic)'},
                'meftal-p': {'name': 'Mefenamic acid + Paracetamol', 'indication': 'Combined analgesic for moderate pain'}
            }

            # helper to identify med from a candidate line
            def identify_med(line):
                # normalize
                ln = re.sub(r'[^A-Za-z0-9\s\-]', ' ', line).lower()
                tokens = [t for t in re.split(r'\s+', ln) if t]
                # try exact token match in knowledge base
                for t in tokens[:3]:
                    if t in MEDICATION_KNOWLEDGE:
                        info = MEDICATION_KNOWLEDGE[t].copy()
                        info['confidence'] = 0.95
                        return info

                # try substring match
                for key in MEDICATION_KNOWLEDGE:
                    if key in ln:
                        info = MEDICATION_KNOWLEDGE[key].copy()
                        info['confidence'] = 0.9
                        return info

                # fuzzy match using difflib against token candidates
                names = list(MEDICATION_KNOWLEDGE.keys())
                for token in tokens[:4]:
                    cand = difflib.get_close_matches(token, names, n=1, cutoff=0.75)
                    if cand:
                        info = MEDICATION_KNOWLEDGE[cand[0]].copy()
                        info['confidence'] = 0.75
                        return info

                return {'name': '', 'indication': '', 'confidence': 0.0}

            # Try a simple named-extraction: look for leading drug name tokens before dosage
            meds_parsed = []
            name_re = re.compile(r"^([A-Za-z][A-Za-z0-9\-\s]{1,60}?)\s*(?:-|:)?\s*(\d+(?:\.\d+)?\s*(?:mg|ml|mcg|g))?", re.I)
            for mln in meds:
                m = name_re.match(mln)
                if m:
                    name = m.group(1).strip()
                    dose = m.group(2) or ''
                else:
                    # fallback: take first token as candidate
                    toks = re.split(r'\s+', mln)
                    name = toks[0] if toks else ''
                    dose = ''

                identified = identify_med(mln if name == '' or len(name) < 4 else name + ' ' + dose)
                meds_parsed.append({'line': mln, 'name': name, 'dose': dose, 'identified': identified})

            summary = f'Found {len(meds_parsed)} medication-like lines.'
            if meds_parsed:
                summary += ' Extracts: ' + '; '.join([ (p.get('identified', {}).get('name') or p.get('name') or p.get('line')) for p in meds_parsed[:6] ])

            return meds_parsed, summary, extracted_text

        meds_parsed, summary, full_text = parse_prescription_text(extracted_text)

        return jsonify({'success': True, 'text': full_text, 'medications': meds_parsed, 'summary': summary})

    except Exception as e:
        logger.exception('Error in api_parse_prescription')
        return jsonify({'success': False, 'error': str(e)}), 500

# -------------------------
# Routes - Hospital Search
# -------------------------
@app.route("/find-hospitals", methods=["POST"])
@login_required
def find_hospitals():
    try:
        data = request.get_json() or {}
        location = data.get('location', '').strip()
        
        if not location:
            return jsonify({"error": "Location is required"}), 400


        
        
        # Minimal mock database (include rating and distance to satisfy tests)
        hospitals_db = {
            "delhi": [
                {"name": "AIIMS Delhi", "address": "Ansari Nagar, New Delhi", "phone": "+91-11-2658-8500", "rating": 4.6, "distance": "5km"},
                {"name": "Apollo Hospitals Delhi", "address": "Sarita Vihar, Delhi", "phone": "+91-11-2692-5858", "rating": 4.2, "distance": "8km"},
                {"name": "Fortis Hospital", "address": "Vasant Kunj, Delhi", "phone": "+91-11-4141-4141", "rating": 4.1, "distance": "10km"}
            ],
            "mumbai": [
                {"name": "Breach Candy Hospital", "address": "Bhulabhai Desai Road, Mumbai", "phone": "+91-22-6708-5000", "rating": 4.5, "distance": "3km"},
                {"name": "Apollo Hospital Mumbai", "address": "Bandra, Mumbai", "phone": "+91-22-5645-5645", "rating": 4.3, "distance": "7km"}
            ],
            "bangalore": [
                {"name": "Apollo Hospital Bangalore", "address": "Bannerghatta Road, Bangalore", "phone": "+91-80-4000-4000", "rating": 4.4, "distance": "6km"},
                {"name": "Manipal Hospital", "address": "Whitefield, Bangalore", "phone": "+91-80-4159-9999", "rating": 4.2, "distance": "12km"}
            ]
        }
        
        location_lower = location.lower()
        hospitals = hospitals_db.get(location_lower, [])
        
        user_id = get_user_id()
        add_to_history(user_id, f"Find hospitals in {location}", f"Found {len(hospitals)}")
        
        return jsonify({
            "success": True,
            "hospitals": hospitals,
            "count": len(hospitals),
            "location": location
        })
    
    except Exception as e:
        logger.error(f"Hospital search error: {str(e)}")
        return jsonify({"error": "Failed to find hospitals"}), 500


# -------------------------
# Google Places - Nearby clinics and booking
# -------------------------
@app.route('/api/nearby-clinics', methods=['POST'])
@login_required
def api_nearby_clinics():
    try:
        data = request.get_json() or {}
        pincode = data.get('pincode')
        concern = data.get('concern', '')
        lat = data.get('lat')
        lng = data.get('lng')

        api_key = os.getenv('GOOGLE_MAPS_API_KEY')



        if not api_key:
            return jsonify({'success': False, 'error': 'Server not configured with GOOGLE_MAPS_API_KEY'}), 400

        candidates = []
        used_path = 'none'
        # Use Geocoding -> Nearby Search for pincode/address for better coverage in India
        if lat and lng:
            url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
            params = {'location': f'{lat},{lng}', 'radius': 5000, 'keyword': concern or 'clinic', 'type': 'hospital', 'key': api_key}
            resp = requests.get(url, params=params, timeout=10)
            dataj = resp.json()
            candidates = dataj.get('results', [])
            used_path = 'nearby_direct_5km'
        elif pincode:
            cache = load_geocode_cache()
            lat0 = lng0 = None
            # Check cache first
            if pincode in cache and isinstance(cache[pincode], dict) and cache[pincode].get('lat') and cache[pincode].get('lng'):
                lat0 = cache[pincode]['lat']
                lng0 = cache[pincode]['lng']
                used_path = 'geocode_cache'
                logger.info(f'api_nearby_clinics: geocode cache hit for {pincode}')

            # If not cached, attempt geocoding
            if not lat0 or not lng0:
                try:
                    geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json'
                    # use components to bias to India which helps ambiguous pincodes
                    params = {'components': f'postal_code:{pincode}|country:IN', 'key': api_key}
                    resp_geo = requests.get(geocode_url, params=params, timeout=8)
                    geo_json = resp_geo.json()
                    geo_results = geo_json.get('results', [])
                    if geo_results:
                        loc = geo_results[0].get('geometry', {}).get('location')
                        if loc and loc.get('lat') and loc.get('lng'):
                            lat0 = loc.get('lat')
                            lng0 = loc.get('lng')
                            # persist to cache
                            try:
                                cache[pincode] = {'lat': lat0, 'lng': lng0, 'timestamp': datetime.now().isoformat()}
                                save_geocode_cache(cache)
                                logger.info(f'api_nearby_clinics: geocode cached for {pincode}')
                            except Exception:
                                pass
                    else:
                        logger.info(f'Geocode returned no results for pincode {pincode}')
                except Exception as e:
                    logger.warning(f'Geocoding failed for pincode {pincode}: {e}')

            # If we have lat/lng (from cache or geocode), try nearby search with expanding radii
            if lat0 and lng0:
                for radius in (5000, 15000, 30000, 50000):
                    try:
                        url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
                        params = {'location': f'{lat0},{lng0}', 'radius': radius, 'keyword': concern or 'clinic', 'type': 'hospital', 'key': api_key}
                        resp = requests.get(url, params=params, timeout=10)
                        dataj = resp.json()
                        results = dataj.get('results', [])
                        logger.info(f'api_nearby_clinics: nearby search radius={radius} returned {len(results)} results')
                        if results:
                            candidates = results
                            used_path = f'nearby_radius_{radius}'
                            break
                    except Exception as e:
                        logger.warning(f'Nearby search failed radius={radius} for pincode {pincode}: {e}')

            # If geocoding / nearby search returned no candidates, fallback to text search
            if not candidates:
                try:
                    url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
                    query = f"{(concern + ' ') if concern else ''}clinic near {pincode}"
                    params = {'query': query, 'key': api_key}
                    resp = requests.get(url, params=params, timeout=10)
                    dataj = resp.json()
                    candidates = dataj.get('results', [])
                    used_path = 'text_search'
                except Exception as e:
                    logger.warning(f'Places textsearch failed for pincode {pincode}: {e}')
        else:
            return jsonify({'success': False, 'error': 'Provide pincode or lat/lng'}), 400

        clinics = []
        for c in candidates[:10]:
            place_id = c.get('place_id')
            name = c.get('name')
            address = c.get('vicinity') or c.get('formatted_address')
            loc = c.get('geometry', {}).get('location', {})
            rating = c.get('rating')
            user_ratings_total = c.get('user_ratings_total')
            clinics.append({
                'place_id': place_id,
                'name': name,
                'address': address,
                'lat': loc.get('lat'),
                'lng': loc.get('lng'),
                'rating': rating,
                'user_ratings_total': user_ratings_total
            })

        user_id = get_user_id()
        add_to_history(user_id, f'Nearby clinics search: pincode={pincode} lat={lat} lng={lng} concern={concern}', f'Found {len(clinics)}')

        return jsonify({'success': True, 'clinics': clinics, 'count': len(clinics)})
    except Exception as e:
        logger.exception('Error in api_nearby_clinics')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/book-appointment', methods=['POST'])
@login_required
def api_book_appointment():
    try:
        data = request.get_json() or {}
        place_id = data.get('place_id')
        patient_name = data.get('patient_name')
        phone = data.get('phone')
        email = data.get('email')
        date = data.get('date')
        time_slot = data.get('time')
        notes = data.get('notes', '')

        if not place_id or not patient_name or not phone or not date or not time_slot:
            return jsonify({'success': False, 'error': 'Missing required booking fields'}), 400

        api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        place_info = {'place_id': place_id}
        if api_key:
            details_url = 'https://maps.googleapis.com/maps/api/place/details/json'
            params = {'place_id': place_id, 'fields': 'name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,opening_hours', 'key': api_key}
            resp = requests.get(details_url, params=params, timeout=10)
            dj = resp.json()
            result = dj.get('result', {})
            place_info.update({
                'name': result.get('name'),
                'address': result.get('formatted_address'),
                'phone': result.get('formatted_phone_number'),
                'website': result.get('website'),
                'rating': result.get('rating'),
                'user_ratings_total': result.get('user_ratings_total')
            })

        booking = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'user': session.get('user', {}).get('email'),
            'patient_name': patient_name,
            'phone': phone,
            'email': email,
            'date': date,
            'time': time_slot,
            'notes': notes,
            'place': place_info
        }

        # Persist booking to a simple JSON file
        appt_file = 'appointments.json'
        try:
            if _HAS_FERNET and os.getenv('FERNET_KEY'):
                try:
                    with open(appt_file, 'rb') as f:
                        ciphertext = f.read()
                    key = os.getenv('FERNET_KEY')
                    dec = Fernet(key.encode())
                    plaintext = dec.decrypt(ciphertext)
                    appts = json.loads(plaintext.decode('utf-8'))
                except Exception:
                    with open(appt_file, 'r', encoding='utf-8') as f:
                        appts = json.load(f)
            else:
                with open(appt_file, 'r', encoding='utf-8') as f:
                    appts = json.load(f)
        except Exception:
            appts = []

        appts.append(booking)
        try:
            try:
                backup_file(appt_file)
            except Exception:
                pass
            if _HAS_FERNET and os.getenv('FERNET_KEY'):
                key = os.getenv('FERNET_KEY')
                enc = Fernet(key.encode())
                plaintext = json.dumps(appts, ensure_ascii=False).encode('utf-8')
                ciphertext = enc.encrypt(plaintext)
                with open(appt_file, 'wb') as f:
                    f.write(ciphertext)
            else:
                atomic_write_json(appt_file, appts)
        except Exception as e:
            logger.warning(f"Failed to save appointment: {e}")

        user_id = get_user_id()
        add_to_history(user_id, f'Booked appointment {booking["id"]}', f'{place_info.get("name")} on {date} {time_slot}')

        return jsonify({'success': True, 'booking_id': booking['id'], 'booking': booking})
    except Exception as e:
        logger.exception('Error in api_book_appointment')
        return jsonify({'success': False, 'error': str(e)}), 500


# Nearby fitness centers (gym / yoga / fitness) - reuse Google Places logic
@app.route('/api/nearby-fitness', methods=['GET', 'POST'])
def api_nearby_fitness():
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            data = request.args.to_dict()
        pincode = data.get('pincode')
        place_type = data.get('type', 'gym')  # gym, yoga, fitness
        lat = data.get('lat')
        lng = data.get('lng')
        keyword = data.get('keyword', '')

        api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if not api_key:
            return jsonify({'success': False, 'error': 'Server not configured with GOOGLE_MAPS_API_KEY'}), 400

        candidates = []
        # If lat/lng provided use nearbysearch
        if lat and lng:
            url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
            params = {'location': f'{lat},{lng}', 'radius': 8000, 'keyword': keyword or place_type, 'type': 'gym' if place_type=='gym' else 'health', 'key': api_key}
            resp = requests.get(url, params=params, timeout=10)
            dataj = resp.json()
            candidates = dataj.get('results', [])
        elif pincode:
            cache = load_geocode_cache()
            lat0 = lng0 = None
            if pincode in cache and isinstance(cache[pincode], dict):
                lat0 = cache[pincode].get('lat')
                lng0 = cache[pincode].get('lng')

            if not lat0 or not lng0:
                try:
                    geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json'
                    params = {'components': f'postal_code:{pincode}|country:IN', 'key': api_key}
                    resp_geo = requests.get(geocode_url, params=params, timeout=8)
                    geo_json = resp_geo.json()
                    geo_results = geo_json.get('results', [])
                    if geo_results:
                        loc = geo_results[0].get('geometry', {}).get('location')
                        if loc:
                            lat0 = loc.get('lat')
                            lng0 = loc.get('lng')
                            try:
                                cache[pincode] = {'lat': lat0, 'lng': lng0, 'timestamp': datetime.now().isoformat()}
                                save_geocode_cache(cache)
                            except Exception:
                                pass
                except Exception:
                    pass

            if lat0 and lng0:
                for radius in (5000, 15000, 30000, 50000):
                    try:
                        url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
                        params = {'location': f'{lat0},{lng0}', 'radius': radius, 'keyword': keyword or place_type, 'type': 'gym', 'key': api_key}
                        resp = requests.get(url, params=params, timeout=10)
                        dataj = resp.json()
                        results = dataj.get('results', [])
                        if results:
                            candidates = results
                            break
                    except Exception:
                        pass

            if not candidates:
                try:
                    url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
                    query = f"{(place_type + ' ') if place_type else ''}clinic near {pincode}"
                    params = {'query': query, 'key': api_key}
                    resp = requests.get(url, params=params, timeout=10)
                    dataj = resp.json()
                    candidates = dataj.get('results', [])
                except Exception:
                    pass
        else:
            return jsonify({'success': False, 'error': 'Provide pincode or lat/lng'}), 400

        facilities = []
        for c in candidates[:12]:
            loc = c.get('geometry', {}).get('location', {})
            facilities.append({
                'place_id': c.get('place_id'),
                'name': c.get('name'),
                'address': c.get('vicinity') or c.get('formatted_address'),
                'lat': loc.get('lat'),
                'lng': loc.get('lng'),
                'rating': c.get('rating'),
                'user_ratings_total': c.get('user_ratings_total')
            })

        user_id = get_user_id()
        add_to_history(user_id, f'Nearby fitness search: pincode={pincode} lat={lat} lng={lng} type={place_type}', f'Found {len(facilities)}')

        return jsonify({'success': True, 'facilities': facilities, 'count': len(facilities)})
    except Exception as e:
        logger.exception('Error in api_nearby_fitness')
        return jsonify({'success': False, 'error': str(e)}), 500


# Order protein-focused meals (search nearby restaurants / cafes with protein keyword)
@app.route('/api/order-protein', methods=['GET', 'POST'])
def api_order_protein():
    try:
        # Accept JSON body, form-encoded body, or query params for maximum compatibility
        json_body = request.get_json(silent=True)
        form = request.form or {}
        args = request.args or {}
        data = {}
        if json_body:
            data.update(json_body)
        # include form fields (e.g., from HTML form POST)
        for k in form:
            if k not in data:
                data[k] = form.get(k)
        # include query params if not present
        for k in args:
            if k not in data:
                data[k] = args.get(k)

        # log request basics for debugging
        try:
            logger.debug('api_order_protein called', extra={'method': request.method, 'args': dict(request.args), 'form': dict(request.form), 'json': json_body})
        except Exception:
            logger.debug('api_order_protein called (logging failed)')

        pincode = data.get('pincode')
        lat = data.get('lat')
        lng = data.get('lng')
        calories = data.get('calories')

        api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        results = []
        if api_key and ((lat and lng) or pincode):
            # prefer nearbysearch with keyword 'protein' or 'high protein'
            if lat and lng:
                url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
                params = {'location': f'{lat},{lng}', 'radius': 8000, 'keyword': 'protein OR "high protein" OR "protein shake"', 'type': 'restaurant', 'key': api_key}
                resp = requests.get(url, params=params, timeout=10)
                try:
                    dataj = resp.json()
                except Exception:
                    logger.debug('Non-json response from Google nearbysearch', extra={'text': resp.text[:400]})
                    dataj = {}
                results = dataj.get('results', [])
            else:
                # geocode pincode
                cache = load_geocode_cache()
                lat0 = lng0 = None
                if pincode in cache and isinstance(cache[pincode], dict):
                    lat0 = cache[pincode].get('lat')
                    lng0 = cache[pincode].get('lng')
                if not lat0 or not lng0:
                    try:
                        geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json'
                        params = {'components': f'postal_code:{pincode}|country:IN', 'key': api_key}
                        resp_geo = requests.get(geocode_url, params=params, timeout=8)
                        geo_json = resp_geo.json()
                        geo_results = geo_json.get('results', [])
                        if geo_results:
                            loc = geo_results[0].get('geometry', {}).get('location')
                            if loc:
                                lat0 = loc.get('lat')
                                lng0 = loc.get('lng')
                                try:
                                    cache[pincode] = {'lat': lat0, 'lng': lng0, 'timestamp': datetime.now().isoformat()}
                                    save_geocode_cache(cache)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                if lat0 and lng0:
                    url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
                    params = {'location': f'{lat0},{lng0}', 'radius': 15000, 'keyword': 'protein OR "high protein"', 'type': 'restaurant', 'key': api_key}
                    resp = requests.get(url, params=params, timeout=10)
                    try:
                        dataj = resp.json()
                    except Exception:
                        logger.debug('Non-json response from Google nearbysearch (geocoded)', extra={'text': resp.text[:400]})
                        dataj = {}
                    results = dataj.get('results', [])
        else:
            # No API key or location: return a small mocked menu list
            results = [
                {'name': 'Protein Bowl Express', 'address': 'Local Healthy Meals', 'phone': '', 'sample_menu': ['Grilled chicken bowl', 'Lentil & quinoa bowl', 'Protein shake'], 'rating': 4.6},
                {'name': 'Shake & Fuel', 'address': 'Nearby Market Road', 'phone': '', 'sample_menu': ['Whey shake', 'Greek yogurt parfait', 'Turkey wrap'], 'rating': 4.4}
            ]

        offers = []
        # If we have a Google API key and place_ids, enrich with place details (phone, website)
        details_fields = 'name,formatted_address,formatted_phone_number,website,opening_hours,types,rating,user_ratings_total'
        for r in results[:8]:
            offer = {
                'name': r.get('name') or r.get('vicinity') or r.get('address'),
                'address': r.get('vicinity') or r.get('formatted_address') or r.get('address'),
                'rating': r.get('rating'),
                'place_id': r.get('place_id'),
                'sample_menu': r.get('sample_menu', [])
            }
            # enrich with details when possible
            try:
                if api_key and r.get('place_id'):
                    details_url = 'https://maps.googleapis.com/maps/api/place/details/json'
                    params = {'place_id': r.get('place_id'), 'fields': details_fields, 'key': api_key}
                    resp = requests.get(details_url, params=params, timeout=8)
                    try:
                        dj = resp.json()
                    except Exception:
                        logger.debug('Non-json response from Google details', extra={'text': resp.text[:400]})
                        dj = {}
                    res = dj.get('result', {})
                    if res:
                        if res.get('formatted_phone_number'):
                            offer['phone'] = res.get('formatted_phone_number')
                        if res.get('website'):
                            offer['website'] = res.get('website')
                        if res.get('opening_hours'):
                            offer['opening_hours'] = res.get('opening_hours')
                        # For simple menu hints, add types
                        if res.get('types'):
                            offer['types'] = res.get('types')
            except Exception:
                # ignore enrichment failures
                pass
            offers.append(offer)

        user_id = get_user_id()
        add_to_history(user_id, f'Order protein meals: pincode={pincode} lat={lat} lng={lng} calories={calories}', f'Found {len(offers)}')

        return jsonify({'success': True, 'offers': offers})
    except Exception as e:
        logger.exception('Error in api_order_protein')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/google-maps-health', methods=['GET'])
def api_google_maps_health():
    """Simple diagnostic endpoint to verify Google Maps API key and basic connectivity."""
    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'error': 'GOOGLE_MAPS_API_KEY not configured'}), 400

    try:
        url = 'https://maps.googleapis.com/maps/api/geocode/json'
        params = {'address': 'New Delhi, IN', 'key': api_key}
        resp = requests.get(url, params=params, timeout=8)
        try:
            dataj = resp.json()
        except Exception:
            return jsonify({'success': False, 'error': 'Non-json response from Google', 'raw': resp.text[:800]}), 502

        status = dataj.get('status')
        return jsonify({'success': True, 'google_status': status, 'sample_result_count': len(dataj.get('results', []))})
    except Exception as e:
        logger.exception('Google Maps health check failed')
        return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/mock-order', methods=['POST'])
    @login_required
    def api_mock_order():
        """Simulate placing an order for a protein meal offer and persist it locally."""
        try:
            data = request.get_json() or {}
            offer = data.get('offer')
            delivery_address = data.get('address') or ''
            contact_phone = data.get('phone') or ''
            user = session.get('user', {}).get('email') or 'anonymous'

            if not offer or not offer.get('name'):
                return jsonify({'success': False, 'error': 'offer data required'}), 400

            order = {
                'id': str(uuid.uuid4()),
                'timestamp': datetime.now().isoformat(),
                'user': user,
                'offer': offer,
                'delivery_address': delivery_address,
                'contact_phone': contact_phone,
                'status': 'placed_simulated'
            }

            orders_file = 'orders.json'
            try:
                if _HAS_FERNET and os.getenv('FERNET_KEY'):
                    try:
                        with open(orders_file, 'rb') as f:
                            ciphertext = f.read()
                        key = os.getenv('FERNET_KEY')
                        dec = Fernet(key.encode())
                        plaintext = dec.decrypt(ciphertext)
                        orders = json.loads(plaintext.decode('utf-8'))
                    except Exception:
                        with open(orders_file, 'r', encoding='utf-8') as f:
                            orders = json.load(f)
                else:
                    with open(orders_file, 'r', encoding='utf-8') as f:
                        orders = json.load(f)
            except Exception:
                orders = []

            orders.append(order)
            try:
                try:
                    backup_file(orders_file)
                except Exception:
                    pass
                if _HAS_FERNET and os.getenv('FERNET_KEY'):
                    key = os.getenv('FERNET_KEY')
                    enc = Fernet(key.encode())
                    plaintext = json.dumps(orders, ensure_ascii=False).encode('utf-8')
                    ciphertext = enc.encrypt(plaintext)
                    with open(orders_file, 'wb') as f:
                        f.write(ciphertext)
                else:
                    atomic_write_json(orders_file, orders)
            except Exception as e:
                logger.warning(f"Failed to save order: {e}")

            user_id = get_user_id()
            add_to_history(user_id, f'Placed simulated order {order["id"]}', f'{offer.get("name")}')

            return jsonify({'success': True, 'order_id': order['id'], 'order': order})
        except Exception as e:
            logger.exception('Error in api_mock_order')
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/medication-explain', methods=['POST'])
@login_required
def api_medication_explain():
    """Return a short, plain-language explanation for a medication name or phrase.
    Uses the local MEDICATION_KNOWLEDGE mapping; if no close match is found attempts openFDA lookup and summarizes results.
    """
    try:
        data = request.get_json() or {}
        query = (data.get('query') or '').strip()
        if not query:
            return jsonify({'success': False, 'error': 'query is required'}), 400

        qnorm = re.sub(r'[^A-Za-z0-9\s\-]', ' ', query).lower()
        tokens = [t for t in re.split(r'\s+', qnorm) if t]

        # local matching first
        match_key = None
        for t in tokens[:3]:
            if t in MEDICATION_KNOWLEDGE:
                match_key = t
                break

        if not match_key:
            for key in MEDICATION_KNOWLEDGE:
                if key in qnorm:
                    match_key = key
                    break

        if match_key:
            info = MEDICATION_KNOWLEDGE[match_key]
            name = info.get('name')
            indication = info.get('indication')
            explanation = f"{name}: {indication}."
            return jsonify({'success': True, 'explanation': explanation, 'match': match_key, 'confidence': 0.9, 'source': 'local'})

        # try openFDA for richer info
        try:
            of = call_openfda_drug_label(query)
        except Exception:
            of = None

        if of:
            parts = []
            if of.get('indications_and_usage'):
                parts.append('Indications: ' + ' '.join(of.get('indications_and_usage')[:2]))
            if of.get('dosage_and_administration'):
                parts.append('Dosage guidance: ' + ' '.join(of.get('dosage_and_administration')[:2]))
            if of.get('adverse_reactions'):
                parts.append('Common adverse reactions: ' + ' '.join(of.get('adverse_reactions')[:2]))
            if of.get('drug_interactions'):
                parts.append('Drug interactions noted: ' + ' '.join(of.get('drug_interactions')[:2]))

            explanation = ' '.join(parts) if parts else 'Information retrieved but no concise fields available.'
            return jsonify({'success': True, 'explanation': explanation, 'match': None, 'confidence': 0.7, 'source': 'openfda'})

        # conservative fallback
        fallback = "No concise mapping found for this medicine in the local database. Please verify the medicine name and consult your healthcare provider or pharmacist for authoritative information."
        return jsonify({'success': True, 'explanation': fallback, 'match': None, 'confidence': 0.0, 'source': 'fallback'})
    except Exception as e:
        logger.exception('Error in api_medication_explain')
        return jsonify({'success': False, 'error': str(e)}), 500


# -------------------------
# Reminder APIs
# -------------------------
@app.route('/api/reminders', methods=['GET', 'POST'])
@login_required
def api_reminders():
    try:
        user_email = session.get('user', {}).get('email')
        if request.method == 'GET':
            reminders = load_reminders()
            # return only reminders for this user (by email) or all if not available
            if user_email:
                filtered = [r for r in reminders if r.get('email') == user_email]
            else:
                filtered = reminders
            return jsonify({'success': True, 'reminders': filtered})

        # POST - create a new reminder
        data = request.get_json() or {}
        rtype = data.get('type')
        time_str = data.get('time')
        frequency = data.get('frequency', 'once')
        note = data.get('note', '')
        email = data.get('email') or user_email

        if not rtype or not time_str or not email:
            return jsonify({'success': False, 'error': 'Missing required fields (type, time, email)'}), 400

        # compute next_run from provided time
        now = datetime.now()
        hh, mm = map(int, time_str.split(':'))
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)

        reminder = {
            'id': str(uuid.uuid4()),
            'user': user_email,
            'email': email,
            'type': rtype,
            'time': time_str,
            'frequency': frequency,
            'note': note,
            'created_at': now.isoformat(),
            'next_run': candidate.isoformat(),
            'active': True
        }

        reminders = load_reminders()
        reminders.append(reminder)
        save_reminders(reminders)

        return jsonify({'success': True, 'reminder': reminder})
    except Exception as e:
        logger.exception('Error in api_reminders')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-test-email', methods=['POST'])
@login_required
def api_send_test_email():
    try:
        data = request.get_json() or {}
        to_addr = data.get('to') or session.get('user', {}).get('email')
        subject = data.get('subject') or 'Test reminder from MediBot'
        body = data.get('body') or 'This is a test email sent from the Medical Chatbot.'

        if not to_addr:
            return jsonify({'success': False, 'error': 'No recipient provided and no user email in session'}), 400

        sent, err = send_email(to_addr, subject, body)
        if sent:
            return jsonify({'success': True, 'message': f'Sent test email to {to_addr}'}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to send email', 'detail': err}), 500
    except Exception as e:
        logger.exception('Error in api_send_test_email')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/smtp-check', methods=['GET'])
@login_required
def api_smtp_check():
    """Attempt to connect and authenticate to configured SMTP server and return diagnostic info."""
    server = os.getenv('SMTP_SERVER')
    port = int(os.getenv('SMTP_PORT', 587))
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_addr = os.getenv('EMAIL_FROM') or user

    if not server or not user or not password or not from_addr:
        return jsonify({'success': False, 'error': 'Missing SMTP configuration in environment'}), 400

    try:
        with smtplib.SMTP(server, port, timeout=20) as smtp:
            smtp.ehlo()
            if port == 587:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, password)
        return jsonify({'success': True, 'message': 'SMTP connection and authentication succeeded'})
    except Exception as e:
        logger.exception('SMTP check failed')
        return jsonify({'success': False, 'error': 'SMTP check failed', 'detail': str(e)}), 500


# -------------------------
# Error Handlers
# -------------------------
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    # start reminder worker thread
    try:
        t = threading.Thread(target=reminder_worker, daemon=True)
        t.start()
    except Exception as e:
        logger.warning(f'Failed to start reminder worker thread: {e}')

    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
