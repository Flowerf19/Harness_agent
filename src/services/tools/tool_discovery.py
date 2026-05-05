"""
Tool Discovery - Auto-discovery system for tools.

Convention-based discovery:
- Scan a directory for tool files
- Auto-import and instantiate tools
- Register tools in registry

Design Philosophy:
- Plug-and-play: Add new tool by creating file
- Convention over configuration: Follow naming convention
- Zero manual registration needed

Convention:
- Directory: src/services/tools/implementations/
- Filename pattern: *_tool.py (e.g., search_memory_tool.py)
- Class pattern: Must inherit from BaseTool
- Export: Each file exports one or more tool classes

Example:
    # implementations/search_memory_tool.py
    class SearchMemoryTool(BaseTool):
        ...
    
    # Auto-discovered and registered on startup
"""

import logging
import os
import importlib
import inspect
from pathlib import Path
from typing import List, Type, Optional, Dict, Any

from src.services.tools.base_tool import BaseTool
from src.services.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolDiscovery:
    """
    Auto-discovery system for tools.
    
    Scans a directory for tool files and auto-registers them.
    
    Attributes:
        tools_dir: Directory to scan for tools
        registry: ToolRegistry to register discovered tools
    
    Example:
        discovery = ToolDiscovery("src/services/tools/implementations", registry)
        tools = discovery.discover_tools()
        
        # All tools are now registered in registry
        print(f"Discovered {len(tools)} tools")
    """
    
    # Filename pattern for tool files
    TOOL_FILE_PATTERN = "*_tool.py"
    
    # Base class that tools must inherit from
    BASE_TOOL_CLASS = BaseTool
    
    def __init__(
        self,
        tools_dir: str,
        registry: ToolRegistry,
        dependencies: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize tool discovery.
        
        Args:
            tools_dir: Directory path to scan for tools
            registry: ToolRegistry to register discovered tools
            dependencies: Dict of dependencies to inject into tools
                         (e.g., {"episodic_manager": ..., "core_manager": ...})
        """
        self.tools_dir = tools_dir
        self.registry = registry
        self.dependencies = dependencies or {}
        
        logger.debug(f"ToolDiscovery initialized: dir={tools_dir}")
    
    # ==========================================
    # DISCOVERY METHODS
    # ==========================================
    
    def discover_tools(self) -> List[BaseTool]:
        """
        Scan directory and discover all tools.
        
        Returns:
            List[BaseTool]: List of discovered and registered tools
        """
        discovered_tools = []
        
        # Ensure directory exists
        tools_path = Path(self.tools_dir)
        if not tools_path.exists():
            logger.warning(f"Tools directory does not exist: {self.tools_dir}")
            return discovered_tools
        
        # Find all tool files
        tool_files = list(tools_path.glob(self.TOOL_FILE_PATTERN))
        logger.debug(f"Found {len(tool_files)} potential tool files in {self.tools_dir}")
        
        # Process each file
        for tool_file in tool_files:
            try:
                tools = self._discover_tools_from_file(tool_file)
                discovered_tools.extend(tools)
            except Exception as e:
                logger.error(f"Failed to discover tools from {tool_file}: {e}")
                continue
        
        logger.debug(f"✅ Discovered {len(discovered_tools)} tools total")
        return discovered_tools
    
    def _discover_tools_from_file(self, tool_file: Path) -> List[BaseTool]:
        """
        Discover tools from a single file.
        
        Args:
            tool_file: Path to tool file
            
        Returns:
            List[BaseTool]: List of discovered tools from this file
        """
        discovered_tools = []
        
        # Convert file path to module path
        # e.g., src/services/tools/implementations/search_memory_tool.py
        # -> src.services.tools.implementations.search_memory_tool
        module_path = self._file_to_module_path(tool_file)
        
        logger.debug(f"Importing module: {module_path}")
        
        # Import module
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            return discovered_tools
        
        # Find all BaseTool subclasses in module
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip imported classes (must be defined in this module)
            if obj.__module__ != module_path:
                continue
            
            # Check if it's a BaseTool subclass (but not BaseTool itself)
            if inspect.isclass(obj) and issubclass(obj, self.BASE_TOOL_CLASS) and obj != self.BASE_TOOL_CLASS:
                try:
                    # Instantiate tool with dependencies
                    tool_instance = self._instantiate_tool(obj)
                    
                    # Register in registry
                    self.registry.register_tool(tool_instance)
                    
                    discovered_tools.append(tool_instance)
                    logger.debug(f"  ✅ Discovered: {obj.__name__} -> {tool_instance.name}")
                    
                except Exception as e:
                    logger.error(f"Failed to instantiate tool {obj.__name__}: {e}")
                    continue
        
        return discovered_tools
    
    def _file_to_module_path(self, file_path: Path) -> str:
        """
        Convert file path to Python module path.
        
        Args:
            file_path: Path to .py file
            
        Returns:
            str: Module import path
        """
        # Get relative path from project root
        # Assuming project root contains 'src' directory
        parts = file_path.parts
        
        # Find 'src' in path and build module path from there
        if 'src' in parts:
            src_index = parts.index('src')
            module_parts = parts[src_index:]
        else:
            # If no 'src', use all parts
            module_parts = parts
        
        # Remove .py extension from last part
        module_parts = list(module_parts)
        module_parts[-1] = module_parts[-1].replace('.py', '')
        
        return '.'.join(module_parts)
    
    def _instantiate_tool(self, tool_class: Type[BaseTool]) -> BaseTool:
        """
        Instantiate a tool class with dependencies.
        
        Args:
            tool_class: Tool class to instantiate
            
        Returns:
            BaseTool: Instantiated tool
            
        Raises:
            Exception: If instantiation fails
        """
        # Get constructor signature
        sig = inspect.signature(tool_class.__init__)
        
        # Build kwargs from available dependencies
        kwargs = {}
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            # Check if we have this dependency
            if param_name in self.dependencies:
                kwargs[param_name] = self.dependencies[param_name]
            elif param.default != inspect.Parameter.empty:
                # Has default value, skip
                continue
            else:
                # Required parameter not available
                logger.warning(f"Missing required dependency '{param_name}' for {tool_class.__name__}")
                # Try to instantiate without it (might fail)
        
        # Instantiate tool
        return tool_class(**kwargs)
    
    # ==========================================
    # UTILITY METHODS
    # ==========================================
    
    def get_tool_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all discovered tools.
        
        Returns:
            List[Dict]: List of tool info dicts
        """
        tools = self.registry.list_tools()
        return [
            {
                "name": tool.name,
                "class": tool.__class__.__name__,
                "description": tool.description[:50] + "..." if len(tool.description) > 50 else tool.description,
            }
            for tool in tools
        ]
    
    def __repr__(self) -> str:
        return f"<ToolDiscovery: dir={self.tools_dir}, tools={self.registry.count()}>"


# ==========================================
# CONVENIENCE FUNCTION
# ==========================================

def discover_and_register_tools(
    tools_dir: str,
    registry: ToolRegistry,
    dependencies: Optional[Dict[str, Any]] = None,
) -> List[BaseTool]:
    """
    Convenience function to discover and register all tools.
    
    Args:
        tools_dir: Directory to scan
        registry: Registry to register tools
        dependencies: Dependencies to inject
        
    Returns:
        List[BaseTool]: List of discovered tools
    """
    discovery = ToolDiscovery(tools_dir, registry, dependencies)
    return discovery.discover_tools()