# 0. Environment Part

# 1. Linux part
```
Unblock-File .\join_chunks.ps1
```
```
powershell -ExecutionPolicy Bypass -File .\join_chunks.ps1
```

```
docker load -i os_image.tar
```

```
.\setup-infrastructure.bat
```

```
.\quick-start.bat
```



```
docker compose up --scale worker=4
```
# 2. Windows Part



### 1.1 Install Dependencies on Windows

```powershell
# Open PowerShell as Administrator
pip install pywin32 flask flask-cors

# Post-install pywin32 (required for COM interface)
python -m pip install --force-reinstall --no-cache-dir pywin32
python Scripts/pywin32_postinstall.py -install
```

### 1.2 Start the Service

```powershell
cd c:\Users\ashok\Documents\dheeraj_project\dheeraj_project\backend\automation

# Make sure EXTRA emulator is running with sessions!

# Start the service
.\start-windows-service.ps1

# Output should show:
# Starting Windows Automation Service on 0.0.0.0:5555
# ⚠️  This service MUST run on Windows with EXTRA emulator open
```

✅ **Service is now running at `http://localhost:5555`**

Test it:
```powershell
curl http://localhost:5555/health
```

Should return: `{"status": "healthy", "service": "windows_automation"}`

---


cd ~/dheeraj_project/backend/automation
