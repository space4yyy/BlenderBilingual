#!/usr/bin/env python3
"""Build and manage Simplified Chinese/English Blender MO catalogs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import string
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKS_ROOT = PROJECT_ROOT / "packs"
LANGUAGE_CODE = "zh_HANS@bilingual"
LANGUAGE_LABEL = "Chinese (Simplified, Bilingual) - 简中 English"
ORDER_ZH_EN = "zh-en"
ORDER_EN_ZH = "en-zh"
ORDERS = (ORDER_ZH_EN, ORDER_EN_ZH)
ORDER_RULE_VERSIONS = {ORDER_ZH_EN: 3, ORDER_EN_ZH: 4}
RULE_VERSION = ORDER_RULE_VERSIONS[ORDER_ZH_EN]
MANAGED_BEGIN = "# BEGIN zh_HANS_Bilingual managed"
MANAGED_END = "# END zh_HANS_Bilingual managed"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
BLENDER_VERSION_RE = re.compile(r"\bBlender\s+(\d+\.\d+\.\d+)\b")
USER_DATAFILES_MARKER = "ZH_HANS_BILINGUAL_USER_DATAFILES="
PRINTF_RE = re.compile(
    r"%(?!%)(?:\d+\$|\([^)]+\))?[-+#0 ']*"
    r"(?:\*(?:\d+\$)?|\d+)?(?:\.(?:\*(?:\d+\$)?|\d+))?"
    r"(?:hh|h|ll|l|j|z|t|L)?[diuoxXfFeEgGaAcspnrb]"
)
FORMATTER = string.Formatter()


class BilingualError(RuntimeError):
    """An expected, user-facing failure."""


@dataclass(frozen=True)
class MOEntry:
    original: str
    translation: str


@dataclass(frozen=True)
class MOCatalog:
    entries: tuple[MOEntry, ...]

    @classmethod
    def read(cls, source: Path | bytes | BinaryIO) -> "MOCatalog":
        if isinstance(source, Path):
            data = source.read_bytes()
        elif isinstance(source, bytes):
            data = source
        else:
            data = source.read()
        if len(data) < 28:
            raise BilingualError("MO 文件过短或已损坏")

        magic_le = struct.unpack_from("<I", data, 0)[0]
        if magic_le == 0x950412DE:
            endian = "<"
        elif magic_le == 0xDE120495:
            endian = ">"
        else:
            raise BilingualError("文件不是有效的 GNU MO")

        _magic, revision, count, original_offset, translation_offset, _hash_size, _hash_offset = struct.unpack_from(
            f"{endian}7I", data, 0
        )
        if revision >> 16 not in (0, 1):
            raise BilingualError(f"不支持的 MO 版本：{revision}")
        for table_offset in (original_offset, translation_offset):
            if table_offset > len(data) or count > (len(data) - table_offset) // 8:
                raise BilingualError("MO 字符串表越界")

        def read_table_item(table_offset: int, index: int) -> str:
            length, offset = struct.unpack_from(f"{endian}2I", data, table_offset + index * 8)
            end = offset + length
            if offset > len(data) or end > len(data):
                raise BilingualError("MO 字符串内容越界")
            try:
                return data[offset:end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BilingualError("MO 包含非 UTF-8 字符串") from exc

        entries = tuple(
            MOEntry(
                read_table_item(original_offset, index),
                read_table_item(translation_offset, index),
            )
            for index in range(count)
        )
        originals = [entry.original for entry in entries]
        if len(set(originals)) != len(originals):
            raise BilingualError("MO 包含重复消息键")
        return cls(entries)

    def to_bytes(self) -> bytes:
        encoded = sorted(
            ((entry.original.encode("utf-8"), entry.translation.encode("utf-8")) for entry in self.entries),
            key=lambda pair: pair[0],
        )
        count = len(encoded)
        original_table = 28
        translation_table = original_table + count * 8
        original_data_offset = translation_table + count * 8

        original_blob = bytearray()
        original_records: list[tuple[int, int]] = []
        for original, _translation in encoded:
            original_records.append((len(original), original_data_offset + len(original_blob)))
            original_blob.extend(original)
            original_blob.append(0)

        translation_data_offset = original_data_offset + len(original_blob)
        translation_blob = bytearray()
        translation_records: list[tuple[int, int]] = []
        for _original, translation in encoded:
            translation_records.append((len(translation), translation_data_offset + len(translation_blob)))
            translation_blob.extend(translation)
            translation_blob.append(0)

        output = bytearray(struct.pack("<7I", 0x950412DE, 0, count, original_table, translation_table, 0, 0))
        for record in original_records:
            output.extend(struct.pack("<2I", *record))
        for record in translation_records:
            output.extend(struct.pack("<2I", *record))
        output.extend(original_blob)
        output.extend(translation_blob)
        return bytes(output)

    def write(self, destination: Path) -> None:
        atomic_write(destination, self.to_bytes())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_version(version: str) -> tuple[str, str]:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise BilingualError("版本必须精确到补丁号，例如 4.4.3 或 5.1.2")
    return version, f"{match.group(1)}.{match.group(2)}"


def strip_context(original: str) -> str:
    return original.split("\x04", 1)[-1]


def has_brace_placeholder(value: str) -> bool:
    try:
        return any(field_name is not None for _literal, field_name, _spec, _conversion in FORMATTER.parse(value))
    except ValueError:
        return False


def has_dynamic_placeholder(value: str) -> bool:
    return bool(PRINTF_RE.search(value)) or has_brace_placeholder(value)


def normalize_order(order: str) -> str:
    if order not in ORDERS:
        raise BilingualError(f"不支持的双语顺序：{order}")
    return order


def bilingual_translation(
    original: str, translation: str, order: str = ORDER_ZH_EN
) -> tuple[str, str]:
    """Return transformed translation and the applied rule name."""
    order = normalize_order(order)
    if original == "":
        return translation, "header"
    message_ids = strip_context(original).split("\0")
    translations = translation.split("\0")
    if any(has_dynamic_placeholder(value) for value in (*message_ids, *translations)):
        return translation, "dynamic"

    transformed: list[str] = []
    for index, translated in enumerate(translations):
        english = message_ids[min(index, len(message_ids) - 1)]
        if not translated:
            transformed.append(english)
        elif translated == english:
            transformed.append(translated)
        elif order == ORDER_EN_ZH:
            transformed.append(f"{english} {translated}")
        else:
            transformed.append(f"{translated} {english}")
    return "\0".join(transformed), "bilingual"


def transform_catalog(
    source: MOCatalog, order: str = ORDER_ZH_EN
) -> tuple[MOCatalog, dict[str, int]]:
    order = normalize_order(order)
    stats = {"messages": 0, "contexts": 0, "plurals": 0, "bilingual": 0, "dynamic": 0, "header": 0}
    transformed: list[MOEntry] = []
    for entry in source.entries:
        translation, rule = bilingual_translation(entry.original, entry.translation, order)
        transformed.append(MOEntry(entry.original, translation))
        stats[rule] += 1
        if entry.original:
            stats["messages"] += 1
            if "\x04" in entry.original:
                stats["contexts"] += 1
            if "\0" in strip_context(entry.original):
                stats["plurals"] += 1
    return MOCatalog(tuple(transformed)), stats


def output_entry_is_dynamic(entry: MOEntry, order: str = ORDER_ZH_EN) -> bool:
    """Re-evaluate the dynamic rule after English has already been appended."""
    order = normalize_order(order)
    message_ids = strip_context(entry.original).split("\0")
    if any(has_dynamic_placeholder(value) for value in message_ids):
        return True
    for index, translated in enumerate(entry.translation.split("\0")):
        english = message_ids[min(index, len(message_ids) - 1)]
        if translated == english:
            original_translation = ""
        elif order == ORDER_ZH_EN and translated.endswith(f" {english}"):
            original_translation = translated[: -(len(english) + 1)]
        elif order == ORDER_EN_ZH and translated.startswith(f"{english} "):
            original_translation = translated[len(english) + 1 :]
        else:
            original_translation = translated
        if has_dynamic_placeholder(original_translation):
            return True
    return False


def catalog_key_digest(catalog: MOCatalog) -> str:
    digest = hashlib.sha256()
    for original in sorted(entry.original for entry in catalog.entries):
        encoded = original.encode("utf-8")
        digest.update(struct.pack("<I", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def blender_layout(blender: Path) -> tuple[Path, Path, str]:
    blender = blender.expanduser().resolve()
    if blender.suffix == ".app":
        executable = blender / "Contents" / "MacOS" / "Blender"
        resources_root = blender / "Contents" / "Resources"
    elif blender.is_file():
        executable = blender
        resources_root = blender.parent
    else:
        executable = blender / ("blender.exe" if os.name == "nt" else "blender")
        resources_root = blender
    if not executable.is_file():
        raise BilingualError(f"找不到 Blender 可执行文件：{executable}")
    try:
        result = subprocess.run(
            [str(executable), "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except OSError as exc:
        raise BilingualError(f"无法运行 Blender：{exc}") from exc
    match = BLENDER_VERSION_RE.search(result.stdout + result.stderr)
    if not match:
        raise BilingualError("无法从 Blender --version 确定完整版本")
    version, resource_version = parse_version(match.group(1))
    datafiles = resources_root / resource_version / "datafiles"
    if not datafiles.is_dir():
        raise BilingualError(f"找不到 Blender 数据目录：{datafiles}")
    return executable, datafiles, version


def discover_blender_installations(platform_name: str | None = None) -> list[Path]:
    """Return likely local Blender app roots or executables without launching them."""
    platform_name = platform_name or sys.platform
    candidates: list[Path] = []
    if platform_name == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            if root.is_dir():
                candidates.extend(root.glob("Blender*.app"))
    elif platform_name == "win32":
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            value = os.environ.get(variable)
            if not value:
                continue
            root = Path(value)
            candidates.extend(root.glob("Blender Foundation/Blender*/blender.exe"))
            candidates.extend(root.glob("Programs/Blender Foundation/Blender*/blender.exe"))
        try:
            import winreg

            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(
                        hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\blender.exe"
                    ) as key:
                        candidates.append(Path(winreg.QueryValue(key, None)))
                except OSError:
                    pass
        except ImportError:
            pass

    executable = shutil.which("blender") or shutil.which("blender.exe")
    if executable:
        candidates.append(Path(executable))

    discovered: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.suffix == ".app":
            exists = (candidate / "Contents" / "MacOS" / "Blender").is_file()
        elif candidate.is_file():
            exists = True
        else:
            exists = (candidate / ("blender.exe" if platform_name == "win32" else "blender")).is_file()
        if not exists:
            continue
        resolved = candidate.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            discovered.append(resolved)
    return sorted(
        discovered,
        key=lambda path: (path.suffix.casefold() == ".app", path.name.casefold()),
        reverse=True,
    )


def source_mo_from_blender(blender: Path) -> tuple[Path, str, str, dict[str, str]]:
    _executable, datafiles, version = blender_layout(blender)
    source = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
    if not source.is_file():
        raise BilingualError(f"找不到官方简中 MO：{source}")
    _version, resource_version = parse_version(version)
    return source, version, resource_version, {"type": "local_blender", "blender": str(blender.resolve())}


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "zh-HANS-Bilingual/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            copied = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                copied += len(chunk)
                if total and (copied == total or copied // (50 * 1024 * 1024) != (copied - len(chunk)) // (50 * 1024 * 1024)):
                    print(f"已下载 {copied / 1024 / 1024:.0f}/{total / 1024 / 1024:.0f} MiB", file=sys.stderr)
    except (OSError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise BilingualError(f"下载失败：{url}（{exc}）") from exc


def expected_checksum(checksum_text: str, filename: str) -> str:
    for line in checksum_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise BilingualError(f"官方 SHA-256 文件中没有 {filename}")


def extract_official_mo(archive: Path, version: str, destination: Path) -> None:
    _version, resource_version = parse_version(version)
    suffix = f"/{resource_version}/datafiles/locale/zh_HANS/LC_MESSAGES/blender.mo"
    try:
        with tarfile.open(archive, mode="r:xz") as bundle:
            matches = [member for member in bundle.getmembers() if member.isfile() and member.name.endswith(suffix)]
            if len(matches) != 1:
                raise BilingualError(f"发行包中应有且仅有一个官方简中 MO，实际找到 {len(matches)} 个")
            member = matches[0]
            if member.size <= 0 or member.size > 100 * 1024 * 1024:
                raise BilingualError("发行包内 MO 大小异常")
            source = bundle.extractfile(member)
            if source is None:
                raise BilingualError("无法读取发行包内的官方简中 MO")
            atomic_write(destination, source.read())
    except (tarfile.TarError, lzma_error()) as exc:
        raise BilingualError(f"无法读取官方 tar.xz：{exc}") from exc


def lzma_error() -> type[Exception]:
    # Import lazily so this module remains importable in minimal Python builds.
    try:
        import lzma

        return lzma.LZMAError
    except ImportError:
        return EOFError


def fetch_source_mo(version: str, temporary_directory: Path) -> tuple[Path, dict[str, str]]:
    _version, resource_version = parse_version(version)
    filename = f"blender-{version}-linux-x64.tar.xz"
    base_url = f"https://download.blender.org/release/Blender{resource_version}"
    archive_url = f"{base_url}/{filename}"
    checksum_url = f"{base_url}/blender-{version}.sha256"
    archive = temporary_directory / filename
    checksum = temporary_directory / f"blender-{version}.sha256"
    print(f"下载官方发行包：{archive_url}", file=sys.stderr)
    download_file(checksum_url, checksum)
    download_file(archive_url, archive)
    wanted = expected_checksum(checksum.read_text(encoding="utf-8"), filename)
    actual = sha256_file(archive)
    if actual != wanted:
        raise BilingualError(f"官方发行包 SHA-256 不匹配：期望 {wanted}，实际 {actual}")
    source = temporary_directory / "official-zh_HANS.mo"
    extract_official_mo(archive, version, source)
    return source, {"type": "official_download", "url": archive_url, "archive_sha256": actual}


def pack_paths(version: str, packs_root: Path = PACKS_ROOT) -> tuple[Path, Path]:
    root = packs_root / version
    return root / LANGUAGE_CODE / "LC_MESSAGES" / "blender.mo", root / "manifest.json"


def build_pack(
    *,
    version: str | None,
    blender: Path | None,
    source_mo: Path | None,
    packs_root: Path = PACKS_ROOT,
    order: str = ORDER_ZH_EN,
) -> tuple[Path, Path]:
    order = normalize_order(order)
    if blender is not None:
        if version is not None or source_mo is not None:
            raise BilingualError("--blender 不能与 --version 或 --source-mo 同时使用")
        source, version, resource_version, source_info = source_mo_from_blender(blender)
        return build_from_source(source, version, resource_version, source_info, packs_root, order)

    if version is None:
        raise BilingualError("请使用 --blender，或指定精确的 --version")
    version, resource_version = parse_version(version)
    if source_mo is not None:
        source = source_mo.expanduser().resolve()
        if not source.is_file():
            raise BilingualError(f"指定的 MO 不存在：{source}")
        return build_from_source(
            source, version, resource_version, {"type": "provided_mo"}, packs_root, order
        )

    with tempfile.TemporaryDirectory(prefix="blender-bilingual-") as temporary:
        source, source_info = fetch_source_mo(version, Path(temporary))
        return build_from_source(source, version, resource_version, source_info, packs_root, order)


def build_from_source(
    source: Path,
    version: str,
    resource_version: str,
    source_info: dict[str, str],
    packs_root: Path,
    order: str = ORDER_ZH_EN,
) -> tuple[Path, Path]:
    order = normalize_order(order)
    source_bytes = source.read_bytes()
    source_catalog = MOCatalog.read(source_bytes)
    output_catalog, stats = transform_catalog(source_catalog, order)
    output_bytes = output_catalog.to_bytes()
    roundtrip = MOCatalog.read(output_bytes)
    if catalog_key_digest(source_catalog) != catalog_key_digest(roundtrip):
        raise BilingualError("生成后的 MO 消息键与官方源不一致")

    output, manifest_path = pack_paths(version, packs_root)
    manifest = {
        "schema_version": 1,
        "language": LANGUAGE_CODE,
        "order": order,
        "display_format": "中文 English" if order == ORDER_ZH_EN else "English 中文",
        "rule_version": ORDER_RULE_VERSIONS[order],
        "blender_version": version,
        "resource_version": resource_version,
        "source": {**source_info, "mo_sha256": sha256_bytes(source_bytes)},
        "output": {
            "path": f"{LANGUAGE_CODE}/LC_MESSAGES/blender.mo",
            "mo_sha256": sha256_bytes(output_bytes),
            "catalog_key_sha256": catalog_key_digest(output_catalog),
            **stats,
        },
    }
    atomic_write(output, output_bytes)
    atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return output, manifest_path


def verify_pack(
    version: str, packs_root: Path = PACKS_ROOT, order: str = ORDER_ZH_EN
) -> dict[str, object]:
    order = normalize_order(order)
    version, resource_version = parse_version(version)
    output, manifest_path = pack_paths(version, packs_root)
    if not output.is_file() or not manifest_path.is_file():
        raise BilingualError(f"找不到 {version} 的语言包或 manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BilingualError(f"manifest 无效：{exc}") from exc
    if manifest.get("blender_version") != version or manifest.get("resource_version") != resource_version:
        raise BilingualError("manifest 中的 Blender 版本不匹配")
    manifest_order = manifest.get("order", ORDER_ZH_EN)
    if manifest_order != order:
        raise BilingualError(
            f"语言包顺序为 {manifest_order}，当前需要 {order}，请按所需顺序重新生成"
        )
    if (
        manifest.get("language") != LANGUAGE_CODE
        or manifest.get("rule_version") != ORDER_RULE_VERSIONS[order]
    ):
        raise BilingualError("manifest 的语言代码或生成规则版本不受支持")
    catalog = MOCatalog.read(output)
    actual_sha = sha256_file(output)
    expected_output = manifest.get("output", {})
    if actual_sha != expected_output.get("mo_sha256"):
        raise BilingualError("双语 MO 的 SHA-256 与 manifest 不一致")
    if catalog_key_digest(catalog) != expected_output.get("catalog_key_sha256"):
        raise BilingualError("双语 MO 的消息键与 manifest 不一致")
    messages = sum(entry.original != "" for entry in catalog.entries)
    contexts = sum("\x04" in entry.original for entry in catalog.entries if entry.original)
    plurals = sum("\0" in strip_context(entry.original) for entry in catalog.entries if entry.original)
    dynamic = sum(output_entry_is_dynamic(entry, order) for entry in catalog.entries if entry.original)
    for key, value in (
        ("messages", messages),
        ("contexts", contexts),
        ("plurals", plurals),
        ("dynamic", dynamic),
    ):
        if expected_output.get(key) != value:
            raise BilingualError(f"manifest 的 {key} 统计不一致")
    return manifest


def remove_managed_block(text: str) -> tuple[str, bool]:
    lines = text.splitlines()
    try:
        begin = lines.index(MANAGED_BEGIN)
    except ValueError:
        return text, False
    try:
        end = lines.index(MANAGED_END, begin + 1)
    except ValueError as exc:
        raise BilingualError("languages 文件中的托管区块不完整") from exc
    if MANAGED_BEGIN in lines[begin + 1 :] or MANAGED_END in lines[end + 1 :]:
        raise BilingualError("languages 文件中存在重复托管标记")
    del lines[begin : end + 1]
    return "\n".join(lines).rstrip() + "\n", True


def used_language_ids(text: str) -> set[int]:
    ids: set[int] = set()
    for line in text.splitlines():
        match = re.match(r"\s*(\d+):", line)
        if match:
            ids.add(int(match.group(1)))
    return ids


def set_blender_language(executable: Path, language_code: str) -> None:
    expression = (
        "import bpy; "
        f"bpy.context.preferences.view.language={language_code!r}; "
        "bpy.ops.wm.save_userpref()"
    )
    try:
        result = subprocess.run(
            [str(executable), "--background", "--python-expr", expression],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BilingualError(f"无法启动 Blender 保存用户语言偏好：{exc}") from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip().splitlines()
        summary = details[-1] if details else f"退出码 {result.returncode}"
        raise BilingualError(f"Blender 保存用户语言偏好失败：{summary}")


def blender_user_datafiles(executable: Path) -> Path:
    """Ask Blender for this version's writable per-user datafiles directory."""
    expression = (
        "import bpy; "
        f"print({USER_DATAFILES_MARKER!r} + bpy.utils.user_resource('DATAFILES'))"
    )
    try:
        result = subprocess.run(
            [str(executable), "--background", "--python-expr", expression],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BilingualError(f"无法启动 Blender 查询用户语言目录：{exc}") from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip().splitlines()
        summary = details[-1] if details else f"退出码 {result.returncode}"
        raise BilingualError(f"Blender 查询用户语言目录失败：{summary}")
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if line.startswith(USER_DATAFILES_MARKER):
            value = line[len(USER_DATAFILES_MARKER) :].strip()
            if value:
                return Path(value).expanduser().resolve()
    raise BilingualError("Blender 未返回用户语言目录")


def install_pack(
    blender: Path,
    version: str | None,
    dry_run: bool,
    packs_root: Path = PACKS_ROOT,
    activate: bool = True,
    order: str = ORDER_ZH_EN,
    user_datafiles: Path | None = None,
) -> str:
    order = normalize_order(order)
    executable, datafiles, detected_version = blender_layout(blender)
    if version is not None and parse_version(version)[0] != detected_version:
        raise BilingualError(f"目标 Blender 是 {detected_version}，不是 {version}")
    source_mo, manifest_path = pack_paths(detected_version, packs_root)
    pack_complete = source_mo.is_file() and manifest_path.is_file()
    pack_partially_present = source_mo.exists() or manifest_path.exists()
    auto_generated = False
    will_auto_generate = False
    if pack_complete or pack_partially_present:
        verify_pack(detected_version, packs_root, order)
    else:
        official_mo = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
        if not official_mo.is_file():
            raise BilingualError(f"找不到本地 Blender 的官方简中 MO：{official_mo}")
        if dry_run:
            will_auto_generate = True
        else:
            _version, resource_version = parse_version(detected_version)
            build_from_source(
                official_mo,
                detected_version,
                resource_version,
                {"type": "local_blender", "blender": str(blender.expanduser().resolve())},
                packs_root,
                order,
            )
            verify_pack(detected_version, packs_root, order)
            auto_generated = True
    system_languages = datafiles / "locale" / "languages"
    if not system_languages.is_file():
        raise BilingualError(f"找不到 Blender 自带的 languages 文件：{system_languages}")
    user_datafiles = (
        user_datafiles.expanduser().resolve()
        if user_datafiles is not None
        else blender_user_datafiles(executable)
    )
    languages = user_datafiles / "locale" / "languages"
    destination = user_datafiles / "locale" / LANGUAGE_CODE / "LC_MESSAGES" / "blender.mo"
    languages_existed = languages.is_file()
    original_text = (
        languages.read_text(encoding="utf-8")
        if languages_existed
        else system_languages.read_text(encoding="utf-8")
    )
    clean_text, had_block = remove_managed_block(original_text)
    user_had_block = languages_existed and had_block
    if not user_had_block and any(
        line.split(":")[2:3] == [LANGUAGE_CODE]
        for line in clean_text.splitlines()
        if not line.lstrip().startswith("#") and line.count(":") >= 2
    ):
        raise BilingualError(f"已存在非本项目管理的语言项：{LANGUAGE_CODE}")
    if not user_had_block and destination.exists():
        raise BilingualError(f"已存在非本项目管理的语言文件：{destination}")
    free_id = next(number for number in range(60, 10000) if number not in used_language_ids(clean_text))
    block = f"{MANAGED_BEGIN}\n{free_id}:{LANGUAGE_LABEL}:{LANGUAGE_CODE}:100%\n{MANAGED_END}\n"
    updated_text = clean_text.rstrip() + "\n" + block
    if dry_run:
        activation = "并设为当前用户语言" if activate else "但不修改当前用户语言"
        generation = "将先从本地 Blender 自动生成对应语言包；" if will_auto_generate else ""
        return f"{generation}将安装 {detected_version} 到 {destination}，语言 ID {free_id}，{activation}"
    destination_existed = destination.exists()
    previous_destination = destination.read_bytes() if destination_existed else None
    wrote_destination = False
    wrote_languages = False
    try:
        atomic_write(destination, source_mo.read_bytes())
        wrote_destination = True
        atomic_write(languages, updated_text.encode("utf-8"))
        wrote_languages = True
        if activate:
            set_blender_language(executable, LANGUAGE_CODE)
    except (OSError, BilingualError) as exc:
        if wrote_languages:
            try:
                if languages_existed:
                    atomic_write(languages, original_text.encode("utf-8"))
                else:
                    languages.unlink(missing_ok=True)
            except OSError:
                pass
        if wrote_destination:
            try:
                if destination_existed and previous_destination is not None:
                    atomic_write(destination, previous_destination)
                else:
                    destination.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, BilingualError):
            raise
        raise BilingualError(f"无法修改 Blender 用户语言目录：{exc}") from exc
    activation = "，已设为当前用户语言" if activate else ""
    generation = f"已自动生成 Blender {detected_version} 双语语言包；" if auto_generated else ""
    return f"{generation}已安装 Blender {detected_version} 双语语言，语言 ID {free_id}{activation}"


def uninstall_pack(
    blender: Path,
    dry_run: bool,
    reset_language: bool = True,
    user_datafiles: Path | None = None,
) -> str:
    executable, datafiles, detected_version = blender_layout(blender)
    system_languages = datafiles / "locale" / "languages"
    if not system_languages.is_file():
        raise BilingualError(f"找不到 Blender 自带的 languages 文件：{system_languages}")
    user_datafiles = (
        user_datafiles.expanduser().resolve()
        if user_datafiles is not None
        else blender_user_datafiles(executable)
    )
    languages = user_datafiles / "locale" / "languages"
    destination_root = user_datafiles / "locale" / LANGUAGE_CODE
    official_mo = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
    user_official_mo = user_datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
    user_text = languages.read_text(encoding="utf-8") if languages.is_file() else None
    source_text = user_text if user_text is not None else system_languages.read_text(encoding="utf-8")
    updated_text, had_block = remove_managed_block(source_text)
    user_had_block = user_text is not None and had_block
    system_text = system_languages.read_text(encoding="utf-8")
    clean_system_text, legacy_system_block = remove_managed_block(system_text)
    keep_user_languages = legacy_system_block or updated_text != clean_system_text
    if dry_run:
        reset = "并将当前用户语言切回官方简中" if reset_language else "且不修改当前用户语言"
        found = user_had_block or legacy_system_block
        return f"将卸载 Blender {detected_version} 双语语言（用户文件：{'有' if found else '无'}），{reset}"
    if reset_language and keep_user_languages and not official_mo.is_file():
        raise BilingualError(f"找不到 Blender 自带的官方简中语言包：{official_mo}")
    languages_existed = languages.is_file()
    original_languages = languages.read_bytes() if languages_existed else None
    official_existed = user_official_mo.is_file()
    original_official = user_official_mo.read_bytes() if official_existed else None
    try:
        if keep_user_languages:
            atomic_write(languages, updated_text.encode("utf-8"))
        elif languages_existed:
            languages.unlink()
        if reset_language and keep_user_languages:
            atomic_write(user_official_mo, official_mo.read_bytes())
        if reset_language:
            set_blender_language(executable, "zh_HANS")
        if user_had_block and destination_root.exists():
            shutil.rmtree(destination_root)
    except (OSError, BilingualError) as exc:
        try:
            if languages_existed and original_languages is not None:
                atomic_write(languages, original_languages)
            else:
                languages.unlink(missing_ok=True)
            if official_existed and original_official is not None:
                atomic_write(user_official_mo, original_official)
            else:
                user_official_mo.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, BilingualError):
            raise
        raise BilingualError(f"无法修改 Blender 用户语言目录：{exc}") from exc
    if user_had_block or legacy_system_block:
        return f"已卸载 Blender {detected_version} 双语语言"
    preference = "已切回官方简中" if reset_language else "未修改当前用户语言"
    return f"Blender {detected_version} 未发现本工具管理的双语语言；{preference}"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成和管理 Blender 简中—英文双语 MO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="生成双语 MO")
    build.add_argument("--blender", type=Path, help="本地 Blender.app、安装目录或可执行文件")
    build.add_argument("--version", help="精确 Blender 版本，例如 4.4.3")
    build.add_argument("--source-mo", type=Path, help="已有的官方简中 blender.mo")
    build.add_argument("--order", choices=ORDERS, default=ORDER_ZH_EN, help="双语显示顺序")

    verify = subparsers.add_parser("verify", help="校验已生成语言包")
    verify.add_argument("--version", required=True)
    verify.add_argument("--order", choices=ORDERS, default=ORDER_ZH_EN, help="双语显示顺序")

    for name in ("install", "uninstall"):
        command = subparsers.add_parser(name, help=f"{name} Blender 双语语言")
        command.add_argument(
            "--blender",
            type=Path,
            default=Path("/Applications/Blender.app") if sys.platform == "darwin" else None,
            required=sys.platform != "darwin",
            help="Blender.app、安装目录或 blender.exe 路径",
        )
        command.add_argument("--dry-run", action="store_true")
        if name == "install":
            command.add_argument("--version", help="可选的目标版本二次校验")
            command.add_argument("--order", choices=ORDERS, default=ORDER_ZH_EN, help="双语显示顺序")
            command.add_argument("--no-activate", action="store_true", help="安装后不修改当前用户语言")
        else:
            command.add_argument("--no-reset-language", action="store_true", help="卸载前不切回官方简中")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            output, manifest = build_pack(
                version=args.version,
                blender=args.blender,
                source_mo=args.source_mo,
                order=args.order,
            )
            print(f"已生成：{output}")
            print(f"元数据：{manifest}")
        elif args.command == "verify":
            manifest = verify_pack(args.version, order=args.order)
            print(
                f"校验通过：Blender {args.version}，"
                f"{manifest['output']['messages']} 条消息，{manifest['output']['bilingual']} 条双语"
            )
        elif args.command == "install":
            print(
                install_pack(
                    args.blender,
                    args.version,
                    args.dry_run,
                    activate=not args.no_activate,
                    order=args.order,
                )
            )
        elif args.command == "uninstall":
            print(uninstall_pack(args.blender, args.dry_run, reset_language=not args.no_reset_language))
        return 0
    except BilingualError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
