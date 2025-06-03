// src/config.js
const config = {
  companyName: "Healthcare AI",
  companyLogo: "/logo.png",
  agentName: "Healthcare AI Assistant",
  projectName: "Healthcare AI",
  chatUrl: "ws://localhost:8000/ws", // Changed from ws://localhost:8000/ws/chat
  phoneSubmitUrl: "http://localhost:8000/api/mobile",
  theme: {
    primaryColor: "#0066cc",
    secondaryColor: "#f0f0f0",
    backgroundColor: "#ffffff",
    textColor: "#333333",
  },
  // Customizable introductory message
  introductionText: `
### 👋 Welcome to our AI Help Chat.
  `,
  // Suggested questions that will appear after assistant replies
  suggestedQuestions: [
    // Four Wheeler Tyres - Popular Brands
    "Show me tyres for Maruti Suzuki cars",
    "Show me tyres for Hyundai vehicles",
    "Show me tyres for Toyota cars",
    "Show me tyres for Honda vehicles",
    "Show me tyres for Mahindra & Mahindra cars",
    "Show me tyres for Tata Motors vehicles",
    "Show me tyres for Ford cars",

    // Four Wheeler Tyres - By Body Type
    "Best tyres for small cars",
    "Best tyres for hatchbacks",
    "Best tyres for premium hatchbacks",
    "Best tyres for SUVs",
    "Best tyres for compact SUVs",
    "Best tyres for all terrain SUVs",
    "Best tyres for luxury SUVs",
    "Best tyres for sedans",
    "Best tyres for luxury sedans",

    // Four Wheeler Tyres - By Rim Size
    "Show me R14 - 14 inch tyres",
    "Show me R15 - 15 inch tyres",
    "Show me R16 - 16 inch tyres",
    "Show me R17 - 17 inch tyres",
    "Show me R18 - 18 inch tyres",
    "Show me R19 - 19 inch tyres",
    "Show me R20 - 20 inch tyres",

    // Two Wheeler Tyres - Popular Brands
    "Show me tyres for Hero bikes",
    "Show me tyres for Honda bikes",
    "Show me tyres for Royal Enfield bikes",
    "Show me tyres for Bajaj bikes",
    "Show me tyres for TVS bikes",
    "Show me tyres for Yamaha bikes",

    // Two Wheeler Tyres - By Bike Segment
    "Best tyres for sport touring bikes",
    "Best tyres for city urban bikes",
    "Best tyres for cruisers",
    "Best tyres for enduro bikes",
    "Best tyres for scooters",
    "Best tyres for street sports bikes",
  ],
  // Number of questions to show at a time (default: 3)
  showNumberOfQuestions: 3,
  inputPlaceholder: "Type your question here...",
};

export default config;
