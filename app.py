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
import mysql.connector
from mysql.connector import Error
import json as json_lib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import hashlib

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

# MySQL Configuration
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'nirbhaysingh@mg1234',
    'database': 'chatbot_analytics'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**MYSQL_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")
    return None

def execute_query(query: str, params: tuple = None, fetch: bool = True) -> Optional[Dict[str, Any]]:
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
            
        if fetch:
            result = cursor.fetchall()
        else:
            connection.commit()
            result = None
            
        return result
    except Error as e:
        print(f"Error executing query: {e}")
        if connection:
            connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def record_user_event(user_id: str, session_id: str, event_type: str, event_data: Dict = None):
    if not user_id:
        return
        
    timestamp = datetime.now().isoformat()
    page_url = event_data.get('page_url') if event_data else None
    
    try:
        # Check if user exists
        user = execute_query(
            "SELECT * FROM users WHERE user_id = %s",
            (user_id,)
        )
        
        if not user:
            # Create new user
            execute_query(
                """
                INSERT INTO users 
                (user_id, first_seen_at, last_active_at, is_active) 
                VALUES (%s, %s, %s, TRUE)
                """,
                (user_id, timestamp, timestamp),
                fetch=False
            )
        
        # Update user stats based on event type
        if event_type == "session_start":
            execute_query(
                """
                UPDATE users 
                SET total_sessions = total_sessions + 1,
                    last_active_at = %s,
                    is_active = TRUE,
                    last_page_url = %s
                WHERE user_id = %s
                """,
                (timestamp, page_url, user_id),
                fetch=False
            )
            
            # Record session
            execute_query(
                """
                INSERT INTO sessions 
                (session_id, user_id, start_time, page_url, message_count, status) 
                VALUES (%s, %s, %s, %s, 0, 'active')
                """,
                (session_id, user_id, timestamp, page_url),
                fetch=False
            )
            
            # Create a new conversation for this session
            conversation_id = str(uuid.uuid4())
            execute_query(
                """
                INSERT INTO conversations 
                (conversation_id, session_id, user_id, start_time, status)
                VALUES (%s, %s, %s, %s, 'active')
                """,
                (conversation_id, session_id, user_id, timestamp),
                fetch=False
            )
                
            # Record the session start event
            execute_query(
                """
                INSERT INTO messages 
                (message_id, conversation_id, user_id, message_type, content, timestamp)
                VALUES (UUID(), %s, %s, 'system', %s, %s)
                """,
                (conversation_id, user_id, json_lib.dumps({"event": "session_start"}), timestamp),
                fetch=False
            )
            
        elif event_type == "question_asked":
            # Get the active conversation for this session
            conversation = execute_query(
                """
                SELECT conversation_id 
                FROM conversations 
                WHERE session_id = %s AND status = 'active'
                ORDER BY start_time DESC LIMIT 1
                """,
                (session_id,)
            )
            
            if conversation:
                conversation_id = conversation[0]['conversation_id']
                
                # Record the user's question
                execute_query(
                    """
                    INSERT INTO messages 
                    (message_id, conversation_id, user_id, message_type, content, timestamp)
                    VALUES (UUID(), %s, %s, 'user', %s, %s)
                    """,
                    (conversation_id, user_id, json_lib.dumps(event_data), timestamp),
                    fetch=False
                )
                
                # Update user message count
                execute_query(
                    """
                    UPDATE users 
                    SET total_messages = total_messages + 1,
                        last_active_at = %s
                    WHERE user_id = %s
                    """,
                    (timestamp, user_id),
                    fetch=False
                )
            
        elif event_type == "bot_response":
            # Get the active conversation
            conversation = execute_query(
                """
                SELECT conversation_id 
                FROM conversations 
                WHERE session_id = %s AND status = 'active'
                ORDER BY start_time DESC LIMIT 1
                """,
                (session_id,)
            )
            
            if conversation:
                conversation_id = conversation[0]['conversation_id']
                
                # Record the bot's response
                execute_query(
                    """
                    INSERT INTO messages 
                    (message_id, conversation_id, user_id, message_type, content, timestamp)
                    VALUES (UUID(), %s, %s, 'bot', %s, %s)
                    """,
                    (conversation_id, user_id, json_lib.dumps(event_data), timestamp),
                    fetch=False
                )
            
        elif event_type == "session_end":
            # Get the active conversation
            conversation = execute_query(
                """
                SELECT conversation_id 
                FROM conversations 
                WHERE session_id = %s AND status = 'active'
                ORDER BY start_time DESC LIMIT 1
                """,
                (session_id,)
            )
            
            if conversation:
                conversation_id = conversation[0]['conversation_id']
                
                # Update conversation status
                execute_query(
                    """
                    UPDATE conversations 
                    SET end_time = %s,
                        status = 'completed',
                        duration = TIMESTAMPDIFF(SECOND, start_time, %s)
                    WHERE conversation_id = %s
                    """,
                    (timestamp, timestamp, conversation_id),
                    fetch=False
                )
                
                # Record the session end event
                execute_query(
                    """
                    INSERT INTO messages 
                    (message_id, conversation_id, user_id, message_type, content, timestamp)
                    VALUES (UUID(), %s, %s, 'system', %s, %s)
                    """,
                    (conversation_id, user_id, json_lib.dumps({"event": "session_end"}), timestamp),
                    fetch=False
                )
            
            # Update user status
            execute_query(
                """
                UPDATE users 
                SET is_active = FALSE
                WHERE user_id = %s
                """,
                (user_id,),
                fetch=False
            )
        
    except Error as e:
        print(f"Error recording user event: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def generate_short_id():
    """Generate a shorter, more readable ID"""
    return hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:8]

def generate_user_id():
    """Generate a meaningful user ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_part = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:4]
    return f"user_{timestamp}_{random_part}"

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
                    # Update the session with the real user ID
                    execute_query(
                        """
                        UPDATE sessions 
                        SET user_id = %s 
                        WHERE session_id = %s
                        """,
                        (new_user_id, session_id),
                        fetch=False
                    )
                    
                    # Record user identification
                    record_user_event(
                        new_user_id,
                        session_id,
                        "user_identified",
                        {
                            "timestamp": datetime.now().isoformat(),
                            "previous_id": user_id
                        }
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
                        response_time = (datetime.now() - message_start_time).total_seconds()
                        
                        # Record the bot's response
                        record_user_event(
                            user_id,
                            session_id,
                            "bot_response",
                            {
                                "response": answer,
                                "timestamp": datetime.now().isoformat(),
                                "sources": [doc.metadata["source"] for doc in result.get("source_documents", [])],
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

# Update analytics endpoints to use the database
@app.get("/analytics")
async def get_analytics():
    try:
        # Get total users
        total_users = execute_query("SELECT COUNT(*) as count FROM users")[0]['count']
        
        # Get total sessions
        total_sessions = execute_query("SELECT SUM(total_sessions) as count FROM users")[0]['count'] or 0
        
        # Get total questions
        total_questions = execute_query("SELECT SUM(total_messages) as count FROM users")[0]['count'] or 0
        
        # Get total chatbot opens
        total_opens = execute_query("SELECT COUNT(*) as count FROM users WHERE total_sessions > 0")[0]['count'] or 0
        
        # Get all users with their stats
        users = execute_query("""
            SELECT 
                u.*,
                COUNT(DISTINCT s.session_id) as session_count,
                AVG(s.duration) as avg_session_duration
            FROM users u
            LEFT JOIN sessions s ON u.user_id = s.user_id
            GROUP BY u.user_id
        """)
        
        users_data = {}
        for user in users:
            user_id = user['user_id']
            # Get user's sessions
            sessions = execute_query("""
                SELECT 
                    s.*,
                    COUNT(m.message_id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.conversation_id
                WHERE s.user_id = %s
                GROUP BY s.session_id
                ORDER BY s.start_time DESC
            """, (user_id,))
            
            sessions_data = []
            for session in sessions:
                # Get events for this session
                events = execute_query("""
                    SELECT 
                        message_type as type,
                        timestamp,
                        content as data
                    FROM messages 
                    WHERE conversation_id = %s
                    ORDER BY timestamp
                """, (session['session_id'],))
                
                events_data = []
                for event in events:
                    event_data = None
                    if event['data']:
                        try:
                            event_data = json_lib.loads(event['data'])
                        except:
                            event_data = event['data']
                            
                    events_data.append({
                        "type": event['type'],
                        "timestamp": event['timestamp'],
                        "data": event_data
                    })
                
                sessions_data.append({
                    "session_id": session['session_id'],
                    "start_time": session['start_time'],
                    "end_time": session['end_time'],
                    "duration": session['duration'],
                    "message_count": session['message_count'],
                    "events": events_data
                })
            
            users_data[user_id] = {
                "sessions": user['total_sessions'],
                "total_messages": user['total_messages'],
                "total_duration": user['total_duration'],
                "last_active": user['last_active_at'],
                "created_at": user['first_seen_at'],
                "is_active": user['is_active'],
                "session_history": sessions_data
            }
        
        return {
            "total_users": total_users,
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "total_chatbot_opens": total_opens,
            "users": users_data
        }
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/sessions", tags=["analytics"])
async def get_session_analytics():
    try:
        # Get active sessions
        active_sessions = execute_query("""
            SELECT COUNT(*) as active_count 
            FROM sessions 
            WHERE status = 'active'
        """)[0]['active_count']

        # Get total sessions today
        today_sessions = execute_query("""
            SELECT COUNT(*) as today_count 
            FROM sessions 
            WHERE DATE(start_time) = CURDATE()
        """)[0]['today_count']

        # Get average session duration
        avg_duration = execute_query("""
            SELECT AVG(duration) as avg_duration 
            FROM sessions 
            WHERE duration > 0
        """)[0]['avg_duration']

        # Get recent sessions with details
        recent_sessions = execute_query("""
            SELECT 
                s.session_id,
                s.user_id,
                s.start_time,
                s.duration,
                s.page_url,
                s.message_count,
                s.status
            FROM sessions s
            ORDER BY s.start_time DESC
            LIMIT 10
        """)

        return {
            "active_sessions": active_sessions or 0,
            "today_sessions": today_sessions or 0,
            "average_duration": round(avg_duration, 2) if avg_duration else 0,
            "recent_sessions": recent_sessions or []
        }
    except Error as e:
        print(f"Error in session analytics: {str(e)}")
        return {
            "active_sessions": 0,
            "today_sessions": 0,
            "average_duration": 0,
            "recent_sessions": []
        }

@app.get("/analytics/conversations", tags=["analytics"])
async def get_conversation_analytics():
    try:
        # Get conversation statistics
        stats = execute_query("""
            SELECT 
                COUNT(*) as total_conversations,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_conversations,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_conversations,
                COUNT(CASE WHEN status = 'handover' THEN 1 END) as handover_conversations,
                AVG(duration) as avg_duration
            FROM conversations
        """)[0]

        # Get recent conversations with message counts
        recent_conversations = execute_query("""
            SELECT 
                c.conversation_id,
                c.user_id,
                c.start_time,
                c.duration,
                c.status,
                COUNT(m.message_id) as message_count
            FROM conversations c
            LEFT JOIN messages m ON c.conversation_id = m.conversation_id
            GROUP BY c.conversation_id
            ORDER BY c.start_time DESC
            LIMIT 10
        """)

        return {
            "total_conversations": stats['total_conversations'] or 0,
            "active_conversations": stats['active_conversations'] or 0,
            "completed_conversations": stats['completed_conversations'] or 0,
            "handover_conversations": stats['handover_conversations'] or 0,
            "average_duration": round(stats['avg_duration'], 2) if stats['avg_duration'] else 0,
            "recent_conversations": recent_conversations or []
        }
    except Error as e:
        print(f"Error in conversation analytics: {str(e)}")
        return {
            "total_conversations": 0,
            "active_conversations": 0,
            "completed_conversations": 0,
            "handover_conversations": 0,
            "average_duration": 0,
            "recent_conversations": []
        }

@app.get("/analytics/messages", tags=["analytics"])
async def get_message_analytics():
    try:
        # Get message statistics
        stats = execute_query("""
            SELECT 
                COUNT(*) as total_messages,
                COUNT(CASE WHEN message_type = 'user' THEN 1 END) as user_messages,
                COUNT(CASE WHEN message_type = 'bot' THEN 1 END) as bot_messages,
                COUNT(CASE WHEN message_type = 'system' THEN 1 END) as system_messages
            FROM messages
        """)[0]

        # Get recent messages with details
        recent_messages = execute_query("""
            SELECT 
                m.message_id,
                m.conversation_id,
                m.user_id,
                m.message_type,
                m.content,
                m.timestamp
            FROM messages m
            ORDER BY m.timestamp DESC
            LIMIT 20
        """)

        return {
            "total_messages": stats['total_messages'] or 0,
            "user_messages": stats['user_messages'] or 0,
            "bot_messages": stats['bot_messages'] or 0,
            "system_messages": stats['system_messages'] or 0,
            "recent_messages": recent_messages or []
        }
    except Error as e:
        print(f"Error in message analytics: {str(e)}")
        return {
            "total_messages": 0,
            "user_messages": 0,
            "bot_messages": 0,
            "system_messages": 0,
            "recent_messages": []
        }

@app.get("/analytics/users", tags=["analytics"])
async def get_user_analytics():
    try:
        # Get user statistics
        stats = execute_query("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(CASE WHEN is_active = TRUE THEN 1 END) as active_users,
                COUNT(CASE WHEN user_type = 'new' THEN 1 END) as new_users,
                COUNT(CASE WHEN user_type = 'returning' THEN 1 END) as returning_users,
                AVG(total_sessions) as avg_sessions_per_user,
                AVG(total_messages) as avg_messages_per_user
            FROM users
        """)[0]

        # Get recent active users
        recent_users = execute_query("""
            SELECT 
                user_id,
                first_seen_at,
                last_active_at,
                total_sessions,
                total_messages,
                is_active,
                user_type
            FROM users
            ORDER BY last_active_at DESC
            LIMIT 10
        """)

        return {
            "total_users": stats['total_users'] or 0,
            "active_users": stats['active_users'] or 0,
            "new_users": stats['new_users'] or 0,
            "returning_users": stats['returning_users'] or 0,
            "average_sessions_per_user": round(stats['avg_sessions_per_user'], 2) if stats['avg_sessions_per_user'] else 0,
            "average_messages_per_user": round(stats['avg_messages_per_user'], 2) if stats['avg_messages_per_user'] else 0,
            "recent_users": recent_users or []
        }
    except Error as e:
        print(f"Error in user analytics: {str(e)}")
        return {
            "total_users": 0,
            "active_users": 0,
            "new_users": 0,
            "returning_users": 0,
            "average_sessions_per_user": 0,
            "average_messages_per_user": 0,
            "recent_users": []
        }

# Parameterized routes after specific routes
@app.get("/analytics/user/{user_id}", tags=["analytics"])
async def get_user_analytics_by_id(user_id: str):
    try:
        # Get user data
        user = execute_query("""
            SELECT 
                u.*,
                COUNT(DISTINCT s.session_id) as session_count,
                AVG(s.duration) as avg_session_duration
            FROM users u
            LEFT JOIN sessions s ON u.user_id = s.user_id
            WHERE u.user_id = %s
            GROUP BY u.user_id
        """, (user_id,))
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = user[0]
        
        # Get user's sessions
        sessions = execute_query("""
            SELECT 
                s.*,
                COUNT(m.message_id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.conversation_id
            WHERE s.user_id = %s
            GROUP BY s.session_id
            ORDER BY s.start_time DESC
        """, (user_id,))
        
        sessions_data = []
        for session in sessions:
            # Get events for this session
            events = execute_query("""
                SELECT 
                    message_type as type,
                    timestamp,
                    content as data
                FROM messages 
                WHERE conversation_id = %s
                ORDER BY timestamp
            """, (session['session_id'],))
            
            events_data = []
            for event in events:
                event_data = None
                if event['data']:
                    try:
                        event_data = json_lib.loads(event['data'])
                    except:
                        event_data = event['data']
                        
                events_data.append({
                    "type": event['type'],
                    "timestamp": event['timestamp'],
                    "data": event_data
                })
            
            sessions_data.append({
                "session_id": session['session_id'],
                "start_time": session['start_time'],
                "end_time": session['end_time'],
                "duration": session['duration'],
                "message_count": session['message_count'],
                "events": events_data
            })
        
        user_data = {
            "user_id": user['user_id'],
            "sessions": user['total_sessions'],
            "total_messages": user['total_messages'],
            "total_duration": user['total_duration'],
            "last_active": user['last_active_at'],
            "created_at": user['first_seen_at'],
            "is_active": user['is_active'],
            "avg_session_duration": user['avg_session_duration'],
            "session_history": sessions_data
        }
        
        return user_data
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))

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
















