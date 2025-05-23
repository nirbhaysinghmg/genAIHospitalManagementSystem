import os
import csv
import json
import re
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import AsyncChromiumLoader, SeleniumURLLoader
from langchain_community.document_transformers import Html2TextTransformer
from dotenv import load_dotenv

# Hard‐code your Gemini API keys (no ADC)
API_KEYS = [
    "AIzaSyCkCdLByf38L5CcH88hf8WSTR_HJYvL738",
    "AIzaSyAhyUH4sCLskS5428llGsaCQoLVAQlWDhw"
]
current_api_index = 0

def get_llm():
    global current_api_index
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        api_key=API_KEYS[current_api_index],
        temperature=0,
        disable_streaming=False
    )

def call_llm_with_retries(prompt_chain, input_data, max_retries=6):
    global current_api_index
    for attempt in range(max_retries):
        try:
            llm = get_llm()
            chain = prompt_chain | llm | StrOutputParser()
            return chain.invoke(input_data)
        except Exception as e:
            msg = str(e)
            print(f"⚠️ LLM attempt {attempt+1} error: {msg}")
            if "429" in msg or "ResourceExhausted" in msg:
                current_api_index = (current_api_index + 1) % len(API_KEYS)
                print(f"🔄 Switching to API Key #{current_api_index+1}...")
                time.sleep(3)
                continue
            break
    return "Error in response"

# Set user agent as environment variable
os.environ["PLAYWRIGHT_USER_AGENT"] = "MyProjectCrawler/1.0"

# 1) URLs to crawl
urls = [
    "https://www.venkateshwarhospitals.com/",
    "https://www.venkateshwarhospitals.com/cardiology.php",
    "https://www.venkateshwarhospitals.com/urology.php",
    "https://www.venkateshwarhospitals.com/critical-care.php" ,
    "https://www.venkateshwarhospitals.com/gastroenterology.php",
    "https://www.venkateshwarhospitals.com/gastrointestinal-and-hepatobiliary-surgery.php",
    "https://www.venkateshwarhospitals.com/neurology.php",
    "https://www.venkateshwarhospitals.com/neurosurgery.php",
    "https://www.venkateshwarhospitals.com/orthopedics-and-joint-replacement.php",
    "https://www.venkateshwarhospitals.com/pulmonology.php",
    "https://www.venkateshwarhospitals.com/radiation-oncology.php",
    "https://www.venkateshwarhospitals.com/surgical-oncology.php",
    "https://www.venkateshwarhospitals.com/nephrology.php"
]

# 2) Load pages via Playwright or Selenium
try:
    loader = AsyncChromiumLoader(urls=urls)
    docs = loader.load()
except Exception as e:
    print(f"AsyncChromiumLoader failed: {e}, trying SeleniumURLLoader...")
    selenium_loader = SeleniumURLLoader(
        urls=urls,
        executable_path="/usr/local/bin/chromedriver",
        browser="chrome",
        headless=True,
        arguments=["--no-sandbox", "--disable-gpu"]
    )
    docs = selenium_loader.load()

# 3) HTML → plain text
transformer = Html2TextTransformer(ignore_links=False)
docs_txt = transformer.transform_documents(docs)

# 4) Prepare department-specific data extraction prompt
extract_data_system = SystemMessagePromptTemplate.from_template("""
You are a healthcare data extraction specialist. Your task is to extract ONLY department-specific information from the provided web page content.

IMPORTANT GUIDELINES:
1. Extract ONLY information that is SPECIFIC to the department mentioned in the URL
2. Ignore any general hospital information or information about other departments
3. Be precise and factual - do not include any assumptions or general statements
4. If information is not available, write "Not available" for that section
5. Maintain a clean, structured format with clear headings

For department pages, extract and organize information in this EXACT format:

# Department Overview
- Department name and brief description
- Department head (if mentioned)
- Department location/floor (if mentioned)

# Services & Treatments
- List of specific services offered by this department
- List of specific treatments available
- Any specialized procedures or techniques

# Medical Team
- Names and specializations of doctors in this department
- Qualifications and experience (if mentioned)
- Areas of expertise within the department

# Technology & Equipment
- List of specialized equipment used in this department
- Advanced technology or facilities specific to this department
- Diagnostic tools or machines available

# Conditions Treated
- Specific medical conditions treated in this department
- Types of cases handled
- Special focus areas or expertise

# Patient Care
- Specialized patient care services
- Support services specific to this department
- Any unique patient care features

# Additional Information
- Any other department-specific information
- Special programs or initiatives
- Department achievements or recognition

Remember:
- Only include information that is EXPLICITLY mentioned in the text
- Do not make assumptions or add general information
- If a section has no specific information, write "Not available"
- Keep the format clean and consistent
""")

human_message_template = HumanMessagePromptTemplate.from_template("Page Text: {page_text}")

extract_data_prompt = ChatPromptTemplate.from_messages([
    extract_data_system,
    human_message_template
])

# 5) Write CSV and extract data on the fly
output_path = "hospital_departments_data.csv"
with open(output_path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
    writer = csv.writer(csvfile)
    # Write header
    writer.writerow(["department_url", "department_data"])
    
    for idx, doc in enumerate(docs_txt, start=1):
        raw = doc.page_content.replace("\n", " ").strip()
        url = doc.metadata.get("source", "")
        print(f"🔍 Processing department page {idx}: {url}")
        
        # Limit content length to avoid token limits
        content_to_process = raw[:50000] if len(raw) > 50000 else raw
        
        # Extract department-specific data
        extracted_data = call_llm_with_retries(extract_data_prompt, {"page_text": content_to_process})
        
        # Clean the extracted data
        cleaned_data = re.sub(r'\s+', ' ', extracted_data).strip()
        
        writer.writerow([
            url,
            cleaned_data
        ])
        csvfile.flush()  # ensure it's written immediately
        time.sleep(2)  # Add delay between API calls

print(f"✅ Saved department-specific data to {output_path}")





