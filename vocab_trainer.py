#!/usr/bin/env python3
"""
Weighted CLI vocabulary trainer.

Features:
- Import vocab from simple key,value text files
- Stores progress in CSV
- Weighted random selection (missed items appear more often)
- Direction toggle (key->value or value->key)
- Multi-file training
- Screen clears between questions
- Limbo state: shows result, waits for keypress
- Ctrl+C clean exit with autosave
"""

from __future__ import annotations
import csv
import random
import sys
import signal
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict


# ------------------------
# Terminal helpers
# ------------------------

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def wait_for_key():
    """Wait for a single keypress (no Enter required)."""
    try:
        # Windows
        import msvcrt
        msvcrt.getch()
    except ImportError:
        # Unix
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ------------------------
# Data model
# ------------------------

@dataclass
class VocabItem:
    key: str
    value: str
    correct: int = 0
    wrong: int = 0
    weight: float = 1.0
    source: Path | None = field(default=None, repr=False)

    def mark_correct(self):
        self.correct += 1
        self.weight = max(0.3, self.weight * 0.7)

    def mark_wrong(self):
        self.wrong += 1
        self.weight = min(10.0, self.weight * 1.5)


# ------------------------
# Persistence
# ------------------------

class VocabStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> List[VocabItem]:
        items = []
        with self.path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(
                    VocabItem(
                        key=row["key"],
                        value=row["value"],
                        correct=int(row["correct"]),
                        wrong=int(row["wrong"]),
                        weight=float(row["weight"]),
                        source=self.path,
                    )
                )
        return items

    def save(self, items: List[VocabItem]):
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["key", "value", "correct", "wrong", "weight"]
            )
            writer.writeheader()
            for item in items:
                writer.writerow(
                    {
                        "key": item.key,
                        "value": item.value,
                        "correct": item.correct,
                        "wrong": item.wrong,
                        "weight": f"{item.weight:.4f}",
                    }
                )


def save_grouped(items: List[VocabItem]):
    """Save vocab items back to their original CSV files."""
    by_file: Dict[Path, List[VocabItem]] = {}
    for item in items:
        if item.source is None:
            continue
        by_file.setdefault(item.source, []).append(item)

    for path, group in by_file.items():
        VocabStore(path).save(group)


# ------------------------
# Import
# ------------------------

def import_vocab(txt_path: Path, csv_path: Path):
    """
    Import from:
        word,translation
    into:
        key,value,correct,wrong,weight
    """
    items = []
    with txt_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = map(str.strip, line.split(",", 1))
            items.append(VocabItem(key=key, value=value))

    store = VocabStore(csv_path)
    store.save(items)
    print(f"Imported {len(items)} items → {csv_path}")


# ------------------------
# Trainer
# ------------------------

class Trainer:
    def __init__(self, items: List[VocabItem], *, reverse: bool = False):
        self.items = items
        self.reverse = reverse

    def pick(self) -> VocabItem:
        weights = [item.weight for item in self.items]
        return random.choices(self.items, weights=weights, k=1)[0]

    def prompt(self, item: VocabItem):
        clear_screen()

        question = item.value if self.reverse else item.key
        answer = item.key if self.reverse else item.value

        user = input(f"{question} → ").strip()

        correct = user == answer
        if correct:
            print("\n✓ Correct")
            item.mark_correct()
        else:
            print(f"\n✗ Wrong → {answer}")
            item.mark_wrong()

        print("\nPress any key for next...")
        wait_for_key()

    def run(self):
        print("Ctrl+C to quit.\n")
        while True:
            item = self.pick()
            self.prompt(item)


# ------------------------
# CLI
# ------------------------

def usage():
    print(
        """
Usage:
  python vocab_trainer.py import vocab.txt
  python vocab_trainer.py train vocab.csv [more.csv ...] [--reverse]

Format for vocab.txt:
  doctor,isha
  nurse,kangoshi
"""
    )
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        usage()

    command = sys.argv[1]

    if command == "import":
        path = Path(sys.argv[2])
        if not path.exists():
            print("File not found.")
            sys.exit(1)
        csv_path = path.with_suffix(".csv")
        import_vocab(path, csv_path)

    elif command == "train":
        paths = [Path(p) for p in sys.argv[2:] if not p.startswith("--")]
        reverse = "--reverse" in sys.argv

        if not paths:
            usage()

        items: List[VocabItem] = []

        for p in paths:
            if not p.exists():
                print(f"File not found: {p}")
                sys.exit(1)
            items.extend(VocabStore(p).load())

        trainer = Trainer(items, reverse=reverse)

        def handle_exit(sig, frame):
            clear_screen()
            print("Saving progress...")
            save_grouped(items)
            print("Done.")
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_exit)
        trainer.run()

    else:
        usage()


if __name__ == "__main__":
    main()
