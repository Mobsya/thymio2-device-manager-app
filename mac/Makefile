# This file is part of tdm-launcher.
# Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
# Miniature Mobile Robots group, Switzerland
# Author: Yves Piguet

SRC = thymio-2-device-manager.swift
SWIFTC ?= swiftc
PYTHON ?= python3
TDM_EXECUTABLE ?= thymio-device-manager
TDM_METADATA_DIR ?=
APP_VERSION ?= $(shell cat ../VERSION.txt)
APP_BUILD ?= 1
UNIVERSAL ?= 0
BUILD_DIR ?= build
APP_EXECUTABLE_NAME = thymio-2-device-manager
APP_EXECUTABLE = $(BUILD_DIR)/launcher-$(UNIVERSAL)/$(APP_EXECUTABLE_NAME)
APP_DISPLAY_NAME = Thymio 2 Device Manager
APP_BUNDLE_PATH = $(BUILD_DIR)/$(APP_DISPLAY_NAME).app
DMG_NAME = $(BUILD_DIR)/$(APP_EXECUTABLE_NAME).dmg
DMG_ROOT = $(BUILD_DIR)/dmg-root
DMG_VOLNAME ?= Thymio 2 Device Manager
APP_SIGN_IDENTITY ?=
NOTARY_PROFILE ?=
NOTARY_KEYCHAIN ?=
NOTARY_KEYCHAIN_ARG = $(if $(NOTARY_KEYCHAIN),--keychain "$(NOTARY_KEYCHAIN)")
NOTARY_ZIP = $(BUILD_DIR)/$(APP_EXECUTABLE_NAME)-notarization.zip

.PHONY: all app clean dmg-root sign-app verify-app notarize-app staple-app \
	create-dmg sign-dmg verify-dmg notarize-dmg staple-dmg release dmg

all: app

$(BUILD_DIR):
	mkdir -p "$@"

$(APP_EXECUTABLE): $(SRC) Makefile | $(BUILD_DIR)
	mkdir -p "$(@D)"
ifeq ($(UNIVERSAL),1)
	$(SWIFTC) -target x86_64-apple-macosx11.0 -o "$@-x86_64" $(SRC)
	$(SWIFTC) -target arm64-apple-macosx11.0 -o "$@-arm64" $(SRC)
	lipo -create "$@-x86_64" "$@-arm64" -output "$@"
else
	$(SWIFTC) -target $(shell uname -m)-apple-macosx11.0 -o "$@" $(SRC)
endif
	codesign --force --sign - "$@"

# Backend paths are recipe arguments, not Make prerequisites: spaces are valid.
app: $(APP_EXECUTABLE) Info.plist AppIcon.icns | $(BUILD_DIR)
	$(PYTHON) ../scripts/tdm.py --platform $(if $(filter 1,$(UNIVERSAL)),macos-universal,macos) --executable "$(TDM_EXECUTABLE)"
	rm -Rf "$(APP_BUNDLE_PATH)"
	mkdir -p "$(APP_BUNDLE_PATH)/Contents/MacOS"
	mkdir -p "$(APP_BUNDLE_PATH)/Contents/Resources"
	cp Info.plist "$(APP_BUNDLE_PATH)/Contents"
	cp AppIcon.icns "$(APP_BUNDLE_PATH)/Contents/Resources"
	cp "$(APP_EXECUTABLE)" "$(APP_BUNDLE_PATH)/Contents/MacOS"
	$(PYTHON) ../scripts/tdm.py --platform macos --executable "$(TDM_EXECUTABLE)" --destination "$(APP_BUNDLE_PATH)/Contents/MacOS/thymio-device-manager" --metadata-dir "$(TDM_METADATA_DIR)" --metadata-destination "$(APP_BUNDLE_PATH)/Contents/Resources/tdm"
	/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $(APP_VERSION)" "$(APP_BUNDLE_PATH)/Contents/Info.plist"
	/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $(APP_BUILD)" "$(APP_BUNDLE_PATH)/Contents/Info.plist"
	@if codesign --verify "$(APP_BUNDLE_PATH)/Contents/MacOS/thymio-device-manager" >/dev/null 2>&1; then \
		codesign --force --sign - "$(APP_BUNDLE_PATH)"; \
	else \
		echo "Local backend is unsigned; preserving it and leaving the app bundle unsealed."; \
	fi

sign-app:
	test -n "$(APP_SIGN_IDENTITY)" || (echo "Set APP_SIGN_IDENTITY to a Developer ID Application identity." && false)
	codesign --force --options runtime --timestamp --sign "$(APP_SIGN_IDENTITY)" "$(APP_BUNDLE_PATH)/Contents/MacOS/thymio-device-manager"
	codesign --force --options runtime --timestamp --sign "$(APP_SIGN_IDENTITY)" "$(APP_BUNDLE_PATH)"

verify-app:
	codesign --verify --deep --strict --verbose=2 "$(APP_BUNDLE_PATH)"
	codesign -dvv "$(APP_BUNDLE_PATH)/Contents/MacOS/$(APP_EXECUTABLE_NAME)" 2>&1 | grep -q "Authority=Developer ID Application:"
	codesign -dvv "$(APP_BUNDLE_PATH)/Contents/MacOS/$(APP_EXECUTABLE_NAME)" 2>&1 | grep -q "^Timestamp="
	codesign -dvv "$(APP_BUNDLE_PATH)/Contents/MacOS/thymio-device-manager" 2>&1 | grep -q "Authority=Developer ID Application:"
	codesign -dvv "$(APP_BUNDLE_PATH)/Contents/MacOS/thymio-device-manager" 2>&1 | grep -q "^Timestamp="
	spctl --assess --type execute --verbose=4 "$(APP_BUNDLE_PATH)"

dmg-root:
	rm -Rf "$(DMG_ROOT)"
	mkdir -p "$(DMG_ROOT)"
	cp -R "$(APP_BUNDLE_PATH)" "$(DMG_ROOT)/"
	ln -s /Applications "$(DMG_ROOT)/Applications"

create-dmg:
	hdiutil create -volname "$(DMG_VOLNAME)" -srcfolder "$(DMG_ROOT)" -ov -format UDZO "$(DMG_NAME)"

sign-dmg:
	codesign --force --timestamp --sign "$(APP_SIGN_IDENTITY)" "$(DMG_NAME)"

notarize-dmg:
	test -n "$(NOTARY_PROFILE)" || (echo "Set NOTARY_PROFILE to a notarytool keychain profile." && false)
	xcrun notarytool submit "$(DMG_NAME)" --keychain-profile "$(NOTARY_PROFILE)" $(NOTARY_KEYCHAIN_ARG) --wait --timeout 30m

staple-dmg:
	xcrun stapler staple "$(DMG_NAME)"
	xcrun stapler validate "$(DMG_NAME)"

verify-dmg:
	codesign --verify --verbose=2 "$(DMG_NAME)"
	spctl --assess --type open --context context:primary-signature --verbose=4 "$(DMG_NAME)"

notarize-app:
	test -n "$(NOTARY_PROFILE)" || (echo "Set NOTARY_PROFILE to a notarytool keychain profile." && false)
	rm -f "$(NOTARY_ZIP)"
	ditto -c -k --keepParent "$(APP_BUNDLE_PATH)" "$(NOTARY_ZIP)"
	xcrun notarytool submit "$(NOTARY_ZIP)" --keychain-profile "$(NOTARY_PROFILE)" $(NOTARY_KEYCHAIN_ARG) --wait --timeout 30m

staple-app:
	xcrun stapler staple -v "$(APP_BUNDLE_PATH)"
	xcrun stapler validate -v "$(APP_BUNDLE_PATH)"


dmg:
	$(MAKE) app
	$(MAKE) dmg-root
	$(MAKE) create-dmg

release:
	$(MAKE) app
	$(MAKE) sign-app
	$(MAKE) notarize-app
	$(MAKE) staple-app
	$(MAKE) verify-app
	$(MAKE) dmg-root
	$(MAKE) create-dmg
	$(MAKE) sign-dmg
	$(MAKE) notarize-dmg
	$(MAKE) staple-dmg
	$(MAKE) verify-dmg

clean:
	rm -Rf "$(BUILD_DIR)"
