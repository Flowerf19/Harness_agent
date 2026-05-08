"""
MCPServer - Model Context Protocol Server implementation.

Theo chuẩn MCP (Anthropic's Model Context Protocol):
https://modelcontextprotocol.io/

Server responsibilities:
- Handle JSON-RPC 2.0 requests
- Route requests to appropriate handlers
- Manage tool registry
- Return proper responses

Supported endpoints:
- initialize: Server info and capabilities
- tools/list: List all available tools
- tools/call: Execute a tool

Architecture:
- Request Handler: Receives MCPRequest, returns MCPResponse
- Tool Registry: Stores all registered tools
- Error Handling: Proper JSON-RPC error codes
"""

import logging
import asyncio
from typing import Dict, Any, Optional

from src.services.tools.tool_registry import ToolRegistry
from src.services.tools.exceptions import BashExecutorUnavailableError
from src.services.tools.mcp_protocol import (
    MCPRequest,
    MCPResponse,
    MCPError,
    MCPMethods,
    MCPServerInfo,
    MCPCapabilities,
    ToolDefinition,
    JSONRPCErrorCodes,
)
from src.services.tools.base_tool import ToolExecutionError

logger = logging.getLogger(__name__)


class MCPServer:
    """
    Model Context Protocol Server.
    
    Handles JSON-RPC 2.0 requests and routes them to appropriate handlers.
    
    Attributes:
        registry: ToolRegistry containing all registered tools
        server_info: Server metadata (name, version, capabilities)
        initialized: Whether server has been initialized
    
    Example:
        registry = ToolRegistry()
        registry.register_tool(SearchMemoryTool())
        
        server = MCPServer(registry)
        
        # Handle a request
        request = MCPRequest(method="tools/list")
        response = await server.handle_request(request)
        
        # Response contains list of tools
    """
    
    # Default timeout for tool execution (seconds)
    DEFAULT_TOOL_TIMEOUT = 60
    
    def __init__(
        self,
        registry: ToolRegistry,
        server_name: str = "discord-bot-mcp-server",
        server_version: str = "1.0.0",
        tool_timeout: int = DEFAULT_TOOL_TIMEOUT,
    ):
        """
        Initialize MCP Server.
        
        Args:
            registry: ToolRegistry with registered tools
            server_name: Server name for identification
            server_version: Server version
            tool_timeout: Timeout for tool execution (seconds)
        """
        self.registry = registry
        self.tool_timeout = tool_timeout
        self.initialized = False
        
        self.server_info = MCPServerInfo(
            name=server_name,
            version=server_version,
            capabilities=MCPCapabilities(
                tools=True,
                resources=False,
                prompts=False,
            )
        )
        
        logger.info(f"MCPServer initialized: {server_name} v{server_version}")
        logger.info(f"  - Tools registered: {registry.count()}")
    
    # ==========================================
    # REQUEST HANDLER
    # ==========================================
    
    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        Handle incoming JSON-RPC request.
        
        Routes request to appropriate handler based on method.
        
        Args:
            request: MCPRequest object
            
        Returns:
            MCPResponse: Success or error response
        """
        logger.debug(f"📥 Received request: {request.method} (id={request.id})")
        
        try:
            # Route to handler based on method
            handler = self._get_handler(request.method)
            if handler is None:
                return MCPResponse.create_error(
                    MCPError.method_not_found(request.method),
                    request.id
                )
            
            # Execute handler
            result = await handler(request.params)
            
            return MCPResponse.success(result, request.id)
            
        except BashExecutorUnavailableError:
            raise
        except ToolExecutionError as e:
            logger.error(f"Tool execution error: {e}")
            return MCPResponse.create_error(
                MCPError.tool_execution_error(e.tool_name, e.message),
                request.id
            )
        except asyncio.TimeoutError:
            logger.error(f"Tool execution timeout")
            return MCPResponse.create_error(
                MCPError.tool_timeout("unknown", self.tool_timeout),
                request.id
            )
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return MCPResponse.create_error(
                MCPError.internal_error(str(e)),
                request.id
            )
    
    def _get_handler(self, method: str) -> Optional[callable]:
        """
        Get handler function for a method.
        
        Args:
            method: Method name
            
        Returns:
            Optional[callable]: Handler function if found, None otherwise
        """
        handlers = {
            MCPMethods.INITIALIZE: self._handle_initialize,
            MCPMethods.PING: self._handle_ping,
            MCPMethods.TOOLS_LIST: self._handle_tools_list,
            MCPMethods.TOOLS_CALL: self._handle_tools_call,
        }
        return handlers.get(method)
    
    # ==========================================
    # METHOD HANDLERS
    # ==========================================
    
    async def _handle_initialize(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle initialize request.
        
        Returns server info and capabilities.
        
        Args:
            params: Optional initialization params
            
        Returns:
            Dict: Server info and capabilities
        """
        self.initialized = True
        logger.info("✅ MCP Server initialized")
        
        return {
            "serverInfo": self.server_info.to_dict(),
            "capabilities": self.server_info.capabilities.to_dict(),
        }
    
    async def _handle_ping(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle ping request.
        
        Simple health check.
        
        Args:
            params: Optional params
            
        Returns:
            Dict: Ping response
        """
        return {"status": "ok", "timestamp": asyncio.get_event_loop().time()}
    
    async def _handle_tools_list(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle tools/list request.
        
        Returns list of all registered tools.
        
        Args:
            params: Optional params (ignored)
            
        Returns:
            Dict: List of tool definitions
        """
        tools = self.registry.get_all_mcp_schemas()
        tool_dicts = [tool.to_dict() for tool in tools]
        
        logger.debug(f"📋 Returning {len(tools)} tools")
        
        return {
            "tools": tool_dicts,
            "count": len(tools),
        }
    
    async def _handle_tools_call(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle tools/call request.
        
        Execute a tool with given arguments.
        
        Args:
            params: Dict containing:
                - name: Tool name
                - arguments: Tool arguments dict
            
        Returns:
            Dict: Tool execution result
            
        Raises:
            ToolExecutionError: If tool execution fails
        """
        if params is None:
            raise ToolExecutionError("unknown", "Missing params for tools/call")
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ToolExecutionError("unknown", "Missing 'name' in params")
        
        logger.info(f"🛠️ Calling tool: {tool_name} with args: {arguments}")
        
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self.registry.execute_tool(tool_name, arguments),
                timeout=self.tool_timeout
            )
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": result,
                    }
                ],
                "isError": False,
            }
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Tool '{tool_name}' timed out after {self.tool_timeout}s")
            raise ToolExecutionError(tool_name, f"Timeout after {self.tool_timeout}s")
        except ToolExecutionError:
            raise  # Re-raise to be caught by handle_request
        except Exception as e:
            logger.error(f"❌ Unexpected error in tool '{tool_name}': {e}")
            raise ToolExecutionError(tool_name, str(e), original_error=e)
    
    # ==========================================
    # UTILITY METHODS
    # ==========================================
    
    def get_openai_schemas(self) -> list:
        """
        Get OpenAI-compatible schemas for all tools.
        
        Convenience method for LLM services.
        
        Returns:
            list: List of OpenAI tool schemas
        """
        return self.registry.get_all_openai_schemas()
    
    def register_tool(self, tool) -> None:
        """
        Register a tool in the registry.
        
        Convenience method.
        
        Args:
            tool: BaseTool instance
        """
        self.registry.register_tool(tool)
    
    def __repr__(self) -> str:
        return f"<MCPServer: {self.server_info.name} v{self.server_info.version}, {self.registry.count()} tools>"