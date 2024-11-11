from quart import Quart, jsonify, request, render_template, redirect, url_for
import asyncio
import logging
from datetime import datetime, timedelta
from hypercorn.config import Config
from hypercorn.asyncio import serve
import json
from typing import Dict
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('chat_controller')

app = Quart(__name__)
app.secret_key = os.urandom(24)

# Store registered proxies and their information
registered_proxies: Dict = {}

# Configuration for endpoints
# Define default BOT endpoint separately
DEFAULT_BOT_ENDPOINT = {
    'BOT': {
        'host': 'api.openai.com',
        'port': 443,
        'is_api': True,
        'path': '/v1/chat/completions',
        'headers': {
            'Authorization': 'Bearer sk-your-default-api-key',
            'Content-Type': 'application/json'
        },
        'transform_request': 'openai_chat',
        'transform_response': 'openai_chat',
        'timeout': 30.0,
        'model_config': {
            'model': 'gpt-3.5-turbo',
            'temperature': 0.7,
            'max_tokens': 150,
            'top_p': 1,
            'frequency_penalty': 0,
            'presence_penalty': 0,
            'stream': False
        }
    }
}
# Default endpoint configurations for each instance
DEFAULT_ENDPOINTS = {
    'behrooz': {
        'endpoints': {
            'alice': {'host': '127.0.0.1', 'port': 10001},
            'bob': {'host': '127.0.0.1', 'port': 10002},
            'BOT': {
                'host': 'api.openai.com',
                'port': 443,
                'is_api': True,
                'path': '/v1/chat/completions',
                'headers': {
                    'Authorization': 'Bearer your-openAI-api-key-here',
                    'Content-Type': 'application/json'
                },
                'transform_request': 'openai_chat',
                'transform_response': 'openai_chat',
                'timeout': 30.0,
                'model_config': {
                    'model': 'gpt-4o',
                    'temperature': 0.7,
                    'max_tokens': 150,
                    'top_p': 1,
                    'frequency_penalty': 0,
                    'presence_penalty': 0,
                    'stream': False
                }
            },
            'ANTHROPIC': {
                'host': 'api.anthropic.com',
                'port': 443,
                'is_api': True,
                'path': '/v1/messages',
                'headers': {
                    'x-api-key': 'your-anthropic-api-key-here',
                    'content-type': 'application/json',
                    'anthropic-version': '2023-06-01'
                },
                'transform_request': 'anthropic_chat',
                'transform_response': 'anthropic_chat',
                'timeout': 30.0,
                'model_config': {
                    'model': 'claude-3-opus-20240229',
                    'max_tokens': 1024,
                    'temperature': 0.7,
                    'top_p': 1,
                    'stream': False
                }
            },
            'GEMINI': {
                'host': 'generativelanguage.googleapis.com',
                'port': 443,
                'is_api': True,
                'path': '/v1beta/models/gemini-pro:generateContent',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'params': {
                    'key': 'your-google-api-key-here'
                },
                'transform_request': 'gemini_chat',
                'transform_response': 'gemini_chat',
                'timeout': 30.0,
                'model_config': {
                    'temperature': 0.7,
                    'top_p': 1,
                    'top_k': 40,
                    'max_output_tokens': 2048,
                }
            },
            'MISTRAL': {
                'host': 'api.mistral.ai',
                'port': 443,
                'is_api': True,
                'path': '/v1/chat/completions',
                'headers': {
                    'Authorization': 'Bearer your-mistral-api-key-here',
                    'Content-Type': 'application/json'
                },
                'transform_request': 'openai_chat',  # Mistral uses OpenAI-compatible API
                'transform_response': 'openai_chat',
                'timeout': 30.0,
                'model_config': {
                    'model': 'mistral-large-latest',
                    'temperature': 0.7,
                    'top_p': 1,
                    'max_tokens': 1000,
                    'stream': False
                }
            }
        }
    },
    'alice': {
        'endpoints': {
            'behrooz': {'host': '127.0.0.1', 'port': 10000},
            'bob': {'host': '127.0.0.1', 'port': 10002},
            'BOT': {
                'host': 'api.openai.com',
                'port': 443,
                'is_api': True,
                'path': '/v1/chat/completions',
                'headers': {
                    'Authorization': 'Bearer your-openai-api-key-here',
                    'Content-Type': 'application/json'
                },
                'transform_request': 'openai_chat',
                'transform_response': 'openai_chat',
                'timeout': 30.0,
                'model_config': {
                    'model': 'gpt-3.5-turbo',  # Different model for Alice
                    'temperature': 0.9,        # Different temperature
                    'max_tokens': 100,         # Different token limit
                    'top_p': 1,
                    'frequency_penalty': 0,
                    'presence_penalty': 0,
                    'stream': False
                }
            }
        }
    },
    'bob': {
        'endpoints': {
            'behrooz': {'host': '127.0.0.1', 'port': 10000},
            'alice': {'host': '127.0.0.1', 'port': 10001},
            'BOT': {
                'host': 'api.openai.com',
                'port': 443,
                'is_api': True,
                'path': '/v1/chat/completions',
                'headers': {
                    'Authorization': 'Bearer your-openai-api-key-here',
                    'Content-Type': 'application/json'
                },
                'transform_request': 'openai_chat',
                'transform_response': 'openai_chat',
                'timeout': 30.0,
                'model_config': {
                    'model': 'gpt-4-turbo-preview',  # Different model for Bob
                    'temperature': 0.5,              # Different temperature
                    'max_tokens': 200,               # Different token limit
                    'top_p': 1,
                    'frequency_penalty': 0.1,        # Added frequency penalty
                    'presence_penalty': 0.1,         # Added presence penalty
                    'stream': False
                }
            }
        }
    },
    'BOT': {
        'endpoints': {
            'behrooz': {'host': '127.0.0.1', 'port': 10000},
            'alice': {'host': '127.0.0.1', 'port': 10001},
            'bob': {'host': '127.0.0.1', 'port': 10002}
        }
    }
}

async def cleanup_stale_proxies():
    """Remove proxies that haven't checked in for more than 2 minutes"""
    while True:
        try:
            current_time = datetime.utcnow()
            stale_proxies = []

            for proxy_id, info in registered_proxies.items():
                if current_time - info['last_seen'] > timedelta(minutes=2):
                    stale_proxies.append(proxy_id)

            for proxy_id in stale_proxies:
                logger.info(f"Removing stale proxy: {proxy_id}")
                del registered_proxies[proxy_id]

            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)


# API Routes


@app.route('/api/register', methods=['POST'])
async def register_proxy():
    """Register a proxy with the controller"""
    try:
        data = await request.get_json()

        proxy_id = data.get('proxy_id')
        instance_name = data.get('instance_name')
        host = data.get('host')
        port = data.get('port')

        if not all([proxy_id, instance_name, host, port]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields'
            }), 400

        # Initialize endpoints based on instance type
        if instance_name in DEFAULT_ENDPOINTS:
            # Known instance gets full default configuration
            initial_endpoints = DEFAULT_ENDPOINTS[instance_name]['endpoints'].copy()
            logger.info(f"Using predefined endpoints for {instance_name}")
        else:
            # New instance gets just the BOT endpoint
            initial_endpoints = DEFAULT_BOT_ENDPOINT.copy()
            logger.info(f"New instance {instance_name} registered. Providing default BOT endpoint")

        registered_proxies[proxy_id] = {
            'instance_name': instance_name,
            'host': host,
            'port': port,
            'last_seen': datetime.now(),
            'endpoints': initial_endpoints
        }

        logger.info(f"Registering {instance_name} with endpoints: {list(initial_endpoints.keys())}")

        return jsonify({
            'status': 'success',
            'message': 'Successfully registered',
            'endpoints': initial_endpoints
        })

    except Exception as e:
        logger.error(f"Error registering proxy: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/getendpoints', methods=['GET'])
async def get_endpoints():
    """Return proxy-specific endpoint configuration"""
    try:
        proxy_id = request.args.get('proxy_id')

        if not proxy_id or proxy_id not in registered_proxies:
            return jsonify({
                'status': 'error',
                'message': 'Unknown proxy'
            }), 404

        # Update last seen timestamp
        registered_proxies[proxy_id]['last_seen'] = datetime.now()

        proxy_info = registered_proxies[proxy_id]
        instance_name = proxy_info['instance_name']

        # If no endpoints exist yet, initialize them
        if 'endpoints' not in proxy_info:
            if instance_name in DEFAULT_ENDPOINTS:
                proxy_info['endpoints'] = DEFAULT_ENDPOINTS[instance_name]['endpoints'].copy()
            else:
                proxy_info['endpoints'] = DEFAULT_BOT_ENDPOINT.copy()

        # Ensure BOT endpoint is always present, but don't overwrite if exists
        if 'BOT' not in proxy_info['endpoints']:
            proxy_info['endpoints']['BOT'] = DEFAULT_BOT_ENDPOINT['BOT']

        logger.info(f"Returning endpoints for {proxy_id} ({instance_name}): {list(proxy_info['endpoints'].keys())}")

        return jsonify({
            'status': 'success',
            'endpoints': proxy_info['endpoints']
        })

    except Exception as e:
        logger.error(f"Error getting endpoints: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# Add this helper function to controller.py
def deep_merge(original, update):
    """
    Recursively merge two dictionaries, preserving nested structures
    """
    if not isinstance(original, dict) or not isinstance(update, dict):
        return update

    merged = original.copy()
    for key, value in update.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# Then modify the endpoint update route in controller.py
@app.route('/api/update_proxy_endpoints/<proxy_id>', methods=['POST'])
async def update_proxy_endpoints(proxy_id):
    """Update endpoint configuration for a specific proxy"""
    try:
        if proxy_id not in registered_proxies:
            return jsonify({
                'status': 'error',
                'message': 'Proxy not found'
            }), 404

        data = await request.get_json()
        proxy_info = registered_proxies[proxy_id]
        instance_name = proxy_info['instance_name']

        # Get current endpoints or initialize appropriately
        current_endpoints = proxy_info.get('endpoints')
        if not current_endpoints:
            if instance_name in DEFAULT_ENDPOINTS:
                current_endpoints = DEFAULT_ENDPOINTS[instance_name]['endpoints'].copy()
            else:
                current_endpoints = DEFAULT_BOT_ENDPOINT.copy()

        # If custom endpoints are provided in the request
        if 'endpoints' in data:
            try:
                custom_endpoints = data['endpoints']
                if isinstance(custom_endpoints, str):
                    custom_endpoints = json.loads(custom_endpoints)

                # Deep merge the endpoints
                for endpoint_name, endpoint_config in custom_endpoints.items():
                    if endpoint_name in current_endpoints:
                        current_endpoints[endpoint_name] = deep_merge(
                            current_endpoints[endpoint_name],
                            endpoint_config
                        )
                    else:
                        current_endpoints[endpoint_name] = endpoint_config

            except json.JSONDecodeError:
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid JSON in endpoints configuration'
                }), 400

        # Ensure BOT endpoint is present with all required fields
        if 'BOT' not in current_endpoints:
            current_endpoints['BOT'] = DEFAULT_BOT_ENDPOINT['BOT']
        else:
            # Ensure all required BOT endpoint fields are present
            bot_endpoint = current_endpoints['BOT']
            default_bot = DEFAULT_BOT_ENDPOINT['BOT']

            # Make sure critical API fields exist
            for key in ['is_api', 'path', 'headers', 'transform_request', 'transform_response']:
                if key not in bot_endpoint:
                    bot_endpoint[key] = default_bot[key]

            # Ensure model_config exists and has required fields
            if 'model_config' not in bot_endpoint:
                bot_endpoint['model_config'] = default_bot['model_config']
            else:
                for key in default_bot['model_config']:
                    if key not in bot_endpoint['model_config']:
                        bot_endpoint['model_config'][key] = default_bot['model_config'][key]

        # Store the updated configuration
        proxy_info['endpoints'] = current_endpoints

        logger.info(f"Updated endpoints for {proxy_id}: {list(current_endpoints.keys())}")
        logger.debug(f"Full endpoint configuration: {json.dumps(current_endpoints, indent=2)}")

        return jsonify({
            'status': 'success',
            'message': f'Updated endpoints for proxy {proxy_id}',
            'endpoints': current_endpoints
        })

    except Exception as e:
        logger.error(f"Error updating endpoints: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/heartbeat', methods=['POST'])
async def heartbeat():
    """Update last_seen timestamp for a proxy"""
    try:
        data = await request.get_json()
        proxy_id = data.get('proxy_id')

        if not proxy_id or proxy_id not in registered_proxies:
            return jsonify({
                'status': 'error',
                'message': 'Unknown proxy'
            }), 404

        registered_proxies[proxy_id]['last_seen'] = datetime.utcnow()

        return jsonify({
            'status': 'success',
            'message': 'Heartbeat received'
        })

    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500




@app.route('/')
async def index():
    """Controller dashboard"""
    return await render_template(
        'controller.html',
        proxies=registered_proxies,
        current_time=datetime.now()  # Changed from utcnow
    )

@app.route('/api/remove_proxy/<proxy_id>', methods=['POST'])
async def remove_proxy(proxy_id):
    """Remove a proxy from the registered list"""
    try:
        if proxy_id in registered_proxies:
            del registered_proxies[proxy_id]
            return jsonify({
                'status': 'success',
                'message': f'Removed proxy {proxy_id}'
            })
        return jsonify({
            'status': 'error',
            'message': 'Proxy not found'
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# Templates directory setup
app.template_folder = 'templates'

if not os.path.exists(app.template_folder):
    os.makedirs(app.template_folder)

# Create controller.html template
CONTROLLER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat Controller Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        function updateProxyEndpoints(proxyId) {
            const config = document.getElementById(`config_${proxyId}`).value;
            try {
                // Validate JSON
                JSON.parse(config);

                fetch(`/api/update_proxy_endpoints/${proxyId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ endpoints: config })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        location.reload();
                    } else {
                        alert('Error: ' + data.message);
                    }
                });
            } catch (e) {
                alert('Invalid JSON format');
            }
        }

        function removeProxy(proxyId) {
            if (confirm('Are you sure you want to remove this proxy?')) {
                fetch(`/api/remove_proxy/${proxyId}`, {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        location.reload();
                    } else {
                        alert('Error: ' + data.message);
                    }
                });
            }
        }

        // Auto-refresh the page every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-8">Chat Controller Dashboard</h1>

        <!-- Registered Proxies Section -->
        <div class="bg-white rounded-lg shadow-md p-6 mb-8">
            <h2 class="text-2xl font-bold mb-4">Registered Proxies</h2>
            <div class="space-y-6">
                {% for proxy_id, info in proxies.items() %}
                <div class="border-t pt-4">
                    <div class="flex justify-between items-start mb-4">
                        <div>
                            <h3 class="text-lg font-semibold">{{ info.instance_name }} ({{ proxy_id[:8] }}...)</h3>
                            <div class="text-sm text-gray-600">
                                Host: {{ info.host }} | Port: {{ info.port }} | 
                                Last Seen: {{ (info.last_seen).strftime('%Y-%m-%d %H:%M:%S') }}
                                {% set time_diff = (current_time - info.last_seen).total_seconds() %}
                                {% if time_diff < 60 %}
                                    <span class="px-2 py-1 bg-green-100 text-green-800 rounded">Active</span>
                                {% elif time_diff < 120 %}
                                    <span class="px-2 py-1 bg-yellow-100 text-yellow-800 rounded">Warning</span>
                                {% else %}
                                    <span class="px-2 py-1 bg-red-100 text-red-800 rounded">Stale</span>
                                {% endif %}
                            </div>
                        </div>
                        <button
                            onclick="removeProxy('{{ proxy_id }}')"
                            class="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600"
                        >
                            Remove
                        </button>
                    </div>
                    <div class="space-y-2">
                        <label class="block font-medium">Endpoints Configuration:</label>
                        <textarea 
                            id="config_{{ proxy_id }}"
                            class="w-full h-48 font-mono text-sm p-2 border rounded"
                        >{{ info.endpoints | tojson(indent=2) }}</textarea>
                        <button
                            onclick="updateProxyEndpoints('{{ proxy_id }}')"
                            class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
                        >
                            Update Configuration
                        </button>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
"""
# Write template file
with open(os.path.join(app.template_folder, 'controller.html'), 'w') as f:
    f.write(CONTROLLER_TEMPLATE)


def run_controller(host='0.0.0.0', port=8000):
    """Run the controller service"""
    config = Config()
    config.bind = [f"{host}:{port}"]

    logger.info(f"Starting controller on {host}:{port}")
    logger.info(f"Dashboard available at http://{host}:{port}")
    asyncio.run(serve(app, config))


if __name__ == "__main__":
    run_controller()