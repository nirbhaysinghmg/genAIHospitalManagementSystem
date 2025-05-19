// src/chatbot-widget.js

import React from "react";
import ReactDOM from "react-dom";
import ChatWidget from "./components/ChatWidget";
// import "./components/ChatWidget.css";  // Removed

// Default configuration
const defaultConfig = {
  container: "#healthcare-ai-container",
  chatUrl: "ws://localhost:8000/ws", // Changed from ws://localhost:8000/ws/chat
  companyName: "Healthcare AI",
  companyLogo: "/logo.png",
  primaryColor: "#0066cc",
  showButton: true,
  showGreeting: true,
  greetingText:
    "Need help with your healthcare needs? Chat with our AI assistant!",
  introductionText:
    "Hello! I'm your healthcare assistant. How can I help you today?",
  inputPlaceholder: "Ask about appointments, departments, or services...",
};

// UMD export: exposes HealthcareAIWidget.init(...)
const HealthcareAIWidget = {
  init: (userConfig = {}) => {
    console.log("Initializing HealthcareAIWidget");

    // Merge user config with defaults
    const config = { ...defaultConfig, ...userConfig };

    console.log("Using configuration:", config);
    console.log("WebSocket URL:", config.chatUrl);

    // Validate WebSocket URL
    if (!config.chatUrl) {
      console.error("No WebSocket URL provided. Using default localhost URL.");
      config.chatUrl = "ws://localhost:8000/ws/chat";
    }

    // Ensure WebSocket URL has correct protocol
    if (
      !config.chatUrl.startsWith("ws://") &&
      !config.chatUrl.startsWith("wss://")
    ) {
      console.error(
        "Invalid WebSocket URL protocol. URL must start with ws:// or wss://"
      );
      return;
    }

    // Check for existing chatbot container
    let container = null;

    // First check if there's an existing chatbot div
    const existingChatbot = document.getElementById("chatbot");

    if (existingChatbot) {
      console.log("Found existing chatbot container with id 'chatbot'");
      container = existingChatbot;
    } else {
      // If no existing chatbot, use the specified container
      container =
        typeof config.container === "string"
          ? document.querySelector(config.container)
          : config.container;
    }

    if (!container) {
      console.error(`Chatbot container not found: ${config.container}`);
      return;
    }

    // Create chat button if it doesn't exist and showButton is true
    if (config.showButton) {
      // First, check if there's an existing button with id "elan-ai-button"
      const existingButton = document.getElementById("elan-ai-button");

      if (existingButton) {
        console.log(
          "Found existing button with id 'elan-ai-button', will use it instead of creating a new one"
        );

        // Update the existing button's click handler
        existingButton.onclick = function (e) {
          e.preventDefault();
          e.stopPropagation();
          console.log("Existing button clicked");
          window.openChatbot();
          return false;
        };

        // Add hover effect if not already present
        if (!document.querySelector("style#elan-button-style")) {
          const style = document.createElement("style");
          style.id = "elan-button-style";
          style.textContent = `
            #elan-ai-button:hover {
              transform: translateY(-3px);
              box-shadow: 0 6px 20px rgba(0,74,173,0.45);
              background: linear-gradient(135deg, #0052c2 0%, #0074e8 100%);
            }
            
            #elan-ai-button:active {
              transform: translateY(0);
              box-shadow: 0 3px 10px rgba(0,74,173,0.3);
            }
            
            @media (max-width: 768px) {
              #elan-ai-button {
                width: auto;
                padding: 12px !important;
              }
              
              #elan-ai-button span {
                display: none;
              }
            }
          `;
          document.head.appendChild(style);
        }
      } else if (!document.getElementById("healthcare-ai-button")) {
        // Create button only if no existing button and no healthcare-ai-button
        const button = document.createElement("div");
        button.id = "healthcare-ai-button";
        button.className = "healthcare-ai-button";
        button.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
        `;

        // Style the button
        Object.assign(button.style, {
          position: "fixed",
          bottom: "20px",
          right: "20px",
          width: "60px",
          height: "60px",
          borderRadius: "50%",
          backgroundColor: config.primaryColor || "#0066cc",
          color: "white",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          boxShadow: "0 4px 8px rgba(0,0,0,0.2)",
          zIndex: "999",
        });

        document.body.appendChild(button);

        // Explicitly attach click event to ensure it works on all devices
        button.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          console.log("Button clicked");
          window.openChatbot();
          return false;
        });

        console.log("Chat button created and added to the page");
      } else {
        console.log("Chat button already exists");
      }
    }

    // Create greeting message if enabled
    if (
      config.showGreeting &&
      !document.getElementById("healthcare-ai-greeting")
    ) {
      const greeting = document.createElement("div");
      greeting.id = "healthcare-ai-greeting";
      greeting.className = "healthcare-ai-greeting";
      greeting.innerHTML = `
        <p>${config.greetingText}</p>
        <span class="greeting-close">&times;</span>
      `;

      // Style the greeting
      Object.assign(greeting.style, {
        position: "fixed",
        bottom: "90px",
        right: "20px",
        maxWidth: "300px",
        padding: "15px",
        backgroundColor: "white",
        borderRadius: "10px",
        boxShadow: "0 4px 8px rgba(0,0,0,0.1)",
        zIndex: "998",
        transition: "all 0.3s ease",
      });

      document.body.appendChild(greeting);

      // Close button for greeting
      const closeBtn = greeting.querySelector(".greeting-close");
      if (closeBtn) {
        Object.assign(closeBtn.style, {
          position: "absolute",
          top: "5px",
          right: "10px",
          cursor: "pointer",
          fontSize: "18px",
        });

        closeBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          greeting.style.display = "none";
        });
      }

      // Also allow clicking greeting to open chatbot
      greeting.addEventListener("click", function (e) {
        if (e.target !== closeBtn) {
          window.openChatbot();
        }
      });

      // Auto-hide greeting after 8 seconds
      setTimeout(() => {
        const greeting = document.getElementById("healthcare-ai-greeting");
        if (greeting) {
          greeting.classList.add("hidden");
        }
      }, 8000);

      console.log("Greeting message created and added to the page");
    }

    // Render the React ChatWidget, passing the config as a prop
    ReactDOM.render(<ChatWidget config={config} />, container);
    console.log("ChatWidget rendered in container");
  },
};

export default HealthcareAIWidget;

// Make chatbot opener available globally
if (typeof window !== "undefined") {
  window.openChatbot = function () {
    console.log("Opening chatbot...");
    const chatbot = document.getElementById("chatbot");
    const healthcareButton = document.getElementById("healthcare-ai-button");
    const elanButton = document.getElementById("elan-ai-button");
    const greeting = document.getElementById("healthcare-ai-greeting");

    if (chatbot) {
      // Remove hidden class and ensure display is block
      chatbot.classList.remove("hidden");
      chatbot.style.display = "block";
      console.log("Chatbot display updated");
    } else {
      console.error("Chatbot element not found");
    }

    // Hide buttons and greeting
    if (healthcareButton) healthcareButton.style.display = "none";
    if (elanButton) elanButton.style.display = "none";
    if (greeting) greeting.style.display = "none";
  };

  // Make chatbot closer available globally
  window.closeChatbot = function () {
    console.log("Closing chatbot...");
    const chatbot = document.getElementById("chatbot");
    const healthcareButton = document.getElementById("healthcare-ai-button");
    const elanButton = document.getElementById("elan-ai-button");

    if (chatbot) {
      chatbot.classList.add("hidden");
      // Use setTimeout to ensure the transition completes before hiding
      setTimeout(() => {
        chatbot.style.display = "none";
      }, 300);
    }

    // Show the appropriate button
    if (elanButton) {
      elanButton.style.display = "block";
    } else if (healthcareButton) {
      healthcareButton.style.display = "flex";
    }
  };

  console.log("Global chatbot functions defined");
}
