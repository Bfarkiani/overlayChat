from hypercorn.config import Config
from hypercorn.asyncio import serve
from quart import Quart, request, jsonify
import asyncio
import logging
import httpx
import json
import argparse
from datetime import datetime
import uuid
import os
from typing import Dict, Optional, Callable
import ssl
from urllib.parse import urlencode

class InstanceFormatter(logging.Formatter):
    """Custom formatter that includes instance name in logs"""
    def format(self, record):
        # Add instance_name to the record if it exists
        if instance_name:
            record.instance = instance_name
        else:
            record.instance = 'unknown'
        return super().format(record)

# Configure logging with custom formatter
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('proxy')

# Create custom formatter
formatter = InstanceFormatter(
    '%(asctime)s - [%(instance)s] - %(name)s - %(levelname)s - %(message)s'
)

# Apply formatter to all handlers
for handler in logger.handlers:
    handler.setFormatter(formatter)

# Add a new handler if none exists
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

app = Quart(__name__)

# Global variables
instance_name = None
proxy_port = None
client_port = None
peers: Dict = {}
http_client = None
proxy_id = str(uuid.uuid4())
controller_url = None


# Request transformation functions
def transform_openai_chat_request(data: dict, endpoint_config: dict) -> dict:
    """Transform chat message to OpenAI API format"""
    return {
        "messages": [
            {"role": "user", "content": data.get('message', '')}
        ],
        **endpoint_config.get('model_config', {})
    }


def transform_anthropic_chat_request(data: dict, endpoint_config: dict) -> dict:
    """Transform chat message to Anthropic API format"""
    config = endpoint_config.get('model_config', {})
    return {
        "model": config.get('model'),
        "messages": [
            {"role": "user", "content": data.get('message', '')}
        ],
        "max_tokens": config.get('max_tokens'),
        "temperature": config.get('temperature'),
        "top_p": config.get('top_p'),
        "stream": config.get('stream', False)
    }


def transform_gemini_chat_request(data: dict, endpoint_config: dict) -> dict:
    """Transform chat message to Google Gemini API format"""
    config = endpoint_config.get('model_config', {})
    return {
        "contents": [{
            "role": "user",
            "parts": [{"text": data.get('message', '')}]
        }],
        "generationConfig": {
            "temperature": config.get('temperature'),
            "topP": config.get('top_p'),
            "topK": config.get('top_k'),
            "maxOutputTokens": config.get('max_output_tokens')
        }
    }


# Response transformation functions
def transform_openai_chat_response(response_data: dict) -> dict:
    """Transform OpenAI/Mistral API response to chat format"""
    try:
        # Check for API error responses
        if 'error' in response_data:
            error_message = response_data['error'].get('message', 'Unknown API error')
            error_type = response_data['error'].get('type', 'unknown')
            error_code = response_data['error'].get('code', 'unknown')

            logger.error(f"API Error: {error_type} - {error_message} (Code: {error_code})")

            # Handle rate limits specially
            if error_type == 'rate_limit_error' or error_code == 'rate_limit_exceeded':
                return {
                    "status": "error",
                    "message": "The service is currently busy. Please try again in a moment.",
                    "error_type": "rate_limit",
                    "retry_after": response_data['error'].get('retry_after', 60)
                }

            return {
                "status": "error",
                "message": error_message,
                "error_type": error_type,
                "error_code": error_code
            }

        # Normal response processing
        message = response_data['choices'][0]['message']['content']
        return {
            "status": "success",
            "message": message,
            "from": "BOT",
            "timestamp": datetime.utcnow().isoformat(),
            "auto": True
        }
    except (KeyError, IndexError) as e:
        logger.error(f"Error transforming OpenAI response: {e}")
        logger.error(f"Response data: {response_data}")
        return {
            "status": "error",
            "message": "An error occurred while processing the response",
            "error": str(e),
            "raw_response": response_data  # This helps with debugging
        }


def transform_anthropic_chat_response(response_data: dict) -> dict:
    """Transform Anthropic API response to chat format"""
    try:
        message = response_data['content'][0]['text']
        return {
            "status": "success",
            "message": message,
            "from": "ANTHROPIC",
            "timestamp": datetime.utcnow().isoformat(),
            "auto": True
        }
    except (KeyError, IndexError) as e:
        logger.error(f"Error transforming Anthropic response: {e}")
        return {
            "status": "error",
            "message": "Failed to process API response",
            "error": str(e)
        }


def transform_gemini_chat_response(response_data: dict) -> dict:
    """Transform Google Gemini API response to chat format"""
    try:
        message = response_data['candidates'][0]['content']['parts'][0]['text']
        return {
            "status": "success",
            "message": message,
            "from": "GEMINI",
            "timestamp": datetime.utcnow().isoformat(),
            "auto": True
        }
    except (KeyError, IndexError) as e:
        logger.error(f"Error transforming Gemini response: {e}")
        return {
            "status": "error",
            "message": "Failed to process API response",
            "error": str(e)
        }


# Maps for transformation functions
TRANSFORM_FUNCTIONS = {
    'openai_chat': transform_openai_chat_request,
    'anthropic_chat': transform_anthropic_chat_request,
    'gemini_chat': transform_gemini_chat_request
}

RESPONSE_TRANSFORM_FUNCTIONS = {
    'openai_chat': transform_openai_chat_response,
    'anthropic_chat': transform_anthropic_chat_response,
    'gemini_chat': transform_gemini_chat_response
}


async def setup_client():
    """Initialize global HTTP/2 client"""
    global http_client
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    http_client = httpx.AsyncClient(
        http2=True,
        verify=True,  # Changed to True for API communication
        limits=limits,
        timeout=10.0
    )
    return http_client


def load_config(config_path: str):
    """Load proxy configuration from file"""
    global instance_name, proxy_port, client_port, controller_url

    logger.info(f"Loading config from: {config_path}")

    with open(config_path, 'r') as f:
        config = json.load(f)

    instance_name = config['instance_name']
    proxy_port = config['proxy_port']
    client_port = config['client_port']
    controller_url = config.get('controller_url', 'http://localhost:8000')

    logger.info(f"Loaded config for {instance_name}")
    logger.info(f"Proxy port: {proxy_port}")
    logger.info(f"Client port: {client_port}")
    logger.info(f"Controller URL: {controller_url}")


async def register_with_controller():
    """Register this proxy with the controller"""
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Registering {instance_name} with controller (proxy_id: {proxy_id})")
            response = await client.post(
                f"{controller_url}/api/register",
                json={
                    "proxy_id": proxy_id,
                    "instance_name": instance_name,
                    "host": "127.0.0.1",
                    "port": proxy_port
                }
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Registration response: {json.dumps(data, indent=2)}")

                if 'endpoints' in data:
                    global peers
                    peers = data['endpoints']
                    logger.info(f"Initial endpoints configuration: {json.dumps(peers, indent=2)}")
                else:
                    logger.error("No endpoints received in registration response")

                logger.info("Successfully registered with controller")
            else:
                logger.error(f"Failed to register with controller: {response.text}")

    except Exception as e:
        logger.error(f"Error registering with controller: {e}")
        raise


async def send_heartbeat():
    """Send periodic heartbeat to controller"""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{controller_url}/api/heartbeat",
                    json={"proxy_id": proxy_id}
                )
                if response.status_code != 200:
                    logger.warning(f"Heartbeat failed: {response.text}")
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
            await asyncio.sleep(30)


# Add at the top of the file with other globals:
#TODO: cached_peers seems unnecessary
cached_peers: Dict = {}


def get_peer_info(peer_id: str) -> tuple[Optional[str], Optional[dict]]:
    """Look up peer info case-insensitively. If peer not found and this proxy is running for that instance, return localhost info"""
    if not peer_id:
        logger.error("No peer_id provided")
        return None, None

    peer_id_lower = peer_id.lower()
    logger.info(f"Looking up peer: {peer_id} (lowercase: {peer_id_lower})")
    logger.info(f"Available peers: {list(peers.keys())}")

    # Check exact match first
    if peer_id in peers:
        logger.info(f"Found exact match for peer: {peer_id}")
        return peer_id, peers[peer_id]

    # Check case-insensitive match
    for pid, info in peers.items():
        if pid.lower() == peer_id_lower:
            logger.info(f"Found case-insensitive match: {pid}")
            return pid, info

    # If peer not found and it matches this proxy's instance, return localhost info
    if peer_id_lower == instance_name.lower():
        logger.info(f"Message is for this instance ({instance_name}), using localhost")
        return instance_name, {
            'host': '127.0.0.1',
            'port': client_port
        }

    logger.error(f"No peer found matching: {peer_id}")
    return None, None
async def update_endpoints():
    """Periodically fetch updated endpoints from controller"""
    global peers
    retries = 0
    max_retries = 3

    while True:
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Fetching endpoints for {instance_name} (proxy_id: {proxy_id})")
                response = await client.get(
                    f"{controller_url}/api/getendpoints",
                    params={"proxy_id": proxy_id}
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Received data from controller: {json.dumps(data, indent=2)}")

                    if not data.get('endpoints'):
                        logger.error("Received empty endpoints from controller")
                        await asyncio.sleep(60)
                        continue

                    # Store current peers for comparison
                    old_peers = set(peers.keys()) if peers else set()
                    new_endpoints = data['endpoints']

                    logger.info(f"Current peers before update: {old_peers}")
                    logger.info(f"New endpoints received: {list(new_endpoints.keys())}")

                    # Update peers dictionary (keeping entire configuration)
                    peers = new_endpoints.copy()

                    # Log changes
                    new_peer_set = set(peers.keys())
                    added = new_peer_set - old_peers
                    removed = old_peers - new_peer_set

                    #logger.info(f"Updated endpoints for {instance_name}. Current peers: {list(peers.keys())}")

                    logger.info(f"Peers configuration after update: {json.dumps(peers, indent=2)}")
                    if added:
                        logger.info(f"Added peers: {added}")
                    if removed:
                        logger.info(f"Removed peers: {removed}")

                    retries = 0
                else:
                    logger.error(f"Failed to get endpoints: {response.text}")
                    if retries < max_retries:
                        retries += 1
                        await asyncio.sleep(5)
                        continue

            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Error updating endpoints: {e}")
            if retries < max_retries:
                retries += 1
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(60)
            retries = 0
@app.before_serving
async def startup():
    """Initialize HTTP/2 client and start background tasks"""
    global http_client
    http_client = await setup_client()

    # Register with controller
    await register_with_controller()

    # Start background tasks
    app.heartbeat_task = asyncio.create_task(send_heartbeat())
    app.endpoints_task = asyncio.create_task(update_endpoints())


@app.after_serving
async def shutdown():
    """Clean up resources"""
    global http_client
    if http_client:
        await http_client.aclose()

    if hasattr(app, 'heartbeat_task'):
        app.heartbeat_task.cancel()
    if hasattr(app, 'endpoints_task'):
        app.endpoints_task.cancel()
    try:
        if hasattr(app, 'heartbeat_task'):
            await app.heartbeat_task
        if hasattr(app, 'endpoints_task'):
            await app.endpoints_task
    except asyncio.CancelledError:
        pass




@app.route('/peers', methods=['GET'])
async def get_peers():
    """Return list of known peers"""
    return jsonify({
        "instance": instance_name,
        "peers": peers
    })


async def forward_to_peer(message_data: dict, target_peer: str):
    """Forward a message to a peer's local service"""
    try:
        peer_id, peer_info = get_peer_info(target_peer)
        if not peer_id or not peer_info:
            logger.error(f"Cannot forward: unknown peer {target_peer}")
            return

        # Add /message to the peer URL
        peer_url = f"http://{peer_info['host']}:{peer_info['port']}/message"  # Changed from just /
        headers = {
            'Host': target_peer,
            'Content-Type': 'application/json'
        }

        async with httpx.AsyncClient() as client:
            await client.post(peer_url, json=message_data, headers=headers)
            logger.info(f"Forwarded message to {target_peer}")

    except Exception as e:
        logger.error(f"Failed to forward to peer: {e}")


@app.route('/', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST'])
async def handle_request(path):
    """Handle incoming requests and route them to appropriate peers or APIs"""
    try:
        target_peer = request.headers.get('Host', '').split(':')[0]
        data = await request.get_json() if request.is_json else None

        logger.info(f"Handling request for {target_peer}")

        actual_peer_id, peer_info = get_peer_info(target_peer)
        if not actual_peer_id or not peer_info:
            return jsonify({"status": "error", "message": f"Unknown peer: {target_peer}"}), 404

        # Case 1: Message is for this instance's peer.py
        if target_peer.lower() == instance_name.lower():
            peer_url = f"http://127.0.0.1:{client_port}/message"
            headers = {'Content-Type': 'application/json'}
            async with httpx.AsyncClient() as client:
                await client.post(peer_url, json=data, headers=headers)
            return jsonify({"status": "success", "message": "Message delivered to local peer"})

        # Case 2: Message is for a bot API
        if peer_info.get('is_api'):
            transform_type = peer_info.get('transform_request')
            if transform_type and transform_type in TRANSFORM_FUNCTIONS:
                transformed_data = TRANSFORM_FUNCTIONS[transform_type](data, peer_info)
            else:
                transformed_data = data

            url = f"https://{peer_info['host']}{peer_info.get('path', '/')}"
            api_headers = peer_info.get('headers', {})

            async def send_api_request():
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(url, json=transformed_data, headers=api_headers)
                        if response.status_code == 200:
                            response_data = response.json()
                            if peer_info.get('transform_response'):
                                response_data = RESPONSE_TRANSFORM_FUNCTIONS[peer_info['transform_response']](
                                    response_data)
                            # Send bot response to our local peer.py
                            peer_url = f"http://127.0.0.1:{client_port}/message"
                            headers = {'Content-Type': 'application/json'}
                            await client.post(peer_url, json=response_data, headers=headers)
                except Exception as e:
                    logger.error(f"API request failed: {e}")

            asyncio.create_task(send_api_request())
            return jsonify({"status": "success", "message": "Request sent to API"})

        # Case 3: Message is for another peer's proxy
        proxy_url = f"http://{peer_info['host']}:{peer_info['port']}/"
        logger.info(f"Forwarding to peer proxy at: {proxy_url}")

        headers = {
            'Host': target_peer,
            'Content-Type': 'application/json'
        }

        async def send_to_peer_proxy():
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(proxy_url, json=data, headers=headers)
            except Exception as e:
                logger.error(f"Failed to send to peer proxy: {e}")

        asyncio.create_task(send_to_peer_proxy())
        return jsonify({"status": "success", "message": f"Message sent to peer proxy at {proxy_url}"})

    except Exception as e:
        logger.error(f"Error handling request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_proxy(config_path: str):
    """Run the proxy server with the specified configuration"""
    load_config(config_path)

    config = Config()
    config.bind = [f"0.0.0.0:{proxy_port}"]
    config.h2_enabled = True

    logger.info(f"Starting proxy for {instance_name} on port {proxy_port}")
    asyncio.run(serve(app, config))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, help='Path to proxy configuration file')
    args = parser.parse_args()

    run_proxy(args.config)