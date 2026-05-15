# dheeraj_project

# steps to create a image:
Unblock-File .\join_chunks.ps1

powershell -ExecutionPolicy Bypass -File .\build_and_save.ps1

powershell -ExecutionPolicy Bypass -File .\split_image.ps1

powershell -ExecutionPolicy Bypass -File .\join_chunks.ps1


powershell -ExecutionPolicy Bypass -File .\load_image.ps1

docker load -i os_image.tar

Unblock-File .\load_image_rancher.ps1
powershell -ExecutionPolicy Bypass -File .\load_image_rancher.ps1



Flow:

VM boots
  └─> Emulator Agent starts (Windows native, 16 emulators ready)

docker compose up --scale worker=4
  └─> Worker 1 starts → claims emulators [1,2,3,4]   → registers queue "worker.abc1"
  └─> Worker 2 starts → claims emulators [5,6,7,8]   → registers queue "worker.abc2"
  └─> Worker 3 starts → claims emulators [9,10,11,12] → registers queue "worker.abc3"
  └─> Worker 4 starts → claims emulators [13,14,15,16]→ registers queue "worker.abc4"

Scheduler triggers daily job
  └─> Orchestrator reads registry → finds 4 workers
  └─> Dispatches 16 jobs round-robin across worker.abc1 … worker.abc4

docker compose up --scale worker=2   (scale down mid-day)
  └─> Workers 3 & 4 SIGTERM → release emulators, delete registry keys
  └─> Orchestrator next dispatch → only sees worker.abc1 and worker.abc2