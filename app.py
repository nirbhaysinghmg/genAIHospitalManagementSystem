import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

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

from langchain.prompts import PromptTemplate
import json
import time
from collections import defaultdict
import sqlite3
import json as json_lib
from datetime import datetime

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

# Prepare embeddings
EMBED_MODEL = os.getenv("EMBED_MODEL", "models/embedding-001")
embeddings = GoogleGenerativeAIEmbeddings(model=EMBED_MODEL, google_api_key=os.getenv("GEMINI_API_KEY"))

# Initialize ChromaDB vector store
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "chroma_db")

def get_vector_store():
    # Check if vector store already exists
    if os.path.exists(PERSIST_DIRECTORY):
        print("Loading existing vector store...")
        return Chroma(
            persist_directory=PERSIST_DIRECTORY,
            embedding_function=embeddings
        )
    else:
        print("Creating new vector store...")
        # Load and process CSV only when creating new vector store
        df = pd.read_csv(CSV_PATH)
        print(f"CSV columns: {df.columns.tolist()}")
        print(f"CSV shape: {df.shape}")
        print(f"First row: {df.iloc[0].to_dict()}")

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
        
        # Generate unique IDs for documents
        ids = [str(uuid.uuid4()) for _ in documents]
        
        vector_store = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=PERSIST_DIRECTORY,
            ids=ids
        )
        # Persist the vector store
        return vector_store

# Initialize vector store
vector_store = get_vector_store()

# Initialize LLM
llm = ChatGoogleGenerativeAI(
    model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    disable_streaming=True  # Changed from streaming=False
)

# Define system prompt
SYSTEM_PROMPT = PromptTemplate(
    input_variables=["context", "question", "chat_history"],
    template="""You are a helpful hospital information assistant. Your role is to:
1. Provide accurate and concise information about hospital services, facilities, and procedures
2. If user say to Schedule an appointment, then you should say that you can schedule an appointment by filling the form i am giving you below, Do not provide any other infomation, do not create your own form cause we will make the form appear from the frontend website.
3. Be professional and empathetic in your responses
4. If you don't know something, admit it and suggest contacting the hospital directly
5. Focus on factual information from the provided hospital data
6. Format your responses in a clear, easy-to-read manner
6. When discussing medical conditions or treatments, always include a disclaimer about consulting healthcare professionals
7. For appointment-related queries, guide users to use the appointment scheduling feature

Remember to:
- Stay within the scope of the information provided in the hospital data
- Be clear about what information is available and what isn't
- Maintain patient confidentiality
- Provide practical, actionable information

Context: {context}
Chat History: {chat_history}
Question: {question}

Answer:"""
)

# Store chat histories for different sessions
chat_histories = {}

# Add analytics storage
user_analytics = defaultdict(lambda: {
    "sessions": 0,
    "chatbot_opens": 0, 
    "questions_asked": 0,
    "last_active": None,
    "session_history": []
})

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
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": SYSTEM_PROMPT}
    )
    
    try:
        # Get answer using chat history
        result = qa({
            "question": req.question,
            "chat_history": chat_histories[session_id]
        })
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

# Initialize SQLite database for analytics
def init_analytics_db():
    conn = sqlite3.connect('analytics.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        sessions INTEGER DEFAULT 0,
        chatbot_opens INTEGER DEFAULT 0,
        questions_asked INTEGER DEFAULT 0,
        last_active TEXT,
        created_at TEXT
    )
    ''')
    
    # Create sessions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT,
        start_time TEXT,
        end_time TEXT,
        questions INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Create events table for detailed analytics
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        session_id TEXT,
        event_type TEXT,
        event_data TEXT,
        timestamp TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    ''')
    
    conn.commit()
    conn.close()
    print("Analytics database initialized")

# Call the initialization function
init_analytics_db()

# In-memory cache for active sessions
active_sessions = {}
chat_histories = {}

# Helper functions for database operations
def get_db_connection():
    conn = sqlite3.connect('analytics.db')
    conn.row_factory = sqlite3.Row
    return conn

def record_user_event(user_id, session_id, event_type, event_data=None):
    if not user_id:
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    timestamp = datetime.now().isoformat()
    
    if not user:
        # Create new user
        cursor.execute(
            "INSERT INTO users (user_id, sessions, chatbot_opens, questions_asked, last_active, created_at) VALUES (?, 0, 0, 0, ?, ?)",
            (user_id, timestamp, timestamp)
        )
    
    # Update user stats based on event type
    if event_type == "session_start":
        cursor.execute("UPDATE users SET sessions = sessions + 1, last_active = ? WHERE user_id = ?", 
                      (timestamp, user_id))
        
        # Record session
        cursor.execute(
            "INSERT INTO sessions (session_id, user_id, start_time, questions) VALUES (?, ?, ?, 0)",
            (session_id, user_id, timestamp)
        )
    elif event_type == "chatbot_opened":
        cursor.execute("UPDATE users SET chatbot_opens = chatbot_opens + 1, last_active = ? WHERE user_id = ?", 
                      (timestamp, user_id))
    elif event_type == "question_asked":
        cursor.execute("UPDATE users SET questions_asked = questions_asked + 1, last_active = ? WHERE user_id = ?", 
                      (timestamp, user_id))
        
        # Update session question count
        cursor.execute("UPDATE sessions SET questions = questions + 1 WHERE session_id = ?", 
                      (session_id,))
    elif event_type == "session_end":
        cursor.execute("UPDATE sessions SET end_time = ? WHERE session_id = ?", 
                      (timestamp, session_id))
    
    # Record the event with details
    event_data_json = json_lib.dumps(event_data) if event_data else None
    cursor.execute(
        "INSERT INTO events (user_id, session_id, event_type, event_data, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, event_type, event_data_json, timestamp)
    )
    
    conn.commit()
    conn.close()

# WebSocket endpoint at /ws
@app.websocket("/ws")
async def websocket_endpoint_ws(websocket: WebSocket):
    try:
        print("New WebSocket connection attempt...")
        await websocket.accept()
        print("WebSocket connection accepted")
        
        # Create a unique session ID for this WebSocket connection
        session_id = str(uuid.uuid4())
        user_id = None
        chat_histories[session_id] = []
        print(f"Created new session: {session_id}")
        
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                print(f"Received message from client: {data[:100]}...")  # Log first 100 chars
                message = json.loads(data)
                
                # Extract user_id from message
                if "user_id" in message:
                    user_id = message["user_id"]
                
                # Handle analytics events
                if "type" in message and message["type"] == "analytics":
                    analytics_data = message["data"]
                    event_user_id = analytics_data.get("userId", user_id)
                    event_session_id = analytics_data.get("sessionId", session_id)
                    
                    if event_user_id:
                        # Record the event in the database
                        action = analytics_data.get("action")
                        print(f"Recording analytics event: {action} for user {event_user_id}")
                        record_user_event(
                            event_user_id, 
                            event_session_id, 
                            action, 
                            analytics_data
                        )
                        print(f"Recorded {action} event for user {event_user_id}")
                        
                        # Send confirmation back to client
                        await websocket.send_json({
                            "type": "analytics_confirmation",
                            "event": action,
                            "status": "recorded"
                        })
                        continue
                
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
                        return_source_documents=True,
                        combine_docs_chain_kwargs={"prompt": SYSTEM_PROMPT}
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
                if user_id:
                    record_user_event(user_id, session_id, "session_end")
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

# Update analytics endpoints to use the database
@app.get("/analytics")
async def get_analytics():
    conn = get_db_connection()
    
    # Get total users
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
    
    # Get total sessions
    total_sessions = conn.execute("SELECT SUM(sessions) as count FROM users").fetchone()["count"] or 0
    
    # Get total questions
    total_questions = conn.execute("SELECT SUM(questions_asked) as count FROM users").fetchone()["count"] or 0
    
    # Get total chatbot opens
    total_opens = conn.execute("SELECT SUM(chatbot_opens) as count FROM users").fetchone()["count"] or 0
    
    # Get all users with their stats
    users = conn.execute("SELECT * FROM users").fetchall()
    users_data = {}
    
    for user in users:
        user_id = user["user_id"]
        # Get user's sessions
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY start_time DESC", 
            (user_id,)
        ).fetchall()
        
        sessions_data = []
        for session in sessions:
            sessions_data.append({
                "session_id": session["session_id"],
                "start_time": session["start_time"],
                "end_time": session["end_time"],
                "questions": session["questions"]
            })
        
        users_data[user_id] = {
            "sessions": user["sessions"],
            "chatbot_opens": user["chatbot_opens"],
            "questions_asked": user["questions_asked"],
            "last_active": user["last_active"],
            "created_at": user["created_at"],
            "session_history": sessions_data
        }
    
    conn.close()
    
    return {
        "total_users": total_users,
        "total_sessions": total_sessions,
        "total_questions": total_questions,
        "total_chatbot_opens": total_opens,
        "users": users_data
    }

@app.get("/analytics/{user_id}")
async def get_user_analytics(user_id: str):
    conn = get_db_connection()
    
    # Get user data
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user's sessions
    sessions = conn.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY start_time DESC", 
        (user_id,)
    ).fetchall()
    
    sessions_data = []
    for session in sessions:
        # Get events for this session
        events = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp", 
            (session["session_id"],)
        ).fetchall()
        
        events_data = []
        for event in events:
            event_data = None
            if event["event_data"]:
                try:
                    event_data = json_lib.loads(event["event_data"])
                except:
                    event_data = event["event_data"]
                    
            events_data.append({
                "type": event["event_type"],
                "timestamp": event["timestamp"],
                "data": event_data
            })
        
        sessions_data.append({
            "session_id": session["session_id"],
            "start_time": session["start_time"],
            "end_time": session["end_time"],
            "questions": session["questions"],
            "events": events_data
        })
    
    user_data = {
        "user_id": user["user_id"],
        "sessions": user["sessions"],
        "chatbot_opens": user["chatbot_opens"],
        "questions_asked": user["questions_asked"],
        "last_active": user["last_active"],
        "created_at": user["created_at"],
        "session_history": sessions_data
    }
    
    conn.close()
    
    return user_data

class Person:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def greet(self):
        print("Hello my name is {self,name} and age is ")

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
















