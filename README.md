# dheeraj_project

# steps to create a image:

powershell -ExecutionPolicy Bypass -File .\build_and_save.ps1

powershell -ExecutionPolicy Bypass -File .\split_image.ps1

powershell -ExecutionPolicy Bypass -File .\join_chunks.ps1

powershell -ExecutionPolicy Bypass -File .\load_image.ps1