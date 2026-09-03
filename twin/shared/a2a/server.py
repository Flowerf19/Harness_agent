"""A2A HTTP server with JSON-RPC endpoint and SSE streaming."""
import asyncio
import json
import logging
import uuid
from typing import AsyncIterator, Callable, Dict, Optional

from aiohttp import web

from twin.shared.a2a.types import (
    A2AMessage,
    A2ATask,
    AgentCard,
    Part,
    TaskStatus,
)
from twin.shared.observability import tracing_context_from_parent

logger = logging.getLogger(__name__)


class _HealthCheckFilter(logging.Filter):
    """Suppress access-log noise from healthcheck / agent-card polling."""

    _QUIET_PATHS = frozenset(["/.well-known/agent.json"])

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._QUIET_PATHS)

TaskHandler = Callable[[dict], AsyncIterator[A2AMessage]]


class A2AServer:
    def __init__(
        self,
        agent_card: AgentCard,
        skill_handlers: Dict[str, TaskHandler],
        host: str = "0.0.0.0",
        port: int = 8000,
        health_probe: Optional[Callable[[], bool]] = None,
    ):
        self.agent_card = agent_card
        self.skill_handlers = skill_handlers
        # Liveness of the platform connections behind the agent (e.g. Discord),
        # which the agent card cannot report: the A2A server stays up while the
        # bot is silently disconnected.
        self._health_probe = health_probe
        self.host = host
        self.port = port
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._tasks: Dict[str, A2ATask] = {}
        self._stream_clients: Dict[str, list[asyncio.Queue]] = {}
        self._task_buffers: Dict[str, list[A2AMessage]] = {}

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/.well-known/agent.json", self._handle_agent_card)
        app.router.add_get("/health", self._handle_health)
        app.router.add_post("/", self._handle_jsonrpc)
        app.router.add_get("/tasks/{task_id}/stream", self._handle_stream)
        return app

    async def start(self):
        self._app = self.build_app()
        access_logger = logging.getLogger("aiohttp.access")
        access_logger.addFilter(_HealthCheckFilter())
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"A2A server listening on {self.host}:{self.port}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            logger.info("A2A server stopped")

    async def wait_closed(self):
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    async def _handle_agent_card(self, request: web.Request) -> web.Response:
        data = {
            "name": self.agent_card.name,
            "description": self.agent_card.description,
            "url": self.agent_card.url,
            "version": self.agent_card.version,
            "provider": self.agent_card.provider,
            "capabilities": self.agent_card.capabilities,
            "skills": self.agent_card.skills,
        }
        return web.json_response(data)

    async def _handle_health(self, request: web.Request) -> web.Response:
        connected = True if self._health_probe is None else bool(self._health_probe())
        payload = {"status": "ok" if connected else "degraded", "connected": connected}
        return web.json_response(payload, status=200 if connected else 503)

    async def _handle_jsonrpc(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
                status=400,
            )

        method = body.get("method", "")
        params = body.get("params", {})
        rpc_id = body.get("id")

        try:
            if method == "tasks/send":
                result = await self._handle_send_task(params, request)
            elif method == "tasks/get":
                result = await self._handle_get_task(params)
            elif method == "tasks/cancel":
                result = await self._handle_cancel_task(params)
            else:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })

            return web.json_response({"jsonrpc": "2.0", "id": rpc_id, "result": result})

        except Exception as e:
            logger.exception(f"Error handling JSON-RPC method {method}")
            return web.json_response({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": str(e)},
            })

    async def _handle_send_task(self, params: dict, request: web.Request) -> dict:
        task_id = params.get("id", str(uuid.uuid4()))
        skill = params.get("skill", "chat")
        session_id = params.get("sessionId")
        trace_parent = self._langsmith_parent_from_request(request)

        task = A2ATask(
            id=task_id,
            session_id=session_id,
            skill=skill,
            status=TaskStatus.IN_PROGRESS,
        )

        if "message" in params:
            msg_data = params["message"]
            task.message = self._parse_message_input(msg_data)

        self._tasks[task_id] = task

        handler = self.skill_handlers.get(skill)
        if handler is None:
            task.status = TaskStatus.FAILED
            return self._task_to_dict(task)

        asyncio.create_task(
            self._execute_handler(task_id, task, handler, params, trace_parent)
        )

        return self._task_to_dict(task)

    async def _execute_handler(
        self,
        task_id: str,
        task: A2ATask,
        handler: TaskHandler,
        params: dict,
        trace_parent: dict[str, str] | None = None,
    ):
        self._task_buffers[task_id] = []
        try:
            with tracing_context_from_parent(trace_parent):
                async for message in handler(params):
                    self._task_buffers[task_id].append(message)
                    await self._broadcast_to_stream(task_id, message)
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            logger.exception(f"Task {task_id} handler failed")
            task.status = TaskStatus.FAILED
            err_msg = A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Error: {e}")],
            )
            self._task_buffers[task_id].append(err_msg)
            await self._broadcast_to_stream(task_id, err_msg)
        # Signal stream closure
        await self._broadcast_to_stream(task_id, None)

    async def _broadcast_to_stream(self, task_id: str, message):
        queues = self._stream_clients.get(task_id, [])
        for q in queues:
            await q.put(message)

    async def _handle_get_task(self, params: dict) -> dict:
        task_id = params.get("id", "")
        task = self._tasks.get(task_id)
        if task is None:
            return {}
        return self._task_to_dict(task)

    async def _handle_cancel_task(self, params: dict) -> dict:
        task_id = params.get("id", "")
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
        return self._task_to_dict(task) if task else {}

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        task_id = request.match_info["task_id"]

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        # Replay buffered messages
        buffered = self._task_buffers.get(task_id, [])
        for message in buffered:
            data = self._message_to_dict(message)
            await response.write(f"data: {json.dumps(data)}\n\n".encode("utf-8"))

        # If task already completed/failed/cancelled, close stream
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            await response.write_eof()
            return response

        # Otherwise, subscribe for future messages
        queue: asyncio.Queue = asyncio.Queue()
        if task_id not in self._stream_clients:
            self._stream_clients[task_id] = []
        self._stream_clients[task_id].append(queue)

        try:
            while True:
                message = await queue.get()
                if message is None:
                    break
                data = self._message_to_dict(message)
                await response.write(f"data: {json.dumps(data)}\n\n".encode("utf-8"))
        except asyncio.CancelledError:
            pass
        finally:
            self._stream_clients[task_id].remove(queue)
            if not self._stream_clients[task_id]:
                del self._stream_clients[task_id]

        await response.write_eof()
        return response

    def _parse_message_input(self, data: dict) -> A2AMessage:
        parts = []
        for p in data.get("parts", []):
            parts.append(Part(
                type=p.get("type", "text"),
                text=p.get("text"),
                data=p.get("data"),
                file_url=p.get("file_url"),
            ))
        return A2AMessage(
            role=data.get("role", "user"),
            parts=parts,
            message_id=data.get("messageId"),
            context_id=data.get("contextId"),
        )

    def _task_to_dict(self, task: A2ATask) -> dict:
        result = {
            "id": task.id,
            "sessionId": task.session_id,
            "skill": task.skill,
            "status": task.status.value,
            "artifacts": task.artifacts,
            "metadata": task.metadata,
        }
        if task.message:
            result["message"] = self._message_to_dict(task.message)
        return result

    def _message_to_dict(self, message: A2AMessage) -> dict:
        result = {"role": message.role}
        if message.message_id:
            result["messageId"] = message.message_id
        if message.context_id:
            result["contextId"] = message.context_id
        result["parts"] = []
        for p in message.parts:
            part = {"type": p.type}
            if p.text is not None:
                part["text"] = p.text
            if p.data is not None:
                part["data"] = p.data
            if p.file_url is not None:
                part["file_url"] = p.file_url
            result["parts"].append(part)
        return result

    @staticmethod
    def _langsmith_parent_from_request(request: web.Request) -> dict[str, str] | None:
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower().startswith("langsmith")
            or key.lower() in {"baggage", "traceparent"}
        }
        return headers or None
