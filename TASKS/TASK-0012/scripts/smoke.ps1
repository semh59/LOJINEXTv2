$ErrorActionPreference = "Stop"

$compose = "TASKS/TASK-0012/docker-compose.smoke.yml"

Write-Host "Starting docker smoke stack..."
docker compose -f $compose up -d --build

function Invoke-CurlJson {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers,
        [object]$Body = $null,
        [string]$HeaderOut = $null
    )
    $args = @("-s", "-S", "-X", $Method)
    foreach ($key in $Headers.Keys) {
        $args += @("-H", "${key}: $($Headers[$key])")
    }
    $tempFile = $null
    if ($Body -ne $null) {
        $tempFile = New-TemporaryFile
        ($Body | ConvertTo-Json -Depth 10) | Set-Content -Path $tempFile -NoNewline
        $args += @("--data-binary", "@$tempFile")
    }
    if ($HeaderOut) {
        $args += @("-D", $HeaderOut)
    }
    $args += $Url
    $result = & curl.exe @args
    if ($tempFile) {
        Remove-Item $tempFile -ErrorAction SilentlyContinue
    }
    if (-not $result) { return $null }
    return $result | ConvertFrom-Json
}

function Get-HeaderValue {
    param(
        [string]$HeaderFile,
        [string]$HeaderName
    )
    $line = Get-Content $HeaderFile | Where-Object { $_ -like "${HeaderName}:*" } | Select-Object -First 1
    if (-not $line) { return $null }
    return $line.Split(":", 2)[1].Trim()
}

Write-Host "Waiting for trip-service /health..."
for ($i = 0; $i -lt 30; $i++) {
    $resp = & curl.exe -s -S http://localhost:8101/health
    if ($resp -like "*ok*") { break }
    Start-Sleep -Seconds 2
}

Write-Host "Running alembic migrations inside service containers..."
@'
import os
from alembic.config import Config
from alembic import command

cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", os.environ["TRIP_DATABASE_URL"])
command.upgrade(cfg, "head")
'@ | docker compose -f $compose exec -T trip-service python -

@'
import os
from alembic.config import Config
from alembic import command

cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", os.environ["LOCATION_DATABASE_URL"])
command.upgrade(cfg, "head")
'@ | docker compose -f $compose exec -T location-service python -

Write-Host "Seeding location-service database..."
docker compose -f $compose exec -T postgres psql -U postgres -d location_service -f /seed/seed-location.sql

Write-Host "Generating JWT tokens in trip-service container..."
$adminToken = @'
import jwt, os
print(jwt.encode({"sub":"admin-1","role":"ADMIN"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@ | docker compose -f $compose exec -T trip-service python -

$superAdminToken = @'
import jwt, os
print(jwt.encode({"sub":"super-1","role":"SUPER_ADMIN"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@ | docker compose -f $compose exec -T trip-service python -

$telegramToken = @'
import jwt, os
print(jwt.encode({"sub":"telegram-service","role":"SERVICE","service":"telegram-service"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@ | docker compose -f $compose exec -T trip-service python -

$excelToken = @'
import jwt, os
print(jwt.encode({"sub":"excel-service","role":"SERVICE","service":"excel-service"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@ | docker compose -f $compose exec -T trip-service python -

$adminHeaders = @{ Authorization = "Bearer $adminToken"; "Content-Type" = "application/json" }
$superHeaders = @{ Authorization = "Bearer $superAdminToken"; "Content-Type" = "application/json" }
$telegramHeaders = @{ Authorization = "Bearer $telegramToken"; "Content-Type" = "application/json" }
$excelHeaders = @{ Authorization = "Bearer $excelToken"; "Content-Type" = "application/json" }

$pairId = "33333333-3333-3333-3333-333333333333"
$nowLocal = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")

Write-Host "Manual create trip..."
$manualPayload = @{
    trip_no = "SMOKE-001"
    route_pair_id = $pairId
    trip_start_local = $nowLocal
    trip_timezone = "Europe/Istanbul"
    driver_id = "driver-1"
    vehicle_id = "vehicle-1"
    trailer_id = $null
    tare_weight_kg = 14000
    gross_weight_kg = 26000
    net_weight_kg = 12000
    note = "smoke"
}
$manualHeadersFile = New-TemporaryFile
$manualTrip = Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/api/v1/trips" -Headers $adminHeaders -Body $manualPayload -HeaderOut $manualHeadersFile
$manualEtag = Get-HeaderValue -HeaderFile $manualHeadersFile -HeaderName "ETag"

Write-Host "Create empty return..."
$emptyPayload = @{
    trip_start_local = $nowLocal
    trip_timezone = "Europe/Istanbul"
    driver_id = "driver-1"
    vehicle_id = "vehicle-1"
    trailer_id = $null
    tare_weight_kg = 14000
    gross_weight_kg = 14000
    net_weight_kg = 0
    note = "smoke empty"
}
$emptyHeaders = $adminHeaders.Clone()
$emptyHeaders["If-Match"] = $manualEtag
$emptyTrip = Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/empty-return" -f $manualTrip.id) -Headers $emptyHeaders -Body $emptyPayload

Write-Host "Telegram full ingest..."
$slipPayload = @{
    source_slip_no = "SLIP-001"
    source_reference_key = "telegram-msg-001"
    driver_id = "driver-1"
    vehicle_id = "vehicle-1"
    trailer_id = $null
    origin_name = "Istanbul"
    destination_name = "Ankara"
    trip_start_local = $nowLocal
    trip_timezone = "Europe/Istanbul"
    tare_weight_kg = 14000
    gross_weight_kg = 26000
    net_weight_kg = 12000
    ocr_confidence = 0.95
}
$slipHeadersFile = New-TemporaryFile
$slipTrip = Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/slips/ingest" -Headers $telegramHeaders -Body $slipPayload -HeaderOut $slipHeadersFile
$slipEtag = Get-HeaderValue -HeaderFile $slipHeadersFile -HeaderName "ETag"

Write-Host "Approve Telegram trip..."
$approveHeaders = $adminHeaders.Clone()
$approveHeaders["If-Match"] = $slipEtag
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/approve" -f $slipTrip.id) -Headers $approveHeaders -Body @{ note = "approve" } | Out-Null

Write-Host "Telegram fallback ingest..."
$fallbackPayload = @{
    source_reference_key = "telegram-msg-002"
    driver_id = "driver-1"
    message_sent_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    fallback_reason = "PARSE_FAILED"
}
Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/slips/ingest-fallback" -Headers $telegramHeaders -Body $fallbackPayload | Out-Null

Write-Host "Excel ingest..."
$excelPayload = @{
    source_reference_key = "excel-row-001"
    trip_no = "EXCEL-001"
    route_pair_id = $pairId
    trip_start_local = $nowLocal
    trip_timezone = "Europe/Istanbul"
    driver_id = "driver-1"
    vehicle_id = "vehicle-1"
    trailer_id = $null
    tare_weight_kg = 14000
    gross_weight_kg = 26000
    net_weight_kg = 12000
    row_number = 1
}
Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/excel/ingest" -Headers $excelHeaders -Body $excelPayload | Out-Null

Write-Host "Driver statement..."
Invoke-CurlJson -Method "GET" -Url ("http://localhost:8101/internal/v1/driver/trips?driver_id=driver-1&date_from={0}&date_to={1}" -f (Get-Date -Format "yyyy-MM-dd"), (Get-Date -Format "yyyy-MM-dd")) -Headers $telegramHeaders | Out-Null

Write-Host "Hard delete flow..."
$cancelHeaders = $adminHeaders.Clone()
$cancelHeaders["If-Match"] = $manualEtag
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/cancel" -f $manualTrip.id) -Headers $cancelHeaders | Out-Null

$hardHeaders = $superHeaders.Clone()
$hardHeaders["If-Match"] = $manualEtag
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/hard-delete" -f $manualTrip.id) -Headers $hardHeaders -Body @{ reason = "smoke cleanup" } | Out-Null

Write-Host "Smoke completed."
