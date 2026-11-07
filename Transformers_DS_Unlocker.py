#!/usr/bin/env python3
"""Unlock online vehicles in Transformers: Autobots / Decepticons Nintendo DS saves.

One 512-byte .sav file contains two player profiles. The game is auto-detected
from its signature. Based on user-verified Autobots and Decepticons edits.

With no command-line arguments, opens a simple Tkinter desktop interface.
With arguments, operates as a CLI (see --help).
Python 3.8+; standard library only. Never overwrites an existing file.
"""

from __future__ import annotations

import argparse
import binascii
import sys
from pathlib import Path
from typing import Dict, List, Tuple

SAVE_LENGTH = 0x200
GAME_SIGNATURES = {
    b"\x1a\x74\x03\x00": "Autobots",
    b"\x1b\x74\x03\x00": "Decepticons",
}
RECORD_SIGNATURE = b"\x1d\x60\xde\xc0"
RECORDS = {
    "A": {"start": 0x01C, "end": 0x0FC, "crc": 0x0FC, "online": 0x008},
    "B": {"start": 0x100, "end": 0x1E0, "crc": 0x1E0, "online": 0x00C},
}
JET_HEADER = 0x004  # Shared/global: Skydive (Autobots) or G1 Starscream (Decepticons)
ONLINE_REWARD_MASK = 0x7F  # Enable known working online-reward header bits
# Relative to the START of the 0xE0-byte player record, not the .sav file.
# Clearing these bits marks the four identified online vehicles as available.
# Masks: two vehicles at +0x6D, one at +0x6E, one at +0x70.
ONLINE_SCAN_MASKS = ((0x6D, 0x03), (0x6E, 0x02), (0x70, 0x20))
CRC_GLOBAL_POS = 0x1FE


def crc16(buffer: bytes, initial: int = 0) -> int:
    """CRC-16/CCITT, poly 0x1021, non-reflected, no final XOR."""
    return binascii.crc_hqx(bytes(buffer), initial)


def stored_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def stored_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def write_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = value.to_bytes(2, "little")


def write_u32(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 4] = value.to_bytes(4, "little")


def checksums(data: bytes) -> Dict[str, Tuple[int, int]]:
    """Returns {field: (stored, computed)} for both profiles and the file."""
    result = {}
    for slot, info in RECORDS.items():
        result[slot] = (
            stored_u16(data, info["crc"]),
            crc16(data[info["start"]:info["end"]]),
        )
    result["whole"] = (
        stored_u16(data, CRC_GLOBAL_POS),
        crc16(data[:CRC_GLOBAL_POS], 0xBEEF),
    )
    return result


def name_of(data: bytes, slot: str) -> str:
    begin = RECORDS[slot]["start"] + 4
    raw = data[begin:begin + 64].split(b"\x00", 1)[0]
    return raw.decode("ascii", errors="replace") or "(unnamed)"


def validate(data: bytes) -> str:
    if len(data) != SAVE_LENGTH:
        raise ValueError(
            f"Expected a 512-byte raw DS .sav; received {len(data)} bytes. "
            "Export the raw backup memory rather than a .dsv or save state."
        )
    game = GAME_SIGNATURES.get(bytes(data[:4]))
    if game is None:
        raise ValueError(
            f"Unrecognized file header {data[:4].hex(' ')}. "
            "Expected an Autobots or Decepticons Nintendo DS save."
        )
    for slot, info in RECORDS.items():
        if data[info["start"]:info["start"] + 4] != RECORD_SIGNATURE:
            raise ValueError(f"Missing player-record signature for Save {slot}; refusing to edit.")
    invalid = [(key, stored, actual) for key, (stored, actual) in checksums(data).items()
               if stored != actual]
    if invalid:
        problems = ", ".join(
            f"{key} stored={stored:04X} expected={actual:04X}"
            for key, stored, actual in invalid
        )
        raise ValueError("Input checksum(s) invalid: " + problems + ". Refusing to patch.")
    return game


def repair_checksums(data: bytearray) -> None:
    """Repair in the required order: both profiles, then the global CRC."""
    for info in RECORDS.values():
        write_u16(data, info["crc"], crc16(data[info["start"]:info["end"]]))
    write_u16(data, CRC_GLOBAL_POS, crc16(data[:CRC_GLOBAL_POS], 0xBEEF))


def patch(data: bytes, slot: str = "B", online: bool = True,
          jet: bool = True) -> Tuple[bytes, List[Tuple[int, int, int]]]:
    """Return (new save, changes [(offset, oldbyte, newbyte)]).

    Online modifies only selected profile(s). The Jet is a SHARED setting.
    Input must have valid CRCs. Unknown/other profile data is preserved.
    """
    validate(data)
    if slot not in ("A", "B", "both"):
        raise ValueError("Slot must be A, B, or both.")
    if not online and not jet:
        raise ValueError("Nothing selected: enable online vehicles and/or the bonus Jet.")
    result = bytearray(data)
    if online:
        targets = ("A", "B") if slot == "both" else (slot,)
        for current_slot in targets:
            info = RECORDS[current_slot]
            # Known working examples set the reward value to 0x7F. OR-ing
            # these low bits also preserves any existing higher flags.
            reward_offset = info["online"]
            write_u32(result, reward_offset,
                      stored_u32(result, reward_offset) | ONLINE_REWARD_MASK)
            for relative, mask in ONLINE_SCAN_MASKS:
                absolute = info["start"] + relative
                result[absolute] &= (~mask & 0xFF)
    if jet:
        # This flag is in the shared header; there is no per-slot Jet flag.
        write_u32(result, JET_HEADER, stored_u32(result, JET_HEADER) | 0x01)
    repair_checksums(result)
    validate(result)
    differences = [(i, data[i], result[i]) for i in range(SAVE_LENGTH)
                   if data[i] != result[i]]
    return bytes(result), differences


def default_name(source: Path, slot: str, online: bool, jet: bool) -> str:
    what = "online_and_jet" if online and jet else "online" if online else "jet"
    return f"{source.stem}_{slot}_{what}_unlocked.sav"


def write_new(source: Path, destination: Path, data: bytes) -> None:
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing to overwrite the original save file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects existing output files as well as the input.
    try:
        with destination.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise ValueError(
            f"Output already exists: {destination}. Choose a new filename; "
            "the program never overwrites saves."
        ) from exc


def description(data: bytes) -> str:
    game = validate(data)
    lines = [f"Game: Transformers: {game}", "File: 512 bytes; all three CRCs valid"]
    for slot, info in RECORDS.items():
        scan = bytes(data[info["start"] + 0x6C:info["start"] + 0x71]).hex(" ").upper()
        reward = stored_u32(data, info["online"])
        lines.append(
            f"Save {slot}: {name_of(data, slot)!r}; "
            f"reward=0x{reward:08X}; vehicle bytes={scan}"
        )
    jet = bool(stored_u32(data, JET_HEADER) & 1)
    jet_name = "Skydive" if game == "Autobots" else "G1 Starscream"
    lines.append(f"Shared {jet_name} flag: {'enabled' if jet else 'disabled'}")
    return "\n".join(lines)


def cli(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Enable the four online vehicles and optional bonus Jet in either "
                    "Transformers DS game. Original input is never modified."
    )
    parser.add_argument("file", help="Input 512-byte .sav file")
    parser.add_argument("--slot", choices=("A", "B", "both"),
                        help="Player record to edit (required unless --inspect)")
    parser.add_argument("-o", "--output", help="New .sav output filename (never overwritten)")
    parser.add_argument("--no-jet", dest="jet", action="store_false", default=True,
                        help="Only unlock online vehicles; do not enable Skydive/G1 Starscream")
    parser.add_argument("--no-online", dest="online", action="store_false", default=True,
                        help="Enable only the Jet; leave online vehicle flags unchanged")
    parser.add_argument("--inspect", action="store_true", help="Display metadata and validate CRCs without editing")
    args = parser.parse_args(argv)
    try:
        source = Path(args.file).expanduser()
        original = source.read_bytes()
        print(description(original))
        if args.inspect:
            return 0
        if args.slot is None:
            parser.error("--slot is required when creating a patched save")
        modified, changes = patch(original, slot=args.slot, online=args.online, jet=args.jet)
        destination = (Path(args.output).expanduser() if args.output else
                       source.with_name(default_name(source, args.slot, args.online, args.jet)))
        write_new(source, destination, modified)
        print(f"\nNew save: {destination}")
        print(f"Changed bytes: {len(changes)} (including any CRC bytes)")
        for index, before, after in changes:
            print(f"  0x{index:03X}: {before:02X} -> {after:02X}")
        if args.jet:
            print("Note: the bonus Jet flag is shared by both Save A and Save B.")
        print("Result: validated; the original file was not changed.")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def gui() -> int:
    """Tkinter interface; imported only when run with no arguments."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("Tkinter is not installed. Use the command-line interface (--help).", file=sys.stderr)
        return 2

    root = tk.Tk()
    root.title("Transformers DS Vehicle Unlocker")
    root.geometry("640x460")
    root.minsize(580, 420)
    pane = ttk.Frame(root, padding=18)
    pane.pack(fill="both", expand=True)
    ttk.Label(pane, text="Transformers DS Vehicle Unlocker", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(pane, text="For 512-byte Autobots and Decepticons .sav files. Originals are never overwritten.",
              wraplength=565).pack(anchor="w", pady=(2, 13))
    info_var = tk.StringVar(value="Choose your .sav file to identify the game and player profiles.")
    file_var = tk.StringVar()
    slot_var = tk.StringVar(value="B")
    online_var = tk.BooleanVar(value=True)
    jet_var = tk.BooleanVar(value=True)
    selected = {"source": None}

    file_row = ttk.Frame(pane)
    file_row.pack(fill="x")
    ttk.Entry(file_row, textvariable=file_var, state="readonly").pack(side="left", fill="x", expand=True)

    def choose_file() -> None:
        filename = filedialog.askopenfilename(
            title="Select Transformers Nintendo DS save",
            filetypes=[("Nintendo DS save", "*.sav"), ("All files", "*.*")],
        )
        if not filename:
            return
        path = Path(filename)
        file_var.set(str(path))
        try:
            data = path.read_bytes()
            info_var.set(description(data))
            selected["source"] = path
            create_btn.configure(state="normal")
        except (ValueError, OSError) as exc:
            selected["source"] = None
            create_btn.configure(state="disabled")
            info_var.set(f"Cannot use this file:\n{exc}")

    ttk.Button(file_row, text="Browse...", command=choose_file).pack(side="left", padx=(8, 0))
    info_box = ttk.LabelFrame(pane, text="Save details", padding=(10, 7))
    info_box.pack(fill="x", pady=(12, 10))
    ttk.Label(info_box, textvariable=info_var, justify="left", wraplength=540).pack(anchor="w")

    slots = ttk.LabelFrame(pane, text="Profile to unlock", padding=(10, 7))
    slots.pack(fill="x", pady=(0, 10))
    for label, value in (("Save A", "A"), ("Save B", "B"), ("Both", "both")):
        ttk.Radiobutton(slots, text=label, variable=slot_var, value=value).pack(side="left", padx=(0, 26))

    options = ttk.Frame(pane)
    options.pack(fill="x")
    ttk.Checkbutton(options, text="Four online-exclusive vehicles", variable=online_var).pack(anchor="w")
    ttk.Checkbutton(options, text="Bonus Jet: Skydive / G1 Starscream (shared by both profiles)",
                    variable=jet_var).pack(anchor="w")

    def create() -> None:
        source = selected["source"]
        if source is None:
            return
        slot = slot_var.get()
        online, jet = online_var.get(), jet_var.get()
        try:
            original = source.read_bytes()
            modified, changes = patch(original, slot=slot, online=online, jet=jet)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Unable to patch save", str(exc))
            return
        proposed = default_name(source, slot, online, jet)
        target = filedialog.asksaveasfilename(
            title="Save patched copy as", initialdir=str(source.parent),
            initialfile=proposed,
            defaultextension=".sav", filetypes=[("Nintendo DS save", "*.sav")],
        )
        if not target:
            return
        try:
            write_new(source, Path(target), modified)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to create output", str(exc))
            return
        lines = [f"Created: {target}", f"Changed {len(changes)} byte(s), including checksums.",
                 "All three CRCs verified. Original save preserved."]
        if jet:
            lines.append("Note: bonus Jet unlock is shared by both profiles.")
        messagebox.showinfo("Patched save created", "\n".join(lines))

    create_btn = ttk.Button(pane, text="Create unlocked copy...", command=create, state="disabled")
    create_btn.pack(anchor="e", pady=(12, 0))
    root.mainloop()
    return 0


def main() -> int:
    if len(sys.argv) == 1:
        return gui()
    return cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
