from dotenv import load_dotenv
import os

from src.helper import (
    load_pdf_file,
    filter_to_minimal_docs,
    text_split,
    download_hugging_face_embeddings
)

from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------
load_dotenv(override=True)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not PINECONE_API_KEY:
    raise ValueError("❌ PINECONE_API_KEY not found")


# --------------------------------------------------
# Load & process documents
# --------------------------------------------------
extracted_data = load_pdf_file(data="data/")
filter_data = filter_to_minimal_docs(extracted_data)
text_chunks = text_split(filter_data)


# --------------------------------------------------
# Embeddings (HuggingFace – LOCAL, FREE)
# --------------------------------------------------
embeddings = download_hugging_face_embeddings()


# --------------------------------------------------
# Pinecone init
# --------------------------------------------------
pc = Pinecone(api_key=PINECONE_API_KEY)

index_name = "medical-chatbot"

if not pc.has_index(index_name):
    pc.create_index(
        name=index_name,
        dimension=384,               # MUST match embedding dimension
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        ),
    )

index = pc.Index(index_name)


# --------------------------------------------------
# Store embeddings in Pinecone
# --------------------------------------------------
docsearch = PineconeVectorStore.from_documents(
    documents=text_chunks,
    index_name=index_name,
    embedding=embeddings,
)

print("✅ Documents successfully indexed into Pinecone")
