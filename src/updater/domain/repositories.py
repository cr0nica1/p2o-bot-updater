from __future__ import annotations

from typing import Protocol

from updater.domain.models import Target, TargetVersion, TargetVulnerability, Vulnerability


class TargetRepository(Protocol):
    def upsert(self, target: Target) -> Target: ...
    def list_all(self) -> list[Target]: ...
    def find_by_name(self, name: str) -> Target | None: ...


class TargetVersionRepository(Protocol):
    def upsert(self, version: TargetVersion) -> TargetVersion: ...


class VulnerabilityRepository(Protocol):
    def upsert(self, vulnerability: Vulnerability) -> Vulnerability: ...
    def list_all(self) -> list[Vulnerability]: ...


class TargetVulnerabilityRepository(Protocol):
    def upsert(self, link: TargetVulnerability) -> TargetVulnerability: ...
    def list_all(self) -> list[TargetVulnerability]: ...


class VulnerabilitySource(Protocol):
    source_name: str

    def search(self, target: Target, query: str) -> list[tuple[Vulnerability, dict]]: ...
