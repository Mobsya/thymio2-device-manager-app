# Thymio 2 Device Manager

Thymio 2 Device Manager provides a minimal user interface to control the Thymio Device Manager (TDM) backend. It adds a menu with About and Quit or Exit entries as a status item on macOS or a tray item on Linux; Windows provides an Exit entry. The TDM is launched as a subprocess, and the launcher only terminates the subprocess it started.

The Thymio Device Manager backend doesn't require any modification.

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
- GTK 3 and Ayatana AppIndicator development headers and libraries, including GLib/GIO.
- A Linux `thymio-device-manager` executable at `linux/thymio-device-manager` if you want the Makefile to copy it next to the launcher in `linux/build/`.
- A graphical desktop session. AppIndicator support enables the optional tray icon.

Common distro package commands:

```sh
# Debian/Ubuntu
sudo apt install build-essential pkg-config libgtk-3-dev libayatana-appindicator3-dev

# Fedora
sudo dnf install gcc make pkgconf-pkg-config gtk3-devel libayatana-appindicator-gtk3-devel

# Arch Linux
sudo pacman -S base-devel pkgconf gtk3 libayatana-appindicator
```

## Quick local builds

Ordinary builds use the executable you supply. They never download TDM, consult
GitHub releases, or require Apple credentials. Existing default locations still
work:

```sh
make -C mac
make -C linux
dotnet build win/thymio-2-device-manager.csproj -c Release
```

To test another backend without replacing the checked-in executable:

```sh
make -C mac TDM_EXECUTABLE="/absolute/path/my backend/thymio-device-manager"
make -C linux TDM_EXECUTABLE="/absolute/path/my backend/thymio-device-manager"
dotnet build win/thymio-2-device-manager.csproj -c Release \
  -p:TdmExecutable="/absolute/path/my backend/thymio-device-manager.exe"
```

Run only the command for your platform. Relative backend paths are resolved from
the respective `mac`, `linux`, or `win` directory. The source can have any
filename: builds copy it under the canonical name the launcher expects.
Windows also copies neighboring `*.dll` files. Keep each backend's dependencies
in its own source directory; use a fresh build directory or `dotnet clean` when
switching between backends with different DLL sets.

Missing files, incompatible executable formats, and missing Unix executable
permissions cause an error instead of silently substituting another backend.
The supplied binary is copied unchanged; Mac release signing changes only the
bundled copy. Normal Mac builds compile the launcher for the host architecture
and ad-hoc sign the launcher without Developer ID credentials. When the supplied
backend is signed, the app bundle is also ad-hoc signed; an unsigned backend is
preserved and the local app bundle is left unsealed. Choose a
backend compatible with that Mac (or an Intel backend where Rosetta is available).

The same overrides work with `make -C mac dmg`, `make -C linux deb`,
`make -C linux deb-podman`, and `dotnet publish`. For example, create a local
Mac disk image without notarization:

```sh
make -C mac dmg TDM_EXECUTABLE="/absolute/path/to/thymio-device-manager"
```

For a universal Mac launcher, add `UNIVERSAL=1`; this requires a universal backend
containing both Intel and Apple Silicon code. Local compilation still requires
the installed platform SDKs/libraries, and a first .NET restore needs NuGet access.

`VERSION.txt` supplies the default wrapper version. `APP_VERSION` and `APP_BUILD`
can override Mac/Linux metadata; `-p:AppVersion=1.2.3` overrides Windows metadata.
`TDM_VERSION` is used only by the explicit release downloader, never by ordinary
local builds.

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

The Linux launcher is implemented in C with GTK 3 and Ayatana AppIndicator. It opens a small status window and provides a tray menu with Show Status, About, and Quit actions. The window reports backend startup failures and unexpected exits. Launching the application again presents the existing window without starting another backend.

When an AppIndicator tray is available, closing the status window keeps the manager in the tray. Without a tray, the window stays available and closing it stops the manager. Quit always stops the subprocess started by this launcher.

At startup, the Linux launcher starts its own `thymio-device-manager` subprocess. It does not kill existing `thymio-device-manager` processes or remove lock files that may belong to another instance.

## Building on Windows

With the Windows prerequisites installed, run:

```sh
dotnet build win/thymio-2-device-manager.csproj -c Release
```

This produces `thymio-2-device-manager.exe` under `win/build/bin/Release/net8.0-windows/`, with the display name **Thymio 2 Device Manager**.

## Publishing a distributable `.exe`

To publish a single-file Windows x86 build from macOS, Linux, or Windows with the .NET 8 SDK or a newer SDK that can target `net8.0-windows`, first place the Windows TDM executable at `win/thymio-device-manager.exe`. A macOS or Linux binary cannot be used in its place.

From the repository root, run:

```sh
dotnet publish win/thymio-2-device-manager.csproj \
  -c Release \
  -r win-x86 \
  --self-contained true \
  -p:PublishSingleFile=true \
  -p:IncludeAllContentForSelfExtract=true \
  -p:DebugType=embedded
```

Distribute the resulting executable:

```text
win/build/bin/Release/net8.0-windows/win-x64/publish/thymio-2-device-manager.exe
```

This bundles the launcher, the .NET runtime, and `thymio-device-manager.exe` into one file. Users do not need to install .NET or keep a separate TDM executable beside the launcher. The bundled files are automatically extracted to disk at startup, and the launcher starts TDM from the extraction directory.

The Windows TDM executable must be present before building or publishing;
validation fails if it is missing or is not a Windows x64 executable. Bonjour
service and USB drivers still need to be installed separately. Test the published
executable on Windows before distribution. The diagnostic command
`thymio-2-device-manager.exe --check-backend` checks discovery, extraction, and DLL loading by
running the backend's `--help` command without opening the tray application.
It returns zero on success (TDM itself returns one for `--help`).

For a regular `dotnet build`, the project instead copies `win/thymio-device-manager.exe` next to the launcher, where it must remain.

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

On some Linux desktop environments, AppIndicator support depends on the desktop shell configuration or an installed tray extension. The status window works without a tray, including on Wayland.

## Building a Debian package

Packages target **Ubuntu 24.04+ and Debian 13+ on x86-64**. From Arch Linux or
Manjaro, use the Podman target to compile and package inside Ubuntu 26.04 LTS while
keeping the resulting `.deb` in your local checkout.

### Building locally with Podman

Install the host prerequisites on Arch Linux or Manjaro:

```sh
sudo pacman -S --needed podman make python
```

With rootless Podman configured for your user and the backend executable at
`linux/thymio-device-manager`, run from the repository root without `sudo`:

```sh
make -C linux deb-podman \
  APP_VERSION=1.0.0 APP_BUILD=1 \
  DEB_MAINTAINER='Mobsya <mobsya@mobsya.org>'
```

The result is `linux/build/thymio-2-device-manager_1.0.0-1_amd64.deb`, owned by
your user. No GTK development libraries or Debian packaging tools are required
on the host. The first build downloads Ubuntu 26.04 LTS and installs the build
dependencies into the image `localhost/thymio-deb-builder:ubuntu-26.04`.
It uses the Ubuntu 26.04-based `buildpack-deps:resolute-curl` image, which includes
CA certificates, and downloads Ubuntu packages over HTTPS from the Init7 mirror
in Switzerland. Subsequent builds reuse those image layers. To choose another
mirror, add `UBUNTU_MIRROR=https://archive.ubuntu.com/ubuntu` to the make command.

The container mounts the source and backend read-only and builds as your user
using `--userns=keep-id`. Intermediate container outputs go under
`linux/build/podman/`; the final package is placed directly in `linux/build/`.
The packaging step runs without network access. The `BUILD_DIR` and
`TDM_EXECUTABLE` overrides also work, including a backend outside the checkout.

To refresh the cached Ubuntu image and build dependencies, run:

```sh
podman build --platform=linux/amd64 --pull=always --no-cache \
  --tag localhost/thymio-deb-builder:ubuntu-26.04 \
  --file linux/packaging/Containerfile linux/packaging
```

If using a custom mirror, also pass `--build-arg UBUNTU_MIRROR=<mirror-url>`
when refreshing the image.

Then run `make -C linux deb-podman` again with the release metadata above.

### Building natively on Ubuntu

Alternatively, use an updated **Ubuntu 26.04 LTS amd64** machine or VM. The native
packaging target uses the Debian/Ubuntu package database to determine runtime
dependencies. Building on a newer release can introduce newer library
requirements. Validate every release on Ubuntu 26.04 and on any older
distribution you intend to support; dependency detection alone is not a
compatibility test.

Install the build and packaging prerequisites:

```sh
sudo apt update
sudo apt install build-essential pkg-config libgtk-3-dev libayatana-appindicator3-dev dpkg-dev python3 \
  desktop-file-utils libavahi-client3 libavahi-common3 libstdc++6
```

Place the Linux x86-64 `thymio-device-manager` executable at
`linux/thymio-device-manager`, with its executable bit set. Packaging requires
this file and copies it unchanged. Both the launcher and the backend must have
all their required shared libraries and symbols available on the build machine.
The current backend requires recent glibc and C++ runtime libraries; Ubuntu 22.04,
Debian 12, and ARM builds are outside this package's supported targets.

Build without `sudo`, supplying the release maintainer's name and email:

```sh
make -C linux deb \
  APP_VERSION=1.0.0 APP_BUILD=1 \
  DEB_MAINTAINER='Mobsya <mobsya@mobsya.org>'
```

This produces `linux/build/thymio-2-device-manager_1.0.0-1_amd64.deb`.
`APP_VERSION` and `APP_BUILD` default to `1.0.0` and `1`; `DEB_MAINTAINER` is
required. Use a non-empty Debian revision for `APP_BUILD`, such as `1` or `2`.
The launcher is rebuilt each time to keep its About dialog synchronized with
these values. Runtime dependencies are generated from both executables using
`dpkg-shlibdeps`, and include an explicit dependency on `udev`. Packaging fails
if dependency analysis finds missing libraries or unresolved symbols.

### Installing and launching

Copy the `.deb` to the user's machine and install it with APT so dependencies
are installed automatically:

```sh
sudo apt install ./thymio-2-device-manager_1.0.0-1_amd64.deb
```

Open **Thymio 2 Device Manager** from the application menu, or run
`thymio-2-device-manager` from a terminal as your normal desktop user. The package
does not start the application automatically or install a background service.
A graphical desktop session is required; tray support is optional.

The launcher and backend are installed together under
`/usr/lib/thymio-2-device-manager/`. The command in `/usr/bin/` is a symlink to the
launcher, which continues to find the backend beside its own executable.

If the application appears to do nothing, make sure you have the current package:
older launchers used only the legacy X11 tray API and could be invisible on
Wayland. The current launcher always opens a status window. On Ubuntu GNOME,
enable the Ubuntu AppIndicators extension in the Extensions application if you
also want the tray icon. No extension is required to use the status window.

For startup diagnostics, run `thymio-2-device-manager` in a terminal as your
desktop user. Backend output goes to that terminal; startup errors and exit
status also appear in the status window. When replacing an older invisible
launcher, log out and back in before launching the updated version so the old
process does not handle the new launch request.

### USB access

The package owns `/usr/lib/udev/rules.d/70-thymio-device-manager.rules`:

```udev
# Thymio II and wireless dongles: allow the active local desktop user USB access.

SUBSYSTEM=="usb", ATTR{idVendor}=="0617", ATTR{idProduct}=="000a", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0617", ATTR{idProduct}=="000c", TAG+="uaccess"
```

The `70-` prefix ensures these tags are present before `73-seat-late.rules`
applies access permissions. Access is granted to the active local desktop user
through the system's udev/logind session management; it does not grant access to
every user or to an SSH-only session.

Installation and upgrades reload the rules and request change events only for
the two matching USB devices. If udev is unavailable during installation, the
package can still be installed; the rules apply when udev starts. Reconnect the
robot or dongle if access is not refreshed immediately, and make sure you are
using an active local desktop session. Administrator overrides with the same
filename under `/etc/udev/rules.d/` take precedence and are preserved.

Remove the package with:

```sh
sudo apt remove thymio-2-device-manager
# To also purge any package configuration state:
sudo apt purge thymio-2-device-manager
```

Removal deletes the packaged rules and reloads udev. Reconnect previously
connected devices to refresh their permissions after removal.

### Checking a release

The launcher regression tests use a private D-Bus session and virtual display.
On a Debian/Ubuntu development machine with the build prerequisites installed:

```sh
sudo apt install dbus-daemon xvfb xauth
make -C linux test
```

They exercise the visible status window without a tray, AppIndicator registration
and tray loss, repeated activation, About, startup failures, unexpected exits,
and graceful/forced Quit using disposable backend fixtures under `linux/build/`.

Run the packaging regression tests from the repository root:

```sh
python3 -B -m unittest discover -s linux/packaging -p 'test_*.py'
```

These tests check package staging, validation failures, and maintainer scripts
using isolated substitutes for Debian tools and udev. They do not install a
package or modify USB permissions. Inspect the real artifact separately:

```sh
dpkg-deb --info linux/build/thymio-2-device-manager_1.0.0-1_amd64.deb
dpkg-deb --contents linux/build/thymio-2-device-manager_1.0.0-1_amd64.deb
```

Before distributing a release, install it on Ubuntu 26.04, Ubuntu 24.04, and Debian 13, upgrade
it with a higher `APP_BUILD`, then remove and purge it. Check the application-menu
entry, About version, and Quit behavior. On desktops with hardware, verify that
both `0617:000a` and `0617:000c` are usable without `sudo`, including when connected
before installation. Verify package installation in an offline environment where
udev is not running as well.
