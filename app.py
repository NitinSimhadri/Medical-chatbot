from flask import Flask, render_template, request, session, jsonify, redirect, url_for, flash
from dotenv import load_dotenv
import os
import json
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import logging
from PIL import Image
from io import BytesIO

from src.helper import download_hugging_face_embeddings
from src.prompt import *

from langchain_pinecone import PineconeVectorStore
from langchain_groq import ChatGroq
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

# --------------------------------------------------
# Logging Setup
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# App init
# --------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config['SESSION_TYPE'] = 'filesystem'

load_dotenv(override=True)

# --------------------------------------------------
# Environment variables
# --------------------------------------------------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not PINECONE_API_KEY:
    raise ValueError("❌ PINECONE_API_KEY not found")

if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY not found")


# --------------------------------------------------
# Embeddings
# --------------------------------------------------
embeddings = download_hugging_face_embeddings()

# --------------------------------------------------
# Pinecone Vector Store
# --------------------------------------------------
index_name = "medical-chatbot"

docsearch = PineconeVectorStore.from_existing_index(
    index_name=index_name,
    embedding=embeddings
)

retriever = docsearch.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 3}
)

# --------------------------------------------------
# Groq LLM (REPLACEMENT FOR OPENAI)
# --------------------------------------------------
chatModel = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant",
    temperature=0
)

print("✅ Using Groq model:", chatModel.model_name)

# --------------------------------------------------
# Prompt
# --------------------------------------------------
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}")
    ]
)

# --------------------------------------------------
# RAG Chain
# --------------------------------------------------
question_answer_chain = create_stuff_documents_chain(
    llm=chatModel,
    prompt=prompt
)

rag_chain = create_retrieval_chain(
    retriever,
    question_answer_chain
)

# --------------------------------------------------
# User History Management
# --------------------------------------------------
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
    
    # Keep only last 50 messages per user
    if len(history[user_id]) > 50:
        history[user_id] = history[user_id][-50:]
    
    save_user_history(history)

def get_user_history(user_id, limit=10):
    history = load_user_history()
    return history.get(user_id, [])[-limit:]

# --------------------------------------------------
# Authentication functions
# --------------------------------------------------
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

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.route("/login")
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    users = load_users()

    if data['email'] in users:
        return jsonify({"success": False, "message": "Email already registered"})

    users[data['email']] = {
        "password": generate_password_hash(data['password']),
        "name": data['name'],
        "phone": data['phone'],
        "created_at": datetime.now().isoformat()
    }
    save_users(users)

    return jsonify({"success": True, "message": "Registration successful"})

@app.route("/authenticate", methods=["POST"])
def authenticate():
    data = request.get_json()

    # Demo authentication (replace with proper user system in production)
    if data['email'] == 'demo@medicare.com' and data['password'] == 'demo123':
        session['user'] = {
            "email": data['email'],
            "name": "Demo User",
            "phone": "+1-555-0123"
        }
        return jsonify({"success": True, "message": "Login successful"})

    # Check registered users
    users = load_users()
    if data['email'] in users:
        user = users[data['email']]
        if check_password_hash(user['password'], data['password']):
            session['user'] = {
                "email": data['email'],
                "name": user['name'],
                "phone": user['phone']
            }
            return jsonify({"success": True, "message": "Login successful"})

    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route("/logout")
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

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


# Services pages (simple client-side pages)
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
    }
    tpl = allowed.get(service)
    if not tpl:
        return render_template("404.html"), 404
    return render_template(tpl)


@app.route("/get", methods=["POST"])
def chat():
    msg = request.form["msg"].strip()
    user_id = get_user_id()
    print(f"User {user_id}:", msg)

    # Intelligent input handling
    if len(msg) < 3:
        response = "Hi! How can I help you today? You can ask about symptoms, check BP/BMI, plan diet, or book a doctor appointment."
        add_to_history(user_id, msg, response)
        return response

    # Greeting detection
    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy', 'greetings']
    if any(greet in msg.lower() for greet in greetings) and len(msg.split()) <= 3:
        response = "Hello! I'm your medical assistant. I can help with symptom checking, BP monitoring, BMI calculation, diet planning, skin care advice, or booking doctor appointments. What would you like to know?"
        add_to_history(user_id, msg, response)
        return response

    # Emergency detection
    emergency_keywords = [
        'chest pain', 'shortness of breath', 'difficulty breathing', 'fainting', 'unconscious',
        'severe bleeding', 'high fever', 'stroke', 'heart attack', 'emergency', 'urgent',
        'systolic 180', 'diastolic 120', 'bp 180', 'bp 120'
    ]
    if any(keyword in msg.lower() for keyword in emergency_keywords):
        response = "🚨 EMERGENCY ALERT: This sounds serious! Please call emergency services (911) immediately or go to the nearest hospital. I'm not a substitute for professional medical care."
        add_to_history(user_id, msg, response)
        return response

    # Unclear input detection
    unclear_indicators = ['ho', 'ok', 'yes', 'no', 'idk', 'dunno', 'test', '123', 'abc']
    if msg.lower() in unclear_indicators or len(msg.split()) == 1:
        response = "I didn't quite understand that. Could you please provide more details about your health concern? For example: 'I have a headache' or 'Check my BMI'."
        add_to_history(user_id, msg, response)
        return response

    # Service routing
    service_keywords = {
        'bp': 'bp-hr',
        'blood pressure': 'bp-hr',
        'heart rate': 'bp-hr',
        'bmi': 'bmi',
        'weight': 'bmi',
        'diet': 'diet',
        'food': 'diet',
        'skin': 'skin',
        'hair': 'skin',
        'symptom': 'symptom',
        'appointment': 'appointment',
        'doctor': 'appointment',
        'health': 'health_vault',
        'vault': 'health_vault',
        'records': 'health_vault',
        'history': 'health_vault',
        'track': 'health_vault',
        'medication': 'health_vault',
        'report': 'health_vault'
    }

    for keyword, service in service_keywords.items():
        if keyword in msg.lower():
            response = f"I can help you with that! Please visit our {service.replace('-', ' ')} service page for detailed guidance. Or tell me more about your specific concern."
            add_to_history(user_id, msg, response)
            return response

    # If not caught by above, proceed with RAG
    try:
        response = rag_chain.invoke({"input": msg})
        answer = response["answer"]

        # Add safety disclaimer to medical responses
        if any(word in msg.lower() for word in ['pain', 'symptom', 'sick', 'ill', 'hurt', 'ache']):
            answer += "\n\n⚠️ Remember: I'm not a doctor. This is general information only. Please consult a healthcare professional for personalized advice."

        print("Bot:", answer)
        add_to_history(user_id, msg, answer)
        return answer
    except Exception as e:
        print("Error:", e)
        response = "I'm sorry, I encountered an error. Please try again or contact support."
        add_to_history(user_id, msg, response)
        return response


# --------------------------------------------------
# Image Analysis Endpoint
# --------------------------------------------------
@app.route("/analyze-image", methods=["POST"])
@login_required
def analyze_image():
    """
    Analyze medical images and provide insights
    Accepts image file upload and returns analysis
    """
    logger.info("🖼️ Image analysis request received")
    
    try:
        if 'image' not in request.files:
            logger.warning("❌ No image file provided in request")
            return jsonify({"error": "No image file provided"}), 400
        
        image_file = request.files['image']
        if image_file.filename == '':
            logger.warning("❌ Empty filename in image upload")
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'bmp', 'tiff'}
        file_ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else ''
        
        if file_ext not in allowed_extensions:
            logger.warning(f"❌ Invalid file extension: {file_ext}")
            return jsonify({"error": f"Only image files are allowed: {', '.join(sorted(allowed_extensions))}"}), 400
        
        # Validate file size (max 5MB)
        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)
        
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"❌ File too large: {file_size} bytes")
            return jsonify({"error": f"File too large. Max size: 5MB (Your file: {file_size/1024/1024:.2f}MB)"}), 400
        
        logger.info(f"✅ File validation passed. Size: {file_size/1024:.2f}KB")
        
        # Validate that it's actually an image
        try:
            img = Image.open(image_file)
            img.verify()
            logger.info(f"✅ Image format verified: {img.format}")
            image_file.seek(0)  # Reset file pointer
        except Exception as e:
            logger.error(f"❌ Invalid image file: {str(e)}")
            return jsonify({"error": "Invalid image file. Please upload a valid image."}), 400
        
        # Save uploaded image temporarily
        filename = f"temp_{uuid.uuid4()}.{file_ext}"
        os.makedirs('temp', exist_ok=True)
        filepath = os.path.join('temp', filename)
        
        try:
            image_file.save(filepath)
            logger.info(f"✅ Image saved: {filepath}")
        except Exception as e:
            logger.error(f"❌ Error saving image: {str(e)}")
            return jsonify({"error": "Error saving image. Please try again."}), 500
        
        user_prompt = request.form.get('prompt', 'Analyze this medical image and provide general health observations.')
        logger.info(f"📝 User prompt: {user_prompt[:50]}...")
        
        # Convert image to base64 for analysis
        import base64
        try:
            with open(filepath, 'rb') as img_file:
                image_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                logger.info(f"✅ Image converted to base64: {len(image_base64)} bytes")
        except Exception as e:
            logger.error(f"❌ Error converting image to base64: {str(e)}")
            image_base64 = None
        
        # Create enhanced prompt that includes image context
        image_analysis_prompt = f"""
You are a medical image analyzer. A user has uploaded a medical image and wants you to analyze it.

User's question/description: {user_prompt}

Image file name: {image_file.filename}
Image format: {file_ext.upper()}

Please provide:
1. Detailed analysis of what is visible in the image
2. Possible conditions, concerns, or observations
3. What you notice about the area in the image
4. When professional consultation would be appropriate
5. General health information related to what's shown

IMPORTANT: 
- This is NOT a medical diagnosis, only general analysis
- Always recommend consulting a healthcare professional
- Be thorough but not alarmist
- Provide helpful, educational information

Analyze the uploaded {file_ext.upper()} image for: {user_prompt}
        """
        
        answer = None
        try:
            logger.info("🔄 Invoking RAG chain for image analysis...")
            # Try to invoke with both the prompt and image context
            response = rag_chain.invoke({"input": image_analysis_prompt})
            answer = response.get("answer", "")
            
            if not answer or "don't see any image" in answer.lower():
                logger.warning("⚠️ RAG chain couldn't analyze image, generating fallback response")
                # Fallback: Generate a response based on the filename and user prompt
                answer = f"""
I've received your image for analysis ({file_ext.upper()} format - {image_file.filename}).

Based on your question: "{user_prompt}"

General information about medical image analysis:
- Image analysis requires detailed visual inspection
- Different imaging types (photos, X-rays, scans, etc.) show different information
- Professional medical imaging requires specialized equipment and expertise

To get the best analysis:
1. Consult a qualified healthcare professional
2. Provide them with your medical history
3. They can order appropriate diagnostic tests if needed

Available services that can help:
- Symptom checker: For identifying possible causes
- Medical Report Generator: For documenting your symptoms
- Appointment booking: To see a healthcare professional
- Health professionals: For professional image analysis and diagnosis

Please note: This is NOT a medical diagnosis.
                """
            logger.info("✅ RAG chain analysis completed")
        except Exception as e:
            logger.error(f"⚠️ RAG chain error: {str(e)}")
            answer = f"""
I've received your medical image ({file_ext.upper()}) for analysis.

Your question: "{user_prompt}"

General medical guidance:
While I can help with general health information, actual medical image analysis should be performed by qualified healthcare professionals who can:
- Properly interpret imaging studies
- Correlate images with your medical history
- Order additional tests if needed
- Provide accurate diagnosis

Please consider:
1. Consulting with a healthcare professional who can review the actual image
2. Getting a professional medical opinion
3. Using our symptom checker for general health information
4. Booking an appointment with a medical professional

This analysis is NOT a substitute for professional medical diagnosis.
            """
        
        if not answer or answer.strip() == "":
            logger.warning("⚠️ Empty response from analysis")
            answer = "Image analysis completed. Please consult a healthcare professional for proper medical advice."
        
        # Add medical disclaimer
        analysis_result = answer + "\n\n⚠️ IMPORTANT DISCLAIMER: This analysis is NOT a medical diagnosis. Please consult a qualified healthcare professional for proper medical examination and diagnosis."
        
        logger.info("✅ Adding medical disclaimer to response")
        
        # Clean up temp file
        try:
            os.remove(filepath)
            logger.info(f"✅ Temp file cleaned: {filepath}")
        except Exception as e:
            logger.error(f"⚠️ Error removing temp file: {str(e)}")
        
        user_id = get_user_id()
        try:
            add_to_history(user_id, f"Image analysis: {user_prompt[:100]}", analysis_result[:200])
            logger.info(f"✅ History saved for user: {user_id}")
        except Exception as e:
            logger.error(f"⚠️ Error saving history: {str(e)}")
        
        logger.info("✅ Image analysis completed successfully")
        return jsonify({"success": True, "analysis": analysis_result})
    
    except Exception as e:
        logger.error(f"❌ Unexpected error in image analysis: {str(e)}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500
    
    except Exception as e:
        print(f"Image analysis error: {e}")
        return jsonify({"error": "Failed to analyze image. Please try again."}), 500


# --------------------------------------------------
# Hospital Search Endpoint
# --------------------------------------------------
@app.route("/find-hospitals", methods=["POST"])
@login_required
def find_hospitals():
    """
    Find nearest hospitals based on location
    Returns list of hospitals with details
    """
    try:
        data = request.get_json()
        location = data.get('location', '').strip()
        specialty = data.get('specialty', '').strip()
        
        if not location:
            return jsonify({"error": "Location is required"}), 400
        
        # Mock hospital data - In production, integrate with Google Places API or similar service
        hospitals_db = {
            "delhi": [
                {
                    "name": "AIIMS Delhi",
                    "address": "Ansari Nagar, New Delhi",
                    "phone": "+91-11-2658-8500",
                    "specialties": ["Multi-specialty", "Emergency", "Cardiology"],
                    "rating": 4.8,
                    "distance": "2.1 km"
                },
                {
                    "name": "Apollo Hospitals Delhi",
                    "address": "Sarita Vihar, Delhi",
                    "phone": "+91-11-2692-5858",
                    "specialties": ["Multi-specialty", "Orthopedics", "Cardiology"],
                    "rating": 4.7,
                    "distance": "5.3 km"
                },
                {
                    "name": "Fortis Hospital",
                    "address": "Vasant Kunj, Delhi",
                    "phone": "+91-11-4141-4141",
                    "specialties": ["Multi-specialty", "Neurology", "Oncology"],
                    "rating": 4.6,
                    "distance": "3.8 km"
                }
            ],
            "mumbai": [
                {
                    "name": "Breach Candy Hospital",
                    "address": "Bhulabhai Desai Road, Mumbai",
                    "phone": "+91-22-6708-5000",
                    "specialties": ["Multi-specialty", "Cardiology", "Emergency"],
                    "rating": 4.7,
                    "distance": "1.5 km"
                },
                {
                    "name": "Apollo Hospital Mumbai",
                    "address": "Bandra, Mumbai",
                    "phone": "+91-22-5645-5645",
                    "specialties": ["Multi-specialty", "Orthopedics", "Pediatrics"],
                    "rating": 4.8,
                    "distance": "3.2 km"
                }
            ],
            "bangalore": [
                {
                    "name": "Apollo Hospital Bangalore",
                    "address": "Bannerghatta Road, Bangalore",
                    "phone": "+91-80-4000-4000",
                    "specialties": ["Multi-specialty", "Cardiology", "Neurology"],
                    "rating": 4.7,
                    "distance": "2.8 km"
                },
                {
                    "name": "Manipal Hospital",
                    "address": "Whitefield, Bangalore",
                    "phone": "+91-80-4159-9999",
                    "specialties": ["Multi-specialty", "Oncology", "Emergency"],
                    "rating": 4.6,
                    "distance": "4.1 km"
                }
            ]
        }
        
        location_lower = location.lower()
        hospitals = hospitals_db.get(location_lower, [])
        
        # Filter by specialty if provided
        if specialty:
            specialty_lower = specialty.lower()
            hospitals = [h for h in hospitals if any(specialty_lower in s.lower() for s in h.get('specialties', []))]
        
        if not hospitals:
            return jsonify({
                "success": True,
                "hospitals": [],
                "message": f"No hospitals found in {location}. Please try nearby cities or provide more details."
            })
        
        user_id = get_user_id()
        add_to_history(user_id, f"Find hospitals in {location}", f"Found {len(hospitals)} hospitals")
        
        return jsonify({
            "success": True,
            "hospitals": hospitals,
            "count": len(hospitals),
            "location": location
        })
    
    except Exception as e:
        print(f"Hospital search error: {e}")
        return jsonify({"error": "Failed to find hospitals. Please try again."}), 500


# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
