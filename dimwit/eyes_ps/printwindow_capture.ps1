# Dimwit EYES Tier-A: capture a window via PrintWindow(PW_RENDERFULLCONTENT=2) — the reliable way to grab a
# DirectX/GPU-composited window (the UE editor / PIE viewport), which a plain desktop framebuffer grab returns
# BLACK/stale. Windows PowerShell 5.1 + .NET System.Drawing (no pip deps). Emits one compact JSON line.
#   powershell -ExecutionPolicy Bypass -File printwindow_capture.ps1 -title "Wanefall" -proc "UnrealEditor" -out cap.png
param([string]$title = "", [string]$proc = "", [string]$out = "cap.png")
$ErrorActionPreference = "Stop"
try {
  Add-Type -AssemblyName System.Drawing
  $sig = @"
using System;
using System.Runtime.InteropServices;
public class PW {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
  Add-Type $sig
  $cands = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle }
  if ($proc)  { $cands = $cands | Where-Object { $_.ProcessName -ieq $proc } }
  if ($title) { $cands = $cands | Where-Object { $_.MainWindowTitle -like "*$title*" } }
  $cands = @($cands)
  if ($cands.Count -eq 0) { @{ ok = $false; error = "no window match"; matches = 0 } | ConvertTo-Json -Compress; exit 0 }
  $p = $cands[0]
  $h = $p.MainWindowHandle
  $r = New-Object PW+RECT
  [void][PW]::GetWindowRect($h, [ref]$r)
  $w = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
  if ($w -le 0 -or $ht -le 0) { @{ ok = $false; error = "bad rect"; matches = $cands.Count } | ConvertTo-Json -Compress; exit 0 }
  $bmp = New-Object System.Drawing.Bitmap $w, $ht
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  $okp = [PW]::PrintWindow($h, $hdc, 2)   # 2 = PW_RENDERFULLCONTENT
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
  @{ ok = [bool]$okp; pid = $p.Id; proc = $p.ProcessName; title = $p.MainWindowTitle;
     width = $w; height = $ht; out = $out; matches = $cands.Count } | ConvertTo-Json -Compress
} catch {
  @{ ok = $false; error = "$_" } | ConvertTo-Json -Compress
}
