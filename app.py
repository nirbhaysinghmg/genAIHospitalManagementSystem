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
from langchain.chains import ConversationalRetrievalChain
from langchain_core.documents import Document
import json

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Initialize FastAPI with WebSocket support
app = FastAPI(title="Google Gen AI RAG App with ChromaDB")

# Add CORS middleware with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Store chat histories for different sessions
chat_histories = {}

# Pydantic model for query
class QueryRequest(BaseModel):
    question: str
    session_id: str = None

@app.post("/query")
async def query_qa(req: QueryRequest):
    # Build retriever
    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
    
    # Use session_id to maintain separate chat histories
    session_id = req.session_id or "default"
    
    if session_id not in chat_histories:
        chat_histories[session_id] = []
    
    # Use ConversationalRetrievalChain instead of RetrievalQA
    qa = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True
    )
    
    try:
        # Get answer using chat history
        result = qa({"question": req.question, "chat_history": chat_histories[session_id]})
        answer = result["answer"]
        
        # Update chat history with the new Q&A pair
        chat_histories[session_id].append((req.question, answer))
        
        # Limit chat history length to prevent context overflow
        if len(chat_histories[session_id]) > 10:
            chat_histories[session_id] = chat_histories[session_id][-10:]
        
        # Get source documents
        source_docs = result.get("source_documents", [])
        sources = [doc.metadata["source"] for doc in source_docs]
        
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint at /ws
@app.websocket("/ws")
async def websocket_endpoint_ws(websocket: WebSocket):
    try:
        print("New WebSocket connection attempt...")
        await websocket.accept()
        print("WebSocket connection accepted")
        
        # Create a unique session ID for this WebSocket connection
        session_id = str(uuid.uuid4())
        chat_histories[session_id] = []
        print(f"Created new session: {session_id}")
        
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                print(f"Received message from client: {data[:100]}...")  # Log first 100 chars
                message = json.loads(data)
                
                # Process the message
                if "user_input" in message:
                    print(f"Processing user input: {message['user_input'][:50]}...")
                    
                    # Get chat history from message
                    chat_history = message.get("chat_history", [])
                    if chat_history:
                        # Convert the chat history to the format expected by the chain
                        formatted_history = [(msg["content"], "") for msg in chat_history if msg["role"] == "user"]
                        chat_histories[session_id] = formatted_history
                    
                    # Build retriever
                    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                    
                    # Use ConversationalRetrievalChain
                    qa = ConversationalRetrievalChain.from_llm(
                        llm=llm,
                        retriever=retriever,
                        return_source_documents=True
                    )
                    
                    try:
                        # Get answer using chat history
                        result = qa({
                            "question": message["user_input"],
                            "chat_history": chat_histories[session_id]
                        })
                        answer = result["answer"]
                        
                        # Update chat history
                        chat_histories[session_id].append((message["user_input"], answer))
                        
                        # Limit chat history length
                        if len(chat_histories[session_id]) > 10:
                            chat_histories[session_id] = chat_histories[session_id][-10:]
                        
                        # Get source documents
                        source_docs = result.get("source_documents", [])
                        sources = [doc.metadata["source"] for doc in source_docs]
                        
                        # Send response back to client
                        response = {
                            "text": answer,
                            "sources": sources,
                            "done": True
                        }
                        await websocket.send_json(response)
                        print(f"Response sent successfully for session {session_id}")
                        
                    except Exception as e:
                        error_msg = f"Error processing request: {str(e)}"
                        print(error_msg)
                        await websocket.send_json({
                            "error": error_msg,
                            "done": True
                        })
            except WebSocketDisconnect:
                print(f"WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                print(f"Error in WebSocket loop: {str(e)}")
                await websocket.send_json({
                    "error": f"Internal server error: {str(e)}",
                    "done": True
                })
                break
    except Exception as e:
        print(f"Fatal WebSocket error: {str(e)}")
    finally:
        print(f"Cleaning up session {session_id}")
        if session_id in chat_histories:
            del chat_histories[session_id]
        try:
            await websocket.close()
        except:
            pass

# Keep the original endpoint for backward compatibility
@app.websocket("/ws/chat")
async def websocket_endpoint_chat(websocket: WebSocket):
    await websocket_endpoint_ws(websocket)

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)














