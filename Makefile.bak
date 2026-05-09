# Makefile for xinmeng_rgb – Xinmeng M87 Linux RGB controller (C++)
#
# Usage:
#   make              – build the binary
#   make clean        – remove build artefacts
#   make install      – copy binary to /usr/local/bin (needs sudo)
#   make uninstall    – remove installed binary

CXX      ?= g++
CXXFLAGS  = -std=c++17 -O2 -Wall -Wextra
LDFLAGS   = $(shell pkg-config --libs hidapi-hidraw 2>/dev/null || echo "-lhidapi-hidraw")
CPPFLAGS  = $(shell pkg-config --cflags hidapi-hidraw 2>/dev/null || echo "-I/usr/include/hidapi")

TARGET  = xinmeng_rgb
SRC     = xinmeng_rgb.cpp

PREFIX  ?= /usr/local

.PHONY: all clean install uninstall

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) -o $@ $< $(LDFLAGS)
	@echo ""
	@echo "  Build successful!  Binary: ./$(TARGET)"
	@echo ""
	@echo "  Quick start:"
	@echo "    ./$(TARGET) detect"
	@echo "    ./$(TARGET) effect static --colour 255,0,0"
	@echo "    ./$(TARGET) effect wave"
	@echo "    ./$(TARGET) effect off"
	@echo ""

clean:
	rm -f $(TARGET)

install: $(TARGET)
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 $(TARGET) $(DESTDIR)$(PREFIX)/bin/$(TARGET)
	@echo "Installed to $(DESTDIR)$(PREFIX)/bin/$(TARGET)"

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/$(TARGET)
