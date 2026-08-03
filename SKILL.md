---
name: blender-bilingual-mo
description: Build, verify, install, update, or uninstall Simplified Chinese and English bilingual GNU MO language packs for Blender 4.x and 5.x in this repository. Use when an AI agent needs to generate a pack from an installed Blender, a supplied official zh_HANS blender.mo, or an exact Blender release; change the bilingual display rule; validate catalogs and manifests; or manage a macOS or Windows Blender installation and saved language preference.
---

# Blender Bilingual MO

Operate from this repository root. Reuse `scripts/bilingual.py`; do not reimplement gettext conversion in ad hoc scripts.

## Preserve these rules

- Take English only from each official Simplified Chinese MO entry's `msgid`. Never translate or rewrite it.
- Support both `zh-en` (`中文 English`) and `en-zh` (`English 中文`), separated by one ASCII space and without parentheses. The repository pack default remains `zh-en`.
- Keep the official Chinese translation unchanged when either side contains runtime placeholders such as `%s`, `%d`, `%(name)s`, `{}`, or `{name}`.
- Work directly with MO catalogs. Do not create or retain PO files.
- Use exact patch versions such as `4.4.3`; never silently resolve `4.4` to a changing latest release.
- Store only the generated MO and `manifest.json` under `packs/<version>/`.
- Use `zh_HANS@bilingual` for the independent bilingual language and retain Blender's official `zh_HANS` unchanged. Do not use the non-standard `zh_HANS_bilingual` form.
- Assign a new entry in `ORDER_RULE_VERSIONS` whenever a new output semantic or display format is introduced. Do not invalidate an unchanged order's existing packs.

## Build

Prefer an installed Blender when its exact version is the target:

```bash
python3 scripts/bilingual.py build --blender /Applications/Blender.app
```

Pass `--order en-zh` when English must appear first. Omit it for the repository default `zh-en`.

For an uninstalled version, let the tool download and verify the official Linux release archive:

```bash
python3 scripts/bilingual.py build --version 4.4.3
```

For offline work, accept a supplied official Simplified Chinese MO:

```bash
python3 scripts/bilingual.py build \
  --version 4.4.3 \
  --source-mo /path/to/zh_HANS/LC_MESSAGES/blender.mo
```

Do not keep the downloaded release archive or extracted official source MO after generation.

## Validate every change

Run all three checks after modifying code or rebuilding a pack:

```bash
python3 -m unittest discover -v
python3 scripts/bilingual.py verify --version 5.1.2
msgunfmt packs/5.1.2/zh_HANS@bilingual/LC_MESSAGES/blender.mo | msgfmt --check -o /dev/null -
```

Substitute the affected version in the last two commands. Confirm that no `.po`, downloaded Blender archive, or obsolete locale directory remains in the repository.

When changing MO parsing, transformation, download, installation, or preference behavior, add a focused test in `tests/test_bilingual.py` before considering the change complete.

## Install on macOS or Windows

Treat installation as an external mutation because it edits the Blender installation directory and the user's Blender preferences. Obtain explicit user authorization before running the real command. Start with:

```bash
python3 scripts/bilingual.py install \
  --dry-run \
  --blender /Applications/Blender.app \
  --version 5.1.2
```

Then, when authorized, run the same command without `--dry-run`. By default it installs the MO, adds the managed language entry, and saves `zh_HANS@bilingual` as the current user language. Use `--no-activate` only when requested.

If the exact detected Blender version has no pack, `install` automatically builds it from that installation's official `zh_HANS` MO and verifies it before mutation. `--dry-run` must only report this pending build and must not create files. Never auto-rebuild a partially present, corrupt, or failed-verification pack; surface that error for inspection.

On Windows, run an Administrator PowerShell and pass the full `blender.exe` path explicitly:

```powershell
py scripts\bilingual.py install `
  --blender "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --version 5.1.2
```

After installation, verify the installed MO checksum matches the pack. Verify persisted preference by starting Blender again and reading:

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  --background \
  --python-expr "import bpy; print('ACTIVE_LANGUAGE=' + bpy.context.preferences.view.language)"
```

Run this restart check with normal macOS system access. A sandboxed Blender process may crash during Metal GPU detection even with `--factory-startup`; inspect the crash stack before attributing that failure to the language pack. Acceptance requires `ACTIVE_LANGUAGE=zh_HANS@bilingual` outside the restricted sandbox.

## Desktop GUI

Use `blender_bilingual_gui.py` as the single GUI entry point. It must discover local Blender installations on launch while retaining manual path selection. For each injection, build the selected order from that exact installation's official `zh_HANS` MO in a temporary directory, verify it, install it, activate it, and remove the temporary directory. Never bundle repository `packs/` into the desktop executable.

Build native artifacts with `python packaging/build_app.py`. PyInstaller is not a cross-compiler: build the macOS `.app` on macOS and the Windows single-file EXE on Windows. Keep Windows `--uac-admin`, because standard Blender installations are normally protected. The restore action must use the normal scoped uninstall path and reset the language to official Simplified Chinese.

## Uninstall on macOS or Windows

Preview first, then obtain authorization before mutation:

```bash
python3 scripts/bilingual.py uninstall --dry-run
python3 scripts/bilingual.py uninstall
```

The normal uninstall path must save official Simplified Chinese `zh_HANS` before removing the managed bilingual menu entry and `zh_HANS@bilingual` catalog. Use `--no-reset-language` only for explicit recovery work.

## Recovery and safety

- Do not manually edit `userpref.blend`.
- Do not overwrite the official `zh_HANS/LC_MESSAGES/blender.mo`.
- Preserve unrelated entries in Blender's `locale/languages` file.
- If preference activation fails, confirm the installer rolled back its managed block and MO before retrying.
- If Blender is currently open, avoid changing saved preferences until it is closed; the running process could overwrite them on exit.
- Read `README.md` and `python3 scripts/bilingual.py --help` when command behavior or supported flags may have changed.
