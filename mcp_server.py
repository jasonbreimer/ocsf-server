#!/usr/bin/env python3
"""
OCSF MCP Server
Exposes OCSF schema as MCP tools for AI assistants.
Requires the OCSF server to be running (default: http://localhost:8080).
"""

import os
import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

OCSF_BASE_URL = os.environ.get("OCSF_BASE_URL", "http://localhost:8080")

# ---------------------------------------------------------------------------
# Cache — fetch each endpoint once
# ---------------------------------------------------------------------------

_cache: dict = {}


async def fetch(path: str) -> dict | list:
    if path not in _cache:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{OCSF_BASE_URL}{path}")
            resp.raise_for_status()
            _cache[path] = resp.json()
    return _cache[path]


async def get_dictionary() -> dict:
    data = await fetch("/api/dictionary")
    return data.get("attributes", data)


async def get_classes() -> list:
    return await fetch("/api/classes")


async def get_objects() -> list:
    return await fetch("/api/objects")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

app = Server("ocsf-mcp")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_attributes",
            description=(
                "Search OCSF schema attributes by name, caption, or description. "
                "Returns matching attributes with type and description. "
                "Use this to discover what fields are available in OCSF events."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against attribute names, captions, and descriptions.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 20, max: 100).",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_classes",
            description=(
                "Search OCSF event classes by name, caption, category, or description. "
                "Event classes define the structure of security events like authentication, "
                "network activity, process activity, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against class names, captions, categories, and descriptions.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 20, max: 100).",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_class",
            description=(
                "Get the full definition of a specific OCSF event class by name or UID. "
                "Returns all attributes, profiles, category, and description. "
                "Use search_classes first to find the class name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Class name (e.g. 'network_activity') or numeric UID (e.g. '4001').",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="search_objects",
            description=(
                "Search OCSF objects by name, caption, or description. "
                "Objects are reusable data structures used within event classes, "
                "like 'process', 'user', 'network_endpoint', 'file', etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against object names, captions, and descriptions.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 20, max: 100).",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_object",
            description=(
                "Get the full definition of a specific OCSF object by name. "
                "Returns all attributes, profiles, and description. "
                "Use search_objects first to find the object name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Object name (e.g. 'process', 'user', 'network_endpoint').",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="list_categories",
            description=(
                "List all OCSF event categories. "
                "Categories group related event classes together, e.g. "
                "System Activity, Network Activity, Identity & Access Management, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="get_schema_version",
            description="Get the current OCSF schema version loaded on the server.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _format_error(msg: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=f"Error: {msg}")]


def _truncate(text: str, max_len: int = 200) -> str:
    return text[:max_len - 3] + "..." if len(text) > max_len else text


async def handle_search_attributes(arguments: dict) -> list[types.TextContent]:
    query = arguments.get("query", "").lower().strip()
    limit = min(int(arguments.get("limit", 20)), 100)
    if not query:
        return _format_error("query cannot be empty")

    dictionary = await get_dictionary()
    matches = []
    for attr_name, attr in dictionary.items():
        if (query in attr_name.lower()
                or query in str(attr.get("caption", "")).lower()
                or query in str(attr.get("description", "")).lower()):
            matches.append({
                "name": attr_name,
                "caption": attr.get("caption", ""),
                "type": attr.get("type", ""),
                "type_name": attr.get("type_name", ""),
                "is_array": attr.get("is_array", False),
                "description": attr.get("description", ""),
            })

    matches = matches[:limit]
    if not matches:
        return [types.TextContent(type="text", text=f"No attributes found matching '{query}'.")]

    lines = [f"Found {len(matches)} attribute(s) matching '{query}':\n"]
    for m in matches:
        array_marker = "[]" if m["is_array"] else ""
        type_label = m["type_name"] or m["type"]
        lines.append(f"**{m['name']}** ({type_label}{array_marker})")
        if m["caption"]:
            lines.append(f"  Caption: {m['caption']}")
        if m["description"]:
            lines.append(f"  Description: {_truncate(m['description'])}")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_search_classes(arguments: dict) -> list[types.TextContent]:
    query = arguments.get("query", "").lower().strip()
    limit = min(int(arguments.get("limit", 20)), 100)
    if not query:
        return _format_error("query cannot be empty")

    classes = await get_classes()
    matches = []
    for cls in classes:
        if (query in cls.get("name", "").lower()
                or query in cls.get("caption", "").lower()
                or query in cls.get("category", "").lower()
                or query in cls.get("category_name", "").lower()
                or query in cls.get("description", "").lower()):
            matches.append(cls)

    matches = matches[:limit]
    if not matches:
        return [types.TextContent(type="text", text=f"No classes found matching '{query}'.")]

    lines = [f"Found {len(matches)} class(es) matching '{query}':\n"]
    for cls in matches:
        lines.append(f"**{cls['name']}** (UID: {cls.get('uid', 'N/A')})")
        lines.append(f"  Caption: {cls.get('caption', '')}")
        lines.append(f"  Category: {cls.get('category_name', cls.get('category', ''))}")
        if cls.get("description"):
            lines.append(f"  Description: {_truncate(cls['description'])}")
        if cls.get("profiles"):
            lines.append(f"  Profiles: {', '.join(cls['profiles'])}")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_get_class(arguments: dict) -> list[types.TextContent]:
    name = arguments.get("name", "").strip()
    if not name:
        return _format_error("name cannot be empty")

    # Try fetching by name or UID
    try:
        data = await fetch(f"/api/classes/{name}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return _format_error(f"Class '{name}' not found. Use search_classes to find the correct name.")
        raise

    lines = [f"# {data.get('caption', data.get('name', name))}\n"]
    lines.append(f"**Name:** {data.get('name', '')}")
    lines.append(f"**UID:** {data.get('uid', 'N/A')}")
    lines.append(f"**Category:** {data.get('category_name', data.get('category', ''))}")
    if data.get("extends"):
        lines.append(f"**Extends:** {data['extends']}")
    if data.get("description"):
        lines.append(f"\n**Description:** {data['description']}\n")
    if data.get("profiles"):
        lines.append(f"**Profiles:** {', '.join(data['profiles'])}\n")

    # Attributes
    attrs = data.get("attributes", {})
    if attrs:
        lines.append(f"**Attributes** ({len(attrs)} total):\n")
        for attr_name, attr in sorted(attrs.items()):
            req = " *(required)*" if attr.get("requirement") == "required" else ""
            rec = " *(recommended)*" if attr.get("requirement") == "recommended" else ""
            array_marker = "[]" if attr.get("is_array") else ""
            type_label = attr.get("type_name") or attr.get("type", "")
            lines.append(f"  - **{attr_name}** ({type_label}{array_marker}){req}{rec}")
            if attr.get("description"):
                lines.append(f"    {_truncate(attr['description'], 150)}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_search_objects(arguments: dict) -> list[types.TextContent]:
    query = arguments.get("query", "").lower().strip()
    limit = min(int(arguments.get("limit", 20)), 100)
    if not query:
        return _format_error("query cannot be empty")

    objects = await get_objects()
    matches = []
    for obj in objects:
        if (query in obj.get("name", "").lower()
                or query in obj.get("caption", "").lower()
                or query in obj.get("description", "").lower()):
            matches.append(obj)

    matches = matches[:limit]
    if not matches:
        return [types.TextContent(type="text", text=f"No objects found matching '{query}'.")]

    lines = [f"Found {len(matches)} object(s) matching '{query}':\n"]
    for obj in matches:
        lines.append(f"**{obj['name']}**")
        if obj.get("caption"):
            lines.append(f"  Caption: {obj['caption']}")
        if obj.get("description"):
            lines.append(f"  Description: {_truncate(obj['description'])}")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_get_object(arguments: dict) -> list[types.TextContent]:
    name = arguments.get("name", "").strip()
    if not name:
        return _format_error("name cannot be empty")

    try:
        data = await fetch(f"/api/objects/{name}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return _format_error(f"Object '{name}' not found. Use search_objects to find the correct name.")
        raise

    lines = [f"# {data.get('caption', data.get('name', name))}\n"]
    lines.append(f"**Name:** {data.get('name', '')}")
    if data.get("extends"):
        lines.append(f"**Extends:** {data['extends']}")
    if data.get("description"):
        lines.append(f"\n**Description:** {data['description']}\n")
    if data.get("profiles"):
        lines.append(f"**Profiles:** {', '.join(data['profiles'])}\n")

    attrs = data.get("attributes", {})
    if attrs:
        lines.append(f"**Attributes** ({len(attrs)} total):\n")
        for attr_name, attr in sorted(attrs.items()):
            req = " *(required)*" if attr.get("requirement") == "required" else ""
            rec = " *(recommended)*" if attr.get("requirement") == "recommended" else ""
            array_marker = "[]" if attr.get("is_array") else ""
            type_label = attr.get("type_name") or attr.get("type", "")
            lines.append(f"  - **{attr_name}** ({type_label}{array_marker}){req}{rec}")
            if attr.get("description"):
                lines.append(f"    {_truncate(attr['description'], 150)}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_list_categories(arguments: dict) -> list[types.TextContent]:
    data = await fetch("/api/categories")
    # categories can be a dict or list depending on server version
    if isinstance(data, dict):
        categories = data.get("attributes", data)
        lines = ["# OCSF Event Categories\n"]
        for cat_id, cat in sorted(categories.items(), key=lambda x: str(x[0])):
            lines.append(f"**{cat.get('caption', cat_id)}** (UID: {cat.get('uid', cat_id)})")
            if cat.get("description"):
                lines.append(f"  {_truncate(cat['description'])}")
            lines.append("")
    else:
        lines = ["# OCSF Event Categories\n"]
        for cat in data:
            lines.append(f"**{cat.get('caption', cat.get('name', ''))}** (UID: {cat.get('uid', 'N/A')})")
            if cat.get("description"):
                lines.append(f"  {_truncate(cat['description'])}")
            lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_get_schema_version(arguments: dict) -> list[types.TextContent]:
    data = await fetch("/api/version")
    if isinstance(data, dict):
        version = data.get("version", str(data))
    else:
        version = str(data)
    return [types.TextContent(type="text", text=f"OCSF Schema Version: {version}")]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

HANDLERS = {
    "search_attributes": handle_search_attributes,
    "search_classes": handle_search_classes,
    "get_class": handle_get_class,
    "search_objects": handle_search_objects,
    "get_object": handle_get_object,
    "list_categories": handle_list_categories,
    "get_schema_version": handle_get_schema_version,
}


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    handler = HANDLERS.get(name)
    if not handler:
        return _format_error(f"Unknown tool: {name}")
    try:
        return await handler(arguments)
    except httpx.ConnectError:
        return _format_error(
            f"Could not connect to OCSF server at {OCSF_BASE_URL}. Is it running?"
        )
    except httpx.HTTPStatusError as e:
        return _format_error(f"HTTP {e.response.status_code} from OCSF server: {e.request.url}")
    except Exception as e:
        return _format_error(f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
