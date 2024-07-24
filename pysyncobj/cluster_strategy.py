from abc import ABC, abstractmethod
from dataclasses import dataclass
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import signal
import sys
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ClusterStrategy(ABC):
    @abstractmethod
    def get_nodes(self) -> set[str]:
        pass

    @property
    @abstractmethod
    def polling_interval(self) -> int:
        pass


@dataclass
class FileClusterStrategy(ClusterStrategy):
    filename: str
    poll_interval: int

    def __read_file(self):
        try:
            with open(self.file_path, "r") as file:
                return file.readlines()
        except FileNotFoundError:
            return []

    def get_nodes(self) -> list[str]:
        lines = self.__read_file()
        file_nodes = {line.strip() for line in lines}
        return list(file_nodes)


@dataclass
class StaticClusterStrategy(ClusterStrategy):
    nodes: list[str]
    poll_interval: int

    def get_nodes(self) -> list[str]:
        return self.nodes


class NetworkScanner(ClusterStrategy):
    def __init__(self, application_port, port=45892):
        self.polling_interval = 0.5
        self.port = port
        self.application_port = application_port
        self.devices = []
        self.responses = {}
        self.local_ip = self.__get_local_ip()
        self.listener_thread = threading.Thread(target=self.__start_listener)
        self.listener_thread.daemon = True
        self.listener_thread.start()
        signal.signal(signal.SIGINT, self.__shutdown)
        signal.signal(signal.SIGTERM, self.__shutdown)

    def polling_interval(self):
        return self.polling_interval

    def __get_local_ip(self):
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        logger.debug(f"Local IP: {local_ip}")
        return local_ip

    def __get_ip_range(self):
        ip_parts = self.local_ip.split(".")
        ip_parts[-1] = "0"
        return ".".join(ip_parts) + "/24"

    def __is_port_open(self, ip, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0

    def __scan_ip(self, ip):
        if self.__is_port_open(ip, self.port):
            return ip
        return None

    def __scan_network(self):
        ip_range = self.__get_ip_range().split("/")[0]
        ip_base = ip_range.rsplit(".", 1)[0]
        ip_list = [f"{ip_base}.{i}" for i in range(2, 255)]

        open_port_devices = []
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(self.__scan_ip, ip) for ip in ip_list]
            for future in futures:
                result = future.result()
                if result and result != self.local_ip:
                    open_port_devices.append(result)
        return open_port_devices

    def __communicate_with_devices(self, devices):
        responses = {}
        for ip in devices:
            if ip == self.local_ip:  # Evita que el nodo se comunique consigo mismo
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, self.port))
                    message = f"ping"
                    s.sendall(message.encode())
                    data = s.recv(1024)
                    responses[ip] = data.decode()
            except Exception:
                pass
        responses = {f"{k}:{self.application_port}" for k in responses.keys()}
        return responses

    def __handle_client(self, client_socket):
        _ = client_socket.recv(1024)
        response = f"pong"
        client_socket.send(response.encode())
        client_socket.close()

    def __shutdown(self):
        self.running = False
        self.listener_thread.join()
        sys.exit(0)

    def __start_listener(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("", self.port))
        server.listen(5)

        while True:
            client_socket, _ = server.accept()
            client_handler = threading.Thread(
                target=self.__handle_client, args=(client_socket,)
            )
            client_handler.start()

    def get_nodes(self) -> set[str]:
        self.devices = self.__scan_network()
        self.responses = self.__communicate_with_devices(self.devices)
        return self.responses


def main(
    port,
    application_port,
):
    scanner = NetworkScanner(port=port, application_port=application_port)
    nodes = []
    import time

    for _ in range(10):
        time.sleep(scanner.polling_interval)
        nodes = scanner.get_nodes()
        logger.debug(f"Nodes: {nodes}")


if __name__ == "__main__":
    port_enviroment = os.environ.get("PORT", 45892)
    application_port = os.environ.get("APPLICATION_PORT", 8080)
    main(port=port_enviroment, application_port=application_port)
