$BASE = "https://swing-terminal.onrender.com"

Write-Host "=== SWING TERMINAL API TEST ===" -ForegroundColor Cyan

# 1. Health
Write-Host "`n[1] /api/health" -ForegroundColor Yellow
try {
    $h = Invoke-RestMethod -Uri "$BASE/api/health"
    Write-Host "  ok=$($h.ok)  cached=$($h.universe_cached)  building=$($h.building)" -ForegroundColor Green
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

# 2. Status
Write-Host "`n[2] /api/status" -ForegroundColor Yellow
try {
    $s = Invoke-RestMethod -Uri "$BASE/api/status"
    Write-Host "  ready=$($s.ready)  stocks=$($s.stocks_cached)" -ForegroundColor Green
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

# 3. Strategies
Write-Host "`n[3] /api/strategies" -ForegroundColor Yellow
try {
    $strats = Invoke-RestMethod -Uri "$BASE/api/strategies"
    Write-Host "  Got $($strats.Count) strategies: $($strats.id -join ', ')" -ForegroundColor Green
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

# 4. Scan - Cup & Handle
Write-Host "`n[4] /api/scan  (strategy=cup)" -ForegroundColor Yellow
try {
    $body = @{
        strategy = "cup"
        cap = "any"
        sector = "any"
        min_score = 0
        min_rr = 0
        trend = "any"
        volume_confirmed = $false
    } | ConvertTo-Json
    $scan = Invoke-RestMethod -Uri "$BASE/api/scan" -Method POST -ContentType "application/json" -Body $body
    Write-Host "  count=$($scan.count)  total_analyzed=$($scan.total_analyzed)" -ForegroundColor Green
    if ($scan.results.Count -gt 0) {
        Write-Host "  Top results:" -ForegroundColor Green
        $scan.results | Select-Object -First 5 | ForEach-Object {
            Write-Host "    $($_.symbol) | price=$($_.price) | score=$($_.fit_score) | RSI=$($_.rsi)" -ForegroundColor White
        }
    }
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

# 5. Scan - Double Bottom
Write-Host "`n[5] /api/scan  (strategy=dbl)" -ForegroundColor Yellow
try {
    $body = @{
        strategy = "dbl"
        cap = "any"
        sector = "any"
        min_score = 0
        min_rr = 0
        trend = "any"
        volume_confirmed = $false
    } | ConvertTo-Json
    $scan2 = Invoke-RestMethod -Uri "$BASE/api/scan" -Method POST -ContentType "application/json" -Body $body
    Write-Host "  count=$($scan2.count)" -ForegroundColor Green
    $scan2.results | Select-Object -First 3 | ForEach-Object {
        Write-Host "    $($_.symbol) | score=$($_.fit_score)" -ForegroundColor White
    }
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

# 6. Chart endpoint
Write-Host "`n[6] /api/chart/TECHM?strategy=cup" -ForegroundColor Yellow
try {
    $chart = Invoke-RestMethod -Uri "$BASE/api/chart/TECHM?strategy=cup"
    Write-Host "  symbol=$($chart.symbol)  data_points=$($chart.data.Count)  landmark_type=$($chart.landmarks.type)" -ForegroundColor Green
    Write-Host "  First candle: time=$($chart.data[0].time) open=$($chart.data[0].open) close=$($chart.data[0].close)" -ForegroundColor White
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

# 7. Chart endpoint - CDSL
Write-Host "`n[7] /api/chart/CDSL?strategy=cup" -ForegroundColor Yellow
try {
    $chart2 = Invoke-RestMethod -Uri "$BASE/api/chart/CDSL?strategy=cup"
    Write-Host "  symbol=$($chart2.symbol)  data_points=$($chart2.data.Count)  landmark_type=$($chart2.landmarks.type)" -ForegroundColor Green
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }

Write-Host "`n=== TEST COMPLETE ===" -ForegroundColor Cyan
