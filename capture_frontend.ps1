# Live-launch capture of THE HOLD (default SQUAD view) + the kit arena match. No SendKeys (UE -game ignores it);
# captures the default camera view. Foregrounds the window via Win32, screenshots the primary screen.
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}
"@
$ue   = "C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$proj = "C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject"
$out  = "C:\Users\developer\Documents\Dimwit\frontend_capture"
New-Item -ItemType Directory -Force $out | Out-Null
$bnd  = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds

function Foreground($p) {
  try { $p.Refresh(); [Win]::ShowWindow($p.MainWindowHandle, 3) | Out-Null; [Win]::SetForegroundWindow($p.MainWindowHandle) | Out-Null } catch {}
  Start-Sleep -Milliseconds 1000
}
function Shot($p, $name) {
  Foreground $p
  $bmp = New-Object System.Drawing.Bitmap $bnd.Width, $bnd.Height
  $g   = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($bnd.X, $bnd.Y, 0, 0, $bmp.Size)
  $bmp.Save("$out\$name.png")
  $g.Dispose(); $bmp.Dispose()
  Write-Output "shot: $name"
}
function Launch($mapurl) {
  return Start-Process $ue -ArgumentList "`"$proj`"","`"$mapurl`"","-game","-windowed",("-ResX=" + $bnd.Width),("-ResY=" + $bnd.Height),"-nosplash" -PassThru
}

$p = Launch "/Game/Wanefall/Maps/Wanefall_TheHold_01?game=/Script/WanefallGreybox.WanefallHoldGameMode"
Start-Sleep -Seconds 60
Shot $p "10_hold_relit"
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

$q = Launch "/Game/Wanefall/Maps/Wanefall_KitArena_01?game=/Script/WanefallGreybox.WanefallMatchGameMode"
Start-Sleep -Seconds 45
Shot $q "11_kitarena_match"
Stop-Process -Id $q.Id -Force -ErrorAction SilentlyContinue

Write-Output "CAPTURE_DONE"
