"""EvernightAgent - consolidation + chat agent."""
import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from langsmith import traceable

from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.tools.tool_registry import ToolRegistry
from twin.shared.tools.exceptions import BashExecutorUnavailableError
from twin.shared.memories.episodic_memory_manager import EpisodicMemoryManager
from twin.shared.memories.wiki.models.wiki_page import WikiPagePayload, generate_page_id
from twin.shared.memories.wiki.wiki_merge import WikiMergeService
from twin.shared.a2a.types import AgentCard, A2AMessage, Part, TaskStatus
from twin.evernight.memories.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

TOOL_EXECUTION_TIMEOUT = 60

TOPIC_EXTRACTION_PROMPT = """Role: Topic_Extractor
Task: Extract_Topics_From_Snapshot

Input: A chat snapshot (list of messages)

Extract distinct topics mentioned in this conversation. For each topic, provide:
- canonical_topic: Normalized name (snake_case, e.g., "Evangelion_Anime")
- category: One of [entertainment, relationship, work_study, casual, daily_mood]
- summary: Brief summary about this topic from the conversation
- key_points: List of specific facts/mentions
- importance: 1-5 (how important this topic seems to the user)
- confidence: 0.0-1.0 (how confident in extraction)

Output: Return ONLY valid JSON array:
[
  {
    "canonical_topic": "<topic_name>",
    "category": "<category>",
    "summary": "<brief summary>",
    "key_points": ["<fact1>", "<fact2>"],
    "importance": <1-5>,
    "confidence": <0.0-1.0>
  }
]

If no clear topics found, return: []
"""


class EvernightAgent:
    def __init__(
        self,
        memory_manager: Any = None,
        episodic_memory: EpisodicMemoryManager = None,
        wiki_merge: WikiMergeService = None,
        llm_service: BaseLLMService = None,
        tool_registry: Optional[ToolRegistry] = None,
        use_native_tools: bool = True,
        march7_url: str = "http://march7:8000",
        **kwargs,
    ):
        self.memory = memory_manager or kwargs.pop("wiki_storage", None)
        self.episodic = episodic_memory or self.memory
        self.merge = wiki_merge
        self.llm = llm_service or kwargs.pop("llm_client", None)
        self._embedding_service = kwargs.pop("embedding_service", None)
        self.tool_registry = tool_registry
        self.use_native_tools = use_native_tools
        self.march7_url = march7_url
        self.use_native_tools = use_native_tools
        self.march7_url = march7_url

        self._llm_type = self._detect_llm_type()
        self._model_name = getattr(self.llm, "model", "unknown") if self.llm else "unknown"

        logger.debug(f"EvernightAgent initialized: model={self._model_name}")

    def _detect_llm_type(self) -> str:
        if self.llm is None:
            return "openai"
        class_name = self.llm.__class__.__name__
        if "Gemini" in class_name:
            return "gemini"
        return "openai"

    def get_agent_card(self) -> AgentCard:
        return AgentCard(
            name="Evernight",
            description="Memory consolidation and analysis agent",
            url="http://evernight:8001",
            version="1.0.0",
            capabilities=["chat", "consolidation", "streaming"],
            skills=[
                {"id": "chat", "name": "Chat", "description": "Conversational chat with memory and tools"},
                {"id": "consolidate", "name": "Consolidate", "description": "Consolidate T1 snapshot into T2 wiki"},
                {"id": "get_snapshot", "name": "Get Snapshot", "description": "Get T1 memory snapshot"},
            ],
        )

    async def get_status(self) -> dict:
        return {"status": "online", "model": self._model_name}

    # ------------------------------------------------------------------
    # Consolidate (original Evernight logic)
    # ------------------------------------------------------------------

    @traceable(name="T2_Consolidate", run_type="chain", tags=["evernight", "consolidation"])
    async def consolidate(self, user_id: str, snapshot: List[dict]) -> bool:
        logger.info(f"Evernight: Consolidating snapshot for user {user_id}")
        try:
            topics = await self._extract_topics(snapshot)
            if not topics:
                logger.info("Evernight: No topics found in snapshot")
                return True

            logger.info(f"Evernight: Found {len(topics)} topics")
            success_count = 0
            for topic_info in topics:
                try:
                    canonical_topic = topic_info.get("canonical_topic")
                    if not canonical_topic:
                        continue

                    page_id = generate_page_id(user_id, canonical_topic)
                    existing_page = await self.episodic.lookup_by_page_id(page_id)

                    if existing_page:
                        merged_page = await self.merge.merge(existing_page, topic_info)
                        if merged_page:
                            await self.episodic.embed_page(merged_page)
                            success_count += 1
                    else:
                        new_page = self.merge.create_new_page(
                            user_id=user_id,
                            canonical_topic=canonical_topic,
                            new_info=topic_info,
                        )
                        await self.episodic.embed_page(new_page)
                        success_count += 1

                except Exception as topic_error:
                    logger.error(f"Evernight: Error processing topic: {topic_error}")
                    continue

            logger.info(f"Evernight: Consolidated {success_count}/{len(topics)} topics for {user_id}")
            return success_count > 0
        except Exception as e:
            logger.error(f"Evernight: Consolidation failed: {e}", exc_info=True)
            return False

    async def _extract_topics(self, snapshot: List[dict]) -> List[dict]:
        try:
            snapshot_text = self._format_snapshot(snapshot)
            prompt = TOPIC_EXTRACTION_PROMPT + f"\n\nChat Snapshot:\n{snapshot_text}"

            llm_response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}]
            )

            if isinstance(llm_response, LLMResponse):
                raw_text = llm_response.content
            else:
                raw_text = str(llm_response)

            cleaned = raw_text.strip()
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"```$", "", cleaned).strip()

            topics = json.loads(cleaned)
            if isinstance(topics, list):
                return topics
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Evernight: Failed to parse topics JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Evernight: Topic extraction failed: {e}")
            return []

    def _format_snapshot(self, snapshot: List[dict]) -> str:
        lines = []
        for msg in snapshot:
            role = msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            lines.append(f"[{role.upper()}]: {content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Chat (new capability for Evernight)
    # ------------------------------------------------------------------

    @traceable(name="Evernight_Chat", run_type="chain", tags=["evernight", "chat"])
    async def handle_chat(self, user_id: str, content: str) -> str:
        try:
            await self.memory.add_message(user_id=user_id, role="user", content=content)

            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id, current_query=content
            )

            max_iterations = 10
            llm_response = None
            for i in range(max_iterations):
                llm_response = await self.llm.generate_response(
                    messages=context_msgs,
                    system_prompt=sys_prompt,
                    use_native_tools=self.use_native_tools,
                )

                if isinstance(llm_response, LLMResponse) and llm_response.has_tool_calls():
                    tool_calls = llm_response.tool_calls
                    logger.debug(
                        f"Evernight wants {len(tool_calls)} tools (iteration {i+1}/{max_iterations})"
                    )

                    tool_call_msg = self._format_tool_call_message(tool_calls)
                    context_msgs.append(tool_call_msg)

                    for tc in tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["arguments"]
                        tool_call_id = tc.get("id", str(uuid.uuid4()))

                        try:
                            tool_result = await asyncio.wait_for(
                                self.tool_registry.execute_tool(tool_name, tool_args),
                                timeout=TOOL_EXECUTION_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            tool_result = f"Lỗi: Tool '{tool_name}' timeout."
                        except Exception as tool_err:
                            tool_result = f"Lỗi: {tool_err}"

                        tool_result_msg = self._format_tool_result_message(
                            tool_call_id, tool_name, tool_result
                        )
                        context_msgs.append(tool_result_msg)
                    continue
                else:
                    break

            bot_response: str
            if isinstance(llm_response, LLMResponse):
                bot_response = llm_response.content
            else:
                bot_response = llm_response

            is_reasoning_only = isinstance(llm_response, LLMResponse) and llm_response.reasoning_only
            if bot_response and not bot_response.startswith("Error:") and not is_reasoning_only:
                await self.memory.add_message(
                    user_id=user_id, role="assistant", content=bot_response
                )

            return bot_response

        except Exception as e:
            logger.error(f"EvernightAgent chat error: {e}")
            return "Xin lỗi, tôi đang gặp chút trục trặc với hệ thống ký ức."

    async def clear_chat_history(self, user_id: str):
        await self.memory.clear_session(user_id)

    def _format_tool_call_message(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        if self._llm_type == "gemini":
            parts = []
            for tc in tool_calls:
                parts.append({
                    "functionCall": {"name": tc["name"], "args": tc["arguments"]}
                })
            return {"role": "model", "parts": parts}
        else:
            formatted = []
            for tc in tool_calls:
                formatted.append({
                    "id": tc.get("id", str(uuid.uuid4())),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                })
            return {"role": "assistant", "content": "", "tool_calls": formatted}

    def _format_tool_result_message(
        self, tool_call_id: str, tool_name: str, result: str
    ) -> Dict[str, Any]:
        if self._llm_type == "gemini":
            return {
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": result},
                    }
                }],
            }
        else:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result,
            }
