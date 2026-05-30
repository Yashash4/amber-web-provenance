# Renders Amber's cover + architecture images from the HTML generators via headless Chrome.
# Usage:  pwsh -File scripts/branding/render.ps1
$ErrorActionPreference = "Stop"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$out    = Join-Path (Split-Path -Parent (Split-Path -Parent $root)) "samples"
function Render($html, $png, $w, $h) {
  $target = Join-Path $out $png
  $uri = "file:///" + ((Join-Path $root $html) -replace '\\','/')
  $a = @("--headless=new","--no-sandbox","--disable-gpu","--hide-scrollbars",
         "--force-device-scale-factor=2","--virtual-time-budget=4000",
         "--screenshot=$target","--window-size=$w,$h", $uri)
  Start-Process -FilePath $chrome -ArgumentList $a -NoNewWindow -Wait | Out-Null
  Write-Host ("rendered " + $png + "  ->  " + (Get-Item $target).Length + " bytes")
}
Render "cover.html"        "cover-image.png"          1280 720
Render "architecture.html" "architecture-diagram.png" 1400 660
