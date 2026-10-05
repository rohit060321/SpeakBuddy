import os
import re
import json
import sqlite3
import requests
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pymongo import MongoClient
from elevenlabs.client import ElevenLabs

load_dotenv()

app = FastAPI(title="SpeakBuddy")

# =========================
# ENVIRONMENT VARIABLES
# =========================
MONGODB_URI = os.getenv("MONGODB_URI")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# =========================
# MONGODB (Optional Cloud Storage)
# =========================
mongo_client = None
sessions_collection = None

if MONGODB_URI and MONGODB_URI.strip():
    try:
        mongo_client = MongoClient(
            MONGODB_URI.strip(),
            serverSelectionTimeoutMS=5000
        )
        mongo_client.admin.command("ping")
        try:
            db = mongo_client.get_default_database()
        except Exception:
            db = None
        if db is None:
            db = mongo_client["speakbuddy"]
        sessions_collection = db["sessions"]
        print("MongoDB Atlas connected successfully.")
    except Exception as e:
        print("MongoDB connection failed (using local SQLite storage):", e)
        mongo_client = None
        sessions_collection = None
else:
    print("MONGODB_URI not set. Using local SQLite storage.")

# =========================
# SQLITE (Persistent Local Storage)
# =========================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.db")

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scenario TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    clarity INTEGER NOT NULL,
                    grammar INTEGER NOT NULL,
                    vocabulary INTEGER NOT NULL,
                    confidence INTEGER NOT NULL,
                    overall INTEGER NOT NULL,
                    suggestions TEXT NOT NULL,
                    follow_up TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
    except Exception as e:
        print("SQLite init error:", e)

init_db()

def save_session(scenario: str, question: str, answer: str, feedback: dict, overall: int, created_at_iso: str):
    # 1. Always save to local SQLite
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    scenario, question, answer,
                    clarity, grammar, vocabulary, confidence,
                    overall, suggestions, follow_up, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scenario,
                    question,
                    answer,
                    int(feedback.get("clarity", 7)),
                    int(feedback.get("grammar", 7)),
                    int(feedback.get("vocabulary", 7)),
                    int(feedback.get("confidence", 7)),
                    int(overall),
                    json.dumps(feedback.get("suggestions", [])),
                    str(feedback.get("follow_up", "")),
                    created_at_iso
                )
            )
            conn.commit()
    except Exception as e:
        print("SQLite save failed:", e)

    # 2. Also save to MongoDB if connected
    if sessions_collection is not None:
        try:
            mongo_doc = {
                "scenario": scenario,
                "question": question,
                "answer": answer,
                "feedback": feedback,
                "overall": overall,
                "created_at": created_at_iso
            }
            sessions_collection.insert_one(mongo_doc)
        except Exception as e:
            print("MongoDB save failed:", e)

def get_history(limit: int = 10):
    # If MongoDB is connected and has sessions, try fetching from it
    if sessions_collection is not None:
        try:
            docs = list(
                sessions_collection.find({}, {"_id": 0})
                .sort("created_at", -1)
                .limit(limit)
            )
            if docs:
                results = []
                for d in docs:
                    created = d.get("created_at")
                    if isinstance(created, datetime):
                        created = created.isoformat()
                    results.append({
                        "scenario": d.get("scenario", "Practice"),
                        "question": d.get("question", ""),
                        "answer": d.get("answer", ""),
                        "feedback": d.get("feedback", {}),
                        "overall": d.get("overall", 7),
                        "created_at": str(created or "")
                    })
                return results
        except Exception as e:
            print("MongoDB read error, falling back to SQLite:", e)

    # Fallback to local SQLite storage
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT scenario, question, answer,
                       clarity, grammar, vocabulary, confidence,
                       overall, suggestions, follow_up, created_at
                FROM sessions
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                try:
                    sugg = json.loads(row["suggestions"])
                except Exception:
                    sugg = [row["suggestions"]] if row["suggestions"] else []
                results.append({
                    "scenario": row["scenario"],
                    "question": row["question"],
                    "answer": row["answer"],
                    "overall": row["overall"],
                    "created_at": row["created_at"],
                    "feedback": {
                        "clarity": row["clarity"],
                        "grammar": row["grammar"],
                        "vocabulary": row["vocabulary"],
                        "confidence": row["confidence"],
                        "suggestions": sugg,
                        "follow_up": row["follow_up"]
                    }
                })
            return results
    except Exception as e:
        print("SQLite read error:", e)
        return []

# =========================
# ELEVENLABS
# =========================
eleven_client = None

if ELEVENLABS_API_KEY and ELEVENLABS_API_KEY.strip():
    try:
        eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY.strip())
        print("ElevenLabs client initialized.")
    except Exception as e:
        print("ElevenLabs init failed:", e)
        eleven_client = None

# =========================
# REQUEST MODEL
# =========================
class PracticeRequest(BaseModel):
    scenario: str
    question: str
    answer: str

# =========================
# LLM INTEGRATION
# =========================
def normalize_feedback(raw: dict) -> dict:
    data = {str(k).lower(): v for k, v in raw.items()}
    if "scores" in data and isinstance(data["scores"], dict):
        for k, v in data["scores"].items():
            data[str(k).lower()] = v

    def clean_score(key, default=7):
        val = data.get(key)
        try:
            n = int(round(float(val)))
            return max(1, min(10, n))
        except (ValueError, TypeError):
            return default

    clarity = clean_score("clarity", 7)
    grammar = clean_score("grammar", 8)
    vocabulary = clean_score("vocabulary", 7)
    confidence = clean_score("confidence", 7)

    raw_sugg = data.get("suggestions", [])
    if isinstance(raw_sugg, str):
        suggestions = [s.strip(" -*•") for s in raw_sugg.split("\n") if s.strip()]
    elif isinstance(raw_sugg, list):
        suggestions = [str(s).strip() for s in raw_sugg if str(s).strip()]
    else:
        suggestions = []

    if not suggestions:
        suggestions = [
            "Structure your answer with clear points and concrete examples.",
            "Maintain a steady, confident speaking pace and natural flow."
        ]

    follow_up = str(data.get("follow_up") or data.get("followup") or data.get("next_question") or "").strip()
    if not follow_up:
        follow_up = "Can you share another detail about your experience?"

    return {
        "clarity": clarity,
        "grammar": grammar,
        "vocabulary": vocabulary,
        "confidence": confidence,
        "suggestions": suggestions[:2],
        "follow_up": follow_up
    }

def heuristic_evaluation(scenario: str, question: str, answer: str) -> dict:
    words = [w for w in re.findall(r"\b\w+\b", answer.lower()) if w]
    word_count = len(words)
    unique_words = len(set(words))

    diversity_ratio = unique_words / max(word_count, 1)
    vocab_score = min(10, max(5, int(diversity_ratio * 10) + (2 if word_count > 25 else 0)))

    if word_count < 6:
        clarity_score = 5
        confidence_score = 5
    elif word_count < 18:
        clarity_score = 7
        confidence_score = 7
    elif word_count < 90:
        clarity_score = 8
        confidence_score = 8
    else:
        clarity_score = 7
        confidence_score = 8

    has_cap = answer[0].isupper() if answer else False
    has_punct = answer.strip().endswith((".", "!", "?")) if answer else False
    grammar_score = 8 if (has_cap and has_punct) else 7
    if word_count > 25 and (has_cap and has_punct):
        grammar_score = 9

    suggestions = []
    if word_count < 15:
        suggestions.append("Give a concrete example to make your answer more convincing and detailed.")
    else:
        suggestions.append("Use the STAR method (Situation, Task, Action, Result) to organize your response.")

    if not has_punct or not has_cap:
        suggestions.append("Frame your points in complete, punchy sentences for stronger impact.")
    else:
        suggestions.append("Highlight the outcome or key lesson learned from that experience.")

    q_lower = question.lower()
    a_lower = answer.lower()
    if "project" in q_lower or "project" in a_lower:
        follow_up = "What was the biggest technical hurdle you encountered in that project, and how did you resolve it?"
    elif "yourself" in q_lower or "background" in q_lower:
        follow_up = "What specific skills or technologies are you currently most interested in deepening?"
    elif "challenge" in q_lower:
        follow_up = "Looking back, is there anything you would do differently if faced with that situation again?"
    else:
        follow_up = "Can you share another example where you applied this approach successfully?"

    return {
        "clarity": clarity_score,
        "grammar": grammar_score,
        "vocabulary": vocab_score,
        "confidence": confidence_score,
        "suggestions": suggestions[:2],
        "follow_up": follow_up
    }

def ask_gemma(scenario: str, question: str, answer: str) -> dict:
    prompt = f"""You are SpeakBuddy.

You are a friendly and encouraging communication practice partner.

Practice mode:
{scenario}

Question:
{question}

User's answer:
{answer}

Analyze the answer.

Give scores from 1 to 10 for:
clarity
grammar
vocabulary
confidence

Give exactly two useful improvement suggestions.
Then ask one follow-up question.
Keep feedback concise.

Return ONLY valid JSON.

Format:
{{
    "clarity": 7,
    "grammar": 8,
    "vocabulary": 6,
    "confidence": 7,
    "suggestions": [
        "Give one specific example.",
        "Make the answer more concise."
    ],
    "follow_up": "Can you tell me about a project you are proud of?"
}}
"""

    # 1. Try Groq Cloud if configured
    if GROQ_API_KEY and GROQ_API_KEY.strip():
        try:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gemma2-9b-it",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7
                },
                timeout=25
            )
            if res.ok:
                content = res.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return normalize_feedback(parsed)
        except Exception as e:
            print("Groq cloud inference error:", e)

    # 2. Try Ollama (Local or remote URL via OLLAMA_BASE_URL)
    try:
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        response = requests.post(
            url,
            json={
                "model": "gemma3:1b",
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=15
        )
        if response.ok:
            raw_content = response.json().get("response", "{}").strip()
            if raw_content.startswith("```"):
                raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
                raw_content = re.sub(r"\s*```$", "", raw_content)
            try:
                parsed = json.loads(raw_content)
            except Exception:
                match = re.search(r"\{[\s\S]*\}", raw_content)
                parsed = json.loads(match.group(0)) if match else {}
            return normalize_feedback(parsed)
    except Exception as e:
        print(f"Ollama ({OLLAMA_BASE_URL}) unavailable, using smart feedback engine: {e}")

    # 3. Fallback Smart Evaluation (guarantees SpeakBuddy always works on Render!)
    return heuristic_evaluation(scenario, question, answer)

# =========================
# PRACTICE API
# =========================
@app.post("/api/practice")
def practice(data: PracticeRequest):
    try:
        feedback = ask_gemma(
            data.scenario,
            data.question,
            data.answer
        )

        clarity = feedback["clarity"]
        grammar = feedback["grammar"]
        vocabulary = feedback["vocabulary"]
        confidence = feedback["confidence"]
        overall = round((clarity + grammar + vocabulary + confidence) / 4)

        created_at_iso = datetime.now(timezone.utc).isoformat()

        # Save session to persistent storage (SQLite & MongoDB)
        save_session(
            scenario=data.scenario,
            question=data.question,
            answer=data.answer,
            feedback=feedback,
            overall=overall,
            created_at_iso=created_at_iso
        )

        return {
            "clarity": clarity,
            "grammar": grammar,
            "vocabulary": vocabulary,
            "confidence": confidence,
            "overall": overall,
            "suggestions": feedback["suggestions"],
            "follow_up": feedback["follow_up"],
            "saved": True
        }

    except Exception as e:
        print("Practice error:", e)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

# =========================
# VOICE API
# =========================
class VoiceRequest(BaseModel):
    text: str

@app.post("/api/voice")
def generate_voice(data: VoiceRequest):
    if not eleven_client:
        return JSONResponse(
            status_code=400,
            content={
                "error": "ElevenLabs API key not configured.",
                "fallback": True
            }
        )

    voice_id = ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"

    try:
        audio = eleven_client.text_to_speech.convert(
            voice_id=voice_id,
            output_format="mp3_44100_128",
            text=data.text,
            model_id="eleven_multilingual_v2"
        )

        audio_bytes = b"".join(audio)

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg"
        )

    except Exception as e:
        print("ElevenLabs voice generation failed:", e)
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "fallback": True
            }
        )

# =========================
# SESSION HISTORY
# =========================
@app.get("/api/history")
def history():
    try:
        return get_history(limit=10)
    except Exception as e:
        print("History retrieval error:", e)
        return []

# =========================
# STATUS API
# =========================
@app.get("/api/status")
def status():
    return {
        "mongo_connected": sessions_collection is not None,
        "elevenlabs_configured": eleven_client is not None,
        "groq_configured": bool(GROQ_API_KEY and GROQ_API_KEY.strip()),
        "storage": "mongodb" if sessions_collection is not None else "sqlite_local"
    }

# =========================
# FRONTEND
# =========================
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

@app.get("/")
def home():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)