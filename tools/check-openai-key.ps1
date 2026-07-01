[CmdletBinding()]
param(
    [switch]$ShowModels
)

function Get-ErrorBody {
    param($Response)

    if ($null -eq $Response) {
        return $null
    }

    try {
        $stream = $Response.GetResponseStream()
        if ($null -eq $stream) {
            return $null
        }

        $reader = New-Object System.IO.StreamReader($stream)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
    }
    catch {
        return $null
    }
}

Write-Host ""
Write-Host "OpenAI API Key Checker" -ForegroundColor Cyan
Write-Host "Paste your key below, then press Enter."
Write-Host "The key will be visible while you type or paste it."
Write-Host ""

Write-Host -NoNewline "OpenAI API key: "
$apiKey = [Console]::ReadLine()
$headers = $null

try {
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-Host "NO: No key was entered." -ForegroundColor Red
        exit 2
    }

    $headers = @{
        Authorization = "Bearer $apiKey"
    }

    $response = Invoke-RestMethod `
        -Method Get `
        -Uri "https://api.openai.com/v1/models" `
        -Headers $headers `
        -TimeoutSec 20 `
        -ErrorAction Stop

    Write-Host ""
    Write-Host "YES: The key authenticated successfully." -ForegroundColor Green

    if ($ShowModels -and $response.data) {
        Write-Host ""
        Write-Host "First available models:"
        $response.data |
            Select-Object -First 5 -ExpandProperty id |
            ForEach-Object { Write-Host " - $_" }
    }

    exit 0
}
catch {
    $statusCode = $null
    $response = $_.Exception.Response

    if ($response -and $response.StatusCode) {
        $statusCode = [int]$response.StatusCode
    }

    $errorBody = Get-ErrorBody -Response $response
    if (-not $errorBody -and $_.ErrorDetails.Message) {
        $errorBody = $_.ErrorDetails.Message
    }

    Write-Host ""

    switch ($statusCode) {
        401 {
            Write-Host "NO: OpenAI rejected this key." -ForegroundColor Red
            Write-Host "Reason: 401 Unauthorized. The key is invalid, revoked, expired, or copied incorrectly."
            exit 1
        }
        403 {
            Write-Host "NO: The request was blocked by OpenAI permissions." -ForegroundColor Red
            Write-Host "Reason: 403 Forbidden. Check the key's project, organization, or API permissions."
            exit 1
        }
        429 {
            Write-Host "MAYBE: The key authenticated, but OpenAI returned a rate or quota limit." -ForegroundColor Yellow
            Write-Host "Reason: 429 Too Many Requests. The key may be valid but unable to make requests right now."
            exit 3
        }
        $null {
            Write-Host "NO: Could not reach OpenAI." -ForegroundColor Red
            Write-Host "Check your internet connection, firewall, or proxy settings."
            exit 4
        }
        default {
            Write-Host "NO: OpenAI returned HTTP $statusCode." -ForegroundColor Red
            if ($errorBody) {
                Write-Host ""
                Write-Host "Details:"
                Write-Host $errorBody
            }
            exit 1
        }
    }
}
finally {
    $headers = $null
    $apiKey = $null
}
