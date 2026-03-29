param(
    [switch]$UseLiveProviders
)

$ErrorActionPreference = "Stop"
$global:PSNativeCommandUseErrorActionPreference = $false
$compose = "TASKS/TASK-0012/docker-compose.smoke.yml"

function Assert-LastExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE"
    }
}

function Load-EnvValue {
    param(
        [string]$Path,
        [string]$Name
    )
    if (-not (Test-Path $Path)) {
        return $null
    }
    $line = Get-Content $Path | Where-Object { $_ -match "^$Name=(.*)$" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }
    return ($line -split "=", 2)[1].Trim()
}

function Invoke-ComposePython {
    param(
        [string]$Service,
        [string]$Script,
        [switch]$Sensitive
    )
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $tempScript = New-TemporaryFile
        Set-Content -Path $tempScript -Value $Script -NoNewline
        $cmd = "type `"$tempScript`" | docker compose -f `"$compose`" exec -T $Service python - 2>nul"
        $output = cmd /c $cmd
        $exitCode = $LASTEXITCODE
    } finally {
        if ($tempScript) {
            Remove-Item $tempScript -ErrorAction SilentlyContinue
        }
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw "python in $Service failed with exit code $exitCode"
    }
    if (-not $Sensitive -and $output) {
        $output | Write-Host
    }
    return (($output | Out-String).Trim())
}

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
    $bodyFile = New-TemporaryFile
    if ($Body -ne $null) {
        $tempFile = New-TemporaryFile
        ($Body | ConvertTo-Json -Depth 10) | Set-Content -Path $tempFile -NoNewline
        $args += @("--data-binary", "@$tempFile")
    }
    if ($HeaderOut) {
        $args += @("-D", $HeaderOut)
    }
    $args += @("-o", $bodyFile, "-w", "%{http_code}", $Url)
    try {
        $statusCode = & curl.exe @args 2>$null
    } finally {
        if ($tempFile) {
            Remove-Item $tempFile -ErrorAction SilentlyContinue
        }
    }
    Assert-LastExitCode "curl $Method $Url"
    $bodyText = if (Test-Path $bodyFile) { Get-Content -Path $bodyFile -Raw } else { "" }
    Remove-Item $bodyFile -ErrorAction SilentlyContinue
    if ([int]$statusCode -ge 400) {
        $problemCode = $null
        $problemDetail = $null
        if ($bodyText) {
            try {
                $problem = $bodyText | ConvertFrom-Json
                $problemCode = $problem.code
                $problemDetail = $problem.detail
            } catch {
            }
        }
        $message = "HTTP $statusCode from $Method $Url"
        if ($problemCode) {
            $message += " ($problemCode)"
        }
        if ($problemDetail) {
            $message += ": $problemDetail"
        }
        throw $message
    }
    if (-not $bodyText) {
        return $null
    }
    return $bodyText | ConvertFrom-Json
}

function Get-HeaderValue {
    param(
        [string]$HeaderFile,
        [string]$HeaderName
    )
    $line = Get-Content $HeaderFile | Where-Object { $_ -like "${HeaderName}:*" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }
    return $line.Split(":", 2)[1].Trim()
}

function Wait-ForHttpOk {
    param(
        [string]$Url,
        [int]$Attempts = 30,
        [int]$SleepSeconds = 2
    )
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $resp = & curl.exe -s -S $Url 2>$null
            if ($resp -like "*ok*") {
                return
            }
        } catch {
        }
        Start-Sleep -Seconds $SleepSeconds
    }
    throw "Timed out waiting for $Url"
}

function Wait-ForRunSuccess {
    param(
        [string]$RunId,
        [hashtable]$Headers,
        [int]$Attempts = 60,
        [int]$SleepSeconds = 2
    )
    for ($i = 0; $i -lt $Attempts; $i++) {
        $run = Invoke-CurlJson -Method "GET" -Url "http://localhost:8103/v1/pairs/processing-runs/$RunId" -Headers $Headers
        if ($run.run_status -eq "SUCCEEDED") {
            return $run
        }
        if ($run.run_status -eq "FAILED") {
            throw "Location processing run $RunId failed: $($run.error_message)"
        }
        Start-Sleep -Seconds $SleepSeconds
    }
    throw "Timed out waiting for location processing run $RunId"
}

$env:SMOKE_SHARED_JWT_SECRET = if ($env:SMOKE_SHARED_JWT_SECRET) { $env:SMOKE_SHARED_JWT_SECRET } else { "trip-service-smoke-secret-please-change-me-32b" }
$env:SMOKE_LOCATION_ENABLE_ORS_VALIDATION = "false"

if ($UseLiveProviders) {
    $locationEnvPath = "services/location-service/.env"
    $mapboxKey = Load-EnvValue -Path $locationEnvPath -Name "LOCATION_MAPBOX_API_KEY"
    if (-not $mapboxKey) {
        throw "Live smoke requested but LOCATION_MAPBOX_API_KEY was not found in services/location-service/.env"
    }
    $env:LOCATION_MAPBOX_API_KEY = $mapboxKey

    $orsKey = Load-EnvValue -Path $locationEnvPath -Name "LOCATION_ORS_API_KEY"
    $orsBaseUrl = Load-EnvValue -Path $locationEnvPath -Name "LOCATION_ORS_BASE_URL"
    if ($orsKey -and $orsBaseUrl) {
        $env:LOCATION_ORS_API_KEY = $orsKey
        $env:LOCATION_ORS_BASE_URL = $orsBaseUrl
        $env:SMOKE_LOCATION_ENABLE_ORS_VALIDATION = "true"
    }
}

Write-Host "Starting docker smoke stack..."
docker compose -f $compose down -v --remove-orphans | Write-Host
Assert-LastExitCode "docker compose down"
docker compose -f $compose up -d --build | Write-Host
Assert-LastExitCode "docker compose up"

Write-Host "Waiting for trip-service /health..."
Wait-ForHttpOk -Url "http://localhost:8101/health"

Write-Host "Running alembic migrations inside service containers..."
Invoke-ComposePython -Service "trip-service" -Script @'
import os
from alembic.config import Config
from alembic import command

cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", os.environ["TRIP_DATABASE_URL"])
command.upgrade(cfg, "head")
'@

Invoke-ComposePython -Service "location-service" -Script @'
import os
from alembic.config import Config
from alembic import command

cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", os.environ["LOCATION_DATABASE_URL"])
command.upgrade(cfg, "head")
'@

Write-Host "Seeding location-service database for offline smoke..."
docker compose -f $compose exec -T postgres psql -U postgres -d location_service -f /seed/seed-location.sql | Write-Host
Assert-LastExitCode "seed location-service database"

Write-Host "Generating JWT tokens in trip-service container..."
$adminToken = Invoke-ComposePython -Service "trip-service" -Sensitive -Script @'
import jwt, os
print(jwt.encode({"sub":"admin-1","role":"ADMIN"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@
$superAdminToken = Invoke-ComposePython -Service "trip-service" -Sensitive -Script @'
import jwt, os
print(jwt.encode({"sub":"super-1","role":"SUPER_ADMIN"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@
$telegramToken = Invoke-ComposePython -Service "trip-service" -Sensitive -Script @'
import jwt, os
print(jwt.encode({"sub":"telegram-service","role":"SERVICE","service":"telegram-service"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@
$excelToken = Invoke-ComposePython -Service "trip-service" -Sensitive -Script @'
import jwt, os
print(jwt.encode({"sub":"excel-service","role":"SERVICE","service":"excel-service"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@
$tripServiceToken = Invoke-ComposePython -Service "trip-service" -Sensitive -Script @'
import jwt, os
print(jwt.encode({"sub":"trip-service","role":"SERVICE","service":"trip-service"}, os.environ["TRIP_AUTH_JWT_SECRET"], algorithm=os.environ["TRIP_AUTH_JWT_ALGORITHM"]))
'@

$adminHeaders = @{ Authorization = "Bearer $adminToken"; "Content-Type" = "application/json" }
$superHeaders = @{ Authorization = "Bearer $superAdminToken"; "Content-Type" = "application/json" }
$telegramHeaders = @{ Authorization = "Bearer $telegramToken"; "Content-Type" = "application/json" }
$excelHeaders = @{ Authorization = "Bearer $excelToken"; "Content-Type" = "application/json" }
$locationInternalHeaders = @{ Authorization = "Bearer $tripServiceToken"; "Content-Type" = "application/json" }

$pairId = "33333333-3333-3333-3333-333333333333"
$nowLocal = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
$emptyReturnLocal = $nowLocal
$slipStartLocal = (Get-Date).AddHours(2).ToString("yyyy-MM-ddTHH:mm:ss")
$excelStartLocal = (Get-Date).AddHours(4).ToString("yyyy-MM-ddTHH:mm:ss")

$manualDriverId = "driver-manual"
$manualVehicleId = "vehicle-manual"
$slipDriverId = "driver-slip"
$slipVehicleId = "vehicle-slip"
$excelDriverId = "driver-excel"
$excelVehicleId = "vehicle-excel"
$emptyReturnDriverId = "driver-empty-return"
$emptyReturnVehicleId = "vehicle-empty-return"

Write-Host "Offline smoke: manual create trip..."
$manualPayload = @{
    trip_no = "SMOKE-001"
    route_pair_id = $pairId
    trip_start_local = $nowLocal
    trip_timezone = "Europe/Istanbul"
    driver_id = $manualDriverId
    vehicle_id = $manualVehicleId
    trailer_id = $null
    tare_weight_kg = 14000
    gross_weight_kg = 26000
    net_weight_kg = 12000
    note = "smoke"
}
$manualHeadersFile = New-TemporaryFile
$manualTrip = Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/api/v1/trips" -Headers $adminHeaders -Body $manualPayload -HeaderOut $manualHeadersFile
$manualEtag = Get-HeaderValue -HeaderFile $manualHeadersFile -HeaderName "ETag"

Write-Host "Offline smoke: create empty return..."
$emptyPayload = @{
    trip_start_local = $emptyReturnLocal
    trip_timezone = "Europe/Istanbul"
    driver_id = $emptyReturnDriverId
    vehicle_id = $emptyReturnVehicleId
    trailer_id = $null
    tare_weight_kg = 14000
    gross_weight_kg = 14000
    net_weight_kg = 0
    note = "smoke empty"
}
$emptyHeaders = $adminHeaders.Clone()
$emptyHeaders["If-Match"] = $manualEtag
$emptyHeadersFile = New-TemporaryFile
$emptyReturnTrip = Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/empty-return" -f $manualTrip.id) -Headers $emptyHeaders -Body $emptyPayload -HeaderOut $emptyHeadersFile
$emptyReturnEtag = Get-HeaderValue -HeaderFile $emptyHeadersFile -HeaderName "ETag"

Write-Host "Offline smoke: Telegram full ingest..."
$slipPayload = @{
    source_slip_no = "SLIP-001"
    source_reference_key = "telegram-msg-001"
    driver_id = $slipDriverId
    vehicle_id = $slipVehicleId
    trailer_id = $null
    origin_name = "Istanbul"
    destination_name = "Ankara"
    trip_start_local = $slipStartLocal
    trip_timezone = "Europe/Istanbul"
    tare_weight_kg = 14000
    gross_weight_kg = 26000
    net_weight_kg = 12000
    ocr_confidence = 0.95
}
$slipHeadersFile = New-TemporaryFile
$slipTrip = Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/slips/ingest" -Headers $telegramHeaders -Body $slipPayload -HeaderOut $slipHeadersFile
$slipEtag = Get-HeaderValue -HeaderFile $slipHeadersFile -HeaderName "ETag"

$approveHeaders = $adminHeaders.Clone()
$approveHeaders["If-Match"] = $slipEtag
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/approve" -f $slipTrip.id) -Headers $approveHeaders -Body @{ note = "approve" } | Out-Null

Write-Host "Offline smoke: Telegram fallback ingest..."
$fallbackPayload = @{
    source_reference_key = "telegram-msg-002"
    driver_id = $slipDriverId
    message_sent_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    fallback_reason = "PARSE_FAILED"
}
Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/slips/ingest-fallback" -Headers $telegramHeaders -Body $fallbackPayload | Out-Null

Write-Host "Offline smoke: Excel ingest..."
$excelPayload = @{
    source_reference_key = "excel-row-001"
    trip_no = "EXCEL-001"
    route_pair_id = $pairId
    trip_start_local = $excelStartLocal
    trip_timezone = "Europe/Istanbul"
    driver_id = $excelDriverId
    vehicle_id = $excelVehicleId
    trailer_id = $null
    tare_weight_kg = 14000
    gross_weight_kg = 26000
    net_weight_kg = 12000
    row_number = 1
}
Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/excel/ingest" -Headers $excelHeaders -Body $excelPayload | Out-Null

Write-Host "Offline smoke: driver statement..."
Invoke-CurlJson -Method "GET" -Url ("http://localhost:8101/internal/v1/driver/trips?driver_id={0}&date_from={1}&date_to={2}" -f $manualDriverId, (Get-Date -Format "yyyy-MM-dd"), ((Get-Date).AddDays(1).ToString("yyyy-MM-dd"))) -Headers $telegramHeaders | Out-Null

Write-Host "Offline smoke: hard delete flow..."
$emptyCancelHeaders = $adminHeaders.Clone()
$emptyCancelHeaders["If-Match"] = $emptyReturnEtag
$emptyCancelHeadersFile = New-TemporaryFile
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/cancel" -f $emptyReturnTrip.id) -Headers $emptyCancelHeaders -HeaderOut $emptyCancelHeadersFile | Out-Null
$emptyCancelEtag = Get-HeaderValue -HeaderFile $emptyCancelHeadersFile -HeaderName "ETag"

$emptyHardHeaders = $superHeaders.Clone()
$emptyHardHeaders["If-Match"] = $emptyCancelEtag
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/hard-delete" -f $emptyReturnTrip.id) -Headers $emptyHardHeaders -Body @{ reason = "smoke cleanup child" } | Out-Null

$cancelHeaders = $adminHeaders.Clone()
$cancelHeaders["If-Match"] = $manualEtag
$cancelHeadersFile = New-TemporaryFile
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/cancel" -f $manualTrip.id) -Headers $cancelHeaders -HeaderOut $cancelHeadersFile | Out-Null
$cancelEtag = Get-HeaderValue -HeaderFile $cancelHeadersFile -HeaderName "ETag"

$hardHeaders = $superHeaders.Clone()
$hardHeaders["If-Match"] = $cancelEtag
Invoke-CurlJson -Method "POST" -Url ("http://localhost:8101/api/v1/trips/{0}/hard-delete" -f $manualTrip.id) -Headers $hardHeaders -Body @{ reason = "smoke cleanup" } | Out-Null

if ($UseLiveProviders) {
    Write-Host "Live smoke: creating points and pair in location-service..."
    $suffix = (Get-Date -Format "yyyyMMddHHmmssfff")
    $offsetLat = [math]::Round((Get-Random -Minimum 11 -Maximum 499) / 1000000.0, 6)
    $offsetLng = [math]::Round((Get-Random -Minimum 11 -Maximum 499) / 1000000.0, 6)
    $liveManualStartLocal = (Get-Date).AddMinutes(-10).ToString("yyyy-MM-ddTHH:mm:ss")
    $liveSlipStartLocal = (Get-Date).AddMinutes(-8).ToString("yyyy-MM-ddTHH:mm:ss")
    $liveExcelStartLocal = (Get-Date).AddMinutes(-6).ToString("yyyy-MM-ddTHH:mm:ss")
    $originCode = "LIVE_ORG_$suffix"
    $destinationCode = "LIVE_DST_$suffix"
    $originName = "Live Origin $suffix"
    $destinationName = "Live Destination $suffix"

    Invoke-CurlJson -Method "POST" -Url "http://localhost:8103/v1/points" -Headers $adminHeaders -Body @{
        code = $originCode
        name_tr = $originName
        name_en = $originName
        latitude_6dp = [math]::Round(41.0082 + $offsetLat, 6)
        longitude_6dp = [math]::Round(28.9784 + $offsetLng, 6)
        is_active = $true
    } | Out-Null
    Invoke-CurlJson -Method "POST" -Url "http://localhost:8103/v1/points" -Headers $adminHeaders -Body @{
        code = $destinationCode
        name_tr = $destinationName
        name_en = $destinationName
        latitude_6dp = [math]::Round(39.9334 + $offsetLat, 6)
        longitude_6dp = [math]::Round(32.8597 + $offsetLng, 6)
        is_active = $true
    } | Out-Null

    $pairHeadersFile = New-TemporaryFile
    $livePair = Invoke-CurlJson -Method "POST" -Url "http://localhost:8103/v1/pairs" -Headers $adminHeaders -Body @{
        origin_code = $originCode
        destination_code = $destinationCode
        profile_code = "TIR"
    } -HeaderOut $pairHeadersFile

    $calcRun = Invoke-CurlJson -Method "POST" -Url ("http://localhost:8103/v1/pairs/{0}/calculate" -f $livePair.pair_id) -Headers $adminHeaders -Body @{}
    Wait-ForRunSuccess -RunId $calcRun.run_id -Headers $adminHeaders | Out-Null

    $pairDetailsHeaders = New-TemporaryFile
    Invoke-CurlJson -Method "GET" -Url ("http://localhost:8103/v1/pairs/{0}" -f $livePair.pair_id) -Headers $adminHeaders -HeaderOut $pairDetailsHeaders | Out-Null
    $pairEtag = Get-HeaderValue -HeaderFile $pairDetailsHeaders -HeaderName "ETag"

    $approvePairHeaders = $adminHeaders.Clone()
    $approvePairHeaders["If-Match"] = $pairEtag
    Invoke-CurlJson -Method "POST" -Url ("http://localhost:8103/v1/pairs/{0}/approve" -f $livePair.pair_id) -Headers $approvePairHeaders | Out-Null

    Write-Host "Live smoke: validating location internal contracts..."
    Invoke-CurlJson -Method "POST" -Url "http://localhost:8103/internal/v1/routes/resolve" -Headers $locationInternalHeaders -Body @{
        origin_name = $originName
        destination_name = $destinationName
        profile_code = "TIR"
        language_hint = "AUTO"
    } | Out-Null
    Invoke-CurlJson -Method "GET" -Url ("http://localhost:8103/internal/v1/route-pairs/{0}/trip-context" -f $livePair.pair_id) -Headers $locationInternalHeaders | Out-Null

    Write-Host "Live smoke: validating trip/location integration..."
    Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/api/v1/trips" -Headers $adminHeaders -Body @{
        trip_no = "LIVE-SMOKE-$suffix"
        route_pair_id = $livePair.pair_id
        trip_start_local = $liveManualStartLocal
        trip_timezone = "Europe/Istanbul"
        driver_id = "driver-live-manual"
        vehicle_id = "vehicle-live-manual"
        trailer_id = $null
        tare_weight_kg = 14000
        gross_weight_kg = 26000
        net_weight_kg = 12000
    } | Out-Null
    Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/slips/ingest" -Headers $telegramHeaders -Body @{
        source_slip_no = "LIVE-SLIP-$suffix"
        source_reference_key = "live-telegram-$suffix"
        driver_id = "driver-live-slip"
        vehicle_id = "vehicle-live-slip"
        trailer_id = $null
        origin_name = $originName
        destination_name = $destinationName
        trip_start_local = $liveSlipStartLocal
        trip_timezone = "Europe/Istanbul"
        tare_weight_kg = 14000
        gross_weight_kg = 26000
        net_weight_kg = 12000
        ocr_confidence = 0.95
    } | Out-Null
    Invoke-CurlJson -Method "POST" -Url "http://localhost:8101/internal/v1/trips/excel/ingest" -Headers $excelHeaders -Body @{
        source_reference_key = "live-excel-$suffix"
        trip_no = "LIVE-EXCEL-$suffix"
        route_pair_id = $livePair.pair_id
        trip_start_local = $liveExcelStartLocal
        trip_timezone = "Europe/Istanbul"
        driver_id = "driver-live-excel"
        vehicle_id = "vehicle-live-excel"
        trailer_id = $null
        tare_weight_kg = 14000
        gross_weight_kg = 26000
        net_weight_kg = 12000
        row_number = 1
    } | Out-Null
}

Write-Host "Smoke completed."
exit 0
