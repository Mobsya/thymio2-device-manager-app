# This file is part of tdm-launcher.
# Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
# Miniature Mobile Robots group, Switzerland
# Author: Yves Piguet

CC ?= gcc
SRC = thymio-2-device-manager.c
BUILD_DIR ?= build
BIN_NAME = thymio-2-device-manager
BIN = $(BUILD_DIR)/$(BIN_NAME)
TDM_EXECUTABLE = thymio-device-manager
PKG_CONFIG ?= pkg-config
PKGS = gtk+-3.0 gio-2.0
PKG_CFLAGS := $(shell $(PKG_CONFIG) --cflags $(PKGS))
PKG_LIBS := $(shell $(PKG_CONFIG) --libs $(PKGS))

.PHONY: all clean copy-tdm

all: $(BIN) copy-tdm

$(BUILD_DIR):
	mkdir -p "$@"

$(BIN): $(SRC) | $(BUILD_DIR)
	$(CC) -o "$@" $^ $(PKG_CFLAGS) $(PKG_LIBS)

copy-tdm: | $(BUILD_DIR)
	@if [ -f "$(TDM_EXECUTABLE)" ]; then cp "$(TDM_EXECUTABLE)" "$(BUILD_DIR)/$(TDM_EXECUTABLE)"; fi

clean:
	rm -Rf "$(BUILD_DIR)"
