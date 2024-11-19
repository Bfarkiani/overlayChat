# Overlay Chat System

A peer-to-peer chat system built on the [Hermes Architecture](https://github.com/Bfarkiani/Hermes), enabling communication between multiple users over an overlay and AI models including GPT-4, Claude, Gemini, and Mistral.

## Features
- 🤝 Peer-to-peer messaging
- 🤖 Multi-AI integration (OpenAI, Anthropic, Google, Mistral)
- 🔄 Basic auto-response capability
- 📊 Web-based controller dashboard
- ⚡ Real-time updates via SSE
- 🎯 Configurable endpoints

## Architecture Overview

The system utilizes the Hermes Architecture pattern, providing a clear separation of concerns between networking, application logic, and system management.

### Component Separation
```
Controller (8000)
    ├── Behrooz
    │   ├── UI/Peer (5000)
    │   └── Proxy (10000)
    ├── Alice
    │   ├── UI/Peer (5001)
    │   └── Proxy (10001)
    ├── Bob
    │   ├── UI/Peer (5002)
    │   └── Proxy (10002)
    └── BOT
        ├── UI/Peer (5003)
        └── Proxy (10003)
```

### Architectural Benefits

#### 1. Separation of Concerns
- **Peer Component**
  - Focuses on chat logic and user interface
  - Handles local message storage and display
  - Manages user interactions
  - Communicates only with its local proxy

- **Proxy Component**
  - Abstracts network complexity from the application
  - Handles message routing
  - Performs message transformation for AI services
  - Manages API communications

- **Controller Component**
  - Provides centralized configuration management
  - Handles peer registration
  - Enables system monitoring via dashboard
  - Manages endpoint configuration

#### 2. Design Pattern Benefits
- **Network Abstraction**
  - Applications communicate through local proxy
  - Proxy handles all remote communication details
  - Simplified error handling through proxy layer
  - Consistent message routing

- **Centralized Management**
  - Single point of configuration through controller
  - Dynamic endpoint updates
  - System-wide monitoring
  - Simplified peer discovery

### Components
- **Peer**: Handles chat interface and message storage
- **Proxy**: Routes messages and handles API communication
- **Controller**: Manages configuration and provides dashboard

## Installation

### Prerequisites
- Python 3.7 or higher
- pip package manager
- Available ports (8000, 5000-5003, 10000-10003)

### Dependencies
```bash
pip install quart httpx tinydb hypercorn
```

## Configuration

### 1. API Keys
Add your API keys in `controller.py`:

```python
DEFAULT_ENDPOINTS = {
    'behrooz': {
        'endpoints': {
            'BOT': {
                'headers': {
                    'Authorization': 'Bearer your-openai-api-key-here',
                },
            },
            'ANTHROPIC': {
                'headers': {
                    'x-api-key': 'your-anthropic-api-key-here',
                },
            },
            'GEMINI': {
                'params': {
                    'key': 'your-google-api-key-here',
                },
            },
            'MISTRAL': {
                'headers': {
                    'Authorization': 'Bearer your-mistral-api-key-here',
                },
            },
        }
    }
}
```

### 2. Instance Configuration
Configure instances in `startup.py`:

```python
INSTANCES = {
    'behrooz': {
        'name': 'Behrooz App',
        'client_port': 5000,
        'proxy_port': 10000,
        'auto_mode': False
    },
    # Add more instances as needed.  
}
```

### 3. Auto-Response Configuration
Configure auto-responses in `peer.py`:

```python
AUTO_RESPONSES = {
    "alice": [
        "Hi! This is Alice's automated response.",
        "Hope you're having a great day!"
    ],
    # Add more responses for other instances
}
```

## Usage

### Starting the System
```bash
python startup.py
```

### Accessing Components
- Controller Dashboard: `http://localhost:8000`
- Chat Interfaces:
  - Behrooz: `http://localhost:5000`
  - Alice: `http://localhost:5001`
  - Bob: `http://localhost:5002`
  - BOT: `http://localhost:5003`

### Using the Chat Interface
1. Select a peer from the available list
2. Type your message in the input field
3. Press Enter or click Send
4. For AI interactions, select BOT/ANTHROPIC/GEMINI/MISTRAL

### Controller Dashboard Features
- View active connections
- Configure endpoints
- View system status

## Component Details

### Controller (`controller.py`)
- Manages endpoint configuration
- Provides web dashboard
- Handles proxy registration

### Proxy (`proxy.py`)
- Routes messages between peers
- Handles API communication
- Transforms messages for different APIs

### Peer (`peer.py`)
- Provides chat interface
- Stores messages locally using TinyDB
- Handles chat logic

### Startup (`startup.py`)
- Starts all components
- Manages process lifecycle

## Message Flow
1. User sends message through chat interface
2. Peer forwards to local proxy
3. Proxy determines destination and routes message
4. For AI services, proxy transforms message format
5. Recipient displays message

## Troubleshooting

### Common Issues
1. **Ports Already in Use**
   ```bash
   # Check ports
   netstat -ano | findstr "8000 5000 10000"
   # Kill process
   taskkill /PID <process_id> /F
   ```

2. **Connection Issues**
   - Verify controller is running
   - Check proxy configuration
   - Confirm port availability

3. **API Issues**
   - Verify API keys in controller configuration
   - Check network connectivity
   - Review console logs

### Logging
Logs are available in the console with timestamp and component name.

## Current Limitations and TODOs

### Network Distribution
- The system currently supports endpoint updates and peers can be distributed across different machines
- Peers receive routing information through controller (no direct peer discovery)
- Currently requires all peers to be directly reachable (not behind NAT)
- Best suited for peers in the same network or with public IP addresses

### Future Improvements
1. **NAT Traversal**
   - Need to implement TURN server for NAT bypass
   - Controller already handles peer discovery/routing
   - TURN server would relay actual traffic between proxies when direct connection impossible
   - Proxy layer would hide TURN relay complexity from chat application
   - Would enable peer connectivity across different networks (home networks, offices etc.)

2. **P2P Network Enhancement**
   - Improve proxy-to-proxy communication reliability
   - Add better handling of network partitions
   - Improve fault tolerance

3. **Security Enhancements**
   - Add encryption for proxy-to-proxy communication
   - Implement authentication system
   - Secure API key management

## Contributing
Feel free to contribute to any of these improvements while maintaining the Hermes Architecture pattern of separating networking concerns from application logic.