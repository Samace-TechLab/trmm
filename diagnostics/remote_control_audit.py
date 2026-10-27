"""Offline investigation: CDP class structure and the hub's actual relay coroutine.

Uses fabricated messages and sockets only. Does not launch an agent/browser,
read browser profiles, access credentials, or contact any server.
Run from the repository root with: python diagnostics/remote_control_audit.py
"""

import ast
import asyncio
import json
import logging
from pathlib import Path
import statistics
import subprocess
import types
import time
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[1]


def cdp_audit():
    path = ROOT / "hvnc" / "cdp_controller.py"
    source = path.read_text(encoding="utf-8")
    # This module's top level contains stdlib imports and definitions only.
    namespace = {"__name__": "offline_cdp_audit"}
    exec(compile(source, str(path), "exec"), namespace)
    controller = namespace["CDPController"]()
    required_methods = ("is_port_open", "list_tabs", "find_browser_binary", "get_user_data_path")
    required_attributes = ("ws", "_command_id", "is_streaming", "frame_callback")
    result = {
        "class_definition_lines": [
            node.lineno for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef) and node.name == "CDPController"
        ],
        "missing_methods": [name for name in required_methods if not hasattr(controller, name)],
        "missing_attributes": [name for name in required_attributes if not hasattr(controller, name)],
        "copy_helper_missing_globals": [
            name for name in ("shutil", "ctypes", "wintypes") if name not in namespace
        ],
    }
    # Attribute lookup reproduces the first failure without making an HTTP request.
    try:
        getattr(controller, "is_port_open")
    except AttributeError as error:
        result["first_launch_failure"] = f"{type(error).__name__}: {error}"

    previous = subprocess.check_output(
        ["git", "show", "0607314^:hvnc/cdp_controller.py"],
        cwd=ROOT, text=True, encoding="utf-8",
    )
    prior_namespace = {"__name__": "offline_previous_cdp_audit"}
    exec(compile(previous, "previous_cdp_controller.py", "exec"), prior_namespace)
    prior = prior_namespace["CDPController"]()
    result["parent_commit_missing_methods"] = [
        name for name in required_methods if not hasattr(prior, name)
    ]
    return result


class SimulatedDisconnect(Exception):
    pass


async def reconnect_audit():
    """Reproduce old-connection cleanup against the real registry methods."""
    path = ROOT / "master_hub" / "agent_manager.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))

    class Socket:
        def __init__(self):
            self.closed = False

        async def close(self, **kwargs):
            self.closed = True

    namespace = {
        "WebSocket": Socket, "Dict": Dict, "Any": Any, "Optional": Optional,
        "time": time, "json": json, "logger": logging.getLogger("offline_reconnect_audit"),
    }
    exec(compile(module, str(path), "exec"), namespace)
    # Avoid the unrelated OTA file scan/import; registry methods stay unchanged.
    namespace["ConnectedAgent"].to_dict = lambda self: {"agent_id": self.agent_id}
    manager = namespace["AgentManager"]()
    old_socket, new_socket = Socket(), Socket()
    manager.register_connection("synthetic", old_socket, {})
    replacement = manager.register_connection("synthetic", new_socket, {})
    replacement_present_before_cleanup = manager.get_agent("synthetic") is replacement
    await asyncio.sleep(0)
    # The old tunnel's finally block passes only the agent ID.
    manager.unregister_connection("synthetic")
    return {
        "replacement_present_before_old_cleanup": replacement_present_before_cleanup,
        "old_socket_closed": old_socket.closed,
        "new_socket_still_open": not new_socket.closed,
        "replacement_present_after_old_cleanup": manager.get_agent("synthetic") is replacement,
        "recorded_status_after_old_cleanup": manager.registered_agents["synthetic"]["status"],
    }


async def relay_audit(slow_viewer=False, separate_modes=False):
    """Run the unchanged relay body, isolated from app startup and real sockets."""
    frame_count = 15
    frame_interval = 1 / 30
    slow_send_delay = 0.100
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    frame_times = {}
    heartbeat_times = {}
    fast_frame_ages = []
    largest_queue = 0

    class Viewer:
        def __init__(self, slow=False):
            self.slow = slow

        async def send_bytes(self, data):
            if self.slow:
                await asyncio.sleep(slow_send_delay)
            else:
                fast_frame_ages.append((loop.time() - frame_times[int(data)]) * 1000)

        async def send_text(self, data):
            pass

    fast = Viewer()
    slow = Viewer(slow=True)
    agent = types.SimpleNamespace(
        viewers={"slow": slow} if separate_modes else {},
        mirror_viewers=({"slow": slow, "fast": fast} if slow_viewer and not separate_modes else {"fast": fast}),
        is_streaming_mirror=True,
        is_streaming_hvnc=separate_modes,
    )

    def update_info(info):
        heartbeat_times["processed"] = loop.time()

    agent.update_info = update_info
    manager = types.SimpleNamespace(
        decommissioned_agents=set(),
        register_connection=lambda *args: agent,
        unregister_connection=lambda *args: None,
    )

    class AgentSocket:
        async def accept(self):
            pass

        async def receive_text(self):
            return json.dumps({"type": "handshake", "data": {"code_hash": "synthetic"}})

        async def receive(self):
            item = await queue.get()
            if item is None:
                raise SimulatedDisconnect()
            return item

    async def broadcast_agent_list():
        pass

    source_path = ROOT / "master_hub" / "app.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "websocket_agent_tunnel"
    )
    function.decorator_list = []
    isolated = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {
        "WebSocket": AgentSocket,
        "WebSocketDisconnect": SimulatedDisconnect,
        "agent_mgr": manager,
        "OTAManager": types.SimpleNamespace(get_code_manifest=lambda: {"overall_hash": "synthetic"}),
        "broadcast_agent_list": broadcast_agent_list,
        "json": json,
        "logger": logging.getLogger("offline_relay_audit"),
    }
    exec(compile(isolated, str(source_path), "exec"), namespace)

    async def producer():
        nonlocal largest_queue
        for index in range(frame_count):
            frame_times[index] = loop.time()
            # Interleave the two streams in the cross-mode experiment.
            kind = 1 if separate_modes and index % 2 == 0 else 2
            await queue.put({"bytes": bytes([kind]) + str(index).encode("ascii")})
            largest_queue = max(largest_queue, queue.qsize())
            await asyncio.sleep(frame_interval)
        heartbeat_times["sent"] = loop.time()
        await queue.put({"text": json.dumps({"type": "heartbeat", "data": {}})})
        await queue.put(None)

    await asyncio.wait_for(
        asyncio.gather(namespace["websocket_agent_tunnel"](AgentSocket(), "synthetic"), producer()),
        timeout=10,
    )
    return {
        "scenario": "slow_backstage_fast_mirror" if separate_modes else (
            "slow_and_fast_mirror_viewers" if slow_viewer else "fast_mirror_viewer_only"
        ),
        "synthetic_source_fps": 30,
        "synthetic_slow_send_ms": 100 if slow_viewer or separate_modes else 0,
        "fast_viewer_frames_received": len(fast_frame_ages),
        "fast_viewer_median_frame_age_ms": round(statistics.median(fast_frame_ages), 1),
        "fast_viewer_max_frame_age_ms": round(max(fast_frame_ages), 1),
        "heartbeat_delay_ms": round((heartbeat_times["processed"] - heartbeat_times["sent"]) * 1000, 1),
        "largest_simulated_incoming_queue": largest_queue,
    }


async def main():
    result = {
        "scope": "offline reproduction; synthetic timings are not live-server measurements",
        "cdp": cdp_audit(),
        "reconnect": await reconnect_audit(),
        "relay": [
            await relay_audit(),
            await relay_audit(slow_viewer=True),
            await relay_audit(separate_modes=True),
        ],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
