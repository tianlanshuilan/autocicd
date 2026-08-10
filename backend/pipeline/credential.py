"""凭据管理模块 - 仅内存存储，进程退出即清除"""

import threading


class CredentialStore:
    """线程安全的内存凭据存储"""

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def set_git_credential(self, task_id: str, credential: dict):
        """存储 Git 凭据
        credential: {
            "type": "password" | "ssh_key",
            "username": str,
            "password": str,      # type=password 时使用
            "sshKey": str         # type=ssh_key 时使用
        }
        """
        with self._lock:
            key = f"{task_id}:git"
            self._store[key] = credential.copy()

    def get_git_credential(self, task_id: str) -> dict | None:
        with self._lock:
            key = f"{task_id}:git"
            return self._store.get(key)

    def set_server_credential(self, task_id: str, credential: dict):
        """存储服务器凭据
        credential: {
            "host": str,
            "port": int,
            "username": str,
            "authType": "password" | "ssh_key",
            "password": str,
            "sshKey": str,
            "deployPath": str
        }
        """
        with self._lock:
            key = f"{task_id}:server"
            self._store[key] = credential.copy()

    def get_server_credential(self, task_id: str) -> dict | None:
        with self._lock:
            key = f"{task_id}:server"
            return self._store.get(key)

    def set_relay_credential(self, task_id: str, credential: dict):
        """存储中继服务器凭据（用于跨云/隔离网络场景）
        credential: {
            "host": str,
            "port": int,
            "username": str,
            "authType": "password" | "ssh_key",
            "password": str,
            "sshKey": str,
            "isolated": bool,
            "notes": str
        }
        """
        with self._lock:
            key = f"{task_id}:relay"
            self._store[key] = credential.copy()

    def get_relay_credential(self, task_id: str) -> dict | None:
        with self._lock:
            key = f"{task_id}:relay"
            return self._store.get(key)

    def set_tool_server_credential(self, task_id: str, credential: dict):
        """存储 CI/CD 工具服务器凭据"""
        with self._lock:
            key = f"{task_id}:tool_server"
            self._store[key] = credential.copy()

    def get_tool_server_credential(self, task_id: str) -> dict | None:
        with self._lock:
            key = f"{task_id}:tool_server"
            return self._store.get(key)

    def set_network_access_credential(self, task_id: str, credential: dict):
        """存储网络访问方式凭据（中继/堡垒机/零信任）"""
        with self._lock:
            key = f"{task_id}:network_access"
            self._store[key] = credential.copy()

    def get_network_access_credential(self, task_id: str) -> dict | None:
        with self._lock:
            key = f"{task_id}:network_access"
            return self._store.get(key)

    def clear_task(self, task_id: str):
        """清除指定任务的所有凭据"""
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(f"{task_id}:")]
            for k in keys_to_remove:
                del self._store[k]

    def clear_all(self):
        """清除所有凭据"""
        with self._lock:
            self._store.clear()
