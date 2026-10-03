# Manual Home Assistant Docker Test Guide

This guide provides the steps to complete the Home Assistant Docker integration test manually, which requires Docker image pulling that may be blocked in sandboxed environments.

## Prerequisites

- Docker Desktop installed and running
- Home Assistant image: `ghcr.io/home-assistant/home-assistant:stable`
- Python 3.14+ image: `python:3.14-slim`
- Repository .env file with router credentials

## Setup

```bash
# Clean any existing test containers
docker rm -f ha-vantiva-test 2>/dev/null || true
rm -rf /tmp/ha-vantiva-config

# Prepare HA configuration directory
mkdir -p /tmp/ha-vantiva-config/custom_components
cp -r custom_components/vantiva /tmp/ha-vantiva-config/custom_components/

# Start Home Assistant
docker run -d \
  --name ha-vantiva-test \
  -p 8123:8123 \
  -v /tmp/ha-vantiva-config:/config \
  -e TZ=America/Vancouver \
  ghcr.io/home-assistant/home-assistant:stable

# Wait for HA to start (1-3 minutes)
echo "Waiting for Home Assistant..."
for i in {1..60}; do
  if curl -sf http://localhost:8123/api/onboarding >/dev/null 2>&1; then
    echo "✓ Home Assistant is ready!"
    break
  fi
  echo "Attempt $i/60..."
  sleep 5
done
```

## Onboarding and Configuration

Create and run the onboarding script:

```bash
# Create onboarding script
cat > /tmp/ha_onboard.py << 'EOFSCRIPT'
#!/usr/bin/env python3
"""Complete HA onboarding and configure Vantiva integration."""
import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


def request_json(url, method="GET", data=None, headers=None):
    """Make HTTP request and return JSON."""
    if headers is None:
        headers = {}
    
    if data is not None:
        if isinstance(data, dict):
            data = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        elif isinstance(data, str):
            data = data.encode('utf-8')
    
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=30) as response:
        response_data = response.read().decode('utf-8')
        return json.loads(response_data) if response_data else {}


def main():
    base_url = "http://localhost:8123"
    
    # Get credentials from environment
    vantiva_host = os.getenv("VANTIVA_HOST")
    vantiva_user = os.getenv("VANTIVA_USERNAME")
    vantiva_pass = os.getenv("VANTIVA_PASSWORD")
    
    if not all([vantiva_host, vantiva_user, vantiva_pass]):
        print("Error: Missing VANTIVA_* environment variables")
        return 1
    
    # Create user
    print("Creating user...")
    user_response = request_json(
        f"{base_url}/api/onboarding/users",
        method="POST",
        data={
            "client_id": f"{base_url}/",
            "name": "Test",
            "username": "test",
            "password": "test-password-12345",
            "language": "en"
        }
    )
    auth_code = user_response["auth_code"]
    print(f"✓ User created")
    
    # Get token
    print("Getting access token...")
    token_response = request_json(
        f"{base_url}/auth/token",
        method="POST",
        data=urlencode({
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": f"{base_url}/"
        }),
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    access_token = token_response["access_token"]
    auth_header = {"Authorization": f"Bearer {access_token}"}
    print(f"✓ Token obtained")
    
    # Complete onboarding
    print("Completing onboarding...")
    request_json(f"{base_url}/api/onboarding/core_config", "POST", {}, auth_header)
    request_json(f"{base_url}/api/onboarding/analytics", "POST", {}, auth_header)
    request_json(f"{base_url}/api/onboarding/integration", "POST", {}, auth_header)
    print("✓ Onboarding complete")
    
    # Start config flow
    print("Starting Vantiva config flow...")
    flow_response = request_json(
        f"{base_url}/api/config/config_entries/flow",
        "POST",
        {"handler": "vantiva"},
        auth_header
    )
    flow_id = flow_response["flow_id"]
    print(f"✓ Flow started: {flow_id}")
    
    # Submit config
    print("Submitting configuration...")
    config_response = request_json(
        f"{base_url}/api/config/config_entries/flow/{flow_id}",
        "POST",
        {
            "host": vantiva_host,
            "username": vantiva_user,
            "password": vantiva_pass
        },
        auth_header
    )
    
    if config_response.get("type") != "create_entry":
        print(f"✗ Config failed: {config_response}")
        return 1
    
    entry_id = config_response["result"]
    title = config_response["title"]
    print(f"✓ Integration configured: {title}")
    
    # Save results
    with open("/tmp/ha_config_result.json", "w") as f:
        json.dump({
            "entry_id": entry_id,
            "title": title,
            "access_token": access_token
        }, f, indent=2)
    
    print(f"\n✓ Configuration complete!")
    print(f"  Entry ID: {entry_id}")
    print(f"  Access token saved to /tmp/ha_config_result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOFSCRIPT

# Run onboarding (loads credentials from .env)
set -a
source .env
set +a
python3 /tmp/ha_onboard.py
```

## Verification

### 1. Check Entities

```bash
# Load access token
ACCESS_TOKEN=$(jq -r .access_token /tmp/ha_config_result.json)

# List all entities
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8123/api/states | jq '.[].entity_id' | grep vantiva

# Get entity states
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8123/api/states | jq '[.[] | select(.entity_id | contains("vantiva"))]' \
  > /tmp/vantiva_entities.json

# Check key entities
cat /tmp/vantiva_entities.json | jq -r '.[] | "\(.entity_id): \(.state)"'
```

**Expected entities:**
- `binary_sensor.nh20t_internet_connectivity` - should be "on"
- `sensor.nh20t_wan_ipv4_address` - should show IP (redact in docs)
- `sensor.nh20t_connected_clients` - should show count
- `device_tracker.nh20t_*` - multiple, mixed "home"/"not_home"

### 2. Check Diagnostics

```bash
ENTRY_ID=$(jq -r .entry_id /tmp/ha_config_result.json)

curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:8123/api/diagnostics/config_entry/$ENTRY_ID" \
  > /tmp/diagnostics_raw.json

# Verify redaction
echo "Checking for password leaks..."
grep -i "password" /tmp/diagnostics_raw.json && echo "✗ FOUND PASSWORD!" || echo "✓ Password redacted"

# Check MACs are redacted
echo "Sample MAC addresses:"
grep -oE '"mac":\s*"[^"]*"' /tmp/diagnostics_raw.json | head -3
```

**Expected:** All passwords show `**REDACTED**`, MACs are masked.

### 3. Monitor Logs

```bash
# Check for errors
docker logs ha-vantiva-test 2>&1 | grep -iE 'vantiva|error|warning' | \
  grep -v -iE 'deprecat.*frontend|setuptools' | tail -50

# Wait for multiple poll cycles (~2 minutes)
echo "Waiting for 3 coordinator updates..."
sleep 130

# Check recent logs
docker logs ha-vantiva-test --since 3m 2>&1 | grep -i vantiva | tail -20
```

**Expected:** No ERROR or WARNING from `custom_components.vantiva`.

### 4. Test Options Flow

```bash
# Start options flow
FLOW_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  -X POST "http://localhost:8123/api/config/config_entries/options/flow" \
  -H "Content-Type: application/json" \
  -d "{\"handler\":\"$ENTRY_ID\"}")

FLOW_ID=$(echo $FLOW_RESPONSE | jq -r .flow_id)

echo "Options flow ID: $FLOW_ID"

# Submit new scan interval
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  -X POST "http://localhost:8123/api/config/config_entries/options/flow/$FLOW_ID" \
  -H "Content-Type: application/json" \
  -d '{"scan_interval": 60}' | jq .

# Check for errors in logs
docker logs ha-vantiva-test --since 1m 2>&1 | grep -i vantiva | tail -10
```

**Expected:** Options flow completes without errors.

## Cleanup

```bash
# Stop and remove container
docker rm -f ha-vantiva-test

# Clean up config (contains router password in .storage/core.config_entries)
rm -rf /tmp/ha-vantiva-config

# Remove temp files
rm -f /tmp/ha_onboard.py /tmp/ha_config_result.json \
      /tmp/vantiva_entities.json /tmp/diagnostics_raw.json
```

## Validation Checklist

After running the above tests, verify:

- [ ] Onboarding completed successfully
- [ ] Config entry created with title containing "NH20T"
- [ ] All expected entities created
- [ ] Internet connectivity binary sensor is "on"
- [ ] WAN IPv4 address present
- [ ] Connected clients count matches router
- [ ] Device trackers show home/not_home mix
- [ ] Diagnostics password is `**REDACTED**`
- [ ] Diagnostics MACs are masked
- [ ] No ERROR/WARNING in logs from vantiva integration
- [ ] Coordinator updates successfully (last_updated changes)
- [ ] Options flow completes without error

## Troubleshooting

### Container won't start
```bash
docker logs ha-vantiva-test
# Check for permission issues or port conflicts
```

### Onboarding fails
```bash
# Check HA is ready
curl http://localhost:8123/api/onboarding

# Restart container
docker restart ha-vantiva-test
```

### Config flow errors
```bash
# Check router is accessible from container
docker exec ha-vantiva-test ping -c 3 $VANTIVA_HOST

# Check integration logs
docker exec ha-vantiva-test cat /config/home-assistant.log | grep vantiva
```

### No entities appear
```bash
# Give HA time to initialize
sleep 60

# Check coordinator status in logs
docker logs ha-vantiva-test | grep -i coordinator
```
