.PHONY: help setup build-orch build-worker build-ui run-orch run-worker run-beat run-flower run-ui logs-all clean stop restart ps migrate superuser shell redis-cli up down logs build status test requirements freeze

help:
	@echo "Build & Deploy Commands:"
	@echo "  make setup              - Setup Docker network and Redis"
	@echo "  make build-orch         - Build orchestrator image"
	@echo "  make build-worker       - Build worker image"
	@echo "  make build-ui           - Build React UI image"
	@echo "  make run-orch           - Run orchestrator (API server)"
	@echo "  make run-worker N=1     - Run worker_N (celery worker)"
	@echo "  make run-beat           - Run beat scheduler"
	@echo "  make run-flower         - Run flower monitoring"
	@echo "  make run-ui             - Run React frontend (port 3000)"
	@echo ""
	@echo "Status & Logs:"
	@echo "  make ps                 - List all containers"
	@echo "  make status             - Show container status"
	@echo "  make logs-all           - View all logs"
	@echo ""
	@echo "Management:"
	@echo "  make stop               - Stop all containers"
	@echo "  make restart            - Restart all containers"
	@echo "  make clean              - Remove all automation containers"
	@echo "  make migrate            - Run database migrations"
	@echo "  make superuser          - Create admin user"
	@echo "  make shell              - Open Django shell"
	@echo ""
	@echo "Docker Compose (Legacy):"
	@echo "  make up                 - Start with docker-compose"
	@echo "  make down               - Stop docker-compose services"
	@echo "  make logs               - View docker-compose logs"

setup:
	@echo "Setting up infrastructure..."
	setup-infrastructure.bat

build-orch:
	@echo "Building orchestrator image..."
	docker build --build-arg ROLE=orchestrator --build-arg IS_ORCHESTRATOR=True -t automation:orchestrator .

build-worker:
	@echo "Building worker image..."
	docker build --build-arg ROLE=worker --build-arg IS_ORCHESTRATOR=False -t automation:worker .

build-ui:
	@echo "Building React UI image..."
	docker build -t automation:ui ../UI/my-react-flow-app

run-orch:
	@echo "Starting orchestrator API server..."
	docker run -d --name automation_main -p 8000:8000 --env-file .env --network automation_network automation:orchestrator serve

run-worker:
	@echo "Starting worker..."
	docker run -d --name automation_worker_$(N) --env-file .env --network automation_network automation:worker worker

run-beat:
	@echo "Starting Celery Beat scheduler..."
	docker run -d --name automation_beat --env-file .env --network automation_network automation:orchestrator beat

run-flower:
	@echo "Starting Flower monitoring..."
	docker run -d --name automation_flower -p 5555:5555 --env-file .env --network automation_network automation:orchestrator flower

run-ui:
	@echo "Starting React UI..."
	docker run -d --name automation_ui -p 3000:3000 --network automation_network automation:ui

ps:
	docker ps -a | findstr automation || docker ps -a | grep automation

status:
	docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

logs-all:
	docker logs -f automation_main

stop:
	@echo "Stopping all automation containers..."
	docker stop $(docker ps -q --filter "name=automation") || @echo "No containers to stop"

restart:
	@echo "Restarting all automation containers..."
	docker restart $(docker ps -q --filter "name=automation") || @echo "No containers to restart"

clean:
	@echo "Removing all automation containers..."
	docker ps -a -q --filter "name=automation" | xargs -r docker rm -f || @echo "No containers to remove"

migrate:
	docker exec automation_main python manage.py migrate

superuser:
	docker exec -it automation_main python manage.py createsuperuser

shell:
	docker exec -it automation_main python manage.py shell

redis-cli:
	docker exec -it automation_redis redis-cli

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

build:
	docker-compose build

requirements:
	pip install -r requirements.txt

freeze:
	pip freeze > requirements.txt
