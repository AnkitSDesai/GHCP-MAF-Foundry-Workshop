"""Wrapper for GitHub Actions: run src/evaluate.py unmodified.

Workshop participants do not have Entra directory permissions (to create an App / SP),
so as the means to authenticate to Foundry from GitHub Actions, we pass **your own user
access token** via a GitHub Secret.

Run the following locally once beforehand (valid 60-90 minutes):

    az login
    gh secret set AZURE_AI_AUTH_TOKEN --body "$(az account get-access-token \
        --scope https://ai.azure.com/.default --query accessToken -o tsv)"

The workflow only passes AZURE_AI_AUTH_TOKEN to this script via env, and does not
touch the evaluation body (src/evaluate.py) at all.
"""

from __future__ import annotations

import os
import sys
import time

import azure.identity
from azure.core.credentials import AccessToken


class _StaticTokenCredential:
    """A minimal TokenCredential-compatible class that just returns the token passed via env."""

    def __init__(self, token: str, lifetime_seconds: int = 3600) -> None:
        self._token = token
        self._expires_on = int(time.time()) + lifetime_seconds

    def get_token(self, *scopes, **kwargs):
        return AccessToken(self._token, self._expires_on)


def _install_credential() -> None:
    token = os.environ.get("AZURE_AI_AUTH_TOKEN")
    if not token:
        sys.stderr.write(
            "ERROR: AZURE_AI_AUTH_TOKEN is unset. Pass it from the workflow env.\n"
        )
        sys.exit(1)
    # Swap out the place where src/evaluate.py calls AzureCliCredential()
    azure.identity.AzureCliCredential = (
        lambda *args, **kwargs: _StaticTokenCredential(token)
    )


def main() -> None:
    _install_credential()
    script = os.path.join("src", "evaluate.py")
    with open(script, encoding="utf-8") as fp:
        code = fp.read()
    # src/evaluate.py resolves the .env path from __file__, so pass it in exec globals
    exec(compile(code, script, "exec"), {"__name__": "__main__", "__file__": script})


if __name__ == "__main__":
    main()
