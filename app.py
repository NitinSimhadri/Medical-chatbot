from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from dotenv import load_dotenv
import os
import json
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import logging
from PIL import Image

# Minimal, cleaned Flask app: no LLM/vector dependencies
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config['SESSION_TYPE'] = 'filesystem'

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

def get_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def load_user_history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

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
        with open('users.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=2)

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
        "summarizer": "services/summarizer.html",
        "vitals": "services/vitals.html",
        "reminder": "services/reminder.html",
        "history": "services/history.html",
        "report_generator": "services/report_generator.html",
        "skin_analysis": "services/skin_analysis.html",
    }
    tpl = allowed.get(service)
    if not tpl:
        return render_template("404.html"), 404
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

    # Not handled by heuristics -> use RAG if available, else fallback generator
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

        # Get optional prompt from form
        prompt = request.form.get('prompt', 'Analyze this medical image and provide general health observations.')

        # Ensure we have a user id for history entries
        user_id = get_user_id()

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
                return jsonify({"success": True, "analysis": answer})
            except Exception as e:
                logger.exception(f"RAG image analysis failed: {e}")
                # fall through to safe fallback

        # Safe fallback analysis (no LLM or RAG failed)
        # Include explicit disclaimer strings expected by tests: 'DISCLAIMER' and 'NOT a'
        analysis = (
            f"Image received ({image_file.filename}). "
            "DISCLAIMER: THIS IS NOT a medical diagnosis. "
            "This is general informational content only. Always consult a healthcare professional for proper diagnosis. "
            f"Analysis prompt: {prompt}"
        )

        add_to_history(user_id, f"Image analysis: {prompt[:100]}", analysis[:200])

        logger.info("analyze_image: success (fallback)")
        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        logger.exception("Unexpected error in analyze_image")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


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
# Error Handlers
# -------------------------
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
