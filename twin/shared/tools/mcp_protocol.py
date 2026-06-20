"""
MCP Protocol - Model Context Protocol implementation.

Theo chuẩn JSON-RPC 2.0 specification:
https://www.jsonrpc.org/specification

MCP (Model Context Protocol) được thiết kế bởi Anthropic:
https://modelcontextprotocol.io/

Protocol Structure:
- Request: Client gửi request đến Server
- Response: Server trả về response (success hoặc error)
- Notification: One-way message (không cần response)

Endpoints:
- tools/list: Lấy danh sách tools
- tools/call: Thực thi tool
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, TYPE_CHECKING
from enum import Enum
import json
import uuid

if TYPE_CHECKING:
    from twin.shared.tools.registry.base import BaseTool


# ==========================================
# JSON-RPC 2.0 CONSTANTS
# ==========================================

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"

# JSON-RPC Error Codes (Theo spec)
class JSONRPCErrorCodes(Enum):
    """Standard JSON-RPC 2.0 error codes."""
    
    PARSE_ERROR = -32700       # Invalid JSON
    INVALID_REQUEST = -32600   # Invalid Request object
    METHOD_NOT_FOUND = -32601  # Method not found
    INVALID_PARAMS = -32602    # Invalid method parameters
    INTERNAL_ERROR = -32603    # Internal JSON-RPC error
    
    # Server errors (implementation-defined, -32000 to -32099)
    TOOL_EXECUTION_ERROR = -32000
    TOOL_NOT_FOUND = -32001
    TOOL_TIMEOUT = -32002


# ==========================================
# MCP REQUEST/RESPONSE MODELS
# ==========================================

@dataclass
class MCPRequest:
    """
    JSON-RPC 2.0 Request.
    
    Attributes:
        jsonrpc: Version string ("2.0")
        method: Method name (VD: "tools/list", "tools/call")
        params: Parameters dict (optional)
        id: Request ID for correlation (optional for notifications)
    """
    
    method: str  # Required - no default
    jsonrpc: str = JSONRPC_VERSION
    params: Optional[Dict[str, Any]] = None
    id: Optional[str] = None
    
    def __post_init__(self):
        # Auto-generate ID if not provided (for requests, not notifications)
        if (
            self.id is None
            and self.method != "initialize"
            and not self.method.startswith("notifications/")
        ):
            self.id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "jsonrpc": self.jsonrpc,
            "method": self.method
        }
        if self.params is not None:
            result["params"] = self.params
        if self.id is not None:
            result["id"] = self.id
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPRequest":
        """Parse from dict."""
        return cls(
            jsonrpc=data.get("jsonrpc", JSONRPC_VERSION),
            method=data.get("method", ""),
            params=data.get("params"),
            id=data.get("id")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "MCPRequest":
        """Parse from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class MCPError:
    """
    JSON-RPC 2.0 Error object.
    
    Attributes:
        code: Error code (from JSONRPCErrorCodes or custom)
        message: Error message
        data: Additional error data (optional)
    """
    
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "code": self.code,
            "message": self.message
        }
        if self.data is not None:
            result["data"] = self.data
        return result
    
    @classmethod
    def method_not_found(cls, method: str) -> "MCPError":
        """Create error for unknown method."""
        return cls(
            code=JSONRPCErrorCodes.METHOD_NOT_FOUND.value,
            message=f"Method not found: '{method}'"
        )
    
    @classmethod
    def invalid_params(cls, message: str) -> "MCPError":
        """Create error for invalid parameters."""
        return cls(
            code=JSONRPCErrorCodes.INVALID_PARAMS.value,
            message=message
        )
    
    @classmethod
    def internal_error(cls, message: str, data: Optional[Dict] = None) -> "MCPError":
        """Create error for internal server error."""
        return cls(
            code=JSONRPCErrorCodes.INTERNAL_ERROR.value,
            message=message,
            data=data
        )
    
    @classmethod
    def tool_not_found(cls, tool_name: str) -> "MCPError":
        """Create error for unknown tool."""
        return cls(
            code=JSONRPCErrorCodes.TOOL_NOT_FOUND.value,
            message=f"Tool not found: '{tool_name}'"
        )
    
    @classmethod
    def tool_execution_error(cls, tool_name: str, error_message: str) -> "MCPError":
        """Create error for tool execution failure."""
        return cls(
            code=JSONRPCErrorCodes.TOOL_EXECUTION_ERROR.value,
            message=f"Tool execution failed: '{tool_name}'",
            data={"tool": tool_name, "error": error_message}
        )
    
    @classmethod
    def tool_timeout(cls, tool_name: str, timeout_seconds: int) -> "MCPError":
        """Create error for tool timeout."""
        return cls(
            code=JSONRPCErrorCodes.TOOL_TIMEOUT.value,
            message=f"Tool '{tool_name}' timed out after {timeout_seconds}s",
            data={"tool": tool_name, "timeout": timeout_seconds}
        )


@dataclass
class MCPResponse:
    """
    JSON-RPC 2.0 Response.
    
    Attributes:
        jsonrpc: Version string ("2.0")
        result: Result data (for success responses)
        error: Error object (for error responses)
        id: Request ID (must match request.id)
    """
    
    jsonrpc: str = JSONRPC_VERSION
    result: Optional[Dict[str, Any]] = None
    error: Optional[MCPError] = None
    id: Optional[str] = None
    
    def is_success(self) -> bool:
        """Check if response is successful."""
        return self.error is None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "jsonrpc": self.jsonrpc,
            "id": self.id
        }
        if self.error is not None:
            result["error"] = self.error.to_dict()
        else:
            result["result"] = self.result or {}
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def success(cls, result: Dict[str, Any], request_id: Optional[str] = None) -> "MCPResponse":
        """Create success response."""
        return cls(
            jsonrpc=JSONRPC_VERSION,
            result=result,
            id=request_id
        )
    
    @classmethod
    def create_error(cls, mcp_error: MCPError, request_id: Optional[str] = None) -> "MCPResponse":
        """Create error response."""
        return cls(
            jsonrpc=JSONRPC_VERSION,
            error=mcp_error,
            id=request_id
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPResponse":
        """Parse from dict."""
        error_data = data.get("error")
        error_obj = None
        if error_data:
            error_obj = MCPError(
                code=error_data.get("code"),
                message=error_data.get("message"),
                data=error_data.get("data")
            )
        
        return cls(
            jsonrpc=data.get("jsonrpc", JSONRPC_VERSION),
            result=data.get("result"),
            error=error_obj,
            id=data.get("id")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "MCPResponse":
        """Parse from JSON string."""
        return cls.from_dict(json.loads(json_str))


# ==========================================
# MCP TOOL DEFINITION MODEL
# ==========================================

@dataclass
class ToolDefinition:
    """
    MCP Tool Definition.
    
    Theo MCP spec, mỗi tool có:
    - name: Tên định danh
    - description: Mô tả cho LLM
    - inputSchema: JSON Schema của parameters
    
    Attributes:
        name: Tool name
        description: Tool description
        inputSchema: JSON Schema for input parameters
    """
    
    name: str
    description: str
    inputSchema: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP format dict."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.inputSchema
            }
        }
    
    @classmethod
    def from_base_tool(cls, tool: "BaseTool") -> "ToolDefinition":
        """Create from BaseTool instance."""
        return cls(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.parameters_schema
        )


# ==========================================
# MCP METHOD CONSTANTS
# ==========================================

class MCPMethods:
    """MCP method names."""
    
    # Core methods
    INITIALIZE = "initialize"
    INITIALIZED = "notifications/initialized"
    PING = "ping"
    
    # Tools methods
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    
    # Resources methods (future)
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    
    # Prompts methods (future)
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"


# ==========================================
# MCP CAPABILITIES
# ==========================================

@dataclass
class MCPCapabilities:
    """
    MCP Server Capabilities.
    
    Declares what features the server supports.
    
    Attributes:
        tools: Whether server supports tools
        resources: Whether server supports resources
        prompts: Whether server supports prompts
    """
    
    tools: bool = True
    resources: bool = False
    prompts: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to capabilities dict."""
        return {
            "tools": {"supported": self.tools} if self.tools else None,
            "resources": {"supported": self.resources} if self.resources else None,
            "prompts": {"supported": self.prompts} if self.prompts else None,
        }


# ==========================================
# MCP SERVER INFO
# ==========================================

@dataclass
class MCPServerInfo:
    """
    MCP Server Information.
    
    Returned during initialize handshake.
    
    Attributes:
        name: Server name
        version: Server version
        capabilities: Server capabilities
    """
    
    name: str = "discord-bot-mcp-server"
    version: str = "1.0.0"
    capabilities: MCPCapabilities = field(default_factory=MCPCapabilities)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to server info dict."""
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": self.capabilities.to_dict()
        }
