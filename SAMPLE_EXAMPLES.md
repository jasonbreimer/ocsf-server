# Sample Event Examples — Proof of Concept

This branch contains a proof of concept for improving the OCSF sample event generator to produce realistic, meaningful data instead of random words.

## The Problem

The OCSF server has a sample event generator accessible at `/sample/classes/:name` (e.g. `/sample/classes/network_activity`). It generates structurally valid events, but all string values are random words from a frequency list — making the output hard to read and useless for normalization guidance or AI-assisted tooling.

Example of current output:
```json
{
  "ip": "53.15.172.146",
  "hostname": "karma.com",
  "protocol_name": "parking stretch vocabulary",
  "message": "wn britannica bedford"
}
```

## The Solution

Two small changes working together:

**1. Add an optional `"example"` field to schema attributes** (`ocsf-schema/dictionary.json` and object files)

```json
"ip": {
  "caption": "IP Address",
  "description": "The IP address, in either IPv4 or IPv6 format.",
  "type": "ip_t",
  "example": "192.168.1.100"
}
```

**2. One line change in `generator.ex`** — check for `example` before generating random data:

```elixir
defp generate_data(_name, _type, %{example: example}), do: example
```

That's it. No new schema version, no compiler changes, no new tooling concepts.

## How It Works

```
Author adds "example" to dictionary.json or an object file
        ↓
ocsf-schema-compiler passes it through unchanged (verified)
        ↓
Compiled schema JSON contains the "example" field
        ↓
generator.ex checks for "example" before generating random data
        ↓
/sample/classes/network_activity returns realistic events
```

## Example vs. Random Output

Before:
```json
{
  "ip": "53.15.172.146",
  "hostname": "karma.com",
  "protocol_name": "parking stretch vocabulary",
  "cipher": "pics measurements nasdaq",
  "provider": "rd bears bear",
  "message": "wn britannica bedford",
  "vendor_name": "maker in verse"
}
```

After:
```json
{
  "ip": "192.168.1.100",
  "hostname": "workstation-42.corp.example.com",
  "protocol_name": "TCP",
  "cipher": "TLS_AES_256_GCM_SHA384",
  "provider": "AWS",
  "message": "Outbound HTTPS connection to external API endpoint",
  "vendor_name": "Dell Inc."
}
```

## Design Decisions

### Where examples live

- **Dictionary level** (`dictionary.json`) — one example per attribute, used as a global default
- **Object/class level** (e.g. `objects/process.json`) — context-specific override, wins over dictionary

This mirrors how OCSF already handles attribute overrides (descriptions, requirements, etc.). The compiler's existing `deep_merge` logic handles the override automatically — no compiler changes needed.

### The `name` problem

`name` is a generic attribute reused across hundreds of objects with very different meanings (`device.name`, `process.name`, `file.name`, `user.name`, etc.). A single dictionary-level example will appear everywhere. The fix is to add context-specific `example` overrides in the relevant object files:

```json
// objects/process.json
"attributes": {
  "name": {
    "description": "The name of the process.",
    "example": "chrome.exe"
  }
}

// objects/file.json
"attributes": {
  "name": {
    "description": "The filename.",
    "example": "invoice.pdf"
  }
}
```

### Backwards compatibility

Fully backwards compatible. Attributes without `"example"` continue to use random generation as before. No breaking changes to any existing API or schema contract.

## Testing Locally

### Prerequisites
- Python 3.14+
- Docker Desktop

### Setup

```bash
# Clone this branch
git clone -b samples https://github.com/jasonbreimer/ocsf-server.git
cd ocsf-server

# Clone the schema
git clone https://github.com/ocsf/ocsf-schema.git

# Set up the compiler
mkdir compiled-schema
python3.14 -m venv compiled-schema/.venv
source compiled-schema/.venv/bin/activate
pip install ocsf-schema-compiler
```

### Add example values to the schema

Edit `ocsf-schema/dictionary.json` and add `"example"` fields to attributes. For example:

```json
"ip": {
  "caption": "IP Address",
  "description": "The IP address, in either IPv4 or IPv6 format.",
  "type": "ip_t",
  "example": "192.168.1.100"
}
```

### Compile and run

```bash
# Compile the schema
ocsf-schema-compiler ocsf-schema -b > compiled-schema/ocsf-schema-browser.json

# Build the Docker image
docker build -t ocsf-server-samples .

# Run on port 8081 (to avoid conflicting with other instances)
docker run -d \
  --name ocsf-server-samples \
  --volume ~/path/to/ocsf-server/compiled-schema:/app/schemas \
  -e SCHEMA_FILE="/app/schemas/ocsf-schema-browser.json" \
  -p 8081:8080 \
  ocsf-server-samples
```

### Validate

Open http://localhost:8081/classes/network_activity and click **Sample**. You should see realistic values for any attributes you added `"example"` to.

Or via API:
```bash
curl http://localhost:8081/sample/classes/network_activity | python3 -m json.tool
```

## Relationship to Other Work

- **ocsf-server PR** — the `generator.ex` change in this branch. Small, self-contained, backwards compatible.
- **ocsf-schema PR** — adds `"example"` fields to dictionary attributes. Can start with the most common attributes and expand incrementally.
- **MCP server** — with realistic sample data, the `/sample` endpoint becomes significantly more useful for AI-assisted normalization workflows. See the [OCSF MCP Server](https://github.com/jasonbreimer/ocsf-server/tree/MCP-Server) branch.

## Open Questions for the OCSF Community

1. Should `"example"` be a formally recognized field in the schema spec, or treated as an advisory convention?
2. If formal, should the compiler validate that example values match the declared type (e.g. reject a non-IP string on an `ip_t` attribute)?
3. Should the schema browser UI surface `"example"` values alongside descriptions in the attribute table?
4. Who is responsible for maintaining examples as the schema evolves?
