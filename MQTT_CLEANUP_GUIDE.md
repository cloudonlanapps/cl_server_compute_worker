# MQTT Retained Message Cleanup Guide

## Problem

Retained MQTT messages are persistent and don't expire automatically. Test runs or crashed workers can leave stale retained messages that persist indefinitely in the MQTT broker.

## Solution

### Automated Cleanup Script

Use the provided `cleanup_mqtt.py` script to remove retained messages:

```bash
# Clean up all test messages
python cleanup_mqtt.py "test/retained/#"

# Clean up stale worker capabilities
python cleanup_mqtt.py "inference/workers/#"

# Clean up everything (use with caution!)
python cleanup_mqtt.py "#"
```

### Manual Cleanup

Using `mosquitto_pub`:

```bash
# Clear a specific retained message by publishing an empty retained message
mosquitto_pub -h localhost -t "test/retained/some-uuid" -n -r
```

Using `mosquitto_sub` to find retained messages:

```bash
# Subscribe and filter for retained messages
mosquitto_sub -h localhost -t '#' -v -R
```

## Test Improvements

The tests have been updated to properly disconnect MQTT clients in `finally` blocks:

- `test_set_will_method_exists` - Now disconnects broadcaster after test
- `test_publish_retained_method_exists` - Now disconnects broadcaster after test
- `test_clear_retained_method_exists` - Now disconnects broadcaster after test

This prevents connection leaks but doesn't prevent retained messages from test data in `cl_server_shared`.

## Cleanup After Tests

After running tests, check for and clean up any retained messages:

```bash
# Check what retained messages exist
mosquitto_sub -h localhost -t '#' -v -R | head -20

# Clean up test messages
python cleanup_mqtt.py "test/#"

# Clean up all inference-related messages (if needed)
python cleanup_mqtt.py "inference/#"
```

## Prevention

To prevent retained messages during testing:

1. **Use `BROADCAST_TYPE=noop`** in test environment:
   ```bash
   export BROADCAST_TYPE=noop
   python -m pytest tests/
   ```

2. **Mock MQTT connections** in tests (already done for most tests)

3. **Clean up in test teardown** (for integration tests that use real MQTT)

## Real-World Usage

In production, retained messages for worker capabilities are **intentional** and should persist:

- `inference/workers/{worker_id}` - Shows which workers are online
- These are properly cleared when workers shut down gracefully
- Use LWT (Last Will & Testament) for abnormal disconnects

Only clean these if:
- Workers have crashed and left stale registrations
- You're decommissioning workers
- Testing/development cleanup is needed
