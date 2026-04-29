# OCSF MCP Server — Proof of Concept

An MCP (Model Context Protocol) server that exposes the [Open Cybersecurity Schema Framework (OCSF)](https://ocsf.io) schema as tools for AI assistants. The goal is to accelerate and improve the accuracy of OCSF normalization work — a process that is currently manual, slow, and error-prone.

## Why This Exists

Normalizing security events to OCSF requires deep familiarity with hundreds of attributes, dozens of event classes, and dozens of reusable objects. Doing this manually means:

- Constantly context-switching between the schema browser and your work
- Missing attributes you didn't know existed
- Inconsistent mappings across team members
- No way to validate your thinking quickly

This MCP server gives an AI assistant (like Claude) live, structured access to the OCSF schema. You can describe a raw event and ask the assistant to help you map it to OCSF — it will look up the right classes, attributes, and objects in real time and guide you through normalization accurately and quickly.

---

## Architecture

```
┌─────────────────────┐        ┌─────────────────────┐        ┌─────────────────────┐
│                     │  MCP   │                     │  HTTP  │                     │
│   AI Assistant      │◄──────►│   ocsf MCP Server   │◄──────►│   OCSF Server       │
│   (Claude Desktop)  │        │   (mcp_server.py)   │        │   (Docker / Elixir) │
│                     │        │                     │        │   localhost:8080     │
└─────────────────────┘        └─────────────────────┘        └─────────────────────┘
```

The MCP server is a lightweight Python sidecar that sits between the AI assistant and the OCSF server. It translates natural language tool calls into OCSF API requests and returns structured schema data.

---

## Available Tools

| Tool | Description |
|------|-------------|
| `search_attributes` | Search the OCSF attribute dictionary by name, caption, or description |
| `search_classes` | Search event classes (network_activity, auth, process_activity, etc.) |
| `get_class` | Get the full definition of an event class including all attributes |
| `search_objects` | Search reusable objects (process, user, file, network_endpoint, etc.) |
| `get_object` | Get the full definition of an object including all attributes |
| `list_categories` | List all OCSF event categories |
| `get_schema_version` | Get the schema version currently loaded on the server |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)
- [Python 3.14+](https://www.python.org/) (required for the schema compiler)
- [Node.js](https://nodejs.org/) (for MCP Inspector, optional but recommended)

---

## Setup

### 1. Clone the repos

```bash
mkdir -p ~/ocsf && cd ~/ocsf
git clone https://github.com/ocsf/ocsf-server.git
git clone https://github.com/ocsf/ocsf-schema.git
```

### 2. Compile the schema

```bash
mkdir -p ~/ocsf/compiled
cd ~/ocsf/compiled
python3.14 -m venv .venv
source .venv/bin/activate
pip install ocsf-schema-compiler
ocsf-schema-compiler ~/ocsf/ocsf-schema -b > ocsf-schema-browser.json
echo "Compiled: $(du -sh ocsf-schema-browser.json)"
```

> The compiled schema is ~46MB and includes browser mode metadata required by the server.

### 3. Build and run the OCSF server

```bash
cd ~/ocsf/ocsf-server
docker build -t ocsf-server .

docker run -d \
  --name ocsf-server \
  --volume ~/ocsf/compiled:/app/schemas \
  -e SCHEMA_FILE="/app/schemas/ocsf-schema-browser.json" \
  -p 8080:8080 \
  ocsf-server
```

Verify it's running:
```bash
curl http://localhost:8080/api/version
```

### 4. Set up the MCP server

```bash
mkdir -p ~/ocsf/ocsf-mcp && cd ~/ocsf/ocsf-mcp
# Copy mcp_server.py, requirements.txt, and run.sh here
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Testing

### Option A: MCP Inspector (recommended for demos)

The MCP Inspector is the official MCP debugging tool. It provides a web UI to call tools interactively without needing an AI assistant.

```bash
npx @modelcontextprotocol/inspector ~/ocsf/ocsf-mcp/run.sh
```

Then open **http://localhost:5173** in your browser.

From the inspector you can:
- See all available tools and their input schemas
- Call any tool with custom arguments
- Inspect raw request/response JSON

**Suggested test queries:**
- `search_attributes` → query: `"severity"`
- `search_classes` → query: `"network"`
- `get_class` → name: `"network_activity"`
- `search_objects` → query: `"process"`
- `get_object` → name: `"process"`
- `list_categories` → (no arguments)

### Option B: Claude Desktop

Add the MCP server to your `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ocsf": {
      "command": "/path/to/ocsf-mcp/.venv/bin/python3",
      "args": ["/path/to/ocsf-mcp/mcp_server.py"],
      "env": {
        "OCSF_BASE_URL": "http://localhost:8080"
      }
    }
  }
}
```

Restart Claude Desktop, then try prompts like:

> *"I have a Windows process creation event with fields: pid, parent_pid, image_path, command_line, user, timestamp. Help me map this to OCSF."*

> *"What OCSF attributes should I use to represent a network connection with source IP, destination IP, port, and protocol?"*

> *"What's the difference between the process_activity and process_query OCSF event classes?"*

### Option C: Command line (raw JSON-RPC)

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_attributes","arguments":{"query":"severity"}}}' | \
  ~/ocsf/ocsf-mcp/run.sh | python3 -m json.tool
```

---

## Example Normalization Workflow

Here's what AI-assisted normalization looks like in practice:

**You:** *"I'm normalizing a Palo Alto firewall log. It has: src_ip, dst_ip, src_port, dst_port, protocol, action, bytes_sent, bytes_received, session_id. What OCSF class should I use and how do I map these fields?"*

**Claude (with OCSF MCP):**
1. Calls `search_classes` → finds `network_activity` (UID 4001)
2. Calls `get_class` → returns full attribute list
3. Maps your fields: `src_ip` → `src_endpoint.ip`, `dst_ip` → `dst_endpoint.ip`, `action` → `activity_id` + `action`, etc.
4. Flags fields you might have missed: `severity_id`, `metadata`, `type_uid`
5. Suggests the `network_proxy` profile if applicable

This workflow that previously took 30–60 minutes of manual schema browsing now takes seconds.

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OCSF_BASE_URL` | `http://localhost:8080` | URL of the running OCSF server |

---

## Stopping the OCSF Server

```bash
docker stop ocsf-server
docker rm ocsf-server
```

To restart:
```bash
docker start ocsf-server
```

---

## Roadmap

- [ ] `validate_event` tool — validate a JSON event against the OCSF schema
- [ ] `suggest_class` tool — given a description of an event, suggest the best matching class
- [ ] `diff_versions` tool — compare attributes between schema versions
- [ ] Feature flag to disable MCP endpoint for hosted deployments
- [ ] Contribute upstream to the OCSF project

---

## Notes

- The OCSF server must be running for the MCP server to function
- Schema data is cached in memory after the first request — restart the MCP server to pick up schema changes
- This POC targets the local development use case; hosting for production is out of scope for now
