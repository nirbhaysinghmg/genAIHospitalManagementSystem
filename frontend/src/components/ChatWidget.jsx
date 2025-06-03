// ChatWidget.jsx

import React, { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatSocket } from "../hooks/useChatSocket";
import defaultConfig from "../config";
import "./ChatWidget.css"; // Import CSS from the same directory

const FeedbackPrompt = ({ onYes, onNo }) => (
  <div
    style={{
      marginTop: 8,
      marginBottom: 8,
      background: "#f7f7f7",
      borderRadius: 8,
      padding: 12,
      display: "flex",
      alignItems: "center",
      gap: 12,
    }}
  >
    <span>Was this helpful?</span>
    <button
      style={{
        background: "#4caf50",
        color: "#fff",
        border: "none",
        borderRadius: 4,
        padding: "4px 12px",
        cursor: "pointer",
      }}
      onClick={onYes}
    >
      Yes
    </button>
    <button
      style={{
        background: "#f44336",
        color: "#fff",
        border: "none",
        borderRadius: 4,
        padding: "4px 12px",
        cursor: "pointer",
      }}
      onClick={onNo}
    >
      No
    </button>
  </div>
);

const FeedbackForm = ({ onClose, onSubmit }) => {
  const [issues, setIssues] = useState([]);
  const [otherText, setOtherText] = useState("");
  const [supportOption, setSupportOption] = useState("");
  const [execMethod, setExecMethod] = useState("");

  const issueOptions = [
    { value: "off-topic", label: "The answer was off-topic" },
    { value: "too-short", label: "It was too short" },
    { value: "too-complex", label: "It was too complex" },
    { value: "different-help", label: "I need a different kind of help" },
    { value: "other", label: "Other:" },
  ];

  const handleIssueChange = (val) => {
    if (issues.includes(val)) {
      setIssues(issues.filter((i) => i !== val));
      if (val === "other") setOtherText("");
    } else {
      setIssues([...issues, val]);
    }
  };

  const canSubmit =
    issues.length > 0 &&
    supportOption &&
    (supportOption !== "talk-exec" || execMethod);

  const handleSubmit = () => {
    const feedback = {
      issues,
      otherText: issues.includes("other") ? otherText : "",
      supportOption,
      execMethod: supportOption === "talk-exec" ? execMethod : "",
    };
    onSubmit(feedback);
  };

  return (
    <div
      style={{
        marginTop: 8,
        marginBottom: 8,
        background: "#fffbe6",
        border: "1px solid #ffe58f",
        borderRadius: 8,
        padding: 16,
        maxWidth: 400,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 8 }}>
        What seems to be the issue?{" "}
        <span style={{ fontWeight: 400, fontSize: 13 }}>
          (Choose one or more)
        </span>
      </div>
      <div style={{ marginBottom: 12 }}>
        {issueOptions.map((opt) => (
          <div key={opt.value} style={{ marginBottom: 4 }}>
            <label>
              <input
                type="checkbox"
                checked={issues.includes(opt.value)}
                onChange={() => handleIssueChange(opt.value)}
                style={{ marginRight: 6 }}
              />
              {opt.label}
              {opt.value === "other" && issues.includes("other") && (
                <input
                  type="text"
                  value={otherText}
                  onChange={(e) => setOtherText(e.target.value)}
                  placeholder="Please specify"
                  style={{
                    marginLeft: 8,
                    padding: 2,
                    borderRadius: 4,
                    border: "1px solid #ccc",
                    width: 140,
                  }}
                />
              )}
            </label>
          </div>
        ))}
      </div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Would you like to:</div>
      <div style={{ marginBottom: 12 }}>
        <label>
          <input
            type="radio"
            name="support"
            value="rephrase"
            checked={supportOption === "rephrase"}
            onChange={() => setSupportOption("rephrase")}
            style={{ marginRight: 6 }}
          />
          Try rephrasing your question
        </label>
        <br />
        <label>
          <input
            type="radio"
            name="support"
            value="talk-exec"
            checked={supportOption === "talk-exec"}
            onChange={() => setSupportOption("talk-exec")}
            style={{ marginRight: 6 }}
          />
          Talk to a human executive
        </label>
      </div>
      {supportOption === "talk-exec" && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            Preferred method to connect?
          </div>
          <label>
            <input
              type="radio"
              name="exec-method"
              value="chat"
              checked={execMethod === "chat"}
              onChange={() => setExecMethod("chat")}
              style={{ marginRight: 6 }}
            />
            Chat now
          </label>
          <br />
          <label>
            <input
              type="radio"
              name="exec-method"
              value="call"
              checked={execMethod === "call"}
              onChange={() => setExecMethod("call")}
              style={{ marginRight: 6 }}
            />
            Schedule a call
          </label>
          <br />
          <label>
            <input
              type="radio"
              name="exec-method"
              value="email"
              checked={execMethod === "email"}
              onChange={() => setExecMethod("email")}
              style={{ marginRight: 6 }}
            />
            Email me back
          </label>
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          style={{
            background: canSubmit ? "#0066cc" : "#ccc",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            padding: "4px 12px",
            cursor: canSubmit ? "pointer" : "not-allowed",
          }}
          onClick={handleSubmit}
          disabled={!canSubmit}
        >
          Submit
        </button>
        <button
          style={{
            background: "#eee",
            color: "#333",
            border: "none",
            borderRadius: 4,
            padding: "4px 12px",
            cursor: "pointer",
          }}
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </div>
  );
};

const ChatWidget = ({ config: userConfig }) => {
  // Merge config with defaults
  const cfg = { ...defaultConfig, ...userConfig };
  const allQuestions = cfg.suggestedQuestions || [];
  const triggerCount = Number.isInteger(cfg.showNumberOfQuestions)
    ? cfg.showNumberOfQuestions
    : 3;

  // Chat state
  const [chatHistory, setChatHistory] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const [feedback, setFeeback] = useState(false);

  // Scheduling form state
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [scheduleFormData, setScheduleFormData] = useState({
    name: "",
    patientId: "",
    date: "",
    timeSlot: "",
  });
  const [scheduleFormSubmitted, setScheduleFormSubmitted] = useState(false);
  const [scheduleError, setScheduleError] = useState("");

  // Suggestions state
  const [usedQuestions, setUsedQuestions] = useState([]);
  const [suggestions, setSuggestions] = useState(
    allQuestions.slice(0, triggerCount)
  );

  // Feedback state
  const [feedbackState, setFeedbackState] = useState({
    showPrompt: false,
    showForm: false,
    lastAssistantIdx: null,
    submitted: false,
  });

  // Track session start time
  const [sessionStartTime, setSessionStartTime] = useState(Date.now());
  useEffect(() => {
    setSessionStartTime(Date.now());
  }, []);

  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  // WebSocket connection
  const { sendMessage, connectionStatus, trackUserAction } = useChatSocket(
    setChatHistory,
    setStreaming,
    cfg.chatUrl
  );

  // Add session tracking on component mount
  useEffect(() => {
    // Track page load/refresh as a new session
    trackUserAction("session_start", {
      referrer: document.referrer,
      userAgent: navigator.userAgent,
    });
  }, [trackUserAction]);

  // Seed the initial system message
  useEffect(() => {
    setChatHistory([{ role: "system", text: cfg.introductionText }]);
  }, [cfg.introductionText]);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, suggestions, showScheduleForm]);

  // Auto-resize textarea - modified to respect fixed height
  useEffect(() => {
    if (textareaRef.current) {
      // Only adjust height if content exceeds the fixed height
      const scrollHeight = textareaRef.current.scrollHeight;
      const fixedHeight = 55; // Match the CSS height

      if (scrollHeight > fixedHeight) {
        // Allow content to scroll within the fixed height
        textareaRef.current.style.overflowY = "auto";
      } else {
        // Hide scrollbar when not needed
        textareaRef.current.style.overflowY = "hidden";
      }
    }
  }, [input]);

  // Clear suggestions when streaming
  useEffect(() => {
    if (streaming) setSuggestions([]);
  }, [streaming]);

  // Show suggestions after assistant reply
  useEffect(() => {
    let timer;
    if (!streaming && chatHistory.some((m) => m.role === "assistant")) {
      timer = setTimeout(() => {
        const remaining = allQuestions.filter(
          (q) => !usedQuestions.includes(q)
        );
        setSuggestions(remaining.slice(0, triggerCount));
      }, 2000);
    }
    return () => clearTimeout(timer);
  }, [streaming, chatHistory, usedQuestions, allQuestions, triggerCount]);

  // Show feedback prompt after each new assistant message
  useEffect(() => {
    // Find the last assistant message
    const lastIdx = [...chatHistory]
      .reverse()
      .findIndex((m) => m.role === "assistant");
    if (lastIdx !== -1) {
      const idx = chatHistory.length - 1 - lastIdx;
      if (feedbackState.lastAssistantIdx !== idx) {
        setFeedbackState({
          showPrompt: true,
          showForm: false,
          lastAssistantIdx: idx,
          submitted: false,
        });
      }
    }
    // eslint-disable-next-line
  }, [chatHistory]);

  // Toggle fullscreen mode
  const toggleFullScreen = () => {
    setFullScreen(!fullScreen);

    // Ensure chat scrolls to bottom after toggling fullscreen
    setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 300);
  };

  // Handle sending message
  const handleSendMessage = (text = input) => {
    if (!text.trim() || streaming) return;

    // Track user question
    trackUserAction("question_asked", { question: text });

    // Add user message to chat
    setChatHistory((prev) => [...prev, { role: "user", text }]);
    setStreaming(true);

    // Check if this is an appointment scheduling request
    const schedulingPhrases = [
      "schedule an appointment",
      "book an appointment",
      "make an appointment",
      "set up an appointment",
      "i need an appointment",
      "booking",
    ];

    const normalizedText = text.toLowerCase().trim();
    const isSchedulingRequest = schedulingPhrases.some((phrase) =>
      normalizedText.includes(phrase.toLowerCase())
    );

    if (isSchedulingRequest) {
      setShowScheduleForm(true);
      // Still send the message to get AI response
    }

    sendMessage({
      user_input: text,
    });

    // Clear input field if it's from the input box
    if (text === input) {
      setInput("");
    }
  };

  // Handle suggestion click
  const handleSuggestion = (question) => {
    handleSendMessage(question);
    setUsedQuestions((prev) => [...prev, question]);
  };

  // Handle Enter key press
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Handle schedule form input changes
  const handleScheduleFormChange = (e) => {
    const { name, value } = e.target;
    setScheduleFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
    setScheduleError("");
  };

  // Handle schedule form submission
  const handleScheduleSubmit = async (e) => {
    e.preventDefault();

    // Validate form
    if (!scheduleFormData.name.trim()) {
      setScheduleError("Please enter your name");
      return;
    }
    if (!scheduleFormData.patientId.trim()) {
      setScheduleError("Please enter your patient ID");
      return;
    }
    if (!scheduleFormData.date) {
      setScheduleError("Please select a date");
      return;
    }
    if (!scheduleFormData.timeSlot) {
      setScheduleError("Please select a time slot");
      return;
    }

    try {
      // Capture lead in analytics
      const leadResponse = await fetch(
        `http://localhost:8000/analytics/leads`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: scheduleFormData.name,
            lead_type: "appointment_scheduled",
          }),
        }
      );

      if (!leadResponse.ok) {
        console.error("Failed to capture lead");
      }

      console.log("Lead captured");

      // Add appointment details to chat
      setChatHistory((prev) => [
        ...prev,
        {
          role: "user",
          text: `I'd like to schedule an appointment with the following details:
- Name: ${scheduleFormData.name}
- Patient ID: ${scheduleFormData.patientId}
- Date: ${scheduleFormData.date}
- Time: ${scheduleFormData.timeSlot}`,
        },
      ]);

      // Send appointment details to backend
      sendMessage({
        user_input: `Schedule appointment for patient ${scheduleFormData.patientId} named ${scheduleFormData.name} on ${scheduleFormData.date} during ${scheduleFormData.timeSlot}`,
        appointment_details: {
          name: scheduleFormData.name,
          patient_id: scheduleFormData.patientId,
          date: scheduleFormData.date,
          time_slot: scheduleFormData.timeSlot,
        },
      });

      setStreaming(true);
      setScheduleFormSubmitted(true);
      setShowScheduleForm(false);

      // Reset form after submission
      setTimeout(() => {
        setScheduleFormData({
          name: "",
          patientId: "",
          date: "",
          timeSlot: "",
        });
        setScheduleFormSubmitted(false);
      }, 1000);
    } catch (error) {
      console.error("Error submitting appointment:", error);
      setScheduleError("Failed to submit appointment. Please try again.");
    }
  };

  // Add tracking to chatbot open function
  const handleChatbotOpen = () => {
    trackUserAction("chatbot_opened", { method: "button_click" });
    window.openChatbot();
  };

  const handleFeedbackYes = () => {
    setFeedbackState((f) => ({ ...f, showPrompt: false, submitted: true }));
  };
  const handleFeedbackNo = () => {
    setFeedbackState((f) => ({ ...f, showPrompt: false, showForm: true }));
  };
  const handleFeedbackFormSubmit = (data) => {
    setFeedbackState((f) => ({ ...f, showForm: false, submitted: true }));
    // Optionally send feedback to backend here
    // If user opted for human handover, log it
    if (data.supportOption === "talk-exec") {
      const userId = localStorage.getItem("healthcare_user_id") || "";
      const sessionId = localStorage.getItem("healthcare_session_id") || "";
      // Find the last user message
      const lastUserMsg =
        [...chatHistory].reverse().find((m) => m.role === "user")?.text || "";
      fetch("http://localhost:8000/analytics/human_handover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          session_id: sessionId,
          issues: data.issues,
          other_text: data.otherText,
          method: data.execMethod,
          support_option: data.supportOption,
          requested_at: new Date()
            .toISOString()
            .replace("T", " ")
            .replace("Z", "")
            .split(".")[0],
          last_message: lastUserMsg,
        }),
      }).catch(() => {});
    }
  };
  const handleFeedbackFormClose = () => {
    setFeedbackState((f) => ({ ...f, showForm: false }));
  };

  // Add this function inside ChatWidget
  const handleCloseChatbot = () => {
    const userId = localStorage.getItem("healthcare_user_id") || "";
    const sessionId = localStorage.getItem("healthcare_session_id") || "";
    const closedAt = new Date();
    const timeSpentSeconds = Math.floor((Date.now() - sessionStartTime) / 1000);
    const lastUserMsg =
      [...chatHistory].reverse().find((m) => m.role === "user")?.text || "";
    const lastBotMsg =
      [...chatHistory].reverse().find((m) => m.role === "assistant")?.text ||
      "";

    // Record chatbot close event
    fetch("http://localhost:8000/analytics/chatbot_close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        session_id: sessionId,
        closed_at: closedAt
          .toISOString()
          .replace("T", " ")
          .replace("Z", "")
          .split(".")[0],
        time_spent_seconds: timeSpentSeconds,
        last_user_message: lastUserMsg,
        last_bot_message: lastBotMsg,
      }),
    }).catch(() => {});

    // Record session end event
    fetch("http://localhost:8000/analytics/session_end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        session_id: sessionId,
        end_time: closedAt
          .toISOString()
          .replace("T", " ")
          .replace("Z", "")
          .split(".")[0],
        duration: timeSpentSeconds,
      }),
    }).catch(() => {});

    window.closeChatbot?.();
  };

  return (
    <div
      id="chatbot"
      className={`chat-widget${fullScreen ? " fullscreen" : ""}`}
      style={{ "--primary-color": cfg.primaryColor }}
    >
      <div className="chat-wrapper">
        {/* Header */}
        <div className="chat-header">
          <img
            src={cfg.companyLogo}
            alt={`${cfg.companyName} logo`}
            className="chat-logo"
          />
          <h2 className="chat-title">{cfg.companyName} AI Assistant</h2>
          <div className="header-buttons">
            <button
              onClick={toggleFullScreen}
              className="fullscreen-button"
              aria-label="Toggle fullscreen"
            >
              {fullScreen ? (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M8 3v3a2 2 0 0 1-2 2H3" />
                  <path d="M21 8h-3a2 2 0 0 1-2-2V3" />
                  <path d="M3 16h3a2 2 0 0 1 2 2v3" />
                  <path d="M21 16h-3a2 2 0 0 1-2 2v3" />
                </svg>
              ) : (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M8 3H5a2 2 0 0 0-2 2v3" />
                  <path d="M21 8V5a2 2 0 0 0-2-2h-3" />
                  <path d="M3 16v3a2 2 0 0 0 2 2h3" />
                  <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
                </svg>
              )}
            </button>
            <button
              onClick={handleCloseChatbot}
              className="close-button"
              aria-label="Close chat"
            >
              ×
            </button>
          </div>
        </div>

        {/* Connection status indicator */}
        {connectionStatus !== "CONNECTED" && (
          <div
            className={`connection-status ${connectionStatus.toLowerCase()}`}
          >
            {connectionStatus === "CONNECTING"
              ? "Connecting..."
              : "Disconnected - Please check your connection"}
          </div>
        )}

        {/* Chat Content */}
        <div className="chat-content">
          {chatHistory.map((msg, i) => (
            <div
              key={i}
              className={`chat-block ${msg.role} ${msg.isError ? "error" : ""}`}
            >
              {msg.role !== "system" && (
                <div className="message-label">
                  {msg.role === "user"
                    ? "You"
                    : `${cfg.companyName} AI Assistant`}
                </div>
              )}
              <div
                className={`message ${
                  msg.role === "assistant" ? "assistant-message" : ""
                }`}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.text}
                </ReactMarkdown>
              </div>
              {/* Feedback prompt for the most recent assistant answer */}
              {msg.role === "assistant" &&
                i === feedbackState.lastAssistantIdx &&
                feedbackState.showPrompt &&
                !feedbackState.submitted && (
                  <FeedbackPrompt
                    onYes={handleFeedbackYes}
                    onNo={handleFeedbackNo}
                  />
                )}
              {/* Feedback form if user said No */}
              {msg.role === "assistant" &&
                i === feedbackState.lastAssistantIdx &&
                feedbackState.showForm && (
                  <FeedbackForm
                    onClose={handleFeedbackFormClose}
                    onSubmit={handleFeedbackFormSubmit}
                  />
                )}
            </div>
          ))}

          {/* Appointment Scheduling Form */}
          {showScheduleForm && !streaming && (
            <div className="schedule-form-container">
              <h3>Schedule an Appointment</h3>
              {scheduleError && (
                <div className="form-error">{scheduleError}</div>
              )}
              <form onSubmit={handleScheduleSubmit} className="schedule-form">
                <div className="form-group">
                  <label htmlFor="name">Full Name</label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={scheduleFormData.name}
                    onChange={handleScheduleFormChange}
                    placeholder="Enter your full name"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="patientId">Patient ID</label>
                  <input
                    type="text"
                    id="patientId"
                    name="patientId"
                    value={scheduleFormData.patientId}
                    onChange={handleScheduleFormChange}
                    placeholder="Enter your patient ID (e.g., P12345)"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="date">Appointment Date</label>
                  <input
                    type="date"
                    id="date"
                    name="date"
                    value={scheduleFormData.date}
                    onChange={handleScheduleFormChange}
                    min={new Date().toISOString().split("T")[0]}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="timeSlot">Time Slot</label>
                  <select
                    id="timeSlot"
                    name="timeSlot"
                    value={scheduleFormData.timeSlot}
                    onChange={handleScheduleFormChange}
                  >
                    <option value="">Select a time slot</option>
                    <option value="9:00 AM - 12:00 PM">
                      9:00 AM - 12:00 PM
                    </option>
                    <option value="12:00 PM - 3:00 PM">
                      12:00 PM - 3:00 PM
                    </option>
                    <option value="3:00 PM - 6:00 PM">3:00 PM - 6:00 PM</option>
                    <option value="6:00 PM - 9:00 PM">6:00 PM - 9:00 PM</option>
                  </select>
                </div>

                <div className="form-actions">
                  <button
                    type="button"
                    className="cancel-button"
                    onClick={() => setShowScheduleForm(false)}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="submit-button">
                    Schedule Appointment
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Suggestions */}
          {!streaming && !showScheduleForm && suggestions.length > 0 && (
            <div className="suggestions">
              {suggestions.map((question, i) => (
                <button
                  key={i}
                  className="suggestion-button"
                  onClick={() => handleSuggestion(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          )}

          {streaming && (
            <div className="chat-block assistant">
              <div className="message-label">
                {cfg.companyName} AI Assistant
              </div>
              <div className="message">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="chat-input-area">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={cfg.inputPlaceholder}
            rows="1"
            className="chat-input"
            disabled={streaming}
            style={{ height: "55px" }}
          />
          <button
            className="send-button"
            onClick={() => {
              if (input.trim() && !streaming) {
                handleSendMessage();
              }
            }}
            disabled={!input.trim() || streaming}
            aria-label="Send message"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              width="24"
              height="24"
            >
              <path
                fill={streaming ? "#d7d7d7" : "#ffffff"}
                d="M22,11.7V12h-0.1c-0.1,1-17.7,9.5-18.8,9.1c-1.1-0.4,2.4-6.7,3-7.5C6.8,12.9,17.1,12,17.1,12H17c0,0,0-0.2,0-0.2c0,0,0,0,0,0c0-0.4-10.2-1-10.8-1.7c-0.6-0.7-4-7.1-3-7.5C4.3,2.1,22,10.5,22,11.7z"
              ></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatWidget;
