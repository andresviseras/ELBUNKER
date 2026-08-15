# ☢️ The Bunker - Social Deduction Game

An async, real-time social deduction web game powered by websockets and AI (Google Gemini). 

Players are assigned unique (and potentially fatal) roles by an AI Game Master in a post-apocalyptic scenario. They must debate and vote to decide who enters the bunker and survives. The AI then evaluates the players' choices against its own logical survival model and generates a dynamic narrative outcome.

## 🏗️ Technical Architecture

This project is built with a focus on separation of concerns, real-time concurrency, and stateless design.

*   **Backend:** Python 3.11, FastAPI, Uvicorn (ASGI).
*   **Real-time Communication:** Native WebSockets with robust connection handling and exponential backoff for mobile network dropouts.
*   **AI Integration:** Asynchronous calls to Google Gemini (`google-genai` SDK) isolated in a dedicated service layer to prevent blocking the WebSocket event loop.
*   **Frontend:** Vanilla JavaScript and Tailwind CSS, following a mobile-first responsive design.

## 🚀 Features

*   **Resilient Connectivity:** The client implements an exponential backoff algorithm for automatic reconnections.
*   **State Recovery:** The server holds the game state in memory and automatically resyncs clients if they drop out and reconnect.
*   **Dynamic Role Generation:** The AI acts as the Game Master, generating mathematically balanced roles with specific skills, fatal flaws, and circular blackmail networks.
*   **Bilingual Support:** Fully playable in both English and Spanish.

## 🛠️ Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/yourusername/elbunker.git](https://github.com/yourusername/elbunker.git)
   cd elbunker