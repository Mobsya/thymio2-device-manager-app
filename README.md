# TDM Launcher

Minimum user interface to control the Thymio Device Manager. Adds a menu with a Quit or Exit entry as a status item on macOS or a tray item on Windows and Linux. The TDM is launched as a subprocess, and the launcher only terminates the subprocess it started.

The Thymio Device Manager doesn't require any modification.

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

The `mac/Makefile` includes helper targets for this flow. First, store your notary credentials in the keychain once:

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

This target signs `thymio-2-device-manager.app`, notarizes and staples it, creates `thymio-2-device-manager.dmg`, signs the DMG, notarizes it, and staples the final disk image.

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
codesign -dvv mac/thymio-2-device-manager.app/Contents/MacOS/thymio-2-device-manager
codesign -dvv mac/thymio-2-device-manager.app/Contents/MacOS/thymio-device-manager
```

## Windows

The application is implemented in C# as a WinForms app targeting the modern .NET SDK.

## Linux

The Linux launcher is implemented in C with GTK 3. It follows the same minimal style as the macOS app: a tray icon, a single Quit action, and a child process for `thymio-device-manager`.

At startup, the Linux launcher starts its own `thymio-device-manager` subprocess. It does not kill existing `thymio-device-manager` processes or remove lock files that may belong to another instance.

## Building on Windows

Install the .NET 8 SDK, then run:

```sh
dotnet build win/TDMLauncher.csproj -c Release
```

This produces the launcher executable under `win/bin/Release/net8.0-windows/`.

## Publishing a distributable `.exe`

To publish a Windows x86 build from any machine with the .NET 8 SDK:

```sh
dotnet publish win/TDMLauncher.csproj -c Release -r win-x86 --self-contained true /p:PublishSingleFile=true
```

The published executable is written under:

```text
win/bin/Release/net8.0-windows/win-x86/publish/
```

The launcher expects `thymio-device-manager.exe` in the same directory as `TDMLauncher.exe`.
If you place `win/thymio-device-manager.exe` before building or publishing, the project copies it automatically next to the launcher in both outputs.

## Cross-building Windows from macOS or Linux

The Windows project uses `EnableWindowsTargeting`, so `dotnet build` and `dotnet publish` can target Windows from macOS or Linux with the current .NET SDK.
The resulting executable is still a Windows program and must be run on Windows.

## Building on Linux

Install the GTK 3 development package for your distribution, then run:

```sh
make -C linux
```

This produces the launcher executable under `linux/`.

The launcher expects `thymio-device-manager` in the same directory as `thymio-2-device-manager`.

On some Linux desktop environments, tray icon support depends on the desktop shell configuration or an installed tray extension.
