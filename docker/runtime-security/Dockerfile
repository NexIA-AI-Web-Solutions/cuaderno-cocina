# syntax=docker/dockerfile:1.7
ARG ALPINE_IMAGE=alpine@sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0
FROM ${ALPINE_IMAGE} AS builder
RUN apk add --no-cache alpine-sdk sudo clang21 compiler-rt
RUN adduser -D builder && addgroup builder abuild && printf 'builder ALL=(ALL) NOPASSWD: ALL\n' >/etc/sudoers.d/builder
COPY . /runtime-security
RUN sh /runtime-security/build.sh

FROM ${ALPINE_IMAGE} AS verifier
RUN busybox --list | sort >/reference-applets
COPY --from=builder /out /security-apks
COPY verify.sh /verify.sh
RUN sh /verify.sh

FROM scratch AS export
COPY --from=verifier /security-apks /
