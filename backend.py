import os
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import ConversationalRetrievalChain
from langchain_core.documents import Document
import json


from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
  CORSMiddleware,
  allow_origins = ['*'],
  allow_headers= ["*"],
  allow_methods=["*"]
)


CSV_path = "data/hospital_data.csv"
df = pd.read_csv(CSV_path)
EMBED_MODEL = "models/gemini-001"
embeddings = GoogleGenerativeAIEmbeddings(model = EMBED_MODEL,google_api_key = os.getenv("Gemini_API_KEY"))

splitter = CharacterTextSplitter(chunk_size = 1024, chunk_overlap = 200)

documents = []

for idx, row in df.iterrows():
  row_dict = row.to_dict()
  content = "\n".joint([f"{k}: {v}" for k, v in row_dict.items()])
  source = str(row.iloc[0])
  chunks = splitter.split_text(content)
  for chunk in chunks:
    documents.append(Document(page_content = chunk, metadata = {"source": source, "row": idx}))


print("Created document chunks")

PERSIST_DIRECTORY = "chroma_db"

ids = [str(uuid.uuid4()) for _ in documents]

vector_store = Chroma.from_documents(
  documents = documents,
  embedding = embeddings,
  persist_directory = PERSIST_DIRECTORY,
  ids = ids
)

llm = ChatGoogleGenerativeAI(
  model = "gemini-2.0-flash",
  google_api_key = os.getenv("Gemini_API_KEY"),
  disable_streaming = True
)

chat_histories = {}

class QueryRequest(BaseModel):
  question : str
  session_id : str = None

@app.post("/query")
async def query_qa(req : QueryRequest):
  retriever = vector_store.as_retriever(search_kwargs = {"k": 5})
  session_id = req.session_id or "default"

  if session_id not in chat_histories:
    chat_histories[session_id] = []

  qa = ConversationalRetrievalChain.from_llm(
    llm = llm,
    retriever = retriever,
    return_source_documents = True
  )


  try:
    result = qa({"question": req.question,
                 "chat_history": chat_histories})
    answer = result["answer"]

    chat_histories[session_id].append(req.question, answer)

    if len(chat_histories[session_id])> 40:
      chat_histories[session_id] = chat_histories[session_id][-20:]

    return answer
  except Exception as e:
    raise HTTPException(status_code = 500, detail = str(e))
  

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
  try:
    await websocket.accept()

    session_id = str(uuid.uuid4())
    chat_histories[session_id] = []

    print(f"Created new session: {session_id}")


    while True:
      try:
        data = await websocket.receive_text()
        message = json.loads(data)

        if "user_input" in message:
          print("Processing User Input")

          chat_history = message.get("chat_history", [])
          if chat_history:
              # Convert the chat history to the format expected by the chain
              formatted_history = [(msg["content"], "") for msg in chat_history if msg["role"] == "user"]
              chat_histories[session_id] = formatted_history


              retriever = vector_store.as_retriever(search_kwargs = {k:5})


              qa = ConversationalRetrievalChain.from_llm(
                llm = llm
                retriever = retriever,
              )

              try:
                result = qa({
                  "question" : message["user_input"],
                  "chat_history" : chat_histories[session_id]
                })


                answer = result(["answer"])


                chat_histories[session_id].append((message["user_input"], answer))


                if len(chat_histories[session_id]) > 10:
                    chat_histories[session_id] = chat_histories[session_id][-10:]

                response = {
                  "text" : answer,
                  "done" : True
                }

                await websocket.send_json(response)
                print("Succesfully Send the Response")

              except Exception as e:
                error_msg = f"Error Processing Request : {str(e)}"

                print(error_msg)

                await websocket.send_json({
                  "error":error_msg
                  "done" : True
      
                })


      except WebSocketDisconect:
        print("webSocket Disconnect")
        break

      except Exception as e:
        await websocket.send_json({
          "error": f"Internal Server Error: {str(e)}",
          "done" : True
        })

        break

  
            
              
