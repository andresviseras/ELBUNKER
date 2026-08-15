class BunkerClient {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectDelay = 10000; // 10 segundos máximo
        this.playerId = this.getOrCreatePlayerId();
        
        this.connect();
    }

    getOrCreatePlayerId() {
        let id = localStorage.getItem('bunker_player_id');
        if (!id) {
            id = crypto.randomUUID();
            localStorage.setItem('bunker_player_id', id);
        }
        return id;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.playerId}`;
        
        console.log(`Intentando conectar a ${wsUrl}...`);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log("🟢 Conectado al Búnker.");
            this.reconnectAttempts = 0; // Resetear intentos al conectar
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleServerMessage(message);
        };

        this.ws.onclose = (event) => {
            console.warn("🔴 Conexión perdida.");
            this.scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error("⚠️ Error en WebSocket:", error);
            // onclose se ejecutará inmediatamente después de un error fatal
        };
    }

    scheduleReconnect() {
        // Algoritmo de Exponential Backoff: 1s, 2s, 4s, 8s... hasta maxReconnectDelay
        const delay = Math.min(
            this.maxReconnectDelay, 
            (Math.pow(2, this.reconnectAttempts) - 1) * 1000
        );
        
        console.log(`⏳ Reconectando en ${delay / 1000} segundos...`);
        
        setTimeout(() => {
            this.reconnectAttempts++;
            this.connect();
        }, delay);
    }

    handleServerMessage(message) {
        if (message.type === "sync_state") {
            console.log("Estado del juego actualizado:", message.data);
            this.renderGame(message.data);
        }
    }

    renderGame(gameState) {
        // Aquí conectas con tu HTML para dibujar los jugadores, el turno, etc.
        // Como recibe el estado completo, siempre redibuja la pantalla correctamente
        // sin importar cuánto tiempo estuvo desconectado el móvil.
    }

    sendAction(actionType, payload) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: actionType, data: payload }));
        } else {
            console.error("No se puede enviar la acción, no hay conexión.");
        }
    }
}

// Inicializar el cliente cuando cargue el documento
document.addEventListener("DOMContentLoaded", () => {
    window.bunkerClient = new BunkerClient();
});