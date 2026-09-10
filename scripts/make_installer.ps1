#requires -Version 5.1
<#
  CodeAgent 一键生成正式安装包（带卸载程序）
  用法（建议右键“使用 PowerShell 运行”，需要管理员权限）：
      powershell -ExecutionPolicy Bypass -File .\scripts\make_installer.ps1

  脚本会自动：
    1. 查找本机 Inno Setup 6（未装则从官方/镜像下载并静默安装）；
    2. 编译 scripts\build_installer.iss；
    3. 输出 dist\CodeAgent-Setup-v1.0.0.exe
#>
param(
    [switch]$SkipInnoInstall   # 本机已装 Inno Setup 6 时可加此参数跳过下载
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

function Find-ISCC {
    $candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe',
        'C:\Program Files (x86)\Inno Setup 7\ISCC.exe',
        'C:\Program Files\Inno Setup 7\ISCC.exe'
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $w = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    return $w.Source
}

function Install-Inno {
    $versions = @('6_7_3', '6_6_1', '6_5_4')   # 依次尝试
    $tmp = Join-Path $env:TEMP 'innosetup-6.7.3.exe'
    $done = $false
    foreach ($v in $versions) {
        $url = "https://github.com/jrsoftware/issrc/releases/download/is-$v/innosetup-$($v.Replace('_','.')).exe"
        Write-Host "下载 Inno Setup $($v.Replace('_','.')): $url"
        for ($i = 1; $i -le 6; $i++) {
            Write-Host "  第 $i 次尝试..."
            & curl.exe -L -C - --fail --silent --show-error --connect-timeout 30 --max-time 300 -o $tmp $url
            if ($LASTEXITCODE -eq 0) { $done = $true; break }
        }
        if ($done) { break }
    }
    if (-not $done) {
        throw '下载 Inno Setup 失败：请确认网络可访问 github.com（可手动安装后重跑本脚本）。'
    }
    Write-Host '静默安装 Inno Setup ...'
    $p = Start-Process -FilePath $tmp -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Inno Setup 安装失败，退出码 $($p.ExitCode)" }
}

Write-Host '==== CodeAgent 安装包构建 ===='
$iscc = Find-ISCC
if (-not $iscc) {
    if ($SkipInnoInstall) {
        throw '未找到 ISCC.exe，且指定了 -SkipInnoInstall，无法编译。'
    }
    Install-Inno
    $iscc = Find-ISCC
    if (-not $iscc) { throw '安装后仍未找到 ISCC.exe。' }
}
Write-Host "使用编译器: $iscc"

Push-Location $Root
$ver = '1.0.0'
$verFile = Join-Path $Root 'VERSION'
if (Test-Path $verFile) { $ver = (Get-Content $verFile -Raw).Trim() }
Write-Host "构建版本: $ver"
try {
    & $iscc "/DMyAppVersion=$ver" "scripts\build_installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败，退出码 $LASTEXITCODE" }
} finally {
    Pop-Location
}
$out = Join-Path $Root "dist\CodeAgent-Setup-v$ver.exe"
if (Test-Path $out) {
    Write-Host ''
    Write-Host "✅ 安装包已生成：$out"
    Write-Host '双击它即可安装 CodeAgent（含桌面快捷方式选项与卸载程序）。'
} else {
    Write-Host '编译结束但未找到输出文件，请检查上面的 ISCC 输出。'
}
