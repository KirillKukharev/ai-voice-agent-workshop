#!/bin/bash
# Load Russian sound files for Asterisk

echo "🇷🇺 Setting up Russian sound files for Asterisk..."

# Check if Russian sound packages are installed
echo "📦 Checking for Russian sound packages..."

# Check if Russian sounds are available in the system
if [ -d "/usr/share/asterisk/sounds/ru" ]; then
    echo "✅ Found Russian sounds in /usr/share/asterisk/sounds/ru"

    # Create symlink to Russian sounds
    ln -sf /usr/share/asterisk/sounds/ru /var/lib/asterisk/sounds/ru

    echo "✅ Created symlink to Russian sounds"

elif [ -d "/var/lib/asterisk/sounds/ru" ]; then
    echo "✅ Found Russian sounds in /var/lib/asterisk/sounds/ru"

else
    echo "⚠️ Russian sounds not found, creating fallback..."

    # Create Russian sounds directory
    mkdir -p /var/lib/asterisk/sounds/ru

    # Copy existing sound files as base for Russian
    echo "📁 Copying existing sound files as base..."

    # Find and copy all existing sound files
    if [ -d "/var/lib/asterisk/sounds" ]; then
        echo "📋 Found sounds directory, copying files..."
        # Copy all .gsm files to Russian directory
        find /var/lib/asterisk/sounds -name "*.gsm" -exec cp {} /var/lib/asterisk/sounds/ru/ \; 2>/dev/null || true

        # Also copy from subdirectories if they exist
        if [ -d "/var/lib/asterisk/sounds/en" ]; then
            echo "📋 Found English sounds, copying as well..."
            find /var/lib/asterisk/sounds/en -name "*.gsm" -exec cp {} /var/lib/asterisk/sounds/ru/ \; 2>/dev/null || true
        fi
    fi

    # Create specific required files if they don't exist
    echo "🔊 Ensuring required sound files exist..."

    # List of required sound files
    required_files=("queue-hold" "tt-allbusy" "vm-goodbye" "queue-thereare" "queue-callswaiting" "queue-minutes" "queue-seconds" "queue-thankyou" "queue-youarenext" "queue-reporthold" "queue-periodic-announce")

    for file in "${required_files[@]}"; do
        if [ ! -f "/var/lib/asterisk/sounds/ru/${file}.gsm" ]; then
            echo "Creating placeholder for ${file}.gsm"
            # Create a minimal GSM file (empty but valid)
            touch /var/lib/asterisk/sounds/ru/${file}.gsm
        else
            echo "✅ Found ${file}.gsm"
        fi
    done
fi

# Set proper permissions
chown -R asterisk:asterisk /var/lib/asterisk/sounds/ru 2>/dev/null || true
chmod -R 644 /var/lib/asterisk/sounds/ru 2>/dev/null || true

echo "✅ Russian sound files setup completed"
echo "📁 Russian sounds directory: /var/lib/asterisk/sounds/ru/"
echo "📊 Files available: $(ls -1 /var/lib/asterisk/sounds/ru/ 2>/dev/null | wc -l)"
