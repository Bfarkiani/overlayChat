from quart import Quart, render_template, jsonify, request, make_response
import httpx
from tinydb import TinyDB, Query
from datetime import datetime
import logging
import os
import signal
import atexit
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
import json
import random
from quart import Response
from asyncio import create_task

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('chat_peer')

# Initialize environment variables
PEER_PORT = int(os.environ.get('CLIENT_PORT', 5000))
PROXY_PORT = int(os.environ.get('PROXY_PORT', 10000))
INSTANCE_NAME = os.environ.get('INSTANCE_NAME', 'main')
AUTO_MODE = os.environ.get('AUTO_MODE', 'false').lower() == 'true'

# Initialize TinyDB with instance-specific database
db = TinyDB(f'chat_history_{INSTANCE_NAME}.json')
messages_table = db.table('messages')

app = Quart(__name__)
http_client = None

# Auto-response messages
AUTO_RESPONSES = {
    "alice": [
        "Hi! This is Alice's automated response.",
        "Hope you're having a great day!",
        "Thanks for your message!",
        "I'll get back to you soon!"
    ],
    "bob": [
        "Hey, Bob here! (auto-response)",
        "I'm currently away but I got your message",
        "Thanks for reaching out!",
        "I'll respond properly when I'm back"
    ]
}

def get_auto_response():
    """Generate an auto-response based on instance name"""
    responses = AUTO_RESPONSES.get(INSTANCE_NAME, [f"Auto response from {INSTANCE_NAME}"])
    return random.choice(responses)

def store_message(peer_id, sender, message, status="success", auto_reply=False):
    """Store a message in the local database"""
    messages_table.insert({
        "peer_id": peer_id,
        "sender": sender,
        "message": message,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "auto_reply": auto_reply
    })

async def setup_client():
    """Initialize global HTTP/2 client to communicate with proxy"""
    global http_client
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    http_client = httpx.AsyncClient(
        http2=True,
        verify=False,
        limits=limits,
        timeout=10.0
    )
    return http_client

@app.before_serving
async def startup():
    """Initialize HTTP/2 client before serving"""
    global http_client
    http_client = await setup_client()
    logger.info(f"Starting peer {INSTANCE_NAME} on port {PEER_PORT}")
    logger.info(f"Connected to proxy on port {PROXY_PORT}")
    logger.info(f"Auto mode: {AUTO_MODE}")

@app.after_serving
async def shutdown():
    """Close HTTP/2 client after serving"""
    global http_client
    if http_client:
        await http_client.aclose()

@app.before_request
async def handle_cors():
    if request.method == 'OPTIONS':
        response = await make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', '*')
        response.headers.add('Access-Control-Allow-Methods', '*')
        return response

@app.after_request
async def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

@app.route("/")
async def index():
    """Render the chat interface"""
    return await render_template("index.html", peer_name=INSTANCE_NAME)

@app.route("/peer_name")
async def get_peer_name():
    """Return the name of this peer"""
    return jsonify({
        "name": INSTANCE_NAME
    })

@app.route("/peers")
async def get_peers():
    """Get list of available peers from proxy"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:{PROXY_PORT}/peers")
            peers_data = response.json()
            #TODO: name is also a field that might not match with peerid
            #name is shown for chat  peerid is for backend things. everything is based on peer id
            peers_list = [
                {"name": peer_id.capitalize(), "id": peer_id}
                for peer_id in peers_data["peers"].keys()
            ]
            return jsonify(peers_list)
    except Exception as e:
        logger.error(f"Failed to get peers list: {e}")
        return jsonify([])

@app.route("/get_chat_history/<peer_id>")
async def get_chat_history(peer_id):
    """Get chat history with specific peer"""
    Message = Query()
    messages = messages_table.search(Message.peer_id == peer_id)
    messages.sort(key=lambda x: x.get('timestamp', '0'))
    return jsonify(messages)


@app.route("/send_message", methods=["POST"])
async def send_message():
    """Handle message sending request from UI"""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({"status": "failed", "error": "No data provided"}), 400

        peer_id = data.get("peer_id")
        message = data.get("message")

        if not all([peer_id, message]):
            return jsonify({"status": "failed", "error": "Missing required fields"}), 400

        # 1. Store outgoing message
        store_message(peer_id, INSTANCE_NAME, message)

        # 2. Send message to proxy
        proxy_url = f"http://localhost:{PROXY_PORT}/"
        headers = {
            'Host': peer_id,
            'Content-Type': 'application/json'
        }

        # Create task for sending - don't wait for response
        create_task(
            httpx.AsyncClient().post(
                proxy_url,
                headers=headers,
                json={
                    "message": message,
                    "from": INSTANCE_NAME,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        )

        # 3. Return immediately
        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/message", methods=["POST"])
async def receive_message():
    """Handle incoming messages from proxy"""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({"status": "failed", "error": "No data provided"}), 400

        message = data.get("message")
        from_peer = data.get("from")

        if not all([message, from_peer]):
            return jsonify({"status": "failed", "error": "Missing required fields"}), 400

        # 1. Store received message
        store_message(from_peer, from_peer, message)

        # 2. If in auto mode, handle auto-response
        if AUTO_MODE:
            auto_response = get_auto_response()
            # Store our auto-response
            store_message(from_peer, INSTANCE_NAME, auto_response, auto_reply=True)

            # Create task to send auto-response - don't wait
            proxy_url = f"http://localhost:{PROXY_PORT}/"
            headers = {
                'Host': from_peer,
                'Content-Type': 'application/json'
            }

            create_task(
                httpx.AsyncClient().post(
                    proxy_url,
                    headers=headers,
                    json={
                        "message": auto_response,
                        "from": INSTANCE_NAME,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            )

        # 3. Return success
        return jsonify({
            "status": "success",
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error receiving message: {str(e)}")
        return jsonify({"status": "failed", "error": str(e)}), 500

@app.route('/message_updates')
async def message_updates():
    """SSE endpoint for real-time message updates"""
    async def event_stream():
        message_count = len(messages_table)
        try:
            while True:
                current_count = len(messages_table)
                if current_count > message_count:
                    message_count = current_count
                    messages = messages_table.all()
                    if messages:
                        latest = messages[-1]
                        data = json.dumps({
                            'peer_id': latest['peer_id'],
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        yield f"data: {data}\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("SSE connection closed by client")
        except Exception as e:
            logger.error(f"Error in SSE stream: {str(e)}")

    response = await make_response(
        event_stream(),
        {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
    )
    return response

@app.route("/clear_chat/<peer_id>", methods=["POST"])
async def clear_chat(peer_id):
    """Clear chat history with specific peer"""
    try:
        Message = Query()
        messages_table.remove(Message.peer_id == peer_id)
        return jsonify({
            "status": "success",
            "message": f"Chat history with {peer_id} cleared."
        })
    except Exception as e:
        return jsonify({
            "status": "failed",
            "error": str(e)
        }), 500

@app.route("/clear_all_chats", methods=["POST"])
async def clear_all_chats():
    """Clear all chat history"""
    try:
        messages_table.truncate()
        return jsonify({
            "status": "success",
            "message": "All chat history cleared."
        })
    except Exception as e:
        return jsonify({
            "status": "failed",
            "error": str(e)
        }), 500

def run_peer():
    """Run the peer application"""
    config = Config()
    config.bind = [f"0.0.0.0:{PEER_PORT}"]
    config.h2_enabled = True

    logger.info(f"Starting peer {INSTANCE_NAME} on 0.0.0.0:{PEER_PORT}")
    try:
        asyncio.run(serve(app, config))
    except KeyboardInterrupt:
        logger.info("Shutting down peer...")

if __name__ == "__main__":
    run_peer()