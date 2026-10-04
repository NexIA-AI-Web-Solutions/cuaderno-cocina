#!/bin/sh
set -eu
work=/tmp/zlib-cve-proof
mkdir "$work"
tar -xzf /var/cache/distfiles/zlib-1.3.2.tar.gz -C "$work"
cp -a "$work/zlib-1.3.2" "$work/unpatched"
cp -a "$work/zlib-1.3.2" "$work/patched"
build_and_run() {
  tree="$1"; expected="$2"
  # 1.3.2 also omitted errno.h; force it only so the vulnerable control can
  # compile on current musl. The 813dac5d follow-up fixes this in the package.
  (cd "$tree" && CC=clang CFLAGS='-fsanitize=address -O0 -g -include errno.h' ./configure --static >/dev/null && make -s)
  clang -fsanitize=address -fno-sanitize-recover=all -O0 -g \
    /runtime-security/tests/zlib-cve-2026-85091.c -I"$tree" "$tree/libz.a" -o "$tree/proof"
  if ASAN_OPTIONS=abort_on_error=1:detect_leaks=0 "$tree/proof" >/tmp/zlib-proof.out 2>/tmp/zlib-proof.err; then
    result=pass
  elif grep -q 'AddressSanitizer: heap-buffer-overflow' /tmp/zlib-proof.err; then
    result=asan_failure
  else
    cat /tmp/zlib-proof.err >&2
    exit 1
  fi
  echo "zlib CVE control $(basename "$tree"): $result (expected $expected)"
  if [ "$result" != "$expected" ]; then cat /tmp/zlib-proof.err >&2; exit 1; fi
}
build_and_run "$work/unpatched" asan_failure
for patch in df84af25dc1942490e1d1c899a07619152a46148 7235b0a581227c56a79a43ff828f8ef6794194c8 813dac5dcb5902ed241e9b0d38abd2d847a335a9 d81c2d7eb705c62294ba03299255672078e89115; do
  patch -d "$work/patched" -p1 <"/runtime-security/aports/main/zlib/$patch.patch"
done
build_and_run "$work/patched" pass
