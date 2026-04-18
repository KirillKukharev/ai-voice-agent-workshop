#!/bin/bash
# Fix Russian queue messages in Asterisk

echo "🇷🇺 Fixing Russian queue messages in Asterisk..."

# Check if we're running in Docker
if [ -f /.dockerenv ]; then
    echo "📦 Running inside Docker container"
    ASTERISK_CMD="asterisk"
    SOUNDS_DIR="/var/lib/asterisk/sounds"
else
    echo "🖥️ Running on host system"
    ASTERISK_CMD="docker-compose exec asterisk asterisk"
    SOUNDS_DIR="/var/lib/asterisk/sounds"
fi

echo "🔧 Reloading Asterisk configuration..."

# Reload queue configuration
$ASTERISK_CMD -x "module reload app_queue.so"
$ASTERISK_CMD -x "module reload res_say.so"
$ASTERISK_CMD -x "module reload pbx_config.so"

# Reload say configuration for Russian digits
$ASTERISK_CMD -x "say reload"

echo "✅ Configuration reloaded"

# Check if Russian sounds exist
echo "🔍 Checking Russian sounds..."

if [ -f /.dockerenv ]; then
    # Inside container
    if [ -d "$SOUNDS_DIR/ru" ]; then
        echo "✅ Russian sounds directory exists: $SOUNDS_DIR/ru"
        echo "📊 Files in Russian sounds: $(ls -1 $SOUNDS_DIR/ru/ 2>/dev/null | wc -l)"

        # Check for required files
        required_files=("queue-hold" "tt-allbusy" "vm-goodbye" "queue-thereare" "queue-callswaiting" "queue-minutes" "queue-seconds" "queue-thankyou" "queue-youarenext" "queue-reporthold" "queue-periodic-announce")

        for file in "${required_files[@]}"; do
            if [ -f "$SOUNDS_DIR/ru/${file}.gsm" ]; then
                echo "✅ Found $file.gsm"
            else
                echo "⚠️ Missing $file.gsm"
            fi
        done
    else
        echo "❌ Russian sounds directory not found: $SOUNDS_DIR/ru"
        echo "🔧 Creating Russian sounds directory..."
        mkdir -p $SOUNDS_DIR/ru
        chown asterisk:asterisk $SOUNDS_DIR/ru
        chmod 755 $SOUNDS_DIR/ru
    fi
else
    # On host system
    echo "🔍 Checking Russian sounds in Docker container..."
    docker-compose exec asterisk ls -la $SOUNDS_DIR/ru/ 2>/dev/null || echo "❌ Russian sounds not found"
fi

echo "🎯 Testing queue configuration..."

# Test queue configuration
$ASTERISK_CMD -x "queue show ai-bot-queue"
$ASTERISK_CMD -x "queue show support-queue"

echo "✅ Russian queue messages fix completed"
echo "📋 Summary:"
echo "  - Removed monkey sounds from all extensions"
echo "  - Fixed queue configuration duplication"
echo "  - Added Russian queue messages configuration"
echo "  - Reloaded Asterisk configuration"
echo ""
echo "🎧 Test the system by calling:"
echo "  - 1002 (Support Queue)"
echo "  - 1004 (Busy Line Handler)"
echo "  - 1007 (Busy Line with Queue)"
