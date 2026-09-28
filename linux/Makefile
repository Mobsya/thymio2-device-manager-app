# This file is part of tdm-launcher.
# Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
# Miniature Mobile Robots group, Switzerland
# Author: Yves Piguet

CC ?= gcc
SRC = thymio-2-device-manager.c
BUILD_DIR ?= build
BIN_NAME = thymio-2-device-manager
BIN = $(BUILD_DIR)/$(BIN_NAME)
TDM_EXECUTABLE ?= thymio-device-manager
TDM_METADATA_DIR ?=
PYTHON ?= python3
APP_VERSION ?= $(shell cat ../VERSION.txt)
APP_BUILD ?= 1
PKG_CONFIG ?= pkg-config
PKGS = gtk+-3.0 gio-2.0 ayatana-appindicator3-0.1
PKG_CFLAGS = $(shell $(PKG_CONFIG) --cflags $(PKGS))
PKG_LIBS = $(shell $(PKG_CONFIG) --libs $(PKGS))
VERSION_CPPFLAGS = -DAPP_VERSION=\"$(APP_VERSION)\" -DAPP_BUILD=\"$(APP_BUILD)\"

.PHONY: all clean copy-tdm deb deb-podman test

all: $(BIN) copy-tdm

$(BUILD_DIR):
	mkdir -p "$@"

$(BIN): $(SRC) ../VERSION.txt | $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(VERSION_CPPFLAGS) -o "$@" $(SRC) $(PKG_CFLAGS) $(PKG_LIBS)

copy-tdm: | $(BUILD_DIR)
	$(PYTHON) ../scripts/tdm.py --platform linux-x64 --executable "$(TDM_EXECUTABLE)" --destination "$(BUILD_DIR)/thymio-device-manager" --metadata-dir "$(TDM_METADATA_DIR)" --metadata-destination "$(BUILD_DIR)/tdm"

$(BUILD_DIR)/launcher-tests/test-launcher: tests/test-launcher.c $(SRC)
	mkdir -p "$(@D)"
	$(CC) $(CPPFLAGS) $(VERSION_CPPFLAGS) -Wall -Wextra -o "$@" $< $(PKG_CFLAGS) $(PKG_LIBS)

test: $(BUILD_DIR)/launcher-tests/test-launcher
	dbus-run-session -- xvfb-run -a env NO_AT_BRIDGE=1 "$(BUILD_DIR)/launcher-tests/test-launcher"

deb deb-podman: export APP_VERSION := $(APP_VERSION)
deb deb-podman: export APP_BUILD := $(APP_BUILD)
deb deb-podman: export BUILD_DIR := $(BUILD_DIR)
deb deb-podman: export TDM_EXECUTABLE := $(TDM_EXECUTABLE)
deb deb-podman: export TDM_METADATA_DIR := $(TDM_METADATA_DIR)
deb deb-podman: export DEB_MAINTAINER := $(DEB_MAINTAINER)
deb:
	@python3 packaging/build-deb.py --check
	$(MAKE) --no-print-directory -B "$(BIN)"
	@python3 packaging/build-deb.py

deb-podman: export UBUNTU_MIRROR := $(UBUNTU_MIRROR)
deb-podman:
	@python3 packaging/build-deb.py --podman

clean:
	rm -Rf "$(BUILD_DIR)"
