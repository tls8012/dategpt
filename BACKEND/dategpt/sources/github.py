from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class GitHubSource:
    owner: str
    repo: str
    ref: str
    subpath: str = ""

    @property
    def clone_url(self) -> str:
        return "https://github.com/{}/{}.git".format(
            self.owner,
            self.repo,
        )

    @property
    def ssh_url(self) -> str:
        return "git@github.com:{}/{}.git".format(
            self.owner,
            self.repo,
        )

    @property
    def cache_key(self) -> str:
        digest = hashlib.sha256(
            "{}:{}:{}".format(
                self.owner,
                self.repo,
                self.ref,
            ).encode("utf-8")
        ).hexdigest()[:12]
        return "{}-{}".format(
            self.ref.replace("/", "_"),
            digest,
        )


def parse_github_source_url(
    value: str,
) -> GitHubSource:
    text = str(value).strip()
    parsed = urlparse(text)

    if parsed.scheme != "https":
        raise ValueError(
            "GitHub source URL must use https"
        )
    if parsed.hostname != "github.com":
        raise ValueError(
            "only github.com source URLs are supported"
        )
    if parsed.username or parsed.password:
        raise ValueError(
            "credentials must not be embedded in GitHub URLs"
        )

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]
    if len(parts) < 2:
        raise ValueError(
            "GitHub source URL must include owner/repository"
        )

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    ref = "main"
    subpath = ""

    if len(parts) > 2:
        if parts[2] != "tree":
            raise ValueError(
                "GitHub URL must be a repository root or /tree/<ref>/<path>"
            )
        if len(parts) < 4:
            raise ValueError(
                "GitHub tree URL is missing a ref"
            )

        ref = parts[3]
        subpath = "/".join(parts[4:])

    return GitHubSource(
        owner=owner,
        repo=repo,
        ref=ref,
        subpath=subpath,
    )


class GitHubSourceResolver:
    """Materialize GitHub tree URLs through the local git client.

    DateGPT does not store GitHub credentials. git inherits the user's normal
    credential helper environment, so private repositories work when ordinary
    command-line git access already works on the machine.
    """

    def __init__(
        self,
        root: Path,
        *,
        git_binary: Optional[str] = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.git_binary = (
            git_binary
            or shutil.which("git")
            or "git"
        )
        self.timeout_seconds = timeout_seconds

    def materialize(
        self,
        source_url: str,
        *,
        refresh: bool = True,
    ) -> Path:
        source = parse_github_source_url(
            source_url
        )

        checkout = (
            self.root
            / source.owner
            / source.repo
            / source.cache_key
        ).resolve()
        checkout.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if checkout.is_dir() and (
            checkout / ".git"
        ).is_dir():
            if refresh:
                self._refresh(
                    checkout,
                    source,
                )
        else:
            self._clone(
                checkout,
                source,
            )

        resolved = checkout
        if source.subpath:
            resolved = (
                checkout
                / Path(source.subpath)
            ).resolve()

            try:
                resolved.relative_to(checkout)
            except ValueError as exc:
                raise ValueError(
                    "GitHub source subpath escapes checkout"
                ) from exc

        if not resolved.is_dir():
            raise FileNotFoundError(
                "GitHub source path not found after checkout: {}".format(
                    source.subpath or "."
                )
            )

        return resolved

    def _clone(
        self,
        checkout: Path,
        source: GitHubSource,
    ) -> None:
        temp = checkout.parent / (
            ".{}.clone-{}".format(
                checkout.name,
                uuid.uuid4().hex,
            )
        )

        if temp.exists():
            shutil.rmtree(temp)

        try:
            clone_args = [
                self.git_binary,
                "clone",
                "--depth",
                "1",
                "--branch",
                source.ref,
                "--single-branch",
            ]

            try:
                self._run(
                    clone_args
                    + [
                        source.clone_url,
                        str(temp),
                    ]
                )
            except RuntimeError as https_error:
                if temp.exists():
                    shutil.rmtree(temp)

                try:
                    self._run(
                        clone_args
                        + [
                            source.ssh_url,
                            str(temp),
                        ]
                    )
                except RuntimeError as ssh_error:
                    raise RuntimeError(
                        "GitHub clone failed over HTTPS and SSH. "
                        "HTTPS: {} | SSH: {}".format(
                            https_error,
                            ssh_error,
                        )
                    ) from ssh_error

            if checkout.exists():
                shutil.rmtree(checkout)

            os.replace(temp, checkout)
        finally:
            if temp.exists():
                shutil.rmtree(temp)

    def _refresh(
        self,
        checkout: Path,
        source: GitHubSource,
    ) -> None:
        self._run(
            [
                self.git_binary,
                "-C",
                str(checkout),
                "fetch",
                "--depth",
                "1",
                "origin",
                source.ref,
            ]
        )
        self._run(
            [
                self.git_binary,
                "-C",
                str(checkout),
                "reset",
                "--hard",
                "FETCH_HEAD",
            ]
        )
        self._run(
            [
                self.git_binary,
                "-C",
                str(checkout),
                "clean",
                "-fdx",
            ]
        )

    def _run(
        self,
        args,
    ) -> None:
        try:
            completed = subprocess.run(
                list(args),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "git executable not found: {}".format(
                    self.git_binary
                )
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "git operation timed out after {} seconds".format(
                    self.timeout_seconds
                )
            ) from exc

        if completed.returncode != 0:
            detail = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or "git exited with code {}".format(
                    completed.returncode
                )
            )
            raise RuntimeError(
                "git source fetch failed: {}".format(
                    detail
                )
            )
