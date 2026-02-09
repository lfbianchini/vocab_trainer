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
    print(f"imported {len(items)} items -> {csv_path}")


# ------------------------
# Trainer
# ------------------------

class Trainer:
    def __init__(self, items: List[VocabItem], *, reverse: bool = False, no_replacement: bool = False):
        self.items = items
        self.reverse = reverse
        self.no_replacement = no_replacement
        self.remaining = items.copy() if no_replacement else []

    def pick(self) -> VocabItem:
        if self.no_replacement:
            if not self.remaining:
                print("\nyou've completed all vocab items")
                return None
            weights = [item.weight for item in self.remaining]
            item = random.choices(self.remaining, weights=weights, k=1)[0]
            self.remaining.remove(item)
            return item
        else:
            weights = [item.weight for item in self.items]
            return random.choices(self.items, weights=weights, k=1)[0]

    def prompt(self, item: VocabItem):
        clear_screen()

        question = item.value if self.reverse else item.key
        answer = item.key if self.reverse else item.value

        user = input(f"{question} -> ").strip()

        correct = user == answer
        if correct:
            print("\ncorrect")
            item.mark_correct()
        else:
            print(f"\nwrong -> {answer}")
            item.mark_wrong()

        print("\npress any key for next...")
        wait_for_key()

    def run(self):
        print("ctrl+c to quit.\n")
        if self.no_replacement:
            print(f"quiz mode: {len(self.remaining)} items\n")
        
        while True:
            item = self.pick()
            if item is None:
                break
            self.prompt(item)


# ------------------------
# CLI
# ------------------------

def usage():
    print(
        """
usage:
  python vocab_trainer.py import vocab.txt
  python vocab_trainer.py train vocab.csv [more.csv ...] [--reverse] [--no-replacement]

options:
  --reverse          quiz value -> key instead of key -> value
  --no-replacement   each item appears only once per session

format for vocab.txt:
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
            print("file not found.")
            sys.exit(1)
        csv_path = path.with_suffix(".csv")
        import_vocab(path, csv_path)

    elif command == "train":
        paths = [Path(p) for p in sys.argv[2:] if not p.startswith("--")]
        reverse = "--reverse" in sys.argv
        no_replacement = "--no-replacement" in sys.argv

        if not paths:
            usage()

        items: List[VocabItem] = []

        for p in paths:
            if not p.exists():
                print(f"file not found: {p}")
                sys.exit(1)
            items.extend(VocabStore(p).load())

        trainer = Trainer(items, reverse=reverse, no_replacement=no_replacement)

        def handle_exit(sig, frame):
            clear_screen()
            print("saving progress...")
            save_grouped(items)
            print("done.")
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_exit)
        trainer.run()

    else:
        usage()


if __name__ == "__main__":
    main()