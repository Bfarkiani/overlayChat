import subprocess
import sys
import os
import signal
import atexit
import time
import logging
from typing import Dict, List
import json
import requests
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('chat_startup')

# Configuration
CONTROLLER_PORT = 8000
CONTROLLER_HOST = "127.0.0.1"
CONTROLLER_URL = f"http://{CONTROLLER_HOST}:{CONTROLLER_PORT}"

# Configuration for different instances
INSTANCES = {
    'behrooz': {
        'name': 'Behrooz App',
        'client_port': 5000,
        'proxy_port': 10000,
        'auto_mode': False
    },

    'alice': {
        'name': 'Alice App',
        'client_port': 5001,
        'proxy_port': 10001,
        'auto_mode': True
    },

    'bob': {
        'name': 'Bob App',
        'client_port': 5002,
        'proxy_port': 10002,
        'auto_mode': True
    },
    'BOT': {
        'name': 'BOT App',
        'client_port': 5003,
        'proxy_port': 10003,
        'auto_mode': False
    }
}


class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, Dict[str, subprocess.Popen]] = {}
        self.controller_process = None
        atexit.register(self.stop_all)

    def start_controller(self):
        """Start the controller service and wait for it to be ready"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            controller_script = os.path.join(current_dir, 'controller.py')

            env = os.environ.copy()
            env.update({
                'CONTROLLER_PORT': str(CONTROLLER_PORT),
                'CONTROLLER_HOST': CONTROLLER_HOST
            })

            self.controller_process = subprocess.Popen(
                [sys.executable, controller_script],
                env=env
            )

            logger.info(f"Started controller on port {CONTROLLER_PORT}")

            # Wait for controller to start up and be ready
            max_retries = 30  # Increased retries
            retry_delay = 1  # seconds
            for i in range(max_retries):
                try:
                    response = requests.get(f"{CONTROLLER_URL}/")
                    if response.status_code == 200:
                        logger.info("Controller is ready")
                        time.sleep(2)  # Give it a bit more time to fully initialize
                        return True
                except:
                    if i == max_retries - 1:
                        raise Exception("Controller failed to start")
                    time.sleep(retry_delay)
                    logger.info(f"Waiting for controller to start... ({i + 1}/{max_retries})")

        except Exception as e:
            logger.error(f"Failed to start controller: {e}")
            raise

    def generate_proxy_config(self, instance_name: str, config: dict) -> str:
        """Generate proxy configuration file for each instance"""
        proxy_config = {
            'instance_name': instance_name,
            'proxy_port': config['proxy_port'],
            'client_port': config['client_port'],
            'controller_url': CONTROLLER_URL
        }

        config_path = f'proxy_config_{instance_name}.json'
        with open(config_path, 'w') as f:
            json.dump(proxy_config, f, indent=2)

        logger.info(f"Generated proxy config for {instance_name}:")
        logger.info(f"Config path: {config_path}")
        logger.info(f"Config content: {json.dumps(proxy_config, indent=2)}")

        return config_path

    def start_instance(self, instance_name: str, config: dict):
        """Start all components for a single instance"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            env = os.environ.copy()

            # Add instance-specific environment variables
            env.update({
                'CLIENT_PORT': str(config['client_port']),
                'PROXY_PORT': str(config['proxy_port']),
                'INSTANCE_NAME': instance_name,
                'AUTO_MODE': str(config.get('auto_mode', False)).lower(),
                'CONTROLLER_URL': CONTROLLER_URL
            })

            # Generate proxy config
            proxy_config_path = self.generate_proxy_config(instance_name, config)

            # Start proxy
            proxy_script = os.path.join(current_dir, 'proxy.py')
            proxy_process = subprocess.Popen(
                [sys.executable, proxy_script, '--config', proxy_config_path],
                env=env
            )

            # Start client (backend + UI)
            client_script = os.path.join(current_dir, 'peer.py')
            client_process = subprocess.Popen(
                [sys.executable, client_script],
                env=env
            )

            # Store processes
            self.processes[instance_name] = {
                'proxy': proxy_process,
                'client': client_process
            }

            logger.info(f"Started {config['name']} - "
                        f"Client/UI: {config['client_port']}, "
                        f"Proxy: {config['proxy_port']}, "
                        f"Mode: {'Auto' if config.get('auto_mode') else 'Manual'}")

        except Exception as e:
            logger.error(f"Failed to start {instance_name}: {e}")
            self.stop_instance(instance_name)
            raise

    def stop_instance(self, instance_name: str):
        """Stop all processes for a single instance"""
        if instance_name in self.processes:
            for process_type, process in self.processes[instance_name].items():
                try:
                    logger.info(f"Stopping {instance_name} {process_type}...")
                    if sys.platform == 'win32':
                        process.terminate()
                    else:
                        os.kill(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
                except Exception as e:
                    logger.error(f"Error stopping {instance_name} {process_type}: {e}")
                    try:
                        process.kill()
                    except:
                        pass
            del self.processes[instance_name]

            # Clean up config file
            try:
                os.remove(f'proxy_config_{instance_name}.json')
            except:
                pass

    def stop_controller(self):
        """Stop the controller process"""
        if self.controller_process:
            try:
                logger.info("Stopping controller...")
                if sys.platform == 'win32':
                    self.controller_process.terminate()
                else:
                    os.kill(self.controller_process.pid, signal.SIGTERM)
                self.controller_process.wait(timeout=5)
            except Exception as e:
                logger.error(f"Error stopping controller: {e}")
                try:
                    self.controller_process.kill()
                except:
                    pass
            self.controller_process = None

    def stop_all(self):
        """Stop all running processes"""
        for instance_name in list(self.processes.keys()):
            self.stop_instance(instance_name)
        self.stop_controller()


def main():
    process_manager = ProcessManager()

    try:
        # Start controller first
        process_manager.start_controller()
        logger.info("Controller started successfully")

        # Wait a moment for controller to initialize
        time.sleep(2)

        # Start all instances
        for instance_name, config in INSTANCES.items():
            process_manager.start_instance(instance_name, config)
            time.sleep(2)  # Give each instance time to start

        logger.info("\nAll instances started successfully")
        logger.info("\nAvailable endpoints:")
        logger.info(f"Controller: http://{CONTROLLER_HOST}:{CONTROLLER_PORT}")
        for instance_name, config in INSTANCES.items():
            logger.info(f"{config['name']}:")
            logger.info(f"  - UI/Client: http://0.0.0.0:{config['client_port']}")
            logger.info(f"  - Proxy: http://0.0.0.0:{config['proxy_port']}")
            logger.info(f"  - Mode: {'Auto' if config.get('auto_mode') else 'Manual'}\n")

        # Keep running until interrupted
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down all instances...")
    finally:
        process_manager.stop_all()


if __name__ == "__main__":
    main()