import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import uuid
from analytics import generate_short_id, generate_user_id, record_user_event, execute_query
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body
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
import mysql.connector
from mysql.connector import Error
import json as json_lib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import hashlib
from analytics import router as analytics_router

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Initialize FastAPI with WebSocket support
app = FastAPI(title="Google Gen AI RAG App with ChromaDB")

# Add CORS middleware with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load CSV into DataFrame
CSV_PATH = os.getenv("CSV_PATH")
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
            # source = str(row.iloc[0])
            
            # Split the content into chunks
            chunks = splitter.split_text(content)
            for chunk in chunks:
                documents.append(Document(page_content=chunk))

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
    template="""You are a helpful tyre information assistant for Apollo Tyres. Your role is to:
1. Help users find the best tyres for their vehicle (car, SUV, van, bike, scooter, truck, bus, agricultural, industrial, earthmover, etc.).
2. Provide accurate and concise information about tyre brands, types, rim sizes, and featured products.
3. Guide users to explore popular brands (e.g., Maruti Suzuki, Hyundai, Hero, Royal Enfield), body types (SUV, sedan, hatchback, etc.), and bike segments (sport touring, city urban, etc.).
4. If the user asks for a product, show relevant Apollo Tyres products or guide them to the right category.
5. Be professional, clear, and helpful in your responses.
6. If you don't know something, admit it and suggest contacting Apollo Tyres directly for more information.
7. Mention Apollo Tyres' social media for the latest updates and events.
8. Focus only on factual tyre and product information from the provided data.
9. Never provide medical or hospital information.
10. When discussing tyre installation or compatibility, always include a disclaimer to consult a tyre expert or authorized dealer.

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
        # return_source_documents=True,
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
        # source_docs = result.get("source_documents", [])
        # sources = [doc.metadata["source"] for doc in source_docs]
        
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Register the analytics router
app.include_router(analytics_router)

@app.websocket("/ws")
async def websocket_endpoint_ws(websocket: WebSocket):
    try:
        print("New WebSocket connection attempt...")
        await websocket.accept()
        print("WebSocket connection accepted")
        
        # Create a unique session ID for this WebSocket connection
        session_id = generate_short_id()
        user_id = generate_user_id()  # Generate a meaningful user ID
        session_start_time = datetime.now()
        chat_histories[session_id] = []
        print(f"Created new session: {session_id} for user: {user_id}")
        
        # Get client info
        client = websocket.client
        page_url = "unknown"  # Default value
        
        # Record session start
        record_user_event(
            user_id=user_id,
            session_id=session_id,
            event_type="session_start",
            event_data={
                "page_url": page_url,
                "timestamp": session_start_time.isoformat(),
                "connection_type": "websocket",
                "client_info": {
                    "host": client.host if hasattr(client, 'host') else 'unknown',
                    "port": client.port if hasattr(client, 'port') else 'unknown'
                }
            }
        )
        
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                print(f"Received message from client: {data[:100]}...")
                message = json.loads(data)
                
                # Update page URL if provided in the message
                if "page_url" in message:
                    page_url = message["page_url"]
                    # Update session with page URL
                    execute_query(
                        """
                        UPDATE sessions 
                        SET page_url = %s 
                        WHERE session_id = %s
                        """,
                        (page_url, session_id),
                        fetch=False
                    )
                
                # Extract user_id from message if provided
                if "user_id" in message and message["user_id"]:
                    new_user_id = message["user_id"]
                    
                    # First ensure the user exists by recording the identification event
                    record_user_event(
                        new_user_id,
                        session_id,
                        "user_identified",
                        {
                            "timestamp": datetime.now().isoformat(),
                            "previous_id": user_id
                        }
                    )
                    
                    # Now that we know the user exists, update the session
                    execute_query(
                        """
                        UPDATE sessions 
                        SET user_id = %s 
                        WHERE session_id = %s
                        """,
                        (new_user_id, session_id),
                        fetch=False
                    )
                    
                    user_id = new_user_id
                
                # Process the message
                if "user_input" in message:
                    message_start_time = datetime.now()
                    print(f"Processing user input: {message['user_input'][:50]}...")
                    
                    # Record the user's question
                    record_user_event(
                        user_id,
                        session_id,
                        "question_asked",
                        {
                            "question": message["user_input"],
                            "timestamp": message_start_time.isoformat(),
                            "chat_history_length": len(chat_histories[session_id])
                        }
                    )
                    
                    # Get chat history from message
                    chat_history = message.get("chat_history", [])
                    if chat_history:
                        formatted_history = [(msg["content"], "") for msg in chat_history if msg["role"] == "user"]
                        chat_histories[session_id] = formatted_history
                    
                    # Build retriever
                    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                    
                    # Use ConversationalRetrievalChain
                    qa = ConversationalRetrievalChain.from_llm(
                        llm=llm,
                        retriever=retriever,
                        # return_source_documents=True,
                        combine_docs_chain_kwargs={"prompt": SYSTEM_PROMPT}
                    )
                    
                    try:
                        # Get answer using chat history
                        result = qa({
                            "question": message["user_input"],
                            "chat_history": chat_histories[session_id]
                        })
                        answer = result["answer"]
                        response_time = (datetime.now() - message_start_time).total_seconds()
                        
                        # Record the bot's response
                        record_user_event(
                            user_id,
                            session_id,
                            "bot_response",
                            {
                                "response": answer,
                                "timestamp": datetime.now().isoformat(),
                                # "sources": [doc.metadata["source"] for doc in result.get("source_documents", [])],
                                "response_time": response_time
                            }
                        )
                        
                        # Update chat history
                        chat_histories[session_id].append((message["user_input"], answer))
                        
                        # Update message count in sessions table (count each interaction as 1)
                        execute_query(
                            """
                            UPDATE sessions 
                            SET message_count = message_count + 1,
                                last_message_time = %s
                            WHERE session_id = %s
                            """,
                            (datetime.now().isoformat(), session_id),
                            fetch=False
                        )
                        
                        # Limit chat history length
                        if len(chat_histories[session_id]) > 10:
                            chat_histories[session_id] = chat_histories[session_id][-10:]
                        
                        # Get source documents
                        # source_docs = result.get("source_documents", [])
                        # sources = [doc.metadata["source"] for doc in source_docs]
                        
                        # Send response back to client
                        response = {
                            "text": answer,
                            # "sources": sources,
                            "done": True
                        }
                        await websocket.send_json(response)
                        print(f"Response sent successfully for session {session_id}")
                        0.2
                    except Exception as e:
                        error_msg = f"Error processing request: {str(e)}"
                        print(error_msg)
                        
                        # Record error event
                        record_user_event(
                            user_id,
                            session_id,
                            "error",
                            {
                                "error": str(e),
                                "timestamp": datetime.now().isoformat(),
                                "question": message["user_input"]
                            }
                        )
                        
                        await websocket.send_json({
                            "error": error_msg,
                            "done": True
                        })
            except WebSocketDisconnect:
                print(f"WebSocket disconnected for session {session_id}")
                session_end_time = datetime.now()
                session_duration = (session_end_time - session_start_time).total_seconds()
                
                # Update session with end time and duration
                execute_query(
                    """
                    UPDATE sessions 
                    SET end_time = %s,
                        duration = %s,
                        status = 'completed'
                    WHERE session_id = %s
                    """,
                    (session_end_time.isoformat(), session_duration, session_id),
                    fetch=False
                )
                
                record_user_event(
                    user_id,
                    session_id,
                    "session_end",
                    {
                        "timestamp": session_end_time.isoformat(),
                        "total_messages": len(chat_histories[session_id]),
                        "duration": session_duration
                    }
                )
                break
            except Exception as e:
                print(f"Error in WebSocket loop: {str(e)}")
                if user_id:
                    record_user_event(
                        user_id,
                        session_id,
                        "error",
                        {
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                            "type": "websocket_error"
                        }
                    )
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

# Add a root endpoint for testing
@app.get("/")
async def root():
    return {"message": "API is running"}

class Person:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def greet(self):
        print("Hello my name is {self,name} and age is ")

# Update the sessions table schema
def update_sessions_table():
    try:
        # Check if columns exist first
        columns = execute_query("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'sessions' 
            AND TABLE_SCHEMA = DATABASE()
        """)
        existing_columns = [col['COLUMN_NAME'] for col in columns]

        # Add columns if they don't exist
        if 'message_count' not in existing_columns:
            execute_query("""
                ALTER TABLE sessions
                ADD COLUMN message_count INT DEFAULT 0
            """, fetch=False)

        if 'last_message_time' not in existing_columns:
            execute_query("""
                ALTER TABLE sessions
                ADD COLUMN last_message_time DATETIME
            """, fetch=False)

        if 'status' not in existing_columns:
            execute_query("""
                ALTER TABLE sessions
                ADD COLUMN status ENUM('active', 'completed', 'error') DEFAULT 'active'
            """, fetch=False)

        print("Sessions table schema updated successfully")
    except Error as e:
        print(f"Error updating sessions table: {e}")
        # Don't raise HTTPException here as this is a startup function

# Call this when the app starts
update_sessions_table()

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)














