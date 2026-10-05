# 🎙️ SpeakBuddy - AI Communication Practice Partner

SpeakBuddy is a full-stack AI-powered communication practice companion. Practice interviews, presentations, and everyday conversations with instant speech feedback, performance metrics, and voice feedback.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohit060321/SpeakBuddy)

---

## 🚀 Features

- **Practice Scenarios**: Tailored interview, presentation, and conversation practice prompts.
- **Detailed Scoring**: 1–10 scores for Clarity, Grammar, Vocabulary, Confidence, and Overall.
- **Actionable Feedback**: Two concrete improvement suggestions plus a relevant follow-up question.
- **Interactive Voice**: Listen to feedback with natural speech (supports ElevenLabs Cloud Voice with automatic Browser Text-to-Speech fallback).
- **Persistent Session History**: Cloud storage with MongoDB Atlas or automatic local storage with SQLite.
- **Multiple LLM Backends**: Supports local Ollama (Gemma), cloud Groq API (Gemma 2), or built-in intelligent evaluation.

---

## ☁️ Deploy to Render

### Option 1: One-Click Blueprint Deploy (Recommended)

1. Click the button below to start deploying on Render:
   
   [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohit060321/SpeakBuddy)

2. Render will automatically read `render.yaml`.
3. Provide your environment variables in the setup form:
   - `MONGODB_URI`: Your MongoDB Atlas connection string.
   - `ELEVENLABS_API_KEY`: Your ElevenLabs API key (optional; if omitted, browser speech synthesis is used).
   - `ELEVENLABS_VOICE_ID`: Voice ID (defaults to `21m00Tcm4TlvDq8ikWAM`).
   - `GROQ_API_KEY`: Free Groq API key for cloud Gemma inference (optional).
4. Click **Apply**. Render will build and deploy your service.
5. Your live app will be accessible at:
   `https://speakbuddy.onrender.com` (or your custom service URL).

---

### Option 2: Manual Web Service Setup on Render

1. Go to [Render Dashboard](https://dashboard.render.com/) and click **New +** > **Web Service**.
2. Connect your GitHub repository: `https://github.com/rohit060321/SpeakBuddy`.
3. Configure the settings:
   - **Name**: `speakbuddy`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`
4. Expand **Advanced** > **Environment Variables** and add:
   | Key | Value / Description | Required? |
   |-----|---------------------|-----------|
   | `PYTHON_VERSION` | `3.11.0` | Recommended |
   | `MONGODB_URI` | `mongodb+srv://<user>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority` | Yes (for cloud history) |
   | `ELEVENLABS_API_KEY` | `your_elevenlabs_api_key` | Optional (cloud voice) |
   | `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | Optional |
   | `GROQ_API_KEY` | `gsk_...` | Optional (cloud Gemma inference) |
   | `OLLAMA_BASE_URL` | Remote Ollama URL (e.g. ngrok tunnel) | Optional |
5. Click **Create Web Service**.

---

## 💻 Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/rohit060321/SpeakBuddy.git
   cd SpeakBuddy
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```

5. Run the server:
   ```bash
   uvicorn main:app --reload
   ```

6. Open `http://localhost:8000` in your browser.
