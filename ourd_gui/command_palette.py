from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class PaletteCommand:
    command_id: str
    label: str
    category: str
    description: str
    action: Callable[[], None]

    @property
    def search_text(self) -> str:
        return " ".join(
            (self.command_id, self.label, self.category, self.description)
        ).casefold()


class CommandPaletteRegistry:
    def __init__(self, commands: Iterable[PaletteCommand] = ()) -> None:
        self._commands: dict[str, PaletteCommand] = {}
        for command in commands:
            self.register(command)

    def register(self, command: PaletteCommand) -> None:
        if command.command_id in self._commands:
            raise ValueError(f"duplicate palette command: {command.command_id}")
        self._commands[command.command_id] = command

    def list(self) -> tuple[PaletteCommand, ...]:
        return tuple(
            sorted(
                self._commands.values(),
                key=lambda item: (item.category.casefold(), item.label.casefold()),
            )
        )

    def search(self, query: str) -> tuple[PaletteCommand, ...]:
        terms = tuple(part for part in query.casefold().split() if part)
        if not terms:
            return self.list()
        return tuple(
            command
            for command in self.list()
            if all(term in command.search_text for term in terms)
        )

    def execute(self, command_id: str) -> None:
        try:
            command = self._commands[command_id]
        except KeyError as exc:
            raise KeyError(f"unknown palette command: {command_id}") from exc
        command.action()
