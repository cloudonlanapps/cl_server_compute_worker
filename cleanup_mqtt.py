#!/usr/bin/env python3
"""
Cleanup script for removing retained MQTT messages.

This script removes all retained messages matching a topic pattern.
Useful for cleaning up test messages or stale worker registrations.

Usage:
    python cleanup_mqtt.py test/retained/#      # Clean all test/retained topics
    python cleanup_mqtt.py inference/workers/#  # Clean all worker capabilities
    python cleanup_mqtt.py "test/#"             # Clean all test topics
"""

import sys
import time
import paho.mqtt.client as mqtt


def clear_retained_messages(broker="localhost", port=1883, topic_pattern="#"):
    """
    Clear all retained messages matching the topic pattern.

    Args:
        broker: MQTT broker hostname
        port: MQTT broker port
        topic_pattern: Topic pattern to match (use # for wildcard)
    """
    found_topics = []

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to {broker}:{port}")
            print(f"Subscribing to: {topic_pattern}")
            client.subscribe(topic_pattern)
        else:
            print(f"Connection failed with code {rc}")
            sys.exit(1)

    def on_message(client, userdata, msg):
        if msg.retain:
            topic = msg.topic
            found_topics.append(topic)
            print(f"Found retained message: {topic}")
            # Clear by publishing empty retained message
            client.publish(topic, payload=None, qos=1, retain=True)
            print(f"  → Cleared: {topic}")

    # Create MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        # Connect to broker
        client.connect(broker, port, 60)

        # Start loop to process messages
        client.loop_start()

        # Wait for messages (2 seconds should be enough)
        print("Scanning for retained messages...")
        time.sleep(2)

        # Stop loop
        client.loop_stop()

        # Disconnect
        client.disconnect()

        # Summary
        print(f"\n✓ Cleanup complete!")
        print(f"  Total retained messages cleared: {len(found_topics)}")
        if found_topics:
            print(f"  Topics cleared:")
            for topic in found_topics:
                print(f"    - {topic}")
        else:
            print(f"  No retained messages found matching '{topic_pattern}'")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python cleanup_mqtt.py <topic_pattern>")
        print("\nExamples:")
        print("  python cleanup_mqtt.py 'test/retained/#'")
        print("  python cleanup_mqtt.py 'inference/workers/#'")
        print("  python cleanup_mqtt.py '#'  # WARNING: Clears ALL retained messages")
        sys.exit(1)

    topic_pattern = sys.argv[1]

    # Optional: broker and port from environment or args
    broker = sys.argv[2] if len(sys.argv) > 2 else "localhost"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 1883

    print("=" * 60)
    print("MQTT Retained Message Cleanup")
    print("=" * 60)
    print(f"Broker: {broker}:{port}")
    print(f"Pattern: {topic_pattern}")
    print("=" * 60)

    # Confirm for wildcard patterns
    if topic_pattern in ("#", "+/#", "#/+"):
        response = input("\n⚠️  WARNING: This will clear ALL retained messages!\nContinue? (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled.")
            sys.exit(0)

    clear_retained_messages(broker, port, topic_pattern)


if __name__ == "__main__":
    main()
