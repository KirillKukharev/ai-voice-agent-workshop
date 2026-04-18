#!/bin/bash

# SIP Firewall Manager - простое управление блокировками IP для защиты Asterisk

DOCKER_USER_CHAIN="DOCKER-USER"
BLOCKLIST="/etc/asterisk/sip_blocklist.txt"

# Создаем файл если не существует
sudo touch "$BLOCKLIST"

show_help() {
    echo "SIP Firewall Manager"
    echo "Usage: $0 <command> [IP]"
    echo ""
    echo "Commands:"
    echo "  block <IP>     - Block IP address"
    echo "  unblock <IP>   - Unblock IP address"
    echo "  list           - Show blocked IPs"
    echo "  clear          - Clear all blocks"
    echo "  status         - Show current iptables rules"
    echo ""
    echo "Examples:"
    echo "  $0 block 203.0.113.1"
    echo "  $0 unblock 203.0.113.1"
    echo "  $0 list"
}

block_ip() {
    local ip=$1

    if [ -z "$ip" ]; then
        echo "Error: IP address required"
        exit 1
    fi

    # Проверяем формат IP
    if ! echo "$ip" | grep -E -q '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
        echo "Error: Invalid IP address format"
        exit 1
    fi

    # Проверяем, не заблокирован ли уже
    if sudo iptables -C "$DOCKER_USER_CHAIN" -s "$ip" -j DROP 2>/dev/null; then
        echo "IP $ip is already blocked"
        return
    fi

    # Блокируем
    sudo iptables -I "$DOCKER_USER_CHAIN" -s "$ip" -j DROP

    # Записываем в список
    echo "$ip:$(date +%s)" | sudo tee -a "$BLOCKLIST" > /dev/null

    echo "✓ Blocked IP: $ip"
}

unblock_ip() {
    local ip=$1

    if [ -z "$ip" ]; then
        echo "Error: IP address required"
        exit 1
    fi

    # Удаляем из iptables
    if sudo iptables -D "$DOCKER_USER_CHAIN" -s "$ip" -j DROP 2>/dev/null; then
        echo "✓ Unblocked IP: $ip"
    else
        echo "IP $ip was not blocked"
    fi

    # Удаляем из списка
    sudo sed -i "/^$ip:/d" "$BLOCKLIST"
}

list_blocked() {
    echo "Currently blocked IPs in iptables:"
    sudo iptables -L "$DOCKER_USER_CHAIN" -n | grep DROP | awk '{print "  " $4}' | sort -u

    echo ""
    echo "IPs in blocklist file:"
    if [ -f "$BLOCKLIST" ]; then
        while IFS=: read -r ip timestamp; do
            if [ -n "$ip" ]; then
                echo "  $ip (blocked at $(date -d @$timestamp))"
            fi
        done < "$BLOCKLIST"
    else
        echo "  No blocklist file found"
    fi
}

clear_all() {
    echo "Clearing all SIP-related blocks..."

    # Удаляем все правила DROP из DOCKER-USER цепочки
    while sudo iptables -D "$DOCKER_USER_CHAIN" -s 0.0.0.0/0 -j DROP 2>/dev/null; do
        true
    done

    # Очищаем файл
    sudo truncate -s 0 "$BLOCKLIST"

    echo "✓ All blocks cleared"
}

show_status() {
    echo "=== SIP Firewall Status ==="
    echo ""
    echo "DOCKER-USER chain rules:"
    sudo iptables -L "$DOCKER_USER_CHAIN" -n
    echo ""
    echo "Blocklist file: $BLOCKLIST"
    if [ -f "$BLOCKLIST" ]; then
        local count=$(wc -l < "$BLOCKLIST")
        echo "Entries in blocklist: $count"
    else
        echo "Blocklist file not found"
    fi
}

# Основная логика
case "$1" in
    "block")
        block_ip "$2"
        ;;
    "unblock")
        unblock_ip "$2"
        ;;
    "list")
        list_blocked
        ;;
    "clear")
        clear_all
        ;;
    "status")
        show_status
        ;;
    "help"|"-h"|"--help"|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
