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