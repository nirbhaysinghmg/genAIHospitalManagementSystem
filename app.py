import os
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.documents import Document
import json

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Initialize FastAPI with WebSocket support
app = FastAPI(title="Google Gen AI RAG App with ChromaDB")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Load CSV into DataFrame
CSV_PATH = os.getenv("CSV_PATH", "data/hospital_data.csv")
print(f"Current working directory: {os.getcwd()}")
print(f"Looking for CSV at: {CSV_PATH}")
print(f"File exists: {os.path.exists(CSV_PATH)}")
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"CSV file not found at {CSV_PATH}")
df = pd.read_csv(CSV_PATH)

# Print CSV structure for debugging
print(f"CSV columns: {df.columns.tolist()}")
print(f"CSV shape: {df.shape}")
print(f"First row: {df.iloc[0].to_dict()}")

# Prepare embeddings
EMBED_MODEL = os.getenv("EMBED_MODEL", "models/embedding-001")
embeddings = GoogleGenerativeAIEmbeddings(model=EMBED_MODEL, google_api_key=os.getenv("GEMINI_API_KEY"))

# Split text into chunks
splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

# Process all columns of the CSV
documents = []
for idx, row in df.iterrows():
    # Convert the entire row to a string representation
    row_dict = row.to_dict()
    content = "\n".join([f"{k}: {v}" for k, v in row_dict.items()])
    
    # Use the first column as the source identifier
    source = str(row.iloc[0])
    
    # Split the content into chunks
    chunks = splitter.split_text(content)
    for chunk in chunks:
        documents.append(Document(page_content=chunk, metadata={"source": source, "row": idx}))

print(f"Created {len(documents)} document chunks")

# Initialize ChromaDB vector store
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "chroma_db")

# Generate unique IDs for documents
ids = [str(uuid.uuid4()) for _ in documents]

vector_store = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
    persist_directory=PERSIST_DIRECTORY,
    ids=ids  # Pass IDs explicitly
)

# Initialize LLM
llm = ChatGoogleGenerativeAI(
    model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    disable_streaming=True  # Changed from streaming=False
)

# Pydantic model for query
class QueryRequest(BaseModel):
    question: str

@app.post("/query")
async def query_qa(req: QueryRequest):
    # Build retriever
    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
    qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=retriever)
    try:
        answer = qa.run(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"answer": answer, "sources": [doc.metadata["source"] for doc in retriever.get_relevant_documents(req.question)]}

# WebSocket endpoint at /ws
@app.websocket("/ws")
async def websocket_endpoint_ws(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Process the message
            if "user_input" in message:
                # Build retriever
                retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=retriever)
                
                try:
                    # Get answer from RAG
                    answer = qa.run(message["user_input"])
                    
                    # Send response back to client
                    await websocket.send_json({
                        "text": answer,
                        "sources": [doc.metadata["source"] for doc in retriever.get_relevant_documents(message["user_input"])],
                        "done": True  # Add this flag to indicate response is complete
                    })
                    
                    # Add a debug message to confirm the response was sent
                    print(f"Response sent with done=True flag for: {message['user_input'][:50]}...")
                    
                except Exception as e:
                    await websocket.send_json({
                        "error": f"Error processing your request: {str(e)}",
                        "done": True  # Also add for error responses
                    })
                    print(f"Error response sent: {str(e)}")
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
    finally:
        await websocket.close()

# Keep the original endpoint for backward compatibility
@app.websocket("/ws/chat")
async def websocket_endpoint_chat(websocket: WebSocket):
    await websocket_endpoint_ws(websocket)

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)













