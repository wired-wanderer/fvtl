# Linux Build Guide — forza-painter-geometrize-gpu

This documents how to build the geometrize CLI generator on Linux, for
integration into a Python/PyQt or PySide FH6 vinyl tool.

Upstream source: https://github.com/zjl88858/forza-painter-geometrize-gpu
(MIT licensed — see LICENSE / THIRD_PARTY_NOTICES.md in this bundle).

## TL;DR

- The **OpenCL backend builds on Linux with zero source changes** — it's
  the default backend (`-backend opencl`, or just omit the flag).
- The **Vulkan backend** needs one small patch (included here as
  `vulkan_linux_cgo.patch` / already applied in `vulkan.go`) because the
  upstream `#cgo` directive only defines link flags for Windows.
- Nothing else in the codebase is Windows-specific (no `//go:build windows`
  files, no Win32 API calls, no hardcoded paths outside `vulkan.go`).

## 1. Build dependencies

```bash
# Go toolchain (>= 1.23, go.mod requires 1.23.0 / toolchain 1.24.12)
sudo apt install golang-go

# OpenCL backend (default) — headers + ICD loader for building
sudo apt install ocl-icd-opencl-dev opencl-headers

# Vulkan backend (optional) — headers + loader for building
sudo apt install libvulkan-dev vulkan-tools
```

## 2. Runtime dependencies (on the machine that will *run* generation)

Pick whichever backend you plan to ship. You don't need both.

```bash
# OpenCL runtime — one of these depending on GPU vendor
sudo apt install mesa-opencl-icd       # AMD / Intel iGPU (Mesa Rusticl/Clover)
# NVIDIA: proprietary driver usually ships its own OpenCL ICD already

# Vulkan runtime — usually already present on any system with a
# desktop GPU driver (Mesa RADV/ANV/Zink, or NVIDIA's proprietary driver)
sudo apt install libvulkan1
```

Sanity check before debugging build issues:

```bash
clinfo          # should list at least one OpenCL platform/device
vulkaninfo      # should list at least one Vulkan device
```

If `clinfo`/`vulkaninfo` show nothing, the problem is the GPU driver /
ICD registration, not this Go program.

## 3. Apply the Vulkan Linux/macOS patch (only if you want the Vulkan backend)

The file `vulkan.go` in this bundle is already patched. To apply it to a
fresh clone of upstream instead:

```bash
cd forza-painter-geometrize-gpu
patch -p1 < vulkan_linux_cgo.patch
# or: cp /path/to/vulkan.go internal/gpu/vulkan.go
```

The change is one addition to the cgo preamble at the top of
`internal/gpu/vulkan.go`:

```c
#cgo windows CFLAGS: -IC:/VulkanSDK/1.4.350.0/Include
#cgo windows LDFLAGS: -LC:/VulkanSDK/1.4.350.0/Lib -lvulkan-1
#cgo linux LDFLAGS: -lvulkan
#cgo darwin LDFLAGS: -lvulkan
```

Consider upstreaming this one-line patch as a PR to
`zjl88858/forza-painter-geometrize-gpu` — it's small, non-invasive, and
saves other Linux users the same investigation.

## 4. Build

```bash
cd forza-painter-geometrize-gpu
go build -o forza-painter-geometrize-linux ./cmd/forza-painter-geometrize
```

The binary is self-contained aside from the dynamically-linked OpenCL/Vulkan
loader (no Go runtime install needed on the target machine, same as the
Windows exe).

## 5. Smoke test

```bash
./forza-painter-geometrize-linux \
    --settings settings/c.ini \
    --preview /tmp/preview \
    --output /tmp/test-output \
    demo/ayylmao.png
```

Expected: progress lines printed to stdout ending in `FINISHED`, and
`/tmp/test-output.json` + periodic `/tmp/preview.<N>.png` snapshots written.

## 6. Backend selection at runtime

```bash
./forza-painter-geometrize-linux --backend opencl ...   # default
./forza-painter-geometrize-linux --backend vulkan ...   # needs the patch above
```

If you want to auto-detect and fall back, the simplest approach on the
Python side is: try `opencl` first, and if the process exits non-zero
within the first second (device init failure), retry with `vulkan`.

## 7. Packaging notes for your PyQt/PySide tool

- Ship the compiled binary alongside your app (e.g. `bin/forza-painter-geometrize-linux`),
  same pattern as the Windows release does with the `.exe`.
- Mark it executable (`chmod +x`) after extraction/install, since zip/tar
  extraction on Linux doesn't always preserve the bit depending on how
  you package it.
- If you want a single static-ish binary with fewer runtime surprises,
  you can build a separate binary per distro family (glibc vs musl) — but
  for a first pass, a normal glibc build covering common desktop distros
  (Ubuntu/Fedora/Arch/Debian) is sufficient.
- Building via CGO means **cross-compiling from another OS is painful**;
  build the Linux binary on an actual Linux machine or in Linux CI
  (see the GitHub Actions note below).
