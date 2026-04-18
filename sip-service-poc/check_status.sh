#!/bin/bash
echo "=== Проверка статуса контейнеров ==="
docker-compose ps

echo ""
echo "=== Проверка логов nginx ==="
docker-compose logs --tail=20 nginx

echo ""
echo "=== Проверка логов frontend ==="
docker-compose logs --tail=20 frontend

echo ""
echo "=== Проверка доступности frontend ==="
docker-compose exec -T frontend curl -s -o /dev/null -w "%{http_code}" http://localhost:80 || echo "Frontend недоступен"

echo ""
echo "=== Проверка сетей Docker ==="
docker network ls | grep -E "(wazo|hbf|default)" || echo "Сети не найдены"
