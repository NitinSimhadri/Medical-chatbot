from flask import Flask, render_template, request
from dotenv import load_dotenv
import os

from src.helper import download_hugging_face_embeddings
from src.prompt import system_prompt

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
# Env vars
# --------------------------------------------------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not PINECONE_API_KEY:
    raise RuntimeError("PINECONE_API_KEY missing")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY missing")

# --------------------------------------------------
# Embeddings (already downloaded at BUILD time)
# --------------------------------------------------
print("✅ Loading embeddings")
embeddings = download_hugging_face_embeddings()

# --------------------------------------------------
# Vector store
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
# Groq LLM
# --------------------------------------------------
chat_model = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant",
    temperature=0,
    timeout=60
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}")
    ]
)

qa_chain = create_stuff_documents_chain(
    llm=chat_model,
    prompt=prompt
)

rag_chain = create_retrieval_chain(
    retriever,
    qa_chain
)

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.route("/")
def index():
    return render_template("chat.html")

@app.route("/get", methods=["POST"])
def chat():
    msg = request.form["msg"]
    response = rag_chain.invoke({"input": msg})
    return response["answer"]

@app.route("/health")
def health():
    return {"status": "ok"}, 200

# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
