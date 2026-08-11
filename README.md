# 🎓 EduStream AI — Intelligent Learning Companion

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Groq](https://img.shields.io/badge/Groq_LLM-llama--3.3--70b-f50057?style=for-the-badge)
![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![AWS](https://img.shields.io/badge/AWS_App_Runner-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white)
[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-EduStream_AI-success?style=for-the-badge&logo=rocket)](https://tsktirkd27.ap-south-1.awsapprunner.com/app)

> 🔗 **Live Application:** [https://tsktirkd27.ap-south-1.awsapprunner.com/app](https://tsktirkd27.ap-south-1.awsapprunner.com/app)
>
> **EduStream AI** is a production-grade, AI-powered educational streaming application that transforms raw academic documents (PDFs, DOCX, TXT) and text into real-time study notes, interactive quizzes, flashcards, and simplified concepts in multiple languages (**English, Kannada, Hindi**).

---

## ✨ Key Features

- ⚡ **Real-Time Token Streaming (SSE):** Utilizes Server-Sent Events (SSE) powered by FastAPI and Groq API (`llama-3.3-70b-versatile`) for low-latency streaming.
- 🔑 **Multi-Key Failover Pool:** Round-robin API key rotation pool (`GroqKeyPool`) with automatic rate-limit cooldown handling to prevent API interruptions.
- 📄 **Multi-Format Document Extraction:** Native text extraction from **PDF** (PyMuPDF), **DOCX** (python-docx), and **TXT** files with character encoding fallbacks.
- 🌐 **Multilingual Learning:** Generate content seamlessly in **English**, **Kannada**, and **Hindi**.
- 🎯 **4 Specialized AI Learning Modes:**
  - 📝 **Structured Notes:** Organizes text into Markdown revision notes with bolded keywords and key takeaways.
  - 🧩 **Interactive Quizzes:** Creates JSON-formatted multiple-choice quizzes with options, correct answers, and varying difficulty.
  - 🃏 **Smart Flashcards:** Generates concept-based front/back flashcard pairs for spaced repetition.
  - 💡 **Concept Simplifier:** Translates complex jargon into beginner-friendly explanations with real-world analogies.
- 🎨 **Modern Dark-Themed UI:** Responsive Single Page Application (SPA) designed with Vanilla CSS, glassmorphism, dynamic theme highlights, and micro-animations.
- 🐳 **Production Ready:** Docker containerization with non-root security standards, container health checks, and AWS App Runner deployment scripts.

---

## 🛠️ Tech Stack

### **Backend**
- **Framework:** FastAPI (`uvicorn`)
- **LLM Engine:** Groq API (`llama-3.3-70b-versatile`) via `AsyncOpenAI` SDK
- **Document Extractors:** `PyMuPDF` (fitz), `python-docx`
- **Data Validation:** `Pydantic` v2

### **Frontend**
- **Architecture:** Vanilla HTML5 / JavaScript (ES6+)
- **Styling:** Custom CSS3 Design System with HSL dynamic colors & glassmorphism
- **Markdown Processing:** `Marked.js`

### **DevOps & Infrastructure**
- **Containerization:** Docker (`python:3.11-slim`, non-root user `appuser`)
- **Cloud Deployment:** AWS App Runner & Amazon ECR (PowerShell automation scripts)

---

## 📁 Repository Structure

```
EduStream_AI/
├── backend/
│   ├── main.py              # FastAPI application, Groq Key Pool, SSE endpoints
│   ├── file_handler.py      # PDF, DOCX, and TXT text extraction logic
│   ├── requirements.txt     # Python dependencies
│   └── __init__.py
├── frontend/
│   └── index.html           # Modern single-page application frontend
├── Dockerfile               # Security-hardened production Docker container
├── deploy-aws.ps1           # Deployment automation script for AWS App Runner
├── redeploy.ps1             # One-click redeployment script for AWS App Runner
├── test_integration.py      # API integration test suite
├── .env.example             # Example environment configuration template
└── README.md                # Project documentation
```

---

## 🚀 Quick Start (Local Setup)

### **1. Prerequisites**
- Python 3.11 or higher
- Git

### **2. Clone the Repository**
```bash
git clone https://github.com/chandana-achar/EduStream_AI.git
cd EduStream_AI
```

### **3. Set Up Virtual Environment & Dependencies**
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### **4. Configure Environment Variables**
Copy `.env.example` to `.env` and add your Groq API Key:
```bash
cp .env.example .env
```
Inside `.env`:
```env
# Single key mode
GROQ_API_KEY=gsk_your_groq_api_key_here

# OR Multi-key pool mode (comma-separated for rate-limit rotation)
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3
```

### **5. Run the Application**
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
Open your browser and navigate to:
- 🌐 **Web Interface:** [http://127.0.0.1:8000/app](http://127.0.0.1:8000/app)
- 📜 **Swagger API Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Running Integration Tests

Run the backend integration test suite to verify operational health, capabilities, file uploading, and rate limits:

```bash
python test_integration.py
```

---

## 🐳 Docker Deployment

### **Build Docker Image**
```bash
docker build -t edustream-ai .
```

### **Run Docker Container**
```bash
docker run -d -p 8000:8000 -e GROQ_API_KEY="your_api_key" --name edustream edustream-ai
```

Access the app at `http://localhost:8000/app`.

---

## ☁️ AWS App Runner Deployment

EduStream AI includes pre-configured PowerShell scripts for one-click AWS ECR + App Runner deployment:

1. Configure AWS CLI with appropriate credentials (`aws configure`).
2. Run initial deployment:
   ```powershell
   .\deploy-aws.ps1
   ```
3. For subsequent updates:
   ```powershell
   .\redeploy.ps1
   ```

---

## 📡 API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | `GET` | Service operational health check & API key pool status |
| `/api/capabilities` | `GET` | Supported processing modes, languages, and char limits |
| `/api/upload` | `POST` | Upload PDF/DOCX/TXT file and extract text |
| `/api/stream` | `POST` | Stream AI response via Server-Sent Events (SSE) |
| `/app` | `GET` | Serves the EduStream AI Web UI |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p center="align">Crafted with ❤️ for intuitive, AI-accelerated learning.</p>
