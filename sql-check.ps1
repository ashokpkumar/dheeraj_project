# sql_check.ps1 - collects SQL Server install + service-rights info for comparison
# Run in an ADMIN PowerShell:  powershell -ExecutionPolicy Bypass -File .\sql_check.ps1
# Output: sql_check_<COMPUTERNAME>.txt on your Desktop

$out = Join-Path ([Environment]::GetFolderPath('Desktop')) "sql_check_$env:COMPUTERNAME.txt"
Start-Transcript -Path $out -Force | Out-Null

function Section($t) { Write-Output "`n==================== $t ====================" }

Section "MACHINE"
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
    Computer     = $env:COMPUTERNAME
    OS           = $os.Caption
    OSVersion    = $os.Version
    Model        = $cs.Model            # shows VMware / Virtual Machine etc. on a VM
    DomainJoined = $cs.PartOfDomain
    Domain       = $cs.Domain
    User         = "$env:USERDOMAIN\$env:USERNAME"
    RunningAsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} | Format-List | Out-String -Width 200

Section "SQL SERVER INSTANCES"
$instKey = 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL'
if (Test-Path $instKey) {
    $inst = Get-ItemProperty $instKey
    $inst.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object {
        $setup = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$($_.Value)\Setup" -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Instance   = $_.Name
            InstanceId = $_.Value
            Edition    = $setup.Edition
            Version    = $setup.Version
            PatchLevel = $setup.PatchLevel
            DataRoot   = $setup.SQLDataRoot
        }
    } | Format-List | Out-String -Width 200
} else { Write-Output "No full SQL Server instances found in registry." }

Section "LOCALDB"
try { sqllocaldb info 2>&1 | Out-String } catch { Write-Output "sqllocaldb not installed." }

Section "SQL SERVICES (account each runs as)"
Get-CimInstance Win32_Service | Where-Object { $_.Name -like '*SQL*' } |
    Select-Object Name, State, StartMode, StartName |
    Format-Table -AutoSize | Out-String -Width 200

Section "WHO HAS 'LOG ON AS A SERVICE' (SeServiceLogonRight)"
$cfg = Join-Path $env:TEMP "secpol_export.cfg"
secedit /export /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
if (Test-Path $cfg) {
    $line = Select-String -Path $cfg -Pattern '^SeServiceLogonRight' | Select-Object -First 1
    if ($line) {
        ($line.Line -split '=', 2)[1].Trim() -split ',' | ForEach-Object {
            $e = $_.Trim()
            if ($e.StartsWith('*')) {
                $sid = $e.TrimStart('*')
                try { $name = (New-Object Security.Principal.SecurityIdentifier $sid).Translate([Security.Principal.NTAccount]).Value }
                catch { $name = '(unresolved)' }
                "  $name   [$sid]"
            } else { "  $e" }
        } | Out-String
    } else { Write-Output "SeServiceLogonRight is EMPTY - no account may log on as a service." }
    Remove-Item $cfg -Force
} else { Write-Output "Could not export policy (run as admin)." }

Section "GROUP POLICIES APPLIED TO THIS COMPUTER"
gpresult /r /scope computer 2>&1 | Out-String -Width 200

Section "SQL ODBC DRIVERS"
Get-OdbcDriver -Platform 64-bit | Where-Object { $_.Name -like '*SQL*' } |
    Select-Object Name | Format-Table -AutoSize | Out-String

Stop-Transcript | Out-Null
Write-Host "`nSaved to: $out" -ForegroundColor Green