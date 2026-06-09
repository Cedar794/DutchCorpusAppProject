#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${FROG_PREFIX:-$ROOT/local/frog}"
SRC="${FROG_SRC_DIR:-$ROOT/deps/src}"
LOG_DIR="${FROG_LOG_DIR:-$ROOT/outputs/native_build_logs}"

BREW_PREFIX="$(brew --prefix)"
AUTOCONF_ARCHIVE_PREFIX="$(brew --prefix autoconf-archive)"
ICU_PREFIX="$(brew --prefix icu4c@78)"
LIBXML2_PREFIX="$(brew --prefix libxml2)"
BISON_PREFIX="$(brew --prefix bison)"
LIBTOOL_PREFIX="$(brew --prefix libtool)"
LLVM_PREFIX="${LLVM_PREFIX:-$(brew --prefix llvm 2>/dev/null || true)}"
LIBOMP_PREFIX="${LIBOMP_PREFIX:-$(brew --prefix libomp 2>/dev/null || true)}"

export PATH="$PREFIX/bin:$LIBTOOL_PREFIX/libexec/gnubin:$BISON_PREFIX/bin:$ICU_PREFIX/bin:$LIBXML2_PREFIX/bin:$BREW_PREFIX/bin:$PATH"
export ACLOCAL_PATH="$BREW_PREFIX/share/aclocal:$AUTOCONF_ARCHIVE_PREFIX/share/aclocal:${ACLOCAL_PATH:-}"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:$ICU_PREFIX/lib/pkgconfig:$LIBXML2_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export CPPFLAGS="-I$PREFIX/include -I$BREW_PREFIX/include -I$ICU_PREFIX/include -I$LIBXML2_PREFIX/include ${CPPFLAGS:-}"
export CXXFLAGS="-std=c++17 ${CXXFLAGS:-}"
export LDFLAGS="-L$PREFIX/lib -L$BREW_PREFIX/lib -L$ICU_PREFIX/lib -L$LIBXML2_PREFIX/lib ${LDFLAGS:-}"
export DYLD_LIBRARY_PATH="$PREFIX/lib:$ICU_PREFIX/lib:$LIBXML2_PREFIX/lib:${DYLD_LIBRARY_PATH:-}"

if [[ "${FROG_USE_GCC:-0}" == "1" ]]; then
  export CC="${CC:-gcc-15}"
  export CXX="${CXX:-g++-15}"
fi

if [[ "${FROG_USE_LLVM:-0}" == "1" ]]; then
  if [[ ! -x "$LLVM_PREFIX/bin/clang++" ]] || [[ ! -f "$LIBOMP_PREFIX/lib/libomp.dylib" ]]; then
    echo "FROG_USE_LLVM=1 requires Homebrew llvm and libomp." >&2
    exit 1
  fi
  export CC="${CC:-$LLVM_PREFIX/bin/clang}"
  export CXX="${CXX:-$LLVM_PREFIX/bin/clang++}"
  export PATH="$LLVM_PREFIX/bin:$PATH"
  export CPPFLAGS="-I$LIBOMP_PREFIX/include $CPPFLAGS"
  export LDFLAGS="-L$LIBOMP_PREFIX/lib $LDFLAGS"
  export DYLD_LIBRARY_PATH="$LIBOMP_PREFIX/lib:$DYLD_LIBRARY_PATH"
fi

mkdir -p "$PREFIX" "$SRC" "$LOG_DIR"

run_logged() {
  local name="$1"
  shift
  echo "==> $name"
  {
    echo "COMMAND: $*"
    echo "PWD: $(pwd)"
    echo "START: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    "$@"
    echo "END: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } 2>&1 | tee "$LOG_DIR/$name.log"
}

patch_legacy_autotools_paths() {
  if [[ -f ./bootstrap.sh ]] \
    && grep -q 'acdirs="' ./bootstrap.sh \
    && ! grep -Fq "$BREW_PREFIX/share/aclocal" ./bootstrap.sh; then
    perl -0pi -e "s#(acdirs=\")#\$1$BREW_PREFIX/share/aclocal/ $AUTOCONF_ARCHIVE_PREFIX/share/aclocal/ #" ./bootstrap.sh
  fi
  if [[ -f ./m4/ac_search_lm.m4 ]] \
    && grep -q 'tcdirs="' ./m4/ac_search_lm.m4 \
    && ! grep -Fq "$PREFIX/share/libexttextcat" ./m4/ac_search_lm.m4; then
    perl -0pi -e "s#(tcdirs=\")#\$1$PREFIX/share/libexttextcat #" ./m4/ac_search_lm.m4
  fi
  if [[ -f ./src/mbma_mod.cxx ]] \
    && grep -Fq "bool operator()( const Rule *m1, const Rule *m2 ){" ./src/mbma_mod.cxx; then
    perl -0pi -e 's#\Qbool operator()( const Rule *m1, const Rule *m2 ){\E#bool operator()( const Rule *m1, const Rule *m2 ) const {#' ./src/mbma_mod.cxx
  fi
  if [[ "${FROG_USE_GCC:-0}" == "1" ]] \
    && [[ -f ./src/Makefile.am ]] \
    && grep -Fq "bin_PROGRAMS = frog mbma mblem ner" ./src/Makefile.am; then
    perl -0pi -e 's#\Qbin_PROGRAMS = frog mbma mblem ner\E#bin_PROGRAMS = frog#' ./src/Makefile.am
  fi
}

fetch_git_tag() {
  local repo="$1"
  local tag="$2"
  local dir="$SRC/$repo-$tag"
  if [[ ! -d "$dir/.git" ]]; then
    git clone --depth 1 --branch "$tag" "https://github.com/LanguageMachines/$repo.git" "$dir"
  fi
}

build_autotools_project() {
  local repo="$1"
  local tag="$2"
  local dir="$SRC/$repo-$tag"
  fetch_git_tag "$repo" "$tag"
  cd "$dir"
  patch_legacy_autotools_paths
  if [[ -f ./bootstrap.sh ]]; then
    run_logged "$repo-bootstrap" bash ./bootstrap.sh
  elif [[ -f ./autogen.sh ]]; then
    run_logged "$repo-autogen" bash ./autogen.sh
  fi
  run_logged "$repo-configure" ./configure --prefix="$PREFIX"
  run_logged "$repo-make" make -j"$(sysctl -n hw.ncpu)"
  run_logged "$repo-install" make install
}

build_libexttextcat() {
  local version="3.4.6"
  local archive="$SRC/libexttextcat-$version.tar.xz"
  local dir="$SRC/libexttextcat-$version"
  if [[ ! -f "$archive" ]]; then
    curl -L "https://dev-www.libreoffice.org/src/libexttextcat/libexttextcat-$version.tar.xz" -o "$archive"
  fi
  if [[ ! -d "$dir" ]]; then
    tar -C "$SRC" -xf "$archive"
  fi
  cd "$dir"
  run_logged "libexttextcat-configure" ./configure --prefix="$PREFIX"
  run_logged "libexttextcat-make" make -j"$(sysctl -n hw.ncpu)"
  run_logged "libexttextcat-install" make install
}

build_libexttextcat
build_autotools_project ticcutils v0.29
build_autotools_project libfolia v2.11
build_autotools_project uctodata v0.9.1
build_autotools_project ucto v0.25
build_autotools_project timbl v6.7
build_autotools_project mbt v3.8
build_autotools_project frogdata v0.21
build_autotools_project frog v0.25

"$PREFIX/bin/frog" --version
