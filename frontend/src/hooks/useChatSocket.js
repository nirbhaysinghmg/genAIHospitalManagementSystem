// src/hooks/useChatSocket.js
import { useRef, useEffect, useCallback, useState } from "react";

const MAX_RETRIES = 5;

export const useChatSocket = (setChatHistory, setStreaming, customChatUrl) => {
  const [connectionStatus, setConnectionStatus] = useState("DISCONNECTED");
  const ws = useRef(null);
  const retryCount = useRef(0);
  const reconnectTimeout = useRef(null);
  const chatHistoryRef = useRef([]);

  // Use the provided URL or fall back to default
  const chatUrl = customChatUrl || "ws://localhost:8000/ws";

  // Wait for the WebSocket to be open
  const waitForConnection = useCallback((timeout = 5000, interval = 500) => {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      const checkConnection = () => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
          resolve();
        } else if (Date.now() - startTime > timeout) {
          reject(new Error("Timeout waiting for WebSocket connection."));
        } else {
          setTimeout(checkConnection, interval);
        }
      };
      checkConnection();
    });
  }, []);

  // Connect to the WebSocket server
  const connectWebSocket = useCallback(() => {
    console.log(
      "Attempting to connect WebSocket to:",
      chatUrl,
      "(Retry:",
      retryCount.current,
      ")"
    );
    setConnectionStatus("CONNECTING");

    try {
      if (ws.current) {
        ws.current.close();
      }

      ws.current = new WebSocket(chatUrl);

      ws.current.onopen = () => {
        console.log("Connected to WebSocket server");
        setConnectionStatus("CONNECTED");
        retryCount.current = 0;
      };

      ws.current.onmessage = (event) => {
        console.log("Received message:", event.data);
        try {
          const data = JSON.parse(event.data);

          if (data.error) {
            console.error("Error from server:", data.error);
            setChatHistory((prev) => [
              ...prev,
              { role: "error", text: data.error },
            ]);
            setStreaming(false);
            return;
          }

          if (data.text) {
            setChatHistory((prev) => {
              const lastMessage = prev[prev.length - 1];
              if (
                lastMessage &&
                lastMessage.role === "assistant" &&
                !lastMessage.completed
              ) {
                return [
                  ...prev.slice(0, -1),
                  { ...lastMessage, text: data.text },
                ];
              } else {
                return [
                  ...prev,
                  { role: "assistant", text: data.text, completed: false },
                ];
              }
            });
          }

          if (data.done) {
            setChatHistory((prev) => {
              const lastMessage = prev[prev.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                return [
                  ...prev.slice(0, -1),
                  { ...lastMessage, completed: true },
                ];
              }
              return prev;
            });
            setStreaming(false);
          }
        } catch (error) {
          console.error("Error parsing message:", error, event.data);
        }
      };

      ws.current.onerror = (error) => {
        console.error("WebSocket error:", error);
        setConnectionStatus("ERROR");
      };

      ws.current.onclose = (event) => {
        console.log("WebSocket disconnected:", event);
        setConnectionStatus("DISCONNECTED");

        if (retryCount.current < MAX_RETRIES) {
          const delay = Math.min(1000 * Math.pow(2, retryCount.current), 30000);
          console.log(`Attempting to reconnect in ${delay} ms...`);
          reconnectTimeout.current = setTimeout(() => {
            retryCount.current += 1;
            connectWebSocket();
          }, delay);
        } else {
          console.error("Maximum reconnection attempts reached.");
          setChatHistory((prev) => [
            ...prev,
            {
              role: "system",
              text: "Connection to server lost. Please refresh the page and try again.",
              isError: true,
            },
          ]);
        }
      };
    } catch (error) {
      console.error("Error creating WebSocket:", error);
      setConnectionStatus("ERROR");
    }
  }, [chatUrl, setChatHistory, setStreaming]);

  // Send a message through the WebSocket
  const sendMessage = useCallback(
    (message) => {
      if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
        console.log("WebSocket not connected, attempting to connect...");
        connectWebSocket();

        waitForConnection()
          .then(() => {
            console.log("Connection established, sending message");
            const formattedMessage = {
              user_input: message.user_input || message,
              chat_history: chatHistoryRef.current.map((msg) => ({
                role: msg.role,
                content: msg.text,
              })),
            };
            ws.current.send(JSON.stringify(formattedMessage));
          })
          .catch((error) => {
            console.error("Failed to establish connection:", error);
            setChatHistory((prev) => [
              ...prev,
              {
                role: "system",
                text: "Failed to connect to the server. Please try again later.",
                isError: true,
              },
            ]);
            setStreaming(false);
          });
      } else {
        console.log("Sending message via WebSocket");
        const formattedMessage = {
          user_input: message.user_input || message,
          chat_history: chatHistoryRef.current.map((msg) => ({
            role: msg.role,
            content: msg.text,
          })),
        };
        ws.current.send(JSON.stringify(formattedMessage));
      }
    },
    [connectWebSocket, waitForConnection, setChatHistory, setStreaming]
  );

  // Update chat history ref when chat history changes
  useEffect(() => {
    chatHistoryRef.current = chatHistoryRef.current || [];
  }, []);

  // Connect on component mount
  useEffect(() => {
    console.log("Initializing WebSocket connection to:", chatUrl);
    connectWebSocket();

    return () => {
      console.log("Cleaning up WebSocket connection");
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [chatUrl, connectWebSocket]);

  return {
    ws,
    connectWebSocket,
    waitForConnection,
    sendMessage,
    connectionStatus,
  };
};
