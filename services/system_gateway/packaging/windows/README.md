# System Gateway Windows Packaging

System Gateway is a Python-native service. Windows service support is not yet
implemented; the current recommended approach is to run it in the foreground
inside a scheduled task or a third-party service wrapper.

## Manual install

1. Install the package:

   ```powershell
   python -m pip install -e services\system_gateway
   ```

2. Generate a shared secret once:

   ```powershell
   python -m system_gateway pair --secret-file %LOCALAPPDATA%\system-gateway\secret
   ```

3. Set the environment variable before starting the service:

   ```powershell
   $env:SYSTEM_GATEWAY_SHARED_SECRET_FILE = "$env:LOCALAPPDATA\system-gateway\secret"
   $env:SYSTEM_GATEWAY_HOST = "127.0.0.1"
   $env:SYSTEM_GATEWAY_PORT = "8380"
   ```

   > **Note:** `scripts/bootstrap_system_gateway.py` writes the Windows secret
   > to `C:\ProgramData\system-gateway\secret`, while the manual `pair` command
   > above defaults to `%LOCALAPPDATA%\system-gateway\secret`. Pick one location
   > and set `SYSTEM_GATEWAY_SHARED_SECRET_FILE` consistently for both the
   > service and the CLI.

4. Run the gateway:

   ```powershell
   python -m system_gateway run
   ```

## Running as a Windows service

Use a service wrapper such as `NSSM` or `WinSW`, or implement a
`pywin32` service harness in `services/system_gateway/packaging/windows/`
as a follow-up. The harness should:

* set `SYSTEM_GATEWAY_SHARED_SECRET_FILE` to a protected path,
* bind to `127.0.0.1:8380`,
* forward stdout/stderr to Event Log or a log file,
* refuse to start if the secret file is missing or world-readable
  (recommended behavior for a future harness; the current Python service
  starts without a secret and only rejects mutating requests).

## Security notes

* Do not store `SYSTEM_GATEWAY_SHARED_SECRET` directly in the Windows Registry
  or in a world-readable scheduled-task XML file.
* Restrict the secret file to the account that runs the service.
* The gateway binds to localhost by default; do not expose it to the network.
