from fastapi import APIRouter, HTTPException, Body
from datetime import datetime
from typing import Optional, Dict, Any
import mysql.connector
from mysql.connector import Error
import uuid
import json as json_lib
import hashlib

router = APIRouter()

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
    duration = event_data.get('duration') if event_data else 0

    try:
        print(f"Updating user {user_id} at {timestamp} for {event_type}")
        # Check if user exists
        user = execute_query(
            "SELECT * FROM users WHERE user_id = %s",
            (user_id,)
        )

        if not user:
            # Create new user with all counters initialized to 0
            execute_query(
                """
                INSERT INTO users 
                  (user_id, first_seen_at, last_active_at, total_sessions, total_messages, total_duration, total_conversations, is_active)
                VALUES (%s, %s, %s, 0, 0, 0, 0, TRUE)
                """,
                (user_id, timestamp, timestamp),
                fetch=False
            )
        else:
            # Always update last_active_at for any event
            execute_query(
                """
                UPDATE users 
                SET last_active_at = %s
                WHERE user_id = %s
                """,
                (timestamp, user_id),
                fetch=False
            )

        # Update user stats based on event type
        if event_type == "session_start":
            execute_query(
                """
                UPDATE users 
                  SET total_sessions = total_sessions + 1,
                      is_active = TRUE,
                      last_page_url = %s
                WHERE user_id = %s
                """,
                (page_url, user_id),
                fetch=False
            )
            # Record new session row
            execute_query(
                """
                INSERT INTO sessions 
                  (session_id, user_id, start_time, page_url, message_count, status) 
                VALUES (%s, %s, %s, %s, 0, 'active')
                """,
                (session_id, user_id, timestamp, page_url),
                fetch=False
            )
            # Create new conversation for this session
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
            # Insert a "session_start" system message
            execute_query(
                """
                INSERT INTO messages 
                  (message_id, conversation_id, user_id, message_type, content, timestamp)
                VALUES (UUID(), %s, %s, 'system', 'session_start', %s)
                """,
                (conversation_id, user_id, timestamp),
                fetch=False
            )

        elif event_type == "question_asked":
            # Find the active conversation for this session
            conv = execute_query(
                """
                SELECT conversation_id
                  FROM conversations
                 WHERE session_id = %s
                   AND status = 'active'
                 ORDER BY start_time DESC
                 LIMIT 1
                """,
                (session_id,)
            )
            if conv:
                conversation_id = conv[0]["conversation_id"]
                # Insert the user's question into messages
                execute_query(
                    """
                    INSERT INTO messages 
                      (message_id, conversation_id, user_id, message_type, content, timestamp)
                    VALUES (UUID(), %s, %s, 'user', %s, %s)
                    """,
                    (conversation_id, user_id, event_data.get("question", ""), timestamp),
                    fetch=False
                )
                # Update user row: bump total_messages
                execute_query(
                    """
                    UPDATE users
                      SET total_messages = total_messages + 1
                    WHERE user_id = %s
                    """,
                    (user_id,),
                    fetch=False
                )

        elif event_type == "bot_response":
            # Find the active conversation for this session
            conv = execute_query(
                """
                SELECT conversation_id
                  FROM conversations
                 WHERE session_id = %s
                   AND status = 'active'
                 ORDER BY start_time DESC
                 LIMIT 1
                """,
                (session_id,)
            )
            if conv:
                conversation_id = conv[0]["conversation_id"]
                # Insert the bot's response
                execute_query(
                    """
                    INSERT INTO messages 
                      (message_id, conversation_id, user_id, message_type, content, timestamp)
                    VALUES (UUID(), %s, %s, 'bot', %s, %s)
                    """,
                    (conversation_id, user_id, event_data.get("response", ""), timestamp),
                    fetch=False
                )

        elif event_type == "session_end":
            # 1) Find the active conversation
            conv = execute_query(
                """
                SELECT conversation_id
                  FROM conversations
                 WHERE session_id = %s
                   AND status = 'active'
                 ORDER BY start_time DESC
                 LIMIT 1
                """,
                (session_id,)
            )
            if conv:
                conversation_id = conv[0]["conversation_id"]
                # 2) Compute the duration in seconds, set conversation to "completed"
                execute_query(
                    """
                    UPDATE conversations
                      SET end_time = %s,
                          status   = 'completed',
                          duration = TIMESTAMPDIFF(SECOND, start_time, %s)
                     WHERE conversation_id = %s
                    """,
                    (timestamp, timestamp, conversation_id),
                    fetch=False
                )
                # 3) Add a "session_end" system message
                execute_query(
                    """
                    INSERT INTO messages 
                      (message_id, conversation_id, user_id, message_type, content, timestamp)
                    VALUES (UUID(), %s, %s, 'system', 'session_end', %s)
                    """,
                    (conversation_id, user_id, timestamp),
                    fetch=False
                )
                # 4) Retrieve that duration we just computed
                result = execute_query(
                    """
                    SELECT duration
                      FROM conversations
                     WHERE conversation_id = %s
                    """,
                    (conversation_id,)
                )
                if result:
                    session_duration = result[0]["duration"] or 0
                else:
                    session_duration = 0
                # 5) Update the user row:
                execute_query(
                    """
                    UPDATE users
                      SET is_active = FALSE,
                          last_active_at = %s,
                          total_duration = total_duration + %s,
                          total_conversations = total_conversations + 1
                    WHERE user_id = %s
                    """,
                    (timestamp, session_duration, user_id),
                    fetch=False
                )

        elif event_type == "user_identified":
            execute_query(
                """
                UPDATE users 
                SET last_active_at = %s,
                    user_type = 'returning'
                WHERE user_id = %s
                """,
                (timestamp, user_id),
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

# --- Analytics Endpoints ---

@router.get("/analytics")
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

@router.get("/analytics/sessions", tags=["analytics"])
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

@router.get("/analytics/conversations", tags=["analytics"])
async def get_conversation_analytics():
    try:
        # Get conversation statistics
        stats = execute_query("""
            SELECT 
                COUNT(*) as total_conversations,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_conversations,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_conversations,
                COUNT(CASE WHEN status = 'handover' THEN 1 END) as handover_conversations,
                AVG(duration) as avg_duration,
                COUNT(CASE WHEN message_type = 'user' THEN 1 END) as user_messages
            FROM conversations c
            LEFT JOIN messages m ON c.conversation_id = m.conversation_id
            GROUP BY c.conversation_id
        """)[0]

        # Get recent conversations with message counts
        recent_conversations = execute_query("""
            SELECT 
                c.conversation_id,
                c.user_id,
                c.start_time,
                c.duration,
                c.status,
                COUNT(CASE WHEN m.message_type = 'user' THEN 1 END) as message_count
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
            "total_messages": stats['user_messages'] or 0,
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
            "total_messages": 0,
            "recent_conversations": []
        }

@router.get("/analytics/messages", tags=["analytics"])
async def get_message_analytics():
    try:
        # Get message statistics - count each user-bot interaction as 1
        stats = execute_query("""
            SELECT 
                COUNT(DISTINCT CASE 
                    WHEN m1.message_type = 'user' AND m2.message_type = 'bot' 
                    AND m1.conversation_id = m2.conversation_id 
                    THEN m1.message_id 
                END) as total_messages,
                COUNT(CASE WHEN m1.message_type = 'user' THEN 1 END) as user_messages,
                COUNT(CASE WHEN m1.message_type = 'bot' THEN 1 END) as bot_messages,
                COUNT(CASE WHEN m1.message_type = 'system' THEN 1 END) as system_messages
            FROM messages m1
            LEFT JOIN messages m2 ON m1.conversation_id = m2.conversation_id 
                AND m2.message_type = 'bot'
                AND m2.timestamp > m1.timestamp
                AND NOT EXISTS (
                    SELECT 1 FROM messages m3 
                    WHERE m3.conversation_id = m1.conversation_id 
                    AND m3.message_type = 'bot'
                    AND m3.timestamp > m1.timestamp 
                    AND m3.timestamp < m2.timestamp
                )
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

@router.get("/analytics/user/{user_id}", tags=["analytics"])
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
            "total_conversations": user['total_conversations'],
            "session_history": sessions_data
        }
        
        return user_data
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analytics/leads", tags=["analytics"])
async def capture_lead(lead_data: dict):
    try:
        # Generate a unique lead ID
        lead_id = str(uuid.uuid4())
        
        # Insert the lead into the analytics table
        execute_query(
            """
            INSERT INTO lead_analytics 
            (lead_id, lead_type, name, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                lead_id,
                'appointment_scheduled',
                lead_data.get('name', ''),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ),
            fetch=False
        )
        
        return {"status": "success", "lead_id": lead_id}
    except Error as e:
        print(f"Error capturing lead: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/leads", tags=["analytics"])
async def get_lead_analytics():
    try:
        # Get lead statistics
        stats = execute_query("""
            SELECT 
                COUNT(*) as total_leads,
                COUNT(CASE WHEN lead_type = 'appointment_scheduled' THEN 1 END) as scheduled_leads,
                DATE(created_at) as date,
                COUNT(*) as daily_leads
            FROM lead_analytics
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 30
        """)
        
        return {
            "total_leads": len(stats) or 0,
            "daily_leads": stats or []
        }
    except Error as e:
        print(f"Error in lead analytics: {str(e)}")
        return {
            "total_leads": 0,
            "daily_leads": []
        }

@router.post("/analytics/human_handover", tags=["analytics"])
async def record_human_handover(data: dict = Body(...)):
    try:
        print("Received handover data:", data)
        # Convert ISO 8601 to MySQL DATETIME
        requested_at = data.get('requested_at')
        if requested_at:
            try:
                if requested_at.endswith('Z'):
                    requested_at = requested_at[:-1]
                if '.' in requested_at:
                    requested_at = requested_at.split('.')[0]
                requested_at = requested_at.replace('T', ' ')
            except Exception as e:
                print("Error parsing requested_at:", e)
                requested_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            requested_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_query(
            """
            INSERT INTO human_handover
                (user_id, session_id, requested_at, method, issues, other_text, support_option, last_message, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            """,
            (
                data.get('user_id'),
                data.get('session_id'),
                requested_at,
                data.get('method'),
                json_lib.dumps(data.get('issues', [])),
                data.get('other_text', ''),
                data.get('support_option', ''),
                data.get('last_message', ''),
            ),
            fetch=False
        )
        return {"status": "success"}
    except Error as e:
        print(f"Error recording human handover: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/human_handover", tags=["analytics"])
async def get_human_handover_analytics():
    try:
        count = execute_query("SELECT COUNT(*) as count FROM human_handover")[0]['count']
        recent = execute_query("""
            SELECT handover_id, user_id, session_id, requested_at, method, issues, other_text, support_option, status
            FROM human_handover
            ORDER BY requested_at DESC
            LIMIT 20
        """)
        return {"total_handover": count, "recent_handover": recent}
    except Error as e:
        print(f"Error in human handover analytics: {e}")
        return {"total_handover": 0, "recent_handover": []}

@router.post("/analytics/chatbot_close", tags=["analytics"])
async def record_chatbot_close(data: dict = Body(...)):
    try:
        closed_at = data.get('closed_at')
        if closed_at:
            try:
                if closed_at.endswith('Z'):
                    closed_at = closed_at[:-1]
                if '.' in closed_at:
                    closed_at = closed_at.split('.')[0]
                closed_at = closed_at.replace('T', ' ')
            except Exception as e:
                print("Error parsing closed_at:", e)
                closed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            closed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_query(
            """
            INSERT INTO chatbot_close_events
                (user_id, session_id, closed_at, time_spent_seconds, last_user_message, last_bot_message)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                data.get('user_id'),
                data.get('session_id'),
                closed_at,
                data.get('time_spent_seconds', 0),
                data.get('last_user_message', ''),
                data.get('last_bot_message', ''),
            ),
            fetch=False
        )
        return {"status": "success"}
    except Error as e:
        print(f"Error recording chatbot close: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analytics/session_end", tags=["analytics"])
async def record_session_end(data: dict = Body(...)):
    try:
        end_time = data.get('end_time')
        if end_time:
            try:
                if end_time.endswith('Z'):
                    end_time = end_time[:-1]
                if '.' in end_time:
                    end_time = end_time.split('.')[0]
                end_time = end_time.replace('T', ' ')
            except Exception as e:
                print("Error parsing end_time:", e)
                end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_query(
            """
            UPDATE sessions
            SET end_time = %s,
                duration = %s,
                status = 'completed'
            WHERE session_id = %s
            """,
            (
                end_time,
                data.get('duration', 0),
                data.get('session_id'),
            ),
            fetch=False
        )
        return {"status": "success"}
    except Error as e:
        print(f"Error recording session end: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 