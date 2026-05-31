#!/bin/bash
# Real-time monitoring script for E2E testing

echo "=== March7 Memory System Monitor ==="
echo "Test User: 726302130318868500 (Hoà)"
echo "Press Ctrl+C to stop"
echo ""

# Function to check T3 profile
check_t3() {
    echo "--- T3 Profile ---"
    docker exec march7 cat /app/memories/726302130318868500.md | tail -10
    echo ""
}

# Function to check T2 memories
check_t2() {
    echo "--- T2 Memories Count ---"
    COUNT=$(docker exec march7-redis redis-cli KEYS "t2:mem:726302130318868500:*" | wc -l)
    echo "Total T2 memories: $COUNT"
    if [ "$COUNT" -gt 0 ]; then
        echo "Latest memory:"
        KEY=$(docker exec march7-redis redis-cli KEYS "t2:mem:726302130318868500:*" | tail -1)
        docker exec march7-redis redis-cli JSON.GET "$KEY" | jq -r '.content' 2>/dev/null || echo "(parse error)"
    fi
    echo ""
}

# Function to check T1 active
check_t1() {
    echo "--- T1 Active Keys ---"
    docker exec march7-redis redis-cli KEYS "active:user:726302130318868500:*" | wc -l
    echo ""
}

# Function to watch logs
watch_logs() {
    echo "--- Recent Logs (last 10 lines) ---"
    docker logs march7 --tail 10 2>&1 | grep -E "T1:|T2:|T3:|tool|ERROR" || echo "(no relevant logs)"
    echo ""
}

# Main loop
while true; do
    clear
    echo "=== March7 Memory System Monitor ==="
    echo "Test User: 726302130318868500 (Hoà)"
    echo "Time: $(date '+%H:%M:%S')"
    echo ""

    check_t1
    check_t2
    check_t3
    watch_logs

    echo "Refreshing in 5 seconds... (Ctrl+C to stop)"
    sleep 5
done
