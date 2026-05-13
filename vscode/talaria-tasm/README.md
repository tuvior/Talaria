# Talaria TASM VS Code Syntax

Local VS Code language extension for Talaria assembly files.

It highlights:

- `.function`, `.end function`, `.name`, `.params`, `.registers`, and `.symbols`
- `.hints` blocks and hint keys
- instruction opcodes such as `LoadConstString`, `CreateClosure`, and `JmpFalse`
- labels and label references
- registers, string/function/bigint references, typed operands, numeric aliases, numbers, strings, and comments

## Install

From the `talaria` repository root:

```sh
mkdir -p ~/.vscode/extensions
ln -s "$PWD/vscode/talaria-tasm" ~/.vscode/extensions/talaria-tasm
```

Reload VS Code, then open a `.tasm` file. If a file is not detected automatically,
choose `Talaria TASM` from the language mode picker.

If you prefer copying instead of symlinking:

```sh
mkdir -p ~/.vscode/extensions/talaria-tasm
cp -R vscode/talaria-tasm/. ~/.vscode/extensions/talaria-tasm/
```
