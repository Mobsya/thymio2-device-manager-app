# This file is part of tdm-launcher.
# Copyright 2022 ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE,
# Miniature Mobile Robots group, Switzerland
# Author: Yves Piguet

CC ?= gcc
SRC = thymio-2-device-manager.c
BIN = thymio-2-device-manager
PKG_CONFIG ?= pkg-config
PKGS = gtk+-3.0 gio-2.0
PKG_CFLAGS := $(shell $(PKG_CONFIG) --cflags $(PKGS))
PKG_LIBS := $(shell $(PKG_CONFIG) --libs $(PKGS))

$(BIN): $(SRC)
	$(CC) -o $@ $^ $(PKG_CFLAGS) $(PKG_LIBS)

clean:
	rm -f $(BIN)
