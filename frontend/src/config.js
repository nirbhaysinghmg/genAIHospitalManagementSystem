// src/config.js
const config = {
  companyName: "Healthcare AI",
  companyLogo: "/logo.png",
  agentName: "Healthcare AI Assistant",
  projectName: "Healthcare AI",
  chatUrl: "ws://localhost:8000/ws",  // Changed from ws://localhost:8000/ws/chat
  phoneSubmitUrl: "http://localhost:8000/api/mobile",
  theme: {
    primaryColor: "#0066cc",
    secondaryColor: "#f0f0f0",
    backgroundColor: "#ffffff",
    textColor: "#333333",
  },
  // Customizable introductory message
  introductionText: `
### 👋 Welcome to Healthcare AI Assistant
I can help you with appointments, medical information, and more.
  `,
  // Suggested questions that will appear after assistant replies
  suggestedQuestions: [
    "Schedule an appointment For Me",
    "What are your operating hours?",
    "Can I speak with a doctor online?",
    "How do I view my medical records?",
    "What insurance plans do you accept?",
    "Do I need a referral to see a specialist?",
    "How can I refill my prescription?",
    "What should I do to prepare for my appointment?",
    "Where are your facilities located?",
    "How do I cancel or reschedule an appointment?",
  ],
  // Number of questions to show at a time (default: 3)
  showNumberOfQuestions: 3,
  inputPlaceholder: "Type your question here...",
};

export default config;


