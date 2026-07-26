# Live-launch capture of the SoulCave-based lobby (walkable). Longer settle for first-run cave shader compile.
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class Win { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n); }
"@
$ue="C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$proj="C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject"
$out="C:\Users\developer\Documents\Dimwit\frontend_capture"; New-Item -ItemType Directory -Force $out | Out-Null
$bnd=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$p=Start-Process $ue -ArgumentList "`"$proj`"","/Game/Wanefall/Maps/Wanefall_Lobby?game=/Script/WanefallGreybox.WanefallLobbyGameMode","-game","-windowed",("-ResX="+$bnd.Width),("-ResY="+$bnd.Height),"-nosplash" -PassThru
Start-Sleep -Seconds 80   # shaders cached from the prior lobby launch
try { $p.Refresh(); [Win]::ShowWindow($p.MainWindowHandle,3)|Out-Null; [Win]::SetForegroundWindow($p.MainWindowHandle)|Out-Null } catch {}
Start-Sleep -Milliseconds 1200
$bmp=New-Object System.Drawing.Bitmap $bnd.Width,$bnd.Height
$g=[System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($bnd.X,$bnd.Y,0,0,$bmp.Size)
$bmp.Save("$out\43_lobby_alien_textured.png"); $g.Dispose(); $bmp.Dispose()
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Write-Output "LOBBY_CAPTURE_DONE"