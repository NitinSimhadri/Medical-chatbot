# MediBot AI - Complete Medical Chatbot

A professional medical chatbot application built with Flask, featuring AI-powered medical assistance, user authentication, modern UI design, and comprehensive healthcare services.

## Features

### 🤖 AI-Powered Medical Assistant
- RAG (Retrieval-Augmented Generation) using LangChain and Pinecone
- Groq LLM integration for fast, accurate responses
- Intelligent conversation handling with emergency detection
- Medical knowledge base with safety disclaimers

### 🔐 User Authentication
- Secure user registration and login
- Session management with Flask sessions
- Password hashing with Werkzeug
- Protected routes for authenticated users

### 🎨 Modern UI Design
- Clean, professional interface inspired by medibot-ai.com
- Dark/Light theme toggle
- Responsive design for all devices
- Smooth animations and transitions
- Font Awesome icons and Inter font

### 🏥 Healthcare Services
- **Symptom Checker**: AI-powered symptom analysis
- **BP & Heart Rate Monitor**: Blood pressure tracking
- **BMI Calculator**: Body mass index calculation
- **Diet Planner**: Personalized nutrition guidance
- **Skin & Hair Care**: Dermatology advice
- **Appointment Booking**: Doctor appointment scheduling
- **Health Vault**: Personal health data storage

### 📱 Additional Features
- Chat history tracking
- Quick action buttons
- Typing indicators
- Error handling and validation
- Mobile-responsive design

## Tech Stack

- **Backend**: Flask (Python web framework)
- **AI/ML**: LangChain, Pinecone, Groq LLM
- **Frontend**: HTML5, CSS3, JavaScript, jQuery
- **Database**: JSON file storage (users, chat history)
- **Styling**: Custom CSS with CSS Variables
- **Icons**: Font Awesome 6
- **Fonts**: Inter (Google Fonts)

## Installation

### Prerequisites
- Python 3.8+
- Conda environment (recommended)

### Setup Steps

1. **Clone or download the repository**
   ```bash
   git clone https://github.com/entbappy/Build-a-Complete-Medical-Chatbot-with-LLMs-LangChain-Pinecone-Flask-AWS.git
   cd Build-a-Complete-Medical-Chatbot-with-LLMs-LangChain-Pinecone-Flask-AWS-main
   ```

2. **Create and activate conda environment**
   ```bash
   conda create -n medibot python=3.11 -y
   conda activate medibot
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   PINECONE_API_KEY=your_pinecone_api_key
   GROQ_API_KEY=your_groq_api_key
   SECRET_KEY=your_secret_key_here
   ```

5. **Store embeddings to Pinecone** (if not already done)
   ```bash
   python store_index.py
   ```

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the application**
   
   Open your browser and go to: `http://localhost:8080`

## Configuration

### API Keys Required

1. **Pinecone API Key**
   - Sign up at [pinecone.io](https://pinecone.io)
   - Create a new index named "medical-chatbot"
   - Get your API key from the dashboard

2. **Groq API Key**
   - Sign up at [groq.com](https://groq.com)
   - Generate an API key from your dashboard

3. **Secret Key**
   - Generate a random secret key for Flask sessions
   - Use a long, random string for security

### Environment Variables

The application uses the following environment variables:

- `PINECONE_API_KEY`: Your Pinecone API key
- `GROQ_API_KEY`: Your Groq API key
- `SECRET_KEY`: Flask secret key for sessions

## Usage

### First Time Setup
1. Visit the application URL
2. Click "Register" to create a new account
3. Login with your credentials
4. Start chatting with the medical assistant

### Demo Account
For testing purposes, you can use:
- **Username**: demo
- **Password**: demo123

### Using the Chatbot
- Type your health-related questions in the chat input
- Use quick action buttons for specific services
- The bot will provide medical information and route you to appropriate services
- Emergency situations are automatically detected and flagged

### Healthcare Services
Access various health services through the sidebar or by asking the chatbot:
- Symptom analysis and advice
- Vital signs monitoring
- BMI calculations
- Diet planning
- Skin care recommendations
- Doctor appointment booking
- Health data storage

## Deployment

### Local Development
```bash
python app.py
```

### Production Deployment
For production deployment, consider:
- Using a production WSGI server (Gunicorn, uWSGI)
- Setting up a reverse proxy (Nginx)
- Using environment-specific configuration
- Implementing proper logging
- Setting up monitoring and alerts

### Cloud Deployment Options
- **AWS**: Elastic Beanstalk, EC2, or Lambda
- **Google Cloud**: App Engine or Cloud Run
- **Azure**: App Service
- **Heroku**: Direct deployment
- **DigitalOcean**: App Platform

## Security Considerations

- **Passwords**: Hashed using Werkzeug's secure hashing
- **Sessions**: Flask session management with secret key
- **Input Validation**: Basic input sanitization
- **Rate Limiting**: Not implemented (consider adding for production)
- **HTTPS**: Required for production deployment
- **API Keys**: Stored securely in environment variables

## Medical Disclaimer

This application is for informational purposes only and is not a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of qualified healthcare providers with questions about medical conditions.

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python version compatibility

2. **API Key Errors**
   - Verify API keys in `.env` file
   - Check API key validity and quotas

3. **Chat Not Working**
   - Check browser console for JavaScript errors
   - Verify Pinecone index exists and has data
   - Check Groq API connectivity

4. **Theme Not Switching**
   - Clear browser cache
   - Check localStorage support

5. **Registration/Login Issues**
   - Check file permissions for `users.json`
   - Verify password requirements

### Debug Mode

Run with debug mode for development:
```bash
python app.py  # debug=True by default
```

## Future Enhancements

- [ ] Real database integration (PostgreSQL/MongoDB)
- [ ] User profile management
- [ ] Advanced analytics and reporting
- [ ] Multi-language support
- [ ] Voice input/output
- [ ] Integration with wearable devices
- [ ] Telemedicine appointment booking
- [ ] Medical report generation
- [ ] Emergency contact integration


### Techstack Used:

- Python
- LangChain
- Flask
- GPT
- Pinecone



# AWS-CICD-Deployment-with-Github-Actions

## 1. Login to AWS console.

## 2. Create IAM user for deployment

	#with specific access

	1. EC2 access : It is virtual machine

	2. ECR: Elastic Container registry to save your docker image in aws


	#Description: About the deployment

	1. Build docker image of the source code

	2. Push your docker image to ECR

	3. Launch Your EC2 

	4. Pull Your image from ECR in EC2

	5. Lauch your docker image in EC2

	#Policy:

	1. AmazonEC2ContainerRegistryFullAccess

	2. AmazonEC2FullAccess

	
## 3. Create ECR repo to store/save docker image
    - Save the URI: 315865595366.dkr.ecr.us-east-1.amazonaws.com/medicalbot

	
## 4. Create EC2 machine (Ubuntu) 

## 5. Open EC2 and Install docker in EC2 Machine:
	
	
	#optinal

	sudo apt-get update -y

	sudo apt-get upgrade
	
	#required

	curl -fsSL https://get.docker.com -o get-docker.sh

	sudo sh get-docker.sh

	sudo usermod -aG docker ubuntu

	newgrp docker
	
# 6. Configure EC2 as self-hosted runner:
    setting>actions>runner>new self hosted runner> choose os> then run command one by one


# 7. Setup github secrets:

   - AWS_ACCESS_KEY_ID
   - AWS_SECRET_ACCESS_KEY
   - AWS_DEFAULT_REGION
   - ECR_REPO
   - PINECONE_API_KEY
   - OPENAI_API_KEY
