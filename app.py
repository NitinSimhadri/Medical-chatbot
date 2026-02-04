from flask import Flask, render_template, request
from dotenv import load_dotenv
import os

from src.helper import download_hugging_face_embeddings
from src.prompt import *

from langchain_pinecone import PineconeVectorStore
from langchain_groq import ChatGroq
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate


# --------------------------------------------------
# App init
# --------------------------------------------------
app = Flask(__name__)

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
# Routes
# --------------------------------------------------
@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html")


# Services pages (simple client-side pages)
@app.route("/services/<service>")
def services(service):
    allowed = {
        "bp-hr": "services/bp_hr.html",
        "bmi": "services/bmi.html",
        "diet": "services/diet.html",
        "skin": "services/skin.html",
        "more": "services/more.html",
        "symptom": "services/symptom.html",
    }
    tpl = allowed.get(service)
    if not tpl:
        return render_template("404.html"), 404
    return render_template(tpl)


@app.route("/get", methods=["POST"])
def chat():
    msg = request.form["msg"]
    print("User:", msg)

    response = rag_chain.invoke({"input": msg})
    answer = response["answer"]

    print("Bot:", answer)
    return answer


# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
