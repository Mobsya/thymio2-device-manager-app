# This file is part of tdm-launcher.
# Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
# Miniature Mobile Robots group, Switzerland
# Author: Yves Piguet

SRC = thymio-2-device-manager.swift
SWIFTC ?= swiftc
BUILD_DIR ?= build
APP_EXECUTABLE_NAME = thymio-2-device-manager
APP_EXECUTABLE = $(BUILD_DIR)/$(APP_EXECUTABLE_NAME)
APP_DISPLAY_NAME = Thymio 2 Device Manager
APP_BUNDLE_PATH = $(BUILD_DIR)/$(APP_DISPLAY_NAME).app
DMG_NAME = $(BUILD_DIR)/$(APP_EXECUTABLE_NAME).dmg
DMG_ROOT = $(BUILD_DIR)/dmg-root
DMG_VOLNAME ?= Thymio 2 Device Manager
APP_SIGN_IDENTITY ?=
NOTARY_PROFILE ?=
NOTARY_ZIP = $(BUILD_DIR)/$(APP_EXECUTABLE_NAME)-notarization.zip

.PHONY: all app clean dmg-root sign-app verify-app notarize-app staple-app \
	create-dmg sign-dmg verify-dmg notarize-dmg staple-dmg release

all: app

$(BUILD_DIR):
	mkdir -p "$@"

$(APP_EXECUTABLE): $(SRC) | $(BUILD_DIR)
	$(SWIFTC) -o "$@" $^

# app: assume a complete (statically-linked) tdm is available
# in this directory as thymio-device-manager.
app: $(APP_EXECUTABLE) thymio-device-manager Info.plist AppIcon.icns | $(BUILD_DIR)
	rm -Rf "$(APP_BUNDLE_PATH)"
	mkdir -p "$(APP_BUNDLE_PATH)/Contents/MacOS"
	mkdir -p "$(APP_BUNDLE_PATH)/Contents/Resources"
	cp Info.plist "$(APP_BUNDLE_PATH)/Contents"
	cp AppIcon.icns "$(APP_BUNDLE_PATH)/Contents/Resources"
	cp "$(APP_EXECUTABLE)" "$(APP_BUNDLE_PATH)/Contents/MacOS"
	cp thymio-device-manager "$(APP_BUNDLE_PATH)/Contents/MacOS"

sign-app:
	codesign --force --timestamp --sign "$(APP_SIGN_IDENTITY)" "$(APP_BUNDLE_PATH)/Contents/MacOS/thymio-device-manager"
	codesign --force --timestamp --sign "$(APP_SIGN_IDENTITY)" "$(APP_BUNDLE_PATH)/Contents/MacOS/$(APP_EXECUTABLE_NAME)"
	codesign --force --deep --options runtime --timestamp --sign "$(APP_SIGN_IDENTITY)" "$(APP_BUNDLE_PATH)"

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
	xcrun notarytool submit "$(DMG_NAME)" --keychain-profile "$(NOTARY_PROFILE)" --wait

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
	xcrun notarytool submit "$(NOTARY_ZIP)" --keychain-profile "$(NOTARY_PROFILE)" --wait

staple-app:
	xcrun stapler staple -v "$(APP_BUNDLE_PATH)"
	xcrun stapler validate -v "$(APP_BUNDLE_PATH)"


release:
	$(MAKE) app
	$(MAKE) sign-app
	$(MAKE) verify-app
# Optionally notarize the app here
	$(MAKE) dmg-root
	$(MAKE) create-dmg
	$(MAKE) sign-dmg
	$(MAKE) notarize-dmg
	$(MAKE) staple-dmg
	$(MAKE) verify-dmg

clean:
	rm -Rf "$(BUILD_DIR)"
