# Метадані Windows без імені користувача, хоста чи серійних номерів.
$ErrorActionPreference = 'Stop'
$experimentRoot = Split-Path -Parent $PSScriptRoot
$metadata = [ordered]@{
    cpu = @(Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, L2CacheSize, L3CacheSize)
    memory_bytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
}
$metadata | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $experimentRoot 'docs/results/machine.json') -Encoding utf8
