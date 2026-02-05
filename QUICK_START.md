# 🚀 Quick Start Commands

## Copy-Paste Ready Commands

### 1️⃣ Create Conda Environment
```bash
conda create -n medibot python=3.11 -y
```

### 2️⃣ Activate Environment
```bash
conda activate medibot
```

### 3️⃣ Navigate to Project
```bash
cd "c:\Users\sreeju\Downloads\Build-a-Complete-Medical-Chatbot-with-LLMs-LangChain-Pinecone-Flask-AWS-main"
```

### 4️⃣ Install All Dependencies
```bash
pip install -r requirements.txt
```

### 5️⃣ Run the Application
```bash
python app.py
```

### 6️⃣ Access in Browser
```
http://localhost:8080
```

---

## 🔑 API Keys You Need

### Get Pinecone API Key
1. Visit https://app.pinecone.io
2. Sign up / Log in
3. Create index: `medical-chatbot`
4. Copy API key

### Get Groq API Key
1. Visit https://console.groq.com
2. Sign up / Log in
3. Create API key
4. Copy key

### Generate Secret Key
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📝 Create .env File

**Location**: Same folder as `app.py`

**Content**:
```env
PINECONE_API_KEY=your_pinecone_key_here
GROQ_API_KEY=your_groq_key_here
SECRET_KEY=your_secret_key_from_above
```

**Save and close**

---

## ✅ Testing After Running

### 1. Login
- URL: http://localhost:8080/login
- Test account: demo / demo123
- Or create new account

### 2. Test Theme Toggle
- Click moon/sun icon
- Theme should change
- Refresh → theme persists

### 3. Test Chat
- Type a message
- Send
- Bot should respond

### 4. Test Services
- Click any service in sidebar
- Page should load
- Theme should work

---

## 🔍 Troubleshooting Commands

### Check Python Version
```bash
python --version
```

### Check Installed Packages
```bash
pip list
```

### Install Specific Package
```bash
pip install package-name
```

### Clear Cache
```bash
# For Python
python -m pip cache purge

# For conda
conda clean --all
```

### Force Reinstall
```bash
pip install --force-reinstall -r requirements.txt
```

---

## 📊 App Status

### Running Indicators
✓ Flask starting...
✓ Using Groq model: llama-3.1-8b-instant
✓ * Running on http://0.0.0.0:8080
✓ * WARNING in production mode

### Common Errors & Solutions

**Error**: ModuleNotFoundError
```bash
# Solution:
pip install -r requirements.txt
```

**Error**: API Key not found
```bash
# Solution:
# Check .env file exists and has correct keys
# Make sure you're in the right directory
```

**Error**: Port 8080 in use
```bash
# Solution 1: Kill process
# Solution 2: Change port in app.py
# Change: app.run(..., port=8080)
# To: app.run(..., port=5000)
```

**Error**: Theme not working
```bash
# Solution:
# Clear browser cache (Ctrl+Shift+Del)
# Check localStorage is enabled
# Restart browser
```

---

## 🎯 Key URLs

| Page | URL | Status |
|------|-----|--------|
| Home | http://localhost:8080 | Redirects to chat/login |
| Login | http://localhost:8080/login | ✓ Working |
| Chat | http://localhost:8080/chat | ✓ Working |
| About | http://localhost:8080/about | ✓ Working |
| Disclaimer | http://localhost:8080/disclaimer | ✓ Working |
| Medication | http://localhost:8080/services/medication | ✓ NEW |
| Prescription | http://localhost:8080/services/prescription | ✓ NEW |
| Summarizer | http://localhost:8080/services/summarizer | ✓ NEW |
| Vitals | http://localhost:8080/services/vitals | ✓ NEW |
| Reminder | http://localhost:8080/services/reminder | ✓ NEW |
| History | http://localhost:8080/services/history | ✓ NEW |
| BMI | http://localhost:8080/services/bmi | ✓ Existing |
| BP/HR | http://localhost:8080/services/bp-hr | ✓ Existing |
| Diet | http://localhost:8080/services/diet | ✓ Existing |
| Skin | http://localhost:8080/services/skin | ✓ Existing |
| Symptom | http://localhost:8080/services/symptom | ✓ Existing |
| Appointment | http://localhost:8080/services/appointment | ✓ Existing |
| Health Vault | http://localhost:8080/services/health_vault | ✓ Existing |

---

## 🛠️ Advanced Commands

### Stop Server
```
Press Ctrl+C in terminal
```

### Run with Different Port
Edit app.py:
```python
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)  # Change 5000 to your port
```

### Run in Production Mode
```bash
gunicorn --workers 4 --timeout 120 app:app
```

### Check if Port is Open
```bash
netstat -ano | findstr :8080  # Windows
lsof -i :8080  # Mac/Linux
```

---

## 📦 File Locations

| File | Location |
|------|----------|
| Main App | `app.py` |
| Chat Page | `templates/chat.html` |
| Dependencies | `requirements.txt` |
| API Keys | `.env` |
| Users Data | `users.json` |
| Chat History | `user_history.json` |
| Services | `templates/services/*.html` |

---

## 🚀 Deployment Quick Links

### AWS
- Console: https://aws.amazon.com/console/
- Elastic Beanstalk: https://console.aws.amazon.com/elasticbeanstalk/

### Google Cloud
- Console: https://console.cloud.google.com/
- Cloud Run: https://console.cloud.google.com/run/

### Azure
- Portal: https://portal.azure.com/
- App Service: https://portal.azure.com/#create/Microsoft.AppServiceWebApp

### Heroku
- Dashboard: https://dashboard.heroku.com/
- CLI: https://devcenter.heroku.com/articles/heroku-cli/

---

## 📚 Useful Commands Reference

```bash
# List all conda environments
conda env list

# List all installed packages
pip list

# Upgrade pip
python -m pip install --upgrade pip

# Check Python path
python -c "import sys; print(sys.executable)"

# Check Flask version
python -c "import flask; print(flask.__version__)"

# Generate requirements file
pip freeze > requirements.txt

# Install from requirements
pip install -r requirements.txt

# Create new Python file
type nul > new_file.py  # Windows
touch new_file.py       # Mac/Linux

# View current directory
cd  # Windows
pwd # Mac/Linux
```

---

## ✨ Success Indicators

When everything is working:
✓ Server starts without errors
✓ Can access http://localhost:8080
✓ Login page loads
✓ Can create account / login
✓ Chat page loads with sidebar
✓ Theme toggle works
✓ All services load
✓ Can send chat messages
✓ Bot responds

---

## 🎓 Next Steps

1. ✅ Setup conda environment
2. ✅ Install dependencies
3. ✅ Create .env file
4. ✅ Run app
5. ✅ Test all features
6. ✅ Test theme toggle
7. ✅ Try all services
8. ✅ Send test messages
9. ✅ Deploy to cloud

---

## 📞 Emergency Fixes

### App won't start?
```bash
# Check Python installation
python --version

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Check for syntax errors
python -m py_compile app.py
```

### Theme toggle not working?
```
1. Open Developer Tools (F12)
2. Go to Application → LocalStorage
3. Look for key 'medibot-theme'
4. Clear if corrupted
5. Refresh page
```

### Chat not responding?
```
1. Check .env file exists with API keys
2. Test API keys on Groq console
3. Check internet connection
4. Restart app
```

### Services not loading?
```
1. Check service HTML file exists
2. Check route in app.py
3. Check HTML file has no syntax errors
4. Clear browser cache
```

---

## 🎉 Ready to Go!

Everything is set up and ready to run. Just:

1. Copy the commands above
2. Run them in order
3. Open browser
4. Enjoy your medical chatbot!

**Questions?** Check the console output for error messages.

---

**Version**: 2.0
**Last Updated**: February 5, 2026
**Status**: ✅ Ready to Deploy
