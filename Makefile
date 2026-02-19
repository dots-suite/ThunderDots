# --- Paths (relative to repo root) ---
GO_PKG_DIR := thunderdots/native/go/cmd/thunderdots
BUILD_DIR  := thunderdots/native/build
LIB_NAME   := thunderdots

# --- OS detection ---
UNAME_S := $(shell uname -s 2>/dev/null || echo Windows_NT)

ifeq ($(UNAME_S),Darwin)
    LIB_EXT := dylib
else ifeq ($(UNAME_S),Linux)
    LIB_EXT := so
else
    # Windows (Git Bash / MSYS / cmd)
    LIB_EXT := dll
endif

LIB_FILE := $(BUILD_DIR)/lib$(LIB_NAME).$(LIB_EXT)

# Optional: choose arch on mac (arm64/x86_64)
# Usage: make build_go_native ARCH=arm64
ARCH ?=

.PHONY: build_go_native clean_go_native tidy_go_native

tidy_go_native:
	@echo "==> go mod tidy"
	cd $(GO_PKG_DIR) && go mod tidy

clean_go_native:
	@echo "==> clean build dir"
	rm -rf $(BUILD_DIR)
	mkdir -p $(BUILD_DIR)

build_go_native: tidy_go_native clean_go_native
	@echo "==> building c-shared: $(LIB_FILE)"
	# On macOS you can force the target arch with ARCH=arm64 or ARCH=amd64
	@if [ "$(UNAME_S)" = "Darwin" ] && [ -n "$(ARCH)" ]; then \
		echo "==> GOARCH=$(ARCH)"; \
		cd $(GO_PKG_DIR) && GOARCH=$(ARCH) go build -buildmode=c-shared -o ../../../build/$(notdir $(LIB_FILE)) . ; \
	else \
		cd $(GO_PKG_DIR) && go build -buildmode=c-shared -o ../../../build/$(notdir $(LIB_FILE)) . ; \
	fi
	@echo "✅ built: $(LIB_FILE)"