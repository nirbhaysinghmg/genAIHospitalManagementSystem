// src/hooks/useChatSocket.js
import { useRef, useEffect, useCallback, useState } from "react";

const MAX_RETRIES = 5;

export const useChatSocket = (setChatHistory, setStreaming, customChatUrl) => {
  const [connectionStatus, setConnectionStatus] = useState("DISCONNECTED");
  const ws = useRef(null);
  const retryCount = useRef(0);
  const reconnectTimeout = useRef(null);

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

    // Update connection status
    setConnectionStatus("CONNECTING");

    try {
      // Close existing connection if any
      if (ws.current) {
        ws.current.close();
      }

      // Create new WebSocket connection
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

          // Handle error messages
          if (data.error) {
            console.error("Error from server:", data.error);
            setChatHistory((prev) => [
              ...prev,
              { role: "error", text: data.error },
            ]);
            setStreaming(false);
            return;
          }

          // Handle text messages (from backend)
          if (data.text) {
            setChatHistory((prev) => {
              const lastMessage = prev[prev.length - 1];
              if (
                lastMessage &&
                lastMessage.role === "assistant" &&
                !lastMessage.completed
              ) {
                const updatedMessage = { ...lastMessage, text: data.text };
                return [...prev.slice(0, -1), updatedMessage];
              } else {
                return [
                  ...prev,
                  { role: "assistant", text: data.text, completed: false },
                ];
              }
            });
          }

          // Handle completion flag
          if (data.done) {
            setChatHistory((prev) => {
              const lastMessage = prev[prev.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                const updatedMessage = { ...lastMessage, completed: true };
                return [...prev.slice(0, -1), updatedMessage];
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
        // Don't close here, let onclose handle it
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

        // Wait for connection and then send
        waitForConnection()
          .then(() => {
            console.log("Connection established, sending message");
            ws.current.send(JSON.stringify(message));
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
        // WebSocket is already open, send directly
        console.log("Sending message via WebSocket");
        ws.current.send(JSON.stringify(message));
      }
    },
    [connectWebSocket, waitForConnection, setChatHistory, setStreaming]
  );

  // Connect on component mount
  useEffect(() => {
    console.log("Initializing WebSocket connection to:", chatUrl);
    connectWebSocket();

    // Cleanup on unmount
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
