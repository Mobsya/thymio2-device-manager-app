# TDM Launcher

Minimum user interface to control the Thymio Device Manager. Adds a menu with About and Quit or Exit entries as a status item on macOS or a tray item on Linux; Windows provides an Exit entry. The TDM is launched as a subprocess, and the launcher only terminates the subprocess it started.

The Thymio Device Manager doesn't require any modification.

## Prerequisites

### macOS

- macOS with Xcode Command Line Tools or Xcode installed. This provides `make`, `swiftc`, `codesign`, `ditto`, `hdiutil`, `xcrun`, `stapler`, and `spctl`.
- A built macOS `thymio-device-manager` executable at `mac/thymio-device-manager`. The Makefile copies this file into the generated `.app` bundle.
- For signed releases outside the Mac App Store, an Apple Developer account, a `Developer ID Application` certificate in the keychain, and a notarytool keychain profile.

Install the Xcode Command Line Tools with:

```sh
xcode-select --install
```

### Windows

- .NET 8 SDK or a newer .NET SDK that can target `net8.0-windows`.
- Network access on first restore/build so NuGet packages and Windows targeting/runtime packs can be downloaded when needed.
- A Windows `thymio-device-manager.exe` at `win/thymio-device-manager.exe` if you want the build to copy it next to `TDMLauncher.exe`.
- Windows is required to run the generated launcher, even when cross-building it from macOS or Linux.

### Linux

- GNU Make.
- A C compiler such as `gcc`.
- `pkg-config`.
- GTK 3 development headers and libraries, including GLib/GIO.
- A Linux `thymio-device-manager` executable at `linux/thymio-device-manager` if you want the Makefile to copy it next to the launcher in `linux/build/`.
- A desktop environment with tray/status icon support for normal runtime behavior.

Common distro package commands:

```sh
# Debian/Ubuntu
sudo apt install build-essential pkg-config libgtk-3-dev

# Fedora
sudo dnf install gcc make pkgconf-pkg-config gtk3-devel

# Arch Linux
sudo pacman -S base-devel pkgconf gtk3
```

## macOS

The application is implemented in Swift. As a command-line program, it can be compiled with the `swiftc` compiler. It expects a command `thymio-device-manager` in the same directory. This can be bundled as a standard self-contained Mac application in a `.app` directory.

At startup, the application launches its own `thymio-device-manager` subprocess. It does not kill existing `thymio-device-manager` processes or remove lock files that may belong to another instance.

### Signing and notarizing the macOS app

If you distribute the app outside the Mac App Store, the warning:

```text
Apple could not verify "...app" is free of malware
```

usually means the app was copied into a `.dmg` without the full Apple release flow. To avoid that warning, you need all of the following:

1. Sign the bundled executable code with a `Developer ID Application` certificate.
2. Enable the hardened runtime when signing.
3. Submit the app or disk image to Apple's notary service with `xcrun notarytool`.
4. Staple the notarization ticket to the final `.app` and `.dmg`.

The `mac/Makefile` includes helper targets for this flow. Generated files are written under `mac/build/`.
First, store your notary credentials in the keychain once:

```sh
xcrun notarytool store-credentials tdm-notary \
  --apple-id "<apple-id>" \
  --team-id "<team-id>" \
  --password "<app-specific-password>"
```

Then build, sign, notarize, and staple the app and DMG:

```sh
make -C mac release \
  APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)" \
  NOTARY_PROFILE="tdm-notary"
```

This target signs `mac/build/Thymio 2 Device Manager.app`, notarizes and staples it, creates `mac/build/thymio-2-device-manager.dmg`, signs the DMG, notarizes it, and staples the final disk image.

You can also run the steps individually:

```sh
make -C mac sign-app APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)"
make -C mac notarize-app APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)" NOTARY_PROFILE="tdm-notary"
make -C mac staple-app APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)" NOTARY_PROFILE="tdm-notary"
make -C mac sign-dmg APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)"
make -C mac notarize-dmg APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)" NOTARY_PROFILE="tdm-notary"
make -C mac staple-dmg APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)" NOTARY_PROFILE="tdm-notary"
```

To verify locally:

```sh
make -C mac verify-app
make -C mac verify-dmg
```

Expected successful checks include:

```text
spctl: accepted
source=Notarized Developer ID
```

If notarization reports `The binary is not signed with a valid Developer ID certificate.`, check the certificate you passed in `APP_SIGN_IDENTITY`. It must be a `Developer ID Application:` certificate, not `Apple Development`, `Mac App Distribution`, or `Developer ID Installer`.

To list the code-signing identities available on the machine:

```sh
security find-identity -v -p codesigning
```

To inspect the actual authority and timestamp attached to each executable inside the app:

```sh
codesign -dvv "mac/build/Thymio 2 Device Manager.app/Contents/MacOS/thymio-2-device-manager"
codesign -dvv "mac/build/Thymio 2 Device Manager.app/Contents/MacOS/thymio-device-manager"
```

## Windows

The application is implemented in C# as a WinForms app targeting the modern .NET SDK.

## Linux

The Linux launcher is implemented in C with GTK 3. It follows the same minimal style as the macOS app: a tray icon, About and Quit actions, and a child process for `thymio-device-manager`.

At startup, the Linux launcher starts its own `thymio-device-manager` subprocess. It does not kill existing `thymio-device-manager` processes or remove lock files that may belong to another instance.

## Building on Windows

With the Windows prerequisites installed, run:

```sh
dotnet build win/TDMLauncher.csproj -c Release
```

This produces the launcher executable under `win/build/bin/Release/net8.0-windows/`.

## Publishing a distributable `.exe`

To publish a Windows x86 build from any machine with the .NET 8 SDK:

```sh
dotnet publish win/TDMLauncher.csproj -c Release -r win-x86 --self-contained true /p:PublishSingleFile=true
```

The published executable is written under:

```text
win/build/bin/Release/net8.0-windows/win-x86/publish/
```

The launcher expects `thymio-device-manager.exe` in the same directory as `TDMLauncher.exe`.
If you place `win/thymio-device-manager.exe` before building or publishing, the project copies it automatically next to the launcher in both outputs.

## Cross-building Windows from macOS or Linux

The Windows project uses `EnableWindowsTargeting`, so `dotnet build` and `dotnet publish` can target Windows from macOS or Linux with the current .NET SDK.
The resulting executable is still a Windows program and must be run on Windows.

## Building on Linux

With the Linux prerequisites installed, run:

```sh
make -C linux
```

This produces the launcher executable under `linux/build/`.

The launcher expects `thymio-device-manager` in the same directory as `thymio-2-device-manager`.
If `linux/thymio-device-manager` exists when building, the Makefile copies it into `linux/build/`.

On some Linux desktop environments, tray icon support depends on the desktop shell configuration or an installed tray extension.
