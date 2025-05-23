import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserConfig

# Load environment variables from .env file
load_dotenv()

# Initialize the language model with the API key from environment variables
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    streaming=False,
    google_api_key=os.getenv("GOOGLE_API_KEY")  # Ensure this variable is set in your .env file
)

# Configure the browser settings
config = BrowserConfig(
    headless=True,   # Run browser in headless mode (no UI)
    keep_alive=True  # Keep the browser session alive for reuse
)

# Initialize the browser with the specified configuration
browser = Browser(config=config)

# Define the task for the agent
task_description = (
    "Scrape the website for information about hospital departments, services, and doctors. "
    "Return the data in a structured JSON format with keys: 'department', 'service_list', and 'doctor_list'."
)

# Initialize the agent with the task, language model, and browser
agent = Agent(
    task=task_description,
    llm=llm,
    browser=browser
)

# Define the main asynchronous function to run the agent
async def main():
    try:
        # Execute the agent's task on the specified URL
        result = await agent.run(url="https://www.venkateshwarhospitals.com/")
        print("Scraped data:", result)
    finally:
        # Wait for user input before closing the browser
        input("Press Enter to close the browser…")
        await browser.close()

# Entry point of the script
if __name__ == "__main__":
    asyncio.run(main())
