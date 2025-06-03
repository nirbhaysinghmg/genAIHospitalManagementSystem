import React, { useEffect, useState } from "react";

const ENDPOINTS = {
  main: "http://localhost:8000/analytics",
  sessions: "http://localhost:8000/analytics/sessions",
  conversations: "http://localhost:8000/analytics/conversations",
  messages: "http://localhost:8000/analytics/messages",
  users: "http://localhost:8000/analytics/users",
  leads: "http://localhost:8000/analytics/leads",
};

const PAGE_SIZE = 20;

const NAV_ITEMS = [
  { key: "home", label: "Home" },
  { key: "sessions", label: "Sessions" },
  { key: "conversations", label: "Conversations" },
  { key: "messages", label: "Messages" },
  { key: "users", label: "Users" },
  { key: "leads", label: "Leads" },
];

const Section = ({ title, children }) => (
  <section style={{ marginBottom: 40 }}>
    <h2 style={{ borderBottom: "2px solid #eee", paddingBottom: 4 }}>
      {title}
    </h2>
    {children}
  </section>
);

const Table = ({ columns, data }) => (
  <div style={{ overflowX: "auto" }}>
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead>
        <tr style={{ background: "#e0e0e0" }}>
          {columns.map((col) => (
            <th key={col} style={{ padding: 8, border: "1px solid #ccc" }}>
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, i) => (
          <tr key={i}>
            {columns.map((col) => (
              <td key={col} style={{ padding: 8, border: "1px solid #ccc" }}>
                {row[col]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const AnalyticsDashboard = () => {
  const [selected, setSelected] = useState("home");
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Paginated data and offsets
  const [sessions, setSessions] = useState([]);
  const [sessionsOffset, setSessionsOffset] = useState(0);
  const [sessionsStats, setSessionsStats] = useState({});
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsHasMore, setSessionsHasMore] = useState(true);

  const [conversations, setConversations] = useState([]);
  const [conversationsOffset, setConversationsOffset] = useState(0);
  const [conversationsStats, setConversationsStats] = useState({});
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [conversationsHasMore, setConversationsHasMore] = useState(true);

  const [messages, setMessages] = useState([]);
  const [messagesOffset, setMessagesOffset] = useState(0);
  const [messagesStats, setMessagesStats] = useState({});
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesHasMore, setMessagesHasMore] = useState(true);

  const [users, setUsers] = useState([]);
  const [usersOffset, setUsersOffset] = useState(0);
  const [usersStats, setUsersStats] = useState({});
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersHasMore, setUsersHasMore] = useState(true);

  const [leads, setLeads] = useState([]);
  const [leadsStats, setLeadsStats] = useState({});
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [leadsHasMore, setLeadsHasMore] = useState(true);

  // Helper for safe access
  const safe = (obj, key, fallback = 0) =>
    obj && obj[key] != null ? obj[key] : fallback;

  // Initial summary fetch
  useEffect(() => {
    setLoading(true);
    fetch(ENDPOINTS.main)
      .then((res) => res.json())
      .then(setSummary)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Section fetchers
  const fetchSessions = (offset = 0, append = false) => {
    setSessionsLoading(true);
    fetch(`${ENDPOINTS.sessions}?offset=${offset}&limit=${PAGE_SIZE}`)
      .then((res) => res.json())
      .then((data) => {
        setSessionsStats(data);
        const newData = data.recent_sessions || [];
        setSessions((prev) => (append ? [...prev, ...newData] : newData));
        setSessionsHasMore(newData.length === PAGE_SIZE);
      })
      .catch((err) => setError(err.message))
      .finally(() => setSessionsLoading(false));
  };
  const fetchConversations = (offset = 0, append = false) => {
    setConversationsLoading(true);
    fetch(`${ENDPOINTS.conversations}?offset=${offset}&limit=${PAGE_SIZE}`)
      .then((res) => res.json())
      .then((data) => {
        setConversationsStats(data);
        const newData = data.recent_conversations || [];
        setConversations((prev) => (append ? [...prev, ...newData] : newData));
        setConversationsHasMore(newData.length === PAGE_SIZE);
      })
      .catch((err) => setError(err.message))
      .finally(() => setConversationsLoading(false));
  };
  const fetchMessages = (offset = 0, append = false) => {
    setMessagesLoading(true);
    fetch(`${ENDPOINTS.messages}?offset=${offset}&limit=${PAGE_SIZE}`)
      .then((res) => res.json())
      .then((data) => {
        setMessagesStats(data);
        const newData = data.recent_messages || [];
        setMessages((prev) => (append ? [...prev, ...newData] : newData));
        setMessagesHasMore(newData.length === PAGE_SIZE);
      })
      .catch((err) => setError(err.message))
      .finally(() => setMessagesLoading(false));
  };
  const fetchUsers = (offset = 0, append = false) => {
    setUsersLoading(true);
    fetch(`${ENDPOINTS.users}?offset=${offset}&limit=${PAGE_SIZE}`)
      .then((res) => res.json())
      .then((data) => {
        setUsersStats(data);
        const newData = data.recent_users || [];
        setUsers((prev) => (append ? [...prev, ...newData] : newData));
        setUsersHasMore(newData.length === PAGE_SIZE);
      })
      .catch((err) => setError(err.message))
      .finally(() => setUsersLoading(false));
  };
  const fetchLeads = (offset = 0, append = false) => {
    setLeadsLoading(true);
    fetch(`${ENDPOINTS.leads}?offset=${offset}&limit=${PAGE_SIZE}`)
      .then((res) => res.json())
      .then((data) => {
        setLeadsStats(data);
        const newData = data.daily_leads || [];
        setLeads((prev) => (append ? [...prev, ...newData] : newData));
        setLeadsHasMore(newData.length === PAGE_SIZE);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLeadsLoading(false));
  };

  // Fetch section data on tab change
  useEffect(() => {
    if (selected === "sessions") {
      setSessions([]);
      setSessionsOffset(0);
      setSessionsHasMore(true);
      fetchSessions(0, false);
    } else if (selected === "conversations") {
      setConversations([]);
      setConversationsOffset(0);
      setConversationsHasMore(true);
      fetchConversations(0, false);
    } else if (selected === "messages") {
      setMessages([]);
      setMessagesOffset(0);
      setMessagesHasMore(true);
      fetchMessages(0, false);
    } else if (selected === "users") {
      setUsers([]);
      setUsersOffset(0);
      setUsersHasMore(true);
      fetchUsers(0, false);
    } else if (selected === "leads") {
      setLeads([]);
      setLeadsLoading(0);
      setLeadsHasMore(true);
      fetchLeads(0, false);
    }
    // eslint-disable-next-line
  }, [selected]);

  if (loading) return <div style={{ padding: 32 }}>Loading analytics...</div>;
  if (error)
    return <div style={{ color: "red", padding: 32 }}>Error: {error}</div>;

  return (
    <div
      style={{ display: "flex", minHeight: "100vh", fontFamily: "sans-serif" }}
    >
      {/* Sidebar Navigation */}
      <nav
        style={{
          width: 220,
          background: "#f5f5f5",
          padding: 24,
          borderRight: "1px solid #e0e0e0",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Analytics</h2>
        <ul style={{ listStyle: "none", padding: 0 }}>
          {NAV_ITEMS.map((item) => (
            <li key={item.key}>
              <button
                style={{
                  width: "100%",
                  background: selected === item.key ? "#0066cc" : "transparent",
                  color: selected === item.key ? "#fff" : "#222",
                  border: "none",
                  borderRadius: 6,
                  padding: "10px 16px",
                  margin: "6px 0",
                  cursor: "pointer",
                  textAlign: "left",
                  fontWeight: selected === item.key ? "bold" : "normal",
                  fontSize: 16,
                }}
                onClick={() => setSelected(item.key)}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      {/* Main Content */}
      <main style={{ flex: 1, padding: 32, maxWidth: 1200 }}>
        {selected === "home" && summary && (
          <>
            <h1>Analytics Dashboard</h1>
            <div style={{ display: "flex", gap: 32, marginBottom: 32 }}>
              <div
                style={{
                  background: "#f5f5f5",
                  padding: 24,
                  borderRadius: 8,
                  flex: 1,
                }}
              >
                <h2>Total Users</h2>
                <div style={{ fontSize: 32 }}>
                  {safe(summary, "total_users")}
                </div>
              </div>
              <div
                style={{
                  background: "#f5f5f5",
                  padding: 24,
                  borderRadius: 8,
                  flex: 1,
                }}
              >
                <h2>Total Sessions</h2>
                <div style={{ fontSize: 32 }}>
                  {safe(summary, "total_sessions")}
                </div>
              </div>
              <div
                style={{
                  background: "#f5f5f5",
                  padding: 24,
                  borderRadius: 8,
                  flex: 1,
                }}
              >
                <h2>Total Questions</h2>
                <div style={{ fontSize: 32 }}>
                  {safe(summary, "total_questions")}
                </div>
              </div>
              <div
                style={{
                  background: "#f5f5f5",
                  padding: 24,
                  borderRadius: 8,
                  flex: 1,
                }}
              >
                <h2>Chatbot Opens</h2>
                <div style={{ fontSize: 32 }}>
                  {safe(summary, "total_chatbot_opens")}
                </div>
              </div>
            </div>
          </>
        )}
        {selected === "sessions" && (
          <Section title="Sessions">
            <div style={{ display: "flex", gap: 32, marginBottom: 16 }}>
              <div>
                Active Sessions: <b>{safe(sessionsStats, "active_sessions")}</b>
              </div>
              <div>
                Today's Sessions: <b>{safe(sessionsStats, "today_sessions")}</b>
              </div>
              <div>
                Average Duration:{" "}
                <b>{safe(sessionsStats, "average_duration")}</b> sec
              </div>
            </div>
            <div>Recent Sessions:</div>
            <Table
              columns={[
                "session_id",
                "user_id",
                "start_time",
                "duration",
                "page_url",
                "message_count",
                "status",
              ]}
              data={sessions}
            />
            {sessionsHasMore && (
              <button
                style={{
                  marginTop: 16,
                  padding: "8px 20px",
                  borderRadius: 6,
                  background: "#0066cc",
                  color: "#fff",
                  border: "none",
                  cursor: "pointer",
                }}
                onClick={() => {
                  const nextOffset = sessionsOffset + PAGE_SIZE;
                  setSessionsOffset(nextOffset);
                  fetchSessions(nextOffset, true);
                }}
                disabled={sessionsLoading}
              >
                {sessionsLoading ? "Loading..." : "Load Older"}
              </button>
            )}
            {!sessionsHasMore && sessions.length > 0 && (
              <div style={{ marginTop: 12, color: "#888" }}>
                No more sessions to load.
              </div>
            )}
          </Section>
        )}
        {selected === "conversations" && (
          <Section title="Conversations">
            <div style={{ display: "flex", gap: 32, marginBottom: 16 }}>
              <div>
                Total: <b>{safe(conversationsStats, "total_conversations")}</b>
              </div>
              <div>
                Active:{" "}
                <b>{safe(conversationsStats, "active_conversations")}</b>
              </div>
              <div>
                Completed:{" "}
                <b>{safe(conversationsStats, "completed_conversations")}</b>
              </div>
              <div>
                Handover:{" "}
                <b>{safe(conversationsStats, "handover_conversations")}</b>
              </div>
              <div>
                Avg Duration:{" "}
                <b>{safe(conversationsStats, "average_duration")}</b> sec
              </div>
              <div>
                Total Messages:{" "}
                <b>{safe(conversationsStats, "total_messages")}</b>
              </div>
            </div>
            <div>Recent Conversations:</div>
            <Table
              columns={[
                "conversation_id",
                "user_id",
                "start_time",
                "duration",
                "status",
                "message_count",
              ]}
              data={conversations}
            />
            {conversationsHasMore && (
              <button
                style={{
                  marginTop: 16,
                  padding: "8px 20px",
                  borderRadius: 6,
                  background: "#0066cc",
                  color: "#fff",
                  border: "none",
                  cursor: "pointer",
                }}
                onClick={() => {
                  const nextOffset = conversationsOffset + PAGE_SIZE;
                  setConversationsOffset(nextOffset);
                  fetchConversations(nextOffset, true);
                }}
                disabled={conversationsLoading}
              >
                {conversationsLoading ? "Loading..." : "Load Older"}
              </button>
            )}
            {!conversationsHasMore && conversations.length > 0 && (
              <div style={{ marginTop: 12, color: "#888" }}>
                No more conversations to load.
              </div>
            )}
          </Section>
        )}
        {selected === "messages" && (
          <Section title="Messages">
            <div style={{ display: "flex", gap: 32, marginBottom: 16 }}>
              <div>
                Total: <b>{safe(messagesStats, "total_messages")}</b>
              </div>
              <div>
                User: <b>{safe(messagesStats, "user_messages")}</b>
              </div>
              <div>
                Bot: <b>{safe(messagesStats, "bot_messages")}</b>
              </div>
              <div>
                System: <b>{safe(messagesStats, "system_messages")}</b>
              </div>
            </div>
            <div>Recent Messages:</div>
            <Table
              columns={[
                "message_id",
                "conversation_id",
                "user_id",
                "message_type",
                "content",
                "timestamp",
              ]}
              data={messages}
            />
            {messagesHasMore && (
              <button
                style={{
                  marginTop: 16,
                  padding: "8px 20px",
                  borderRadius: 6,
                  background: "#0066cc",
                  color: "#fff",
                  border: "none",
                  cursor: "pointer",
                }}
                onClick={() => {
                  const nextOffset = messagesOffset + PAGE_SIZE;
                  setMessagesOffset(nextOffset);
                  fetchMessages(nextOffset, true);
                }}
                disabled={messagesLoading}
              >
                {messagesLoading ? "Loading..." : "Load Older"}
              </button>
            )}
            {!messagesHasMore && messages.length > 0 && (
              <div style={{ marginTop: 12, color: "#888" }}>
                No more messages to load.
              </div>
            )}
          </Section>
        )}
        {selected === "users" && (
          <Section title="Users">
            <div style={{ display: "flex", gap: 32, marginBottom: 16 }}>
              <div>
                Total: <b>{safe(usersStats, "total_users")}</b>
              </div>
              <div>
                Active: <b>{safe(usersStats, "active_users")}</b>
              </div>
              <div>
                New: <b>{safe(usersStats, "new_users")}</b>
              </div>
              <div>
                Returning: <b>{safe(usersStats, "returning_users")}</b>
              </div>
              <div>
                Avg Sessions/User:{" "}
                <b>{safe(usersStats, "average_sessions_per_user")}</b>
              </div>
              <div>
                Avg Messages/User:{" "}
                <b>{safe(usersStats, "average_messages_per_user")}</b>
              </div>
            </div>
            <div>Recent Users:</div>
            <Table
              columns={[
                "user_id",
                "first_seen_at",
                "last_active_at",
                "total_sessions",
                "total_messages",
                "is_active",
                "user_type",
              ]}
              data={users}
            />
            {usersHasMore && (
              <button
                style={{
                  marginTop: 16,
                  padding: "8px 20px",
                  borderRadius: 6,
                  background: "#0066cc",
                  color: "#fff",
                  border: "none",
                  cursor: "pointer",
                }}
                onClick={() => {
                  const nextOffset = usersOffset + PAGE_SIZE;
                  setUsersOffset(nextOffset);
                  fetchUsers(nextOffset, true);
                }}
                disabled={usersLoading}
              >
                {usersLoading ? "Loading..." : "Load Older"}
              </button>
            )}
            {!usersHasMore && users.length > 0 && (
              <div style={{ marginTop: 12, color: "#888" }}>
                No more users to load.
              </div>
            )}
          </Section>
        )}
        {selected === "leads" && (
          <Section title="Leads">
            <div>
              Total Leads: <b>{safe(leadsStats, "total_leads")}</b>
            </div>
            <div>Daily Leads (last 30 days):</div>
            <Table
              columns={["date", "daily_leads", "scheduled_leads"]}
              data={leads}
            />
            {leadsHasMore && (
              <button
                style={{
                  marginTop: 16,
                  padding: "8px 20px",
                  borderRadius: 6,
                  background: "#0066cc",
                  color: "#fff",
                  border: "none",
                  cursor: "pointer",
                }}
                onClick={() => {
                  const nextOffset = leads.length;
                  fetchLeads(nextOffset, true);
                }}
                disabled={leadsLoading}
              >
                {leadsLoading ? "Loading..." : "Load Older"}
              </button>
            )}
            {!leadsHasMore && leads.length > 0 && (
              <div style={{ marginTop: 12, color: "#888" }}>
                No more leads to load.
              </div>
            )}
          </Section>
        )}
      </main>
    </div>
  );
};

export default AnalyticsDashboard;
