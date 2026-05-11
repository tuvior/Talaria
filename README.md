# Talaria

<p align="center">
  <img src="assets/banner.png" alt="Talaria banner: winged tools for Hermes bytecode">
</p>

<p align="center"><strong>Winged tools for Hermes bytecode.</strong></p>

Talaria is a Python command-line tool and library for disassembling, editing,
and assembling Hermes bytecode bundles used by React Native applications.

<p align="center">
  <a href="pyproject.toml"><img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="#hermes-bytecode-support"><img alt="Supported HBC versions" src="https://img.shields.io/badge/HBC-59%20%7C%2062%20%7C%2074%20%7C%2076%20%7C%2084%20%7C%2085%20%7C%2090%20%7C%2094%20%7C%2096%20%7C%2098-blue"></a>
  <br>
  <a href="src/talaria/cli.py"><img alt="CLI: Click" src="https://img.shields.io/badge/interface-Click-222222"></a>
  <a href="https://black.readthedocs.io/"><img alt="Code style: Black" src="https://img.shields.io/badge/code%20style-Black-000000"></a>
  <a href="https://docs.astral.sh/ruff/"><img alt="Lint: Ruff" src="https://img.shields.io/badge/lint-Ruff-D7FF64"></a>
  <a href="tests"><img alt="Tests: pytest" src="https://img.shields.io/badge/tests-pytest-0A9EDC"></a>
</p>

Talaria is named after the winged sandals of Mercury, the Roman counterpart to
Hermes. The name fits the project directly: it is built to move quickly through
Hermes bytecode, from React Native APKs to editable TASM and back again.


## Hermes Bytecode Support

Talaria supports the Hermes bytecode (HBC) versions listed below. Hermes does
not publish separate end-user documentation for each bytecode version; the
closest authoritative references are the Hermes source files that define the
bytecode file format and opcode list. General background is available in the
[React Native Hermes guide](https://reactnative.dev/docs/hermes) and the
[Bundled Hermes architecture notes](https://reactnative.dev/architecture/bundled-hermes).

| HBC version | Opcodes | Talaria metadata | Upstream reference | Test fixture |
| --- | ---: | --- | --- | --- |
| 59 | 177 | [`hbc59`](src/talaria/hbc/hbc59) | No stable public source tag recorded yet | Yes |
| 62 | 177 | [`hbc62`](src/talaria/hbc/hbc62) | No stable public source tag recorded yet | Yes |
| 74 | 180 | [`hbc74`](src/talaria/hbc/hbc74) | No stable public source tag recorded yet | Yes |
| 76 | 180 | [`hbc76`](src/talaria/hbc/hbc76) | No stable public source tag recorded yet | Yes |
| 84 | 199 | [`hbc84`](src/talaria/hbc/hbc84) | [`facebook/hermes@v0.9.0`](https://github.com/facebook/hermes/tree/v0.9.0/include/hermes/BCGen/HBC) | No |
| 85 | 201 | [`hbc85`](src/talaria/hbc/hbc85) | No stable public source tag recorded yet | No |
| 90 | 204 | [`hbc90`](src/talaria/hbc/hbc90) | No stable public source tag recorded yet | No |
| 94 | 206 | [`hbc94`](src/talaria/hbc/hbc94) | No stable public source tag recorded yet | No |
| 96 | 206 | [`hbc96`](src/talaria/hbc/hbc96) | No stable public source tag recorded yet | No |
| 98 | 219 | [`hbc98`](src/talaria/hbc/hbc98) | [`facebook/hermes@hermes-v250829098.0.10`](https://github.com/facebook/hermes/tree/hermes-v250829098.0.10/include/hermes/BCGen/HBC) | Yes |

Unsupported bundle versions fail explicitly before parsing. The source tag
registry lives in [`specs.json`](src/talaria/hbc/specs.json); add a tag there
when a supported HBC version is traced to an upstream Hermes release.

## Install

```bash
python -m pip install talaria
```

## Usage

```bash
talaria disasm index.android.bundle workspace/
talaria asm workspace/ index.android.bundle
```

For APKs that contain the usual React Native bundle path:

```bash
talaria apk disasm app.apk app-workspace/
# edit app-workspace/tasm/functions.tasm
talaria apk asm app-workspace/
```

`talaria apk disasm` runs `apktool d -r`, so APK resources are kept raw. The
decoded APK tree is written to `app-workspace/apk`, and the TASM workspace is
written to `app-workspace/tasm`. `talaria apk asm` updates
`app-workspace/apk/assets/index.android.bundle`.

Use `talaria --help` for the complete command reference.

## Workspace Format

`talaria disasm` writes a Talaria workspace:

- `talaria.json`: workspace manifest and format version
- `bundle.json`: raw Hermes bytecode metadata needed for reassembly
- `strings.json`: editable string table view
- `functions.tasm`: Talaria assembly text

Function blocks in `functions.tasm` use a smali-inspired line-oriented syntax:

```text
.function @0
    .name "global"
    .params 1
    .registers 3
    .symbols 0

    LoadConstUndefined r0
    CreateClosure r1, r0, fn@1

    LoadConstString r2, s@4 "use strict"
    JmpFalse :done, r2

:done
    Ret r0
.end function
```

Common operand forms are `r0` for registers, plain integers for opcode-typed
unsigned immediates, `i32:-1` for signed immediates, `s@18 "value"` for editable
string table references, `fn@4` for function references, and labels such as
`:done` for branch targets. Cache slots and similar common operands render with
aliases such as `cache:2`, `slot:0`, `param:1`, and `argc:3`.

## VS Code Syntax Highlighting

This repository includes a local VS Code language extension for `functions.tasm`
and other `.tasm` files.

Install it from the `talaria` repository root:

```bash
mkdir -p ~/.vscode/extensions
ln -s "$PWD/vscode/talaria-tasm" ~/.vscode/extensions/talaria-tasm
```

Reload VS Code, then open a `.tasm` file. If VS Code does not detect the
language automatically, choose `Talaria TASM` from the language mode picker.

To install by copying instead of symlinking:

```bash
mkdir -p ~/.vscode/extensions/talaria-tasm
cp -R vscode/talaria-tasm/. ~/.vscode/extensions/talaria-tasm/
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python tools/check_hbc_specs.py
python -m ruff check src/talaria/cli.py src/talaria/commands.py tools tests
```

The bytecode parsers are data-driven by the versioned Hermes structure and
opcode metadata under `src/talaria/hbc/hbc*/data`. Use
`tools/check_hbc_specs.py` after updating any `BytecodeList.def` or
`opcode.json` file.
